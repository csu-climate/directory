# CLAUDE.md — CSU Climate Faculty Directory

Guidance for Claude Code working in this repository. Read this before making changes.

## What this project is

This repo delivers a directory at http://csu-climate.github.io/directory/ that people can use to find specialists working on climate change and sustainability issues in a particular area, or at a particular campus in the CSU system. It is a static site: no backend, no database — one YAML file per member, built into JSON + a single HTML page.

## Repo layout

- `members/*.yml` — one file per member (~984). This is the source of truth. Fields:
  `Name, Campus, College, Department, Title, Email, Research Interests, Teaching Interests,
  Sustainability Contributions, Notes` (also optional `Photo`, `Website`, `id`/`slug`, and an
  optional `Area of Specialization` override — see below). `member_template.yaml` is the blank form.
- `scripts/normalize_member_text.py` — one-shot-but-re-runnable cleanup of the three prose
  fields in `members/*.yml` (see "Prose fields" below). Not part of the build; run it by hand
  after a scrape adds new members.
- `scripts/export_mail_list.py` — exports the mailing list for a mail merge. **Re-run it after
  any change that could touch an address** — imports, merges, deletions, removal requests. The
  export is a snapshot; if it goes stale, a mailing can reach someone who asked to be removed.
  It writes outside the repo and refuses to write inside it, because the output is every
  member's address in plain text and this repo is public.
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

## Prose fields (Research / Teaching Interests, Sustainability Contributions)

The scraped data arrived Title-Cased after every comma and with proper nouns lowercased
("Applied econometrics, Political economy" / "california environmental quality act (ceqa)").
`scripts/normalize_member_text.py` rewrites these three fields to one house style:

- sentence case — only the first word of a sentence keeps its capital, so list items after the
  first are lowercase unless they are proper nouns or acronyms
- a list item that is really a sentence ("Current research examines ...") is split off with a
  period; every value ends with a period
- proper nouns, acronyms and course codes are restored from curated lists in the script
  (`PROPER_TERMS`, `ACRONYMS`), and an acronym in parentheses title-cases its expansion when
  the initials line up
- `Sustainability Contributions` keeps its internal capitals — those are mostly organization
  names — and only gets punctuation and proper-noun fixes

The same script also gives `Department` a much lighter touch, since that string is displayed
verbatim on the card. It only fixes outright errors: drops the `Representing:` prefix that
non-academic staff entries carried, lowercases the small words the title-caser capitalized
("Chemistry And Biochemistry", "Office Of Sustainability"), fixes possessives ("Women'S"), and
uppercases acronyms via explicit lists (`DEPT_ACRONYMS`, `BARE_ACRONYMS`) because "(Lecturer)"
is a real word and "reach"/"wet" are ordinary words that must be left alone.

It also moves things that are not departments out of the field: a rank in parentheses or in a
`;`-separated tail is removed and promoted into `Title` if `Title` is empty, and certifications
and committee memberships move to `Notes`. A Department that *starts* with a rank is left alone
— a dean belongs to a college, so "Dean of the College of ..." is the real answer. Values that
only name a job category ("Staff", "N/A") are cleared; those members get their areas from
`Title` instead, which is why `build_members.py` falls back to it.

The script is idempotent, only rewrites the fields that actually change (so editing one field
doesn't re-wrap its neighbours), and preserves each file apart from those scalars. It has a
`--dry-run` mode; use it, and check the report, before writing. Its guard rails matter: the
"same letters, ignoring case and punctuation" invariant is what proves nothing was lost.

Judgment calls live in the curated lists, so when a new campus's data lands, expect to add a
few proper nouns rather than to change the rules. Bare adjectives are deliberately absent from
`PROPER_TERMS` ("black bears", "southern India" and "native plant" are all correct lowercase),
which is why phrases like "Black geographies" are listed in full.

## Campus names

`members/*.yml` carry the short campus name ("Northridge"). `CAMPUS_NAMES` in
`scripts/build_members.py` maps it to the name that campus actually goes by, which is not
uniform across the CSU — "CSU Northridge", "Chico State", "Cal Poly Humboldt",
"San Diego State University", "Cal Poly SLO", "Cal State LA". The card shows that name with no
"Campus:" label. Keep the YAML short names; add mappings here instead.

Filtering goes through `Campus_Filters`, not the display name, because a campus can sit inside
another. Cal Maritime merged into Cal Poly SLO, so its members display as "Cal Poly SLO, Solano
campus" and carry *both* that and "Cal Poly SLO" as filter values: picking the parent returns
Solano too (49), picking the sub-campus returns only Solano (17), picking both returns the union
without double-counting. Add future mergers to `CAMPUS_PARENTS`.

## Email addresses

Addresses are never published in the clear. `build_members.py` reverses each address and
base64-encodes it into `Email_Enc`; the plain `Email` key is dropped from `members.json`
entirely. The card renders an **Email** button holding only the encoded string, and
`decodeEmail()` in the page swaps in a real `mailto:` link when the reader clicks it.

Decoding happens **only on click**, one address at a time — `normalize()` deliberately does not
decode, so a scraper that runs the page's JavaScript still finds no list of addresses anywhere
in memory. The cost is that search cannot match on an email address; name, interests,
department and campus all still work. Don't "fix" that by decoding at load.

Net effect: neither `site/index.html` nor `site/members.json` contains anything matching an
email pattern — verify with
`grep -oE "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}" site/members.json`, which should
return nothing.

The site contact address is handled the same way: `CONTACT_EMAIL` in `build_members.py` is
encoded into the template context, and the contact line under the filters renders a button
labelled with `CONTACT_NAME` instead of the address. Change the address there, not in the
template.

This is obfuscation, not protection. It defeats the pattern-matching harvesters that do the bulk
of address scraping; it does not stop anyone who reads this file and writes six lines of code.
**The real exposure is `members/*.yml`, which holds every address in plain text in a public
repo.** Closing that would mean encoding at rest or making the repo private — neither is done,
so treat these addresses as public.

## Crawlers

`robots.txt` is only honoured at a **domain root**. The site lives at
`csu-climate.github.io/directory/`, so crawlers read `csu-climate.github.io/robots.txt` and
ignore `/directory/robots.txt` entirely.

The live policy therefore lives in a second repo, **`csu-climate/csu-climate.github.io`**,
which GitHub Pages serves at the domain root. It governs every project page under that host,
this directory included. That repo also carries a one-page landing site, so the root is not a
404.

The `robots.txt` in *this* repo is the **canonical copy** — edit it here first, then copy it
across (the header comment differs between the two, since only one of them is live). It is not
dead weight: the build copies it to the deployment root, so it takes over automatically if the
site ever moves to its own domain.

What does work per-page is the `<meta name="robots">` tag in `templates/index.html`. It is set to
`index, follow, noarchive`: the directory is meant to be found, so indexing stays on, and
`noarchive` stops search engines serving their own cached copy.

Don't `Disallow: /members.json`. The page renders every card from that file at runtime, so
blocking it would leave search engines indexing an empty shell — the directory would stop being
findable by member name, which is the main way people arrive.

To actually apply the crawler rules, copy this repo's `robots.txt` into a repo named
`csu-climate.github.io` (GitHub Pages serves that at the domain root), or point a custom domain
at this site.

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
