#!/usr/bin/env python3
"""
Build script for a simple Faculty Directory site

- Expects one YAML file per faculty member in data/members/*.yml
- Each file can include fields like:
    name: "Dr. Ada Lovelace"
    email: "ada@university.edu"
    campus: "CSU Example"
    college: "Engineering"
    department: "Computer Science"
    research_focus: ["Compilers", "Numerical Analysis"]
    photo: "static/photos/ada.jpg"   # optional
    website: "https://adalovelace.example.edu"  # optional

- Generates a static site under ./site with:
    - /index.html (directory listing with search/filter)
    - /members/<slug>/index.html (profile pages)
    - /members.json (JSON API of all members)

Templates:
- If ./templates/index.html and ./templates/member.html exist, they'll be used.
- Otherwise, minimal built-in templates are used as a fallback.

This script intentionally focuses on a minimal, flat structure—no separate course/lesson slugs.
"""

from __future__ import annotations

import os
import json
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, List

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ---------------------------
# Configuration
# ---------------------------
ROOT = Path(__file__).parent.resolve()
DATA_DIR = ROOT / "data" / "members"
TEMPLATES_DIR = ROOT / "templates"
SITE_DIR = ROOT / "site"
MEMBERS_DIR = SITE_DIR / "members"
STATIC_DIR = ROOT / "static"  # Optional; copied recursively to site/static if present

# ---------------------------
# Helpers
# ---------------------------

