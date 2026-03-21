# Concepts: Unit Lifecycle

Every unit in a CUTIP group follows a three-phase lifecycle. Understanding this lifecycle is key to writing workflows that are predictable, debuggable, and safe to re-run.

---

## The three phases

```
pre_build(ctx)  ──▶  workflow main(ctx)  ──▶  startup(ctx)
    │                      │                      │
    │                      │                      │
 Generate files         Start containers       Post-start
 Stage build context    Order by behavior       verification
 Write configs          Health-check loops      Smoke tests
```

| Phase | Hook | When it runs | Typical use |
|---|---|---|---|
| **Pre-build** | `pre_build(ctx)` in `startup.py` | Before image builds, per unit | Generate config files, stage buildtime resources, write secrets into build context |
| **Orchestration** | `main(ctx)` in `workflow.py` | After all images are built and networks ensured | Start containers in order, run health checks, branch on container state |
| **Post-start** | `startup(ctx)` in `startup.py` | After `workflow.main()` completes, per unit | Verify services are running, print connection instructions, run smoke tests |

---

## Phase 1: Pre-build

Each unit may define a `pre_build(ctx)` function in its `startup.py`. CUTIP calls this function before building the unit's image.

```python
# cutip/units/web/startup.py

def pre_build(ctx):
    """Generate config.yaml into the build context."""
    import yaml

    config = {
        "database": {"host": "cutip-db", "port": 5432},
        "app": {"debug": False, "port": 8080},
    }

    config_path = ctx.project_root / "resources" / "buildtime" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.dump(config))
```

**Why this matters:** In compose, you either commit generated files to the repo, write a Makefile target, or pass everything as environment variables. `pre_build` makes file generation an explicit, auditable step in the container lifecycle.

---

## Phase 2: Orchestration

The `workflow.py` attached to a group is the orchestration layer. CUTIP calls `main(ctx)` after all pre-build hooks have run and images are built.

The orchestrator has full control over container start order. There is no `depends_on` declaration --- ordering is imperative Python:

```python
# cutip/groups/complex/workflow.py
from cutip.workflow.decorators import action, orchestrator

@action(name="Start DB", container="cutip-db")
def start_db(ctx):
    ctx.container("cutip-db").start()

    import time
    for attempt in range(1, 31):
        exit_code, _ = ctx.container("cutip-db").exec_run(
            ["psql", "-U", "appuser", "-d", "appdb", "-c", "SELECT 1"],
            environment={"PGPASSWORD": ctx.secrets["db_password"]},
        )
        if exit_code == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("Postgres did not become ready")

@action(name="Start Web", container="cutip-web", depends_on=["start_db"])
def start_web(ctx):
    ctx.container("cutip-web").start()

@orchestrator
def main(ctx):
    start_db(ctx)
    start_web(ctx)
```

The `@action` and `@orchestrator` decorators are optional --- a plain `def main(ctx)` works identically. The decorators add metadata that CUTIP uses for introspection (see [Annotations](annotations.md)).

---

## Phase 3: Post-start

After `workflow.main()` returns, CUTIP calls `startup(ctx)` in each unit's `startup.py`. This is the place for verification and smoke tests:

```python
# cutip/units/web/startup.py

def startup(ctx):
    """Verify the web app is serving."""
    exit_code, output = ctx.container("cutip-web").exec_run(
        ["curl", "-sf", "http://localhost:8080/health"]
    )
    if exit_code == 0:
        logger.success("Web app is serving at http://localhost:8080")
    else:
        logger.warning(f"Health endpoint returned non-zero: {exit_code}")
```

**Why this matters:** Post-start hooks run after the full orchestration sequence is complete. They confirm the deployment is healthy, not just that containers started. This is the difference between "the process is running" and "the service is reachable."

---

## Full lifecycle sequence

For a group with two units (`db` and `web`), the complete execution order is:

```
1. Load paths.yaml + secrets.yaml
2. Validate all {{ paths.X }} / {{ secrets.X }} refs
3. Create generated directories
4. Create host dirs + named volumes
5. pre_build(ctx) for each unit        ← Phase 1
6. Build/pull images
7. Ensure networks
8. Create containers
9. workflow.main(ctx)                   ← Phase 2
10. startup(ctx) for each unit          ← Phase 3
```

Steps 1--8 are handled by CUTIP's runtime. Steps 5, 9, and 10 are your code.

---

## Lifecycle and `cutip plan`

`cutip plan` runs steps 1--4 (validation and directory setup) and prints what steps 5--10 would do. No containers are created, no images are built, no hooks are called. This makes `cutip plan` safe to run anywhere --- no runtime required.

---

## Idempotency

CUTIP removes stale containers before recreating them on each `cutip run`. The lifecycle is designed to be re-runnable: `pre_build` regenerates files, `main` starts fresh containers, `startup` re-verifies. There is no hidden state between runs.
