"""Runnable fixture-first demo for the unreleased read-only SQL agent preview.

Default mode uses a deterministic protocol fixture and makes no network request.
Pass --live to opt into OpenRouter and its configured free model.
"""

from __future__ import annotations

import argparse

QUESTION = "Show item quantities above five"


def build_generator(live: bool, model: str):
    if live:
        # Import the optional remote provider only after explicit network opt-in.
        from refpot.agent import AgentConfig
        from refpot.providers import OpenRouter

        return AgentConfig(
            generator=OpenRouter(model=model, api_key_env="OPENROUTER_API_KEY"),
            relations=("items",),
            disclose_schema=True,
        )

    from refpot.agent import AgentConfig, QueryProposal

    def fixture(request):
        # A fixed response fixture, not an implementation of language interpretation.
        return QueryProposal(
            "SELECT id, quantity FROM items WHERE quantity > ? ORDER BY id",
            (5,),
            ("The fixture interprets above five as quantity > 5.",),
        )

    return AgentConfig(generator=fixture, relations=("items",), disclose_schema=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="send the displayed question to OpenRouter"
    )
    parser.add_argument(
        "--model",
        default="nvidia/nemotron-3.5-super-vl:free",
        help="OpenRouter model for --live (default: free preview model)",
    )
    args = parser.parse_args()

    from refpot.agent import (
        AgentConfig,
        AgentError,
        Clarification,
        ClarificationRequired,
        QueryDeclined,
    )
    from refpot.sql import Database

    config = build_generator(args.live, args.model)
    print(
        "Live model: schema and question disclosed"
        if args.live
        else "Protocol fixture: no model or network calls"
    )
    with Database(agent=config) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, quantity INTEGER NOT NULL)")
        db.execute("INSERT INTO items VALUES (1, 8)")
        db.execute("INSERT INTO items VALUES (2, 3)")
        db.execute("INSERT INTO items VALUES (3, 12)")
        print(f"Question: {QUESTION}")
        try:
            result = db.execute(query=QUESTION, agent=True)
        except ClarificationRequired as exc:
            print("Clarification needed:", *exc.questions)
            return
        except QueryDeclined as exc:
            print("Declined:", exc.reason)
            return
        print("Rows:", result.rows)
        assert result.generation is not None
        print("Generated query:", result.generation.query)
        print("Parameters:", result.generation.parameters)
        print("Assumptions:", result.generation.assumptions)
        inspected = db.execute(query=QUESTION, agent=True, explain=True)
        print("Plan:", inspected.plan)

    # Generation is rejected inside an active transaction. Known SQL remains usable
    # there, including deliberate read-your-writes, without invoking the generator.
    with Database(agent=config) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, quantity INTEGER NOT NULL)")
        with db.transaction():
            db.execute("INSERT INTO items VALUES (1, 21)")
            try:
                db.execute(query=QUESTION, agent=True)
            except AgentError:
                print("Generation refused inside transaction")
            else:
                raise AssertionError("generation must not enter an active transaction")
            visible = db.execute("SELECT id, quantity FROM items")
            assert visible.rows == ((1, 21),)
            print("Read-your-writes with ordinary SQL:", visible.rows)

    # A separate protocol fixture demonstrates the clarification exception; it is
    # not a claim that a real model will always recognize ambiguous questions.
    clarification = AgentConfig(
        generator=lambda request: Clarification(("What quantity threshold should be used?",)),
        relations=("items",),
        disclose_schema=True,
    )
    with Database(agent=clarification) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, quantity INTEGER NOT NULL)")
        try:
            db.execute(query="Which items are low?", agent=True)
        except ClarificationRequired as exc:
            print("Clarification needed:", *exc.questions)


if __name__ == "__main__":
    main()
