for (const link of document.querySelectorAll("[data-selected-check-link]")) link.href = link.dataset.selectedCheckLink;
window.addEventListener("package-selected", function (event) {
  const identity = event.detail;
  const key = identity.scenario + ":" + identity.rank;
  const saved = JSON.parse(document.getElementById("package-export-data").textContent).packages[key].record;
  const views = JSON.parse(document.getElementById("package-view-data").textContent)[identity.scenario];
  const projects = saved.project_ids.map(id => views[id]).sort((a, b) => a.rank - b.rank);
  document.getElementById("selected-projects").dataset.package = key;
  document.getElementById("selected-package-label").textContent =
    key + ": " + saved.kind + " package, " + saved.evidence_mode + " evidence.";
  document.getElementById("selected-project-empty").hidden = projects.length !== 0;
  document.getElementById("selected-project-list").innerHTML = projects.map(p => p.link).join("");
  const sheets = document.getElementById("selected-project-sheets");
  sheets.innerHTML = projects.map(p => p.sheet).join("");
  for (const article of sheets.querySelectorAll("article")) article.dataset.package = key;
  for (const link of sheets.querySelectorAll("[data-selected-check-link]")) link.href = link.dataset.selectedCheckLink;
});
function showOption(select) {
  const key = select.value;
  document.getElementById("option-package-label").textContent = key;
  for (const article of document.querySelectorAll("div[data-option-id]"))
    article.hidden = article.dataset.optionType + ":" + article.dataset.optionId !== key;
}
document.addEventListener("change", function (event) {
  if (event.target.id === "option-package-select") showOption(event.target);
});
const optionSelect = document.getElementById("option-package-select");
if (optionSelect) showOption(optionSelect);
