#!/usr/bin/env python3
"""
Build script for the Members Directory (simple, gh-pages friendly)

- Reads one YAML per member from /members/*.yml (or .yaml)
- Normalizes fields (case-insensitive); keeps extras
- Writes:
    data/members.json           (for your existing consumers)
    site/members.json           (for the deployed site)
    site/index.html             (directory page)
    site/static/*               (copied from repo /static)
- Templates:
    If /templates/index.html exists, it's used.
    Otherwise a minimal fallback HTML is rendered.
- GitHub Pages:
    Pass BASE_PATH="/<repo>" to prefix all links/asset URLs.
"""

from __future__ import annotations
import os, json, yaml, shutil, sys, re
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Tuple
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ---------------------------
# Paths (repo-root based)
# ---------------------------
ROOT = Path(__file__).resolve().parent.parent
MEMBERS_DIR = ROOT / "members"
TEMPLATES_DIR = ROOT / "templates"
SITE_DIR = ROOT / "site"
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"

# ---------------------------
# Data model
# ---------------------------
@dataclass
class Member:
    id: str
    Name: str
    Email: str | None = None
    Campus: str | None = None
    College: str | None = None
    Department: str | None = None
    Title: str | None = None
    Research_Interests: List[str] | str | None = None
    Teaching_Interests: List[str] | str | None = None
    Sustainability_Contributions: str | None = None
    Notes: str | None = None
    Photo: str | None = None
    Website: str | None = None
    extras: Dict[str, Any] | None = None

    @property
    def slug(self) -> str:
        return self.id

    @property
    def email_href(self) -> str | None:
        return f"mailto:{self.Email}" if self.Email else None

    @property
    def Research_Interests_List(self) -> List[str]:
        v = self.Research_Interests
        if v is None:
            return []
        return v if isinstance(v, list) else [str(v)]

# Accept a variety of key spellings; map to canonical keys above
KEY_MAP = {
    "name": "Name",
    "email": "Email",
    "campus": "Campus",
    "college": "College",
    "department": "Department",
    "dept": "Department",
    "title": "Title",
    "research interests": "Research_Interests",
    "research_interests": "Research_Interests",
    "research": "Research_Interests",
    "focus": "Research_Interests",
    "teaching interests": "Teaching_Interests",
    "teaching_interests": "Teaching_Interests",
    "sustainability contributions": "Sustainability_Contributions",
    "sustainability_contributions": "Sustainability_Contributions",
    "notes": "Notes",
    "photo": "Photo",
    "image": "Photo",
    "website": "Website",
    "url": "Website",
    "id": "id",
    "slug": "id",
}

RECOMMENDED_FIELDS = ["Name", "Email", "Campus", "College", "Department", "Title"]

def _slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9\s-_]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "member"

def _load_yaml(p: Path) -> Dict[str, Any]:
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _normalize_member(d: Dict[str, Any]) -> Tuple[Member, List[str]]:
    # Case-insensitive keys → canonical keys
    norm: Dict[str, Any] = {}
    extras: Dict[str, Any] = {}
    warnings: List[str] = []

    for k, v in d.items():
        ck = KEY_MAP.get(k.strip().lower())
        if ck:
            norm[ck] = v
        else:
            extras[k] = v

    name = str(norm.get("Name", "") or "").strip()
    email = str(norm.get("Email", "") or "").strip()

    # id / slug fallback
    id_src = norm.get("id") or email or name
    mid = _slugify(str(id_src)) if id_src else _slugify(name)

    # Warn if recommended fields are missing
    for rf in RECOMMENDED_FIELDS:
        if not (str(norm.get(rf) or "").strip()):
            warnings.append(f"missing {rf}")

    m = Member(
        id=mid,
        Name=name or "Unnamed Member",
        Email=email or None,
        Campus=(norm.get("Campus") or None),
        College=(norm.get("College") or None),
        Department=(norm.get("Department") or None),
        Title=(norm.get("Title") or None),
        Research_Interests=(norm.get("Research_Interests") or None),
        Teaching_Interests=(norm.get("Teaching_Interests") or None),
        Sustainability_Contributions=(norm.get("Sustainability_Contributions") or None),
        Notes=(norm.get("Notes") or None),
        Photo=(norm.get("Photo") or None),
        Website=(norm.get("Website") or None),
        extras=(extras or None),
    )
    return m, warnings

def _collect_members() -> Tuple[List[Member], List[str]]:
    if not MEMBERS_DIR.exists():
        raise SystemExit(f"Members directory not found: {MEMBERS_DIR}")

    members: List[Member] = []
    notes: List[str] = []
    for yml in sorted(list(MEMBERS_DIR.glob("*.yml")) + list(MEMBERS_DIR.glob("*.yaml"))):
        try:
            raw = _load_yaml(yml)
            m, warns = _normalize_member(raw)
            if warns:
                notes.append(f"{yml.name}: " + "; ".join(warns))
            members.append(m)
        except Exception as e:
            notes.append(f"{yml.name}: ERROR {e}")

    # Sort by last name, fallback to Name
    def sort_key(m: Member):
        parts = (m.Name or "").split()
        return (parts[-1].lower() if parts else m.Name.lower(), m.Name.lower())

    return sorted(members, key=sort_key), notes

