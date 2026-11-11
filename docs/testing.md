# Testing and verification

All tests use PostgreSQL and the normal project settings. Django creates the
selected test database, applies migrations **there**, runs tests and drops it.
`DB_TEST_NAME` must start with `test_`, differ from the application database name
and fit PostgreSQL's identifier limit. It must name disposable data only. Do not
reuse a database belonging to another running test session.

Commands below use Bash/zsh from the repository root. No external AI calls are
needed: Compose sets an empty API key, and AI-dependent tests use mocks or the
rule-based provider. Test execution does not establish live OpenAI reliability.

## Docker image tests

Define `dc` as in [Docker setup](docker-development.md#first-setup). With the
database and backend already running:

```sh
dc exec backend python backend/manage.py check --database default
dc exec backend python backend/manage.py makemigrations --check --dry-run
dc exec backend python backend/manage.py test config monitoring coach analysis --noinput
git diff --check
```

The default Docker test database is `test_smart_energy_docker`. The development
role can create/drop it. `--noinput` assumes this database is disposable and can
be removed if left by a failed session. Tests must never target the running
application database. The continuous worker can remain running: its application
database is separate from the test database.

These commands exercise code **already built into the backend image**. Source
edits are not automatically copied into a running container.

## Working-tree tests without restarting services

An existing image can supply dependencies while a one-off container reads the
current backend source through a read-only bind mount:

```sh
dc run --rm --no-deps -T \
  --volume "$PWD/backend:/app/backend:ro" \
  --env OPENAI_API_KEY= \
  backend python backend/manage.py test config monitoring coach analysis --noinput
```

No image is rebuilt and no existing service is restarted. `--no-deps` requires the
Docker database/network to be running already. The one-off container does not
publish the backend port. The same read-only mount can be used with the `check`
and migration-consistency commands above. This tests the mounted working-tree
code with the existing image's dependency versions; dependency changes require
an updated image in a normal development workflow.

## Host tests

Use the virtual environment and connection configuration described in
[host development](host-development.md#environment). The role needs database
creation permission and access to the PostgreSQL maintenance database.

```sh
OPENAI_API_KEY='' python backend/manage.py check --database default
OPENAI_API_KEY='' python backend/manage.py makemigrations --check --dry-run
OPENAI_API_KEY='' python backend/manage.py test config monitoring coach analysis --noinput
git diff --check
```

For PowerShell, set `$env:OPENAI_API_KEY = 'disabled-for-tests'` before the Python
commands rather than using the Bash assignment prefix. This non-key placeholder
fails the provider's key check and prevents a private file from supplying a real
key. Private `.env` files are not
modified for test execution. If PostgreSQL or permissions are unavailable, report
the blocker; do not substitute SQLite or use the application database for tests.

## Coverage and limits

The suite exercises model validation/database constraints, duplicate handling,
shared energy calculations, management/history APIs, selected PostgreSQL
concurrency cases, completed-minute scheduling, per-building rollback, legacy
migration preservation/rejection, demo initialization and graceful shutdown.
Timing-sensitive tests use controlled clocks rather than minute-long waits.

Passing tests do not demonstrate calibrated forecast accuracy, measured savings,
realistic weather/building behavior, performance under load or secure public
access. The dashboard, current UML and presentation deliverables are not covered
by the backend tests. Migration tests operate on disposable schemas; they are not
an audit or repair of the running application's legacy data.
