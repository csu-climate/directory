# CLAUDE.md — CSU Climate Faculty Directory

Guidance for Claude Code working in this repository. Read this before making changes.

## What this project is

This repo delivers a directory at http://csu-climate.github.io/directory/ that people can use to find specialists working on climate change and sustainability issues in a particular area, or at a particular campus in the CSU system. It is a static site: no backend, no database — one YAML file per member, built into JSON + a single HTML page.

## Repo layout

- `members/*.yml` — one file per member (~984). This is the source of truth. Fields:
  `Name, Campus, College, Department, Title, Email, Research Interests, Teaching Interests,
  Sustainability Contributions, Notes` (also optional `Photo`, `Website`, `id`/`slug`, and an
  optional `Area of Specialization` override — see below). `member_template.yaml` is the blank form.
- `scripts/build_members.py` — the whole build. Reads `members/*.yml`, normalizes keys
  (case-insensitive via `KEY_MAP`, unknown keys are preserved under `extras`), derives Areas of
  Specialization, renders `templates/index.html`, and writes `site/index.html`,
  `site/members.json`, `data/members.json`, and `site/static/`.
- `templates/index.html` — the actual directory page. All search/filter/render logic is plain JS
  inside this file; it fetches `members.json` at runtime, so it is *data-driven*, not Jinja-rendered
  per member. The Jinja parts are only `{{ base_path }}`.
- `scripts/build_members.py::FALLBACK_INDEX` — a minimal page used only if `templates/index.html`
  fails to render. Keep it roughly in sync but don't invest in it.
- `static/theme.css` — all styling, incl. light/dark. Card classes: `.lesson-card`,
  `.lesson-title`, `.department-line`, `.lesson-meta`, `.meta-item`.
- `templates/member.html`, `templates/lesson.html`, `templates/platforms/`, `index*.html.disabled`,
  `scripts/build_members.py.old` — dead weight from an earlier lessons site. Not built, not served.
- `.github/workflows/build-members.yml` — on push to `main`: validates every YAML parses, runs the
  build with `BASE_PATH=/directory`, then deploys `site/` to the `gh-pages` branch.
- `site/` is gitignored (build output). `data/members.json` is tracked but stale sample data — the
  build overwrites it locally, so `git checkout -- data/members.json` after building unless you
  actually mean to refresh it.

## Area of Specialization (the Department problem)

Campuses name departments inconsistently — "Accountancy", "Accounting & Law", "Accounting &
Finance", "Accounting, Law, and Finance" were four separate entries in the old Department filter,
which made it useless (280 distinct department strings across 984 members). The site now filters on
**Area of Specialization** instead:

- `AREA_PATTERNS` in `scripts/build_members.py` maps a department string to one or more canonical
  areas via regex. A department can (and usually should) yield several areas — someone in
  "Accounting, Law, and Finance" appears under Accounting, Law, *and* Finance.
- `DECOY_SUBS` runs first to neutralize ambiguous phrases before matching, so "construction
  management" doesn't read as Business and "facilities planning" doesn't read as urban planning.
  Add here when a new department name creates a false positive.
- Anything matching nothing falls into `OTHER_AREA` ("Other"); members with no Department get no
  areas and only appear under "All Areas". Currently ~51 areas, nothing in "Other".
- A member YAML may set `Area of Specialization:` (comma/semicolon separated, or a list) to
  override the derived areas entirely.
- **The Department string is never rewritten** — the results card still shows the member's real
  department. Areas only drive the filter and search.

When editing `AREA_PATTERNS`, re-run the build and diff the derived areas before committing; it's
easy to add a pattern that quietly swallows unrelated departments.

## Coding conventions

- Python 3.12, stdlib + `pyyaml` + `jinja2` only. No new dependencies without a good reason —
  the CI workflow pip-installs them by name.
- Front-end is vanilla JS in `templates/index.html`. No build step, no framework, no CDN scripts.
- Member data flows Python → `members.json` → JS. Derive things in Python (single source of
  truth); keep the JS to filtering and rendering.
- The JS `normalize()` in `templates/index.html` maps both `Snake_Case` (from the dataclass) and
  `Title Case` key spellings — keep new fields working under both.

## Local development

`pyyaml`/`jinja2` are not in the system Python. Use a venv:

```
python3 -m venv .venv && .venv/bin/pip install pyyaml jinja2
.venv/bin/python scripts/build_members.py      # writes site/
cd site && python3 -m http.server 8777         # then open http://localhost:8777
```

The page fetches `members.json` at runtime, so opening `site/index.html` via `file://` will not
work — serve it. For a quick visual check without a browser session:
`"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu
--virtual-time-budget=8000 --screenshot=shot.png http://localhost:8777/index.html`

## Workflow

- **Say when context pressure is likely to start degrading the work — before it does.**
- For any command preceded by "[short]", make the response as **short and succinct as possible**
  without losing clarity.

## Validation rules

- Every `members/*.yml` must parse as YAML — CI fails the build otherwise.
- The build warns (does not fail) on missing `Name, Email, Campus, College, Department, Title`.
  Many members are legitimately missing some; ~37 have no Department at all.
- CI requires `site/index.html` and `site/members.json` to exist after the build.
