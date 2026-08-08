#!/usr/bin/env python3
"""
Normalize prose fields in members/*.yml.

The member data was scraped and passed through something that Title-Cased the
first word after every comma while lowercasing proper nouns elsewhere, so files
arrived looking like:

    Research Interests: 'Environmental and natural resource economics, Applied
      econometrics, Political economy, Current research examines the role of ...'

This script rewrites `Research Interests`, `Teaching Interests` and
`Sustainability Contributions` so that:

  * a list item only keeps its capital if it starts a sentence or is a proper noun
  * "And x" mid-list becomes "and x"
  * an item that is really a sentence ("Current research examines ...") is split
    off with a period and capitalized
  * proper nouns, acronyms and course codes get their capitals back
    ("california environmental quality act (ceqa)" -> "California Environmental
    Quality Act (CEQA)")
  * every value ends with a period, and stray whitespace/punctuation is cleaned up

Only those three fields are touched, and only their scalar value: the rest of
each file (key order, other fields, quoting style) is left alone.

Usage:
    python scripts/normalize_member_text.py            # rewrite files
    python scripts/normalize_member_text.py --dry-run  # print a diff-style report
"""

from __future__ import annotations
import argparse
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEMBERS_DIR = ROOT / "members"
FIELDS = ["Research Interests", "Teaching Interests", "Sustainability Contributions"]

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------
# Acronyms and initialisms, keyed by their lowercase form. Only unambiguous ones
# belong here -- bare "us", "pe", "r" and "se" are real English words and are
# deliberately absent.
ACRONYMS = {
    "gis": "GIS", "giscience": "GIScience", "gps": "GPS", "lidar": "LiDAR",
    "stem": "STEM", "steam": "STEAM", "ceqa": "CEQA", "nepa": "NEPA",
    "epa": "EPA", "nsf": "NSF", "nasa": "NASA", "noaa": "NOAA", "usda": "USDA",
    "usgs": "USGS", "ipcc": "IPCC", "leed": "LEED", "hvac": "HVAC",
    "ghg": "GHG", "ghgs": "GHGs", "co2": "CO2", "dna": "DNA", "rna": "RNA",
    "pcr": "PCR", "crispr": "CRISPR", "nmr": "NMR", "xrd": "XRD", "uav": "UAV",
    "uavs": "UAVs", "mpa": "MPA", "mpas": "MPAs", "mph": "MPH", "msw": "MSW",
    "csr": "CSR", "esg": "ESG", "ipm": "IPM", "tek": "TEK", "ai": "AI",
    "iot": "IoT", "hdr": "HDR", "dsp": "DSP", "matlab": "MATLAB",
    "arcgis": "ArcGIS", "qgis": "QGIS", "python": "Python", "phd": "PhD", "usa": "USA",
    "uc": "UC", "csu": "CSU", "sgma": "SGMA", "gsp": "GSP", "gsps": "GSPs",
    "pv": "PV", "lca": "LCA", "pfas": "PFAS", "voc": "VOC", "vocs": "VOCs",
    "ev": "EV", "evs": "EVs", "ph": "pH", "sts": "STS", "iscor": "ISCOR",
    "sdsu": "SDSU", "csun": "CSUN", "csub": "CSUB", "sfsu": "SFSU",
    "csusm": "CSUSM", "ssu": "SSU", "cahss": "CAHSS", "aashe": "AASHE",
    "ieee": "IEEE", "ii": "II", "iii": "III", "cad": "CAD", "cfd": "CFD",
    "roi": "ROI", "gdp": "GDP", "hiv": "HIV", "covid-19": "COVID-19",
    "k-12": "K-12", "x-ray": "X-ray", "3d": "3D", "2d": "2D",
    # course-catalog prefixes
    "anth": "ANTH", "biol": "BIOL", "geog": "GEOG", "crim": "CRIM",
    "enst": "ENST", "soc": "SOC", "chem": "CHEM", "phys": "PHYS",
    "geol": "GEOL", "envs": "ENVS", "wshd": "WSHD",
}

