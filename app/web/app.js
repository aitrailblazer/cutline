const $ = (id) => document.getElementById(id);
let scenario;

const escapeText = (value) => String(value ?? "");
const request = async (path, options = {}) => {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error?.message || "Request failed");
  return payload;
};
const post = (path, body = {}) =>
  request(path, { method: "POST", body: JSON.stringify(body) });

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = escapeText(text);
  return element;
}

function renderShots(shots) {
  $("shot-bars").replaceChildren(
    ...shots.map((shot, index) => {
      const bar = node("div", `shot ${shot.at_risk ? "risk" : ""}`);
      bar.style.height = `${36 + index * 7}px`;
      bar.title = `${shot.id}: ${shot.status}`;
      return bar;
    }),
  );
  $("shots").replaceChildren(
    ...shots.map((shot) => {
      const row = document.createElement("tr");
      row.dataset.risk = shot.at_risk;
      [
        shot.id,
        `${shot.frame_start}–${shot.frame_end}`,
        shot.status,
        `${shot.remaining_frames} frames`,
        shot.attempts,
        shot.worker,
        `${shot.eta_minutes} min`,
        shot.dependency,
      ].forEach((value) => row.append(node("td", "", value)));
      return row;
    }),
  );
}

function renderEvidence(items) {
  $("evidence-count").textContent = `${items.length} items`;
  if (!items.length) {
    $("evidence").className = "empty";
    $("evidence").textContent = "Run an investigation to retrieve evidence.";
    return;
  }
  $("evidence").className = "";
  $("evidence").replaceChildren(
    ...items.map((item) => {
      const box = node("div", "evidence-item");
      box.append(
        node("b", "", `${item.kind.toUpperCase()} · ${item.operation}`),
        node("span", "", item.summary),
        node(
          "small",
          "",
          `${item.id} · ${item.source_mode} · ${new Date(item.observed_at).toLocaleTimeString()}`,
        ),
      );
      return box;
    }),
  );
}

function renderDiagnosis(value) {
  if (!value) {
    $("diagnosis").className = "empty";
    $("diagnosis").textContent =
      "No diagnosis until current evidence is available.";
    return;
  }
  $("diagnosis").className = "";
  $("diagnosis").replaceChildren(
    ...[
      ["Evidence", value.evidence_status],
      ["Hypothesis", value.hypothesis],
      ["Alternative", value.alternative],
      ["Discriminator", value.discriminator],
      ["Falsifier", value.falsifier],
    ].map(([label, text]) => {
      const fact = node("div", "fact");
      fact.append(node("small", "", label), node("b", "", text));
      return fact;
    }),
  );
}

function renderProposal(value) {
  if (!value) {
    $("proposal").className = "empty";
    $("proposal").textContent =
      "Investigation must complete before a proposal exists.";
    return;
  }
  $("proposal").className = "keyvals";
  $("proposal").replaceChildren(
    ...[
      ["Plan", value.version],
      ["Concurrency", `${value.concurrency_before} → ${value.concurrency_after}`],
      ["Reserve workers", `${value.reserve_workers_before} → ${value.reserve_workers_after}`],
      ["Blast radius", value.scope],
      ["Scenario cost", `$${value.scenario_cost_usd}`],
      ["Rollback", value.rollback],
    ].map(([label, text]) => {
      const box = node("div");
      box.append(node("span", "", label), node("b", "", text));
      return box;
    }),
  );
}

function renderRecord(id, value, empty) {
  const target = $(id);
  if (!value) {
    target.className = "empty";
    target.textContent = empty;
    return;
  }
  target.className = "";
  target.replaceChildren(node("pre", "", JSON.stringify(value, null, 2)));
}

function render(data) {
  scenario = data;
  const risk = data.shots.filter((shot) => shot.at_risk).length;
  $("mode-badge").textContent = data.mode.replaceAll("_", " ");
  $("connection").textContent = data.blockers.length
    ? data.blockers.join(", ")
    : "Evidence boundary healthy";
  $("state-pill").textContent = data.state;
  $("disclosure").textContent = data.disclosure;
  $("risk-count").textContent = `${risk} / ${data.shots.length}`;
  $("manifest-summary").textContent = `${risk} at risk`;
  $("backlog").textContent = `${data.backlog_frames.toLocaleString()} frames`;
  $("throughput").textContent = `${data.impact.observed_throughput} f/min`;
  $("variance").textContent = data.impact.label;
  $("variance").className = data.impact.variance_minutes > 0 ? "success" : "danger";
  renderShots(data.shots);
  renderEvidence(data.evidence);
  renderDiagnosis(data.diagnosis);
  $("formulas").replaceChildren(
    ...data.impact.formulas.map((formula) => node("div", "formula", formula)),
  );
  renderProposal(data.proposal);
  renderRecord("receipt", data.receipt, "No action executed.");
  renderRecord("verification", data.verification, "Recovery has not been verified.");
  const awaiting = data.state === "AWAITING_APPROVAL";
  $("decision-actions").hidden = !awaiting;
  $("investigate").hidden = !["READY", "BLOCKED"].includes(data.state);
  $("execute").hidden = data.decision?.status !== "APPROVED" || !!data.receipt;
  $("verify").hidden = data.state !== "VERIFYING";
  $("action-help").textContent = `Run ${data.run_id.slice(0, 8)} · ${data.state}`;
  $("announcement").textContent = `CUTLINE state ${data.state}; ${data.impact.label}.`;
}

async function act(action, body) {
  try {
    render(await post(`/api/scenario/${action}`, body));
  } catch (error) {
    $("announcement").textContent = error.message;
    $("action-help").textContent = error.message;
    await load();
  }
}

async function load() {
  render(await request("/api/scenario"));
  const readiness = await request("/api/readiness");
  $("connection").textContent = readiness.ready
    ? "Evidence boundary healthy"
    : readiness.blockers.join(", ");
}

$("reset").addEventListener("click", () => act("reset"));
$("investigate").addEventListener("click", () => act("investigate"));
$("approve").addEventListener("click", () =>
  act("approve", { approver: "Maya Chen" }),
);
$("reject").addEventListener("click", () =>
  act("reject", { approver: "Maya Chen", reason: "Operator rejected plan" }),
);
$("execute").addEventListener("click", () =>
  act("execute", { idempotency_key: `demo-${scenario.run_id}` }),
);
$("verify").addEventListener("click", () => act("verify"));
$("refresh-audit").addEventListener("click", async () => {
  $("audit").textContent = JSON.stringify(await request("/api/audit"), null, 2);
});

load().catch((error) => {
  $("connection").textContent = "Application unavailable";
  $("announcement").textContent = error.message;
});
