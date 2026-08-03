# Feature QA Report

Tracker source: `feature_status_tracker.csv`

## Totals

- Total features discovered: 43
- Total verified before fixes: 37
- Total failed before fixes: 6
- Total fixed: 6
- Total verified after retest: 43
- Total still blocked: 0
- Total needing product decision: 0

## Unresolved Critical Or High

- None

## Files Changed Or Audited

- `app/web/index.html; app/web/app.js; app/api.py`
- `app/api.py; app/service.py; app/domain.py`
- `app/web/index.html; app/web/app.js; app/domain.py`
- `app/api.py; app/adapters.py; app/web/app.js`
- `app/adapters.py; app/service.py`
- `app/adapters.py; app/service.py; app/domain.py`
- `app/service.py; app/domain.py`
- `app/domain.py; app/service.py`
- `app/service.py; app/domain.py; app/web/app.js`
- `app/api.py; app/service.py; app/web/app.js`
- `app/service.py; app/api.py`
- `app/service.py; app/adapters.py; app/domain.py`
- `app/service.py; app/adapters.py`
- `app/adapters.py; app/service.py; app/api.py`
- `app/service.py; app/api.py; app/web/app.js`
- `app/domain.py; app/service.py; app/web/index.html; README.md; tests/integration/test_api.py`
- `app/api.py; tests/integration/test_api.py; agents-cli-manifest.yaml; Cloud Run IAM policy`
- `app/web/app.js; app/api.py; app/service.py`
- `app/web/index.html; app/web/styles.css; app/web/app.js`
- `app/web/styles.css; app/web/index.html`
- `tests/integration/test_workflow.py; tests/integration/test_api.py`
- `app/agent.py; tests/unit/test_agent_contract.py; tests/eval/datasets/basic-dataset.json`
- `app/api.py; app/service.py; tests/integration/test_api.py`
- `app/actions.py; app/api.py; app/adapters.py; tests/unit/test_actions.py; tests/unit/test_adapters.py; tests/integration/test_api.py; pyproject.toml; uv.lock; .env.example; tests/integration/test_api.py`
- `app/agent_runtime.py; app/api.py; app/domain.py; app/service.py; app/web/app.js; tests/unit/test_agent_runtime.py; tests/integration/test_api.py; tests/integration/test_workflow.py`
- `app/adapters.py; app/api.py; app/service.py; tests/unit/test_adapters.py; tests/integration/test_api.py; tests/integration/test_workflow.py; .env.example; deploy/grafana-mcp/Dockerfile`
- `app/api.py; Dockerfile; Cloud Run IAM policy`
- `README.md; LICENSE; repository metadata`
- `pyproject.toml; uv.lock`
- `app/web/app.js; app/domain.py; app/adapters.py; README.md`
- `docs/CUTLINE_Competition_Submission_Package_2026_07_31.html`
- `artifacts/submission-video/CUTLINE_Agentic_Cinema_Competition_Final_2026_08_02.mp4; qa_evidence/reports/competition_demo_video_2026_08_02.sha256; qa_evidence/reports/competition_demo_video_metadata_2026_08_02.json; qa_evidence/reports/competition_demo_public_verification_2026_08_02.json; qa_evidence/screenshots/competition_demo_public_youtube_2026_08_02.png; pyproject.toml`
- `feature_qa_report.md; feature_status_tracker.html; feature_status_tracker.xlsx`
- `Cloud Run service configuration; README.md; .env.example`
- `git history; repository metadata`

## Commits Recorded In Tracker

- `8db728e`
- `2a53f46`
- `cdaa0e2`
- `1223c7e`
- `6d3e13c; e92972b`
- `959a70f`
- `437d47b`

## Test Evidence

- Test types used: `Manual UI`, `Integration Test`, `Automated Test`, `Manual UI; Competition Compliance Review`, `Accessibility Review`, `Responsive Review`, `Regression Test`, `Contract Test; Hosted Integration Test`, `Hosted Browser; Integration Test`, `Competition Compliance Review`, `Static Compliance Scan; Contract Test`, `Hosted Browser; Evidence Review`, `Competition Compliance Review; Content Review`, `Competition Compliance Review; Media Review`, `Static Review`, `Artifact Parity Test`, `Cloud Configuration Review`
- Commands run are not captured as a dedicated tracker column, so this report only summarizes tracker-backed test evidence.

## Coverage Gaps

- No explicit coverage gaps recorded

## Recommended Next Pass

- Continue using the tracker loop for the next repo improvement and regenerate the workbook/report artifacts after changes.