# Proper nouns restored anywhere they appear, longest phrase first so that
# "san diego state university" wins over "san diego".
PROPER_TERMS = [
    # institutions
    "California State University", "Cal Poly Humboldt", "Cal Poly Pomona",
    "Cal Poly San Luis Obispo", "Cal Poly", "Cal Maritime",
    "San Diego State University", "San Francisco State University",
    "San Jose State University", "Sonoma State University", "Stanislaus State",
    "Sacramento State", "Fresno State", "Chico State", "Moss Landing Marine Laboratories",
    "Humboldt Marine Lab", "Trinidad Rancheria",
    # named acts, programs, agreements
    "California Environmental Quality Act", "National Environmental Policy Act",
    "Endangered Species Act", "Clean Water Act", "Clean Air Act",
    "Sustainable Groundwater Management Act", "Paris Agreement", "Green New Deal",
    "Title IX", "Fulbright",
    # places
    "California", "Baja California", "Central Valley", "San Joaquin Valley",
    "Salinas Valley", "Imperial Valley", "Sierra Nevada", "Central Coast",
    "Bay Area", "Monterey Bay", "Humboldt Bay", "Lake Tahoe", "Klamath",
    "Colorado River", "Mojave", "Yosemite", "Channel Islands", "Santa Barbara",
    "Santa Cruz", "Santa Rosa", "Los Angeles", "San Francisco", "San Diego",
    "San Jose", "San Luis Obispo", "Long Beach", "Orange County", "Monterey County",
    "Sacramento", "Fresno", "Sonoma", "Napa", "Humboldt", "Pacific", "Atlantic",
    "Arctic", "Antarctica", "Antarctic", "Amazon", "Africa", "Asia", "Europe",
    "North America", "South America", "Latin America", "Central America",
    "Mesoamerica", "Mediterranean", "Caribbean", "Australia", "Borneo", "Brazil",
    "Canada", "China", "Ecuador", "India", "Indonesia", "Japan", "Kenya", "Mexico",
    "Mozambique", "Nigeria", "Peru", "Rwanda", "Vietnam", "New York", "New Zealand",
    "Great Basin", "United States", "Puerto Rico", "Hawaii", "Italy",
    "Arizona", "Venice", "Salton Sea", "UC Davis",
    # peoples, languages, demonyms
    "African American", "African Americans", "Asian American", "Asian Americans",
    "Native American", "Native Americans", "American Indian", "Pacific Islander",
    "American", "Americans", "African", "Asian", "European", "Mexican", "Brazilian",
    "Chinese", "Japanese", "Filipino", "Hmong", "Chicano", "Chicana", "Chicanx",
    "Latino", "Latina", "Latinx", "Hispanic", "Indigenous", "Yurok", "Karuk",
    "Wiyot", "Maya", "Aztec", "English", "Spanish", "French", "German",
    "Portuguese", "Global South", "Global North",
    # people
    "Kant", "Nietzsche", "Heidegger", "Levinas", "Foucault", "Marx", "Darwin",
    "Shakespeare", "Moby Dick", "Bayesian", "Monte Carlo", "Derrida", "Einstein",
    # phrases only -- the bare adjectives stay lowercase ("black bears",
    # "southern India", "native plant" are all correct as-is)
    "Southern California", "Northern California", "Black geographies",
    "Black studies", "Black feminism", "Black feminist", "Native nations",
    "American Indians", "US-Latin",
]
# Longest first so multi-word phrases are matched before their fragments.
PROPER_TERMS.sort(key=len, reverse=True)

# Single-word proper nouns keep their capital wherever they appear. Multi-word
# phrases are checked as whole prefixes instead, so "Global South" stays capital
# but "global environmental policy" does not.
SINGLE_PROPER = {t.lower() for t in PROPER_TERMS if " " not in t} | set(ACRONYMS)
MULTI_PROPER = [t for t in PROPER_TERMS if " " in t]

# An item starting with one of these is a continuation of the previous clause,
# never a new sentence -- always lowercased.
CONTINUATIONS = {
    "and", "or", "but", "with", "while", "which", "including", "especially",
    "such", "as", "where", "when", "focusing", "particularly", "mainly",
    "primarily", "principally", "regardless", "along", "through", "to", "in",
    "on", "at", "for", "by", "from", "using", "based", "etc", "etc.",
}

# A short opening phrase starting with one of these is a fronted adverbial
# ("As a Fulbright Scholar, she ..."), not a finished sentence.
SUBORDINATORS = {
    "as", "with", "in", "during", "after", "before", "through", "throughout",
    "while", "following", "since", "because", "although", "though", "by", "at",
    "on", "for", "from", "upon", "under", "within", "across", "among", "via",
    "when", "if", "despite", "besides", "beyond", "alongside", "amid",
}

