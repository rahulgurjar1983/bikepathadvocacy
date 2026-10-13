document.addEventListener("DOMContentLoaded", function () {
  const data = JSON.parse(document.getElementById("network-data").textContent);
  const colours = { today: "#2e7d32", made: "#1b5e8a", still: "#a01010" };
  const kinds = { school: "#e0b000", station: "#ffffff", town_centre: "#7b3fa0" };
  const slider = document.getElementById("disruption-slider");
  const totals = document.getElementById("step-totals");
  const dot = document.getElementById("chart-dot");
  const map = L.map("network-map", { attributionControl: false });
  const group = L.layerGroup().addTo(map);
  const points = [];
  for (const option of data.options) {
    for (const item of option.lines) {
      for (const point of item.line) points.push([point[1], point[0]]);
    }
  }
  if (points.length) map.fitBounds(L.latLngBounds(points));
  else map.setView([0, 0], 1);
  for (const place of data.places) {
    L.circleMarker([place.lat, place.lon], {
      radius: 4,
      color: "#222222",
      weight: 1,
      fillColor: kinds[place.type] || "#888888",
      fillOpacity: 1,
    })
      .bindTooltip(place.name + " (" + place.type + ")")
      .addTo(map);
  }
  let current = data.options.find(function (option) {
    return option.id === data.pick;
  });

  function draw(step) {
    const stepOf = {};
    current.steps.forEach(function (item, index) {
      for (const work of item.works) stepOf[work] = index;
    });
    group.clearLayers();
    for (const item of current.lines) {
      let state = "still";
      if (item.ok) state = "today";
      else if (item.work !== null && stepOf[item.work] <= step) state = "made";
      const layer = L.polyline(
        item.line.map(function (point) {
          return [point[1], point[0]];
        }),
        { color: colours[state], weight: 4, opacity: 1 },
      );
      group.addLayer(layer);
      layer.getElement().setAttribute("data-state", state);
    }
    totals.textContent = current.steps[step].text;
    const spot = current.steps[step].dot;
    dot.setAttribute("cx", spot[0]);
    dot.setAttribute("cy", spot[1]);
    slider.value = String(step);
  }

  function choose(option) {
    current = option;
    slider.max = String(option.steps.length - 1);
    draw(option.rec);
  }

  slider.addEventListener("input", function () {
    draw(Number(slider.value));
  });
  for (const option of data.options) {
    document.getElementById("option-" + option.id).addEventListener("change", function () {
      choose(option);
    });
  }
  document.getElementById("map-controls").hidden = false;
  slider.max = String(current.steps.length - 1);
  draw(current.rec);
});
