#!/usr/bin/env python3
"""One-off migration: parse the accordion HTML embedded in the newer Google Site
(sites.google.com/site/soumya3sankar/organization/ag-seminar-uu, downloaded to
/tmp/agsem.html) into one YAML file per block under data/blocks/.

Entries the heuristics cannot fully classify are written with a 'REVIEW'
marker and listed on stderr for a manual pass.
"""

import html
import json
import re
import sys
import textwrap
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

SRC = Path("/tmp/agsem.html")
OUT = Path(__file__).resolve().parent.parent / "data" / "blocks"

MONTHS = {m: i + 1 for i, m in enumerate(
    "January February March April May June July August September October November December".split())}

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse_long_date(s):
    m = re.match(r"(\w+) (\d{1,2}), (\d{4})", s.strip())
    return date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))


def infer_year(month, day, start, end):
    """Pick the year (block start's or end's) putting the date nearest the block."""
    best = None
    for y in {start.year, end.year}:
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        dist = max((start - d).days, (d - end).days, 0)
        if best is None or dist < best[0]:
            best = (dist, d)
    return best[1]


def is_one_paren_group(s):
    """True when s is a single balanced (...) group, e.g. '(no talk: x)'."""
    depth = 0
    for i, c in enumerate(s):
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i == len(s) - 1
    return False


def split_on_toplevel_colon(s):
    depth = 0
    for i, c in enumerate(s):
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == ":" and depth == 0:
            return s[:i], s[i + 1:]
    return s, ""


def yaml_str(s):
    return json.dumps(s, ensure_ascii=False)


def emit_talk(t):
    lines = [f"  - date: {t['date'].isoformat()}"]
    for key in ("time", "speaker", "affiliation", "title"):
        if t.get(key):
            lines.append(f"    {key}: {yaml_str(t[key])}")
    if t.get("abstract"):
        lines.append("    abstract: >-")
        for line in textwrap.wrap(t["abstract"], width=88,
                                  break_on_hyphens=False, break_long_words=False):
            lines.append(f"      {line}")
    if t.get("room"):
        lines.append(f"    room: {yaml_str(t['room'])}")
    if t.get("note"):
        lines.append(f"    note: {yaml_str(t['note'])}")
    if t.get("review"):
        lines.append(f"    # REVIEW: {t['review']}")
    return "\n".join(lines)


def parse_header(header, start, end):
    """Parse a panel header like
    'April 23, 15.30 (Note different day and time): Philip Engel (UIC)'."""
    talk = {}
    review = []
    prefix, rest = split_on_toplevel_colon(header)
    rest = rest.strip()

    m = re.match(r"(\w+)\s+(\d{1,2})\s*(.*)", prefix.strip())
    talk["date"] = infer_year(MONTHS[m.group(1)], int(m.group(2)), start, end)
    extra = m.group(3).strip().lstrip(",").strip()

    # time and/or remarks living between the date and the colon
    for paren in re.findall(r"\(([^)]*)\)", extra):
        if re.search(r"\d|a\.?\s?m|p\.?\s?m", paren):
            talk["time"] = paren.strip()
        elif not re.match(r"(?i)note different", paren):
            talk["note"] = paren.strip()
    bare = re.sub(r"\([^)]*\)", "", extra).strip().strip(",").strip()
    if bare:
        if re.match(r"[\d.]+$", bare):
            talk["time"] = bare
        else:
            review.append(f"unparsed before colon: {bare!r}")

    # classification of what follows the colon
    m = re.match(r"(?i)\(\s*(?P<flag>(?:no talk|cancelled)[^)]*)\)\s*(?P<rem>.+)$", rest)
    if m:
        # e.g. "(Cancelled) Victoria Hoskins (Radboud University Nijmegen)"
        talk["note"] = m.group("flag").strip().lower()
        rest = m.group("rem").strip()
    elif re.match(r"(?i)\(?\s*(no talk|cancelled)", rest):
        note = rest
        if note.startswith("(") and note.endswith(")") and is_one_paren_group(note):
            note = note[1:-1].strip()
        talk["note"] = note
        rest = ""

    sl = re.match(r"(?i)special lecture by\s+(?P<name>[^()]+?)\s*\((?P<aff>[^)]+)\)\s*(?P<trail>.*)$", rest)
    ls = re.match(r"(?i)lecture series by\s+(?P<name>.+?)\s*-\s*(?P<part>[IVX]+)\s*\((?P<aff>[^)]+)\)\s*$", rest)
    sp = re.match(r"(?P<name>[^()]+?)\s*\((?P<aff>[^)]+)\)\s*(?P<trail>.*)$", rest)
    if not rest:
        pass
    elif rest.upper() == "TBA":
        talk["note"] = "TBA"
    elif sl:
        talk["speaker"] = sl.group("name").strip()
        talk["affiliation"] = sl.group("aff").strip()
        trail = sl.group("trail").strip(" ,")
        talk["note"] = ("special lecture " + trail).strip() if trail else "special lecture"
    elif ls:
        talk["speaker"] = ls.group("name").strip()
        talk["affiliation"] = ls.group("aff").strip()
        talk["note"] = f"lecture series, part {ls.group('part')}"
    elif sp and not re.match(r"(?i)(short talks|day \d)", rest):
        talk["speaker"] = sp.group("name").strip()
        talk["affiliation"] = sp.group("aff").strip()
        if sp.group("trail").strip(" ,"):
            talk["note"] = sp.group("trail").strip(" ,")
    else:
        # workshops, short-talk days, other irregular entries
        talk["note"] = rest
        review.append("irregular entry kept as note")

    if review:
        talk["review"] = "; ".join(review)
    return talk


