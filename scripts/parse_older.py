#!/usr/bin/env python3
"""One-off migration: parse the older AG-seminar Google Site
(sites.google.com/view/woonamlim/organization/ag-seminar-at-uu, downloaded to
/tmp/agsem2.html) into YAML files under data/blocks/.

The page has two regimes:
- Blocks 2-4 of 2023-24: an intro paragraph per block, then per talk a <li>
  date line, a bold speaker/title paragraph, and an abstract paragraph.
- Flat "2023" / "2022" / "2021" archive lists where everything for a talk
  lives in a single <li>.

Entries the heuristics cannot fully classify get a 'REVIEW' marker.
"""

import html
import json
import re
import sys
import textwrap
from collections import Counter
from datetime import date
from pathlib import Path

SRC = Path("/tmp/agsem2.html")
OUT = Path(__file__).resolve().parent.parent / "data" / "blocks"

MONTHS = {m[:3].lower(): i + 1 for i, m in enumerate(
    "January February March April May June July August September October November December".split())}

# UU teaching blocks, taken from the academic calendar
BLOCK_META = {
    2: {"slug": "2023-2024-2", "block": "Block II", "year": "2023–2024",
        "start": date(2023, 11, 13), "end": date(2024, 2, 2)},
    3: {"slug": "2023-2024-3", "block": "Block III", "year": "2023–2024",
        "start": date(2024, 2, 5), "end": date(2024, 4, 19)},
    4: {"slug": "2023-2024-4", "block": "Block IV", "year": "2023–2024",
        "start": date(2024, 4, 22), "end": date(2024, 6, 28)},
}


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


def parse_date(text, year_hint):
    m = re.match(r"(\w+)\.?\s+(\d{1,2})", text)
    if not m or m.group(1)[:3].lower() not in MONTHS:
        return None, text
    month, day = MONTHS[m.group(1)[:3].lower()], int(m.group(2))
    return date(year_hint, month, day), text[m.end():].lstrip(" ,:")


def parse_paren(text):
    """Pull a leading '(13:00-14:00, BBG 083)' / '(HFG-409)' off the text."""
    time_v = room = None
    m = re.match(r"\(([^)]*)\)", text.strip())
    if m:
        inside = m.group(1).strip()
        parts = [p.strip() for p in inside.split(",", 1)]
        tm = re.match(r"(?P<t>[\d.:]+(\s*[-–]\s*[\d.:]+)?)\s*(?P<r>.*)$", parts[0])
        if tm:
            time_v = re.sub(r"\s*[-–]\s*", "-", tm.group("t"))
            room = tm.group("r").strip() or (parts[1] if len(parts) > 1 else None)
        else:
            room = inside
        text = text.strip()[m.end():].lstrip(" ,")
    return time_v, room, text


def finish_block(blocks, current):
    if current and current["talks"]:
        blocks.append(current)


def parse_block_li(text, year_hints, talk_defaults):
    """Date line in the block regime, e.g.
    'May 21 (10:00-11:00, KBG - ATLAS) -- unusual day, time, location [This week ...]'."""
    talk = {}
    notes = []
    for y in year_hints:
        d, rest = parse_date(text, y)
        if d and year_hints[0] <= d.year <= year_hints[-1]:
            # block lists never cross New Year ambiguously: month decides
            d = date(y if d.month >= 8 else year_hints[-1], d.month, d.day) \
                if len(year_hints) > 1 else d
            break
    talk["date"], rest = d, rest
    for bracket in re.findall(r"\[([^\]]*)\]", rest):
        notes.append(bracket.strip())
    rest = re.sub(r"\[[^\]]*\]", "", rest).strip()
    if re.search(r"(?i)no talk", rest):
        m = re.search(r"(?i)no talk", rest)
        notes.insert(0, "no talk")
        rest = (rest[:m.start()] + rest[m.end():]).strip(" -")
        if rest:
            notes.append(rest.strip(" -"))
        talk["note"] = "; ".join(notes)
        return talk
    talk["time"], talk["room"], rest = parse_paren(rest)
    rest = rest.strip()
    if rest.startswith("--"):
        notes.insert(0, rest.lstrip("- ").strip())
        rest = ""
    if rest:
        talk.setdefault("review", "leftover on date line: " + rest)
    if notes:
        talk["note"] = "; ".join(notes)
    return {k: v for k, v in talk.items() if v}


def parse_speaker_p(text, talk):
    """Bold paragraph 'Ruijie Yang (Berlin) -- Minimal exponent of a hypersurface'."""
    parts = re.split(r"\s+--\s+|\s+–\s+", text, maxsplit=1)
    head = parts[0].strip()
    if len(parts) > 1:
        talk["title"] = parts[1].strip()
    m = re.match(r"(?P<name>[^()]+?)\s*\((?P<aff>.+?)\)\s*$", head)
    if m:
        talk["speaker"] = m.group("name").strip()
        talk["affiliation"] = m.group("aff").strip()
    else:
        talk["speaker"] = head
    return talk


