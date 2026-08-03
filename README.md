# CUTLINE

CUTLINE is a human-governed release-assurance agent for an agentic-cinema
production deadline. It turns live Grafana MCP evidence into a bounded recovery
proposal, requires explicit operator approval, executes through a Google Cloud
action boundary, and verifies the result with fresh evidence.

The included **Eclipse Protocol / SQ-42** scenario is a controlled, deterministic
demonstration: 18 final VFX shots, 4,800 frames of backlog, and 24 minutes until
package lock.

**Hosted controlled build:** https://cutline-vfz4s45c3q-uc.a.run.app/

**Competition demo:** https://youtu.be/yoquhZPl8Cc

## Why this is not “an AI that makes a movie”

CUTLINE does not generate a finished film. It solves a production problem that
becomes more important as agentic tools create media at scale: can the team prove
that the final shots will cross the delivery cutline, safely recover when they
will not, and preserve an auditable decision trail?

## Architecture

- **Google ADK + Gemini 2.5 Flash on Vertex AI**: bounded evidence synthesis; it cannot approve,
  execute, perform authoritative arithmetic, or declare success.
- **FastAPI service**: deterministic workflow, impact arithmetic, approval
  invariants, idempotency, receipts, and verification gates.
- **Official Grafana MCP**: protocol-native streamable-HTTP client for a private
  Cloud Run deployment of `grafana/mcp-grafana`, using service identity,
  discovered datasource UIDs, and Prometheus/Loki evidence.
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
GRAFANA_MCP_TOKEN=
GRAFANA_MCP_USE_GOOGLE_ID_TOKEN=true
GRAFANA_MCP_AUDIENCE=https://<private-mcp-cloud-run-service>
CUTLINE_ACTION_URL=https://<cloud-run-action-service>
CUTLINE_ACTION_TOKEN=<secret-manager-injected-action-token>
```

The Grafana endpoint must expose the official `list_datasources`,
`query_prometheus`, and `query_loki_logs` operations. CUTLINE uses their current
official schemas, requires provider timestamps and `run_id` labels, and rejects
missing, stale, malformed, or mismatched evidence instead of manufacturing
provenance.

`deploy/grafana-mcp/Dockerfile` pins the official Grafana MCP image used for the
private Cloud Run evidence boundary. The MCP service receives its Grafana Cloud
service-account token only from Secret Manager and is deployed with write tools
disabled; CUTLINE authenticates to that private service with its Cloud Run
identity token.

The live action route is authenticated, plan-allowlisted, and idempotent.
Cloud Run stores action records with atomic-create semantics in Firestore, so
retries return the original receipt and conflicting key reuse is rejected.

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
The approved managed Vertex evaluation completed all three cases with 100%
final-response-quality and safety pass rates. Curated traces and grader results
are under `qa_evidence/eval/`.

The included Dockerfile is Cloud Run-ready. The public hosted revision runs in
live mode with Gemini 2.5 Flash on Vertex AI, a private official
`grafana/mcp-grafana` Cloud Run service, and an authenticated Google Cloud action
boundary. Provider credentials are configured through Secret Manager and never
shipped to the browser. Live readiness and investigation remain fail-closed if
any required provider, identity, datasource, or action configuration is absent.

```bash
gcloud config set project <dedicated-cutline-project>
agents-cli deploy
```

The local test workflow never performs deployment, billing mutation, or paid
evaluation.