# ---------------------------
# Templates (Jinja) + fallbacks
# ---------------------------
FALLBACK_INDEX = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Members Directory</title>
  <link rel="stylesheet" href="{{ base_path }}/static/theme.css" />
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 2rem; }
    header { display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap: wrap; }
    .grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 1rem; margin-top:1rem; }
    .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 1rem; }
    .card h3 { margin: 0 0 .5rem; font-size: 1.1rem; }
    .muted { color:#6b7280; font-size:.9rem; }
    img.thumb { width: 100%; height: 140px; object-fit: cover; border-radius: 8px; background:#f3f4f6; }
    .search { padding:.6rem .8rem; border:1px solid #d1d5db; border-radius: 10px; min-width:260px; }
    .logo { height: 48px; }
  </style>
</head>
<body>
  <header>
    <div style="display:flex;align-items:center;gap:.75rem;">
      <img class="logo" src="{{ base_path }}/static/climate-directory-logo.png" alt="Logo">
      <h1>Members Directory</h1>
    </div>
    <input id="q" class="search" placeholder="Search name, dept, campus, college, research">
  </header>

  <div id="count" class="muted">{{ members|length }} members</div>

  <section class="grid" id="cards">
    {% for m in members %}
    <article class="card" data-text="{{ (m.Name ~ ' ' ~ (m.Department or '') ~ ' ' ~ (m.College or '') ~ ' ' ~ (m.Campus or '') ~ ' ' ~ m.Research_Interests_List|join(' ')) | lower }}">
      {% if m.Photo %}<img class="thumb" src="{{ base_path }}/{{ m.Photo }}" alt="{{ m.Name }}">{% endif %}
      <h3>{{ m.Name }}</h3>
      {% if m.Title %}<div class="muted">{{ m.Title }}</div>{% endif %}
      {% if m.Department %}<div class="muted">{{ m.Department }}</div>{% endif %}
      {% if m.College or m.Campus %}<div class="muted">{{ [m.College, m.Campus]|select|join(' · ') }}</div>{% endif %}
      {% if m.Research_Interests_List %}<div>{{ m.Research_Interests_List|join(', ') }}</div>{% endif %}
      {% if m.Email %}<div><a href="mailto:{{ m.Email }}">{{ m.Email }}</a></div>{% endif %}
    </article>
    {% endfor %}
  </section>

  <script>
    const q = document.getElementById('q');
    const cards = Array.from(document.querySelectorAll('#cards .card'));
    const count = document.getElementById('count');
    q.addEventListener('input', () => {
      const term = q.value.trim().toLowerCase();
      let visible = 0;
      cards.forEach((el) => {
        const hay = el.getAttribute('data-text');
        const show = !term || hay.includes(term);
        el.style.display = show ? '' : 'none';
        if (show) visible++;
      });
      count.textContent = `${visible} members`;
    });
  </script>
</body>
</html>
"""

def _get_env() -> Environment:
    if TEMPLATES_DIR.exists():
        return Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )
    # Fallback env (we'll render from string)
    return Environment(autoescape=select_autoescape(["html", "xml"]))

def _render_index(env: Environment, members: List[Member], base_path: str) -> str:
    try:
        tmpl = env.get_template("index.html")
        return tmpl.render(members=members, base_path=base_path)
    except Exception:
        return env.from_string(FALLBACK_INDEX).render(members=members, base_path=base_path)

# ---------------------------
# Writers
# ---------------------------
def _write_json(members: List[Member]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    data = [
        asdict(m) | {
            "slug": m.slug,
            "email_href": m.email_href,
            "Research_Interests_List": m.Research_Interests_List,
        }
        for m in members
    ]
    (DATA_DIR / "members.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    (SITE_DIR / "members.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def _write_index(env: Environment, members: List[Member], base_path: str):
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    html = _render_index(env, members, base_path)
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")

def _copy_static():
    if STATIC_DIR.exists():
        dst = SITE_DIR / "static"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(STATIC_DIR, dst)

# ---------------------------
# Entry point
# ---------------------------
def build() -> int:
    env = _get_env()
    base_path = os.getenv("BASE_PATH", "")  # e.g., "/<repo-name>" on GitHub Pages
    members, notes = _collect_members()
    _write_index(env, members, base_path)
    _write_json(members)
    _copy_static()

    print(f"✅ Built {len(members)} members into {SITE_DIR}")
    if notes:
        print("ℹ️ Notes:")
        for n in notes:
            print(" -", n)
    return 0

if __name__ == "__main__":
    sys.exit(build())
