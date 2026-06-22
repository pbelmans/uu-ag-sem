#!/usr/bin/env python3
"""One-off: re-bucket the calendar-year archive files (archive-2021/2022/2023)
into academic-year files, splitting at the summer break (a talk in August or
later belongs to the academic year starting that calendar year). Talk entries
are moved verbatim so their typeset LaTeX is preserved. Fall-2023 talks land in
academic year 2023-2024 alongside the existing block files for that year.
"""

import re
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "blocks"
SOURCES = ["archive-2021.yaml", "archive-2022.yaml", "archive-2023.yaml"]


def academic_year(dt):
    return (dt.year, dt.year + 1) if dt.month >= 8 else (dt.year - 1, dt.year)


# gather every talk entry as (date, raw_text), dropping the old block headers
chunks = []
for name in SOURCES:
    text = (DATA / name).read_text(encoding="utf-8")
    for part in re.split(r"(?m)^(?=  - date: )", text)[1:]:
        m = re.match(r"  - date: (\d{4})-(\d{2})-(\d{2})", part)
        dt = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        chunks.append((dt, part.rstrip("\n")))

groups = {}
for dt, txt in chunks:
    groups.setdefault(academic_year(dt), []).append((dt, txt))

for ay, items in sorted(groups.items()):
    items.sort(key=lambda x: x[0])
    start, end = items[0][0], items[-1][0]
    label = f"{ay[0]}–{ay[1]}"
    header = [f'year: "{label}"', f"start: {start.isoformat()}",
              f"end: {end.isoformat()}", "talks:"]
    body = "\n".join(txt for _, txt in items)
    path = DATA / f"archive-{ay[0]}-{ay[1]}.yaml"
    path.write_text("\n".join(header) + "\n" + body + "\n", encoding="utf-8")
    print(f"wrote {path.name}: {len(items)} talks ({start} to {end})")

for name in SOURCES:
    (DATA / name).unlink()
    print(f"removed {name}")
