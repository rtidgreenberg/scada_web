"""DynamicData → browser-friendly JSON mapping.

Transforms the raw output of DynamicData.to_json():

  - Unions: already projected to active branch by to_json() (no work needed).
  - char[N] arrays: to_json() emits ["R","U","N","","","..."] — this module
    converts them to a single NUL-trimmed string "RUN".

The transform is applied recursively to the entire JSON tree so it works
regardless of nesting depth (e.g. Limits_t contains Value_t unions with
char arrays inside).
"""

from __future__ import annotations

import json
from typing import Any

import rti.connextdds as dds


def _is_char_array(value: list) -> bool:
    """Detect the DynamicData char[N] pattern: list of single-char strings."""
    if not value:
        return False
    return all(isinstance(v, str) and len(v) <= 1 for v in value)


def _char_array_to_string(chars: list[str]) -> str:
    """Join single-char list and strip NUL padding."""
    return "".join(chars).split("\0", 1)[0]


def _transform(obj: Any) -> Any:
    """Recursively transform a parsed JSON tree to browser-friendly form."""
    if isinstance(obj, dict):
        return {k: _transform(v) for k, v in obj.items()}
    if isinstance(obj, list):
        if _is_char_array(obj):
            return _char_array_to_string(obj)
        return [_transform(item) for item in obj]
    return obj


def sample_to_dict(data: dds.DynamicData) -> dict[str, Any]:
    """Convert a DynamicData sample to a browser-friendly dict.

    Uses DynamicData.to_json() (which already projects unions to active
    branch only) then fixes char[N] arrays to strings.
    """
    raw = json.loads(data.to_json())
    return _transform(raw)
