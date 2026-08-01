# Changelog

## 2026-07-31 — Submission compliance

- Added a top-level Apache-2.0 license so the public source repository satisfies
  the contest's open-source submission requirement.
- Replaced the scaffold-only model alias with `gemini-2.5-flash`, fixed the
  F-029 capability response, and set deterministic generation temperature.
- Completed managed Vertex evaluation: all three cases were valid, with 100%
  final-response-quality and safety pass rates.
- Deployed revision `cutline-00002-d48` to a dedicated Google Cloud Run
  project, added a portable `/health` endpoint, and restored the public invoker
  policy after deployment.
- Revalidated F-024 with five consecutive hosted workflows and a hosted
  Lighthouse pass scoring 100 for accessibility, best practices, SEO, and
  agentic browsing.
- Added the F-031 authenticated Cloud Run action boundary with an allowlisted
  recovery plan, Secret Manager-ready bearer authentication, and durable
  Firestore idempotency for live mode.
- Expanded the quality gate to 39 tests while retaining 100% statement and
  branch coverage over the deterministic application scope.

## 2026-07-31 — Initial feature-audit and implementation pass

- Audited 30 user-visible CUTLINE stories from release overview through
  failure, accessibility, responsive, reliability, agent, and audit behavior.
- Replaced the stock Google ADK scaffold with the CUTLINE release-assurance
  workflow, accessible command center, protocol-native Grafana MCP adapter,
  approval-gated action boundary, immutable receipts, and fresh verification.
- Added the winning product specification and execution plan as self-contained
  StrategiX visual specifications.
- Added 33 automated tests with 100% statement and branch coverage across the
  deterministic Python application scope.
- Completed five consecutive integration regression runs, desktop/mobile
  browser acceptance, a 100 Lighthouse accessibility score after correcting the
  F-026 action-button contrast defect, and a local Cloud Run container build and
  health smoke.
- Regenerated the canonical CSV tracker and its XLSX/HTML views; all 30 stories
  are tracker-backed and verified.
- Kept paid Gemini evaluation, hosted Grafana proof, and Google Cloud deployment
  explicitly approval-gated; this pass created no cloud deployment resources.
