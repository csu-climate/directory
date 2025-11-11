#!/usr/bin/env python3
"""
Build script for the Members Directory
Reads YAML files from members/ and generates data/members.json
No individual member pages are generated.
"""
import json, yaml, sys
from pathlib import Path

REQUIRED_FIELDS = ["Name","College","Department","Title","Email","Research Interests","Teaching Interests","Sustainability Contributions","Notes"]

def load_yaml(p: Path):
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def normalize_member(d: dict) -> dict:
    out = {k: (d.get(k) or "").strip() if isinstance(d.get(k), str) else (d.get(k) or "") for k in REQUIRED_FIELDS}
    # Add derived fields
    out["id"] = out["Email"] or out["Name"].lower().replace(" ", "-")
    return out

def main():
    project = Path(__file__).resolve().parents[1]
    members_dir = project / "members"
    data_dir = project / "data"
    data_dir.mkdir(exist_ok=True)
    members = []
    errors = []
    for yml in sorted(members_dir.glob("*.yml")) + sorted(members_dir.glob("*.yaml")):
        try:
            raw = load_yaml(yml)
            member = normalize_member(raw)
            # minimal validation: must have Name
            if not member["Name"]:
                errors.append(f"{yml.name}: missing Name")
                continue
            members.append(member)
        except Exception as e:
            errors.append(f"{yml.name}: {e}")
    # Write JSON
    out_path = data_dir / "members.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(members, f, indent=2, ensure_ascii=False)
    print(f"✅ Wrote {len(members)} members to {out_path.relative_to(project)}")
    if errors:
        print("⚠️ Some files had issues:")
        for e in errors:
            print(" -", e)
    return 0

if __name__ == "__main__":
    sys.exit(main())
