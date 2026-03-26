# Why CUTIP?

CUTIP is an automation framework that uses containers as deterministic execution environments. Containers are the medium through which tasks get automated — SSH sessions, dev servers, build pipelines, deployment scripts. CUTIP handles the full lifecycle — from generating config files before an image build, through ordering container startups by actual readiness, to verifying services after deployment.

This page is an honest comparison. If `docker-compose` does what you need, use it --- it is simpler, widely understood, and has first-class IDE tooling. CUTIP solves a different class of problems.

---

## The core difference

| | docker-compose | CUTIP |
|---|---|---|
| **Model** | Declarative convergence — describe desired state, the runtime figures out transitions | Declarative definitions + imperative Python — YAML for structure, Python for orchestration |
| **Startup ordering** | `depends_on` with `condition: service_healthy` — polls a healthcheck defined in the file | Full Python: loop, exec into the container, branch on result, log progress |
| **Post-start hooks** | None native — you write shell scripts and call them yourself | `startup(ctx)` per unit — runs after the container starts, has full container API |
| **Pre-build file staging** | None — build context must be ready before `docker compose up` | `pre_build(ctx)` per unit — generate config files, copy local deps, write secrets to build context |
| **Config variables** | `.env` flat substitution — one level, no validation | `paths.yaml` + `secrets.yaml` with `required:` / `generated:` sections — fails fast with a clear error if any required value is missing |
| **Validation** | Runtime only — errors surface when the daemon tries to create the container | Static graph validation — `cutip validate` checks every ref before any backend is contacted |
| **Orchestration logic** | Separate shell scripts or CI YAML | First-class Python in `workflow.py` — testable, importable, debuggable |
| **Migration from compose** | — | `cutip from-compose <compose-file>` — converts an existing compose file into a full CUTIP workspace in one command |

**Use compose when:**

- You are deploying a standard stack (postgres + redis + your app) with no custom startup logic
- You want maximum ecosystem compatibility (`docker compose`, Portainer, VS Code Dev Containers)
- Your stack needs no programmatic startup logic and a declarative definition is sufficient

**Use CUTIP when:**

- You need to exec into a container during startup (health checks, schema migrations, config patching)
- You generate config files at build time from local state (not hardcoded values)
- You want static validation before touching the container runtime
- You need startup ordering that depends on actual container behavior, not just a healthcheck definition
- You want your orchestration logic to be Python you can import, test, and step through in a debugger
- You have an existing compose file and want to migrate — `cutip from-compose` generates the full workspace for you

---

## Hands-on: the `complex` project

`cutip init` creates two example projects. `simple` is the minimal single-container hello-world. `complex` is the one that shows why CUTIP exists.

The `complex` project runs a **PostgreSQL database** and a **Python web application** that connects to it. It is a realistic setup and it demonstrates four CUTIP capabilities that compose cannot replicate cleanly:

1. **Pre-build config generation** — a Python script writes `config.yaml` into the build context before the image build runs
2. **Health-check loop in Python** — the workflow waits for postgres to be ready by exec-ing into it
3. **Isolated container network** — both containers live on a private network defined in a NetworkCard
4. **Post-start verification** — startup.py for the web unit confirms the app is serving

### Step 1 — paths.yaml + secrets.yaml

**`cutip/secrets.yaml`**:
```yaml
required:
  db_password: ""        # must be filled in before cutip run complex
```

**`cutip/paths.yaml`**:
```yaml
generated:
  db_data_dir: ".cutip-complex-data"   # cutip creates this automatically
```

`db_password` is a required secret. CUTIP will refuse to run if it is empty — before touching the container backend, before pulling images. No silent misconfigurations.

`db_data_dir` is a generated path. CUTIP creates `.cutip-complex-data/` at the project root automatically.

---

### Step 2 — The network

```yaml
# cutip/cards/app-net/app-net.network.yaml
apiVersion: cutip/v1
kind: NetworkCard
metadata:
  name: app-net

spec:
  driver: bridge
  subnet: "172.20.0.0/24"
  gateway: "172.20.0.1"
```

