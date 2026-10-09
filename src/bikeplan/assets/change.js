window.addEventListener("load", function () {
  const data = JSON.parse(document.getElementById("change-data").textContent);
  const map = window.reportMap;
  const slider = document.getElementById("change-slider");
  const dot = document.getElementById("change-dot");
  const output = document.getElementById("change-step");
  const group = L.layerGroup().addTo(map);
  const shapes = {};
  for (const feature of data.shapes.features) {
    const project = feature.properties.project;
    if (!shapes[project]) shapes[project] = [];
    shapes[project].push(feature);
  }
  let current = data.default;

  function scenario() {
    return data.scenarios.find(function (item) {
      return item.id === current;
    });
  }

  function places(key) {
    if (key.startsWith("people.")) return 0;
    if (key.startsWith("km.")) return 3;
    return { score: 1, disruption: 1, parking_spaces: 0, lane_km: 3, speed_km: 3 }[key];
  }

  function value(pick, key) {
    if (key.startsWith("people.")) return pick.people[key.slice(7)];
    if (key.startsWith("km.")) return pick.km_by_fix[key.slice(3)] || 0;
    return pick[key];
  }

  function draw(chosen, step) {
    group.clearLayers();
    for (let index = 1; index <= step; index++) {
      const pick = chosen.picks[index];
      for (const feature of shapes[pick.id] || []) {
        const shape = L.geoJSON(feature, {
          pointToLayer: function (item, latlng) {
            return L.circleMarker(latlng, {
              className: "change-project", radius: 8, color: "#e66100", weight: 3, interactive: false,
              fillColor: "#ffffff", fillOpacity: 1,
            });
          },
          style: function () {
            return { className: "change-project", color: "#e66100", weight: 7, opacity: 0.9, interactive: false };
          },
        });
        shape.addTo(group);
      }
    }
  }

  function show(step) {
    const chosen = scenario();
    const pick = chosen.picks[step];
    draw(chosen, step);
    const opening = document.getElementById("opening");
    opening.dataset.package = current + ":" + step;
    const rankLink = document.createElement("a");
    rankLink.href = "#F13";
    rankLink.textContent = String(step);
    document.getElementById("package-status").replaceChildren(
      document.createTextNode(chosen.label + " (" + current + ") proposal, rank "), rankLink
    );
    document.getElementById("proposal-state").textContent = step === 0
      ? "No new works are selected."
      : "I propose the modelled works in this selection.";
    for (const cell of document.querySelectorAll("[data-opening]")) {
      cell.textContent = value(pick, cell.dataset.opening).toFixed(places(cell.dataset.opening));
    }
    for (const cell of document.querySelectorAll("#change-totals [data-total]")) {
      cell.textContent = value(pick, cell.dataset.total).toFixed(places(cell.dataset.total));
    }
    const point = document.getElementById("curve-" + current).getAttribute("points").split(" ")[step].split(",");
    dot.setAttribute("cx", point[0]);
    dot.setAttribute("cy", point[1]);
    dot.setAttribute("data-step", String(step));
    output.textContent = "Step " + step + " of " + (chosen.picks.length - 1) + ": " + pick.name;
  }

  function choose(id) {
    current = id;
    const chosen = scenario();
    for (const item of data.scenarios) {
      const curve = document.getElementById("curve-" + item.id);
      const selected = item.id === id;
      curve.setAttribute("data-selected", String(selected));
      curve.setAttribute("stroke-width", selected ? "4" : "2");
    }
    slider.max = String(chosen.picks.length - 1);
    slider.value = String(chosen.recommended_stop || 0);
    show(Number(slider.value));
  }

  slider.disabled = false;
  slider.addEventListener("input", function () {
    show(Number(slider.value));
  });
  for (const item of data.scenarios) {
    const radio = document.getElementById("scenario-" + item.id);
    radio.disabled = false;
    radio.addEventListener("change", function () {
      choose(item.id);
    });
  }
  choose(data.default);
});
