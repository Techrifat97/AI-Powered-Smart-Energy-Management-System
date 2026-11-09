# S1 simulated telemetry

The simulator is the project's intended primary data source; no physical IoT
integration is planned. Its values are synthetic, not a calibrated building or
weather model, and command output is labelled `SYNTHETIC`. Manual development and
demos use the configured PostgreSQL database, normally `smart_energy_db`.
Automated tests alone use a separate disposable PostgreSQL test database.

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

The `run_telemetry` management command supports continuous operation and `--once`.
See [Docker operations](docker-development.md#explicit-demo-inventory) or
[host processes](host-development.md#schema-and-processes) for environment-specific
commands.

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
retains diagnostic details. Ctrl+C and container SIGTERM stop cleanly; if they interrupt a write, the
current building transaction rolls back while earlier completed buildings remain.

## Operation

The configured development database holds simulator data; a separate simulation
database is not required. Docker has its own PostgreSQL server/volume, independent
of host PostgreSQL. Follow the [Docker guide](docker-development.md) for private
configuration, startup, explicit four-meter demo initialization and logs, or
[host development](host-development.md) for the optional direct setup.

Meter eligibility is based on interval start: a meter created at 12:00:30 UTC
first qualifies for `[12:01,12:02)`, processed at 12:02. Waiting two minute boundaries
after setup ensures this interval is complete. Inventory changes apply to new
cycles; retrying a previously written minute with changed eligible membership is
a conflict. The [S1 API guide](s1-management-api.md#manual-api-checks) demonstrates
meter deactivation/reactivation and historical retention.

Unknown-duration history can block ingestion. No command automatically repairs
legacy data, invents missing intervals or backfills downtime. Automated checks use
controlled clocks and a [separate disposable test database](testing.md).