A dedicated bridge network. Both the database and web containers reference it via `networkRef`. No `network_mode: bridge` shortcut — they are isolated from other containers by default.

---

### Step 3 — The database

```yaml
# cutip/cards/db/db.image.yaml
apiVersion: cutip/v1
kind: ImageCard
metadata:
  name: db

spec:
  source: pull
  image: docker.io/library/postgres
  tag: "16"
```

```yaml
# cutip/cards/db/db.container.yaml
apiVersion: cutip/v1
kind: ContainerCard
metadata:
  name: cutip-db

spec:
  imageRef:
    ref: images/db
  networkRef:
    ref: networks/app-net

  environment:
    POSTGRES_DB: appdb
    POSTGRES_USER: appuser
    POSTGRES_PASSWORD: "{{ secrets.db_password }}"

  volumes:
    db_data: /var/lib/postgresql/data
```

The password is `{{ secrets.db_password }}` — resolved from `secrets.yaml` at run time. CUTIP checks this ref exists and is non-empty before creating a single container.

The data volume `db_data` is a named volume. CUTIP creates it automatically.

---

### Step 4 — Pre-build config generation

The web app reads a `config.yaml` that is baked into its image at build time. CUTIP generates this file before the image build runs:

```python
# cutip/units/web/startup.py

def pre_build(ctx: CutipContext) -> None:
    """Generate config.yaml into the build context before the image is built."""
    import yaml

    config = {
        "database": {
            "host": "cutip-db",
            "port": 5432,
            "name": "appdb",
            "user": "appuser",
        },
        "app": {
            "debug": False,
            "port": 8080,
        },
    }

    config_path = ctx.project_root / "resources" / "buildtime" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.dump(config))
    logger.info("Generated resources/buildtime/config.yaml")
```

This runs before the image build. The Dockerfile copies `config.yaml` from the build context:

```dockerfile
# resources/dockerfiles/web.dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# config.yaml generated by pre_build() and staged by buildtime_resources
COPY config.yaml /app/config.yaml
COPY app.py /app/app.py

CMD ["python", "app.py"]
```

In compose, you would need to either: commit `config.yaml` to the repo, write a Makefile target that generates it, or pass everything as environment variables. None of those options are as explicit or fail-fast.

---

### Step 5 — The workflow: ordering by behavior, not by declaration

This is the core of CUTIP's value proposition:

```python
# cutip/groups/complex/workflow.py

def main(ctx: CutipContext) -> None:
    """Start the database, wait for it to be ready, then start the web app."""

    db = ctx.container("cutip-db")
    web = ctx.container("cutip-web")

    # Start the database first
    db.start()
    logger.info("Waiting for postgres to be ready...")

    # Health-check loop: exec psql into the running container
    import time
    for attempt in range(1, 31):
        exit_code, _ = db.exec_run(
            ["psql", "-U", "appuser", "-d", "appdb", "-c", "SELECT 1"],
            environment={"PGPASSWORD": ctx.secrets["db_password"]},
        )
        if exit_code == 0:
            logger.success(f"Postgres ready after {attempt} attempt(s)")
            break
        logger.debug(f"  attempt {attempt}/30 — not ready yet")
        time.sleep(1)
    else:
        raise RuntimeError("Postgres did not become ready within 30 seconds")

    # Database is confirmed ready — start the web app
    web.start()
```

Compare this to the compose equivalent:

```yaml
# docker-compose.yaml
services:
  db:
    image: postgres:16
    healthcheck:
      test: ["CMD-SHELL", "psql -U appuser -d appdb -c 'SELECT 1'"]
      interval: 1s
      timeout: 5s
      retries: 30

  web:
    build: .
    depends_on:
      db:
        condition: service_healthy
```

The compose version looks simpler. But the health check runs on a fixed interval you declared upfront — you cannot branch on the result, add context-aware logging, or take a different action on persistent failure. In CUTIP, the health-check is code. You can raise a specific exception, log the failure reason, or fall back to a different startup path.

