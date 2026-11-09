# Validated S1 telemetry ingestion

`monitoring.services.ingestion.ingest_reading` validates and saves **one new
60-second reading**. It does not generate values, create meters, update solar
installation status or calculate building summaries. Legacy imports and repairs
must use a separately reviewed process.

## Calling the function

```python
from datetime import datetime, timezone

from django.core.exceptions import ValidationError
from monitoring.services.ingestion import ingest_reading

# meter_id must identify an existing active meter in this database.
values = dict(
    meter=meter_id,  # A Meter instance or integer primary key; not device_id.
    timestamp=datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc),
    interval_seconds=60,
    energy_kwh=0.1,
    power_kw=9.0,
    voltage=230.0,
)

reading, created = ingest_reading(**values)  # created=True for a new reading.
same_reading, created = ingest_reading(**values)  # created=False: already exists.
assert same_reading.pk == reading.pk

try:
    ingest_reading(**dict(values, energy_kwh=0.2))
except ValidationError as error:
    # error.error_dict['timestamp'][0].code == 'conflicting_reading'
    print(error.messages)  # Original reading remains 0.1 kWh.
```

All measurement arguments are required. Values must be Python `int` or `float`,
finite and nonnegative. Numeric strings, booleans, `Decimal` and other implicit
conversions are rejected at this boundary. Valid integer measurements are stored
using the model's normal float representation. Aware UTC timestamps must have
zero seconds and microseconds; dates, strings, naive datetimes and nonzero UTC
offsets are rejected. Duration must be the integer `60`, with no default or
inference. No timestamps are rounded. A datetime whose end cannot be represented
is rejected as well.

The example intentionally has `energy_kwh != power_kw / 60`: power is an
instantaneous sample, not the interval's average power. Zero is valid for every
measurement, including voltage. The service reloads the meter from PostgreSQL,
so an old Python object's `is_active=True` cannot bypass a database deactivation.
Even exact retries require the meter to be active.

## Retries, conflicts and coverage

The result is `(reading, created)`, following Django's usual created-flag pattern:

| Situation | Result |
| --- | --- |
| New, valid reading with clear same-meter coverage | Saves one row; returns it with `True`. |
| Same meter/start, identical stored duration, energy, power and voltage | Returns the existing row with `False`, without writing. |
| Same meter/start with different measurements or stored duration | `ValidationError`, code `conflicting_reading`; never overwrites. |
| Known same-meter interval overlaps | `ValidationError`, code `overlapping_reading`. |
| Unknown-duration same-meter interval could overlap | `ValidationError`, code `unknown_coverage`; no duration is guessed. |

Floats are compared exactly after model field conversion, without an epsilon or
rounding. Retrying with an invalid payload still fails validation. Exact retries
return before coverage checks because they add no new energy; they remain retries
even if unrelated old history later becomes unresolved.

Intervals are half-open: `[start, end)`. A 12:00–12:01 reading can touch a
12:01–12:02 reading. An existing 11:30–12:30 hourly reading blocks a new 12:00
minute, and a legacy off-minute reading starting inside that minute blocks it too.

For unknown duration, only the start is known. Any such reading starting **before
the new interval's end** blocks insertion, even if it started years ago. It might
extend into the new minute. One starting exactly at or after the new end cannot
overlap that earlier minute. Establish historical provenance outside this service
before repairing duration metadata.

Only the same meter is checked. Another meter's unknown history or overlapping
timestamps do not block ingestion. Solar can arrive before or after main-meter
data. Whole-building meter ambiguity and main/solar matching remain aggregation's
responsibility.

## Validation and transactions

1. Strict input guards prevent Django's normal date/string coercion from accepting
   unsuitable telemetry input. The existing timestamp validator is reused.
2. A transaction locks and reloads the meter, then checks active status.
3. `full_clean(validate_constraints=False)` runs field/model validation, including
   the existing finite/nonnegative numeric validators. Its pre-save constraint
   queries are intentionally skipped: the `(meter, timestamp)` UniqueConstraint
   would otherwise reject an exact retry before the service could recognize it.
   **All database constraints remain enforced on insertion.**
4. The service checks retries and coverage, then inserts using a savepoint. Only
   an integrity error naming `s1_reading_meter_timestamp_unique` is interpreted as
   a duplicate race. It rolls back the savepoint, reads the winning row and returns
   an exact retry or raises a conflict. Other database errors propagate unchanged.

The PostgreSQL `FOR NO KEY UPDATE` meter-row lock serializes service calls for
that meter, including their coverage checks and insertion. Normal updates to the
meter, including deactivation, must wait for that lock, or complete before the
service acquires it. Different meters are independent. The weaker lock permits
foreign-key checks by other writers; uniqueness still protects duplicate keys.

This guarantee assumes the project's normal PostgreSQL READ COMMITTED isolation.
Writers that bypass this service can still insert different-key overlaps, invalid
timestamps or readings on inactive meters: those rules are not database
constraints. The lock does not turn the service into a universal database gate.
All future telemetry writers should therefore use this function.

Failures leave no new reading from the failed call and do not update existing
readings. If the caller wraps multiple operations in an outer transaction,
successful ingestion is not committed until that outer transaction commits.

## Generator and verification

The [synthetic worker](simulated-telemetry.md) discovers inventory every cycle and
calls this function with duration `60` for each planned building member. It counts
`created=False` as an exact retry and rolls back a building's new set on validation
failure. The worker schedules completed UTC minutes; ingestion never rounds
timestamps or waits for other meters. Ingestion itself still saves only one row;
worker scheduling and building transactions live in the generator/command.

Run checks using the configured separate disposable PostgreSQL test database:

```sh
python backend/manage.py check --database default
python backend/manage.py makemigrations --check --dry-run
python backend/manage.py test config monitoring coach analysis --noinput
git diff --check
```

`test_ingestion.py` includes ordinary validation/coverage tests and PostgreSQL
`TransactionTestCase` tests using separate connections for concurrent duplicate
submissions and deterministic database uniqueness races. Existing tests are
unchanged. No model or migration change is needed for ingestion.
