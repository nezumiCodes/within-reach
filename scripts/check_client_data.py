#!/usr/bin/env python3
"""Pre-commit guard: block anything that looks like real client data (spec NFR-06).

Rules:
  1. Spreadsheet and data files (.csv, .tsv, .xlsx, .xls, .xlsm, .ods) may only be committed
     under fixtures/synthetic/ (synthetic client data) or pipeline/tests/fixtures/ (small
     samples of public data). Both are still scanned by rules 2 and 3.
  2. CSV/TSV files there must not have columns that look like names, NHS numbers or dates of
     birth, and every client_ref value must start with "SYN-".
  3. No committed CSV/TSV may contain a 10-digit number that passes the NHS number check digit.

Usage: check_client_data.py FILE [FILE ...]   (exit code 1 if anything is blocked)
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path, PurePosixPath

DATA_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xls", ".xlsm", ".ods"}
TEXT_TABLE_SUFFIXES = {".csv", ".tsv"}
SYNTHETIC_DIR = PurePosixPath("fixtures/synthetic")
ALLOWED_DIRS = (SYNTHETIC_DIR, PurePosixPath("pipeline/tests/fixtures"))
FORBIDDEN_COLUMN = re.compile(
    r"^(first_?name|last_?name|sur_?name|full_?name|forename|name|"
    r"nhs_?(no|num|number)?|nhs number|chi_?(no|number)?|dob|date_?of_?birth)$",
    re.IGNORECASE,
)
TEN_DIGITS = re.compile(r"(?<!\d)(\d{3}[ -]?\d{3}[ -]?\d{4})(?!\d)")


def is_valid_nhs_number(candidate: str) -> bool:
    digits = [int(c) for c in candidate if c.isdigit()]
    if len(digits) != 10:
        return False
    total = sum(d * (10 - i) for i, d in enumerate(digits[:9]))
    check = 11 - (total % 11)
    if check == 11:
        check = 0
    return check != 10 and check == digits[9]


def problems_for(path: Path, repo_relative: PurePosixPath) -> list[str]:
    suffix = path.suffix.lower()
    if suffix not in DATA_SUFFIXES:
        return []
    if not any(allowed in repo_relative.parents for allowed in ALLOWED_DIRS):
        allowed_list = " or ".join(f"{d}/" for d in ALLOWED_DIRS)
        return [f"{repo_relative}: data files may only be committed under {allowed_list}"]
    if suffix not in TEXT_TABLE_SUFFIXES:
        return []

    problems: list[str] = []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    for match in TEN_DIGITS.finditer(text):
        if is_valid_nhs_number(match.group(1)):
            problems.append(f"{repo_relative}: contains a valid NHS number pattern")
            break

    delimiter = "\t" if suffix == ".tsv" else ","
    rows = list(csv.DictReader(text.splitlines(), delimiter=delimiter))
    columns = rows[0].keys() if rows else []
    for column in columns:
        if column and FORBIDDEN_COLUMN.match(column.strip()):
            problems.append(f"{repo_relative}: forbidden column '{column}'")
    for line_no, row in enumerate(rows, start=2):
        ref = (row.get("client_ref") or "").strip()
        if ref and not ref.upper().startswith("SYN-"):
            problems.append(f"{repo_relative}:{line_no}: client_ref '{ref}' must start with SYN-")
            break
    return problems


def main(argv: list[str]) -> int:
    problems: list[str] = []
    for name in argv:
        path = Path(name)
        if path.is_file():
            problems.extend(problems_for(path, PurePosixPath(path.as_posix())))
    for problem in problems:
        print(f"BLOCKED: {problem}", file=sys.stderr)
    if problems:
        print("Only synthetic client data may be committed (spec NFR-06).", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
