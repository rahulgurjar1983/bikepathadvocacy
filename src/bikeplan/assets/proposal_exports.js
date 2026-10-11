let exportSelection = 0;
window.addEventListener("package-selected", async function (event) {
  const selection = ++exportSelection;
  const data = JSON.parse(document.getElementById("package-export-data").textContent);
  const identity = event.detail;
  const key = identity.scenario + ":" + identity.rank;
  const saved = data.packages[key];
  const curve = JSON.parse(document.getElementById("change-data").textContent)
    .scenarios.find(item => item.id === identity.scenario);
  const payload = { ...data.metadata, selected: saved.record, curve_totals: { ...curve.picks[identity.rank], ...Object.fromEntries(Object.entries(saved.record.model_totals).map(([name, metric]) => [name, metric.value])) } };
  function link(kind, text, type) {
    const node = document.getElementById("package-export-" + kind);
    if (node.href) URL.revokeObjectURL(node.href);
    node.href = URL.createObjectURL(new Blob([text], { type: type + ";charset=utf-8" }));
    node.download = "proposal-" + identity.scenario + "-" + identity.rank + "." + kind;
    node.dataset.package = key;
  }
  link("json", JSON.stringify(payload, null, 2) + "\n", "application/json");
  const csv = document.getElementById("package-export-csv");
  if (csv.href) URL.revokeObjectURL(csv.href);
  csv.removeAttribute("href");
  csv.removeAttribute("data-package");
  const bytes = Uint8Array.from(atob(saved.csv_gzip), character => character.charCodeAt(0));
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  const text = await new Response(stream).text();
  if (selection !== exportSelection) return;
  link("csv", text, "text/csv");
  document.getElementById("package-export-status").textContent =
    "Export " + key + ": " + saved.record.kind + " package, " + saved.record.evidence_mode + " evidence.";
});
