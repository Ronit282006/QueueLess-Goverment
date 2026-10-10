# PRAVAAH — Killer Features & Implementation Context

**Purpose:** Canonical working context for feature design, workflows, implementation, integration, testing, and hackathon demonstration.

**Status rule:** This document separates known project foundations from planned or unverified functionality. A feature must not be described as implemented merely because it is specified here. The status notes below are based on the available project context and must be checked against the current repository before making external claims.

---

## 1. Product vision

PRAVAAH is a decision-support platform for queues in government service offices. It connects three users:

- **Citizen:** “When should I come, and how can I avoid an unnecessary wait or trip?”
- **Staff member:** “Who should I serve next, and what needs attention in the queue?”
- **Administrator:** “What operational change would improve the whole office, and how do I know it worked?”

The main operating loop is:

**Observe → Predict → Detect → Simulate → Optimize → Recommend → Apply → Measure**

PRAVAAH should not be just a queue display or a dashboard of charts. Its differentiator is a closed decision loop: estimate what is happening, identify an issue, propose an action, preview its likely impact, apply an approved change, and measure the outcome.

### Product principles

1. **Useful before flashy:** decisions must be explainable and operationally valid.
2. **Protect live service:** a token already being served stays with its serving counter until completion, even if future assignments change.
3. **Human approval for consequential actions:** recommendations may be generated automatically, but operational changes require an explicit authorized action.
4. **Honest estimates:** show uncertainty and assumptions; never present a prediction as a guarantee.
5. **Privacy by design:** use synthetic demo data. Do not depend on Aadhaar, biometrics, payments, or real government citizen databases.
6. **Mobile-first citizen experience:** make citizen workflows usable on a phone; staff/admin screens may use wider layouts where appropriate.
7. **Graceful degradation:** if an ML model, routing provider, or external service is unavailable, the queue must continue with a clearly identified fallback.
8. **Measure outcomes:** keep predicted improvement separate from observed improvement.

## 2. Existing foundations versus planned work

The following is based on prior project context, not a fresh inspection of every source file. Verify it against the current code and demo before treating it as a final status report.

### Known existing foundations / previously implemented or tested

- FastAPI backend with versioned `/api/v1` routes.
- JWT authentication and role/object-level access checks are part of the architecture.
- Queue-token, office, service, and counter entities.
- Service-to-counter eligibility and counter status handling.
- FIFO queue ordering: `created_at ASC, id ASC`.
- A token already in service should finish at its original counter; future calls follow the latest assignment and counter status.
- A call-next workflow validates office, counter status, idle/current-token state, assignment, and service eligibility.
- An authoritative live ETA endpoint exists at `GET /api/v1/queues/{token_id}/eta`.
- Queue joining was changed so it no longer invents ETA from mock feature values; stored token ETA is set to `None`, and the live ETA endpoint is the authoritative prediction path.
- A hybrid ETA serving path with ML model and analytical fallback exists in the current test context. Recent tests cover negative/non-finite model output and fallback behavior.
- Scenario/demo loading, API documentation, and a demo rehearsal script exist.
- SQLite has been exercised. PostgreSQL runtime behavior has not been confirmed in the available context.
- Process-local locking means the current setup should use a single Uvicorn worker unless synchronization is moved to a shared coordination mechanism.

These foundations do **not** prove every frontend flow, every scenario, or every feature below is fully integrated or production-ready.

### Planned or not yet verified end-to-end

- Travel-time estimation and travel-aware token recommendations.
- Remote token creation and the complete citizen self-service journey.
- Proof-based service eligibility with secure review/verification.
- End-to-end mobile-first citizen UX and responsive staff/admin flows.
- A complete what-if simulator comparing multiple plans against one baseline.
- Explainable, constraint-aware optimization recommendations.
- Reliable before/after outcome measurement.
- Real-time anomaly detection and alert lifecycle.
- Production-grade external integrations, monitoring, deployment, and multi-worker coordination.

### Status labels for project tracking

- **Implemented and verified:** code exists and a relevant test or repeatable demo proves it.
- **Implemented, integration unverified:** a component exists but end-to-end behavior has not been demonstrated.
- **Planned:** specification only; do not claim it works.
- **Blocked:** needs a decision, dependency, data, or fix before safe implementation.

Update status only after checking code, tests, and the actual demo flow.

## 3. Feature portfolio

