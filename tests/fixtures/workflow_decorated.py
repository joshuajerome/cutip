"""Test fixture: a workflow using @action/@orchestrator decorators."""

from __future__ import annotations

from cutip.workflow import action, orchestrator


@action(name="Start DB", description="Start the database", container="cutip-db")
def start_db(ctx):
    pass


@action(
    name="Wait for DB",
    description="Poll until DB accepts connections",
    container="cutip-db",
    depends_on=["Start DB"],
)
def wait_for_db(ctx):
    pass


@action(name="Start Web", description="Start the web app", container="cutip-web")
def start_web(ctx):
    pass


@orchestrator
def main(ctx):
    start_db(ctx)
    wait_for_db(ctx)
    start_web(ctx)
