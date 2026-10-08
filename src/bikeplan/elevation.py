from pathlib import Path

import networkx as nx
import numpy
import rasterio
from pyproj import Transformer
from scipy.ndimage import map_coordinates


def node_heights(graph: nx.MultiDiGraph, path: Path) -> dict:
    with rasterio.open(path) as source:
        data = source.read(1).astype("float64")
        nodes = list(graph.nodes)
        to_raster = Transformer.from_crs(graph.graph["crs"], source.crs, always_xy=True)
        xs, ys = to_raster.transform(
            [graph.nodes[n]["x"] for n in nodes], [graph.nodes[n]["y"] for n in nodes]
        )
        rows, columns = rasterio.transform.rowcol(source.transform, xs, ys, op=float)
        centred = [numpy.array(rows) - 0.5, numpy.array(columns) - 0.5]
        heights = map_coordinates(data, centred, order=1, mode="nearest")
    return dict(zip(nodes, heights, strict=True))


def set_grades(graph: nx.MultiDiGraph, path: Path) -> None:
    heights = node_heights(graph, path)
    for u, v, data in graph.edges(data=True):
        rise = float(heights[v] - heights[u])
        data["rise_m"] = rise
        data["grade_pct"] = rise / data["length_m"] * 100 if data["length_m"] > 0 else 0.0
