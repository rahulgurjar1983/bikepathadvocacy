document.addEventListener("DOMContentLoaded", function () {
  const data = JSON.parse(document.getElementById("map-data").textContent);
  const colours = { 1: "#5aa9e6", 2: "#16407a", 3: "#f08080", 4: "#a01010" };
  const weights = {
    path: 2, footway: 2, cycleway: 2, pedestrian: 2, living_street: 2, service: 2, track: 2,
    residential: 3, unclassified: 3, tertiary: 4, tertiary_link: 4,
    secondary: 5, secondary_link: 5, primary: 6, primary_link: 6, trunk: 7, trunk_link: 7,
  };
  const map = L.map("report-map-canvas", { attributionControl: false });
  window.reportMap = map;
  const boundary = L.geoJSON(data.boundary, {
    style: { color: "#444444", weight: 2, dashArray: "6 6", fill: false },
    interactive: false,
  }).addTo(map);
  map.fitBounds(boundary.getBounds());
  const group = L.layerGroup().addTo(map);
  const levels = { 1: true, 2: true, 3: true, 4: true };
  let safeOnly = false;

  function describe(text) {
    const box = document.createElement("div");
    box.textContent = text;
    return box;
  }

  function mark(layer, attributes) {
    layer.on("add", function () {
      for (const name in attributes) layer.getElement().setAttribute(name, attributes[name]);
    });
    layer.bindTooltip(describe(attributes.text), { sticky: true });
    layer.on("click", function () {
      layer.openTooltip();
    });
  }

  const streets = data.segments.map(function (segment, index) {
    const layer = L.polyline(segment.lines, {
      color: colours[segment.lts],
      weight: weights[segment.highway] || 3,
      opacity: 1,
    });
    const safe = segment.aaa ? "Safe for all ages" : "Not safe for all ages";
    mark(layer, {
      "data-id": String(index),
      text:
        (segment.name || "Unnamed street") + ", " + segment.highway +
        ". Stress level " + segment.lts + ". " + safe + "." +
        (segment.fix ? " Fix: " + segment.fix + "." : ""),
    });
    return { layer: layer, segment: segment };
  });

  function refresh() {
    for (const street of streets) {
      const shown = levels[street.segment.lts] && (!safeOnly || street.segment.aaa);
      if (shown) group.addLayer(street.layer);
      else group.removeLayer(street.layer);
    }
  }

  function placeLayer(kind, fill) {
    const places = L.layerGroup();
    for (const place of data.places) {
      if (place.kind !== kind) continue;
      const layer = L.circleMarker([place.lat, place.lon], {
        className: "map-place", radius: 6, color: "#222222", weight: 2, fillColor: fill, fillOpacity: 1,
      });
      mark(layer, {
        "data-kind": kind,
        text: (place.name || "Unnamed") + ", " + kind,
      });
      places.addLayer(layer);
    }
    return places;
  }

  const placeLayers = { schools: placeLayer("school", "#f2c200"), stations: placeLayer("station", "#ffffff") };

  const surveys = L.geoJSON(data.survey_options || { type: "FeatureCollection", features: [] }, {
    style: function () {
      return { className: "map-survey", color: "#a65b00", weight: 4, dashArray: "4 4" };
    },
    onEachFeature: function (feature, layer) {
      layer.bindTooltip(describe(feature.properties.street + ": needs survey; check " + feature.properties.survey_checks.join(", ")), { sticky: true });
    },
  });
  document.getElementById("layer-survey").addEventListener("change", function (event) {
    if (event.target.checked) surveys.addTo(map);
    else surveys.remove();
  });
  const proposed = L.layerGroup();
  if (data.projects) {
    for (const feature of data.projects.features) {
      const found = feature.properties;
      const shape = L.geoJSON(feature, {
        pointToLayer: function (item, latlng) {
          return L.circleMarker(latlng, {
            className: "map-project", radius: 8, color: "#7b2cbf", weight: 3,
            fillColor: "#ffffff", fillOpacity: 1,
          });
        },
        style: function () {
          return { className: "map-project", color: "#7b2cbf", weight: 6, opacity: 0.9 };
        },
      });
      shape.eachLayer(function (layer) {
        layer.bindTooltip(describe("Rank " + found.rank + ": " + found.fix + ", " + found.street), {
          sticky: true,
        });
      });
      proposed.addLayer(shape);
    }
  }
  document.getElementById("layer-proposed").addEventListener("change", function (event) {
    if (event.target.checked) proposed.addTo(map);
    else proposed.remove();
  });

  for (const level of [1, 2, 3, 4]) {
    document.getElementById("layer-lts-" + level).addEventListener("change", function (event) {
      levels[level] = event.target.checked;
      refresh();
    });
  }
  document.getElementById("layer-aaa").addEventListener("change", function (event) {
    safeOnly = event.target.checked;
    refresh();
  });
  for (const name in placeLayers) {
    document.getElementById("layer-" + name).addEventListener("change", function (event) {
      if (event.target.checked) placeLayers[name].addTo(map);
      else placeLayers[name].remove();
    });
  }
  refresh();
});
