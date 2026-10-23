# FX Lag Intelligence — Product Requirements Document

Status: product proposal for human review. The full MVP is not implemented. A [BCCR SDDE adapter](BCCR_SDDE.md) and [legacy prototype](BCCR_COLLECTOR.md) are implemented and tested offline. The project owner reported one successful authenticated SDDE single-date query; broader live validation remains pending.

## Product vision

Help a USD seller in Costa Rica make better-informed conversion timing decisions through fresh, traceable rate observations and explainable alerts. The planned product will monitor Banco Promerica USD compra, BCCR compra, and MONEX market data.

The hypothesis is that some meaningful MONEX decreases may precede Promerica compra decreases; increases may sometimes make waiting beneficial. Neither a causal relationship nor a known adjustment lag is established. The product must not promise a future rate, optimal timing, or guaranteed savings.

## Target user and primary use case

The initial user is an individual who receives USD and sells **USD 3,000 every 15 days** for CRC through Banco Promerica. They need timely information before a personal conversion deadline, with primary attention to potential decreases and secondary attention to potential increases.

The schedule is every 15 days, not necessarily twice per calendar month. The user sets a starting date, next deadline, and any flexibility; these dates are not inferred. A higher executable compra rate produces more CRC for this seller.

## Primary user stories

| ID | User story |
| --- | --- |
| US-1 | As a USD seller, I want the latest Promerica compra, BCCR compra, and MONEX observations with timestamps so I can judge their relevance. |
| US-2 | As a USD seller, I want a meaningful MONEX decrease alert while Promerica has not yet decreased over the comparison window so I can consider selling before a possible decrease. |
| US-3 | As a USD seller, I want a secondary increase alert so I can consider waiting within my deadline, understanding that Promerica may not follow. |
| US-4 | As a USD seller, I want to see the CRC impact on USD 3,000 so I can decide whether a movement matters. |
| US-5 | As a USD seller, I want WhatsApp and web push preferences and deduplicated notifications so I can receive useful alerts without repeated noise. |
| US-6 | As a Product Owner, I want observation and alert history so I can assess data reliability and test timing hypotheses. |

## MVP requirements

| ID | Requirement |
| --- | --- |
| R-1 | Collect all three sources through verified, permitted methods; preserve each series' identity and meaning. |
| R-2 | Store source, series, rate/statistic type, CRC-per-USD units, decimal value, source URL or identifier, source publication/effective time when available, retrieval time, quality status, and raw-record reference where permitted. Preserve whether source time was unavailable. |
| R-3 | Store timestamps in UTC; display a labeled timezone, defaulting to America/Costa_Rica. Show source time and retrieval time separately. Never present retrieval time as publication time. |
| R-4 | Configure freshness limits per source based on verified publication cadence and market calendar. Detect missing, stale, invalid, future-dated, and out-of-order data; expose degraded status and suppress affected actionable alerts. |
| R-5 | Evaluate the deterministic rules below with configurable thresholds, windows, and recorded rule versions. Settings must be reviewed before live alerting. |
| R-6 | Show estimated Promerica proceeds, observed changes, and separately labeled hypothetical CRC impacts for USD 3,000; allow future amount configuration while preserving this default. |
| R-7 | Support both WhatsApp and web push, with explicit opt-in, channel preferences, revocation, delivery status, bounded retries, and deduplication. A silent failed delivery must not be recorded as successful. |
| R-8 | Show current observations, freshness, recent movements, alert explanations, and history. Allow configuration of the 15-day conversion schedule and deadline. |
| R-9 | Retain observation IDs, comparison baselines, rule versions, decisions, and delivery attempts so each alert can be reconstructed. Keep credentials and phone/push subscription details protected and out of Git. |

### Out of scope

Automated currency trading, bank-account access, guaranteed forecasts, causal claims, a claimed fixed adjustment lag, multi-user commercial operations, and machine-learning prediction are outside the MVP. The original PRD task delivered documentation only. The current repository also includes a BCCR SDDE adapter and a legacy prototype tested offline; deployments, paid services and the full MVP remain unimplemented.

## Data sources and discovery decisions

| Source | Intended use | Required verification before implementation |
| --- | --- | --- |
| Banco Promerica Costa Rica USD compra | Retail bank buying rate relevant to selling USD | Official endpoint or page, allowed collection method, rate applicability by channel/amount, effective timestamp, refresh cadence, fees and executable-quote limitations |
| BCCR compra | Official reference context | Exact reference series and definition, permitted API/feed access, authentication if any, publication calendar, historical coverage and revisions |
| MONEX market data published by BCCR | Detect meaningful market movements and support historical comparison | Exact statistic/series (for example, a published weighted average if available), aggregation interval, units, session calendar, publication delay, access method and historical coverage |

