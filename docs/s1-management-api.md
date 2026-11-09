# S1 management and reading history

The simulator is the project's intended data source. These APIs configure its
inventory and expose stored readings to the dashboard. Manual development/demo
work uses the configured `smart_energy_db`; automated tests use a **separate
disposable PostgreSQL database**. No model/migration change is required here.

## Routes for the dashboard

Both `/api/` and `/api/monitoring/` prefixes work. Examples use `/api/`.

| Route | Methods | Behavior |
| --- | --- | --- |
| `/api/buildings/` | GET, POST | Paginated building list; create building. |
| `/api/buildings/{id}/` | GET, PUT, PATCH | Retrieve or update descriptive fields/allowed solar metadata. |
| `/api/buildings/{id}/meters/` | GET, POST | Paginated list of that building's meters; create an assigned meter. |
| `/api/meters/{id}/` | GET, PATCH | Retrieve meter; PATCH only `is_active`. |
| `/api/buildings/{id}/readings/` | GET | Paginated read-only history, optionally filtered by meter and time. |
| `/api/buildings/{id}/summary/` | GET | Existing all-history summary; calculations and response semantics unchanged. |

HEAD/OPTIONS are also available where supported. There are no hard-delete or
reading-write endpoints. Meter PUT and DELETE return 405. Existing building
response fields remain; nested meter objects gain the additive `building` ID.

### Create/update examples

Create a building with `POST /api/buildings/`:

```json
{"name":"Energy lab","location":"Block A","area_sqm":1200,"baseline_kwh_per_day":200,"has_solar_installation":true}
```

Response: HTTP 201, for example:

```json
{"id":7,"name":"Energy lab","location":"Block A","area_sqm":1200.0,"baseline_kwh_per_day":200.0,"has_solar_installation":true,"meters":[],"created_at":"2026-11-09T12:00:30Z"}
```

Creation requires explicit non-null solar status, even for form submissions. Name
is required. Area must be finite and positive; baseline finite and nonnegative.
Both numeric fields retain their existing model defaults when omitted.
`PATCH /api/buildings/7/` can send `{"location":"Block B"}`. PUT requires name;
omitted optional values are preserved. IDs, creation timestamps, nested meter
writes and unknown write fields are rejected rather than silently accepted.

Create a meter with `POST /api/buildings/7/meters/`:

```json
{"device_id":"LAB7-MAIN","meter_type":"ELECTRICITY","unit":"kWh","is_active":true}
```

Response: HTTP 201, for example:

```json
{"id":12,"building":7,"device_id":"LAB7-MAIN","meter_type":"ELECTRICITY","meter_type_display":"Electricity Main","unit":"kWh","is_active":true,"created_at":"2026-11-09T12:00:31Z"}
```

The URL assigns ownership; sending `building` in the body is rejected. Device ID
is required and globally unique. Supported types are ELECTRICITY, HVAC, LIGHTING,
SOLAR; unit is kWh. Omitted type/unit/active retain model defaults
ELECTRICITY/kWh/true. Multiple HVAC/lighting meters are allowed.

Activate/deactivate using `PATCH /api/meters/12/`:

```json
{"is_active":false}
```

HTTP 200 returns the full meter object with the updated flag. Device ID, type,
unit, building, ID and creation time are immutable through this endpoint, even
before readings exist. Do not send the full GET object as the PATCH body.

### Inventory and history policy

- Creation/activation permits **at most one active main and one active solar** per
  building. Inactive spares are allowed; deactivate an old main before activating
  a replacement. The API permits temporary missing main/solar meters during setup.
- Any solar meter creation, including an inactive one, requires declared solar
  status `true`. Solar reactivation also requires `true`. The API does not infer
  installations or change metadata from a device's existence.
- Deactivation is always allowed, including for a required main/solar meter or
  inconsistent legacy inventory. It preserves readings and may pause generation.
  Existing HVAC/lighting meters can be deactivated and reactivated normally.
- A **change** to solar status is rejected after **any building reading** exists,
  including zero readings, inactive meters' data and legacy unknown-duration rows.
  This protects earlier no-solar assumptions as well as recorded solar generation.
  Same-value status and descriptive updates remain allowed. Legacy unknown status
  remains readable but cannot be ordinarily repaired after history exists.
- Before history exists, false/true setup changes are allowed, except declaring
  `false` when any SOLAR meter is configured, including inactive ones. Historical
  installation changes/corrections need a reviewed process, not this ordinary API.

Writes call model `full_clean()`; serializer validation alone is not treated as
model validation. Inventory operations lock the building first and current meters
in ascending PK order, matching the generator. Checks use fresh locked state, so
concurrent supported API attempts cannot create/activate competing mains/solar.
Normal ingestion's meter lock coordinates the history check with incoming data.
Device-ID uniqueness also has a database constraint: a cross-building race is
returned as a field error, with failed insertion rolled back. Other DB errors are
not hidden. Writers bypassing these services do **not** gain these API policies.

### History query and response

Example request:

```text
GET /api/buildings/7/readings/?meter_id=12&start=2026-11-09T12:00:00Z&end=2026-11-10T00:00:00Z&page=1&page_size=100
```

`meter_id`, `start` and `end` are optional. The meter must belong to the requested
building; missing or wrong-building meters return 404, not another building's
rows. This is relational scoping, not per-user authorization.

