# Changelog

## 2026-07-31 — Live Grafana MCP audit closure

- Created least-privilege Grafana Viewer and telemetry-writer credentials,
  stored their replacements in GCP Secret Manager, and deployed the official
  pinned `grafana/mcp-grafana` image as a private Cloud Run service.
- Added bounded Prometheus remote-write and Loki publishing for the controlled
  release scenario, using a write-only token that is isolated from the MCP
  service account.
- Corrected live integration defects found during hosted testing: PromQL
  same-label de-duplication, ambiguous datasource selection, official
  list-shaped metric payloads, and quoted nanosecond Loki timestamps.
- Completed hosted run `28d84011-b821-4574-a2bc-15ff0b38d24c` on revision
  `cutline-00009-kh2`: real pre/post Grafana evidence, Gemini 2.5 Flash
  synthesis, approval, authenticated Cloud Run execution, six passing
  verification gates, and a final `VERIFIED` state.
- Expanded the deterministic quality gate to 51 tests, 731 statements, and 128
  branches at 100% coverage.
- Closed F-032 and F-033 as Verified and regenerated the canonical CSV
  tracker plus its XLSX and self-contained HTML views; all 33 tracked stories
  are now Verified.

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
- Added the F-032 live-only ADK runtime path: hosted investigations now require
  Gemini 2.5 Flash synthesis after evidence collection, persist the bounded
  synthesis on the run, and block approval if the provider is unavailable.
- Expanded the quality gate to 44 tests at 100% statement and branch coverage;
  a real Vertex runner smoke also cited all four active evidence IDs.
- Replaced the assumed Grafana calls with the current official
  `grafana/mcp-grafana` contract: required-tool verification, datasource
  discovery, Prometheus/Loki schemas, provider provenance checks, and private
  Cloud Run service-identity authentication.
- Expanded the quality gate to 46 tests, 651 statements, and 112 branches at
  100% coverage.
- Added a deployable, read-only private-Cloud-Run image wrapper pinned to the
  official `grafana/mcp-grafana` OCI digest and verified the image builds
  locally.

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
