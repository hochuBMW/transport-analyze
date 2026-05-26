"""
Загрузка предобработанного пешего графа из pickle (этап 1 изохрон).

Файл создаётся скриптом: python -m scripts.build_pedestrian_graph
"""
from __future__ import annotations

import logging
import os
import pickle
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def project_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, ".."))


def default_pickle_path() -> str:
    return os.path.join(project_root(), "data", "pedestrian_graph.pkl")


def default_geojson_path() -> str:
    root = project_root()
    candidates = [
        os.path.join(root, "pedestrian_graph.geojson"),
        os.path.join(root, "data", "pedestrian_graph.geojson"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return candidates[0]


def load_pedestrian_graph(path: Optional[str] = None) -> Dict[str, Any]:
    """
    Возвращает словарь графа:
      meta, node_coords (id -> (lon, lat)), edges (from, to, length_m, walk_time_s), adj (from -> [(to, walk_time_s), ...])
    """
    pkl_path = path or default_pickle_path()
    if not os.path.isfile(pkl_path):
        raise FileNotFoundError(
            f"Граф не найден: {pkl_path}. "
            "Экспортируйте пешую сеть из QGIS в data/pedestrian_graph.geojson "
            "и выполните: cd backend && python -m scripts.build_pedestrian_graph"
        )

    mtime = os.path.getmtime(pkl_path)
    cached = _CACHE.get(pkl_path)
    if cached and cached[0] == mtime:
        return cached[1]

    with open(pkl_path, "rb") as f:
        graph = pickle.load(f)

    _CACHE[pkl_path] = (mtime, graph)
    meta = graph.get("meta") or {}
    logger.info(
        "Пеший граф загружен: %s узлов, %s рёбер",
        meta.get("node_count"),
        meta.get("edge_count"),
    )
    return graph


def graph_summary(path: Optional[str] = None) -> Dict[str, Any]:
    g = load_pedestrian_graph(path)
    return dict(g.get("meta") or {})
