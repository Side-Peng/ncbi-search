#!/usr/bin/env python3
"""
PubMed Search via NCBI E-Utilities API

Intelligent PubMed search with natural language query conversion.

Usage:
    python pubmed_search.py "your query" [options]

Features:
    - Natural language to PubMed query conversion (ATM-first: no forced field tags)
    - Concept recognition (MeSH vocabulary, genes, authors) used as plain keywords
    - Date filtering
    - Article type filtering
    - Tiered abstract display: none (titles only), preview (~400 chars), full (complete)
    - CSV export for systematic-review screening
"""

import os
import sys
import json
import argparse
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

# Ensure we can import ncbi_utils from scripts directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from ncbi_utils import (
        http_get, get_element_text, parse_pubmed_xml, truncate_abstract,
        NCBIError, PREVIEW_CHARS, date_filter,
    )
except ImportError:
    print("Error: Could not import ncbi_utils.py from the scripts directory.", file=sys.stderr)
    sys.exit(1)

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)

# NCBI E-Utilities Base URLs
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ESEARCH_URL = f"{EUTILS_BASE}/esearch.fcgi"
EFETCH_URL = f"{EUTILS_BASE}/efetch.fcgi"

# Maximum IDs per EFetch request (NCBI recommended limit)
BATCH_SIZE = 200

# Known MeSH terms for common medical concepts.
# Multi-word phrases are matched first (longest first). Single anatomy words
# (brain/heart/blood/liver/kidney) are intentionally NOT mapped: `"Brain"[MeSH]`
# expands the whole anatomy tree and drops recall for e.g. "brain tumor"
# (39,754 vs 183,787 results). Those words pass through as plain keywords and
# PubMed's automatic term mapping resolves them.
MESH_TERMS = {
    # Diseases
    "alzheimer": "Alzheimer Disease",
    "alzheimer's": "Alzheimer Disease",
    "alzheimer disease": "Alzheimer Disease",
    "dementia": "Dementia",
    "parkinson": "Parkinson Disease",
    "parkinson's": "Parkinson Disease",
    "stroke": "Stroke",
    "cerebrovascular": "Cerebrovascular Disorders",
    "cerebrovascular disorders": "Cerebrovascular Disorders",
    "diabetes": "Diabetes Mellitus",
    "diabetes mellitus": "Diabetes Mellitus",
    "cancer": "Neoplasms",
    "tumor": "Neoplasms",
    "neoplasms": "Neoplasms",
    "hypertension": "Hypertension",
    "depression": "Depression",
    "schizophrenia": "Schizophrenia",
    "autism": "Autistic Disorder",
    "autistic disorder": "Autistic Disorder",
    "epilepsy": "Epilepsy",
    "multiple sclerosis": "Multiple Sclerosis",

    # Systems
    "nervous system": "Nervous System",
    "cardiovascular": "Cardiovascular System",
    "cardiovascular system": "Cardiovascular System",
    "immune": "Immune System",
    "immune system": "Immune System",

    # Concepts
    "neuroinflammation": "Neuroinflammation",
    "amyloid": "Amyloid",
    "tau": "Tau Proteins",
    "tau proteins": "Tau Proteins",

    # Processes
    "apoptosis": "Apoptosis",
    "autophagy": "Autophagy",
    "angiogenesis": "Angiogenesis",
}

# Multi-word MeSH keys sorted by length (longest first) for greedy matching
MESH_MULTIWORD_KEYS = sorted(
    [k for k in MESH_TERMS if ' ' in k or "'" in k],
    key=lambda x: len(x),
    reverse=True
)

# Gene symbols (common ones)
GENE_SYMBOLS = [
    "APOE", "APP", "PSEN1", "PSEN2", "TREM2", "MAPT", "SNCA", "TARDBP",
    "BRCA1", "BRCA2", "TP53", "EGFR", "KRAS", "MYC", "PTEN", "VEGF",
    "IL6", "TNF", "IFNG", "IL1B", "IL10", "TGFB1",
    "BDNF", "NGF", "GDNF", "NTF3",
]