| Feature | Main user | Main output | Status in this context |
|---|---|---|---|
| AI-powered queue prediction | Citizen, staff, admin | Wait estimate and uncertainty | Existing backend foundation; end-to-end UX must be verified |
| Dynamic counter reallocation | Admin, supervisor | Feasible proposed/approved assignment change | Counter model/eligibility foundations exist; full optimization behavior must be verified |
| Real-time bottleneck/anomaly detection | Staff, admin | Prioritized issue with evidence | Planned / integration to verify |
| What-if queue simulator | Admin | Side-by-side scenario outcomes | Planned / integration to verify |
| Explainable optimization recommendations | Admin | Action, reason, constraints, expected impact | Planned / integration to verify |
| Before-and-after impact measurement | Admin, judge | Predicted vs observed metrics | Planned / integration to verify |
| Remote queue token | Citizen | Remote token, status, check-in instructions | Planned / integration to verify |
| Proof-based service eligibility | Citizen, staff | Eligibility result and review outcome | Planned / integration to verify |
| Travel estimation | Citizen | Journey duration and source/freshness | Planned / integration to verify |
| Travel-aware token recommendation | Citizen | Recommended departure/arrival window | Planned / integration to verify |
| Mobile-first design | Citizen, staff | Usable phone-first workflows | Requirement; implementation must be verified |

**Priority rule:** do not build every feature to equal depth. Deliver one reliable end-to-end story, then add supporting features that make it more convincing.

---

## 4. Feature 1 — AI-powered queue prediction

### Problem and behavior

Citizens cannot easily tell whether arriving now means a 10-minute wait or a 90-minute wait. PRAVAAH estimates waiting time using live queue state, active eligible counters, service-time estimates, and only those prediction signals supported by reliable data. Return an estimate, its source/method, and uncertainty only when justified.

### Workflow

1. Citizen chooses an office/service or opens their token.
2. Frontend requests current queue/ETA data.
3. Backend validates office, service, token, and access scope.
4. Prediction layer computes an estimate.
5. If the ML model is unavailable or produces invalid output, use the analytical fallback.
6. API returns estimate, prediction source, and supported interval fields.
7. UI shows estimated wait, last-updated time, and a note that the estimate can change.
8. Refresh/realtime updates recalculate the estimate as queue conditions change.

### Data and algorithm

Potential inputs include waiting-token count, active eligible counter count, current service workload, remaining service-time estimate when available, service-specific duration, and recent arrival rate only when event history is reliable. Use no-show/abandonment rates only if measured rather than invented.

Use a hybrid design:

- **Analytical baseline:** transparent estimate from work ahead and service capacity.
- **ML estimate:** existing Random Forest or another validated regressor, only with a stable feature schema and representative training data.
- **Validation:** clamp physically impossible negative values; reject NaN/infinity; fall back when model output is invalid.
- **Uncertainty:** show P10/P50/P90 only if the serving pipeline genuinely provides meaningful interval estimates. Do not invent a confidence percentage.

### Implementation notes

Keep prediction logic in a service/module rather than duplicating it in route handlers. Keep the ETA endpoint authoritative; do not write fake predictions at token creation. Avoid loading the model per request. Record prediction time and compare estimates with actual service-start wait when data is available.

### Value

Reduces uncertainty for citizens, gives staff a shared operational estimate, and powers travel-aware recommendations and impact measurement.

### Risks and acceptance criteria

Risks include sparse/synthetic data, stale state, false precision, and incorrect active-counter counts. Label synthetic estimates, show freshness, use active eligible counters as the source of truth where defined, and provide fallback.

**Done when:** valid requests return finite nonnegative estimates; invalid model outputs trigger fallback; queue/counter changes can affect estimates; access errors are rejected; UI never shows NaN/infinity or fabricated values.

---

## 5. Feature 2 — Dynamic counter reallocation

### Problem and behavior

A service queue may grow while another eligible counter is underused. PRAVAAH identifies imbalance, checks eligibility and operational constraints, proposes a feasible reassignment, previews expected impact, and allows an authorized supervisor to apply it.

### Workflow

1. Monitor waiting counts, wait estimates, counter states, and service eligibility.
2. Detect queue pressure and spare eligible capacity.
3. Generate candidate assignments that satisfy hard constraints.
4. Estimate each candidate's impact against the same assumptions.
5. Show current versus proposed assignment and expected service impact.
6. Authorized admin approves or rejects the change.
7. Backend revalidates the latest state to prevent stale recommendations.
8. Persist the assignment and audit actor, time, reason, and before/after values.
9. Recalculate future routing and measure observed outcomes.

### Hard constraints

- A counter only serves eligible services.
- An unavailable counter cannot receive future calls.
- A token already being served stays at its original counter until completion.
- Reallocation affects future calls, not the in-progress service.
- A simulator may model a conceptual 3-minute switching delay only when clearly labeled as an assumption.
- Live and simulated assignment logic should share the same eligibility rules.

