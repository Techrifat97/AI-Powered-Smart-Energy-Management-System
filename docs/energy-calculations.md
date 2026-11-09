# Shared energy calculations (S1, S2 and S3)

## Measurement policy

- `energy_kwh` is interval energy. `power_kw` is an independent sampled power
  value, not an interval average. Zero energy can coexist with nonzero power.
- `timestamp` is the interval start. Nullable `interval_seconds` explicitly defines
  its duration: `[timestamp, timestamp + interval_seconds)`. New telemetry will
  supply `60`; the new demo generator supplies `3600`. No duration is inferred
  from timestamp gaps, energy/power ratios or meter type.
- `ELECTRICITY` is gross whole-building load. HVAC and lighting are included in
  that load. Solar is separate generation. Deactivated meters retain their data
  and continue contributing to historical calculations.
- Known nonoverlapping mains may represent sequential replacements. Any overlap,
  including on one meter or between hourly and minute readings, makes gross,
  peak and averages unavailable. Unknown duration also makes dependent results
  unavailable; two recording mains with unknown coverage are flagged ambiguous.
  Unused meters do not cause ambiguity. Solar coverage uses the same conservative
  overlap policy; multiple simultaneous solar meters are not assumed independent.
- `Building.has_solar_installation` is `true`, `false` or `null` (unknown).
  `false` is an explicit declaration that no installation exists **throughout the
  reported history**, not a deduction from missing readings or inactive meters.
  With `true` or `null`, missing solar remains unknown; a matching recorded solar
  zero is valid evidence. `false` conflicting with solar observations is flagged.
  A later installation/removal needs historical policy before changing this flag.
- The MVP assumes **no battery**. With exact matching, unambiguous main and solar
  intervals, estimate `import=max(gross-solar, 0)` and
  `export=max(solar-gross, 0)` separately for each interval, then sum separately.
  Confirmed absence of solar supplies explicit zero generation. Missing solar
  intervals, extra unmatched solar intervals or unknown durations block estimates.
  No intrainterval import/export fluctuations can be recovered this way.

## Shared Python functions and time scopes

`monitoring.services.aggregation.summarize_building(building, *, start=None, end=None)`
returns the public S1 summary dictionary. `building_energy_report` accepts the
same arguments and additionally returns `main_intervals`, `grid_intervals` and
`complete_days` for S2/S3. Pass a saved `Building`; bounds must be aware datetimes.
Invalid bounds raise `ValueError`.

The default scope is all history. Optional bounds select **interval starts** in
`[start, end)`. Intervals crossing the end boundary are unavailable rather than
prorated. Known overlaps starting before a window are checked too. An earlier
unknown duration blocks a later window because its end cannot be established;
resolve its provenance rather than guessing it ended before the window.
The REST summary and cost endpoints remain all-history endpoints: query-string
start/end parameters are not implemented.

Gaps never become measured zeros. Gross totals can summarize known, unambiguous
recorded intervals even if gaps exist. `main_coverage_complete` reports whether
main intervals continuously cover `scope_start` to `scope_end`; without explicit
bounds this is the span from first main start to last main end. This does not
prove completeness before/after that span or imply a calendar billing period.

| Field | Meaning / unavailable behavior |
| --- | --- |
| `total_consumption_kwh` | Gross main energy only; `null` if missing, unknown duration or ambiguous. |
| `peak_demand_kw` | Largest recorded main-meter power sample; `null` if main coverage cannot be resolved. Zero kWh alone does not make this zero. |
| `total_solar_generated_kwh` | Known, nonoverlapping recorded solar sum; `null` if missing/unknown/ambiguous, or zero for explicitly absent installation. |
| `net_grid_consumption_kwh` | Legacy **signed recorded energy balance** gross minus solar; `null` if either total unavailable. Totals may have different recorded coverage. This is not an import/export estimate. |
| `estimated_grid_import_kwh`, `estimated_grid_export_kwh` | Separate sums over exactly matched intervals, or confirmed no solar; otherwise `null`. Estimates cover recorded intervals only. |
| `average_daily_kwh` | Mean of recorded main totals grouped by UTC start date, including partial days; never a full-day extrapolation. |
| `full_day_average_kwh` | Mean only of complete UTC days (`00:00` through next `00:00`), otherwise `null`. Cross-midnight intervals are not arbitrarily split. |
| `main_data_available`, `main_data_ambiguous`, `main_data_reason` | Availability/ambiguity and a machine-readable reason. |
| `solar_data_available`, `solar_data_reason` | Solar availability, including `confirmed_no_installation` or conflicting inventory. |
| `grid_estimates_available`, `grid_estimates_reason` | Whether interval matching supports estimates. |
| `main_readings_count`, `main_meter_count`, `recorded_main_days_count` | Main records, recording mains and UTC start dates in scope. |
| `complete_main_days_count`, `solar_readings_count` | Fully covered UTC days and recorded solar records. |
| `active_meters_count` | Current inventory, independent of historical inclusion. |
| `total_readings_count`, `earliest_reading`, `latest_reading` | All meter types in scope; dates are starts, not interval ends. |

