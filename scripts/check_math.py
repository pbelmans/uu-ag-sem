#!/usr/bin/env python3
"""Sanity checks for KaTeX math in the data files: balanced $ delimiters,
no known-invalid macros, no overlong or tab-indented lines."""

import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "blocks"

# macros that KaTeX does not know but show up in lazily-TeXed abstracts
BAD_MACROS = re.compile(r"\\(F|N|Z|Q|R|C|Hom|End|Pic|Spec|Hilb|Quot|coh|Db)\b")

ok = True
for path in sorted(DATA.glob("*.yaml")):
    text = path.read_text(encoding="utf-8")
    # one chunk per talk so unbalanced $ are localized in the report
    chunks = re.split(r"(?m)^  - date: ", text)
    for chunk in chunks[1:]:
        label = f"{path.name} @ {chunk[:10]}"
        if chunk.count("$") % 2:
            print(f"UNBALANCED $: {label}")
            ok = False
        m = BAD_MACROS.search(chunk)
        if m:
            print(f"BAD MACRO {m.group(0)}: {label}")
            ok = False
        if "$$" in chunk:
            print(f"EMPTY/DISPLAY $$: {label}")
            ok = False
    for i, line in enumerate(text.splitlines(), 1):
        if "\t" in line:
            print(f"TAB: {path.name}:{i}")
            ok = False
        # only abstract continuation lines need wrapping; one-line titles are fine
        if len(line) > 100 and re.match(r"^      \S", line):
            print(f"LONG LINE ({len(line)}): {path.name}:{i}")
            ok = False

print("all checks passed" if ok else "PROBLEMS FOUND")
sys.exit(0 if ok else 1)
