"""
boardview_loader.py — Unified loader / indexer / highlighter for board flat-dumps.

Supports BOTH flat-board JSON dialects:

1. REFOX-style flat dump (parsed from .lef board packages), e.g. `sdffgdgh_flat_dump.json`:
   {
     "embeddedImage": "data:image/png;base64,...",
     "bbox": {"minX":..,"minY":..,"maxX":..,"maxY":..},
     "components": [{"id","name","type","value","x","y","rotation","layer",
                     "pins":[{"name","x","y","width","height","rotationDeg",
                              "shape","outline","netName"}]}],
     "outline":[], "segments":[], "vias":[], "testPads":[], "arcs":[]
   }

2. Mooxy "skilbypm v1.0" format (output of blp_convert.py on .blp BoardLens packages),
   e.g. `POCO M2_flat.json`:
   {
     "bbox": {"minX":0,"minY":0,"maxX":4200,"maxY":1440},
     "netTable":["GND",...], "netIndex":{"GND":0,...},
     "components": [{"id","name","type","value","x","y","rotation","layer",
                     "visibility","outline","pins":[{"name","x","y","width","height",
                       "rotationDeg","netIndex","netName","diode","diodeReading","outline"}]}],
     "segments":[...], "vias":[], "testPads":[], "embeddedImage":"data:image/png;base64,..."
   }

Feature list:
  - BoardView.load(path)  → unified object (schema-agnostic)
  - .nets                → {netName: [PinRef]} index ($$$N anonymous nets excluded by default)
  - .components_by_type  → ref-des prefix (C/R/L/U/D/J/Q/F/T/Z...) → components
  - search_nets(keyword) → nets matching a keyword (AVDD, DVDD, I2C, MCLK ...)
  - test_points_for_net  → best measurement points for a net (prefers testPads / fpads)
  - render_highlight(points, out_png) → board image + markers (PIL), auto board→pixel mapping
  - summary()            → quick stats for the UI / reports

Typical flow:
    bv = BoardView.load("config/boardviews/POCO_M2_flat.json")
    nets = bv.search_nets("AVDD")
    pts  = bv.test_points_for_nets(nets[:3])
    bv.render_highlight(pts, "highlight.png")
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - UI side effect only
    Image = ImageDraw = ImageFont = None


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PinRef:
    """A single pad/pin of a component, in board coordinates."""
    component_id: str
    component_name: str        # designator / reference, e.g. "J3407", "C802"
    component_type: str        # package / type string, e.g. "02011"
    pin_name: str              # "1", "2", "A1", "BGA pin name"...
    net: str                   # net this pin belongs to ("$$$N" = anonymous)
    x: float
    y: float
    width: float = 0.0
    height: float = 0.0
    rotation_deg: float = 0.0
    diode: str = ""            # skilbypm: expected diode-mode reading text (if any)
    diode_reading: str = ""    # skilbypm: measured diode reading (if any)
    from_testpad: bool = False

    def __hash__(self) -> int:  # pragma: no cover
        return hash((self.component_id, self.pin_name, self.net))


@dataclass
class ComponentRef:
    id: str
    name: str                  # designator
    type: str
    value: str
    layer: str
    x: float
    y: float
    rotation: float
    pins: List[PinRef] = field(default_factory=list)


@dataclass
class TestPoint:
    """A physical place to put a multimeter probe, with its expected value."""
    net: str
    component: str             # designator of the component whose pad to probe
    pin: str                   # pin name on that component
    x: float
    y: float
    expected_v: Optional[float] = None   # rail voltage the board should show
    label: str = ""            # e.g. "AVDD_2V8 camera rail"
    measured_v: Optional[float] = None
    notes: str = ""


def _ref_prefix(name: str) -> str:
    """'J3407' -> 'J'; 'U1001_A' -> 'U'; 'FPAD_1' -> 'FPAD'."""
    m = re.match(r"([A-Za-z]{1,4})", name or "")
    return m.group(1).upper() if m else "?"


def _decode_image(embedded_image: str) -> Optional["Image.Image"]:
    """Decode 'data:image/png;base64,....' or raw base64 into a PIL image."""
    if not embedded_image or Image is None:
        return None
    try:
        if embedded_image.startswith("data:"):
            b64 = embedded_image.split(",", 1)[1]
        else:
            b64 = embedded_image
        return Image.open(__import__("io").BytesIO(base64.b64decode(b64))).convert("RGB")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# The board view
# ---------------------------------------------------------------------------

class BoardView:
    """One board flat-dump, indexed for schematic-level diagnosis."""

    def __init__(self, source_path: Optional[Path] = None):
        self.source_path = Path(source_path) if source_path else None
        self.raw: dict = {}
        self.bbox = {"minX": 0.0, "minY": 0.0, "maxX": 0.0, "maxY": 0.0}
        self.components: List[ComponentRef] = []
        self.testpads: List[PinRef] = []
        self.net_index: Dict[str, List[PinRef]] = {}
        self.net_list: List[str] = []
        self._by_name: Dict[str, ComponentRef] = {}
        self._by_type: Dict[str, List[ComponentRef]] = {}
        self.embedded_image: Optional["Image.Image"] = None
        self.image_scale = (1.0, 1.0)  # (sx, sy) board-unit → image-pixel
        self.image_offset = (0.0, 0.0)

    # -- loading ----------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> "BoardView":
        bv = cls(path)
        with open(path, "r", encoding="utf-8-sig") as f:
            bv.raw = json.load(f)
        bv._parse_common()
        bv._parse_components()
        bv._parse_testpads()
        bv._build_indexes()
        bv._load_image()
        return bv

    @classmethod
    def from_dict(cls, data: dict) -> "BoardView":
        bv = cls()
        bv.raw = data
        bv._parse_common()
        bv._parse_components()
        bv._parse_testpads()
        bv._build_indexes()
        bv._load_image()
        return bv

    def _parse_common(self) -> None:
        bb = self.raw.get("bbox") or self.raw.get("board", {}).get("bbox") or {}
        self.bbox = {
            "minX": float(bb.get("minX", 0.0)),
            "minY": float(bb.get("minY", 0.0)),
            "maxX": float(bb.get("maxX", bb.get("width", 0.0))),
            "maxY": float(bb.get("maxY", bb.get("height", 0.0))),
        }
        self.net_list = list(self.raw.get("netTable", []))

    @staticmethod
    def _pin_net(pin: dict) -> str:
        net = pin.get("netName")
        if net is None and "net" in pin:
            net = pin["net"]
        if net is None and "netIndex" in pin and pin["netIndex"] is not None:
            # skilbypm: netIndex is position in netTable; netIndex dict maps name->idx
            net = str(pin.get("netIndex", ""))
        return str(net or "").strip()

    def _parse_components(self) -> None:
        for c in self.raw.get("components", []):
            comp_id = str(c.get("id", c.get("name", "")))
            name = str(c.get("name", comp_id))
            pins: List[PinRef] = []
            for p in c.get("pins", []):
                net = self._pin_net(p)
                is_test = bool(c.get("visibility") == 0 or "TEST" in name.upper())
                pins.append(PinRef(
                    component_id=comp_id,
                    component_name=name,
                    component_type=str(c.get("type", "")),
                    pin_name=str(p.get("name", "")),
                    net=net,
                    x=float(p.get("x", 0) or 0),
                    y=float(p.get("y", 0) or 0),
                    width=float(p.get("width", 0) or 0),
                    height=float(p.get("height", 0) or 0),
                    rotation_deg=float(p.get("rotationDeg", 0) or 0),
                    diode=str(p.get("diode", "") or ""),
                    diode_reading=str(p.get("diodeReading", "") or ""),
                    from_testpad=is_test,
                ))
            self.components.append(ComponentRef(
                id=comp_id, name=name, type=str(c.get("type", "")),
                value=str(c.get("value", "")), layer=str(c.get("layer", "Top")),
                x=float(c.get("x", 0) or 0), y=float(c.get("y", 0) or 0),
                rotation=float(c.get("rotation", 0) or 0), pins=pins,
            ))

    def _parse_testpads(self) -> None:
        for tp in self.raw.get("testPads", []):
            net = tp.get("netName") or tp.get("net") or ""
            self.testpads.append(PinRef(
                component_id="TP", component_name="TP",
                component_type="TESTPAD", pin_name=str(tp.get("name", "")),
                net=str(net), x=float(tp.get("x", 0) or 0), y=float(tp.get("y", 0) or 0),
                from_testpad=True,
            ))

    def _build_indexes(self) -> None:
        self._by_name = {}
        self._by_type = {}
        for comp in self.components:
            self._by_name.setdefault(comp.name.upper(), comp)
            self._by_type.setdefault(comp.type, []).append(comp)
            pre = _ref_prefix(comp.name)
            if pre != "?":
                self._by_type.setdefault(pre, []).append(comp)
            for pin in comp.pins:
                if pin.net:
                    self.net_index.setdefault(pin.net, []).append(pin)
        for tp in self.testpads:
            if tp.net:
                self.net_index.setdefault(tp.net, []).append(tp)

    def _load_image(self) -> None:
        img_src = self.raw.get("embeddedImage") or self.raw.get("image")
        self.embedded_image = _decode_image(img_src)
        if self.embedded_image:
            w, h = self.embedded_image.size
            bw = max(self.bbox["maxX"] - self.bbox["minX"], 1)
            bh = max(self.bbox["maxY"] - self.bbox["minY"], 1)
            self.image_scale = (w / bw, h / bh)
            self.image_offset = (self.bbox["minX"], self.bbox["minY"])

    # -- queries ----------------------------------------------------------

    @property
    def named_nets(self) -> List[str]:
        """Nets with meaningful names (anonymous $$$N dropped)."""
        return [n for n in self.net_index if n and not n.startswith("$$$")]

    def component(self, designator: str) -> Optional[ComponentRef]:
        return self._by_name.get(designator.strip().upper())

    def components_of_type(self, *prefixes: str) -> List[ComponentRef]:
        out: List[ComponentRef] = []
        for p in prefixes:
            out.extend(self._by_type.get(p.upper(), []))
        return out

    def search_nets(self, keyword: str, limit: int = 50) -> List[str]:
        k = keyword.strip().upper()
        if not k:
            return []
        hits = [n for n in self.named_nets if k in n.upper()]
        return hits[:limit]

    def pins_on_net(self, net: str) -> List[PinRef]:
        return list(self.net_index.get(net, []))

    def pins_for_keyword(self, keyword: str, limit: int = 200) -> List[PinRef]:
        """All pins whose NET matches a keyword (AVDD → AVDD_2V8, VDD_AVDD ...)."""
        k = keyword.strip().upper()
        out: List[PinRef] = []
        for net, pins in self.net_index.items():
            if net and not net.startswith("$$$") and k in net.upper():
                out.extend(pins)
        return out[:limit]

    def test_points_for_net(self, net: str, max_points: int = 4) -> List[TestPoint]:
        """Best probe points: testPads first, then FPAD/*_TEST components, then biggest pads."""
        pins = self.pins_on_net(net)
        if not pins:
            return []
        ranked = sorted(
            pins,
            key=lambda p: (
                p.from_testpad,
                "TEST" in p.component_name.upper() or p.component_name.upper().startswith("FPAD"),
                p.width * p.height,
            ),
            reverse=True,
        )
        out: List[TestPoint] = []
        for p in ranked[:max_points]:
            out.append(TestPoint(
                net=net, component=p.component_name, pin=p.pin_name,
                x=p.x, y=p.y,
                label=f"{p.component_name}.{p.pin_name}@{net}",
            ))
        return out

    def test_points_for_nets(self, nets: Iterable[str], max_per_net: int = 3) -> List[TestPoint]:
        out: List[TestPoint] = []
        for n in nets:
            out.extend(self.test_points_for_net(n, max_per_net))
        return out

    # -- rendering --------------------------------------------------------

    def to_image_px(self, x: float, y: float) -> Tuple[float, float]:
        sx, sy = self.image_scale
        ox, oy = self.image_offset
        return (x - ox) * sx, (y - oy) * sy

    def render_highlight(self, points: List[TestPoint],
                         out_png: str | Path,
                         size: Tuple[int, int] = (1400, 900)) -> str:
        """Draw the board image with markers on the given points. Returns the PNG path."""
        if Image is None:
            raise RuntimeError("Pillow (PIL) is required to render highlights")
        img = self.embedded_image
        if img is None:
            img = Image.new("RGB", size, (28, 28, 44))
        else:
            img = img.copy()
            base_w, base_h = img.size
            scale = min(size[0] / base_w, size[1] / base_h)
            new_w, new_h = int(base_w * scale), int(base_h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            canvas = Image.new("RGB", size, (28, 28, 44))
            canvas.paste(img, ((size[0] - new_w) // 2, (size[1] - new_h) // 2))
            img = canvas

        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        colors = ["#ff3b30", "#ff9500", "#34c759", "#007aff", "#af52de", "#ff2d55"]
        for i, tp in enumerate(points):
            px, py = to_canvas_wrap(self, tp.x, tp.y, img.size, True)
            color = colors[i % len(colors)]
            r = 10  # fixed marker radius (TestPoint has no pad-size info)
            draw.ellipse([px - r, py - r, px + r, py + r], outline=color, width=3)
            lbl = tp.label or tp.net
            if font:
                draw.text((px + r + 4, py - r - 4), lbl, fill=color, font=font)
        img.save(out_png)
        return str(out_png)

    # -- summaries --------------------------------------------------------

    def summary(self) -> dict:
        named = [n for n in self.net_index if not n.startswith("$$$")]
        pin_total = sum(len(c.pins) for c in self.components)
        return {
            "source": str(self.source_path or "dict"),
            "components": len(self.components),
            "pins": pin_total,
            "nets_total": len(self.net_index),
            "nets_named": len(named),
            "testpads": len(self.testpads),
            "bbox": self.bbox,
            "image": self.embedded_image.size if self.embedded_image else None,
        }


def to_canvas_wrap(bv: BoardView, x: float, y: float, size: Tuple[int, int],
                   letterbox: bool) -> Tuple[float, float]:
    """Map board coords → canvas pixel coords, mirroring render logic."""
    if bv.embedded_image is None:
        bw = max(bv.bbox["maxX"] - bv.bbox["minX"], 1)
        bh = max(bv.bbox["maxY"] - bv.bbox["minY"], 1)
        return (x - bv.bbox["minX"]) / bw * size[0], (y - bv.bbox["minY"]) / bh * size[1]
    base_w, base_h = bv.embedded_image.size
    scale = min(size[0] / base_w, size[1] / base_h)
    new_w, new_h = int(base_w * scale), int(base_h * scale)
    ox = (size[0] - new_w) / 2
    oy = (size[1] - new_h) / 2
    px, py = bv.to_image_px(x, y)
    return ox + px * scale, oy + py * scale


def main_cli() -> None:
    """python boardview_loader.py <flat.json> [net keyword] [out.png]"""
    import sys
    path = sys.argv[1]
    kw = sys.argv[2] if len(sys.argv) > 2 else "AVDD"
    out = sys.argv[3] if len(sys.argv) > 3 else "board_highlight.png"
    bv = BoardView.load(path)
    print(json.dumps(bv.summary(), indent=2))
    nets = bv.search_nets(kw)
    print(f"\nnets matching '{kw}': {nets[:20]}")
    pts = bv.test_points_for_nets(nets[:6])
    for tp in pts:
        print(f"  {tp.label:40s} ({tp.x:.1f}, {tp.y:.1f})")
    if pts and bv.embedded_image:
        bv.render_highlight(pts, out)
        print(f"\nhighlight -> {out}")


if __name__ == "__main__":
    main_cli()