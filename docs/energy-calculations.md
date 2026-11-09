# Shared energy calculations (S1, S2 and S3)

## Measurement policy

- `energy_kwh` is interval energy. `power_kw` is an independent sampled power
  value, not an interval average. Zero energy can coexist with nonzero power.
- `timestamp` is the interval start. Nullable `interval_seconds` explicitly defines
  its duration: `[timestamp, timestamp + interval_seconds)`. The minute simulator
  stores `60`; the hourly fixture generator stores `3600`. No duration is inferred
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
`estimated_daily_cost_eur` is `null`; pricing belongs to S3.

Generated recommendation `estimated_savings_eur` is `null`, including when an AI model
supplies a monetary guess. No hardcoded €0.32 conversion remains in S2. Rule-based
weekly energy goals are illustrative scenarios, not measured savings. A power
sample or shifting a solar load alone does not establish reduced gross kWh, so
those rules leave their legacy kWh-saving field at zero. Existing stored forecasts
and recommendations retain their stored values. Historical monetary guesses are
not automatically repriced and must not be treated as tariff-based estimates.

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

| Measurements | Interpretation to avoid | Shared result |
| --- | --- | --- |
| Same interval: main 100, HVAC 40, lighting 20, solar 30 kWh | Adding included submeters gives 160, or balance 70 is mislabeled as gross. | Gross 100, solar 30, signed balance 70; matched-interval import estimate 70. |
| Main 0 kWh with power sample 7 kW, solar 10 kWh | Replacing zero with baseline, or forcing power/balance to zero. | Gross 0, peak 7, balance −10, import 0, export 10. |
| Day main 0 / solar 10, night main 10 / solar 0 | Using the zero period balance as zero imports and charges. | Import 10 and export 10. At €0.30 import / €0.08 feed-in: €3 charge − €0.80 credit = €2.20 estimate. Gaps prevent a complete-period claim. |
| No main data, baseline 250 | Presenting baseline as measured consumption. | Gross, peak, averages and balance unavailable; baseline stays reference only. |

## Legacy data and hourly fixtures

The numeric/uniqueness migration checks legacy values before adding database
constraints and refuses incompatible data rather than deleting or repairing it.
The interval-metadata migration adds nullable `interval_seconds` and solar status;
it does not guess values for old rows. Existing timestamps, energy values and
inactive-meter history are preserved. The coach migrations permit unavailable
monetary savings and describe forecast bands as illustrative; they do not reprice
stored recommendations.

Unknown legacy durations require dataset provenance before explicit metadata
entry. Gaps, energy/power ratios and meter type do not establish duration. Missing
old solar observations cannot be inserted as zeros without evidence. Uncertain
data remains unknown and can make dependent results unavailable.

`seed_demo_data` is an optional historical fixture command. For a fresh compatible
fixture it creates 14 full UTC days, 3600-second intervals, recorded night solar
zeros and 1,008 readings across three meters. It uses fixed building/device names
and a main-reading-count threshold to skip populated fixtures; this is not a
validation or repair of existing datasets. Partial/incompatible fixtures require
review. It writes hourly data separately from the minute-ingestion service and is
not called at startup. Routine demonstrations use explicit inventory plus the
[minute simulator](simulated-telemetry.md).

Schema setup is documented separately for [Docker](docker-development.md#services-and-startup)
and [host development](host-development.md#schema-and-processes). Automated checks
use the [isolated testing workflow](testing.md), not an application database.

S1 centralizes coverage and measurement rules. S2 uses the all-history summary
and complete days from its forecast window; S3 uses matched grid intervals. These
are direct Python calls, not HTTP requests between subsystems. Dashboard work,
batteries, independent parallel meter coverage and historical tariff/installation
policies are not implemented by these calculations.
