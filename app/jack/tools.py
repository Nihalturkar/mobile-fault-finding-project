"""
Tool registry — every function Jack's brain is allowed to call.

Each tool has:
  schema   OpenAI-style function schema (Groq and Ollama both accept it)
  handler  python callable(**args) -> dict
  risky    True = needs the technician's spoken/clicked confirmation first.
           Section 3 (action tools) will use this for anything that writes to
           a phone. Knowledge tools are all read-only (risky=False).
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from app.jack.knowledge import KnowledgeBase

MAX_TOOL_RESULT_CHARS = 3500  # keep Groq free-tier token use low


@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Any]
    risky: bool = False
    label: str = ""  # short Hinglish status shown in UI, e.g. "Phone database dekh raha hoon"
    # streams=True: long-running scan. Handler also receives _emit(line), _progress(pct, msg)
    # and _stop (threading.Event) so the UI can show live output and stop it.
    streams: bool = False

    def schema(self) -> Dict[str, Any]:
        return {"type": "function",
                "function": {"name": self.name, "description": self.description,
                             "parameters": self.parameters}}


def _obj(props: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    return {"type": "object", "properties": props, "required": required}


def _s(desc: str) -> Dict[str, str]:
    return {"type": "string", "description": desc}


@dataclass
class ToolRegistry:
    tools: Dict[str, Tool] = field(default_factory=dict)

    def add(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def schemas(self) -> List[Dict[str, Any]]:
        return [t.schema() for t in self.tools.values()]

    def get(self, name: str) -> Tool:
        return self.tools.get(name)

    def run(self, name: str, args: Dict[str, Any], stream_kwargs: Dict[str, Any] = None) -> str:
        """Execute a tool and return a (truncated) JSON string for the LLM."""
        tool = self.tools.get(name)
        if tool is None:
            return json.dumps({"error": f"Unknown tool '{name}'"})
        try:
            kwargs = dict(args or {})
            if tool.streams and stream_kwargs:
                kwargs.update(stream_kwargs)
            result = tool.handler(**kwargs)
        except TypeError as e:
            result = {"error": f"Bad arguments for {name}: {e}"}
        except Exception as e:
            result = {"error": f"{name} failed: {e}"}
        text = json.dumps(result, ensure_ascii=False, default=str, separators=(",", ":"))
        if len(text) > MAX_TOOL_RESULT_CHARS:
            text = text[:MAX_TOOL_RESULT_CHARS] + ' ...[truncated]"'
        return text


def build_knowledge_tools(kb: KnowledgeBase) -> ToolRegistry:
    reg = ToolRegistry()

    reg.add(Tool(
        name="search_phone",
        description="Look up a phone model in the shop's phone database: chipset, PMIC, charging IC, "
                    "codename, EDL mode, known common faults, fastboot keys. Use whenever a model is mentioned.",
        parameters=_obj({"model": _s("Phone model, e.g. 'Redmi Note 10', 'Galaxy A15', 'Vivo Y20'")}, ["model"]),
        handler=lambda model: kb.search_phone(model),
        label="Phone database check kar raha hoon",
    ))
    reg.add(Tool(
        name="get_chipset_info",
        description="Get details of a SoC (e.g. MT6765, Helio G35, SM6225, Snapdragon 680, Exynos850, T606) "
                    "or of any IC (PMIC like MT6357, charger IC like BQ25601, DRAM regulator, touch IC): "
                    "function, voltage rails, I2C address, companion ICs.",
        parameters=_obj({"chip": _s("Chipset or IC part number / marketing name")}, ["chip"]),
        handler=lambda chip: kb.get_chipset_info(chip),
        label="Chipset/IC database dekh raha hoon",
    ))
    reg.add(Tool(
        name="search_fault_patterns",
        description="Match a symptom (dead, no charging, no network, no display, bootloop, overheating, "
                    "no audio, wifi/bt, camera, touch, battery drain, fingerprint) to known fault patterns "
                    "with possible causes, confidence %, measurement checks, test points and repair steps.",
        parameters=_obj({"symptom": _s("Symptom in the technician's words, e.g. 'dead 0.00A no charging'")},
                        ["symptom"]),
        handler=lambda symptom: kb.search_fault_patterns(symptom),
        label="Fault patterns match kar raha hoon",
    ))
    reg.add(Tool(
        name="search_community_fixes",
        description="Search real repair cases from the community database: root cause, fix, repair steps, "
                    "parts used, success rate. Filter by brand and/or chipset when known.",
        parameters=_obj({
            "query": _s("Symptom or fault, e.g. 'no charging after water damage'"),
            "brand": _s("Optional brand, e.g. Samsung, Xiaomi, Vivo"),
            "chipset": _s("Optional chipset, e.g. MT6765, SM6225"),
        }, ["query"]),
        handler=lambda query, brand="", chipset="": kb.search_community_fixes(query, brand, chipset),
        label="Community fixes search kar raha hoon",
    ))
    reg.add(Tool(
        name="search_repair_history",
        description="Search this shop's own past detections and repairs (UART/ADB scans, faults found, "
                    "healthy components). Use for 'pehle kab aaya tha', 'last scan', or recurring faults.",
        parameters=_obj({"query": _s("Device name, fault, or 'latest' for recent records")}, ["query"]),
        handler=lambda query: kb.search_repair_history("" if query.lower() in ("latest", "recent", "last") else query),
        label="Repair history dekh raha hoon",
    ))
    reg.add(Tool(
        name="get_edl_test_point",
        description="Get the EDL (9008) test point location for a Qualcomm phone model.",
        parameters=_obj({"model": _s("Phone model")}, ["model"]),
        handler=lambda model: kb.get_edl_test_point(model),
        label="EDL test point dhoondh raha hoon",
    ))
    reg.add(Tool(
        name="get_brand_tools",
        description="Get brand-specific flash tool, download-mode key combo and FRP notes for a brand.",
        parameters=_obj({"brand": _s("Brand, e.g. samsung, xiaomi, oppo")}, ["brand"]),
        handler=lambda brand: kb.get_brand_tools(brand),
        label="Brand tools dekh raha hoon",
    ))
    return reg
