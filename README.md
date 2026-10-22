# FX Lag Intelligence

FX Lag Intelligence is a planned decision-support product for people selling US dollars for Costa Rican colones. It will monitor Banco Promerica USD **compra**, BCCR **compra**, and MONEX market data, showing timely observations and explainable alerts.

## Problem statement

The primary user sells **USD 3,000 every 15 days** and wants to identify meaningful MONEX decreases that may precede decreases in Promerica's compra rate. Secondary alerts identify increases that may make waiting beneficial, subject to the user's conversion deadline. Manually checking multiple sources makes it difficult to assess freshness, distinguish meaningful movements from noise, and understand the CRC amount at stake.

Compra is the bank's USD buying rate: the relevant direction when the user sells USD. BCCR reference rates and MONEX market statistics provide context; neither is a guaranteed executable Promerica quote.

Market movements are not assumed to cause bank rate changes. No adjustment lag, predictive accuracy, or financial benefit has been established. Historical evidence must validate any proposed timing relationship.

## Planned key features

- Timestamped observations of Promerica compra, BCCR compra, and a precisely defined MONEX series, with source provenance and freshness status.
- Primary decrease alerts and secondary increase alerts using configurable meaningful-change thresholds and comparison windows.
- Freshness checks that suppress actionable alerts when required inputs are stale, missing, or invalid.
- Alert deduplication, bounded retries, and delivery tracking for both **WhatsApp and web push**.
- CRC proceeds and impact calculations for USD 3,000, separating observed bank-rate changes from hypothetical scenarios.
- Observation and alert history to investigate possible timing relationships without claiming causality.

Detailed requirements and acceptance criteria are in the [Product Requirements Document](docs/PRD.md).

## Proposed product architecture

| Area | Candidate | Purpose |
| --- | --- | --- |
| Web interface | TypeScript, React / Next.js | Rate view, history, preferences, web push consent |
| Collection and analysis | Python with scheduled jobs | Source adapters, validation, deterministic alert rules |
| Storage | PostgreSQL | Timestamped observations, rules, alert and delivery records |
| Notifications | WhatsApp Business Platform and Web Push APIs | Opt-in delivery through both channels |
| Collaboration and checks | GitHub, Codex, GitHub Actions | Reviewed changes and automated validation |

This full product architecture remains proposed; only the standalone legacy Python prototype below is implemented. These candidates are not installed dependencies or service commitments. Source access, hosting, provider pricing, and security design require investigation before implementation. No paid services are configured in this phase. AI assists development; the MVP does not require an AI prediction model.

## Development roadmap

1. **Product foundation (current):** review this overview and PRD; resolve product questions.
2. **Source discovery:** verify official access methods, permissions, series definitions, timestamps, cadence, and historical coverage for all three sources.
3. **Observation foundation:** implement source adapters, storage, validation, freshness policies, and history using fixtures first.
4. **Rules and CRC calculations:** implement deterministic thresholds, comparison windows, deduplication, and scenario calculations with acceptance tests.
5. **Notification MVP:** implement and test WhatsApp and web push with consent and delivery records; review costs before selecting services.
6. **Pilot and evaluation:** measure reliability, usefulness, and historical timing relationships; revise rules before making any predictive claims.

These are ordered milestones, not delivery-date commitments.

## Current project status

**Legacy BCCR prototype implemented and tested offline; no verified live integration.** The Python CLI constructs requests for USD compra reference indicator 317 through the legacy XML service. BCCR announced that service's retirement for 2026-06-30, so this is not the intended production integration. [Setup, usage and official-source verification](docs/BCCR_COLLECTOR.md) distinguish this prototype from the documented replacement SDDE API, which is not implemented or authenticated here. No dashboard, database, alerts, predictions, Promerica or MONEX integrations exist.

## How we will build with Codex and GitHub

1. The Product Owner defines a small outcome and acceptance criteria in an issue or task.
2. Codex inspects the repository and proposes or implements a scoped change on a **branch**: a separate line of work that leaves `main` unchanged.
3. Codex checks the diff (the exact changed lines) and runs relevant checks. A **commit** saves a named snapshot of related changes in Git history.
4. A **pull request (PR)** proposes bringing the branch into `main`. It presents the changes, reasons, and validation results for discussion.
5. A human reviews correctness, product intent, evidence, costs, and risks; requests revisions where necessary; and decides whether to merge. Codex leaves PRs unmerged for human review.

Keep secrets out of Git. Record assumptions explicitly, use synthetic data for early tests, and distinguish proposed features from working functionality. The only current implementation is the legacy collector prototype; full application development and paid-service setup remain future work.

## Learning objectives

- Turn a business problem into user stories, testable requirements, and a small MVP.
- Learn the roles of branches, commits, pull requests, checks, and human review.
- Read diffs and verify AI-generated work against product intent.
- Understand data quality, freshness, alert noise, and financial calculations.
- Evaluate historical evidence without confusing sequence or correlation with causation.

## License

[MIT](LICENSE).
