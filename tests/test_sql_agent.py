"""Agent protocol tests use explicit fixtures, not language interpreters."""

import pytest

from refpot.sql import Database


def test_agent_query_uses_same_result_and_native_readonly_path():
    from refpot.agent import AgentConfig, QueryProposal

    requests = []

    def generator(request):
        requests.append(request)
        return QueryProposal("SELECT id FROM items WHERE quantity > ? ORDER BY id", (5,))

    config = AgentConfig(generator=generator, relations=("items",), disclose_schema=True)
    with Database(agent=config) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, quantity INTEGER NOT NULL)")
        db.execute("CREATE TABLE secret (id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO items VALUES (1, 8)")
        db.execute("INSERT INTO items VALUES (2, 3)")
        result = db.execute(query="Which items exceed five?", agent=True)
        assert result.rows == ((1,),)
        assert result.columns == ("id",)
        assert result.affected == 0
        assert result.generation is not None
        assert result.generation.query == "SELECT id FROM items WHERE quantity > ? ORDER BY id"
        assert result.generation.parameters == (5,)
        assert len(requests) == 1
        request = requests[0]
        assert request.query == "Which items exceed five?"
        assert tuple(r.name for r in request.relations) == ("items",)
        assert request.relations[0].columns == ("id", "quantity")
        assert not hasattr(request, "rows")
        assert not hasattr(request, "revision")
        assert db.execute("SELECT * FROM items").generation is None


def test_agent_missing_configuration_fails_without_guessing_sql():
    from refpot.agent import AgentError

    with Database() as db, pytest.raises(AgentError, match="configuration"):
        db.execute("SELECT * FROM anything", agent=True)


def test_clarification_and_decline_are_structured_and_do_not_execute():
    from refpot.agent import (
        AgentConfig,
        Clarification,
        ClarificationRequired,
        Decline,
        QueryDeclined,
    )

    for proposal, exception in [
        (Clarification(("What quantity counts as available?",)), ClarificationRequired),
        (Decline("Text columns are not supported"), QueryDeclined),
    ]:
        with Database(
            agent=AgentConfig(lambda request, proposal=proposal: proposal, ("items",), True)
        ) as db:
            db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
            with pytest.raises(exception) as caught:
                db.execute("Find available items", agent=True)
            if isinstance(proposal, Clarification):
                assert caught.value.questions == proposal.questions
            else:
                assert caught.value.reason == proposal.reason
            assert db.execute("SELECT * FROM items").rows == ()


