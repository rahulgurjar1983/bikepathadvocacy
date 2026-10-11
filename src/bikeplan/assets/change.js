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
    if (key === "unique_people" || key === "gains_by_type" || key.startsWith("people.")) return 0;
    if (key.startsWith("km.")) return 3;
    return { score: 1, disruption: 1, parking_spaces: 0, lane_km: 3, speed_km: 3 }[key];
  }

  function value(pick, key) {
    if (key.startsWith("people.")) return pick.unique_people_by_type[key.slice(7)];
    if (key.startsWith("km.")) return pick.km_by_fix[key.slice(3)] || 0;
    return pick[key];
  }

  function draw(saved, key) {
    group.clearLayers();
    const elements = new Set(saved.element_ids);
    const drawn = new Set();
    for (const id of saved.project_ids) {
      for (const feature of shapes[id] || []) {
        const element = feature.properties.id;
        if (!elements.has(element) || drawn.has(element)) continue;
        drawn.add(element);
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
          onEachFeature: function (item, layer) {
            layer.on("add", function () {
              const path = layer.getElement();
              path.dataset.elementId = element;
              path.dataset.projectId = id;
              path.dataset.package = key;
            });
          },
        });
        shape.addTo(group);
      }
    }
    document.getElementById("report-map").dataset.package = key;
    document.getElementById("map-package-label").textContent = key;
  }

  function show(step) {
    const chosen = scenario();
    const key = current + ":" + step;
    const saved = JSON.parse(document.getElementById("package-export-data").textContent).packages[key].record;
    const pick = Object.fromEntries(Object.entries(saved.model_totals).map(([name, metric]) => [name, metric.value]));
    draw(saved, key);
    document.getElementById("change-totals").dataset.package = key;
    const worksData = document.getElementById("works-data");
    if (worksData) {
      const plans = JSON.parse(worksData.textContent)[current];
      const work = saved.works;
      const summary = Object.fromEntries(["unique_roads", "distinct_sections", "unnamed_roads", "km_by_design", "existing_links_retained", "crossing_upgrades", "parking_spaces"].map(name => [name, work[name]]));
      summary.gap_records = work.remaining_gaps.length;
      document.getElementById("physical-works").dataset.package = key;
      document.getElementById("works-package").textContent = key;
      document.getElementById("works-summary").textContent = JSON.stringify(summary);
      const body = document.getElementById("works-rows");
      body.replaceChildren();
      for (const id of work.sections.map(section => section.id).concat(work.crossing_upgrades)) {
        const row = document.createElement("tr");
        row.dataset.workId = id;
        row.dataset.package = key;
        for (const value of plans.rows[id]) {
          const cell = document.createElement("td");
          const code = document.createElement("code");
          code.textContent = value;
          cell.appendChild(code);
          row.appendChild(cell);
        }
        body.appendChild(row);
      }
    }
    const deliveryData = document.getElementById("delivery-data");
    if (deliveryData) {
      const text = JSON.parse(deliveryData.textContent)[current + ":" + step];
      document.getElementById("delivery-choice").innerHTML = text;
      document.getElementById("opening-delivery").innerHTML = '<p id="council-ask">I ask council to take the next evidence and design step.</p>' + text;
    }
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
    for (const cell of document.querySelectorAll("#change-totals [data-total], #change-totals [data-measure]")) {
      cell.textContent = value(pick, cell.dataset.measure || cell.dataset.total).toFixed(places(cell.dataset.measure || cell.dataset.total));
    }
    const point = document.getElementById("curve-" + current).getAttribute("points").split(" ")[step].split(",");
    dot.setAttribute("cx", point[0]);
    dot.setAttribute("cy", point[1]);
    dot.setAttribute("data-step", String(step));
    output.textContent = "Step " + step + " of " + (chosen.picks.length - 1) + ": " + chosen.picks[step].name;
    window.dispatchEvent(new CustomEvent("package-selected", { detail: { scenario: current, rank: step } }));
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
