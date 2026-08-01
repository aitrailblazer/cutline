# Feature QA Report

Tracker source: `feature_status_tracker.csv`

## Totals

- Total features discovered: 33
- Total verified before fixes: 31
- Total failed before fixes: 33
- Total fixed: 2
- Total verified after retest: 31
- Total still blocked: 0
- Total needing product decision: 0

## Unresolved Critical Or High

- F-032 `Hosted ADK Gemini investigation` — Critical — Retest Required
- F-033 `Official Grafana MCP runtime contract` — Critical — Retest Required

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
- `app/api.py; app/web/index.html; app/web/app.js`
- `app/api.py; tests/integration/test_api.py; agents-cli-manifest.yaml; Cloud Run IAM policy`
- `app/web/app.js; app/api.py; app/service.py`
- `app/web/index.html; app/web/styles.css; app/web/app.js`
- `app/web/styles.css; app/web/index.html`
- `tests/integration/test_workflow.py; tests/integration/test_api.py`
- `app/agent.py; tests/unit/test_agent_contract.py; tests/eval/datasets/basic-dataset.json`
- `app/api.py; app/service.py; tests/integration/test_api.py`
- `app/actions.py; app/api.py; app/adapters.py; tests/unit/test_actions.py; tests/unit/test_adapters.py; tests/integration/test_api.py; pyproject.toml; uv.lock; .env.example`
- `app/agent_runtime.py; app/api.py; app/domain.py; app/service.py; app/web/app.js; tests/unit/test_agent_runtime.py; tests/integration/test_api.py; tests/integration/test_workflow.py`
- `app/adapters.py; app/api.py; tests/unit/test_adapters.py; .env.example; deploy/grafana-mcp/Dockerfile`

## Commits Recorded In Tracker

- `8db728e`
- `2a53f46`
- `cdaa0e2`
- `1223c7e`
- `6d3e13c`
- `3212e19`
- `cd2d7e3`

## Test Evidence

- Test types used: `Manual UI`, `Integration Test`, `Automated Test`, `Accessibility Review`, `Responsive Review`, `Regression Test`, `Contract Test; Hosted Integration Test`
- Commands run are not captured as a dedicated tracker column, so this report only summarizes tracker-backed test evidence.

## Coverage Gaps

- No explicit coverage gaps recorded

## Recommended Next Pass

- Resolve the remaining unresolved critical/high rows before expanding scope.
