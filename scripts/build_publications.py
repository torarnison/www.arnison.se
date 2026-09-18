#!/usr/bin/env python3
"""
Build the publications list from ORCID.

Runs automatically before every `quarto render` (see _quarto.yml). It

  1. fetches all public works for ORCID_ID from the ORCID public API,
  2. fills in authors/journal details from Crossref when ORCID lacks them,
  3. merges the hand-written notes in publications/summaries.yml,
  4. writes publications/_generated.qmd, which publications.qmd includes.

A copy of the fetched data is kept in publications/orcid-cache.json. If the
network is unavailable the cache is used, so the site always renders.

Only the Python standard library plus PyYAML is needed.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
ORCID_ID = "0000-0002-9035-0287"
SELF_NAMES = ("arnison",)        # lower-case; author names containing these are bolded
USE_CROSSREF = True              # fill in authors / journal from Crossref if ORCID lacks them
CROSSREF_MAILTO = "tor@arnison.se"   # polite-pool contact for Crossref
MAX_AUTHORS_SHOWN = 12

ROOT = Path(__file__).resolve().parent.parent
PUB_DIR = ROOT / "publications"
CACHE_FILE = PUB_DIR / "orcid-cache.json"
SUMMARIES_FILE = PUB_DIR / "summaries.yml"
OUTPUT_FILE = PUB_DIR / "_generated.qmd"

TYPE_LABELS = {
    "journal-article": "",
    "dissertation-thesis": "Doctoral thesis",
    "dissertation": "Doctoral thesis",
    "preprint": "Preprint",
    "book": "Book",
    "book-chapter": "Book chapter",
    "edited-book": "Edited book",
    "conference-paper": "Conference paper",
    "conference-abstract": "Conference abstract",
    "conference-poster": "Poster",
    "report": "Report",
    "review": "Review",
    "working-paper": "Working paper",
    "data-set": "Dataset",
    "software": "Software",
    "other": "Other",
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def get_json(url: str, accept: str = "application/json", retries: int = 3, timeout: int = 30):
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"Accept": accept, "User-Agent": f"arnison.se-site-builder (mailto:{CROSSREF_MAILTO})"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as err:
            last_err = err
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {last_err}")


# ---------------------------------------------------------------------------
# ORCID
# ---------------------------------------------------------------------------
def _val(obj, *keys, default=None):
    """Safely walk nested dicts: _val(d, 'title', 'title', 'value')."""
    cur = obj
    for k in keys:
        if not isinstance(cur, dict) or cur.get(k) is None:
            return default
        cur = cur[k]
    return cur


def fetch_orcid_works(orcid: str) -> list[dict]:
    base = f"https://pub.orcid.org/v3.0/{orcid}"
    data = get_json(f"{base}/works")
    works = []
    for group in data.get("group", []):
        summaries = group.get("work-summary") or []
        if not summaries:
            continue
        # ORCID lists the preferred version first; keep the lowest display-index.
        summary = min(summaries, key=lambda s: int(s.get("display-index") or 0))
        ext_ids = _val(group, "external-ids", "external-id", default=[]) or []
        ids = {}
        for e in ext_ids:
            t = (e.get("external-id-type") or "").lower()
            v = _val(e, "external-id-normalized", "value") or e.get("external-id-value")
            if t and v and t not in ids:
                ids[t] = v
        works.append({
            "put_code": summary.get("put-code"),
            "title": _val(summary, "title", "title", "value", default="").strip(),
            "subtitle": _val(summary, "title", "subtitle", "value"),
            "journal": _val(summary, "journal-title", "value"),
            "type": summary.get("type") or "other",
            "year": _val(summary, "publication-date", "year", "value"),
            "month": _val(summary, "publication-date", "month", "value"),
            "url": _val(summary, "url", "value"),
            "ids": ids,
            "authors": [],
            "source": _val(summary, "source", "source-name", "value"),
        })

    # Full records (in chunks of 50) carry the contributor lists and citations.
    by_code = {w["put_code"]: w for w in works}
    codes = [str(c) for c in by_code if c is not None]
    for i in range(0, len(codes), 50):
        chunk = codes[i:i + 50]
        try:
            bulk = get_json(f"{base}/works/{','.join(chunk)}")
        except RuntimeError as err:
            print(f"  warning: could not fetch work details: {err}", file=sys.stderr)
            continue
        for item in bulk.get("bulk", []):
            work = item.get("work")
            if not work:
                continue
            w = by_code.get(work.get("put-code"))
            if w is None:
                continue
            contribs = _val(work, "contributors", "contributor", default=[]) or []
            names = []
            for c in contribs:
                role = (_val(c, "contributor-attributes", "contributor-role") or "author").lower()
                if role not in ("author", "co-author", "co_author"):
                    continue
                name = _val(c, "credit-name", "value")
                if name:
                    names.append(name.strip())
            if not names:
                names = authors_from_bibtex(_val(work, "citation", "citation-value") or "")
            w["authors"] = names
            if not w["journal"]:
                w["journal"] = journal_from_bibtex(_val(work, "citation", "citation-value") or "")
    return works


def authors_from_bibtex(bib: str) -> list[str]:
    m = re.search(r"author\s*=\s*[{\"](.+?)[}\"]\s*,?\s*\n", bib, flags=re.S | re.I)
    if not m:
        return []
    raw = re.sub(r"\s+", " ", m.group(1))
    names = []
    for part in re.split(r"\s+and\s+", raw):
        part = part.strip().strip("{}")
        if "," in part:
            last, first = [p.strip() for p in part.split(",", 1)]
            names.append(f"{first} {last}".strip())
        elif part:
            names.append(part)
    return names


def journal_from_bibtex(bib: str):
    m = re.search(r"journal\s*=\s*[{\"](.+?)[}\"]", bib, flags=re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


# ---------------------------------------------------------------------------
# Crossref (optional enrichment)
# ---------------------------------------------------------------------------
def enrich_from_crossref(w: dict) -> None:
    doi = w["ids"].get("doi")
    if not doi:
        return
    try:
        msg = get_json(f"https://api.crossref.org/works/{urllib.request.quote(doi)}?mailto={CROSSREF_MAILTO}",
                       retries=2, timeout=20).get("message", {})
    except RuntimeError:
        return
    if not w["authors"]:
        names = []
        for a in msg.get("author", []) or []:
            given, family = a.get("given", ""), a.get("family", "")
            n = f"{given} {family}".strip() or a.get("name", "")
            if n:
                names.append(n)
        w["authors"] = names
    if not w["journal"]:
        ct = msg.get("container-title") or []
        if ct:
            w["journal"] = ct[0]
    if not w.get("volume"):
        w["volume"] = msg.get("volume")
        w["issue"] = msg.get("issue")
        w["pages"] = msg.get("page")
    if not w["year"]:
        parts = _val(msg, "issued", "date-parts", default=[[None]])
        if parts and parts[0] and parts[0][0]:
            w["year"] = str(parts[0][0])


# ---------------------------------------------------------------------------
# PubMed and PMC ids (NCBI id converter), for works that only carry a DOI
# ---------------------------------------------------------------------------
def add_pubmed_ids(works: list[dict]) -> None:
    # PMIDs: one E-utilities search per DOI (the id converter below only
    # covers articles that are in PMC, which is why most PubMed links were missing).
    for w in works:
        doi = w["ids"].get("doi")
        if not doi or w["ids"].get("pmid"):
            continue
        url = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
               f"?db=pubmed&term={urllib.request.quote(doi)}[doi]&retmode=json&tool=arnison.se&email={CROSSREF_MAILTO}")
        try:
            ids = get_json(url, retries=2, timeout=20).get("esearchresult", {}).get("idlist", [])
            if len(ids) == 1:
                w["ids"]["pmid"] = str(ids[0])
        except RuntimeError as err:
            print(f"  warning: PubMed lookup failed for {doi}: {err}", file=sys.stderr)
        time.sleep(0.35)   # NCBI allows 3 requests per second without an API key

    # PMC ids (free full text) via the id converter
    todo = [w for w in works if w["ids"].get("doi") and not w["ids"].get("pmcid")]
    for i in range(0, len(todo), 100):
        chunk = todo[i:i + 100]
        dois = ",".join(w["ids"]["doi"] for w in chunk)
        url = ("https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
               f"?ids={urllib.request.quote(dois, safe=',')}&format=json&tool=arnison.se&email={CROSSREF_MAILTO}")
        try:
            data = get_json(url, retries=2, timeout=20)
        except RuntimeError as err:
            print(f"  warning: PubMed id lookup failed: {err}", file=sys.stderr)
            return
        by_doi = {}
        for rec in data.get("records", []):
            if rec.get("doi") and rec.get("status") != "error":
                by_doi[rec["doi"].lower()] = rec
        for w in chunk:
            rec = by_doi.get(w["ids"]["doi"].lower())
            if rec:
                if rec.get("pmid") and not w["ids"].get("pmid"):
                    w["ids"]["pmid"] = str(rec["pmid"])
                if rec.get("pmcid"):
                    w["ids"]["pmcid"] = str(rec["pmcid"])


# ---------------------------------------------------------------------------
# Notes / summaries
# ---------------------------------------------------------------------------
def load_summaries() -> list[dict]:
    if not SUMMARIES_FILE.exists():
        return []
    data = yaml.safe_load(SUMMARIES_FILE.read_text(encoding="utf-8")) or []
    return [d for d in data if isinstance(d, dict)]


def find_note(w: dict, notes: list[dict]):
    """Merge every entry in summaries.yml that matches this work; later entries win."""
    doi = (w["ids"].get("doi") or "").lower()
    merged: dict = {}
    for n in notes:
        hit = (
            (n.get("doi") and doi and str(n["doi"]).lower() == doi)
            or (n.get("put_code") is not None and str(n["put_code"]) == str(w["put_code"]))
            or (n.get("title_contains") and str(n["title_contains"]).lower() in w["title"].lower())
        )
        if hit:
            merged.update({k: v for k, v in n.items() if v not in (None, "")})
    return merged or None


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def format_authors(names: list[str]) -> str:
    def fmt(n: str) -> str:
        e = html.escape(n)
        return f'<span class="pub-self">{e}</span>' if any(s in n.lower() for s in SELF_NAMES) else e

    if not names:
        return ""
    if len(names) > MAX_AUTHORS_SHOWN:
        shown = [fmt(n) for n in names[:MAX_AUTHORS_SHOWN - 2]]
        # keep the author's own name visible even in a long list
        own = [fmt(n) for n in names[MAX_AUTHORS_SHOWN - 2:] if any(s in n.lower() for s in SELF_NAMES)]
        rest = len(names) - len(shown) - len(own)
        return ", ".join(shown + own) + f", and {rest} others"
    return ", ".join(fmt(n) for n in names)


def primary_link(w: dict):
    doi = w["ids"].get("doi")
    if doi:
        return f"https://doi.org/{doi}"
    return w.get("url")


def render_work(w: dict, note: dict | None) -> str:
    title = html.escape(w["title"] or "Untitled")
    if w.get("subtitle"):
        title += ": " + html.escape(w["subtitle"])
    link = primary_link(w)
    title_html = f'<a href="{html.escape(link)}">{title}</a>' if link else title
    kind = TYPE_LABELS.get(w["type"], w["type"].replace("-", " ").capitalize())
    kind_html = f'<span class="pub-kind">{html.escape(kind)}</span>' if kind else ""

    meta_parts = []
    authors = format_authors(w["authors"])
    if authors:
        meta_parts.append(authors)
    if w.get("journal"):
        j = f'<span class="pub-journal">{html.escape(w["journal"])}</span>'
        vol = w.get("volume")
        if vol:
            j += f", {html.escape(str(vol))}"
            if w.get("issue"):
                j += f"({html.escape(str(w['issue']))})"
            if w.get("pages"):
                j += f", {html.escape(str(w['pages']))}"
        meta_parts.append(j)
    if w.get("year"):
        meta_parts.append(html.escape(str(w["year"])))
    meta = ". ".join(meta_parts) + ("." if meta_parts else "")

    links = []
    doi = w["ids"].get("doi")
    if doi:
        links.append(f'<a href="https://doi.org/{html.escape(doi)}">doi:{html.escape(doi)}</a>')
    pmid = w["ids"].get("pmid")
    if pmid:
        links.append(f'<a href="https://pubmed.ncbi.nlm.nih.gov/{html.escape(str(pmid))}/">PubMed</a>')
    pmcid = w["ids"].get("pmcid")
    if pmcid:
        links.append(f'<a href="https://pmc.ncbi.nlm.nih.gov/articles/{html.escape(str(pmcid))}/">Free full text</a>')
    if note and note.get("link"):
        links.append(f'<a href="{html.escape(str(note["link"]))}">{html.escape(str(note.get("link_text", "Full text")))}</a>')
    if note and note.get("pdf"):
        pdf = str(note["pdf"])
        if not (ROOT / pdf).exists():
            print(f"  warning: PDF not found for '{w['title'][:50]}': {pdf}", file=sys.stderr)
        href = urllib.request.quote(pdf, safe="/")     # spaces and apostrophes in file names
        links.append(f'<a class="pub-pdf" href="{href}" download>'
                     f'<i class="bi bi-file-earmark-arrow-down"></i>Download PDF</a>')
    links_html = f'<p class="pub-links">{" ".join(links)}</p>' if links else ""

    out = [
        "::: {.pub-item}",
        "```{=html}",
        f'<p class="pub-title">{title_html}{kind_html}</p>',
        f'<p class="pub-meta">{meta}</p>' if meta else "",
        links_html,
        "```",
    ]
    if note and note.get("summary"):
        summary = str(note["summary"]).strip()
        out += ["", "::: {.pub-summary}", summary, ":::"]
    out += [":::", ""]
    return "\n".join(line for line in out if line is not None)


def render_page(works: list[dict], notes: list[dict], synced_on: str, from_cache: bool) -> str:
    visible = []
    for w in works:
        note = find_note(w, notes)
        if note and note.get("hide"):
            continue
        visible.append((w, note))

    def sort_key(item):
        w = item[0]
        return (-int(w["year"] or 0), -int(w.get("month") or 0), w["title"].lower())

    visible.sort(key=sort_key)

    # A note about the data source is kept as an HTML comment only (visible in
    # the page source, useful when checking that the sync worked).
    source_note = "a saved copy; ORCID could not be reached at render time" if from_cache else "ORCID"
    lines = [f"<!-- {len(visible)} publications, synced from {source_note} on {synced_on} -->", ""]

    current_year = None
    for w, note in visible:
        year = w["year"] or "Undated"
        if year != current_year:
            if current_year is not None:
                lines += [":::", ":::", ""]          # close .pub-list and .pub-year
            current_year = year
            lines += ["::: {.pub-year}", "::: {.pub-year-label}", str(year), ":::", "::: {.pub-list}", ""]
        lines.append(render_work(w, note))
    if visible:
        lines += [":::", ":::", ""]
    else:
        lines.append("*No publications found.*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
def main() -> int:
    PUB_DIR.mkdir(exist_ok=True)
    notes = load_summaries()
    from_cache = False
    try:
        print(f"Fetching works for ORCID {ORCID_ID} ...")
        works = fetch_orcid_works(ORCID_ID)
        if USE_CROSSREF:
            for w in works:
                if not w["authors"] or not w["journal"] or not w.get("volume"):
                    enrich_from_crossref(w)
        add_pubmed_ids(works)
        synced_on = date.today().isoformat()
        CACHE_FILE.write_text(json.dumps({"synced_on": synced_on, "works": works}, indent=2, ensure_ascii=False),
                              encoding="utf-8")
        print(f"  {len(works)} works fetched and cached.")
    except Exception as err:  # network down, API change, etc.
        print(f"  warning: {err}", file=sys.stderr)
        if not CACHE_FILE.exists():
            OUTPUT_FILE.write_text(
                "*Publications could not be loaded from ORCID and no cached copy exists yet. "
                "Render again with an internet connection.*\n", encoding="utf-8")
            print("  wrote placeholder (no cache available).")
            return 0
        cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        works, synced_on, from_cache = cached["works"], cached.get("synced_on", "an earlier date"), True
        print(f"  using cached copy from {synced_on}.")

    OUTPUT_FILE.write_text(render_page(works, notes, synced_on, from_cache), encoding="utf-8")
    print(f"  wrote {OUTPUT_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