Bounds must be aware ISO 8601 datetimes, with `Z` or an explicit offset. Non-UTC
offsets are accepted; URL-encode `+` as `%2B` or use curl `--data-urlencode`.
Empty, malformed, naive, equal or reversed bounds return 400 field errors.
Filtering selects **interval starts** in `[start,end)`, not intervals overlapping
the window; it does not prorate energy or reinterpret hourly/unknown durations.
Inactive-meter readings remain included.

HTTP 200 response:

```json
{"count":1,"next":null,"previous":null,"results":[{"id":50,"meter":12,"meter_device_id":"LAB7-MAIN","meter_type":"ELECTRICITY","meter_unit":"kWh","timestamp":"2026-11-09T12:00:00Z","interval_seconds":60,"energy_kwh":0.2,"power_kw":12.0,"voltage":230.0}]}
```

Legacy `interval_seconds` may be null. Ordering is newest first by timestamp,
then ID descending as a tie-breaker. History defaults to 100 rows; `page_size` is
capped at 500. Standard DRF invalid page-size handling falls back to the default;
an invalid/out-of-range page returns 404. Building/meter lists retain project
pagination: 20 rows per page, with the same envelope. Meter history uses a joined
query to avoid one extra query per row. Page-number pagination is not a frozen
snapshot during live inserts; a fixed end bound is useful when paging completed
history, though backdated/bypass writes can still change the result set.

### Errors and access control

Validation errors use HTTP 400 and field names, for example:

```json
{"device_id":["A meter with this device ID already exists."]}
```

```json
{"is_active":["This building already has an active ELECTRICITY meter; deactivate it first."]}
```

```json
{"end":["End must be after start."]}
```

Exact wording can come from Django/DRF validators. Unknown resources return 404;
unsupported methods return 405. Existing global permissions are **AllowAny**:
these management endpoints require no login, and there is no per-user building
ownership. CORS currently allows all origins. These development endpoints are
**not suitable for public internet deployment** without access-control work.
Authentication redesign is outside this change.

## Manual API verification later

These steps intentionally write demo data to the configured development database
(`smart_energy_db`), not the disposable automated-test database. They were not
executed against application data during implementation. No `.env` edit or
separate simulation database is needed.

1. Activate `.venv`, confirm your normal local database configuration, and start
   `python backend/manage.py runserver`. Use a second terminal for the commands
   below. Create a fresh building so old unknown-duration history cannot block it:

   ```sh
   API=http://127.0.0.1:8000/api
   s1_building_json=$(curl -fsS -X POST "$API/buildings/" -H 'Content-Type: application/json' \
     -d '{"name":"API demo","location":"Lab","area_sqm":1000,"baseline_kwh_per_day":200,"has_solar_installation":true}')
   printf '%s\n' "$s1_building_json"
   BUILDING_ID=$(printf '%s' "$s1_building_json" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
   ```

2. Create main/HVAC/solar explicitly; save the HVAC ID for deactivation:

   ```sh
   curl -fsS -X POST "$API/buildings/$BUILDING_ID/meters/" -H 'Content-Type: application/json' \
     -d "{\"device_id\":\"API-$BUILDING_ID-MAIN\",\"meter_type\":\"ELECTRICITY\"}"
   s1_meter_json=$(curl -fsS -X POST "$API/buildings/$BUILDING_ID/meters/" -H 'Content-Type: application/json' \
     -d "{\"device_id\":\"API-$BUILDING_ID-HVAC\",\"meter_type\":\"HVAC\"}")
   METER_ID=$(printf '%s' "$s1_meter_json" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
   curl -fsS -X POST "$API/buildings/$BUILDING_ID/meters/" -H 'Content-Type: application/json' \
     -d "{\"device_id\":\"API-$BUILDING_ID-PV\",\"meter_type\":\"SOLAR\"}"
   curl -fsS "$API/buildings/$BUILDING_ID/"
   ```

3. Wait two UTC minute boundaries after the last meter creation, then run
   `python backend/manage.py run_telemetry --once` from the activated project
   environment. The worker processes every configured building and reports skips
   or failures for other existing inventories; this new building should generate
   three rows. Inspect it:

   ```sh
   curl -fsS "$API/buildings/$BUILDING_ID/readings/?page_size=10"
   curl -fsS "$API/buildings/$BUILDING_ID/summary/"
   curl -fsS -X PATCH "$API/meters/$METER_ID/" -H 'Content-Type: application/json' -d '{"is_active":false}'
   curl -fsS "$API/buildings/$BUILDING_ID/readings/?meter_id=$METER_ID"
   curl -fsS -X PATCH "$API/meters/$METER_ID/" -H 'Content-Type: application/json' -d '{"is_active":true}'
   ```

   The deactivated meter's old row remains in history. For a stopped-meter check,
   leave it inactive through a later continuous worker cycle and confirm no new
   row arrives, then reactivate. Do not retry an already-written minute after
   changing its eligible inventory: the generator correctly reports a changed-set
   conflict. Subsequent new minutes use the new inventory.

4. Exercise errors without overwriting data: repeat a device-ID POST; try a second
   active main; PATCH a meter's `meter_type`; PATCH solar status after readings;
   request history with `start=bad` or another building's `meter_id`. Expect field
   errors/404, and verify the original objects/readings remain unchanged.

Automated verification is `python backend/manage.py test config monitoring coach
analysis --noinput` using the configured **separate disposable PostgreSQL test DB**,
plus Django checks, migration consistency and `git diff --check`.

S1 is ready for Docker integration once these changes are reviewed and the target
inventory/legacy metadata are checked. Activation timestamps, historical metadata
repair, process supervision and access-control hardening remain separate work;
Docker Compose will provide process setup, not fix those data policies.
