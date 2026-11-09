# Optional host-based development

[Docker](docker-development.md) is the default setup. This alternative runs Django
and the simulator directly against a host PostgreSQL server, such as Postgres.app.
The simulator remains the intended data source; no extra simulation database is
required. Host and Docker databases are separate even when both are named
`smart_energy_db`.

## Environment

Commands run from the repository root. Python 3.13 matches the Docker runtime.
Shell examples use Bash/zsh on macOS/Linux.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

For Windows PowerShell, create the environment with `python -m venv .venv` and
activate it with `.venv\Scripts\Activate.ps1`. Python commands are otherwise the
same; Bash heredocs/functions elsewhere in the documentation need adaptation.

Use a PostgreSQL version supported by Django 5.2 (14 or newer). On macOS,
Postgres.app command-line tools are normally under
`/Applications/Postgres.app/Contents/Versions/latest/bin`. In an administrator's
`psql` session, create a local role/database if they do not already exist:

```sql
CREATE ROLE smart_energy_user LOGIN CREATEDB;
\password smart_energy_user
CREATE DATABASE smart_energy_db OWNER smart_energy_user;
```

The password prompt avoids putting a password in SQL/shell history. `CREATEDB`
and access to the maintenance database `postgres` support disposable Django tests;
superuser privileges are not required. See [testing](testing.md#host-tests).

Copy [`.env.example`](../.env.example) to ignored `.env` only if the private file
does not already exist. Set a private `SECRET_KEY` and PostgreSQL password. The
example defines `DB_HOST=127.0.0.1`, `DB_PORT=5432`, `DB_NAME=smart_energy_db` and a
separate `DB_TEST_NAME`. Keep `OPENAI_API_KEY` empty for ordinary offline development
and all tests. Supplying a usable key enables optional external coach requests;
never commit it or print private configuration.

Settings load the root `.env` and optional `backend/.env` without overriding
existing process variables. PostgreSQL is mandatory: missing details fail clearly,
and an unavailable server does not trigger a SQLite fallback.

## Schema and processes

For a new application database, apply its migrations. For an existing database,
back up and inspect the migration plan first:

```sh
python backend/manage.py showmigrations
python backend/manage.py migrate --plan
python backend/manage.py migrate
python backend/manage.py runserver
```

The numeric/uniqueness migration rejects incompatible legacy values and duplicate
keys without deleting or repairing data. Duration/solar metadata migrations leave
old unknown values unknown. See [legacy data](energy-calculations.md#legacy-data-and-hourly-fixtures).

With the same environment active in another terminal, explicitly initialize a
fresh compatible demo inventory and start the worker:

```sh
python backend/manage.py setup_demo_inventory
python backend/manage.py run_telemetry
```

The setup command creates/verifies the same named four-meter inventory used in
Docker. It is never automatic and rejects incompatible existing configurations.
Wait two UTC minute boundaries after creation for first eligible readings. Use
Ctrl+C to stop the host worker/server. If Docker's backend occupies port 8000,
use a different host development port, such as `python backend/manage.py runserver
127.0.0.1:8001`.

API examples are in the [S1 guide](s1-management-api.md#manual-api-checks).
Tests and checks are centralized in the [testing guide](testing.md). Optional
admin access uses Django's built-in components and an explicitly created
superuser; the `accounts` app does not implement custom authentication.