# Stop words to exclude from query.
# Domain instruction words (last/years/author/gene/paper...) are included so they
# cannot leak into the AND-group: "Alzheimer last 5 years" used to become
# `... AND (last years) AND <date>` and lost 99.7% of its recall.
STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "shall", "can", "need",
    "this", "that", "these", "those", "about", "after", "before", "during",
    "between", "into", "through", "during", "above", "below", "up", "down",
    "out", "off", "over", "under", "again", "further", "then", "once",
    "here", "there", "when", "where", "why", "how", "all", "each", "few",
    "more", "most", "other", "some", "such", "no", "nor", "not", "only",
    "own", "same", "so", "than", "too", "very", "just", "also", "now",
    # Domain instruction / filler words
    "last", "year", "years", "author", "authors", "written", "et", "al",
    "gene", "genes", "paper", "papers", "article", "articles", "study",
    "studies", "find", "search", "show", "please", "recent", "latest",
    "newest", "via", "using", "regarding", "concerning",
}

# Article type filters (shared with ncbi_search.py)
TYPE_FILTER = {
    "review": "Review[pt]",
    "clinical_trial": "Clinical Trial[pt]",
    "randomized": "Randomized Controlled Trial[pt]",
    "meta_analysis": "Meta-Analysis[pt]",
    "case_report": "Case Reports[pt]",
}

# Abstract display tiers for progressive search (token optimization for AI agents)
ABSTRACT_NONE = "none"       # Tier 1: Title + metadata only (lowest token cost, default)
ABSTRACT_PREVIEW = "preview" # Tier 2: Sentence-aware abstract preview (~400 chars)
ABSTRACT_FULL = "full"       # Tier 3: Complete abstract (final selection)
ABSTRACT_CHOICES = [ABSTRACT_NONE, ABSTRACT_PREVIEW, ABSTRACT_FULL]
DEFAULT_ABSTRACT_MODE = ABSTRACT_NONE


def get_api_key(args: argparse.Namespace) -> Optional[str]:
    """Get NCBI API key from args or environment."""
    if hasattr(args, 'api_key') and args.api_key:
        return args.api_key
    return os.environ.get("NCBI_API_KEY")


_TYPE_PATTERNS = [
    ("review", re.compile(r"\breviews?\b", re.IGNORECASE)),
    ("clinical_trial", re.compile(r"\bclinical\s+trials?\b|\btrials?\b", re.IGNORECASE)),
    ("randomized", re.compile(r"\brandomi[sz]ed\b|\brct\b", re.IGNORECASE)),
    ("meta_analysis", re.compile(r"\bmeta[- ]?analy[sz]is\b", re.IGNORECASE)),
    ("case_report", re.compile(r"\bcase\s+(?:reports?|stud(?:y|ies))\b", re.IGNORECASE)),
]

_TYPE_WORDS = {
    "review", "reviews", "trial", "trials", "clinical", "randomized",
    "randomised", "rct", "meta", "analysis", "case", "report", "reports",
}

