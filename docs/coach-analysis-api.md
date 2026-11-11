# S2 coach and S3 analysis APIs

These services use the [shared S1 Python calculations](energy-calculations.md)
within Django; they do not request the S1 summary HTTP endpoint. Requests use the
same API server as [S1](s1-management-api.md). Examples use Bash/zsh and the
`/api/` prefix; `/api/coach/` and `/api/analysis/` also expose their own routes.

## S2 routes and prerequisites

| Route | Methods | Behavior |
| --- | --- | --- |
| `/api/buildings/{id}/forecast/` | GET, POST | Recalculate/store daily forecasts and return availability. |
| `/api/recommendations/generate/` | POST | Assess observations and generate/store recommendations if sufficient. |
| `/api/recommendations/` | GET | Paginated stored recommendations; optional `building_id`. |
| `/api/recommendations/{id}/feedback/` | POST | Store submitted feedback; limitations below apply. |

The daily forecaster needs at least **two fully covered UTC days** in the preceding
14 completed UTC calendar days. The current partial day is excluded. Missing days
are not filled with zero consumption, and baseline is never substituted for
observed energy. A new minute-based demo will not immediately meet this requirement.

A usable request returns seven predicted daily totals starting tomorrow, together
with `confidence_lower_kwh`, `confidence_upper_kwh` and a baseline-comparison
`trend`. The weekday/weekend profile, small drift and widening bands are heuristic,
not a calibrated statistical model. Insufficient or unresolved history returns
HTTP 200 with `forecast=[]`, nullable totals and an availability reason.
**Both GET and POST can persist forecasts**; this route is not a read-only query.

Recommendation generation accepts:

```json
{"building_id":1,"target_savings_pct":15}
```

The optional savings target is 1–50%. The response includes the all-history energy
summary, recent complete-day forecast availability, an illustrative sustainability
assessment and recommendation records. Complete matched main/solar observations
(or explicit absence of solar) are required for the daily assessment inputs.
Insufficient data returns HTTP 200, `availability.available=false`, no new
recommendations and engine status `NOT_RUN`. Forecast calculation may still have
stored valid forecasts before recommendation eligibility is determined. A usable
generation returns HTTP 201 and stores recommendations plus an execution log.

Docker explicitly disables external AI calls. Without a usable configured key,
the deterministic rule-based provider is used. Optional OpenAI requests use the
configured model and record tokens, latency and status; tests mock this integration.
Weekly energy goals and scores are illustrative, not measured savings. Monetary
recommendation savings and the daily cost field are unavailable; tariff estimates
belong to S3. The fixed carbon factor is a scenario assumption.

### Feedback behavior and limitations

Feedback stores a recommendation reference, optional user, integer rating (`1–5`),
acceptance flag and comment. It does not train or update the recommendation engine.
`POST /api/recommendations/{id}/feedback/` binds the feedback to `{id}` in the URL
(if `recommendation` is also supplied in the request body, it must match `{id}`).
Authentication is not required by the current permission policy, so a submitted
user reference is not verified ownership.

## S3 routes and prerequisites

| Route | Methods | Behavior |
| --- | --- | --- |
| `/api/tariffs/` | GET, POST | List/create global scenario tariffs (validated; only one may be active). |
| `/api/tariffs/{id}/` | GET, PUT, PATCH | Retrieve/update a tariff, e.g. deactivate it. |
| `/api/buildings/{id}/cost/` | GET | Estimate costs from recorded matched intervals. |
| `/api/buildings/{id}/scenarios/` | POST | What-if re-pricing: alternative tariff, consumption and solar change. |
| `/api/buildings/{id}/reports/` | GET, POST | List/generate stored cost reports for an inclusive UTC date range. |
| `/api/reports/` | GET | Paginated stored cost reports; optional `building_id`. |
| `/api/alerts/` | GET | List stored alerts; optional `building_id`, `is_resolved`, `severity`, `alert_type`. |
| `/api/alerts/detect/` | POST | Run rule-based detection for `{"building_id":1}` and store new alerts. |
| `/api/alerts/{id}/` | GET, PUT, PATCH | Retrieve an alert; only `is_resolved` can be changed. |

### Scenarios, reports and alert rules

`POST /api/buildings/{id}/scenarios/` accepts optional `tariff` (rates, peak hours;
never stored), `consumption_change_pct` and `solar_change_pct` (signed). It returns
baseline (active tariff) and scenario import/export kWh and costs plus the net-cost
difference. It needs the same complete coverage as the cost estimate; otherwise
`available=false` with a reason.

`POST /api/buildings/{id}/reports/` with `{"period_start":"2026-01-05","period_end":"2026-01-05"}`
stores a `CostReport` (net cost from estimated imports minus export credit). Both
dates are inclusive UTC days and must be continuously covered by main readings;
otherwise HTTP 422 with a reason and nothing stored.

Alert detection is a simple threshold heuristic, not a statistical model:
`PEAK_SPIKE` (latest power above 2x the 24 h mean), `UNUSUAL_NIGHT_LOAD` (00:00-04:59 UTC
mean above 50 % of the daytime mean), `BUDGET_EXCEEDED` (latest complete UTC day above the
building baseline), `METER_OFFLINE` (no reading for 15 minutes). Rules stay silent on too
little data, and an unresolved alert of the same type/meter is not duplicated. Detection runs
only when `/api/alerts/detect/` is called; there is no background scheduler.

Cost calculations require exactly **one active global tariff**. Check the existing
list before creating a plan; POST is not an idempotent configuration operation.
For a database with no active tariff, an explicit flat-rate example is:

```sh
curl -fsS http://127.0.0.1:8000/api/tariffs/
curl -fsS -X POST http://127.0.0.1:8000/api/tariffs/ \
  -H 'Content-Type: application/json' \
  -d '{"name":"Local demo flat tariff","rate_standard_eur_per_kwh":0.30,"rate_peak_eur_per_kwh":0.30,"peak_start_hour":11,"peak_end_hour":16,"solar_feed_in_eur_per_kwh":0.08,"is_active":true}'
curl -fsS http://127.0.0.1:8000/api/buildings/1/cost/
```

The tariff API rejects invalid rates/hours and a second active plan; deactivate
the current one via PATCH first (the admin can still bypass this check). Missing/multiple
active tariffs produce unavailable costs rather than an arbitrary selection. The
cost service rejects invalid rates/hours; tariff storage itself does not enforce
all those calculation rules.

Standard/peak prices apply to estimated interval imports, feed-in price to
estimated exports. Bands use UTC and support overnight periods. A known interval
crossing unequal price bands cannot be priced without finer measurements. The
active tariff is a scenario applied to recorded history, not an effective-dated
contract. Gaps or unavailable measurements remain explicit. See the
[measurement and pricing contract](energy-calculations.md#s3-tariff-estimates)
for fields, signed balances, import/export estimates and nullable legacy totals.

Cost responses are not complete utility bills: taxes, fixed fees, contract history
and a billing-period model are absent. Reports are scenario estimates over a
covered period, not invoices.

The current `AllowAny` policy and permissive CORS apply across these endpoints.
They are not suitable for public deployment without access-control work. Test
commands and coverage limits are maintained in the [testing guide](testing.md).
