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
import os, json, yaml, shutil, sys, re, base64
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
# Area of Specialization
# ---------------------------
# Campuses name their departments differently ("Accountancy", "Accounting & Law",
# "Accounting, Law, and Finance", ...), which made the Department filter useless.
# Each department string is mapped to one or more canonical areas; a member shows
# up under every area their department touches. The Department string itself is
# untouched and still what the card displays.
#
# Ambiguous phrases are neutralized first: "construction management" should not
# make someone a Business person, "facilities planning" not an urban planner.
DECOY_SUBS = [
    (r"\b(construction|facilit\w+|natural resources?|resources?|rangeland|fire|tourism|"
     r"recreation|land|waste|emergency|project|environmental|energy|wildlife|marine|"
     r"watershed)\s+((\w+|&|,)\s+){0,2}management\b", r"\1"),
    (r"\b(facilit\w+|capital|resources?|financial|event|space|strategic)\s+planning\b", r"\1"),
]

AREA_PATTERNS = [
    ("Accounting", r"accountanc|accounting"),
    ("Agriculture", r"agricultur|agribusiness|regenerative agriculture|irrigation|"
                    r"animal science|plant science|viticultur|food (science|industry)|nutrition, food"),
    ("Anthropology", r"anthropolog"),
    ("Architecture", r"architectur"),
    ("Art & Design", r"\bart\b|\barts\b|\bdesign\b|apparel|interiors|\bcinema\b|creative arts"),
    ("Biology", r"biolog|ecology|botan|zoolog|microbiolog|molecular"),
    ("Business & Management", r"business|\bmanagement\b|marketing|entrepreneur|logistics|"
                              r"supply chain|decision science|merchandising|global innovation"),
    ("Chemical & Materials Engineering", r"chemical (and|&) material|chemical engineering"),
    ("Chemistry", r"chemistry|biochem"),
    ("City & Regional Planning", r"urban|regional planning|city planning|city (and|&) regional|"
                                 r"\bplanning\b"),
    ("Civil & Environmental Engineering", r"civil|environmental (and )?\w*\s?engineering|"
                                          r"environmental resources engineering|structural engineering"),
    ("Communication & Media", r"communicat|journalism|\bmedia\b|broadcast"),
    ("Computer Science & Information Systems", r"computer science|computing|information system|"
                                               r"information technolog|information studies|"
                                               r"informatics|data science|software|^technology$"),
    ("Construction Management", r"construction"),
    ("Economics", r"econom"),
    ("Education", r"education|teaching|teacher|liberal studies|curriculum"),
    ("Electrical & Computer Engineering", r"electrical|electronic engineering"),
    ("Energy", r"\benergy\b|\bsolar\b"),
    ("Engineering", r"engineering|mechatronic"),
    ("English & Literature", r"\benglish\b|literature|writing|linguistic"),
    ("Environmental Science", r"environment|research station"),
    ("Ethnic & Indigenous Studies", r"native american|american indian|indian tribal|africana|"
                                    r"chicana|chicano|latina|latino|asian american|ethnic studies|"
                                    r"race (&|,)|critical race|american studies"),
    ("Facilities & Operations", r"facilit|grounds|capital planning|purchasing|parking|housing|"
                                r"culinary|conference & event"),
    ("Finance", r"finance|financial|real estate"),
    ("Forestry & Natural Resources", r"forestry|rangeland|natural resource|\bfire\b|wildlife"),
    ("Gender & Sexuality Studies", r"gender|women|sexuality|feminist"),
    ("Geography", r"geograph|spatial analysis"),
    ("Geology & Earth Science", r"geolog|earth science|earth (and|,) environmental|geoscience"),
    ("Health Sciences", r"health|nursing|kinesiolog|nutrition|exercise|audiolog|gerontolog|"
                        r"human ecology"),
    ("History", r"histor"),
    ("Humanities", r"humanities|global cultures|global studies|culture and communication|"
                   r"interdisciplinary studies"),
    ("Landscape Architecture", r"landscape"),
    # "justice" alone means law, but not in "climate/environmental/social justice"
    ("Law", r"\blaw\b|legal|criminal justice|"
            r"(?<!climate )(?<!environmental )(?<!social )(?<!food )(?<!racial )"
            r"(?<!spatial )(?<!water )\bjustice\b"),
    ("Library & Information Studies", r"librar"),
    ("Marine Science", r"marine|oceanograph|aquacultur|moss landing|\bmlml\b|training ship"),
    ("Mathematics & Statistics", r"mathematic|statistic|statics"),
    ("Mechanical & Aerospace Engineering", r"mechanical|mehanical|aerospace|industrial technology|"
                                           r"manufacturing"),
    ("Meteorology & Climate Science", r"meteorolog|climate science|atmospheric"),
    ("Music & Performing Arts", r"\bmusic\b|theatre|theater|dance|performing"),
    ("Philosophy", r"philosoph|ethic"),
    ("Physics & Astronomy", r"physics|astronom|physical science"),
    ("Political Science", r"political science|\bpolitics\b|government|international relations|"
                          r"peacebuilding|conflict resolution"),
    ("Psychology", r"psycholog"),
    ("Public Administration & Policy", r"public (policy|administration|affairs)|\bpolicy\b|"
                                       r"civic engagement"),
    ("Public Health", r"public health|occupational health|epidemiolog"),
    ("Religious Studies", r"religio|theolog"),
    ("Social Work", r"social work"),
    ("Sociology", r"sociolog|social science|labor studies"),
    ("Sustainability", r"sustainab|regenerative|resilient systems|zero waste"),
    ("Tourism & Recreation", r"tourism|recreation|hospitality"),
    ("University Administration", r"academic senate|provost|academic affairs|administrative affairs|"
                                  r"office of research|sponsored programs|\bstaff\b|human resources|"
                                  r"advancement|research & innovation"),
]

