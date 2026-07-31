# CUTLINE

CUTLINE is a human-governed release-assurance agent for an agentic-cinema
production deadline. It turns live Grafana MCP evidence into a bounded recovery
proposal, requires explicit operator approval, executes through a Google Cloud
action boundary, and verifies the result with fresh evidence.

The included **Eclipse Protocol / SQ-42** scenario is a controlled, deterministic
demonstration: 18 final VFX shots, 4,800 frames of backlog, and 24 minutes until
package lock.

## Why this is not “an AI that makes a movie”

CUTLINE does not generate a finished film. It solves a production problem that
becomes more important as agentic tools create media at scale: can the team prove
that the final shots will cross the delivery cutline, safely recover when they
will not, and preserve an auditable decision trail?

## Architecture

- **Google ADK + Gemini**: bounded evidence synthesis; it cannot approve,
  execute, perform authoritative arithmetic, or declare success.
- **FastAPI service**: deterministic workflow, impact arithmetic, approval
  invariants, idempotency, receipts, and verification gates.
- **Grafana MCP**: protocol-native streamable-HTTP client for alert, Prometheus,
  Loki, and trace evidence.
- **Google Cloud Run action boundary**: the only live mutation path.
- **Vanilla accessible web UI**: sequence-first command center with explicit
  controlled/live disclosure.

## Local controlled demo

```bash
agents-cli install
uv run uvicorn app.fast_api_app:app --host 127.0.0.1 --port 8011
```

Open `http://127.0.0.1:8011`, then follow:

1. **Investigate with Grafana evidence**
2. **Approve recovery**
3. **Execute approved plan**
4. **Verify with fresh evidence**
5. **Refresh audit**

Local mode is clearly labeled and never claims to be live evidence.

## Live integration contract

Copy `.env.example` to `.env` and populate values through Secret Manager in
deployment. Never commit secrets.

```text
CUTLINE_MODE=live
GRAFANA_MCP_URL=https://<hosted-grafana-mcp-endpoint>
GRAFANA_MCP_TOKEN=<secret-manager-injected-token>
CUTLINE_ACTION_URL=https://<cloud-run-action-service>
```

The Grafana endpoint must expose these official MCP tool operations:
`get_alert_rule_by_uid`, `query_prometheus`, `query_loki_logs`, and `get_trace`.
Tool results must provide structured content with `summary`, `values`, and,
when available, `observed_at`, `run_id`, and `id`.

## Quality gates

```bash
./scripts/test
agents-cli lint
node --check app/web/app.js
```

The deterministic Python application scope has a hard 100% statement and branch
coverage gate. Protocol transport, generated ADK utilities, and framework
entrypoints are excluded from that deterministic metric and are covered by
contract/integration checks.

The canonical feature audit is `feature_status_tracker.csv`;
`feature_status_tracker.xlsx` and `feature_status_tracker.html` are generated
views. Evidence lives under `qa_evidence/`.

## Evaluation and deployment

The CUTLINE eval dataset is in `tests/eval/datasets/basic-dataset.json`.
`agents-cli eval run` invokes Gemini/managed evaluation and may consume Google
Cloud credits, so it is intentionally not run without explicit approval.

The included Dockerfile is Cloud Run-ready. Deployment is also intentionally
approval-gated:

```bash
gcloud config set project <dedicated-cutline-project>
agents-cli deploy
```

No deployment, billing mutation, or paid evaluation is performed by the local
test workflow.