---

### Step 6 — Post-start verification

After `workflow.main()` starts both containers, CUTIP calls `startup(ctx)` in the web unit:

```python
# cutip/units/web/startup.py

def startup(ctx: CutipContext) -> None:
    """Verify the web app is serving after it starts."""
    web = next(c for c in ctx.resolved_cards.values() if isinstance(c, ContainerCard) and c.metadata.name == "cutip-web")

    exit_code, output = ctx.container("cutip-web").exec_run(
        ["curl", "-sf", "http://localhost:8080/health"]
    )
    if exit_code == 0:
        logger.success("Web app is serving at http://localhost:8080")
    else:
        logger.warning(f"Health endpoint returned non-zero: {exit_code}")

    logger.info("  Connect to db:  podman exec -it cutip-db psql -U appuser -d appdb")
    logger.info("  Stop all:       podman stop cutip-db cutip-web")
```

---

### Step 7 — Static validation before touching the runtime

```shell
cutip validate
```

```
INFO  Discovered 5 card(s), 2 unit(s), 1 group(s)
INFO  Validating 5 card(s) ...
INFO    ✓ containers/cutip-db
INFO    ✓ images/db
INFO    ✓ networks/app-net
INFO    ✓ containers/cutip-web
INFO    ✓ images/web
INFO  Validating 1 group(s) ...
INFO    ✓ complex → units/db
INFO    ✓ complex → units/web
INFO    ✓ complex: workflow.py
```

Every ref in every card is resolved. The workflow file is confirmed to exist. The `{{ secrets.db_password }}` ref is confirmed non-empty. No container runtime required. This runs cleanly in CI before any image is pulled.

---

## What this looks like end-to-end

```shell
# First time
cutip init
# Edit cutip/secrets.yaml — fill in db_password

cutip validate          # checks the whole graph, no Podman needed
cutip plan complex      # prints execution table, starts nothing

cutip run complex
# pre_build(ctx) generates resources/buildtime/config.yaml
# build web image
# pull postgres:16
# workflow.main() starts db, waits 3s for postgres, starts web
# startup(ctx) confirms web is serving
# ✓ done
```

Subsequent runs are idempotent — CUTIP removes stale containers and recreates them.

---

## Migrating from an existing compose file

If you already have a `docker-compose.yaml`, you do not need to rewrite it by hand. CUTIP ships a converter:

```shell
cutip from-compose docker-compose.yaml --output-dir .
```

This generates the full workspace in one command:

- **ImageCard** per service — `source: pull` for image references, `source: build` for build sections
- **ContainerCard** per service — ports, environment, volumes, bind mounts, labels, restart policy, cap_add
- **NetworkCard** per compose network — with a placeholder subnet you fill in once
- **Unit** per service — ready to extend with `pre_build(ctx)` and `startup(ctx)` hooks
- **Group** with a `workflow.py` stub — services ordered by `depends_on`, annotated with TODO comments where health checks are needed
- **secrets.yaml** — sensitive environment variables (passwords, tokens, API keys) are automatically extracted as `{{ secrets.<key> }}` references

Fields that cannot be mapped automatically (`entrypoint`, `depends_on` health logic, `healthcheck`) are listed in the end-of-run report with specific instructions.

After conversion, run `cutip validate` to confirm the graph is consistent, then implement the health-check stubs in each unit's `startup.py` and review the start order in `workflow.py`.

---

## Summary

CUTIP is not trying to replace compose for standard stacks. It is designed for environments where the startup sequence is imperative, not declarative — where you need to generate files, exec into containers, branch on health state, and treat container orchestration as code you can test and debug.

If your workflow is "bring up 3 services and let them find each other", use compose. If your workflow is "generate a config file, start the database, wait until it can answer queries, then start the app that depends on it", CUTIP gives you the right primitives.

If you are already on compose and want to move to CUTIP, `cutip from-compose` handles the translation.