# An item starting with one of these *and* containing a finite verb is really a
# new sentence that lost its period.
SENTENCE_LEADERS = {
    "he", "she", "they", "his", "her", "their", "current", "currently",
    "previously", "recent", "recently", "also", "additionally", "this", "it",
    "teaches", "explores", "focuses", "serves", "advises", "supervises",
    "specializes", "collaborates", "works", "wants", "leads",
    "studies", "investigates", "develops", "created", "published", "received",
    "conducts", "advocates", "promotes", "participated", "organized", "mentors",
    "contributes", "contributed", "supports", "supported", "coordinates",
    "directs", "founded", "co-founded", "authored", "co-authored", "wrote",
}
FINITE_VERB = re.compile(
    r"\b(is|are|was|were|has|have|had|includes?|involves?|examines?|explores?|"
    r"focuses|teaches|serves|advises|supervises|specializes|collaborates|works?|"
    r"wants?|aims?|seeks?|conducts?|advocates?|promotes?|participated|organized|"
    r"co-organized|leads?|studies|investigates?|uses?|develops?|created|published|"
    r"received|mentors?|contributes?|contributed|supports?|supported|coordinates?|"
    r"directs?|founded|co-founded|authored|co-authored|wrote|highlighted|"
    r"advanced|advances|established|designed|built|earned|holds?)\b", re.I)

# Misspellings actually present in the corpus, found by spell-checking every
# word against the system dictionary and hand-checking the candidates. Nearly
# all "unknown" words turned out to be proper nouns, acronyms or technical
# vocabulary; these are the real ones.
TYPOS = {
    "critisism": "criticism",       # brian-cozen
    "pacfic": "Pacific",            # steven-james
    "sistainable": "sustainable",   # susan-cholette
    "biodivestion": "biodigestion", # laura-gonzalez-ospina
    "transbord": "transborder",     # vinod-sasidharan (spelled correctly later in the same file)
    "archeology": "archaeology",    # steven-james, mixed with "Archaeology" in the same field
    "fullbright": "Fulbright",      # cheryl-logan
}

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-\.]*")


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------
def _fix_typos(text: str) -> str:
    def sub(m):
        w = m.group(0)
        rep = TYPOS.get(w.lower())
        if not rep:
            return w
        return rep.capitalize() if w[0].isupper() else rep
    return re.sub(r"[A-Za-z]+", sub, text)