### Algorithm

Start with a constraint-based heuristic:

1. Calculate queue pressure per service.
2. Identify spare eligible capacity.
3. Generate only feasible assignments.
4. Score candidates by expected reduction in waiting/workload imbalance minus switching cost.
5. Reject any candidate violating a hard constraint.
6. Return the best candidate with reasons.
7. Require explicit approval before applying.

Consider integer programming only if scale/constraints justify a solver dependency.

### Risks and acceptance criteria

Revalidate at application time, use transactions, prevent recommendation churn with a minimum improvement threshold, label simulation assumptions, and show staff why the action is proposed.

**Done when:** no recommendation violates eligibility/status; in-progress tokens are not moved; applied changes are audited; stale plans are rejected/recomputed; before/after assignments are visible.

---

## 6. Feature 3 — Real-time bottleneck and anomaly detection

### Problem and behavior

A queue can deteriorate before a supervisor notices. PRAVAAH flags operational conditions that exceed configured thresholds or depart from a credible baseline, ranks them by severity, and explains the evidence.

### Candidate detections

- Queue length or predicted wait exceeds a threshold.
- Queue growth rate is unusually high.
- Waiting tokens exist but no active eligible counter is available.
- A counter is unavailable for too long.
- Actual service duration greatly exceeds its baseline.
- Predicted and observed outcomes repeatedly diverge.
- Workload is highly imbalanced across eligible counters.

Only enable detections supported by available data.

### Workflow

1. Receive queue/counter events or refresh a short-interval snapshot.
2. Compute metrics and compare them with thresholds or rolling baselines.
3. Create/update an issue containing service, time, severity, evidence, and suggested action.
4. Deduplicate repeated alerts for a continuing condition.
5. Show the alert in staff/admin views.
6. Link to a relevant action: inspect counter, simulate reallocation, or review delay.
7. Resolve the alert when the condition clears while retaining history.

### Algorithm and data

Begin with transparent rule-based detection. Use rolling median/percentile baselines only with enough observations. Avoid calling every threshold breach “AI anomaly detection” if it is a rule.

A conceptual alert record includes ID, office/service, type, severity, status, creation/last-seen/resolution times, observed value, threshold/baseline, explanation, suggested action, and related counter/scenario references.

### Risks and acceptance criteria

Control alert fatigue with thresholds, deduplication, cooldowns, and severity levels. Show evidence to reduce false-positive confusion. Polling is acceptable for a demo if update frequency is stated honestly.

**Done when:** a known synthetic incident triggers an evidence-backed alert; repeat polling does not create unlimited duplicates; alert state changes when the issue clears.

---

## 7. Feature 4 — What-if queue simulator

### Problem and behavior

Administrators need to assess changes before applying them to a live queue. The simulator models a proposed action against a fixed baseline and compares outcomes side by side.

### Candidate scenarios

- Reassign an eligible counter to an overloaded service.
- Temporarily mark a counter unavailable.
- Change an assumed service duration.
- Add/remove counter capacity for a defined period.
- Compare current allocation with a candidate allocation.

Only support scenario types that can be modeled correctly with available data.

### Workflow

1. Capture baseline queue, counter status, assignments, and service-time assumptions.
2. Admin selects a scenario and supported parameters.
3. Validate hard constraints.
4. Simulate baseline and candidate with identical arrival/queue assumptions.
5. Calculate outcome metrics.
6. Display deltas and assumptions.
7. Let the admin discard the scenario or submit the selected plan for approval/application.
8. Store inputs/results for reproducibility.

### Metrics and algorithm

Potential metrics: estimated wait by service, total waiting workload, longest queue/highest service wait, counter workload balance, affected token count, constraint violations, and expected improvement/trade-offs.

Start with a deterministic simulation using the known queue snapshot and service durations. If arrivals are modeled, use the same assumptions for both plans; if randomness is necessary, use the same seeded arrivals. Do not compare two plans using unrelated random inputs.

### Risks and acceptance criteria

Label estimates and assumptions, share eligibility logic with live operations, use documented synthetic scenarios, and bound computation.

**Done when:** both plans use the same baseline; invalid plans cannot be applied; assumptions and deltas are shown; repeated deterministic runs match; simulation does not mutate live state.

---

## 8. Feature 5 — Explainable optimization and action recommendations

### Problem and behavior

A chart can show a queue is bad without telling the administrator what to do. PRAVAAH should recommend a specific action, explain why, show expected impact and trade-offs, and identify constraints checked.

### Recommendation structure

