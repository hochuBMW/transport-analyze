"""
Пешие изохроны по предобработанному графу (pickle).
"""
from __future__ import annotations

import heapq
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import pyproj
from shapely.geometry import MultiPoint, Point, mapping
from shapely.strtree import STRtree

from graph_store import load_pedestrian_graph
from utils import haversine_m

logger = logging.getLogger(__name__)

_transformer_to_m = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

_NODE_TREE_CACHE: Dict[str, Tuple[float, STRtree, List[int]]] = {}

# Цвета зон для фронта (от меньшего интервала к большему)
_ZONE_COLORS = ("#22c55e", "#3b82f6", "#8b5cf6", "#f59e0b", "#ef4444", "#06b6d4")


def _graph_cache_key(graph: Dict[str, Any]) -> str:
    meta = graph.get("meta") or {}
    return str(meta.get("source_geojson", "")) + str(meta.get("edge_count", ""))


def _node_spatial_index(graph: Dict[str, Any]) -> Tuple[STRtree, List[int]]:
    key = _graph_cache_key(graph)
    pkl_mtime = graph.get("meta", {}).get("_pkl_mtime")
    cache_key = f"{key}:{pkl_mtime}"

    cached = _NODE_TREE_CACHE.get(cache_key)
    if cached:
        return cached[1], cached[2]

    node_coords: Dict[int, Tuple[float, float]] = graph["node_coords"]
    node_ids = list(node_coords.keys())
    points_m = []
    for nid in node_ids:
        lon, lat = node_coords[nid]
        x, y = _transformer_to_m.transform(lon, lat)
        points_m.append(Point(x, y))

    tree = STRtree(points_m)
    _NODE_TREE_CACHE[cache_key] = (0.0, tree, node_ids)
    return tree, node_ids


def nearest_graph_node(
    graph: Dict[str, Any],
    lon: float,
    lat: float,
    max_snap_m: float = 80.0,
) -> Tuple[Optional[int], float]:
    tree, node_ids = _node_spatial_index(graph)
    x, y = _transformer_to_m.transform(lon, lat)
    pt = Point(x, y)
    idx = tree.nearest(pt)
    if idx is None:
        return None, float("inf")

    nid = node_ids[int(idx)]
    lon_n, lat_n = graph["node_coords"][nid]
    dist_m = haversine_m(lon, lat, lon_n, lat_n)
    if dist_m > max_snap_m:
        return None, dist_m
    return nid, dist_m


def _dijkstra_times(
    adj: Dict[int, List[Tuple[int, float]]],
    start: int,
    max_time_s: float,
) -> Dict[int, float]:
    dist: Dict[int, float] = {start: 0.0}
    heap: List[Tuple[float, int]] = [(0.0, start)]

    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, math.inf):
            continue
        if d > max_time_s:
            continue
        for v, w in adj.get(u, []):
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist


def _hull_from_nodes(
    node_coords: Dict[int, Tuple[float, float]],
    node_ids: List[int],
    max_vertices: int = 8000,
) -> Optional[Dict[str, Any]]:
    if not node_ids:
        return None
    if len(node_ids) > max_vertices:
        step = max(1, len(node_ids) // max_vertices)
        node_ids = node_ids[::step]

    coords = [node_coords[n] for n in node_ids if n in node_coords]
    if len(coords) < 3:
        if len(coords) == 1:
            pt = Point(coords[0])
            geom = pt.buffer(0.00025)
            return mapping(geom)
        if len(coords) == 2:
            mp = MultiPoint(coords)
            geom = mp.buffer(0.0002)
            return mapping(geom)
        return None

    mp = MultiPoint(coords)
    hull = mp.convex_hull
    if hull.is_empty:
        return None
    return mapping(hull)


def compute_pedestrian_isochrones(
    origin_lon: float,
    origin_lat: float,
    intervals_min: List[float],
    max_snap_m: float = 80.0,
    graph: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not intervals_min:
        raise ValueError("intervals_min must not be empty")

    intervals_sorted = sorted(set(float(t) for t in intervals_min if float(t) > 0))
    if not intervals_sorted:
        raise ValueError("intervals_min must contain positive values")

    g = graph or load_pedestrian_graph()
    start_node, snap_m = nearest_graph_node(g, origin_lon, origin_lat, max_snap_m=max_snap_m)
    if start_node is None:
        raise ValueError(
            f"Не удалось привязать точку к графу в пределах {max_snap_m} м (расстояние до ближайшего узла: {snap_m:.0f} м)"
        )

    max_time_s = intervals_sorted[-1] * 60.0
    adj_raw = g.get("adj") or {}
    adj: Dict[int, List[Tuple[int, float]]] = {}
    for k, edges in adj_raw.items():
        adj[int(k)] = [(int(v), float(w)) for v, w in edges]

    times_s = _dijkstra_times(adj, start_node, max_time_s)
    node_coords: Dict[int, Tuple[float, float]] = g["node_coords"]

    features: List[Dict[str, Any]] = []
    zones_meta: List[Dict[str, Any]] = []

    for i, t_min in enumerate(intervals_sorted):
        limit_s = t_min * 60.0
        reachable = [nid for nid, t in times_s.items() if t <= limit_s + 1e-6]
        geom = _hull_from_nodes(node_coords, reachable)
        if not geom:
            continue
        color = _ZONE_COLORS[i % len(_ZONE_COLORS)]
        props = {
            "interval_min": t_min,
            "interval_s": limit_s,
            "reachable_nodes": len(reachable),
            "fill_color": color,
            "stroke_color": color,
        }
        features.append({"type": "Feature", "geometry": geom, "properties": props})
        zones_meta.append(
            {
                "interval_min": t_min,
                "reachable_nodes": len(reachable),
                "max_travel_s": min((times_s[n] for n in reachable), default=0),
            }
        )

    snap_lon, snap_lat = node_coords[start_node]
    origin_feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [origin_lon, origin_lat]},
        "properties": {"role": "origin"},
    }
    snap_feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [snap_lon, snap_lat]},
        "properties": {"role": "snapped_node", "snap_distance_m": round(snap_m, 1)},
    }

    return {
        "origin": [origin_lon, origin_lat],
        "snapped_node": [snap_lon, snap_lat],
        "snap_distance_m": round(snap_m, 1),
        "start_node_id": start_node,
        "intervals_min": intervals_sorted,
        "zones": zones_meta,
        "geojson": {
            "type": "FeatureCollection",
            "features": [origin_feature, snap_feature] + features,
        },
        "graph_meta": g.get("meta"),
    }