def parse_body(body, talk):
    body = re.sub(r"<br\s*/?>", "\n", body)

    def grab(field):
        m = re.search(rf"<strong>\s*{field}:\s*</strong>(.*?)(?=<strong>|$)", body, re.S)
        return clean(m.group(1)) if m else ""

    title = grab("Title")
    if title and title.upper() not in ("TBA", "N/A"):
        talk["title"] = title
    abstract = grab("Abstract")
    if abstract and abstract.upper() not in ("TBA", "N/A"):
        talk["abstract"] = abstract
    loc = grab("Location")
    loc = re.sub(r"(?i)\(note different location\)", "", loc).strip()
    if loc:
        talk["room"] = loc
    return talk


def main():
    content = SRC.read_text(encoding="utf-8", errors="ignore")
    content = html.unescape(html.unescape(content))
    # name typos on the source page that entity-decoding cannot repair
    content = content.replace("Szendröi", "Szendrői")

    blocks = []
    button_re = re.compile(
        r'<button type="button1"[^>]*>([^<]*)</button>')
    matches = list(button_re.finditer(content))
    for i, m in enumerate(matches):
        label = m.group(1).strip()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        chunk = content[m.end():end_pos]

        bm = re.match(r"\(?Block (I+V?|IV)\)?:?\s*(\w+ \d{1,2}, \d{4}) to (\w+ \d{1,2}, \d{4})", label)
        if not bm:
            print(f"SKIP button: {label!r}", file=sys.stderr)
            continue
        number = ROMAN[bm.group(1)]
        start, end = parse_long_date(bm.group(2)), parse_long_date(bm.group(3))

        sm = re.search(r"In this block, the seminar will be held on ([^<]*?)\.?\s*<", chunk)
        schedule = re.sub(r"\s+", " ", sm.group(1)).strip() if sm else ""

        talks = []
        for pm in re.finditer(
                r'href="#collapse[^"]*">(?P<header>.*?)</a>.*?<div class="panel-body">(?P<body>.*?)</div>',
                chunk, re.S):
            header = clean(pm.group("header"))
            talk = parse_header(header, start, end)
            talk = parse_body(pm.group("body"), talk)
            if talk.get("review"):
                print(f"REVIEW [{label}] {header!r} -> {talk['review']}", file=sys.stderr)
            talks.append(talk)
        talks.sort(key=lambda t: t["date"])

        # block default room = most common room; drop per-talk room when it matches
        rooms = Counter(t.get("room") for t in talks if t.get("room"))
        default_room = rooms.most_common(1)[0][0] if rooms else None
        for t in talks:
            if t.get("room") == default_room:
                del t["room"]

        ay_start = start.year if start.month >= 8 else start.year - 1
        blocks.append({
            "number": number, "start": start, "end": end, "schedule": schedule,
            "room": default_room, "talks": talks,
            "year": f"{ay_start}–{ay_start + 1}",
            "slug": f"{ay_start}-{ay_start + 1}-{number}",
        })

    OUT.mkdir(parents=True, exist_ok=True)
    for b in blocks:
        roman = {v: k for k, v in ROMAN.items()}[b["number"]]
        out = [
            f"block: \"Block {roman}\"",
            f"year: \"{b['year']}\"",
            f"start: {b['start'].isoformat()}",
            f"end: {b['end'].isoformat()}",
            f"schedule: {yaml_str(b['schedule'])}",
        ]
        if b["room"]:
            out.append(f"room: {yaml_str(b['room'])}")
        out.append("talks:")
        out.extend(emit_talk(t) for t in b["talks"])
        path = OUT / f"{b['slug']}.yaml"
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"wrote {path.name}: {len(b['talks'])} talks")


if __name__ == "__main__":
    main()
