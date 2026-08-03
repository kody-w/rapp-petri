"""A minimal RAPP agent, here so CI has something to culture.

Single file, typed metadata contract, one perform(). That is the whole shape --
anything matching it can be dropped into the dish.
"""

import json
import sys

try:
    from agents.basic_agent import BasicAgent
except ImportError:  # outside a brainstem -- stay executable anyway
    class BasicAgent:
        def __init__(self, name=None, metadata=None):
            if name:
                self.name = name
            if metadata:
                self.metadata = metadata

        def perform(self, **kwargs):
            return "Not implemented."

        def to_tool(self):
            return {"type": "function", "function": {
                "name": self.name,
                "description": self.metadata.get("description", ""),
                "parameters": self.metadata.get("parameters", {})}}


class PlateCountAgent(BasicAgent):
    def __init__(self):
        self.name = "PlateCount"
        self.metadata = {
            "name": "PlateCount",
            "description": "Report the runtime the agent is executing in and "
                           "echo back its arguments. Proves the dish is real.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Anything to echo, so a caller can tell "
                                       "one culture from another.",
                    },
                },
                "required": [],
            },
        }
        super().__init__(name=self.name, metadata=self.metadata)

    def perform(self, **kwargs):
        import platform
        return json.dumps({
            "status": "ok",
            "label": kwargs.get("label", "(none)"),
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "note": "If this reports CPython from inside a browser, the "
                    "brainstem is genuinely running -- not being simulated.",
        }, indent=2)


if __name__ == "__main__":
    _a = sys.argv[1:]
    if _a and _a[0] == "--tool":
        print(json.dumps(PlateCountAgent().to_tool(), indent=2))
    else:
        _raw = _a[0] if _a else (sys.stdin.read().strip() or "{}")
        print(PlateCountAgent().perform(**json.loads(_raw)))
