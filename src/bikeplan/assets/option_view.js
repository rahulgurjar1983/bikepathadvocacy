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
