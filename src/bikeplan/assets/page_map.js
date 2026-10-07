document.addEventListener("DOMContentLoaded", function () {
  const data = JSON.parse(document.getElementById("page-data").textContent);
  const colours = { 1: "#5aa9e6", 2: "#16407a", 3: "#f08080", 4: "#a01010" };
  const map = L.map("report-map-canvas", { attributionControl: false });
  const lts = L.geoJSON(data.network, {
    style: function (feature) {
      return { color: colours[feature.properties.lts], weight: 3, opacity: 1 };
    },
  });
  const aaa = L.geoJSON(data.network, {
    filter: function (feature) {
      return feature.properties.aaa;
    },
    style: { color: "#2a9d3a", weight: 5, opacity: 0.8 },
  });
  const places = L.geoJSON(data.places, {
    pointToLayer: function (feature, latlng) {
      return L.circleMarker(latlng, { radius: 5, color: "#222222", fillColor: "#f4d35e", fillOpacity: 1 });
    },
  });
  const projects = L.geoJSON(data.project_shapes, {
    style: { color: "#7b2cbf", weight: 6, opacity: 0.9 },
  });
  const layers = { lts: lts, aaa: aaa, places: places, projects: projects };
  for (const name in layers) {
    const box = document.getElementById("layer-" + name);
    const apply = function () {
      if (box.checked) layers[name].addTo(map);
      else map.removeLayer(layers[name]);
    };
    box.addEventListener("change", apply);
    apply();
  }
  const bounds = lts.getBounds();
  if (bounds.isValid()) map.fitBounds(bounds);
  else map.setView([0, 0], 2);
});
