#!/usr/bin/env python3
"""
Export the member mailing list for a mail merge.

Run this after ANY change to members/*.yml that could touch an address --
imports, merges, deletions, removal requests. The exported files are a snapshot;
if they are older than the member data, a mailing can reach someone who asked to
be removed.

Writes, to a directory OUTSIDE the repo:

    mailmerge.csv        Name, FirstName, Email -- feed this to the mail merge
    emails-all.txt       one address per line, each ending ";"
    emails-batch-NN.txt  the same, split for BCC sending limits
    needs-attention.csv  members whose address is missing, messy or duplicated,
                         with campus/department/title for tracking them down

The output must never land in the repo: this is every member's address in plain
text, and the repo is public. The script refuses to write inside it.

Usage:
    python scripts/export_mail_list.py                    # -> ~/Desktop/csu-directory-emails
    python scripts/export_mail_list.py --out DIR
    python scripts/export_mail_list.py --batch-size 50
"""

from __future__ import annotations
import argparse
import csv
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MEMBERS_DIR = ROOT / "members"
sys.path.insert(0, str(ROOT / "scripts"))
from build_members import campus_name  # noqa: E402  (same display names as the site)

VALID = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
FIND = re.compile(r"[A-Za-z0-9._%+-]+\s*@\s*[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ATTENTION_COLUMNS = [
    "Issue", "Name", "Campus", "Department", "Title",
    "RawEmailField", "AddressUsed", "OtherAddressesFound", "File",
]
ISSUE_ORDER = {"no usable address": 0, "repaired": 1, "duplicate record": 2}


def collect():
    """Return (recipients, attention). Recipients are de-duplicated on address."""
    good, attention = [], []
    for path in sorted(MEMBERS_DIR.glob("*.yml")):
        d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        name = (d.get("Name") or "").strip()
        raw = (d.get("Email") or "").strip()
        meta = {
            "Name": name,
            "Campus": campus_name(d.get("Campus")) or "",
            "Department": (d.get("Department") or "").strip(),
            "Title": " ".join((d.get("Title") or "").split()),
            "File": path.name,
        }
        if VALID.match(raw):
            good.append((name, raw, meta))
            continue
        # salvage an address from a messy field, but say so in the report
        found = [m.group(0).replace(" ", "") for m in FIND.finditer(raw)]
        found = [f for f in found if VALID.match(f)]
        if found:
            good.append((name, found[0], meta))
            attention.append(meta | {"Issue": "repaired", "RawEmailField": raw,
                                     "AddressUsed": found[0],
                                     "OtherAddressesFound": ", ".join(found[1:])})
        else:
            attention.append(meta | {"Issue": "no usable address", "RawEmailField": raw,
                                     "AddressUsed": "", "OtherAddressesFound": ""})

    seen, recipients = set(), []
    for name, email, meta in good:
        k = email.lower()
        if k in seen:
            attention.append(meta | {"Issue": "duplicate record", "RawEmailField": email,
                                     "AddressUsed": "", "OtherAddressesFound": ""})
            continue
        seen.add(k)
        recipients.append((name, email))
    attention.sort(key=lambda r: (ISSUE_ORDER[r["Issue"]], r["Campus"], r["Name"]))
    return recipients, attention


def write(out: Path, recipients, attention, batch_size: int):
    out.mkdir(parents=True, exist_ok=True)

    (out / "emails-all.txt").write_text(
        "".join(f"{e};\n" for _, e in recipients), encoding="utf-8")

    for stale in out.glob("emails-batch-*.txt"):
        stale.unlink()
    for i in range(0, len(recipients), batch_size):
        chunk = recipients[i:i + batch_size]
        (out / f"emails-batch-{i // batch_size + 1:02d}.txt").write_text(
            "".join(f"{e};\n" for _, e in chunk), encoding="utf-8")

    with (out / "mailmerge.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Name", "FirstName", "Email"])
        for name, email in recipients:
            w.writerow([name, name.split()[0] if name else "", email])

    with (out / "needs-attention.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ATTENTION_COLUMNS)
        w.writeheader()
        for row in attention:
            w.writerow({c: row.get(c, "") for c in ATTENTION_COLUMNS})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="~/Desktop/csu-directory-emails")
    ap.add_argument("--batch-size", type=int, default=100,
                    help="addresses per BCC batch file (default 100)")
    args = ap.parse_args()

    out = Path(args.out).expanduser().resolve()
    if ROOT == out or ROOT in out.parents:
        raise SystemExit(
            f"Refusing to write inside the repo ({out}).\n"
            "These files hold every member's address in plain text and this repo is public."
        )

    recipients, attention = collect()
    write(out, recipients, attention, args.batch_size)

    print(f"{len(recipients)} recipients -> {out}")
    print(f"  {-(-len(recipients) // args.batch_size)} batch files of {args.batch_size}")
    if attention:
        print(f"  {len(attention)} needing attention:")
        for row in attention:
            print(f"    {row['Issue']:20s} {row['Name']:24s} {row['Campus']}")
    else:
        print("  nothing needing attention")
    return 0


if __name__ == "__main__":
    sys.exit(main())
