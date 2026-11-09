# S1 simulated telemetry

These readings are **synthetic**, not physical measurements or a calibrated
building/weather model. The command labels every cycle `SYNTHETIC`. The database
currently has no per-reading source flag, so use a separate simulation database
when demonstrating it; stored synthetic and physical data are not distinguishable
by a source field.

## One building-minute

At 12:01 UTC, the worker processes `[12:00, 12:01)` and stores start `12:00:00`,
duration `60`. It queries the current database inventory, validates it, plans the
whole building's values, and sends each reading through `ingest_reading()`.
For example, a synthetic 12 kW main load corresponds to `12/60 = 0.2 kWh`.
HVAC gets at most 30% and lighting at most 15% of that main load, shared among
eligible active meters in each category. These are included loads, not extra
whole-building consumption. Solar generation is recorded separately.

`monitoring.services.generator.generate_minute(minute, *, now=None)` processes
one supplied completed UTC minute. `now` is a trusted optional clock for tests;
the command uses the current UTC clock. Invalid or unfinished intervals raise
`ValidationError`. The service never creates buildings/meters or changes metadata.

It returns `minute`, `created`, `already_existing`, `skipped`, `failed`, and a
`buildings` list. Created/existing count **readings**; skipped/failed count
**buildings**. Each building result includes its status, reason, row counts and
`skipped_meter_ids` for active meters too new for the interval.

## Supported inventory

Each cycle independently checks each building:

- Exactly one **active ELECTRICITY** main is required. Inactive retired mains may
  retain history. Missing or multiple active mains skip the building.
- Any number of active HVAC and LIGHTING submeters is supported, including none.
- `has_solar_installation` must be explicitly `True` or `False`; unknown skips.
- `True` requires exactly one active solar meter. More than one active solar is
  unsupported. Inactive retired solar meters are allowed alongside the active one.
- `False` requires **no configured SOLAR meters**, including inactive ones. A
  configured solar device conflicts with this conservative absence policy; the
  generator does not decide whether an inactive device represents an installation.
- Existing database constraints restrict types to ELECTRICITY/HVAC/LIGHTING/SOLAR
  and units to kWh. The generator does not change those contracts.

A meter must have `created_at <= interval_start`. A newer submeter waits until
its first eligible minute; its ID is reported. A newer required main/solar meter
makes the whole building wait, avoiding an incomplete main/solar set. Activation
is observed **at cycle time**: activation timestamps are not stored, so the worker
cannot reconstruct which part of an earlier minute a meter was active for.
Deactivation stops subsequent cycles and preserves all historical readings.

## Synthetic profile v1

Times are UTC, with a constant assumed load over each generated minute:

| Quantity | Profile |
| --- | --- |
| Main, weekdays 08:00–18:00 | 12 kW plus deterministic variation from 0 to 0.999 kW. |
| Main, weekends 08:00–18:00 | 8 kW plus the same bounded kind of variation. |
| Main, other times | 4 kW plus bounded variation. |
| All HVAC combined | At most 30% of main, split equally by integer watts. |
| All lighting combined | At most 15% of main, split equally by integer watts. |
| Solar | Triangular curve: zero through 06:00, 10 kW at noon, zero from 18:00; explicit night zeros. |
| Voltage | Constant 230 V. |
| Energy | Generated constant power in kW divided by 60, retaining float precision. |

Variation uses SHA-256 of a fixed profile version, building PK, UTC interval start
and sorted eligible meter identities/types/device IDs. It uses neither fresh
random numbers nor Python's randomized `hash()`. Identical inputs give identical
values. Changes to inventory or profile code can conflict with an earlier set.
Baseline and floor area do not invent simulated measurements.

The constant-power assumption belongs **only to this generator**. Ingestion still
does not require general measured `energy_kwh` to equal `power_kw / 60`.

## Persistence, retries and concurrency

Each building-minute has its own atomic transaction. All rows are saved through
validated ingestion. A validation failure on any member rolls back **new rows for
that building-minute**, preserves existing rows and allows the next building to
run. Unknown-duration and overlap errors from ingestion remain errors; nothing
is backfilled, repaired or overwritten.

Ingestion checks coverage on each current meter. Historical ambiguity across
different retired main/solar meters remains aggregation's responsibility; this
worker does not certify that all old building history is usable.

Before inserting, the worker compares all existing reading meter IDs at that
building/start with the current eligible set. A nonempty **partial or different**
set is rejected as a conflict. Even an apparently repairable partial set is not
completed, because there is no historical inventory manifest. A complete matching
set is retried through ingestion: equal stored values return `already_existing`,
and unequal values fail without overwriting. Historical metadata changes are not
versioned, so the worker cannot reconstruct past physical assignments.

