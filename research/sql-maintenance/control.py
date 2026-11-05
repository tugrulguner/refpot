#!/usr/bin/env python3
"""Frozen SQLite incremental-maintenance control for maintained-SQL slice.

Only stdlib SQLite; source table/aggregate/trigger SQL is generated from a small
fixture descriptor. Full Python recomputation is the correctness oracle, not the
maintenance implementation.
"""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "workload.json"
EVIDENCE_PATH = HERE / "evidence" / "sqlite-control.json"

FIXTURES = {
    "capacity": {"dimensions": [(1, 11, 1), (2, 9, 1), (3, 12, 1)],
                 "facts": [(1, 1, 3), (2, 1, 2), (3, 2, 4), (4, 3, 5)],
                 "limit_label": "capacity", "rate_label": "unit"},
    "pricing": {"dimensions": [(1, 10000, 7), (2, 10000, 11), (3, 10000, 5)],
                "facts": [(1, 1, 2), (2, 1, 3), (3, 2, 4), (4, 3, 6)],
                "limit_label": "revenue_ceiling", "rate_label": "unit_price"},
}


def create_fixture(conn: sqlite3.Connection, name: str) -> None:
    d = FIXTURES[name]
    conn.executescript('''
      CREATE TABLE dimension (id INTEGER PRIMARY KEY, ceiling INTEGER NOT NULL, rate INTEGER NOT NULL);
      CREATE TABLE fact (id INTEGER PRIMARY KEY, dimension_id INTEGER NOT NULL REFERENCES dimension(id), amount INTEGER NOT NULL);
      CREATE TABLE maintained (dimension_id INTEGER PRIMARY KEY, total INTEGER NOT NULL, n INTEGER NOT NULL, amount_sum INTEGER NOT NULL);
      CREATE INDEX fact_dimension_idx ON fact(dimension_id);
    ''')
    conn.executemany("INSERT INTO dimension VALUES (?, ?, ?)", d["dimensions"])
    conn.executemany("INSERT INTO maintained VALUES (?,0,0,0)", [(x[0],) for x in d["dimensions"]])
    conn.executemany("INSERT INTO fact VALUES (?, ?, ?)", d["facts"])
    # One generic aggregate shape: SUM(fact.amount * dimension.rate), COUNT(*).
    # Parent updates maintain their group's total; child updates handle both old
    # and new groups. The ordinary view is intentionally not materialized.
    conn.executescript('''
      CREATE TRIGGER fact_ai AFTER INSERT ON fact BEGIN
        UPDATE maintained SET amount_sum=amount_sum+NEW.amount,
          total=(amount_sum+NEW.amount)*(SELECT rate FROM dimension WHERE id=NEW.dimension_id), n=n+1 WHERE dimension_id=NEW.dimension_id;
      END;
      CREATE TRIGGER fact_ad AFTER DELETE ON fact BEGIN
        UPDATE maintained SET amount_sum=amount_sum-OLD.amount,
          total=(amount_sum-OLD.amount)*(SELECT rate FROM dimension WHERE id=OLD.dimension_id), n=n-1 WHERE dimension_id=OLD.dimension_id;
      END;
      CREATE TRIGGER fact_au AFTER UPDATE ON fact BEGIN
        UPDATE maintained SET amount_sum=amount_sum-OLD.amount,
          total=(amount_sum-OLD.amount)*(SELECT rate FROM dimension WHERE id=OLD.dimension_id), n=n-1 WHERE dimension_id=OLD.dimension_id;
        UPDATE maintained SET amount_sum=amount_sum+NEW.amount,
          total=(amount_sum+NEW.amount)*(SELECT rate FROM dimension WHERE id=NEW.dimension_id), n=n+1 WHERE dimension_id=NEW.dimension_id;
      END;
      CREATE TRIGGER dimension_au AFTER UPDATE OF rate ON dimension BEGIN
        UPDATE maintained SET total=amount_sum*NEW.rate WHERE dimension_id=NEW.id;
      END;
      CREATE VIEW joined_result AS
        SELECT f.id AS fact_id, f.dimension_id AS dimension_id, f.amount AS amount,
               d.rate AS rate, f.amount*d.rate AS extended
        FROM fact AS f JOIN dimension AS d ON d.id=f.dimension_id;
      CREATE VIEW violations AS
        SELECT m.dimension_id, m.total, d.ceiling FROM maintained AS m
        JOIN dimension AS d ON d.id=m.dimension_id WHERE m.total>d.ceiling;
    ''')
    conn.execute("UPDATE maintained SET amount_sum=COALESCE((SELECT SUM(f.amount) FROM fact f WHERE f.dimension_id=maintained.dimension_id),0), total=COALESCE((SELECT SUM(f.amount*d.rate) FROM fact f JOIN dimension d ON d.id=f.dimension_id WHERE d.id=maintained.dimension_id),0), n=(SELECT COUNT(*) FROM fact f WHERE f.dimension_id=maintained.dimension_id)")
    conn.commit()


