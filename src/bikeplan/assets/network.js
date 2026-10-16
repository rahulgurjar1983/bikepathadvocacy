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
  map.createPane("streets").style.zIndex = 390;
  map.createPane("places").style.zIndex = 395;
  const colours_by_level = { 1: "#5aa9e6", 2: "#16407a", 3: "#f08080", 4: "#a01010" };
  const widths = {
    path: 2, footway: 2, cycleway: 2, pedestrian: 2, living_street: 2, service: 2, track: 2,
    residential: 3, unclassified: 3, tertiary: 4, tertiary_link: 4,
    secondary: 5, secondary_link: 5, primary: 6, primary_link: 6, trunk: 7, trunk_link: 7,
  };

  function describe(text) {
    const box = document.createElement("div");
    box.textContent = text;
    return box;
  }

  function mark(layer, attributes, text) {
    layer.on("add", function () {
      for (const name in attributes) layer.getElement().setAttribute(name, attributes[name]);
    });
    layer.bindTooltip(describe(text), { sticky: true });
    layer.on("click", function () {
      layer.openTooltip();
    });
  }

  const streetLayers = data.streets.pieces.map(function (piece) {
    const layer = L.polyline(piece.lines, {
      pane: "streets",
      className: "street-line",
      color: colours_by_level[piece.lts],
      weight: widths[piece.highway] || 3,
      opacity: 1,
    });
    mark(
      layer,
      { "data-level": String(piece.lts) },
      (piece.name || "Unnamed street") + ", " + piece.highway + ". Stress level " + piece.lts +
        ", modelled. " + (piece.aaa ? "Rated all ages." : "Not rated all ages."),
    );
    return { layer: layer, piece: piece };
  });
  const levels = { 1: true, 2: true, 3: true, 4: true };
  const overlay = { streets: false, aaa: false };

  function refreshStreets() {
    for (const street of streetLayers) {
      const shown =
        overlay.streets && levels[street.piece.lts] && (!overlay.aaa || street.piece.aaa);
      if (shown) street.layer.addTo(map);
      else street.layer.remove();
    }
  }

  const placeLayers = {};
  for (const place of data.places) {
    const key = document.querySelector('#overlay-key .key-shape[data-kind="' + place.type + '"]');
    const label = place.type.replace("_", " ");
    const marker = L.marker([place.lat, place.lon], {
      pane: "places",
      icon: L.divIcon({
        className: "place-marker",
        html: key ? key.outerHTML : "",
        iconSize: [16, 16],
      }),
    });
    mark(marker, { "data-kind": place.type }, place.name + ", " + label);
    (placeLayers[place.type] = placeLayers[place.type] || L.layerGroup()).addLayer(marker);
  }
  for (const kind in placeLayers) {
    placeLayers[kind].addTo(map);
    document.getElementById("overlay-" + kind).addEventListener("change", function (event) {
      if (event.target.checked) placeLayers[kind].addTo(map);
      else placeLayers[kind].remove();
    });
  }
  const switches = {
    streets: function (on) { overlay.streets = on; },
    aaa: function (on) { overlay.aaa = on; },
  };
  for (const level of [1, 2, 3, 4]) {
    switches["lts-" + level] = function (on) { levels[level] = on; };
  }
  for (const name in switches) {
    const input = document.getElementById("overlay-" + name);
    if (!input) continue;
    input.addEventListener("change", function () {
      switches[name](input.checked);
      refreshStreets();
    });
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
      if (item.outside) layer.bindTooltip(item.outside, { sticky: true });
      layer.getElement().setAttribute("data-state", state);
    }
    (totals.querySelector("a") || totals).textContent = current.steps[step].text;
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
