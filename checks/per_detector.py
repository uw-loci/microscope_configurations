"""Per-camera values in one microscope config: the ``per_detector`` overlay.

COPY. The canonical function is ``apply_detector_overlay`` in microscope_control
(``microscope_control/config/per_detector.py``); QPSC's MicroscopeConfigManager applies
the same rules. This repository's checks run in CI with only PyYAML installed, so they
carry this copy instead of depending on microscope_control. Change all three together.

The active camera's entry of every ``per_detector`` mapping is merged into the mapping
that holds it: scalars replaced, mappings merged recursively, ``device_properties``
lists merged by ``(device, property)`` (replace in place, append new ones). The
``per_detector`` key stays. A detector of None, or one a node does not name, leaves
that node unchanged.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

PER_DETECTOR_KEY = "per_detector"
DEVICE_PROPERTIES_KEY = "device_properties"


def apply_detector_overlay(config: Any, detector_id: Optional[str]) -> Any:
    """A deep copy of ``config`` with ``detector_id``'s ``per_detector`` entries merged in.

    The input is never modified. See the module docstring for the rules.
    """
    result = deepcopy(config)
    _walk(result, detector_id)
    return result


def _walk(node: Any, detector_id: Optional[str]) -> None:
    if isinstance(node, dict):
        if detector_id is not None:
            per_detector = node.get(PER_DETECTOR_KEY)
            if isinstance(per_detector, dict):
                entry = per_detector.get(detector_id)
                if isinstance(entry, dict):
                    _merge_into(node, deepcopy(entry))
        for value in node.values():
            _walk(value, detector_id)
    elif isinstance(node, list):
        for item in node:
            _walk(item, detector_id)


def _merge_into(target: dict, overlay: dict) -> None:
    for key, value in overlay.items():
        current = target.get(key)
        if key == DEVICE_PROPERTIES_KEY and isinstance(current, list) and isinstance(value, list):
            target[key] = _merge_device_properties(current, value)
        elif isinstance(current, dict) and isinstance(value, dict):
            _merge_into(current, value)
        else:
            target[key] = value


def _property_key(entry: Any):
    if isinstance(entry, dict):
        return (entry.get("device"), entry.get("property"))
    return None


def _merge_device_properties(base: list, overlay: list) -> list:
    merged = list(base)
    index = {}
    for i, entry in enumerate(merged):
        key = _property_key(entry)
        if key is not None and key not in index:
            index[key] = i
    for entry in overlay:
        key = _property_key(entry)
        if key is not None and key in index:
            merged[index[key]] = entry
        else:
            if key is not None:
                index[key] = len(merged)
            merged.append(entry)
    return merged