Lock order is building first (`FOR UPDATE`), then all current meter rows by
ascending PK (`FOR NO KEY UPDATE`), then ingestion in the same meter order.
Generator workers for the same building serialize and identical concurrent
cycles return one created set and one retry. The building lock coordinates solar
metadata changes and normal foreign-key-checked meter creation; current meter
locks coordinate activation/deactivation. The cycle uses this locked snapshot;
changes waiting on it appear on a later cycle.

Single-meter ingestion uses its existing meter lock and unique-key protection.
It does not acquire a building lock or promise a whole-building set. Other code
using different lock orders can still deadlock, and bypass writers can introduce
partial/overlapping data. These locks are not a database-wide multi-meter
constraint. Use the project's normal READ COMMITTED isolation and route new
telemetry through these services. If an outer caller transaction surrounds the
cycle, commits wait for that outer transaction.

## Command and scheduling

```sh
python backend/manage.py run_telemetry --once
python backend/manage.py run_telemetry
```

`--once` processes only the latest completed minute, reports results and exits.
Repeated calls within the same wall-clock minute retry the same interval. Expected
inventory skips are reported without an error exit. Failed building writes are
reported and make `--once` exit nonzero.

Continuous mode starts with the latest completed minute, then recomputes its wait
until the next UTC minute boundary **after** processing. It never does “work plus
sleep(60)”, and never walks through missed minutes. Downtime, slow processing or
a forward clock jump leave gaps. A backward clock does not replay older minutes
within that running process. Correct UTC system time is assumed.

Expected configuration/validation problems are reported per building and revisited
on a later scheduled cycle. Unexpected errors propagate. PostgreSQL errors stop
the command with an error rather than causing a rapid retry loop; `--traceback`
retains diagnostic details. Ctrl+C stops cleanly; if it interrupts a write, the
current building transaction rolls back while earlier completed buildings remain.

## Manual demonstration later (not the application database)

These instructions create disposable simulation data. They were not run against
the application's database during implementation.

1. Activate the environment: `source .venv/bin/activate` (macOS/Linux). Keep normal
   local PostgreSQL credentials in your ignored `.env`. Create a separate empty
   database owned by that configured local role, replacing `YOUR_POSTGRES_ROLE`:

   ```sh
   createdb -h 127.0.0.1 -p 5432 -U YOUR_POSTGRES_ROLE smart_energy_simulation
   export DB_NAME=smart_energy_simulation
   export OPENAI_API_KEY=''
   python backend/manage.py migrate
   ```

   `DB_NAME` overrides `.env` in this shell. These migrations target the new
   simulation database only. Do not run the hourly demo seeder for this setup.

2. Create the explicit synthetic inventory:

   ```sh
   python backend/manage.py shell <<'PY'
   from django.conf import settings
   from django.db import transaction
   from monitoring.models import Building, Meter
   assert settings.DATABASES['default']['NAME'] == 'smart_energy_simulation'
   with transaction.atomic():
       b = Building.objects.create(name='Synthetic demo', has_solar_installation=True)
       for kind in ['ELECTRICITY', 'HVAC', 'LIGHTING', 'SOLAR']:
           Meter.objects.create(building=b, device_id=f'SIM-{b.pk}-{kind}', meter_type=kind)
   print('Created one synthetic building with four meters.')
   PY
   ```

3. Wait until **two UTC minute boundaries after creation** so all meters existed
   at the start of the latest completed minute. For example, meters created at
   12:00:30 first qualify for `[12:01,12:02)`, processed at/after 12:02. Then run:

   ```sh
   python backend/manage.py run_telemetry --once
   python backend/manage.py run_telemetry --once
   ```

   Within the same UTC wall-clock minute, expect `created=4` then
   `already_existing=4`, with no duplicate rows. Crossing another boundary creates
   the next interval instead. Running too early reports a creation-time skip.

4. Inspect only that simulation database:

   ```sh
   python backend/manage.py shell <<'PY'
   from django.conf import settings
   from django.db.models import Max
   from monitoring.models import EnergyReading
   assert settings.DATABASES['default']['NAME'] == 'smart_energy_simulation'
   latest = EnergyReading.objects.aggregate(start=Max('timestamp'))['start']
   rows = list(EnergyReading.objects.filter(timestamp=latest).select_related('meter'))
   assert len(rows) == 4
   for r in rows:
       assert r.interval_seconds == 60
       assert r.energy_kwh == r.power_kw / 60
       print(r.meter.meter_type, r.timestamp, r.interval_seconds, r.energy_kwh, r.power_kw)
   PY
   ```

5. For continuous operation run `python backend/manage.py run_telemetry`; stop
   with Ctrl+C. `unset DB_NAME OPENAI_API_KEY` restores normal `.env` selection
   for subsequent commands in that shell. No source flag, batteries, weather
   realism, activation history, backfill or process supervisor is implemented.

Tests run with controlled clocks and separate disposable PostgreSQL data. The next
small task is explicit meter-management workflows so users can configure supported
inventory and verified solar status without relying on shell setup.