- **Action:** e.g. temporarily reassign an eligible counter.
- **Reason:** queue pressure and spare capacity evidence.
- **Expected impact:** a value calculated by the actual simulator, never a hard-coded claim.
- **Trade-off:** possible effect on other supported services.
- **Constraints checked:** eligibility, availability, in-progress token protection.
- **Assumptions/source:** identify simulation or model basis.
- **Next step:** preview, approve, or dismiss.

### Workflow and implementation

1. Read active alerts and queue/counter metrics.
2. Generate feasible actions.
3. Score by expected benefit, people affected, operational cost, and constraints.
4. Simulate leading candidates.
5. Rank with a transparent scoring rule.
6. Explain the chosen action from computed evidence.
7. Require admin approval.
8. Record applied, dismissed, or failed-validation status.

Use structured rules/optimization for action generation and scoring. Use deterministic templates for critical explanations. An LLM may rephrase an already-computed explanation only if it cannot invent metrics, alter the action, or bypass constraints. Return structured API fields rather than unstructured prose alone.

**Done when:** every recommendation includes action, evidence, assumptions, impact, and approval requirement; it follows simulator constraints; explanation matches computed output; no LLM suggestion directly applies an action.

---

## 9. Feature 6 — Before-and-after impact measurement

### Problem and behavior

A change may be applied without proving it helped. PRAVAAH records a baseline, captures post-action observations, and compares results while acknowledging that simple before/after comparison does not prove causality.

### Workflow

1. Record baseline snapshot and time window before applying a plan.
2. Record action, actor, assignment/status changes, and timestamp.
3. Capture comparable metrics after a defined observation window.
4. Compare baseline, predicted result, and observed result.
5. Show metric deltas, data coverage, and caveats.
6. Preserve the report for audit/demo use.

### Keep three values distinct

- **Baseline:** observed state before intervention.
- **Predicted result:** model/simulator estimate.
- **Observed result:** measured state after intervention.

Never describe a predicted improvement as a measured improvement.

### Metrics and data

Use average/median waiting time only when actual timestamps exist; queue length at fixed intervals; throughput per time window; counter workload balance where supported; no-show/abandonment only if reliably tracked; and prediction error against actual service-start wait.

A report can store intervention ID, baseline snapshot, predicted metrics, observation window, post-action snapshot, metric deltas, and data-quality flags. Avoid unnecessary citizen data.

**Done when:** each applied recommendation links to baseline and post-action measurements; predicted and observed values are distinct; missing data is explicit; reports do not overstate causal certainty.

---

## 10. Citizen feature — Remote queue token

### Problem and behavior

Citizens may have to arrive physically just to obtain a token. Remote token creation should let a citizen select an office/service, review requirements, request a token when allowed, and monitor status on a phone.

### Workflow

1. Choose office and service.
2. View eligibility, required documents, hours, and remote-token restrictions.
3. Complete required answers and only the minimum necessary demo information.
4. Backend validates service, office, token rules, and duplicate/request limits.
5. Create a token with a stable ID and status.
6. Show token number, service, ETA, status, and when to travel/check in.
7. Refresh/receive updates as the queue changes.
8. Check in on arrival if policy requires it.
9. Serve the token under existing queue/counter rules.

### Token lifecycle and key policy decision

Inspect the current token enum and transitions before adding statuses. A possible lifecycle is `WAITING → CALLED → SERVING → COMPLETED`, with `CANCELLED`, `EXPIRED`, or `NO_SHOW` only if actually required and implemented across all transitions, tests, and UI.

A remote token is not automatically an appointment. Decide whether it reserves queue position, joins a virtual waiting list, or requires physical check-in before becoming active. State the rule clearly. The ETA and departure recommendation cannot be correct until this policy is defined.

### Risks and acceptance criteria

Prevent duplicate token creation with idempotency and explicit retry rules; clarify late arrival/expiry; preserve token ID through network retries; use synthetic identities and no Aadhaar/sensitive document requirement.

**Done when:** a retried request cannot create unintended duplicate tokens; status access is scoped to the owner; ETA comes from the authoritative ETA endpoint; check-in/cancel/expiry semantics are explicit and tested.

---

## 11. Citizen feature — Proof-based service eligibility

### Problem and behavior

A citizen may travel to an office and discover they do not meet requirements or lack a document. PRAVAAH should check service-specific answers and evidence before token creation or visit recommendations.

### Workflow

