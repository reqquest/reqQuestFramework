#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reqq_check_links.py — Markdown link integrity check (reqQuest Framework).

Every relative inline link `[text](path.md)` (optional `#anchor`) in the `.md` files of the
folders listed under `link_check_paths` in config.yaml (default: `requirements`; an empty
list disables the check) must resolve to an existing file. The anchor is not checked.
Only that plain form is parsed: links with a title (`[t](x.md "title")`), angle-bracket
destinations (`[t](<x.md>)`) and reference-style links (`[t][ref]`) are not checked.
Absolute URLs, root-relative links (`/x.md`, whose base depends on the renderer), `mailto:`
and links inside inline code or fenced code blocks are skipped. Methodology: conventions.md,
section 6.

Broken links are listed one per line (`file:line: link`), followed by one fix hint. A file that
cannot be read as UTF-8 text is an error too (`unreadable file`, with its own hint): its links
were not checked. The validator entry point runs the same check as `links` and reports
`links.broken` and `links.unreadable` records.

Exit codes: 0 = OK, 2 = broken links or unreadable files.
"""
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

sys.dont_write_bytecode = True  # importing the validator must not leave __pycache__ in adopter repos
import reqq_common as C  # noqa: E402

DEFAULT_FOLDERS = ["requirements"]
LINK = re.compile(r"\]\(([^)\s]+)\)")
INLINE_CODE = re.compile(r"`[^`]*`")
FENCE = re.compile(r"^\s*(```|~~~)")
HINT = "Fix the path (relative to the linking file) or restore the target file."
UNREADABLE_MESSAGE = "Cannot be read as UTF-8 text, so its links are not checked."
HINT_UNREADABLE = "Save the file as UTF-8 text, or take its folder out of `link_check_paths` in config.yaml."


def prose_lines(text: str) -> Iterator[Tuple[int, str]]:
    """Yield (line number, line) outside fenced code blocks, with inline code removed."""
    in_fence = False
    for number, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            yield number, INLINE_CODE.sub("", line)


def is_checked(target: str) -> bool:
    """True for a relative link to a Markdown file."""
    return (
        "://" not in target
        and not target.startswith(("mailto:", "/"))
        and target.endswith(".md")
    )


def file_broken(md: Path) -> List[Tuple[int, str]]:
    """Return (line number, link) for every checked link in `md` that resolves to no file.
    Raises OSError or UnicodeError when `md` cannot be read as UTF-8 text."""
    found = []
    for number, line in prose_lines(md.read_text(encoding="utf-8")):
        for link in LINK.findall(line):
            target = link.split("#", 1)[0]
            if is_checked(target) and not (md.parent / target).is_file():
                found.append((number, link))
    return found


def scan(root: Path, folders: List[str]) -> Tuple[List[Tuple[Path, int, str]], List[Path]]:
    """Return ((file, line number, link) of every broken link, files that cannot be read as UTF-8
    text) of the `.md` files under `folders` (relative to `root`). A file whose links were not
    checked is a finding, not a pass. A path that is not a file, e.g. a folder named `x.md`, is skipped."""
    broken: List[Tuple[Path, int, str]] = []
    unreadable: List[Path] = []
    for folder in folders:
        for md in sorted(p for p in (root / folder).rglob("*.md") if p.is_file()):
            try:
                broken += [(md, number, link) for number, link in file_broken(md)]
            except (OSError, UnicodeError):
                unreadable.append(md)
    return broken, unreadable


def _rel(md: Path, root: Path) -> str:
    return md.relative_to(root).as_posix()


def broken_links(root: Path, folders: List[str]) -> List[str]:
    """Return `file:line: link` for every broken link under `folders` (relative to `root`)."""
    return [f"{_rel(md, root)}:{number}: {link}" for md, number, link in scan(root, folders)[0]]


def run(ctx: C.RunContext) -> List[Dict[str, Any]]:
    """The `links` check: a `links.broken` record for every broken link and a `links.unreadable`
    record for every file it could not read, in the folders of `link_check_paths`, whole folders
    whatever the files of the run; an empty list checks nothing."""
    broken, unreadable = scan(C.ROOT, ctx.cfg.get("link_check_paths", DEFAULT_FOLDERS))
    return ([C._rec(md, "error", "links.broken", f"line {number}", f"'{link}' resolves to no file.", HINT,
                    number) for md, number, link in broken]
            + [C._rec(md, "error", "links.unreadable", "$", UNREADABLE_MESSAGE, HINT_UNREADABLE)
               for md in unreadable])


def main() -> int:
    folders = C.load_config().get("link_check_paths", DEFAULT_FOLDERS)
    if not folders:
        print("✔ link check skipped: link_check_paths is empty")
        return 0
    broken, unreadable = scan(C.ROOT, folders)
    for md, number, link in broken:
        print(f"✖ broken link {C.printable(f'{_rel(md, C.ROOT)}:{number}: {link}')}")
    if broken:
        print(f"  ↳ hint: {HINT}")
    for md in unreadable:
        print(f"✖ unreadable file {C.printable(_rel(md, C.ROOT))}")
    if unreadable:
        print(f"  ↳ hint: {HINT_UNREADABLE}")
    if broken or unreadable:
        return 2
    print(f"✔ links OK in: {', '.join(map(C.printable, folders))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
