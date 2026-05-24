// Live BPMN dashboard for Autonomous Ops orchestrator.
// Loads the diagram, opens an SSE stream for the request_id from ?rid=,
// and lights up nodes as StatusEvents arrive.

const params = new URLSearchParams(location.search);
const rid = params.get("rid");
document.getElementById("rid-label").textContent = rid ? `req: ${rid}` : "no request";

const viewer = new BpmnJS({ container: "#canvas" });
const canvas = () => viewer.get("canvas");

const log = (msg) => {
  const li = document.createElement("li");
  li.textContent = msg;
  document.getElementById("event-log").prepend(li);
};

async function loadDiagram() {
  const xml = await fetch("/static/diagram.bpmn").then(r => r.text());
  await viewer.importXML(xml);
  canvas().zoom("fit-viewport");
}

function applyEvent(ev) {
  const id = ev.node;
  if (ev.status === "started") {
    canvas().removeMarker(id, "highlight-done");
    canvas().addMarker(id, "highlight-active");
  } else if (ev.status === "done") {
    canvas().removeMarker(id, "highlight-active");
    canvas().addMarker(id, "highlight-done");
  }
  const time = ev.at?.split("T")[1]?.slice(0, 8) ?? "";
  log(`${time} ${ev.node} ${ev.status} ${ev.detail || ""}`);
}

function connect(rid) {
  const es = new EventSource(`/events/stream/${rid}`);
  es.onmessage = (e) => applyEvent(JSON.parse(e.data));
  es.onerror = () => {
    es.close();
    log("(stream lost — reconnecting in 1s)");
    setTimeout(() => connect(rid), 1000);
  };
}

(async () => {
  await loadDiagram();
  if (rid) connect(rid);
})();
