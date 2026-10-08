document.addEventListener("DOMContentLoaded", function () {
  const data = JSON.parse(document.getElementById("review-data").textContent);
  const colours = { 1: "#5aa9e6", 2: "#16407a", 3: "#f08080", 4: "#a01010" };
  const map = L.map("review-map-canvas", { attributionControl: false });
  const route = L.featureGroup().addTo(map);

  function describe(text) {
    const box = document.createElement("div");
    box.textContent = text;
    return box;
  }

  function tip(layer, text) {
    layer.bindTooltip(describe(text), { sticky: true });
    layer.on("click", function () {
      layer.openTooltip();
    });
  }

  for (const item of data.lines) {
    const latlngs = item.line.map(function (point) {
      return [point[1], point[0]];
    });
    const layer = L.polyline(latlngs, {
      className: "route-line",
      color: item.off ? "#222222" : colours[item.lts],
      weight: 6,
      opacity: 1,
      dashArray: item.off ? "8 8" : null,
    });
    tip(
      layer,
      item.off
        ? "Off network: this stretch needs new building."
        : item.name + ". Stress level " + item.lts + ". " +
          (item.aaa ? "Safe for all ages." : "Not safe for all ages.")
    );
    route.addLayer(layer);
  }

  function marker(className, point, fill, text) {
    const layer = L.circleMarker([point[1], point[0]], {
      className: className, radius: 9, color: "#000000", weight: 3, fillColor: fill, fillOpacity: 1,
    });
    tip(layer, text);
    route.addLayer(layer);
  }

  for (const item of data.breaks) {
    marker("route-break", item.lonlat, "#f2c200", "A break in the safe run starts here.");
  }
  for (const item of data.crossings) {
    marker("route-crossing", item.lonlat, "#ffffff", "Crossing of " + item.road + " with no signal.");
  }
  map.fitBounds(route.getBounds());
});