Official institutional starting points: [Banco Promerica Costa Rica](https://www.promerica.fi.cr/) and [BCCR](https://www.bccr.fi.cr/). These are discovery references, not verified ingestion endpoints. No API availability, scraping permission, intraday feed, or live access is assumed.

Choose and document one consistent MONEX statistic before alert implementation; do not mix transaction prices, averages, or daily/intraday observations. BCCR reference compra, MONEX statistics, and Promerica retail compra are different series. Do not substitute one for another or label market/reference data as an executable retail quote.

## Freshness and comparison policy

Each rule must record its comparison window, source-specific freshness limit, maximum allowed cross-source time skew, and baseline selection. Numeric values remain open until source cadence is verified and the Product Owner reviews them; live rules remain disabled until these settings exist.

Compare a current MONEX observation with the latest eligible observation at or before the configured window boundary from the same series and aggregation interval. Require the baseline to fall within a configured boundary tolerance; otherwise suppress the rule. Use comparable Promerica observations at those endpoints to determine whether the bank has already moved. BCCR is context, not evidence that Promerica has changed.

All three current inputs must pass their source-specific freshness and quality checks; baseline eligibility is checked separately. An unknown source timestamp cannot establish freshness unless a documented, reviewed source-specific policy provides reliable effective-period evidence. Refetching an unchanged old publication does not make it fresh. Closed-market periods may be shown as last available data but must not generate new movement alerts from old observations. Revisions are recorded and must not silently rewrite prior alert evidence.

## Alert rules

Define `delta_MONEX = current_MONEX - baseline_MONEX` in CRC per USD. Let `T_down` and `T_up` be positive directional thresholds and `I_min` a minimum absolute scenario impact in CRC. These settings, the comparison window, repeat/rearm policy, and cooldown are configurable and require approval before live use; no threshold is claimed to be validated.

- **Primary decrease warning:** trigger when `delta_MONEX <= -T_down`, `3000 × abs(delta_MONEX) >= I_min`, required data passes eligibility checks, and Promerica compra has not decreased between the matched endpoints. Say a MONEX decrease was observed and a Promerica decrease is possible, with timing unknown. If Promerica already decreased, show the observed change in history rather than describe it as an advance warning.
- **Secondary increase notice:** trigger when `delta_MONEX >= T_up`, the same impact and data gates pass, and Promerica compra has not increased between the matched endpoints. Explain that waiting could help only if the user's eventual executable rate improves; a reversal or unchanged bank rate remains possible. After the user's deadline, do not suggest waiting for that conversion cycle.
- **No actionable movement alert:** suppress below-threshold movements, invalid/missing baselines, stale inputs, excessive time skew, and already-processed observations. Show a separate data-health status explaining suppression.
- **Deduplication:** maintain an event identity using user, rule version, series, direction, and movement episode. Track deliveries per event and channel; repeated polls, sliding-window evaluations of the same episode, and retries must not create new logical alerts. Rearm only after a configured recovery boundary is crossed and cooldown has elapsed; a new episode can then alert. Persist the decision and delivery state across restarts. Use provider idempotency when available; reconcile ambiguous delivery outcomes before retrying to reduce duplicates.

An alert contains the observed values and deltas, publication/retrieval timestamps, comparison window, freshness, current Promerica compra, USD amount, scenario impact, uncertainty, and a link to its evidence. Delivery logs distinguish queued, provider-accepted, delivered where confirmed, failed, and unknown states; provider acceptance is not proof the user read it.

WhatsApp requires user consent and verification of current provider/template rules and costs. Web push requires supported browser capabilities, permission, subscription management, and HTTPS in deployment. Provider selection and any paid setup are deferred.

## CRC impact calculations

Use decimal arithmetic, preserve source precision for comparisons, and round displayed CRC amounts to two decimals. State that estimates exclude fees unless verified fees are explicitly included.

- Estimated gross proceeds: `USD amount × current Promerica compra`.
- Observed gross proceeds change: `USD amount × (current Promerica compra - baseline Promerica compra)`.
- Hypothetical market-movement impact: `USD amount × delta_MONEX`, labeled **scenario only, assuming an equal-sized Promerica movement**. This is neither a forecast nor an expected loss/gain.

Synthetic example: at Promerica compra of CRC 500/USD, selling USD 3,000 yields CRC 1,500,000 before fees. An actual Promerica decrease to 499 reduces proceeds by CRC 3,000. A MONEX decrease of 1 CRC/USD also gives a CRC -3,000 hypothetical scenario, but does not establish any Promerica change. BCCR compra is not used to calculate executable Promerica proceeds.

## Acceptance criteria

These are future implementation checks, not tests that have already passed.

| ID | Acceptance criterion |
| --- | --- |
| AC-1 | Given one valid observation from each source, the view shows the correct series, CRC/USD units, source provenance, separate source/retrieval times, and freshness status. Missing source time is explicit. |
| AC-2 | Given stale or missing required input, an invalid value, excessive time skew, or an ineligible baseline, no actionable alert is generated and the suppression reason is recorded. Refetching old data does not bypass the gate. |
| AC-3 | Given eligible data, configured `T_down = 1`, `T_up = 1`, and `I_min = 3000` as synthetic test settings, a MONEX move of -1 with unchanged Promerica produces one primary warning; +1 produces one secondary notice. A move of magnitude 0.99 produces neither. These are test fixtures, not production defaults. |
| AC-4 | Given a matching Promerica decrease already occurred, the decrease is shown as observed history and no advance decrease warning is issued. The equivalent condition applies to increases; a passed deadline prevents a suggestion to wait. |
| AC-5 | Repeated polls, window shifts within the same episode, retries, and a restart produce at most one logical alert per event and one intended delivery per enabled channel. Recovery plus cooldown permits a new episode. Ambiguous provider outcomes remain visible. |
| AC-6 | For USD 3,000 at Promerica compra 500, gross proceeds are CRC 1,500,000.00; an actual change to 499 gives CRC -3,000.00. A MONEX-only -1 change is labeled hypothetical and does not change displayed observed bank proceeds. |
| AC-7 | With explicit consent, both WhatsApp and web push can receive a test alert in their supported test environments, with evidence links and correct delivery state. Revoked channels receive no further sends; a channel failure does not erase the alert or block the other channel. |
| AC-8 | From any alert, a reviewer can reconstruct the input observations, baseline, thresholds, rule version, freshness decision, CRC calculation, and delivery attempts. No message claims causality or a validated lag without reviewed evidence. |
| AC-9 | A next conversion date advances by 15 calendar days from the configured anchor; schedule and deadline display in the labeled user timezone. Thresholds, dates, and channel preferences persist. |

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Source access changes or collection is not permitted | Verify official access and terms first; isolate adapters and show degraded status on failure. |
| Delayed, revised, daily-only, or non-comparable data | Record provenance and effective periods; use cadence-aware freshness and compatible baselines; do not imply intraday lead time from daily data. |
| Spurious correlation or unstable timing patterns | Evaluate historical aligned series, uncertainty, direction, and market regimes; validate on held-out periods before predictive claims. |
| Alert noise or missed movements | Review meaningful-change settings against historical replay and user feedback; track suppression reasons and deduplication. |
| Notification delays, duplicates, permissions, or costs | Track delivery state, consent, retries and idempotency; verify provider constraints and costs before setup. |
| Actual bank quote differs from published rate | Label estimates and applicability; user verifies the executable quote and fees before deciding. |
| Exposure of personal data or credentials | Minimize stored contact data, restrict access, manage secrets outside Git, and define retention before pilot. |

## Assumptions and open decisions

- The initial user can sometimes choose conversion timing before their deadline; confirm actual flexibility and schedule anchor.
- Access to sufficient historical data and collection permission is unverified. Source cadence may prevent useful advance warnings.
- Confirm MONEX series, baseline window/tolerance, thresholds, freshness limits, maximum time skew, cooldown, and rearm boundary before rules go live.
- Confirm Promerica channel applicability, fees, notification provider, consent flow, hosting budget, retention period, and supported browsers before pilot.
- Historical evaluation must account for market hours, publication delays, revisions, and information actually available at the time; avoid hindsight when replaying alerts.

## Success metrics

Proposed pilot measurement period: 30 consecutive days after source and notification readiness, followed by human review. Targets are initial reliability goals, not measured results or predictive promises.

| Metric | Definition / initial goal |
| --- | --- |
| Observation coverage | Valid observations / expected publications or collection opportunities per verified source schedule; target >=95% per source, with outages disclosed. |
| Freshness safety | Actionable alerts passing every required freshness gate / all actionable alerts; target 100%. |
| Traceability | Alerts with reconstructable evidence and CRC calculations / all alerts; target 100%. |
| Duplicate rate | Unintended repeated deliveries per channel / delivery attempts; target 0, with provider ambiguity reported separately. |
| Notification reliability | Provider-accepted notifications / attempted eligible sends, measured separately for each channel; initial target >=95%. Report confirmed delivery and unknown states separately. |
| Processing latency | Time from eligible observation retrieval to notification attempt; initial target p95 <=5 minutes. Report source publication delay separately. |
| Decision usefulness | User rates alerts useful or not useful for each completed 15-day conversion cycle; collect reasons and establish a baseline before choosing a target. |
| Timing hypothesis | Measure how often qualifying MONEX moves precede same-direction Promerica moves within a predeclared horizon, compared with a baseline; report sample size, lead-time distribution, false alarms, missed moves, and uncertainty on held-out periods. Horizon and evidence standard must be agreed before evaluation. |
| Financial outcome | Compare documented realized net CRC proceeds with a predefined conversion-time benchmark where comparable quotes and fees exist. Report counterfactual limits; do not attribute savings causally to alerts. |

A successful pilot demonstrates reliable, understandable information. It may find no useful predictive timing relationship; that is a valid outcome and must be reported.

## Development and human review

Use the [Codex and GitHub workflow](../README.md#how-we-will-build-with-codex-and-github): small scoped tasks, separate branches, descriptive commits, pull requests with validation evidence, and human review before merging. The Product Owner reviews business meaning and unresolved settings; technical review checks data semantics, calculations, privacy, and delivery behavior. Changes to prediction claims require reviewed historical evidence. Implementation PRs remain subject to human review before merging.