Baseline is comparison information only. Consumers must check availability/null
before arithmetic. Do not use `value or baseline` or `value or 0` for measurements.
Float precision is retained in S1; round for display only.

## S2 behavior

Forecasting uses the preceding **14 completed UTC calendar days**, excluding the
current partial day. At least two completely covered days are required. Missing
dates are excluded, never filled with zeros; the complete-days count is returned.
This small threshold is an explicit MVP policy, not evidence of predictive accuracy.
With insufficient, unknown or ambiguous data, `forecast=[]`, aggregate prediction
fields are `null`, and `availability` gives the reason. Previously saved forecasts
are not returned as newly calculated observations.

Available forecasts start tomorrow and retain the existing seven-day weekday /
weekend heuristic. The `confidence_*` names remain for compatibility, but these
are illustrative bands, **not calibrated 95% intervals**. `trend` compares the
observed average with baseline, rather than estimating a measured temporal trend.

Recommendations expose the all-history `energy_summary`, plus
`forecast_availability` identifying the recent full-day observation window. Daily
assessment and recommendation inputs use those recent complete days; sampled
peak is the all-history main peak. If main history, complete days or matched solar
coverage are insufficient, return HTTP 200 with `availability.available=false`,
an empty recommendation list and `engine_telemetry.status=NOT_RUN`. No AI request
or recommendation/log write is made in that case. A usable generation retains
HTTP 201 and the existing response names.

The score is an illustrative baseline comparison and is unavailable with no
positive baseline or missing daily measurements. Carbon is an explicit scenario
using average matched-interval imports and `0.385 kg/kWh`; it does not net solar
across an entire day. Solar offset ratio is unavailable when gross is zero.
`estimated_daily_cost_eur` is now `null`; pricing belongs to S3.

New recommendation `estimated_savings_eur` is `null`, including when an AI model
supplies a monetary guess. No hardcoded €0.32 conversion remains in S2. Rule-based
weekly energy goals are illustrative scenarios, not measured savings. A power
sample or shifting a solar load alone does not establish reduced gross kWh, so
those rules leave their legacy kWh-saving field at zero. Existing stored forecasts
and recommendations are preserved; old monetary guesses are not re-priced by
these migrations. Audit them before treating them as tariff-based estimates.

## S3 tariff estimates

`GET /api/buildings/{id}/cost/` reuses S1's all-history report. Exactly one active
`TariffPlan` must exist. It is the explicit **global MVP scenario tariff** applied
to the selected history; there is no building assignment or effective-date model.
Zero or multiple active tariffs make prices unavailable, with a reason. No
arbitrary first tariff or hardcoded fallback is used. Rates must be finite and
nonnegative, and peak start/end hours must be distinct values from 0 to 23.

Peak bands are `[peak_start_hour, peak_end_hour)` in **UTC every day**; overnight
bands are supported. This is a documented MVP convention, not a claim about a
real contract's local timezone. Standard and peak prices apply to estimated
interval imports. Feed-in price applies only to estimated exports, including an
explicit zero compensation rate. If an interval crosses unequal price bands,
prices are unavailable: uniform consumption within that interval is not assumed.
A flat tariff can price such intervals without allocating their energy.

- `estimated_import_cost_eur`: sum of interval imports × applicable import rate.
- `estimated_export_credit_eur`: sum of exports × explicit feed-in price.
- `estimated_net_cost_eur`: import charge minus export credit; it may be negative.
- `cost_estimates_available` / `cost_estimates_reason`: price availability.
- `coverage_complete`: S1's main span coverage; gaps remain visible.
- `complete_bill_available`: always `false`; these are scenario estimates without
  contract effective dates, fixed fees, taxes or a specified billing period.