1. Citizen chooses a service.
2. Backend returns configured eligibility checklist and accepted proof types.
3. Citizen answers questions and, if supported, uploads synthetic evidence or selects a mock proof.
4. Backend validates size/type and associates evidence with the request.
5. A deterministic eligibility engine evaluates configured rules.
6. Outcome: **Likely eligible**, **Needs review**, or **Not eligible based on provided information**.
7. Explain which requirement passed, failed, or needs clarification.
8. Authorized staff records a review decision and reason when required.
9. Continue only according to that service's configured policy.

### Important safety distinction

“Proof-based” must not mean a generic AI model claims to authenticate government documents. For the hackathon, use mock/synthetic proof, deterministic checks, and an explicit human-review state. OCR can extract text but does not prove document authenticity. Real verification requires an authorized trusted source and a stronger privacy/security review.

### Data and controls

Potential records include service requirement version, eligibility response, evidence metadata/storage reference/hash/time, review status, reviewer and decision audit. Avoid logging document contents or personal identifiers. If uploads exist, use private storage rather than public static directories, validate size/type, and never execute uploaded files.

**Done when:** service rules are versioned and testable; self-declaration, automated rule outcome, and human verification are distinct; failures explain missing requirements; unauthorized users cannot access another citizen's evidence; the demo uses synthetic data.

---

## 12. Citizen feature — Travel estimation

### Problem and behavior

A queue estimate alone is insufficient. A citizen may need 40 minutes to reach the office. PRAVAAH estimates travel duration from a user-supplied origin to the office using a routing provider when available, or a clearly labeled manual/demo estimate.

### Workflow

1. Citizen selects an office.
2. Citizen enters an origin or grants location access voluntarily.
3. Only minimum origin/destination data is sent to the routing adapter.
4. Provider returns travel duration and optionally distance/route status.
5. Backend/UI records source and calculation time.
6. UI shows duration and freshness/uncertainty.
7. If routing fails, offer manual input or an explicitly labeled demo fallback; do not silently invent a route.

### Dependencies and controls

Choose a terms-compliant routing API with a suitable free tier only after checking key restrictions, rate limits, privacy terms, and network access. Hide provider calls behind a backend adapter. Never expose a private key in frontend source or repository. If no provider is practical, support a manually entered duration labelled user-provided.

Support manual origin entry without GPS permission, avoid unnecessary origin persistence, cache suitable estimates to control rate limits, and round values to practical minutes.

**Done when:** location permission is optional; provider failure does not break queue functionality; origin/destination are not unnecessarily persisted; UI identifies provider/manual/demo source.

---

## 13. Citizen feature — Travel-aware token recommendation

### Problem and behavior

The shortest queue is not always the best time to leave. A citizen needs enough time to reach the office before being called without arriving unnecessarily early. Combine queue ETA, travel duration, uncertainty, check-in rules, and office hours to recommend a practical departure or arrival window.

### Keep these times distinct

- `estimated_wait_minutes`: expected wait from a precisely defined reference point.
- `travel_minutes`: estimated journey duration.
- `recommended_departure_time`: when the citizen should leave.
- `recommended_arrival_window`: suggested time to reach the office.
- `check_in_deadline`/token expiry: only if a real rule is configured.

Do not simply add travel time to queue wait and call the result a departure time. First define whether ETA means time until service begins from now or time after arrival/joining. The recommendation must use the matching reference point.

### Workflow

1. Citizen selects/creates a token.
2. Fetch current queue ETA and prediction source.
3. Fetch travel estimate.
4. Check office hours, token policy, check-in buffer, and ETA freshness.
5. Calculate a safe departure/arrival window using a configurable buffer.
6. Show one recommended option and optionally a small number of alternatives.
7. Explain the basis in plain language.
8. Refresh when queue conditions change materially or inputs become stale.
9. If uncertainty is too high, say “check again later” rather than manufacturing precision.

### Algorithm

Start with deterministic rules. Use a conservative percentile/upper interval only when a valid interval exists. Respect office hours and configured check-in rules. If no meaningful uncertainty interval exists, use a configurable heuristic buffer and label it. Recalculate on relevant input changes.

This feature is blocked until the remote-token queue-position policy and ETA reference point are clearly defined.

**Done when:** calculation uses the correct ETA reference point, incorporates travel and buffer, respects hours/token policy, explains inputs/freshness, and never guarantees a service time.

---

## 14. Mobile-first design

### Goal

The citizen experience must work on a small phone screen with minimal typing. Staff/admin tools should be responsive but can prioritize operational density on larger screens.

### Citizen information hierarchy

1. Current token/status.
2. Estimated wait and last-updated time.
3. Travel estimate and recommended departure/arrival window.
4. Eligibility/proof checklist.
5. Required next action.
6. Details only when requested.

