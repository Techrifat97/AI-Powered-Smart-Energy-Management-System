# Docker: local development and university demonstrations

This local-only stack runs the simulator-backed project. Examples use Bash/zsh
on macOS/Linux from the repository root. Gunicorn serves the Django JSON APIs
with worker management and graceful termination. No frontend service is started
because the frontend directory is a placeholder. [Host development](host-development.md)
uses an independent PostgreSQL configuration.

## First setup

Run from the repository root with Docker Desktop running. Create the **separate**
ignored `.env.docker` with generated secrets, without printing them or replacing
an existing file:

```sh
python3 - <<'PY'
from pathlib import Path
import secrets
p = Path('.env.docker')
if p.exists():
    print('Existing .env.docker retained.')
else:
    text = Path('.env.docker.example').read_text()
    text = text.replace('DOCKER_SECRET_KEY=\n', 'DOCKER_SECRET_KEY=' + secrets.token_urlsafe(48) + '\n')
    text = text.replace('DOCKER_DB_PASSWORD=\n', 'DOCKER_DB_PASSWORD=' + secrets.token_urlsafe(32) + '\n')
    p.write_text(text)
    p.chmod(0o600)
    print('Created private .env.docker.')
PY
```

The tracked example contains empty secret placeholders and non-secret defaults.
Do not overwrite the existing `.env`. Do not regenerate the Docker password after
initializing the volume: PostgreSQL initialization variables create credentials
only for an empty data directory; changing the file does not rotate an existing
database password. Keep the private file with your local persistent database.

For short commands below, define this function in each new Bash/zsh terminal:

```sh
dc() { docker compose --env-file .env.docker -p smart-energy "$@"; }
dc config --quiet
dc build backend
dc up -d
dc ps -a
```

`build backend` builds the shared image once. All three application services use
that same image. After source/dependency changes, run `dc build backend` and
`dc up -d` again to recreate affected services. There is no source bind mount or
automatic reload. If host port 8000 is occupied, set `DOCKER_BACKEND_PORT=8001`
in `.env.docker` and use localhost:8001; do not stop an unrelated server.

## Services and startup

| Service | Role | Startup condition |
| --- | --- | --- |
| `db` | Official `postgres:18-bookworm`; own named volume | Readiness checked with `pg_isready`. |
| `migrate` | One-shot `python backend/manage.py migrate --noinput` | Database healthy. |
| `backend` | Gunicorn with two workers, same application image | Database healthy and migrations exit 0. |
| `telemetry` | `python backend/manage.py run_telemetry` | Database healthy and migrations exit 0. |

`migrate` showing **Exited (0)** is expected. Backend and worker never each run
their own migrations. No inventory creation, historical seeding, data copying or
downtime backfill occurs at startup. Application processes run as user `app`
(UID 10001). The worker maps SIGTERM to its clean Ctrl+C shutdown path, rolling
back an interrupted building transaction. An init process forwards signals and
reaps children. PostgreSQL has its normal image-managed database process user.

Application services have no automatic restart loop: startup/worker errors remain
visible in status and logs. Correct the error, then use `dc up -d`. Database
readiness is checked before migration execution. A database readiness failure or unsuccessful migration prevents dependent
startup. The backend healthcheck reads the
building API and therefore checks both HTTP and database connectivity.

Inspect without dumping secrets:

```sh
dc ps -a
dc logs --tail 50 migrate backend telemetry
dc logs --tail 30 db
curl -fsS http://127.0.0.1:8000/api/buildings/
```

## Environment and database isolation

- `--env-file .env.docker` explicitly supplies **Compose interpolation** values.
  `environment:` in `compose.yaml` explicitly supplies the actual container
  variables. There is no automatic container `env_file` loading or host `.env`
  mount. Required private values fail clearly when missing.
- `DOCKER_*` variable names avoid accidental reuse of local `DB_HOST`, `DB_NAME`
  or `SECRET_KEY`. Shell `DOCKER_*` variables still override the file; avoid old
  overrides. Do not use bare `docker compose up` and expect this file to load.
- Application containers always receive `DB_HOST=db` and `DB_PORT=5432`. The
  backend and worker share that Docker database. `OPENAI_API_KEY` is explicitly
  empty, so external AI calls remain disabled.
- PostgreSQL has **no published host port**. It does not compete with Postgres.app
  on host port 5432. The backend alone publishes `127.0.0.1:8000` by default.
