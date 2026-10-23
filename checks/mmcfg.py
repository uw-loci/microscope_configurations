"""Read a Micro-Manager hardware configuration (.cfg) far enough to check it against a YAML.

Only the lines a QPSC config depends on are kept: device labels, the Core camera,
configuration-group presets and pixel-size presets. The format is Micro-Manager's
comma-separated one ("Device,<label>,<library>,<adapter>", "ConfigGroup,<group>,
<preset>,<device>,<property>,<value>", ...). Values can contain commas (a property
value such as "D5020-20V Controller" cannot, but a description can), so each line is
split only as far as its keyword needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

Setting = Tuple[str, str, str]  # (device, property, value)


@dataclass
class MMConfig:
    path: Path
    devices: Dict[str, Tuple[str, str]] = field(default_factory=dict)  # label -> (library, adapter)
    core_camera: Optional[str] = None
    groups: Dict[str, Dict[str, List[Setting]]] = field(default_factory=dict)
    pixel_presets: Dict[str, List[Setting]] = field(default_factory=dict)
    pixel_sizes: Dict[str, float] = field(default_factory=dict)

    def preset(self, group: str, name: str) -> Optional[List[Setting]]:
        return self.groups.get(group, {}).get(name)

    def pixel_size_for(self, settings: List[Setting]) -> List[Tuple[str, float]]:
        """Pixel-size presets whose every setting is part of ``settings``, with their sizes.

        Micro-Manager picks the pixel-size preset whose settings all match the current
        hardware state, so a preset applies to an objective preset when its settings are
        a subset of that preset's.
        """
        have = set(settings)
        out = []
        for name, req in self.pixel_presets.items():
            if req and set(req) <= have and name in self.pixel_sizes:
                out.append((name, self.pixel_sizes[name]))
        return out


def parse(path: Path) -> MMConfig:
    cfg = MMConfig(path=Path(path))
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        kind = line.split(",", 1)[0]
        if kind == "Device":
            _, label, library, adapter = line.split(",", 3)
            cfg.devices[label] = (library, adapter)
        elif kind == "Property":
            parts = line.split(",", 3)
            if len(parts) == 4 and parts[1] == "Core" and parts[2] == "Camera":
                cfg.core_camera = parts[3]
        elif kind == "ConfigGroup":
            parts = line.split(",", 5)
            if len(parts) == 6:
                _, group, preset, device, prop, value = parts
                cfg.groups.setdefault(group, {}).setdefault(preset, []).append(
                    (device, prop, value)
                )
            elif len(parts) == 3:  # an empty group declaration
                cfg.groups.setdefault(parts[1], {}).setdefault(parts[2], [])
        elif kind == "ConfigPixelSize":
            parts = line.split(",", 4)
            if len(parts) == 5:
                _, name, device, prop, value = parts
                cfg.pixel_presets.setdefault(name, []).append((device, prop, value))
        elif kind == "PixelSize_um":
            _, name, value = line.split(",", 2)
            try:
                cfg.pixel_sizes[name] = float(value)
            except ValueError:
                pass
    return cfg