_DECOY_SUBS = [(re.compile(p, re.I), r) for p, r in DECOY_SUBS]
_AREA_PATTERNS = [(area, re.compile(pat, re.I)) for area, pat in AREA_PATTERNS]

OTHER_AREA = "Other"


# ---------------------------
# Campus names
# ---------------------------
# Member files carry the short campus name ("Northridge"). The site shows the
# name each campus is actually known by, which is not uniform across the CSU --
# some go by "CSU X", some by "X State", the polytechnics by "Cal Poly X".
CAMPUS_NAMES = {
    "bakersfield": "CSU Bakersfield",
    "channel islands": "CSU Channel Islands",
    "chico": "Chico State",
    "dominguez hills": "CSU Dominguez Hills",
    "east bay": "CSU East Bay",
    "fresno state": "Fresno State",
    "fresno": "Fresno State",
    "fullerton": "CSU Fullerton",
    "humboldt": "Cal Poly Humboldt",
    "long beach": "CSU Long Beach",
    "los angeles": "Cal State LA",
    "maritime": "Cal Maritime",
    "monterey bay": "CSU Monterey Bay",
    "northridge": "CSU Northridge",
    "pomona": "Cal Poly Pomona",
    "sacramento state": "Sacramento State",
    "sacramento": "Sacramento State",
    "san bernardino": "CSU San Bernardino",
    "san bernadino": "CSU San Bernardino",   # misspelling seen in older files
    "san diego": "San Diego State University",
    "san francisco": "San Francisco State University",
    "san jose": "San José State University",
    "san luis obispo": "Cal Poly SLO",
    "san marcos": "CSU San Marcos",
    "sonoma": "Sonoma State University",
    "stanislaus": "Stanislaus State",
}


def campus_name(campus: str | None) -> str | None:
    """Short campus name from the YAML -> the name that campus goes by."""
    if not campus or not campus.strip():
        return None
    return CAMPUS_NAMES.get(campus.strip().lower(), campus.strip())


def areas_for_department(dept: str | None) -> List[str]:
    """Map a free-text department name to canonical Areas of Specialization."""
    text = (dept or "").strip()
    if not text:
        return []
    for rx, repl in _DECOY_SUBS:
        text = rx.sub(repl, text)
    areas = [area for area, rx in _AREA_PATTERNS if rx.search(text)]
    return areas or [OTHER_AREA]

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
    Areas: List[str] | None = None
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
    def Areas_List(self) -> List[str]:
        return list(self.Areas or [])

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
    # Optional per-member override of the derived areas
    "area of specialization": "Areas",
    "areas of specialization": "Areas",
    "areas": "Areas",
    "area": "Areas",
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
    text = re.sub(r"[^a-z0-9\\s\\-_]", "", text)
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

    department = norm.get("Department") or None

    # Explicit "Area of Specialization" in the YAML wins; otherwise derive it
    # from the department name.
    override = norm.get("Areas")
    if isinstance(override, str):
        override = [s.strip() for s in re.split(r"[,;]+", override) if s.strip()]
    # Sustainability staff have no department -- their job title is the only
    # thing that says what they work on, so fall back to it. Only a real match
    # counts: a title of "Professor" says nothing, and must not become "Other".
    areas = override or areas_for_department(department)
    if not areas:
        from_title = areas_for_department(norm.get("Title"))
        areas = [a for a in from_title if a != OTHER_AREA]

    m = Member(
        id=mid,
        Name=name or "Unnamed Member",
        Email=email or None,
        Campus=campus_name(norm.get("Campus")),
        College=(norm.get("College") or None),
        Department=department,
        Areas=(sorted(set(areas)) or None),
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
    <article class="card" data-text="{{ (m.Name ~ ' ' ~ (m.Department or '') ~ ' ' ~ m.Areas_List|join(' ') ~ ' ' ~ (m.College or '') ~ ' ' ~ (m.Campus or '') ~ ' ' ~ m.Research_Interests_List|join(' ')) | lower }}">
      {% if m.Photo %}<img class="thumb" src="{{ base_path }}/{{ m.Photo }}" alt="{{ m.Name }}">{% endif %}
      <h3>{{ m.Name }}</h3>
      {% if m.Title %}<div class="muted">{{ m.Title }}</div>{% endif %}
      {% if m.Department %}<div class="muted">{{ m.Department }}</div>{% endif %}
      {% if m.College or m.Campus %}<div class="muted">{{ [m.College, m.Campus]|select|join(' · ') }}</div>{% endif %}
      {% if m.Research_Interests_List %}<div>{{ m.Research_Interests_List|join(', ') }}</div>{% endif %}
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
def _encode_email(email: str | None) -> str | None:
    """Reverse, then base64. members.json is a public static file, so a plain
    address in it is free lunch for a harvester; this leaves nothing that
    matches an email pattern. The page decodes it only when the reader clicks
    the Email button. Obfuscation, not encryption -- see CLAUDE.md."""
    if not email:
        return None
    return base64.b64encode(email.strip()[::-1].encode("utf-8")).decode("ascii")


def _write_json(members: List[Member]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    data = []
    for m in members:
        row = asdict(m)
        row.pop("Email", None)          # never published in the clear
        row["Email_Enc"] = _encode_email(m.Email)
        row |= {
            "slug": m.slug,
            "Research_Interests_List": m.Research_Interests_List,
            "Areas_List": m.Areas_List,
        }
        data.append(row)
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