# Author parsing only fires on explicit clue words: "Smith J author" /
# "author Smith J". Without this gate, "Vitamin D" / "Hepatitis B" / "Influenza A"
# were parsed as authors and the query collapsed to 3 results (99.99% recall loss).
_AUTHOR_AFTER_RE = re.compile(r"\b([A-Z][A-Za-z-]+)\s+([A-Z])\s+(?:author|authors|au)\b")
_AUTHOR_BEFORE_RE = re.compile(
    r"\b(?:author|authors|written\s+by|by)\s*:?\s+([A-Z][A-Za-z-]+)\s+([A-Z])\b"
)

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_LAST_YEARS_RE = re.compile(r"\blast\s+(\d+)\s+years?\b", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[\w][\w-]*", re.UNICODE)
_QUOTE_RE = re.compile(r'"([^"]+)"')


def detect_query_elements(query: str) -> Dict[str, Any]:
    """Detect and categorize elements in a natural-language query.

    Each rule below fixes a measured recall bug:
    - Authors parse only with a clue word ("author"/"by"/"written by").
    - Quoted phrases are kept verbatim (never split or MeSH-tagged per word).
    - Hyphenated tokens survive tokenization ("IL-6", "p-tau217", "COVID-19").
    - MeSH phrases match on word boundaries; single anatomy words are not
      force-mapped to [MeSH] (that expanded the anatomy tree and halved recall).

    Returns:
        Dict with 'terms', 'genes', 'mesh', 'authors', 'phrases',
        'year', 'year_range', 'article_type'
    """
    elements = {
        "terms": [], "genes": [], "mesh": [], "authors": [], "phrases": [],
        "year": None, "year_range": None, "article_type": None,
    }
    chars = list(query)

    def mask(start: int, end: int):
        for i in range(start, end):
            chars[i] = " "

    def masked_text() -> str:
        return "".join(chars)

    # 1. Authors — require a clue word before or after the name
    for regex in (_AUTHOR_AFTER_RE, _AUTHOR_BEFORE_RE):
        for match in regex.finditer(masked_text()):
            name = f"{match.group(1)} {match.group(2)}"
            if name not in elements["authors"]:
                elements["authors"].append(name)
            mask(match.start(), match.end())

    # 2. Quoted phrases — kept verbatim
    for match in _QUOTE_RE.finditer(masked_text()):
        phrase = match.group(1).strip()
        if phrase:
            elements["phrases"].append(phrase)
        mask(match.start(), match.end())

    # 3. "last N years" (mask the phrase so its words never leak into keywords)
    match = _LAST_YEARS_RE.search(masked_text())
    if match:
        elements["year_range"] = int(match.group(1))
        mask(match.start(), match.end())

    # 4. Explicit 4-digit year -> [PDat]
    match = _YEAR_RE.search(masked_text())
    if match:
        elements["year"] = int(match.group(0))
        mask(match.start(), match.end())

    # 5. Multi-word MeSH phrases (greedy, longest first, word boundaries)
    for key in MESH_MULTIWORD_KEYS:
        pattern = re.compile(r"\b" + re.escape(key) + r"\b", re.IGNORECASE)
        while True:
            match = pattern.search(masked_text())
            if not match:
                break
            elements["mesh"].append(MESH_TERMS[key])
            mask(match.start(), match.end())

    # 6. Article type (word boundaries: "indusTRIAL" must not match "trial")
    for atype, pattern in _TYPE_PATTERNS:
        if pattern.search(masked_text()):
            elements["article_type"] = atype
            break

    # 7. Remaining tokens (hyphens kept; duplicates dropped; stop words removed)
    seen = set()
    for match in _TOKEN_RE.finditer(masked_text()):
        token = match.group(0)
        lower = token.lower()
        upper = token.upper()
        if lower in seen:
            continue
        if lower in STOP_WORDS:
            continue
        if elements["article_type"] and lower in _TYPE_WORDS:
            continue
        if token.isdigit() and len(token) < 4:
            continue  # keep "type 2" from injecting a bare "2" keyword
        seen.add(lower)

        if upper in GENE_SYMBOLS or upper.replace("-", "") in GENE_SYMBOLS:
            if token not in elements["genes"]:
                elements["genes"].append(token)
            continue
        if lower in MESH_TERMS:
            if MESH_TERMS[lower] not in elements["mesh"]:
                elements["mesh"].append(MESH_TERMS[lower])
            continue
        elements["terms"].append(token)

    return elements


def build_pubmed_query(
    query: str,
    elements: Dict[str, Any],
    years: Optional[int] = None,
    article_type: Optional[str] = None,
    mesh_filter: Optional[str] = None,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
) -> Tuple[str, str]:
    """
    Build a PubMed query from natural-language input.

    - Explicit boolean syntax (OR/NOT, or bracket field tags) is passed through
      with lower-case operators normalized to upper case.
    - Otherwise: MeSH/gene/author elements get field tags; the remaining words
      stay a raw keyword group so PubMed's ATM handles stemming and synonyms.

    Returns:
        Tuple of (pubmed_query, explanation)
    """
    lower_query = query.lower()

    atype = (article_type or elements.get("article_type") or "").strip().lower()
    year_range = years or elements.get("year_range")
    date_part = date_filter(year_range, min_year, max_year)

    # Passthrough: hand-written syntax or boolean operators
    if "[" in query or "]" in query or re.search(r"\b(?:or|not)\b", lower_query):
        base = re.sub(r"\b(and|or|not)\b", lambda m: m.group(0).upper(),
                      query, flags=re.IGNORECASE)
        extras = []
        if atype in TYPE_FILTER:
            extras.append(TYPE_FILTER[atype])
        if elements.get("year"):
            extras.append(f"{elements['year']}[PDat]")
        if date_part:
            extras.append(date_part)
        if mesh_filter:
            extras.append(f'"{mesh_filter}"[MeSH]')
        return " AND ".join([base] + extras), "Passthrough PubMed query"

    parts = []
    explanation = []

    for phrase in elements.get("phrases", []):
        parts.append(f'"{phrase}"')
        explanation.append(f'Phrase "{phrase}"')

    for gene in elements.get("genes", []):
        parts.append(f"{gene}[Title/Abstract]")
        explanation.append(f"Gene {gene}")

    # Detected MeSH concepts are passed through as plain keywords and left to
    # PubMed's automatic term mapping (ATM): ATM expands entry terms + tree and
    # still finds recently indexed / not-yet-indexed records. Explicit [MeSH]
    # tagging is opt-in via --mesh only (it bypasses ATM and loses recall).
    keywords = list(elements.get("terms", []))
    for mesh in elements.get("mesh", []):
        if mesh not in keywords:
            keywords.append(mesh)

    if keywords:
        kw = " ".join(keywords)
        parts.append(f"({kw})")
        explanation.append(f"Keywords: {kw}")

    for author in elements.get("authors", []):
        parts.append(f"{author}[Author]")
        explanation.append(f"Author {author}")

    if atype in TYPE_FILTER:
        parts.append(TYPE_FILTER[atype])
        explanation.append(f"Type {atype}")

    if elements.get("year"):
        parts.append(f"{elements['year']}[PDat]")
        explanation.append(f"Year {elements['year']}")

    if date_part:
        parts.append(date_part)
        if min_year or max_year:
            explanation.append(f"Years {min_year or 1900}-{max_year or 'now'}")
        else:
            explanation.append(f"Last {year_range} years")

    if mesh_filter:
        parts.append(f'"{mesh_filter}"[MeSH]')
        explanation.append(f"Mesh filter {mesh_filter}")

    if not parts:
        parts = [f"({query})"]

    return " AND ".join(parts), " | ".join(explanation) if explanation else "Keywords search"


def search_pubmed(
    query: str,
    max_results: int = 10,
    api_key: Optional[str] = None,
    sort: str = "relevance",
    verbose: bool = False,
    offset: int = 0,
) -> Dict[str, Any]:
    """Search PubMed and return PMIDs using shared http_get utility."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": sort
    }
    if offset > 0:
        params["retstart"] = offset
    
    if api_key:
        params["api_key"] = api_key
        
    response_text = http_get(ESEARCH_URL, params=params, api_key=api_key, timeout=30, verbose=verbose)
    data = json.loads(response_text)
    result = data.get("esearchresult", {})
    
    return {
        "count": int(result.get("count", 0)),
        "ids": result.get("idlist", []),
    }


def fetch_articles(
    pmids: List[str],
    api_key: Optional[str] = None,
    verbose: bool = False
) -> List[Dict[str, Any]]:
    """Fetch article details by PMID using EFetch (returns full abstracts).
    P2 fix: Batch requests (max 200 IDs per EFetch) to avoid silent truncation.
    """
    if not pmids:
        return []
    
    all_articles = []
    total_batches = (len(pmids) + BATCH_SIZE - 1) // BATCH_SIZE
    
    for i in range(total_batches):
        batch = pmids[i * BATCH_SIZE : (i + 1) * BATCH_SIZE]
        if verbose:
            print(f"Fetching batch {i + 1}/{total_batches} ({len(batch)} PMIDs)...", file=sys.stderr)
        
        params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "rettype": "xml",
            "retmode": "xml"
        }
        
        if api_key:
            params["api_key"] = api_key
            
        response_text = http_get(EFETCH_URL, params=params, api_key=api_key, timeout=60, verbose=verbose)
        all_articles.extend(parse_pubmed_xml(response_text))
        
        # Small delay between batches to respect rate limits
        if i < total_batches - 1:
            import time
            time.sleep(0.5)
    
    return all_articles


def trim_json_article(article: Dict[str, Any], mode: str) -> Dict[str, Any]:
    """Apply the --abstract tier to JSON output (it used to be ignored)."""
    rec = dict(article)
    if mode == ABSTRACT_NONE:
        for key in ("abstract", "mesh_terms", "doi"):
            rec.pop(key, None)
    elif mode == ABSTRACT_PREVIEW:
        rec.pop("mesh_terms", None)
        if rec.get("abstract"):
            rec["abstract"] = truncate_abstract(rec["abstract"])
    return rec


def format_csv_output(
    articles: List[Dict[str, Any]],
    total_count: int,
    query: str,
    effective_mode: str,
    offset: int = 0,
) -> str:
    """CSV export for systematic-review screening (one row per record).

    Columns: rank, pmid, title, authors (all), journal, year, doi, url, and
    abstract when the tier is not 'none'.
    """
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    header = ["rank", "pmid", "title", "authors", "journal", "year", "doi", "url"]
    if effective_mode != ABSTRACT_NONE:
        header.append("abstract")
    writer.writerow(header)

    for i, article in enumerate(articles, 1):
        pmid = article.get("pmid", "")
        authors = "; ".join(article.get("authors") or [])
        row = [
            offset + i,
            pmid,
            article.get("title", ""),
            authors,
            article.get("journal", ""),
            article.get("year", ""),
            article.get("doi", ""),
            article.get("url") or f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        ]
        if effective_mode != ABSTRACT_NONE:
            abstract = article.get("abstract") or ""
            if effective_mode == ABSTRACT_PREVIEW:
                abstract = truncate_abstract(abstract)
            row.append(abstract)
        writer.writerow(row)

    return buf.getvalue()


def format_output(
    articles: List[Dict[str, Any]],
    total_count: int,
    query: str,
    explanation: str,
    format: str = "summary",
    full_abstract: bool = False,
    abstract_mode: str = DEFAULT_ABSTRACT_MODE,
    offset: int = 0,
) -> str:
    """Format output for display (compact, token-optimized).

    abstract_mode: 'none' (title + metadata), 'preview' (sentence-aware ~400 chars),
    'full' (complete abstract + DOI + MeSH). URL is derivable from PMID and is
    omitted from summary output (JSON keeps it).
    """
    effective_mode = ABSTRACT_FULL if full_abstract else abstract_mode

    if format == "csv":
        return format_csv_output(articles, total_count, query, effective_mode, offset)

    if format == "json":
        output = {
            "pubmed_query": query,
            "total_results": total_count,
            "returned": len(articles),
            "articles": [trim_json_article(a, effective_mode) for a in articles],
        }
        if offset:
            output["offset"] = offset
        return json.dumps(output, separators=(",", ":"), ensure_ascii=False)

    # Summary format (default)
    lines = [f"# PubMed | query: {query} | total: {total_count} | shown: {len(articles)}"]
    if not articles:
        lines.append("No results.")
        return "\n".join(lines)

    for i, article in enumerate(articles, 1):
        pmid = article.get("pmid", "N/A")
        authors = article.get("authors") or []
        author_str = ""
        if authors:
            author_str = ", ".join(authors[:3])
            if len(authors) > 3:
                author_str += " et al."
        journal = article.get("journal") or ""
        year = article.get("year") or ""
        meta = " | ".join(x for x in [
            f"{journal} ({year})" if journal and year else journal,
            author_str,
        ] if x)

        lines.append("")
        lines.append(f"[{i}] PMID {pmid}" + (f" | {meta}" if meta else ""))
        lines.append(f"Title: {article.get('title', 'N/A')}")

        if effective_mode == ABSTRACT_FULL and article.get("abstract"):
            lines.append(f"Abstract: {article['abstract']}")
        elif effective_mode == ABSTRACT_PREVIEW and article.get("abstract"):
            lines.append(f"Abstract: {truncate_abstract(article['abstract'])}")

        if effective_mode == ABSTRACT_FULL:
            if article.get("doi"):
                lines.append(f"DOI: {article['doi']}")
            if article.get("mesh_terms"):
                mesh_str = ", ".join(article["mesh_terms"][:5])
                if len(article["mesh_terms"]) > 5:
                    mesh_str += " ..."
                lines.append(f"MeSH: {mesh_str}")

    return "\n".join(lines)


def validate_mesh_term(term: str, api_key: Optional[str] = None) -> Optional[bool]:
    """Check whether a term exists in the MeSH vocabulary.

    Returns True/False, or None when the check itself failed (network error) —
    a failed check must never block the search.
    """
    params = {"db": "mesh", "term": term, "retmode": "json", "retmax": 1}
    try:
        data = json.loads(http_get(ESEARCH_URL, params=params, api_key=api_key, timeout=15))
        return int(data.get("esearchresult", {}).get("count", 0)) > 0
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(
        description="PubMed 智能检索 (NCBI E-Utilities)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    %(prog)s "Alzheimer disease cerebrovascular mechanisms"
    %(prog)s "APOE gene and Alzheimer disease" --years 5
    %(prog)s "Smith J author Alzheimer" --max 20
    %(prog)s "diabetes treatment review" --type review
    %(prog)s "p-tau217 Abeta42 blood Alzheimer biomarker" --full-abstract
        """
    )
    
    parser.add_argument("query", help="自然语言检索词或 PubMed 检索式")
    parser.add_argument("--max", type=int, default=10, help="最大返回结果数 (默认: 10, 上限 200)")
    parser.add_argument("--years", type=int, help="限制最近 N 年")
    parser.add_argument("--min-year", type=int, help="最早发表年份（优先于 --years）")
    parser.add_argument("--max-year", type=int, help="最晚发表年份（优先于 --years）")
    parser.add_argument("--offset", type=int, default=0, help="跳过前 N 条结果（翻页）")
    parser.add_argument("--type", help="文章类型: review, clinical_trial, randomized, meta_analysis, case_report")
    parser.add_argument("--mesh", help="MeSH 主题词筛选")
    parser.add_argument("--sort", choices=["relevance", "pub_date", "Author", "Journal"], default="relevance",
                        help="排序方式: relevance(相关性), pub_date(日期), Author(作者), Journal(期刊)")
    parser.add_argument("--full-abstract", action="store_true", help="显示完整摘要（不截断）[等同 --abstract full]")
    parser.add_argument("--abstract", choices=ABSTRACT_CHOICES, default=DEFAULT_ABSTRACT_MODE,
                        help="摘要显示级别: none(仅标题元数据, 默认), preview(~400字符按句截断), full(完整摘要)")
    parser.add_argument("--format", choices=["json", "summary", "csv"], default="summary", help="输出格式")
    parser.add_argument("--count-only", action="store_true", help="只输出命中数（不抓取记录）")
    parser.add_argument("--output", "-o", help="保存到文件")
    parser.add_argument("--api-key", help="NCBI API key")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细信息")
    
    args = parser.parse_args()

    if args.max < 1 or args.max > 200:
        args.max = max(1, min(args.max, 200))
        print(f"Warning: --max adjusted to {args.max} (allowed 1-200)", file=sys.stderr)
    if args.offset < 0:
        args.offset = 0
    if args.min_year and args.max_year and args.min_year > args.max_year:
        args.min_year, args.max_year = args.max_year, args.min_year
    if args.years and (args.min_year or args.max_year):
        print("Warning: --min-year/--max-year given; ignoring --years", file=sys.stderr)

    api_key = get_api_key(args)
    
    try:
        query_text = args.query

        # Detect query elements
        elements = detect_query_elements(query_text)
        if args.verbose:
            print(f"检测到的元素: {json.dumps(elements, ensure_ascii=False, indent=2)}", file=sys.stderr)
        
        # Build PubMed query
        pubmed_query, explanation = build_pubmed_query(
            query_text,
            elements,
            years=args.years,
            article_type=args.type,
            mesh_filter=args.mesh,
            min_year=args.min_year,
            max_year=args.max_year,
        )
        
        if args.verbose:
            print(f"PubMed 检索式: {pubmed_query}", file=sys.stderr)
        
        # Search
        search_result = search_pubmed(pubmed_query, args.max, api_key, args.sort, args.verbose, offset=args.offset)
        pmids = search_result["ids"]
        total = search_result["count"]
        
        if args.verbose:
            print(f"找到 {total} 篇文献, 获取 {len(pmids)} 篇...", file=sys.stderr)
        
        if args.mesh:
            valid = validate_mesh_term(args.mesh, api_key)
            if valid is False:
                print(f"Warning: MeSH term {args.mesh!r} not found in MeSH; queries may return 0 results (see meshb.nlm.nih.gov).", file=sys.stderr)

        if total == 0:
            if re.search(r"[\u4e00-\u9fff]", query_text):
                print("Hint: PubMed indexes English; translate the query (e.g. 阿尔茨海默病 -> Alzheimer disease) or relax filters.", file=sys.stderr)
            elif args.mesh:
                print(f"Hint: MeSH term {args.mesh!r} may be invalid; look it up at meshb.nlm.nih.gov.", file=sys.stderr)
            else:
                print("Hint: 0 results; try broader terms or drop --type/--years/--mesh filters.", file=sys.stderr)

        if args.count_only:
            print(f"# PubMed | query: {pubmed_query} | total: {total}")
            return

        # Fetch articles
        articles = fetch_articles(pmids, api_key, args.verbose) if pmids else []
        
        # Format output
        output = format_output(articles, total, pubmed_query, explanation, args.format,
                               args.full_abstract, args.abstract, offset=args.offset)
        
        # Print or save
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"已保存到 {args.output}", file=sys.stderr)
        else:
            print(output)
    
    except requests.exceptions.ConnectionError:
        print("Error: cannot reach NCBI (network problem or blocked host).", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("Error: NCBI request timed out; retry or lower --max.", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        code = getattr(getattr(e, "response", None), "status_code", "?")
        print(f"Error: NCBI HTTP {code}.", file=sys.stderr)
        sys.exit(1)
    except NCBIError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
