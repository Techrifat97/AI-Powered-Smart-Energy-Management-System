# University Submission Review

Reviewed on 13 November 2026 against main commit `88b7f0e`, including PR #13.
The documentation branch is `docs/university-submission-cleanup`.
The initial working tree was clean. Fetching `origin/main` confirmed an identical
local/remote commit. Source review preceded documentation edits.

## Implementation assessment

| Area | Verified implementation | Important limitations |
|---|---|---|
| S1 | Validated inventory and ingestion, explicit interval metadata, deterministic profile strategies, durable Kafka outbox/receipt processing, historical bootstrap, history APIs and shared aggregation. | Service bypass writes, missing activation timelines, historical gaps, unbounded history scans and outbox retention. |
| S2 | Complete-day forecast gating, seven heuristic predictions, baseline-relative score, carbon scenario, optional OpenAI/rule-based recommendations, stored logs and authenticated feedback. | Unvalidated provider output can partially persist, request retries can repeat actions, heuristic outputs lack calibration, and feedback has no training workflow. |
| S3 | Tariff validation, interval pricing, automatic/explicit scenario periods, alert-rule ABCs, stored reports, CSV UI export and OpenAI/template explanations. | Several invalid inputs return 500, active-tariff and alert uniqueness rely on sequential checks, scenario tariff validation differs from costs, and some explanatory wording overstates measurements. |
| Accounts | JWT issue/refresh, current profile, authenticated user creation/list/deletion and current-user feedback attribution. | Account management is available to ordinary authenticated users, password validators are bypassed on API creation, and building ownership is unmodeled. |
| Dashboard | Login, session restoration, ten authenticated pages, charting, inventory controls and S2/S3 workflows. | Process-wide session restoration can authenticate a different browser, and daily chart calculations bypass conservative shared measurement rules. |
| Runtime | Seven Compose services with persistent PostgreSQL/Kafka, backend migration/bootstrap before serving, topic initialization and worker dependency conditions. | Published HTTP interfaces, development defaults and CORS need review. Health is an HTTP probe. The local private configuration differs from the running backend connection. |

The source review covered all backend apps, every service, serializers, views,
routes, models, migrations, admin registrations, commands, settings, dependencies,
tests, Streamlit source/theme/assets, the historical acceptance script and every
existing Markdown/UML document. The current snapshot contains 91 Python files.
The three subsystem guides provide class responsibilities, exact APIs, validation,
OOP evidence and technical requirements.

## Confirmed bugs and security findings

### R01 — Critical shared dashboard authentication state