### Design rules

- Test from 320–360 CSS pixels through larger phones, tablets, and desktop.
- Prefer one primary action per screen.
- Make status and wait time readable; avoid dense tables in citizen views.
- Use tap targets around 44 CSS pixels or larger.
- Provide explicit loading, empty, error, offline, and stale-data states.
- Never use color alone to communicate status/severity.
- Support keyboard navigation and visible focus.
- Do not force GPS permission.
- Keep forms short and preserve progress across recoverable network errors.
- Collapse staff/admin tables into cards/responsive rows on narrow screens.
- Respect reduced-motion and contrast preferences.

### Suggested screens

1. Select office/service.
2. Eligibility checklist.
3. Token confirmation/status.
4. “When should I leave?” recommendation.
5. Token detail with status, ETA, instructions, and refresh.
6. Help/error recovery.

**Done when:** no horizontal overflow at 320px; token status and primary action are easy to find; loading/error/empty states exist; touch and keyboard interactions work; API failures never show fabricated data.

---

## 15. Shared architecture and integration

Use the existing stack unless repository inspection shows a concrete reason to change it:

- **Frontend:** React + TypeScript + Vite.
- **Backend:** FastAPI / Python.
- **Database:** current SQLAlchemy models/configuration; SQLite has been exercised, PostgreSQL runtime is unconfirmed in the available context.
- **ML:** existing ETA serving/model pipeline with analytical fallback.
- **Realtime:** existing WebSocket/refresh mechanism where available.
- **Tests:** pytest and existing demo rehearsal script.

### Logical architecture

```text
Mobile Citizen UI ─────┐
Staff Operations UI ───┼──> FastAPI API + Authentication/RBAC
Admin Decision UI ─────┘                |
                                        +--> Queue/Token Service
                                        +--> Counter/Eligibility Rules
                                        +--> ETA Prediction Service
                                        +--> Alert/Anomaly Service
                                        +--> Simulation/Optimization Service
                                        +--> Travel Provider Adapter
                                        +--> Audit/Impact Measurement
                                                   |
                                                Database
```

External routing must be optional and isolated behind an adapter. Core queue operation should not depend on a third-party map service.

### Integration rules

- Keep business rules on the backend; frontend validation is usability support, not security.
- Revalidate permissions, eligibility, counter state, and plan feasibility on every write.
- Use transactions for assignment/token state changes.
- Use idempotency for retryable token creation and other operations where duplicates are harmful.
- Do not expose citizen PII through WebSockets; send only fields needed by the live view.
- Keep `docs/api_contract.md` aligned with route/response changes.
- Add schema/migrations only when needed; update tests and scenario seeding together.
- Do not store a fake ETA in the token record if the authoritative design calculates it dynamically.
- Audit sensitive admin actions and eligibility reviews.
- Use one Uvicorn worker while synchronization is process-local. Before scaling, move coordination to a shared mechanism or database-safe design.

### Possible API boundaries — proposals only

These are conceptual boundaries, not assertions that routes already exist. Inspect current OpenAPI/API contract before adding routes and reuse existing equivalents.

- Queue/ETA: existing `GET /api/v1/queues/{token_id}/eta`.
- Remote token creation and token status/check-in/cancel: proposed after inspecting current lifecycle.
- Eligibility requirements/evaluation: proposed service-specific endpoints.
- Travel estimate: proposed endpoint behind routing adapter.
- Travel-aware recommendation: proposed endpoint combining ETA, travel, hours, and token policy.
- Alerts: proposed list/acknowledge/resolve operations.
- Simulation: proposed create/run/read scenario operations.
- Recommendations: proposed list/preview/apply/dismiss operations.
- Impact measurement: proposed baseline/result/report operations.

Do not add duplicate routes if equivalent functionality already exists.

---

## 16. Data model considerations

These are conceptual entities. Reuse current models where possible; do not create duplicate tables unnecessarily.

| Entity | Purpose | Key considerations |
|---|---|---|
| Office | Service location and hours | identity, hours, timezone if needed |
| Service | Service definition | duration, requirements, remote-token policy |
| Counter | Physical capacity | status, office, eligible services |
| QueueToken | Place in queue | status, service, creation time, current assignment |
| EligibilityCheck | Requirement evaluation | rule version, result, reason, review state |
| EvidenceReference | Mock-proof reference | private storage, retention, access controls |
| TravelEstimate | Journey duration/source | timestamp, provider/manual/fallback source |
| Alert | Current/historical issue | severity, evidence, deduplication state |
| SimulationRun | Reproducible what-if result | baseline, assumptions, candidate plan |
| Recommendation | Proposed action | evidence, impact, approval state |
| AuditEvent | Consequential action record | actor, action, before/after, timestamp |
| ImpactReport | Outcome measurement | baseline, prediction, observed metrics, caveats |

