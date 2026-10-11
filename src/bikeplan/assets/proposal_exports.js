window.addEventListener("package-selected", function (event) {
  const data = JSON.parse(document.getElementById("package-export-data").textContent);
  const identity = event.detail;
  const key = identity.scenario + ":" + identity.rank;
  const saved = data.packages[key];
  const curve = JSON.parse(document.getElementById("change-data").textContent)
    .scenarios.find(item => item.id === identity.scenario);
  const payload = { ...data.metadata, selected: saved.record, curve_totals: curve.picks[identity.rank] };
  for (const [kind, text, type] of [
    ["json", JSON.stringify(payload, null, 2) + "\n", "application/json"],
    ["csv", saved.csv, "text/csv"],
  ]) {
    const link = document.getElementById("package-export-" + kind);
    if (link.href) URL.revokeObjectURL(link.href);
    link.href = URL.createObjectURL(new Blob([text], { type: type + ";charset=utf-8" }));
    link.download = "proposal-" + identity.scenario + "-" + identity.rank + "." + kind;
    link.dataset.package = key;
  }
  document.getElementById("package-export-status").textContent =
    "Export " + key + ": " + saved.record.kind + " package, " + saved.record.evidence_mode + " evidence.";
});