class DeferredDB:
    """Minimal explicit transaction wrapper with final-state assertion checks."""
    def __init__(self, conn):
        self.conn = conn
        self.active = False
        self.aborted = False
    def begin(self):
        if self.active: raise RuntimeError("transaction already active")
        self.conn.execute("BEGIN")
        self.active, self.aborted = True, False
    def execute(self, sql, params=()):
        if not self.active: raise RuntimeError("statement requires transaction")
        if self.aborted: raise RuntimeError("transaction is aborted")
        try:
            return self.conn.execute(sql, params)
        except Exception:
            self.aborted = True
            raise
    def commit(self):
        if not self.active: raise RuntimeError("no active transaction")
        if self.aborted:
            self.conn.rollback(); self.active=False
            raise RuntimeError("ordinary statement error aborted transaction")
        try:
            if self.conn.execute("SELECT EXISTS(SELECT 1 FROM violations)").fetchone()[0]:
                raise ValueError("deferred assertion violations is not empty")
            self.conn.commit(); self.active=False
        except Exception:
            self.conn.rollback(); self.active=False
            raise
    def rollback(self):
        if self.active: self.conn.rollback(); self.active=False


def source_rows(conn):
    return {"dimension": [list(r) for r in conn.execute("SELECT id,ceiling,rate FROM dimension ORDER BY id")],
            "fact": [list(r) for r in conn.execute("SELECT id,dimension_id,amount FROM fact ORDER BY id")]}

def expected_state(src):
    dims={r[0]:r for r in src["dimension"]}
    totals={k:[0,0] for k in dims}
    for _fid, did, amount in src["fact"]:
        if did not in dims: raise AssertionError("orphan fact in independent oracle")
        totals[did][0] += amount*dims[did][2]
        totals[did][1] += 1
    maintained=[[k,*totals[k]] for k in sorted(totals)]
    joined=sorted([[fid,did,amount,dims[did][2],amount*dims[did][2]] for fid,did,amount in src["fact"]])
    violations=sorted([[k,totals[k][0],dims[k][1]] for k in dims if totals[k][0]>dims[k][1]])
    return {"maintained":maintained,"joined_result":joined,"violations":violations}

def verify(conn, context):
    src=source_rows(conn); exp=expected_state(src)
    internal_expected={k:sum(amount for _fid,did,amount in src["fact"] if did==k) for k,_,_ in src["dimension"]}
    internal_actual={r[0]:r[1] for r in conn.execute("SELECT dimension_id,amount_sum FROM maintained ORDER BY dimension_id")}
    if internal_actual != internal_expected: raise AssertionError(f"incremental amount-sum mismatch after {context}: expected={internal_expected} actual={internal_actual}")
    got={"maintained":[list(r) for r in conn.execute("SELECT dimension_id,total,n FROM maintained ORDER BY dimension_id")],
         "joined_result":[list(r) for r in conn.execute("SELECT fact_id,dimension_id,amount,rate,extended FROM joined_result ORDER BY fact_id")],
         "violations":[list(r) for r in conn.execute("SELECT dimension_id,total,ceiling FROM violations ORDER BY dimension_id")]}
    if exp != got: raise AssertionError(f"oracle mismatch after {context}: expected={exp} actual={got}")
    return src, got

def apply_op(tx, op):
    kind=op["op"]
    if kind=="insert_fact": tx.execute("INSERT INTO fact VALUES (?,?,?)",(op["id"],op["dimension"],op["amount"]))
    elif kind=="delete_fact": tx.execute("DELETE FROM fact WHERE id=?",(op["id"],))
    elif kind=="update_fact": tx.execute("UPDATE fact SET dimension_id=?,amount=? WHERE id=?",(op["dimension"],op["amount"],op["id"]))
    elif kind=="update_dimension": tx.execute("UPDATE dimension SET rate=?,ceiling=? WHERE id=?",(op["rate"],op["ceiling"],op["id"]))
    elif kind=="ordinary_error": tx.execute("INSERT INTO fact VALUES (?,?,?)",(op["id"],999999,op["amount"]))
    else: raise ValueError(f"unknown workload operation {kind}")

