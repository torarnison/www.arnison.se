#!/usr/bin/env python3
"""
Build the CV page from cv/cv.yml.

Runs automatically before every `quarto render` (see _quarto.yml) and writes
cv/_generated.qmd, which cv.qmd includes. Needs only PyYAML.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CV_FILE = ROOT / "cv" / "cv.yml"
OUTPUT_FILE = ROOT / "cv" / "_generated.qmd"


def md_escape_span(text: str) -> str:
    """Light escaping for text that goes into a Markdown span (keeps it readable)."""
    return str(text).replace("[", "\\[").replace("]", "\\]")


def render_header(cv: dict) -> list[str]:
    lines = ["::: {.cv-header}"]
    if cv.get("headline"):
        lines.append(f"[{cv['headline']}]{{.lead}}")
        lines.append("")
    contact = cv.get("contact") or {}
    parts = []
    emails = contact.get("email") or []
    for e in (emails if isinstance(emails, list) else [emails]):
        parts.append(f'<span><a href="mailto:{html.escape(str(e))}">{html.escape(str(e))}</a></span>')
    if contact.get("phone"):
        parts.append(f"<span>{html.escape(str(contact['phone']))}</span>")
    if contact.get("location"):
        parts.append(f"<span>{html.escape(contact['location'])}</span>")
    if contact.get("orcid"):
        parts.append(f'<span><a href="https://orcid.org/{html.escape(contact["orcid"])}">ORCID {html.escape(contact["orcid"])}</a></span>')
    if contact.get("website"):
        parts.append(f'<span><a href="https://{html.escape(contact["website"])}">{html.escape(contact["website"])}</a></span>')
    if parts:
        lines += ["```{=html}", f'<p class="cv-contact">{"".join(parts)}</p>', "```"]
    if cv.get("pdf"):
        lines += ["```{=html}",
                  f'<a class="cv-download" href="{html.escape(cv["pdf"])}" download>Download as PDF</a>', "```"]
    lines += [":::", ""]
    return lines


def render_entry(e: dict) -> list[str]:
    period = e.get("period", "")
    lines = ["::: {.cv-entry}", f"[{md_escape_span(period)}]{{.cv-period}}", "", "::: {.cv-body}"]
    head = f"[{md_escape_span(e.get('role', ''))}]{{.cv-role}}"
    if e.get("org"):
        head += f"  \n[{md_escape_span(e['org'])}]{{.cv-org}}"
    if e.get("place"):
        head += f"  \n[{md_escape_span(e['place'])}]{{.cv-place}}"
    lines.append(head)
    details = e.get("details") or []
    if details:
        lines.append("")
        lines += [f"- {d}" for d in details]
    lines += [":::", ":::", ""]
    return lines


def render_section(sec: dict) -> list[str]:
    lines = [f"## {sec.get('title', '')}", ""]
    if sec.get("text"):
        lines += [str(sec["text"]).strip(), ""]
    if sec.get("items"):
        lines += ["::: {.cv-inline-list}"]
        lines += [f"- {i}" for i in sec["items"]]
        lines += [":::", ""]
    for e in sec.get("entries") or []:
        lines += render_entry(e)
    return lines


def main() -> int:
    cv = yaml.safe_load(CV_FILE.read_text(encoding="utf-8")) or {}
    out = render_header(cv)
    for sec in cv.get("sections") or []:
        out += render_section(sec)
    OUTPUT_FILE.write_text("\n".join(out), encoding="utf-8")
    print(f"  wrote {OUTPUT_FILE.relative_to(ROOT)} ({len(cv.get('sections') or [])} sections)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