def _restore_proper_terms(text: str) -> str:
    for term in PROPER_TERMS:
        pattern = re.compile(r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b", re.I)
        text = pattern.sub(lambda m, t=term: t, text)
    return text


def _restore_acronyms(text: str) -> str:
    def sub(m):
        w = m.group(0)
        rep = ACRONYMS.get(w.lower())
        return rep if rep else w
    return re.sub(r"[A-Za-z0-9][A-Za-z0-9\-]*", sub, text)


def _titlecase_acronym_expansions(text: str) -> str:
    """"california environmental quality act (ceqa)" -> "California Environmental
    Quality Act (CEQA)". Only fires when the initials actually line up with the
    words in front of the parenthesis, so it never guesses."""
    SKIP = {"of", "and", "the", "for", "in", "on", "to", "a", "an", "&"}
    out = text
    pos = 0
    while True:
        m = re.compile(r"\(([A-Za-z]{2,8})\)").search(out, pos)
        if not m:
            return out
        acro = m.group(1)
        letters = [c.lower() for c in acro if c.isalpha()]
        words = list(WORD_RE.finditer(out[: m.start()]))
        picked, idx, ok = [], len(words) - 1, True
        for letter in reversed(letters):
            while idx >= 0 and words[idx].group(0).lower() in SKIP:
                idx -= 1
            if idx < 0 or words[idx].group(0)[0].lower() != letter:
                ok = False
                break
            picked.append(idx)
            idx -= 1
        if not ok or not picked:
            pos = m.end()
            continue
        chars = list(out)
        for i in picked:
            w = words[i]
            chars[w.start()] = chars[w.start()].upper()
        out = "".join(chars)
        out = out[: m.start()] + "(" + acro.upper() + ")" + out[m.end():]
        pos = m.start() + len(acro) + 2


def _split_sentences(value: str):
    """Split on sentence-ending periods, keeping the delimiter off."""
    parts = re.split(r"(?<=[.!?])\s+", value.strip())
    return [p for p in parts if p.strip()]


def _lead_word(item: str) -> str:
    m = WORD_RE.match(item.strip())
    return m.group(0).lower().rstrip(".") if m else ""


def _lower_first(item: str) -> str:
    m = WORD_RE.match(item)
    if not m:
        return item
    w = m.group(0)
    if w.lower() == "us":
        return "US" + item[2:]  # a list item never starts with the pronoun "us"
    if w == "A":
        return "a" + item[1:]   # the article, not an initialism
    if w.lower().rstrip(".") in SINGLE_PROPER or w.isupper():
        return item  # single-word proper noun or acronym
    if len(w) > 1 and w[1:].lower() != w[1:]:
        return item  # CamelCase like "GIScience"
    if any(item.startswith(t) for t in MULTI_PROPER):
        return item  # "Latin America ...", "Global South ..."
    return w[0].lower() + item[1:]


def _flatten_titlecase(item: str) -> str:
    """Some members wrote their interests in Title Case ("Power Systems
    Distribution"). Lowercasing only the leading word would leave a mongrel
    ("power Systems Distribution"), so drop the whole item to sentence case --
    unless it holds a known proper-noun phrase, which stays as it is."""
    words = item.split()
    if len(words) < 2:
        return item
    if any(term in item for term in MULTI_PROPER):
        return item
    alpha = [w for w in words if w[:1].isalpha()]
    capped = [w for w in alpha if w[:1].isupper()]
    if len(alpha) < 2 or len(capped) * 2 < len(alpha):
        return item  # ordinary sentence case already

    def flatten(w: str) -> str:
        bare = w.strip(".,;:()&/").lower()
        if bare in SINGLE_PROPER or w.strip(".,;:()").isupper():
            return w
        if "-" in w:  # "Human-Centered" -> "human-centered", "X-ray" kept above
            return "-".join(
                p if p.strip(".,;:()").lower() in SINGLE_PROPER or p.isupper()
                else (p[0].lower() + p[1:] if p[:1].isupper() else p)
                for p in w.split("-")
            )
        if len(w) > 1 and w[1:].lower() != w[1:]:
            return w  # internal capitals: "GIScience"
        return w[0].lower() + w[1:] if w[:1].isupper() else w

    return " ".join(flatten(w) for w in words)


def _upper_first(item: str) -> str:
    m = WORD_RE.match(item)
    if not m:
        return item
    return item[: m.start()] + item[m.start()].upper() + item[m.start() + 1:]


def normalize_value(value: str, listy: bool) -> str:
    """`listy` marks the comma-separated interest fields, where each item after
    the first should start lowercase."""
    # A handful of members list one interest per line instead of comma-separating
    # them; fold those into the same list shape as everyone else.
    text = re.sub(r"\s*\n+\s*", ", ", value.strip())
    text = " ".join(text.split())
    text = re.sub(r",\s*,", ",", text)
    if not text:
        return ""

    text = _fix_typos(text)
    text = _titlecase_acronym_expansions(text)
    text = _restore_proper_terms(text)
    text = _restore_acronyms(text)

    # tidy punctuation
    text = re.sub(r"\s+([,;.])", r"\1", text)
    text = re.sub(r",\s*\.", ".", text)
    # "...policy., Serves as..." -> "...policy. Serves as...". The 4+ letter
    # guard keeps real abbreviations ("etc.,", "U.S.,", "Inc.,") intact.
    text = re.sub(r"([a-z]{4,})\.\s*,\s*", r"\1. ", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"\s{2,}", " ", text)

    sentences = _split_sentences(text)
    out_sentences = []
    for sent in sentences:
        trailing = "." if sent.rstrip().endswith((".", "!", "?")) else ""
        body = sent.rstrip(".!? ").strip()
        if not body:
            continue
        items = re.split(r"\s*,\s*", body)
        rebuilt = [_upper_first(_flatten_titlecase(items[0])) if listy else items[0]]
        for item in items[1:]:
            if not item:
                continue
            lead = _lead_word(item)
            words = item.split()
            # Don't split off a sentence when what precedes it is a stub like
            # "Broadly," or a fronted adverbial like "As a Fulbright Scholar,"
            # -- in both cases the clause that follows completes that sentence
            # rather than starting a new one.
            preceding = " ".join(str(x) for x in rebuilt)
            preceding_words = len(preceding.split())
            fronted = (
                preceding_words <= 8
                and preceding.split()[0].lower().strip(",") in SUBORDINATORS
            ) if preceding.split() else False
            starts_sentence = (
                lead in SENTENCE_LEADERS
                and lead not in CONTINUATIONS
                and len(words) >= 5
                and preceding_words >= 4
                and not fronted
                and FINITE_VERB.search(item) is not None
            )
            if starts_sentence:
                rebuilt.append(("\0", _upper_first(item)))  # marker: new sentence
            elif listy:
                rebuilt.append(_lower_first(_flatten_titlecase(item)))
            else:
                rebuilt.append(item)
        # stitch items back, turning markers into sentence breaks
        chunk = ""
        for part in rebuilt:
            if isinstance(part, tuple):
                chunk = chunk.rstrip(", ") + ". " + part[1]
            else:
                chunk = part if not chunk else chunk + ", " + part
        out_sentences.append(_upper_first(chunk).rstrip(", ") + (trailing or "."))

    result = " ".join(out_sentences).strip()
    if result and not result.endswith((".", "!", "?")):
        result += "."
    result = re.sub(r"\s+([,;.])", r"\1", result)
    return result


# ---------------------------------------------------------------------------
# Surgical YAML rewriting
# ---------------------------------------------------------------------------
KEY_RE = {f: re.compile(rf"^{re.escape(f)}:[ \t]*(.*)$", re.M) for f in FIELDS}


def _quote_closed(text: str, q: str) -> bool:
    """Is this quoted scalar terminated on this line? Handles '' escapes."""
    body = text[1:] if text.startswith(q) else text
    i = 0
    while i < len(body):
        if body[i] == q:
            if q == "'" and i + 1 < len(body) and body[i + 1] == q:
                i += 2
                continue
            return True
        i += 1
    return False


def _read_scalar(lines, start):
    """Return (raw_value, end_index) for the scalar beginning on lines[start].

    Quoted scalars may run across blank lines -- YAML folds a single break into
    a space and a blank line into a newline -- so those are followed to their
    closing quote rather than stopping at the first empty line.
    """
    first = lines[start].split(":", 1)[1].strip()
    collected = [first]
    i = start + 1
    open_quote = None
    if first[:1] in ("'", '"') and not _quote_closed(first, first[0]):
        open_quote = first[0]

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if open_quote:
            collected.append("\n" if not stripped else stripped)
            if stripped and _quote_closed(stripped + " ", open_quote):
                i += 1
                break
            i += 1
            continue
        if not stripped or not line.startswith((" ", "\t")):
            break
        collected.append(stripped)
        i += 1

    raw = ""
    for part in collected:
        if part == "\n":
            raw = raw.rstrip() + "\n"
        elif raw.endswith("\n") or not raw:
            raw += part
        else:
            raw += " " + part
    return raw, i


def _unquote(raw: str) -> tuple[str, str]:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1].replace("''", "'"), "single"
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        body = raw[1:-1].replace('\\"', '"')
        body = body.replace("\\n", "\n").replace("\\t", " ")
        return body, "double"
    return raw, "plain"