def apply_plan_fixture(name, txns, check_each=True):
    conn=sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    create_fixture(conn,name); wrapper=DeferredDB(conn)
    verify(conn,"fixture construction")
    checks=0; accepted=0; rejected=0; history=[]
    for ti, txn in enumerate(txns):
        wrapper.begin(); error=None
        try:
            for op in txn["ops"]: apply_op(wrapper,op)
            try: wrapper.commit()
            except (ValueError,RuntimeError) as exc: error=str(exc)
        except Exception as exc:
            error=str(exc); wrapper.rollback()
        expected_reject=txn.get("outcome","accept") == "reject"
        if txn.get("outcome") == "rollback":
            wrapper.rollback(); error=None
        if bool(error) != expected_reject:
            raise AssertionError(f"{name} txn {ti} expected {'reject' if expected_reject else 'accept'}, got {error!r}")
        accepted += not bool(error); rejected += bool(error)
        if check_each:
            src, derived = verify(conn,f"{name} txn {ti} outcome={txn.get('outcome','accept')}")
            history.append({"id":txn["id"],"outcome":txn.get("outcome","accept"),"source_rows":src,"derived_rows":derived})
            checks+=1
    return conn, {"transactions":len(txns),"accepted":accepted,"rejected":rejected,"oracle_checks":checks,"history":history}

def frozen_plan():
    # Fixed workload and seeds are persisted, not regenerated during the run.
    return json.loads(PLAN_PATH.read_text())

def run_control():
    plan=frozen_plan(); records=[]
    for name in plan["fixtures"]:
        start=time.perf_counter_ns()
        conn,stats=apply_plan_fixture(name,plan["workloads"][name])
        elapsed=time.perf_counter_ns()-start
        src,derived=verify(conn,f"{name} final")
        records.append({"fixture":name,"stats":stats,"elapsed_ns_including_setup_oracle_and_workload":elapsed,
                        "source_rows":src,"derived_rows":derived})
        conn.close()
    return {"format":"maintained-sql-sqlite-control-v1","plan_sha256":__import__('hashlib').sha256(PLAN_PATH.read_bytes()).hexdigest(),
            "python":sys.version,"sqlite":sqlite3.sqlite_version,"records":records}

def validate_evidence(path):
    data=json.loads(Path(path).read_text()); plan=frozen_plan()
    if data["plan_sha256"] != __import__('hashlib').sha256(PLAN_PATH.read_bytes()).hexdigest(): raise AssertionError("plan hash mismatch")
    if [r["fixture"] for r in data["records"]] != plan["fixtures"]: raise AssertionError("fixture set/order mismatch")
    total=0
    for rec in data["records"]:
        expected=expected_state(rec["source_rows"])
        if expected != rec["derived_rows"]: raise AssertionError(f"persisted rows fail Python recomputation: {rec['fixture']}")
        txns=plan["workloads"][rec["fixture"]]
        n=len(txns)
        if rec["stats"]["oracle_checks"] != n or len(rec["stats"]["history"]) != n: raise AssertionError("oracle check count mismatch")
        for txn,snapshot in zip(txns,rec["stats"]["history"]):
            if snapshot["id"] != txn["id"] or snapshot["outcome"] != txn.get("outcome","accept"):
                raise AssertionError("transaction evidence identity/outcome mismatch")
            if expected_state(snapshot["source_rows"]) != snapshot["derived_rows"]:
                raise AssertionError(f"per-transaction evidence fails Python recomputation: {rec['fixture']} {txn['id']}")
        total+=n
    return {"fixtures":len(data["records"]),"transactions_validated":total,"evidence":"valid"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--write-baseline",action="store_true")
    p.add_argument("--validate",action="store_true")
    p.add_argument("--candidate-python",help="Explicit Python executable for parent-built candidate; not run by default")
    args=p.parse_args()
    if args.write_baseline:
        result=run_control(); EVIDENCE_PATH.parent.mkdir(parents=True,exist_ok=True); EVIDENCE_PATH.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        print(json.dumps({"written":str(EVIDENCE_PATH),"validation":validate_evidence(EVIDENCE_PATH)},indent=2)); return
    if args.validate:
        print(json.dumps(validate_evidence(EVIDENCE_PATH),indent=2)); return
    if args.candidate_python:
        subprocess.run([args.candidate_python,str(HERE/"candidate_adapter.py"),"--plan",str(PLAN_PATH)],check=True)
        return
    result=run_control(); print(json.dumps(result,indent=2,sort_keys=True))

if __name__=="__main__": main()
