#!/usr/bin/env python3
"""
PMC Full Text Fetch - Retrieve open-access full text from PubMed Central

Uses NCBI E-Utilities EFetch (db=pmc) to download the complete article body
(JATS XML) for articles in the PMC Open Access Subset, then parses it into
readable sections. Non-open-access articles return metadata + abstract only.

Accepts PMC IDs directly, or PMIDs (auto-converted to PMCIDs via ELink).

Usage:
    python pmc_fetch.py PMC8241728
    python pmc_fetch.py 8241728 5334499 --outline
    python pmc_fetch.py 34239348 --pmid --abstract full
    python pmc_fetch.py --file ids.txt --format json -o out.json
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import List, Optional, Dict, Any

# Ensure we can import ncbi_utils from the scripts directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from ncbi_utils import http_get, get_element_text
except ImportError:
    print("Error: Could not import ncbi_utils.py from the scripts directory.", file=sys.stderr)
    sys.exit(1)

import xml.etree.ElementTree as ET

try:
    import requests
except ImportError:
    # ncbi_utils already handles this, but just in case
    print("Error: 'requests' library is required. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)

# NCBI E-Utilities Base URLs
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EFETCH_URL = f"{EUTILS_BASE}/efetch.fcgi"
ELINK_URL = f"{EUTILS_BASE}/elink.fcgi"

# PMC full-text XML responses are large; use a smaller batch than PubMed abstracts.
BATCH_SIZE = 20

# Full-text display tiers (mirrors the --abstract philosophy in the other scripts)
BODY_FULL = "full"        # complete body text (default — the point of fetching full text)
BODY_OUTLINE = "outline"  # section headings only (token-cheap structure preview)


def get_api_key(args: argparse.Namespace) -> Optional[str]:
    """Get NCBI API key from args or environment."""
    if getattr(args, "api_key", None):
        return args.api_key
    return os.environ.get("NCBI_API_KEY")


def read_ids_from_file(filepath: str) -> List[str]:
    """Read identifiers from a file (one per line, blanks/comments ignored)."""
    ids = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                ids.append(line)
    return ids


def normalize_pmcid(raw: str) -> str:
    """Normalize a PMC identifier to its bare numeric form.

    Accepts 'PMC8241728', 'pmc8241728', or '8241728' -> '8241728'.
    Raises ValueError if the value is not a valid PMC id.
    """
    if raw is None:
        raise ValueError("empty PMC id")
    value = raw.strip()
    if value.upper().startswith("PMC"):
        value = value[3:]
    if not value.isdigit():
        raise ValueError(f"invalid PMC id: {raw!r}")
    return value


def _clean(text: Optional[str]) -> str:
    """Collapse internal whitespace/newlines into single spaces."""
    if not text:
        return ""
    return " ".join(text.split())


def pmid_to_pmcid(pmid: str, api_key: Optional[str] = None, verbose: bool = False) -> Optional[str]:
    """Map a single PMID to its own PMCID via ELink (linkname=pubmed_pmc).

    Returns the numeric PMCID string, or None if the article is not in PMC.
    linkname=pubmed_pmc restricts the result to the article's own PMC record
    (excluding pubmed_pmc_refs, which are citing articles).
    """
    params = {
        "dbfrom": "pubmed",
        "db": "pmc",
        "id": pmid,
        "linkname": "pubmed_pmc",
        "retmode": "json",
    }
    if api_key:
        params["api_key"] = api_key

    response_text = http_get(ELINK_URL, params=params, api_key=api_key, timeout=30, verbose=verbose)
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        return None

    for linkset in data.get("linksets", []):
        for linksetdb in linkset.get("linksetdbs", []):
            if linksetdb.get("linkname") == "pubmed_pmc":
                links = linksetdb.get("links", [])
                if links:
                    return str(links[0])
    return None


def map_pmids_to_pmcids(
    pmids: List[str],
    api_key: Optional[str] = None,
    verbose: bool = False,
) -> Dict[str, Optional[str]]:
    """Map each PMID to a PMCID (or None). One ELink call per PMID for accuracy."""
    mapping: Dict[str, Optional[str]] = {}
    for pmid in pmids:
        mapping[pmid] = pmid_to_pmcid(pmid, api_key, verbose)
        if verbose:
            status = mapping[pmid] or "not in PMC"
            print(f"PMID {pmid} -> PMC {status}", file=sys.stderr)
    return mapping


def fetch_fulltext_batched(
    pmcids: List[str],
    api_key: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """Fetch full-text JATS XML for a list of PMCIDs, batched to keep responses sane."""
    if not pmcids:
        return []

    all_articles = []
    total_batches = (len(pmcids) + batch_size - 1) // batch_size

    for i in range(total_batches):
        batch = pmcids[i * batch_size:(i + 1) * batch_size]
        if verbose or total_batches > 1:
            print(f"Fetching batch {i + 1}/{total_batches} ({len(batch)} PMC IDs)...", file=sys.stderr)

        params = {
            "db": "pmc",
            "id": ",".join(batch),
            "rettype": "xml",
            "retmode": "xml",
        }
        if api_key:
            params["api_key"] = api_key

        response_text = http_get(EFETCH_URL, params=params, api_key=api_key, timeout=90, verbose=verbose)
        all_articles.extend(parse_pmc_xml(response_text))

        # Small delay between batches to respect rate limits
        if i < total_batches - 1:
            import time
            time.sleep(0.5)

    return all_articles


def _blocks_from_sec(sec: ET.Element, level: int) -> List[Dict[str, Any]]:
    """Recursively convert a JATS <sec> into ordered heading/paragraph blocks."""
    blocks: List[Dict[str, Any]] = []

    label = sec.find("label")
    title = sec.find("title")
    heading = ""
    if label is not None and label.text:
        heading += label.text.strip() + " "
    if title is not None:
        heading += get_element_text(title)
    heading = _clean(heading)
    if heading:
        blocks.append({"type": "heading", "level": level, "text": heading})

    for child in sec:
        if child.tag in ("label", "title"):
            continue  # already consumed as the section heading
        if child.tag == "p":
            text = _clean(get_element_text(child))
            if text:
                blocks.append({"type": "paragraph", "text": text})
        elif child.tag == "sec":
            blocks.extend(_blocks_from_sec(child, level + 1))
    return blocks


def extract_body_blocks(body: ET.Element) -> List[Dict[str, Any]]:
    """Convert a JATS <body> into an ordered list of heading/paragraph blocks."""
    blocks: List[Dict[str, Any]] = []
    for child in body:
        if child.tag == "p":
            text = _clean(get_element_text(child))
            if text:
                blocks.append({"type": "paragraph", "text": text})
        elif child.tag == "sec":
            blocks.extend(_blocks_from_sec(child, 1))
    return blocks


def parse_pmc_xml(xml_text: str) -> List[Dict[str, Any]]:
    """Parse a PMC EFetch (JATS) response into structured article dicts.

    Each article contains: pmcid, pmid, doi, title, journal, year, authors,
    abstract, open_access (bool), content (ordered blocks), full_text, char_count.
    open_access is False when the body is absent (publisher blocks XML download).
    """
    articles: List[Dict[str, Any]] = []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"Warning: Failed to parse PMC XML: {e}", file=sys.stderr)
        return articles

    for art in root.findall(".//article"):
        article: Dict[str, Any] = {}
        front = art.find("front")

        # Identifiers (pmcid / pmid / doi) from <article-id pub-id-type="...">
        for aid in art.findall(".//article-id"):
            id_type = aid.get("pub-id-type")
            if not aid.text:
                continue
            if id_type == "pmcid":
                article["pmcid"] = aid.text.replace("PMC", "")
            elif id_type == "pmcaid" and "pmcid" not in article:
                article["pmcid"] = aid.text
            elif id_type == "pmid":
                article["pmid"] = aid.text
            elif id_type == "doi":
                article["doi"] = aid.text

        # Title
        if front is not None:
            title_elem = front.find(".//title-group/article-title")
            if title_elem is not None:
                article["title"] = _clean(get_element_text(title_elem))

            # Journal
            journal_elem = front.find(".//journal-title")
            if journal_elem is not None and journal_elem.text:
                article["journal"] = _clean(journal_elem.text)

            # Publication year (first pub-date with a year)
            for pub_date in front.findall(".//pub-date"):
                year_elem = pub_date.find("year")
                if year_elem is not None and year_elem.text:
                    article["year"] = year_elem.text
                    break

            # Authors
            authors = []
            for contrib in front.findall(".//contrib[@contrib-type='author']"):
                surname = contrib.find(".//surname")
                given = contrib.find(".//given-names")
                collab = contrib.find(".//collab")
                if surname is not None and surname.text:
                    initial = given.text[0] if (given is not None and given.text) else ""
                    authors.append(_clean(f"{surname.text} {initial}"))
                elif collab is not None:
                    text = _clean(get_element_text(collab))
                    if text:
                        authors.append(text)
            article["authors"] = authors

            # Abstract (structured abstracts are flattened via get_element_text)
            abstract_elem = front.find(".//abstract")
            if abstract_elem is not None:
                abstract = _clean(get_element_text(abstract_elem))
                if abstract:
                    article["abstract"] = abstract

        # Body full text
        body = art.find("body")
        if body is not None:
            blocks = extract_body_blocks(body)
            article["content"] = blocks
            paragraphs = [b["text"] for b in blocks if b["type"] == "paragraph"]
            article["full_text"] = "\n\n".join(paragraphs)
            article["char_count"] = len(article["full_text"])
            article["open_access"] = True
        else:
            article["content"] = []
            article["full_text"] = ""
            article["char_count"] = 0
            article["open_access"] = False

        # PMC URL
        if article.get("pmcid"):
            article["url"] = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{article['pmcid']}/"

        articles.append(article)

    return articles


def _render_body(blocks: List[Dict[str, Any]], outline: bool, max_chars: int) -> List[str]:
    """Render body blocks to summary lines. outline=headings only; max_chars=0 unlimited."""
    lines: List[str] = []
    used = 0
    truncated = False
    for block in blocks:
        if block["type"] == "heading":
            hashes = "#" * min(block["level"] + 2, 6)
            indent = "  " * (block["level"] - 1) if outline else ""
            lines.append("")
            lines.append(f"{indent}{hashes} {block['text']}")
        elif block["type"] == "paragraph" and not outline:
            text = block["text"]
            if max_chars and used + len(text) > max_chars:
                remaining = max_chars - used
                if remaining > 0:
                    lines.append(text[:remaining])
                truncated = True
                break
            lines.append("")
            lines.append(text)
            used += len(text)
    if truncated:
        lines.append("")
        lines.append("... [full text truncated; use --max-chars 0 for the complete body]")
    return lines


def format_output(
    articles: List[Dict[str, Any]],
    fmt: str = "summary",
    body_mode: str = BODY_FULL,
    max_chars: int = 0,
    abstract_mode: str = "full",
    unavailable: Optional[List[str]] = None,
) -> str:
    """Format PMC results as JSON or human-readable summary."""
    unavailable = unavailable or []
    outline = body_mode == BODY_OUTLINE

    if fmt == "json":
        payload = {
            "fetch_date": datetime.now().isoformat(),
            "requested": len(articles) + len(unavailable),
            "returned": len(articles),
            "full_text_available": sum(1 for a in articles if a.get("open_access")),
            "unavailable_pmids": unavailable,
            "articles": articles,
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)

    # Summary (default)
    full_count = sum(1 for a in articles if a.get("open_access"))
    meta_only = len(articles) - full_count

    lines = []
    lines.append("=" * 70)
    lines.append("PMC Full Text Results")
    lines.append("=" * 70)
    lines.append(f"Retrieved: {len(articles)} articles | Full text: {full_count} | Metadata only: {meta_only}")
    if unavailable:
        lines.append(f"Not in PMC: {', '.join(unavailable)}")
    lines.append("=" * 70)

    for i, article in enumerate(articles, 1):
        pmcid = article.get("pmcid", "N/A")
        lines.append(f"\n[{i}] PMCID: PMC{pmcid} | PMID: {article.get('pmid', 'N/A')}")
        lines.append(f"Title: {article.get('title', 'N/A')}")

        authors = article.get("authors", [])
        if authors:
            author_str = ", ".join(authors[:5])
            if len(authors) > 5:
                author_str += f" et al. ({len(authors)} authors)"
            lines.append(f"Authors: {author_str}")

        lines.append(f"Journal: {article.get('journal', 'N/A')} ({article.get('year', 'N/A')})")
        if article.get("doi"):
            lines.append(f"DOI: {article['doi']}")
        if article.get("url"):
            lines.append(f"URL: {article['url']}")

        if article.get("open_access"):
            lines.append(f"Open Access Full Text: Yes ({article.get('char_count', 0)} chars)")
        else:
            lines.append("Open Access Full Text: No (publisher blocks XML full-text download)")

        # Abstract
        if abstract_mode != "none" and article.get("abstract"):
            abstract = article["abstract"]
            if abstract_mode == "preview" and len(abstract) > 1000:
                abstract = abstract[:1000] + "..."
            lines.append("")
            lines.append(f"Abstract: {abstract}")

        # Body
        if article.get("open_access") and article.get("content"):
            lines.append("")
            lines.append("--- Full Text ---" if not outline else "--- Section Outline ---")
            lines.extend(_render_body(article["content"], outline, max_chars))
        elif not article.get("open_access"):
            lines.append("")
            lines.append("Note: Full text XML not available. Open the URL above for the publisher's version.")

        lines.append("")
        lines.append("-" * 70)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch PMC open-access full text via NCBI E-Utilities (EFetch db=pmc)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s PMC8241728
    %(prog)s 8241728 5334499 --outline
    %(prog)s 34239348 33597265 --pmid --abstract full
    %(prog)s --file ids.txt --format json -o out.json

Notes:
    - Bare numbers and PMCxxxxx are treated as PMC IDs.
    - Use --pmid to pass PubMed IDs instead (auto-converted to PMCIDs).
    - Only PMC Open Access Subset articles return full body text; others
      return metadata + abstract only.
        """
    )

    parser.add_argument("ids", nargs="*", help="PMC IDs (e.g. PMC8241728 or 8241728), or PMIDs with --pmid")
    parser.add_argument("--file", "-f", help="File containing IDs (one per line)")
    parser.add_argument("--pmid", action="store_true", help="Treat inputs as PubMed IDs and convert to PMCIDs via ELink")
    parser.add_argument("--outline", action="store_true", help="Show section headings only (no body paragraphs) — token-cheap structure preview")
    parser.add_argument("--max-chars", type=int, default=0, help="Truncate body text to N chars (0 = unlimited, default)")
    parser.add_argument("--abstract", choices=["none", "preview", "full"], default="full",
                        help="Abstract display level: none, preview (first 1000 chars), full (default)")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help=f"Max PMC IDs per EFetch request (default: {BATCH_SIZE})")
    parser.add_argument("--format", choices=["json", "summary"], default="summary", help="Output format (default: summary)")
    parser.add_argument("--output", "-o", help="Save to file")
    parser.add_argument("--api-key", help="NCBI API key")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed progress")

    args = parser.parse_args()

    # Collect raw IDs
    raw_ids = list(args.ids)
    if args.file:
        raw_ids.extend(read_ids_from_file(args.file))

    if not raw_ids:
        print("Error: No IDs provided", file=sys.stderr)
        sys.exit(1)

    api_key = get_api_key(args)
    body_mode = BODY_OUTLINE if args.outline else BODY_FULL
    unavailable: List[str] = []

    try:
        if args.pmid:
            # Validate PMIDs and convert to PMCIDs
            pmids = [p.strip() for p in raw_ids if p.strip().isdigit()]
            invalid = [p for p in raw_ids if not p.strip().isdigit()]
            for p in invalid:
                print(f"Warning: skipping non-numeric PMID {p!r}", file=sys.stderr)
            if not pmids:
                print("Error: No valid PMIDs found", file=sys.stderr)
                sys.exit(1)
            print(f"Resolving {len(pmids)} PMIDs to PMCIDs...", file=sys.stderr)
            mapping = map_pmids_to_pmcids(pmids, api_key, args.verbose)
            pmcids = []
            for pmid, pmcid in mapping.items():
                if pmcid:
                    pmcids.append(pmcid)
                else:
                    unavailable.append(pmid)
            if unavailable:
                print(f"Warning: {len(unavailable)} PMID(s) not in PMC: {', '.join(unavailable)}", file=sys.stderr)
        else:
            # Treat inputs as PMC IDs
            pmcids = []
            for raw in raw_ids:
                try:
                    pmcids.append(normalize_pmcid(raw))
                except ValueError as e:
                    print(f"Warning: {e}", file=sys.stderr)

        if not pmcids:
            print("Error: No valid PMC IDs to fetch", file=sys.stderr)
            # Still emit the unavailable notice in the chosen format
            output = format_output([], args.format, body_mode, args.max_chars, args.abstract, unavailable)
            print(output)
            sys.exit(1)

        print(f"Fetching full text for {len(pmcids)} PMC article(s)...", file=sys.stderr)
        articles = fetch_fulltext_batched(pmcids, api_key, args.batch_size, args.verbose)

        output = format_output(articles, args.format, body_mode, args.max_chars, args.abstract, unavailable)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"Saved to {args.output}", file=sys.stderr)
        else:
            print(output)

    except requests.exceptions.ConnectionError:
        print("Error: 无法连接到 NCBI 服务器，请检查网络连接。", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("Error: NCBI 服务器响应超时，请稍后重试或减少批次大小(--batch-size)。", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"Error: NCBI 服务器返回错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