def parse_archive_li(text, year):
    """Single-line archive entry, many shapes; see module docstring."""
    talk = {}
    review = []
    talk["date"], rest = parse_date(text, year)
    if talk["date"] is None:
        return None
    brackets = [b.strip() for b in re.findall(r"\[([^\]]*)\]", rest)]
    rest = re.sub(r"\[[^\]]*\]", "", rest).strip()
    talk["time"], talk["room"], rest = parse_paren(rest)
    # the parenthetical sometimes comes after a 'research talk by' prefix
    kind = None
    m = re.match(r"(?i)(research talk|preprint talk|minicourse)\s+(on|by)?\s*", rest)
    if m:
        kind = m.group(1).lower()
        rest = rest[m.end():]
    if talk["time"] is None and talk["room"] is None:
        t2, r2, rest = parse_paren(rest)
        talk["time"], talk["room"] = t2, r2

    # split off the abstract
    abstract = None
    am = re.search(r"A\s?bstract\s*[:.]\s*", rest)
    if am:
        abstract = rest[am.end():].strip()
        rest = rest[:am.start()].strip()

    # speaker (affiliation) title  |  speaker[:|,] title  |  bare speaker
    title = None
    m = re.match(r"(?P<name>[^,:(\"]+?)\s*\((?P<aff>[^)]+)\)\s*[:,]?\s*(?P<rest>.*)$", rest)
    if m:
        talk["speaker"] = m.group("name").strip()
        talk["affiliation"] = m.group("aff").strip()
        title = m.group("rest")
    else:
        m = re.match(r"(?P<name>[^,:\"]+?)\s*[:,]\s*(?P<rest>.*)$", rest)
        if m:
            talk["speaker"] = m.group("name").strip()
            title = m.group("rest")
        elif rest and len(rest) < 60 and '"' not in rest:
            talk["speaker"] = rest.strip()
        elif rest:
            review.append("unparsed entry: " + rest[:80])
    if title and re.match(r"(?i)preprint talk on\s*", title):
        kind = "preprint talk"
        title = re.sub(r"(?i)preprint talk on\s*", "", title)
    if title:
        talk["title"] = title.strip(" ,")
    if abstract:
        talk["abstract"] = abstract
    notes = ([kind] if kind and kind != "research talk" else []) + brackets
    if notes:
        talk["note"] = "; ".join(notes)
    if review:
        talk["review"] = "; ".join(review)
    return {k: v for k, v in talk.items() if v}


def main():
    content = SRC.read_text(encoding="utf-8", errors="ignore")
    content = html.unescape(html.unescape(content))

    items = []
    for m in re.finditer(r"<(li|p)\b[^>]*>(.*?)</\1>", content, re.S):
        tag, inner = m.group(1), m.group(2)
        bold = "font-weight: 700" in inner
        text = re.sub(r"<[^>]+>", " ", inner)
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        if text:
            items.append((tag, bold, text))
    # drop everything before the first block intro (JS polyfill noise etc.)
    start = next(i for i, it in enumerate(items) if it[2].startswith("In Block"))
    items = items[start:]

    blocks = []
    current = None
    mode = None  # 'block' | 'archive'
    talk = None

    for tag, bold, text in items:
        bm = re.match(r"In Block (\d) \((Fall|Spring) (\d{4})\)\s*,\s*(?P<intro>.*)$", text)
        am = re.fullmatch(r"(20\d\d)", text)
        if bm and tag == "p":
            finish_block(blocks, current)
            meta = dict(BLOCK_META[int(bm.group(1))])
            sm = re.search(r"take place on (.*?)(?:[.,]| in | For| after)", bm.group("intro"))
            meta["schedule"] = sm.group(1).strip() if sm else ""
            current = {**meta, "talks": []}
            mode, talk = "block", None
            ys = ([2023, 2024] if bm.group(2) == "Fall" else [int(bm.group(3))])
            current["_years"] = ys
            continue
        if am and tag == "p":
            finish_block(blocks, current)
            year = int(am.group(1))
            current = {"slug": f"archive-{year}", "block": f"Talks in {year}",
                       "start": None, "end": None, "schedule": "", "talks": []}
            mode, talk = "archive", None
            continue
        if current is None:
            continue

        if mode == "block":
            if tag == "li":
                talk = parse_block_li(text, current["_years"], current)
                current["talks"].append(talk)
            elif tag == "p" and bold and talk is not None and "speaker" not in talk:
                parse_speaker_p(text, talk)
            elif tag == "p" and talk is not None:
                abs_text = re.sub(r"^A\s?bstract\s*[:.]\s*", "", text)
                talk["abstract"] = (talk.get("abstract", "") + " " + abs_text).strip()
        elif mode == "archive" and tag == "li":
            t = parse_archive_li(text, int(current["slug"].split("-")[1]))
            if t:
                current["talks"].append(t)
            else:
                print(f"SKIP archive li: {text[:90]!r}", file=sys.stderr)
    finish_block(blocks, current)

    OUT.mkdir(parents=True, exist_ok=True)
    for b in blocks:
        talks = sorted(b["talks"], key=lambda t: t["date"])
        if b["start"] is None:
            b["start"], b["end"] = talks[0]["date"], talks[-1]["date"]

        # block default time/room = the most common values; drop matching per-talk ones
        for field in ("time", "room"):
            vals = Counter(t.get(field) for t in talks if t.get(field))
            if not vals:
                continue
            default, n = vals.most_common(1)[0]
            if n >= max(3, len(talks) // 2):
                for t in talks:
                    if t.get(field) == default:
                        del t[field]
                if field == "room":
                    b["room"] = default
                elif b["schedule"] and not re.search(r"\d", b["schedule"]):
                    b["schedule"] += f" ({default})"

        out = [f"block: {yaml_str(b['block'])}"]
        if b.get("year"):
            out.append(f"year: \"{b['year']}\"")
        out.append(f"start: {b['start'].isoformat()}")
        out.append(f"end: {b['end'].isoformat()}")
        if b.get("schedule"):
            out.append(f"schedule: {yaml_str(b['schedule'])}")
        if b.get("room"):
            out.append(f"room: {yaml_str(b['room'])}")
        out.append("talks:")
        out.extend(emit_talk(t) for t in talks)
        path = OUT / f"{b['slug']}.yaml"
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
        n_review = sum(1 for t in talks if t.get("review"))
        print(f"wrote {path.name}: {len(talks)} talks" + (f" ({n_review} to review)" if n_review else ""))


if __name__ == "__main__":
    main()