`get_session_cache()` uses process-wide `st.cache_resource`. A browser session
without an `auth_token` or `sid` can restore `_SESSION_CACHE['active_session']`.
That entry contains another login's JWT. A `sid` also derives from username and a
seconds timestamp. Logging out or receiving a domain 401 clears the shared cache.
The existing `test_session_restored_on_tab_reload_even_without_query_params`
creates a new AppTest session and confirms token restoration without credentials.
This behavior exposes the previous authenticated account to another browser using
the same frontend process. [Session cache and restoration](../frontend/app.py#L27),
[existing session tests](../frontend/test_app.py#L111)

### R02 — High broad account management and weak password acceptance

Both account-management views require `IsAuthenticated`, with no staff or owner
check. A nonstaff member can list accounts, create another user and delete another
ordinary user. The primary-admin and self-deletion guards still apply. The serializer
calls `create_user()` without Django `validate_password()`. A disposable probe
successfully created an account with a one-character password and deleted it as a
nonstaff user. UI wording that reserves management for administrators exceeds the
API's implemented permission policy. [Account views](../backend/accounts/views.py#L11),
[user creation](../backend/accounts/serializers.py#L7)

### R03 — High malformed AI output can leave partial stored recommendations

The coach accepts a nonempty JSON list, logs the provider result and creates records
one at a time. Numeric conversion and persistence occur after the provider try/except
and have no surrounding transaction. A mocked response with one valid action followed
by invalid numeric savings raised `ValueError` after storing one recommendation and
one request log. Field choices, numeric finiteness and score ranges also lack complete
provider-output validation. [Coach generation](../backend/coach/services/llm_coach.py#L101)

### R04 — Medium maximum report date returns an internal server error

The report serializer accepts `9999-12-31`, and report generation adds a day to the
inclusive end date without an overflow guard. A disposable API probe returned 500.
The scenario serializer already rejects this value, so the two date contracts differ.
[Report generation](../backend/analysis/services/reports.py#L9),
[request serializers](../backend/analysis/serializers.py#L86)

### R05 — Medium malformed list filters return internal server errors

The alerts and reports list views pass `building_id` directly into integer ORM
filters. Requests with `building_id=invalid` returned 500 in isolated probes. The
recommendation list handles malformed IDs with a validation response.
[Alert filters](../backend/analysis/views.py#L39),
[report filters](../backend/analysis/views.py#L154)

### R06 — Medium scenario and cost tariff validation are inconsistent

`cost_analysis()` rejects invalid stored tariff rates/hours. `run_scenario()` checks
active tariff count but passes that record directly to `_price()`. A disposable
legacy fixture with negative stored import rates produced `invalid_tariff` from
cost analysis and an available scenario with negative baseline cost. Serializer
validation protects normal API writes, while model/admin/bypass writes can supply
such records. [Cost validation](../backend/analysis/services/costs.py#L37),
[scenario pricing](../backend/analysis/services/scenarios.py#L57)

### R07 — Medium dashboard daily charts bypass shared quality rules

`daily_energy()` sums meter rows and calls `fillna(0)`. Missing solar on a day can
therefore appear as a recorded zero. Overlapping or ambiguous mains are added
without S1's availability checks. Its 100-page safety cap can silently truncate
larger histories. Live chart pivoting averages same-type samples. The primary S1
summary continues to use conservative aggregation, so a chart can disagree with
its summary. [Daily chart loader](../frontend/app.py#L201),
[shared aggregation](../backend/monitoring/services/aggregation.py#L42)

### R08 — Medium cost wording and daily averages can misrepresent coverage

The cost UI and `build_cost_facts()` divide cost by elapsed time between first and
last reading starts. That span excludes the final interval duration and includes
gaps. The UI and explanation say “You paid” although the values apply the current
scenario tariff to observations. The template claims most solar was used in the
building whenever generation is positive, without checking the self-consumed share.
[Cost facts and templates](../backend/analysis/services/explainer.py#L31),
[cost page](../frontend/app.py#L710)

## Integration risks and technical limitations

| Finding | Classification and evidence |
|---|---|
| Concurrent active tariffs | Confirmed missing enforcement mechanism, with concurrency behavior untested in this review. Serializer query checks and multi-request UI switching provide no database single-active constraint or shared transaction. The backend safely reports ambiguous active tariffs in cost analysis. [Serializer](../backend/analysis/serializers.py#L7), [UI switch](../frontend/app.py#L631) |
| Concurrent duplicate alerts | Confirmed check-then-create pattern. Sequential tests pass, while concurrent detection has no uniqueness constraint. Absolute “never duplicated” wording in older documentation is too strong. [Detector](../backend/analysis/services/alerts.py#L154) |
| Report tariff race | Report generation prices through one tariff lookup and later fetches an active tariff again for the saved reference. Concurrent changes can create an inconsistent reference. This race was identified by inspection. [Report service](../backend/analysis/services/reports.py#L9) |
| Development credentials and exposure | Demo bootstrap creates a hardcoded administrator password. Settings and Compose contain development defaults, CORS allows all origins, and backend/frontend ports bind to all host interfaces. These facts are visible in source. The README publishes only the existing public evaluator credentials. [Demo setup](../backend/monitoring/services/demo.py#L141), [settings](../backend/config/settings.py), [Compose](../compose.yaml) |
| Token lifecycle | Login stores an access token and leaves refresh handling unused in the frontend. Logout clears UI state. JWT blacklist/revocation is unconfigured. API access tokens last 24 hours and refresh tokens seven days. [Settings](../backend/config/settings.py#L128), [frontend](../frontend/app.py#L170) |
| Health probe scope | `/api/health/` returns a constant successful response without accessing PostgreSQL. A healthy API container can still require a domain/database check. [Health view](../backend/monitoring/views.py#L20) |
| Runtime configuration mismatch | Initial one-off Compose tests failed PostgreSQL password authentication with the current host `.env`. Tests succeeded using the running backend's established connection settings. Existing credentials and configuration files were preserved. Rebuilding the existing stack requires resolving the mismatch between its private file and established database role. |
| Historical acceptance script | `scripts/verify_demo.py` calls protected routes without obtaining a JWT. The first buildings request now receives 401. The old instructions also used a retired port variable. Its assignment-era implementation was retained. [Script](../scripts/verify_demo.py#L19) |
| Legacy fixture command | `seed_demo_data` uses a main-reading count threshold and bulk insertion. Partially populated fixtures can conflict with existing keys. Its assignment implementation is preserved, and current startup uses the dedicated bootstrap service. [Fixture command](../backend/monitoring/management/commands/seed_demo_data.py) |
| Measurement history | Unknown durations, earlier unresolved coverage, overlapping readings and unmatched main/solar intervals remain explicit blockers. Activation and solar-installation timelines are absent. Raw ORM/admin writes can bypass supported service policies. [S1 guide](subsystems/s1-energy-monitoring.md#9-technical-limitations) |
| Scaling and retention | Aggregation loads complete building history even for bounded requests and evaluates overlap against earlier rows. Publication is serial and outbox rows have no archival policy. Capacity and latency benchmarks are absent. [Aggregation](../backend/monitoring/services/aggregation.py), [publication](../backend/monitoring/services/kafka_pipeline.py#L135) |
| Alert interpretation | Power averages weight records equally across hourly/minute samples. No-reading meters yield no offline finding. Daily budget uses the latest complete day, which may predate yesterday. [Rules](../backend/analysis/services/alerts.py) |
| AI and feedback | Provider figures and template language lack independent fact verification. The coach uses SDK-default timeouts/retries. Its target serializer lacks an explicit finite check. Feedback stores user opinions without updating a learning model or recommendation status. [S2 guide](subsystems/s2-sustainability-ai-coach.md#9-technical-limitations) |

Functional findings are recorded for a subsequent implementation task. This review
changed source comments and documentation only.

## Documentation discrepancies corrected

The retired Docker guide described `.env.docker`, separate migration/bootstrap
services and host-only Streamlit. Compose currently uses `.env`, runs startup jobs
inside `backend` and includes a frontend service. Older guides said domain APIs
were public and feedback users were client-supplied. Current views require
`IsAuthenticated`, and feedback attributes the current user. Older scenario docs
specified all-history defaults, while current S3 selects latest complete days.

Old diagrams represented standalone functions as classes such as `ExplainService`
and `CostAnalysis`. The new class diagrams contain actual classes only. The nullable
CostReport tariff is represented with multiplicity `0..1`. Requirements distinguish
sequential behavior, known gaps and unverified objectives. Performance and “always
answers” claims were replaced with scoped evidence and actual SDK settings.

The `CostReport` class docstring still describes an absent generation workflow.
The alert module docstring also makes an absolute duplicate-prevention statement.
All docstrings were retained so introspection and the acceptance script's
`argparse` help remain identical. The primary guides describe current behavior.

## Consolidation and evidence preservation

| Earlier document | Current destination |
|---|---|
| `s1-architecture.md` | S1 guide sections 4–6 and the S1 PNG. |
| `s1-management-api.md` | S1 guide sections 6–8 and README usage. |
| `reading-ingestion.md` | S1 guide sections 6 and 8. |
| `simulated-telemetry.md` | S1 guide sections 5–6 and README demo usage. |
| `kafka.md` | S1 guide sections 6 and 9, plus the architecture PNG. |
| `energy-calculations.md` | Shared measurement rules in S1 section 6 and S2/S3 integration sections. |
| `coach-analysis-api.md` | S2 and S3 guide API/validation sections. |
| `s3-architecture.md`, `s3-requirements.md` | S3 guide and S3 PNG with corrected claims. |
| `host-development.md` | README optional host setup and S1 host/schema guidance. |
| `testing.md` | README reproducible test commands and subsystem coverage sections. |
| `implementation-verification.md` | Dated S1 Kafka verification archive under `docs/test-results/`. Historical commands/results retained. |
| `docker-development.md` | Setup content consolidated in README. A short compatibility link remains at the path referenced by the untouched frontend module docstring. |
| `docs/uml/*.mmd` | Two editable sources and an empty placeholder removed after source review. Relevant classes/relationships are preserved in PNGs and text. |
| `frontend/README.md` | Short frontend entry point linking the consolidated setup and review. |

The existing S3 test-results file remains byte-identical. The historical S1 record
retains its content with an archival heading and repaired guide links. The existing
presentation placeholder and coursework video link remain. All migrations, tests,
assignment fixture code and the four homework branch references are preserved.
No university rubric, licensing policy or AI-disclosure policy was present in the
reviewed tree. The recorded team names, responsibilities and simulated-data disclosure
were retained.

The current capstone screencast link and presentation file remain outstanding
submission materials for the team. No link or presentation was fabricated.

## Verification performed

### Source and configuration equivalence

All 91 Python files were compared against commit `88b7f0e` using complete ASTs,
including docstrings, and executable token streams. Ordinary comment/NL tokens were
excluded from the latter comparison. All comparisons passed. The only Python text
changes remove six ordinary comments across two files.

| File | Cleanup |
|---|---|
| `frontend/app.py` | Removed comments announcing meter retrieval, meter creation and a table header. |
| `backend/coach/services/llm_coach.py` | Removed comments announcing prompt-context construction, log creation and recommendation persistence. |

All other original non-documentation files are byte-identical. This includes Docker,
settings, dependencies, API/model/serializer definitions, migrations, tests, frontend
assets/theme and the acceptance script. Private environment files match their initial
SHA-256 hashes. Transaction, concurrency, calculation, validation, security and retry
comments remain. No application database was seeded, migrated, reset or used for tests
by this review.

### Executed test and check results

Both backend runs used the existing application image with read-only current-source
mounts. A temporary runner privately supplied the running backend's established
connection settings after the host-file mismatch. It forced an empty OpenAI key and
a distinct test database. Its temporary environment files were removed after use.
The following are the actual commands executed inside those containers.

| Command / scope | Actual result |
|---|---|
| `python backend/manage.py test config accounts monitoring coach analysis --noinput`, baseline database `test_submission_baseline_20261113` | 255 passed in 33.315 s. |
| Same existing suite after comment cleanup, database `test_submission_final_20261113` | 255 passed in 32.120 s. |
| `python -m unittest discover -s frontend -p 'test_*.py'`, HTTP mocked | 22 passed in 3.268 s. |
| `python backend/manage.py test review_probes --noinput`, temporary external module and `test_submission_probes_20261113` | Five diagnostic probes confirmed R02–R06 in 1.151 s. |
| `python backend/manage.py check --database default` | No issues. |
| `python backend/manage.py makemigrations --check --dry-run` | No changes detected. |
| `docker compose config --quiet` | Passed with the original Compose configuration. |
| Read-only HTTP requests to health and buildings without a token | Health 200, buildings 401. |
| `git diff --check` | Passed. |

Representative final backend output was recorded as follows.

```text
Found 255 test(s).
Creating test database for alias 'default'...
System check identified no issues (0 silenced).
Ran 255 tests in 32.120s
OK
Destroying test database for alias 'default'...
```

The expected mocked OpenAI fallback log appeared. External AI services were not
called. Test databases were separate and removed by Django afterward. Backend tests
include serializer/API contract checks. Complete source equivalence additionally
verifies that API behavior and executable functionality were preserved.

### Requirements, diagrams and presentation checks

Each primary guide has the same nine requested sections and exactly ten FR and ten
NFR entries, totaling 60 requirement rows. Requirements reference implemented symbols
and existing tests, with design objectives identified explicitly. Source references
and local Markdown targets were checked. Four source-derived PNGs were rendered at
high resolution and visually inspected. Labels and routing were corrected during
review. Editable diagram-generation code remained outside the repository.

Browser screenshot capture failed because the computer-use browser access host was
unavailable. Genuine dashboard screenshots were therefore omitted. Existing assets,
theme and application code were preserved. Frontend interaction tests still passed.
The repository contains PNG documentation diagrams and no editable Mermaid files or
Mermaid diagram blocks.

## Submission scope

This branch prepares the requested engineering documentation and PNG diagrams.
The open security and functional findings, current runtime-configuration mismatch,
capstone video and final presentation remain items for follow-up. The application
implementation and runtime services were preserved during this review.
