"""Fail CI if static/diagram.bpmn lacks any node id that the coordinator emits."""

import sys
import xml.etree.ElementTree as ET

REQUIRED = {"intake", "triage", "context", "vendor", "risk_gate", "comms", "closed"}


def main(path: str) -> int:
    tree = ET.parse(path)
    ids = {el.attrib.get("id") for el in tree.iter() if "id" in el.attrib}
    missing = REQUIRED - ids
    if missing:
        print(f"BPMN diagram missing required ids: {sorted(missing)}", file=sys.stderr)
        return 1
    print("BPMN ids OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