def load_yaml_file(filepath: Path) -> Dict[str, Any]:
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def slugify(text: str) -> str:
    import re
    text = (text or "").strip().lower()
    # Keep alphanumerics, replace spaces and separators with '-'
    text = re.sub(r"[^a-z0-9\s-_]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "member"


@dataclass
class Member:
    id: str
    name: str
    email: str | None = None
    campus: str | None = None
    college: str | None = None
    department: str | None = None
    research_focus: List[str] | str | None = None
    photo: str | None = None
    website: str | None = None
    extras: Dict[str, Any] | None = None  # capture any other fields

    @property
    def slug(self) -> str:
        return self.id

    @property
    def email_href(self) -> str | None:
        return f"mailto:{self.email}" if self.email else None

    @property
    def research_focus_list(self) -> List[str]:
        if self.research_focus is None:
            return []
        if isinstance(self.research_focus, list):
            return [str(x) for x in self.research_focus]
        return [str(self.research_focus)]


# ---------------------------
# Template environment with graceful fallbacks
# ---------------------------
FALLBACK_INDEX_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Faculty Directory</title>
  <link rel="stylesheet" href="/static/style.css" />
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 2rem; }
    header { display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap: wrap; }
    .grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 1rem; margin-top:1rem; }
    .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 1rem; }
    .card h3 { margin: 0 0 .5rem; font-size: 1.1rem; }
    .muted { color:#6b7280; font-size:.9rem; }
    .search { padding:.6rem .8rem; border:1px solid #d1d5db; border-radius: 10px; min-width: 260px; }
    a { color:#2563eb; text-decoration:none; }
    a:hover { text-decoration:underline; }
    img.thumb { width: 100%; height: 140px; object-fit: cover; border-radius: 8px; background:#f3f4f6; }
  </style>
</head>
<body>
  <header>
    <h1>Faculty Directory</h1>
    <input id="q" class="search" placeholder="Search name, dept, campus, college, research focus" />
  </header>
  <div id="count" class="muted">{{ members|length }} members</div>

  <section class="grid" id="cards">
    {% for m in members %}
    <article class="card" data-text="{{ (m.name ~ ' ' ~ (m.department or '') ~ ' ' ~ (m.college or '') ~ ' ' ~ (m.campus or '') ~ ' ' ~ m.research_focus_list|join(' ')) | lower }}">
      {% if m.photo %}<img class="thumb" src="/{{ m.photo }}" alt="{{ m.name }}" />{% endif %}
      <h3><a href="/members/{{ m.slug }}/">{{ m.name }}</a></h3>
      {% if m.department %}<div class="muted">{{ m.department }}</div>{% endif %}
      {% if m.college or m.campus %}
        <div class="muted">{{ [m.college, m.campus]|select|join(' · ') }}</div>
      {% endif %}
      {% if m.research_focus_list %}<div>{{ m.research_focus_list|join(', ') }}</div>{% endif %}
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

FALLBACK_MEMBER_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ m.name }} · Faculty Profile</title>
  <link rel="stylesheet" href="/static/style.css" />
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 2rem; max-width: 900px; }
    .back { margin-bottom: 1rem; display:inline-block; }
    .wrap { display:grid; grid-template-columns: 180px 1fr; gap: 1.25rem; align-items: start; }
    img.portrait { width: 180px; height: 180px; object-fit: cover; border-radius: 12px; background:#f3f4f6; }
    .muted { color:#6b7280; }
    ul.tags { list-style:none; padding:0; display:flex; gap:.5rem; flex-wrap:wrap; }
    ul.tags li { background:#eef2ff; color:#3730a3; padding:.25rem .5rem; border-radius: 999px; font-size:.85rem; }
  </style>
</head>
<body>
  <a class="back" href="/">← All members</a>
  <article>
    <div class="wrap">
      {% if m.photo %}<img class="portrait" src="/{{ m.photo }}" alt="{{ m.name }}" />{% endif %}
      <header>
        <h1>{{ m.name }}</h1>
        <div class="muted">
          {{ [m.department, m.college, m.campus]|select|join(' · ') }}
        </div>
        <p>
          {% if m.email_href %}<a href="{{ m.email_href }}">{{ m.email }}</a>{% endif %}
          {% if m.website %} · <a href="{{ m.website }}" rel="noopener">Website</a>{% endif %}
        </p>
      </header>
    </div>

    {% if m.research_focus_list %}
      <h2>Research focus</h2>
      <ul class="tags">
        {% for tag in m.research_focus_list %}<li>{{ tag }}</li>{% endfor %}
      </ul>
    {% endif %}

    {% if m.extras %}
      <h2>Additional information</h2>
      <pre>{{ m.extras | tojson(indent=2) }}</pre>
    {% endif %}
  </article>
</body>
</html>
"""


def get_env() -> Environment:
    if TEMPLATES_DIR.exists():
        loader = FileSystemLoader(str(TEMPLATES_DIR))
        env = Environment(loader=loader, autoescape=select_autoescape(["html", "xml"]))
        return env
    # Fallback: construct an env and register in-memory templates
    env = Environment(autoescape=select_autoescape(["html", "xml"]))
    env.globals["fallback_index"] = FALLBACK_INDEX_TEMPLATE
    env.globals["fallback_member"] = FALLBACK_MEMBER_TEMPLATE
    return env


def render_template(env: Environment, name: str, **ctx) -> str:
    """Render template by filename or fallback constant."""
    try:
        tmpl = env.get_template(f"{name}.html")
        return tmpl.render(**ctx)
    except Exception:
        # Use fallbacks baked into this script
        if name == "index":
            return env.from_string(FALLBACK_INDEX_TEMPLATE).render(**ctx)
        elif name == "member":
            return env.from_string(FALLBACK_MEMBER_TEMPLATE).render(**ctx)
        raise


# ---------------------------
# Core building logic
# ---------------------------

def collect_members() -> List[Member]:
    if not DATA_DIR.exists():
        raise SystemExit(f"Data directory not found: {DATA_DIR}")

    members: List[Member] = []
    for yml in sorted(DATA_DIR.glob("*.yml")):
        raw = load_yaml_file(yml)
        # Prefer explicit id/slug, else derive from name, else filename stem
        preferred = raw.get("id") or raw.get("slug") or raw.get("name") or yml.stem
        member_id = slugify(str(preferred))

        known = {
            "name": raw.get("name", "Unnamed Member"),
            "email": raw.get("email"),
            "campus": raw.get("campus") or raw.get("campus_name") or raw.get("campus_dept"),
            "college": raw.get("college"),
            "department": raw.get("department") or raw.get("dept") or raw.get("campus_dept"),
            "research_focus": raw.get("research_focus") or raw.get("research") or raw.get("focus"),
            "photo": raw.get("photo"),
            "website": raw.get("website"),
        }
        # Extras: keep any keys we didn't normalize
        extras = {k: v for k, v in raw.items() if k not in set(known.keys()) | {"id", "slug"}}

        members.append(
            Member(
                id=member_id,
                extras=extras if extras else None,
                **known,
            )
        )

    # Sort by last name if possible, otherwise by name
    def sort_key(m: Member):
        parts = (m.name or "").split()
        return (parts[-1].lower() if parts else m.name.lower(), m.name.lower())

    return sorted(members, key=sort_key)


def write_json(members: List[Member]):
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    data = [asdict(m) | {"slug": m.slug, "email_href": m.email_href, "research_focus_list": m.research_focus_list} for m in members]
    (SITE_DIR / "members.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_index(env: Environment, members: List[Member]):
    html = render_template(env, "index", members=members)
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")


def write_member_pages(env: Environment, members: List[Member]):
    MEMBERS_DIR.mkdir(parents=True, exist_ok=True)
    for m in members:
        html = render_template(env, "member", m=m)
        out_dir = MEMBERS_DIR / m.slug
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(html, encoding="utf-8")


def copy_static():
    if STATIC_DIR.exists():
        dst = SITE_DIR / "static"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(STATIC_DIR, dst)


def build():
    env = get_env()
    members = collect_members()
    write_index(env, members)
    write_member_pages(env, members)
    write_json(members)
    copy_static()
    print(f"Built {len(members)} member pages to {SITE_DIR}")


if __name__ == "__main__":
    build()