def _emit(key: str, value: str, style: str) -> list[str]:
    needs_quote = (
        style in ("single", "double")
        or not value
        or re.search(r":\s|\s#|^[-?:,\[\]{}#&*!|>'\"%@`]", value)
    )
    if needs_quote:
        body = "'" + value.replace("'", "''") + "'"
    else:
        body = value
    wrapped = textwrap.wrap(
        f"{key}: {body}", width=92, subsequent_indent="  ",
        break_long_words=False, break_on_hyphens=False,
    )
    return wrapped or [f"{key}: {body}"]


def process_file(path: Path, dry_run: bool):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    changes = []
    i = 0
    out = []
    while i < len(lines):
        line = lines[i]
        matched = None
        for field in FIELDS:
            if line.startswith(field + ":"):
                matched = field
                break
        if not matched:
            out.append(line)
            i += 1
            continue
        raw, end = _read_scalar(lines, i)
        value, style = _unquote(raw)
        listy = matched in ("Research Interests", "Teaching Interests")
        new_value = normalize_value(value, listy=listy)
        if new_value != value:
            changes.append((matched, value, new_value))
        out.extend(_emit(matched, new_value, style if new_value else "single"))
        i = end
    new_text = "\n".join(out) + "\n"
    if changes and not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return changes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="only report N changed files")
    ap.add_argument("--files", nargs="*", help="specific files instead of all members")
    args = ap.parse_args()

    paths = [Path(f) for f in args.files] if args.files else sorted(MEMBERS_DIR.glob("*.yml"))
    changed_files = 0
    changed_fields = 0
    shown = 0
    for p in paths:
        changes = process_file(p, args.dry_run)
        if not changes:
            continue
        changed_files += 1
        changed_fields += len(changes)
        if args.limit == 0 or shown < args.limit:
            shown += 1
            print(f"\n=== {p.name}")
            for field, old, new in changes:
                print(f"  [{field}]\n  -  {old}\n  +  {new}")
    print(f"\n{changed_files} files changed, {changed_fields} fields rewritten "
          f"({'dry run' if args.dry_run else 'written'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