- Legacy `gross_cost_eur`: hypothetical cost of gross energy before solar;
  `solar_savings_eur`: estimated self-consumed solar × import rate;
  `net_cost_eur`: import charge minus export credit. These three legacy totals are
  `null` if prices or continuous span coverage are unavailable. New estimate
  fields may describe matched recorded intervals even when the span has gaps.
- `rate_eur_per_kwh` remains the standard rate for compatibility, not a claim that
  peak intervals use that rate. See `tariff_timezone` and `pricing_scope`.

Decimal currency arithmetic is rounded once after summing, to cents. Period-level
solar generation is never all credited at the import price.

## Small numerical checks

| Measurements | Previous problem | Shared result |
| --- | --- | --- |
| Same interval: main 100, HVAC 40, lighting 20, solar 30 kWh | Gross could become 160, or net 70 mislabeled as gross. | Gross 100, solar 30, signed balance 70; matched-interval import estimate 70. |
| Main 0 kWh with power sample 7 kW, solar 10 kWh | Baseline fallback or all fields forced to zero. | Gross 0, peak 7, balance −10, import 0, export 10. |
| Day main 0 / solar 10, night main 10 / solar 0 | Period balance zero hid both flows and charges. | Import 10 and export 10. At €0.30 import / €0.08 feed-in: €3 charge − €0.80 credit = €2.20 estimate. Gaps prevent a complete-period claim. |
| No main data, baseline 250 | Baseline presented as measured consumption. | Gross, peak, averages and balance unavailable; baseline stays reference only. |

## Migrations and teammate setup after pulling

1. Preserve local work before pulling the reviewed changes. Activate the virtual
   environment and run `python -m pip install -r requirements.txt`. Configure local
   PostgreSQL `.env` credentials without committing them. Dependencies are unchanged.
2. Back up and inspect the local application database before applying migrations.
   Run `python backend/manage.py showmigrations` and
   `python backend/manage.py migrate --plan`, then
   `python backend/manage.py migrate` when ready. These commands are teammate
   setup instructions; this integration task did **not** migrate the application DB.
3. New `monitoring.0003` adds nullable solar status and nullable positive duration.
   Existing readings, values, timestamps and inactive-meter history are preserved.
   Existing durations and solar status remain `null`: do not blanket-label legacy
   rows. Establish provenance for each known dataset before explicitly recording
   its duration. Missing old solar observations cannot be backfilled as zeros
   without evidence. Leave uncertain data unknown and expect unavailable results.
4. `coach.0002` permits unavailable monetary recommendation savings;
   `coach.0003` corrects forecast-band help text. Old migrations are unchanged.
   Existing stored recommendation/forecast values remain preserved.
5. For a **new disposable demo database**, after migrating, optionally run
   `python backend/manage.py seed_demo_data`. New data has 14 full UTC days,
   3600-second intervals, explicit solar zeros and 1,008 readings. The command
   skips populated demos; it does not repair old metadata or overwrite old values.
   The [synthetic worker](simulated-telemetry.md) explicitly supplies 60-second
   duration through validated ingestion. Do not run demo seeding as a data repair.
6. Confirm `DB_TEST_NAME` names an unused disposable PostgreSQL database,
   starts with `test_` and differs from the application database. The local test
   role needs `CREATEDB`. Leave `OPENAI_API_KEY` empty in the test process. Run:

   ```sh
   python backend/manage.py check --database default
   python backend/manage.py makemigrations --check --dry-run
   python backend/manage.py test config monitoring coach analysis --noinput
   git diff --check
   ```

7. API clients should display unavailable values using the availability/reason
   fields before arithmetic. Confirm solar status for the reporting history and
   configure one applicable global scenario tariff before demonstrating costs.

S1 loads stored readings and resolves their coverage once. S2 uses that report's
complete days for forecasting and assessment. S3 uses its matched import/export
intervals for tariff estimates. Neither consumer adds submeters to the main load
or invents missing measurements.

Legacy-data provenance and explicit metadata entry remain necessary for old rows.
Validated ingestion and a [synthetic minute worker](simulated-telemetry.md) are now
available. Dashboard changes, batteries, true grid-flow meters, independent
parallel meter networks and historical tariff/installation policies remain outside
these calculations.