- The volume is `smart-energy_postgres_data`, mounted at `/var/lib/postgresql`.
  PostgreSQL 18 stores data below `/var/lib/postgresql/18/docker`. This is the
  [official 18+ image layout](https://hub.docker.com/_/postgres), not the older
  `/var/lib/postgresql/data` mount. Keep the major version explicit; a future major
  upgrade requires a planned data migration, not merely a tag edit.
- Docker's database may also be named `smart_energy_db`, but it is on a different
  server and starts empty. No Postgres.app files or data are copied/mounted.
- `.dockerignore` excludes env files, keys, virtual environments, caches, dumps
  and Git history. The Dockerfile copies only requirements and backend code.
  Secrets are supplied at runtime, never as build arguments or image files.

Use `dc config --quiet` for validation. **Do not share full `compose config`,
`config --environment` or unrestricted container-inspect output**: rendered
environment values can contain secrets. Docker access on the local machine is
trusted. The official PostgreSQL initializer creates the configured local role
with superuser privileges, allowing disposable test database creation; this is a
development convenience, not a production role design.

References: [Compose interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/),
[dependency conditions](https://docs.docker.com/reference/compose-file/services/#depends_on),
[Gunicorn deployment](https://gunicorn.org/deploy/).

## Explicit demo inventory

```sh
dc exec backend python backend/manage.py setup_demo_inventory
```

This creates `Docker demo` with declared solar installation and four active kWh
meters: main, HVAC, lighting, solar. Repeating it verifies the same inventory and
preserves existing IDs, readings, timestamps and status. Partial/ambiguous or
incompatible inventory, inactive required demo devices and reserved device IDs
assigned elsewhere produce an error; nothing is silently overwritten. Run setup
serially. The command is never called by Compose startup.

Meters must exist at the **start** of the completed interval. If created at
12:00:30 UTC, their first eligible interval is 12:01–12:02, processed at 12:02.
Wait two UTC minute boundaries after creation, then inspect:

```sh
dc logs --tail 10 telemetry
curl -fsS http://127.0.0.1:8000/api/buildings/
# Replace 1 with the printed building ID if different.
curl -fsS 'http://127.0.0.1:8000/api/buildings/1/readings/?page_size=8'
curl -fsS http://127.0.0.1:8000/api/buildings/1/summary/
```

For manual `--once` retries, first stop this stack's continuous worker, then run
the command twice within the same UTC wall-clock minute:

```sh
dc stop telemetry
dc exec backend python backend/manage.py run_telemetry --once
dc exec backend python backend/manage.py run_telemetry --once
dc up -d telemetry
```

Depending on the worker's last cycle, the first command creates or reuses a set;
the second reports four existing rows. Crossing a minute boundary selects a new
interval. No duplicate keys are created. Do not retry an old completed set after
changing its eligible inventory. The controlled-clock test suite checks exact
retry behavior without depending on manual timing.

## Tests and checks

The [testing guide](testing.md) is the reference for Docker image tests,
read-only working-tree tests and optional host tests. It defines disposable
PostgreSQL database requirements and how external AI calls are disabled. Test
execution does not require stopping the application worker because its database
is separate. Code changes are not visible in an already-built image unless the
working-tree mount described in that guide is used.

## Stop, recreate and return to host development

```sh
dc stop             # Stop this stack; keep containers and data.
dc up -d            # Start with dependency checks and the migration job.
dc down             # Remove only this project's containers/network; keep volume.
dc up -d            # Recreate using the SAME persistent volume.
```

Do **not** add `--volumes`/`-v` to routine shutdown: that option deletes database
storage. The named volume is retained across ordinary container recreation. Back up data
before planned storage or database-version changes.

To use Postgres.app again, run `dc down`, activate `.venv`, and use the unchanged
local `.env` with normal `python backend/manage.py ...` commands. There are no
Docker database exports to unset in this workflow. Docker data stays in its own
volume and is available on the next `dc up -d`.

## Operational limitations

Management permissions remain `AllowAny`, CORS remains permissive, and there is
no HTTPS or per-user access control. Localhost publishing does not make this a
public production deployment. Gunicorn serves JSON APIs; static assets for admin
and the browsable API are not configured. Streamlit UI, backups/restore workflow,
deployment hardening and full dependency locking remain future work. Existing
measurement/legacy-data limits still apply; Docker does not repair old records.