def test_generator_failure_is_distinct_and_does_not_leak_provider_details():
    from refpot.agent import AgentConfig, AgentError

    def fail(request):
        raise ValueError("private-provider-diagnostic")

    with Database(agent=AgentConfig(fail, ("items",), True)) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
        with pytest.raises(AgentError, match="generation failed") as caught:
            db.execute("Count items", agent=True)
        assert "private-provider-diagnostic" not in str(caught.value)
        assert db.execute("SELECT * FROM items").rows == ()


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM items",
        "CREATE TABLE rogue (id INTEGER PRIMARY KEY)",
        "BEGIN",
        "SELECT * FROM secret",
        "SELECT * FROM items; DELETE FROM items",
        "SELECT a.id FROM items AS a JOIN secret AS b ON a.id = b.id",
        "SELECT a.id FROM items AS a WHERE NOT EXISTS (SELECT * FROM secret AS b WHERE b.id = a.id)",
    ],
)
def test_agent_output_cannot_widen_authority(query):
    from refpot.agent import AgentConfig, QueryProposal
    from refpot.sql import SQLError

    with Database(agent=AgentConfig(lambda request: QueryProposal(query), ("items",), True)) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE secret (id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO items VALUES (1)")
        with pytest.raises(SQLError):
            db.execute("irrelevant fixture question", agent=True)
        assert db.execute("SELECT * FROM items").rows == ((1,),)


def test_agent_does_not_enter_generator_in_transaction_or_without_disclosure():
    from refpot.agent import AgentConfig, AgentError

    def forbidden(request):
        pytest.fail("generator must not be called")

    with Database(agent=AgentConfig(forbidden, ("items",), True)) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
        with db.transaction():
            db.execute("INSERT INTO items VALUES (1)")
            with pytest.raises(AgentError, match="transaction"):
                db.execute("Count items", agent=True)
            assert db.execute("SELECT * FROM items").rows == ((1,),)
        assert db.execute("SELECT * FROM items").rows == ((1,),)
    with Database(agent=AgentConfig(forbidden, ("items",))) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
        with pytest.raises(AgentError, match="disclosure"):
            db.execute("Count items", agent=True)


def test_agent_inspection_and_callback_reentrancy():
    from refpot.agent import AgentConfig, QueryProposal

    def generator(request):
        for operation in (lambda: db.execute("DELETE FROM items"), db.close, db.stats):
            with pytest.raises(RuntimeError, match="reentrant"):
                operation()
        return QueryProposal("SELECT * FROM items")

    with Database(agent=AgentConfig(generator, ("items",), True)) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO items VALUES (1)")
        inspected = db.execute("Read items", agent=True, explain=True)
        assert inspected.rows == ()
        assert inspected.generation is not None
        assert inspected.generation.query == "SELECT * FROM items"
        assert db.execute(inspected.generation.query, inspected.generation.parameters).rows == (
            (1,),
        )


@pytest.mark.parametrize("kind", ["questions", "reason", "assumptions"])
def test_agent_metadata_is_bounded_and_immutable(kind):
    from refpot.agent import AgentConfig, AgentError, Clarification, Decline, QueryProposal

    def generator(request):
        if kind == "questions":
            return Clarification(["mutable question"])  # type: ignore[arg-type]
        if kind == "reason":
            return Decline("x" * 65537)
        return QueryProposal("SELECT * FROM items", assumptions=("x" * 65537,))

    with Database(agent=AgentConfig(generator, ("items",), True)) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
        with pytest.raises(AgentError, match="bounded"):
            db.execute("Read items", agent=True)


def test_config_rejects_names_outside_the_native_identifier_byte_limit():
    from refpot.agent import AgentConfig, QueryProposal

    for name in ("a" * 65, "é" * 33):
        with pytest.raises(ValueError, match="64"):
            AgentConfig(lambda request: QueryProposal("SELECT * FROM items"), (name,), True)


def test_authorized_view_does_not_disclose_or_authorize_its_inputs():
    from refpot.agent import AgentConfig, QueryProposal
    from refpot.sql import SQLError

    requests = []
    proposals = iter(
        (QueryProposal("SELECT * FROM visible"), QueryProposal("SELECT * FROM hidden"))
    )

    def generate(request):
        requests.append(request)
        return next(proposals)

    with Database(agent=AgentConfig(generate, ("visible",), True)) as db:
        db.execute("CREATE TABLE hidden (id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO hidden VALUES (7)")
        db.execute("CREATE MATERIALIZED VIEW visible AS SELECT id FROM hidden")
        assert db.execute("Read the authorized view", agent=True).rows == ((7,),)
        assert requests[0].relations[0].derived is True
        assert "hidden" not in repr(requests[0])
        with pytest.raises(SQLError, match="not authorized"):
            db.execute("Read its underlying source", agent=True)


def test_agent_mode_keeps_ordinary_sql_provider_free(tmp_path):
    import os
    import subprocess
    import sys

    # A fresh interpreter detects imports rather than relying on this test process's cache.
    script = """
import sys
from refpot.sql import Database
with Database() as db:
    db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
    assert db.execute("SELECT COUNT(*) FROM items").rows == ((0,),)
assert "refpot.agent" not in sys.modules
assert "refpot.providers" not in sys.modules
"""
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