Schema changes must be driven by required behavior. Do not persist exact citizen origins if a recommendation can be calculated without saving them.

---

## 17. Demo strategy: one coherent story

Do not demo every feature as an unrelated screen. Show one synthetic scenario with a visible problem, a justified decision, and a measurable outcome.

### Suggested 3–5 minute narrative

1. **Show a queue problem:** one service is overloaded while another eligible counter has spare capacity.
2. **Show the citizen perspective:** select a service, review requirements, and view the remote token/ETA flow if implemented.
3. **Show travel-aware planning:** display travel duration, queue estimate, and a recommended departure/arrival window with assumptions.
4. **Show the detected issue:** admin sees a bottleneck alert with concrete evidence.
5. **Simulate before acting:** compare current allocation with a feasible counter-reallocation plan.
6. **Explain the recommendation:** show why the action was selected, which constraints were checked, and what the simulator predicts.
7. **Apply the action:** approve it and show live future assignment changes. Keep in-progress service uninterrupted.
8. **Measure the result:** compare baseline, predicted, and observed metrics; label synthetic data and observation window honestly.
9. **Close on value:** citizens get better visit planning; staff get a next action; administrators can evaluate operational changes.

### What makes it convincing

- Use a fixed reproducible scenario rather than random data that changes each run.
- Show one fallback case deliberately, such as model fallback or routing-provider failure.
- Show explanations and constraints, not only a green success banner.
- Use values produced by the actual simulation/measurement path.
- Do not claim real-world government impact from synthetic data.
- Have a fallback ready if external routing or realtime transport fails.

### Recommended centerpiece

The strongest coherent “killer moment” is **simulate → explain → approve a counter reallocation → measure the impact**, connected to the citizen’s changing ETA and travel recommendation. This is more compelling than many unrelated AI widgets, provided each stage works reliably.

---

## 18. Phased implementation plan

### Phase 0 — Repository truth and scope lock

- Inspect current routes, schemas, frontend pages, services, tests, scenario loader, and API contract.
- Mark each feature implemented / partial / planned / blocked.
- Identify the shortest working end-to-end path.
- Do not rewrite architecture before establishing what already exists.

**Exit:** accurate feature/status inventory and agreed API/data contract.

### Phase 1 — Core queue correctness and safety

- Verify token lifecycle, FIFO behavior, counter eligibility/status, and in-progress token protection.
- Verify auth/RBAC and cross-office/object-level isolation.
- Verify authoritative ETA and fallback.
- Ensure test fixtures use isolated databases and cannot delete persistent demo data.

**Exit:** core queue tests and demo rehearsal pass; no known data-safety blocker.

### Phase 2 — One reliable operational decision loop

- Implement/verify bottleneck detection.
- Implement deterministic what-if simulation.
- Generate feasible counter-reallocation candidates.
- Explain recommendations with computed evidence.
- Add explicit approve/apply and audit trail.

**Exit:** a reproducible scenario moves from detection to simulation to approved action without violating constraints.

### Phase 3 — Impact measurement

- Capture baseline before application.
- Store prediction separately from observed result.
- Show metric deltas and data-quality caveats.

**Exit:** one applied action produces a traceable before/predicted/after report.

### Phase 4 — Citizen journey

- Complete mobile-first office/service selection.
- Implement requirements and proof-based eligibility with synthetic evidence.
- Implement remote-token policy and status lifecycle.
- Make ETA display robust and explain check-in rules.

**Exit:** citizen can complete supported flow on a phone, and sensitive operations are scoped and tested.

### Phase 5 — Travel and visit recommendation

- Select/validate routing provider or manual fallback.
- Implement travel estimate with source/freshness.
- Define remote-token queue-position semantics and ETA reference point.
- Implement travel-aware recommendation with office hours and buffer rules.

**Exit:** deterministic, explainable recommendations pass tests for stale ETA, missing travel duration, closed office, and no location permission.

### Phase 6 — Integration hardening and demo

- Run focused tests for changed modules.
- Run full `pytest -q`.
- Run `python scripts/rehearse_demo.py`.
- Run `git diff --check`.
- Test responsive breakpoints, API errors, model fallback, and routing-provider failure.
- Inspect status/diff; commit only after agreed checks pass.
- Rehearse from a clean startup.

**Exit:** checks have actual recorded results, limitations are documented, and the demo is repeatable without manual database cleanup.

### Priority under time pressure

1. Correct queue and counter behavior.
2. One complete simulator → recommendation → apply → measure loop.
3. Citizen ETA/token display.
4. Travel-aware recommendation after its input semantics are defined.
5. Eligibility evidence with synthetic data.
6. Visual polish and secondary charts.

Do not implement all features superficially at the expense of the main decision loop.

---

## 19. Testing plan

### Unit tests

- ETA finite/nonnegative output and fallback.
- Counter eligibility and assignment candidate validation.
- Alert threshold and deduplication.
- Simulation determinism and constraints.
- Recommendation explanation matching computed values.
- Travel recommendation buffers and missing/stale inputs.
- Eligibility rules, missing proof, and review-required outcomes.
- Token idempotency and lifecycle transitions.

### API/integration tests

- Valid and invalid requests.
- Authenticated and unauthenticated access.
- Citizen cannot read/alter another citizen’s token/evidence.
- Staff/admin permissions enforced.
- Cross-office access denied.
- Stale/invalid counter plans rejected.
- In-progress tokens remain at their serving counter.
- WebSocket payloads contain no unnecessary PII.
- Routing failure does not break queue flow.
- Test fixtures use isolated databases.

### UI checks

- Widths around 320, 360, 390 pixels, tablet, and desktop.
- Loading, empty, stale, error, offline/reconnect states.
- No fake ETA values or misleading success states.
- Keyboard/touch access to primary actions.
- Manual travel entry without GPS permission.
- Recommendations show reason, assumptions, and expected impact.

### Demo acceptance checklist

- Scenario loads deterministically.
- Queue and counter data are coherent.
- Known bottleneck triggers an evidence-backed alert.
- Simulator returns feasible alternatives.
- Recommendation is explainable.
- Approval changes future assignment correctly.
- In-progress service remains uninterrupted.
- Report distinguishes baseline, prediction, and observed result.
- Citizen ETA/travel recommendation updates or marks stale data.
- Rehearsal passes without manual database repair.

---

## 20. Risks, dependencies, and guardrails

| Risk/dependency | Impact | Mitigation |
|---|---|---|
| Sparse training data | Poor ETA accuracy | Hybrid analytical fallback; label synthetic estimates |
| Routing provider limits/API key | Travel feature fails live | Adapter, key restrictions, caching, manual fallback |
| Ambiguous remote-token policy | Incorrect visit advice | Decide queue-position and check-in rules first |
| Proof-verification overclaim | False assurance/privacy risk | Synthetic proof, deterministic rules, human review; no authenticity claims |
| Counter concurrency | Invalid assignment/double service | Transactional revalidation; single worker until coordination is safe |
| Prediction/simulation mismatch | Misleading recommendation | Shared rules and same baseline assumptions |
| Before/after confounding | Overstated benefit | Separate prediction/observation and disclose limits |
| Scope expansion | Incomplete demo | Prioritize one complete decision loop |
| Frontend/API drift | Broken integration | Keep API contract current; run end-to-end tests |
| Sensitive data in logs/events | Privacy breach | Minimize data; no PII in WebSockets/logs; access controls |
| Overengineering | Time lost without judge value | Simple explainable algorithms and deterministic scenarios |

### Out of scope unless explicitly approved

- Real Aadhaar or government identity verification.
- Biometrics or face recognition.
- Payments.
- Direct production government database integration.
- Guaranteed service-time claims or proven real-world impact from synthetic data.
- Large-scale distributed deployment before shared locking/coordination exists.
- An LLM controlling counter assignments without deterministic constraints and human approval.

---

## 21. Final definition of done

PRAVAAH is ready for a hackathon demonstration when:

- Core queue/token/counter rules behave correctly.
- ETA predictions are valid, source-aware, and have a safe fallback.
- At least one synthetic bottleneck is detected with evidence.
- A candidate counter plan can be simulated without changing live state.
- A recommendation explains its action, assumptions, and computed impact.
- An authorized user can approve a feasible action.
- The applied change is audited and future routing respects it.
- Before/predicted/after metrics are distinct and honestly labeled.
- Citizen flows work on a phone for the features actually enabled in the demo.
- Travel-aware recommendations respect the ETA reference point, office hours, and token policy.
- Eligibility distinguishes self-declaration, rule evaluation, and human review.
- Focused tests, full suite, and demo rehearsal have been executed and actual results recorded.
- Known limitations are documented rather than disguised as completed functionality.

**Strategic goal:** build one reliable, explainable, measurable operational loop, then connect the citizen journey to it. The quality of integration—not the number of feature names—is what will make PRAVAAH stand out.
