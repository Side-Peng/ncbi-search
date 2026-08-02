#!/usr/bin/env python3
"""
PubMed Search via NCBI E-Utilities API

Intelligent PubMed search with natural language query conversion.

Usage:
    python pubmed_search.py "your query" [options]

Features:
    - Natural language to PubMed query conversion (lenient approach)
    - MeSH term recognition and expansion (including multi-word phrases)
    - Smart field mapping (Title/Abstract, Author, Journal)
    - Date filtering
    - Article type filtering
    - Tiered abstract display: none (titles only), preview (1000 chars), full (complete)
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
    from ncbi_utils import http_get, get_element_text
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

# Known MeSH terms for common medical concepts
# P2 fix: includes multi-word phrases (will be matched via phrase matching)
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
    
    # Anatomy
    "brain": "Brain",
    "heart": "Heart",
    "liver": "Liver",
    "kidney": "Kidney",
    "blood": "Blood",
    
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

# Stop words to exclude from query
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
}

# Default abstract preview length (P1 fix: raised from 200 to 1000)
DEFAULT_ABSTRACT_LENGTH = 1000

# Abstract display tiers for progressive search (token optimization for AI agents)
ABSTRACT_NONE = "none"       # Tier 1: Title + metadata only (lowest token cost)
ABSTRACT_PREVIEW = "preview" # Tier 2: First 1000 chars of abstract (current default)
ABSTRACT_FULL = "full"       # Tier 3: Complete abstract (final selection)
ABSTRACT_CHOICES = [ABSTRACT_NONE, ABSTRACT_PREVIEW, ABSTRACT_FULL]
DEFAULT_ABSTRACT_MODE = ABSTRACT_PREVIEW


def get_api_key(args: argparse.Namespace) -> Optional[str]:
    """Get NCBI API key from args or environment."""
    if hasattr(args, 'api_key') and args.api_key:
        return args.api_key
    return os.environ.get("NCBI_API_KEY")


def detect_query_elements(query: str) -> Dict[str, Any]:
    """
    Detect and categorize elements in natural language query.
    
    P2 fix: Multi-word MeSH phrases are matched first (greedy, longest first),
    then single-word fallback.
    
    Returns:
        Dict with 'terms', 'genes', 'mesh', 'authors', 'journal', 'year'
    """
    query_lower = query.lower()
    elements = {
        "terms": [],
        "genes": [],
        "mesh": [],
        "authors": [],
        "journal": None,
        "year": None,
        "year_range": None,
        "article_type": None,
    }
    
    # P2 fix: Try multi-word MeSH phrase matching first (greedy, longest first)
    matched_spans = []  # (start, end, mesh_value) in lowercase query
    for phrase_key in MESH_MULTIWORD_KEYS:
        idx = query_lower.find(phrase_key)
        while idx != -1:
            # Check this span doesn't overlap with already-matched spans
            span_start = idx
            span_end = idx + len(phrase_key)
            overlaps = False
            for (ms, me, _) in matched_spans:
                if span_start < me and span_end > ms:
                    overlaps = True
                    break
            if not overlaps:
                matched_spans.append((span_start, span_end, MESH_TERMS[phrase_key]))
                elements["mesh"].append(MESH_TERMS[phrase_key])
            idx = query_lower.find(phrase_key, span_end)
    
    # Now process individual words, skipping words that are part of matched phrases
    words = re.findall(r'\b\w+\b', query)
    
    # Build a set of character positions covered by matched phrases
    phrase_positions = set()
    for (start, end, _) in matched_spans:
        for pos in range(start, end):
            phrase_positions.add(pos)
    
    for word in words:
        word_upper = word.upper()
        word_lower = word.lower()
        
        # Check if this word's position is part of a matched multi-word phrase
        # Find the position of this word in the original query
        word_match = re.search(r'\b' + re.escape(word) + r'\b', query, re.IGNORECASE)
        if word_match:
            word_start = word_match.start()
            word_end = word_match.end()
            in_phrase = any(word_start < me and word_end > ms for (ms, me, _) in matched_spans)
            if in_phrase:
                continue  # Skip, already covered by multi-word MeSH
        
        # Detect genes (uppercase or known symbols)
        if word_upper in GENE_SYMBOLS:
            elements["genes"].append(word_upper)
        elif word_lower not in STOP_WORDS and len(word) > 1:
            # Check if it's a single-word MeSH term
            if word_lower in MESH_TERMS:
                elements["mesh"].append(MESH_TERMS[word_lower])
            elements["terms"].append(word)
    
    # Detect year patterns
    year_match = re.search(r'\b(19|20)\d{2}\b', query)
    if year_match:
        elements["year"] = int(year_match.group())
    
    # Detect "last N years" pattern
    last_years_match = re.search(r'last\s+(\d+)\s+years?', query_lower)
    if last_years_match:
        elements["year_range"] = int(last_years_match.group(1))
    
    # Detect article types
    type_patterns = {
        "review": ["review", "reviews"],
        "clinical_trial": ["clinical trial", "clinical trials", "trial"],
        "randomized": ["randomized", "rct"],
        "meta_analysis": ["meta-analysis", "meta analysis", "metaanalysis"],
        "case_report": ["case report", "case study"],
    }
    for atype, patterns in type_patterns.items():
        for pattern in patterns:
            if pattern in query_lower:
                elements["article_type"] = atype
                break
        if elements["article_type"]:
            break
    
    # Detect author pattern (Name followed by initial or just last name)
    author_match = re.search(r'\b([A-Z][a-z]+)\s+([A-Z](?:\s|$|,))', query)
    if author_match:
        elements["authors"].append(f"{author_match.group(1)} {author_match.group(2).strip()}")
    
    return elements


def build_pubmed_query(
    query: str,
    elements: Dict[str, Any],
    years: Optional[int] = None,
    article_type: Optional[str] = None,
    mesh_filter: Optional[str] = None
) -> Tuple[str, str]:
    """
    Build PubMed query from natural language and detected elements.
    
    P1 fix: Natural language conversion is now LENIENT.
    - MeSH terms and gene symbols get explicit field tags ([MeSH], [Title/Abstract])
    - Other terms are passed as RAW KEYWORDS without field restriction
    - PubMed's own search engine handles the rest (stemming, MeSH auto-mapping, etc.)
    - This avoids the "0 results" problem from AND-ing every word with [Title/Abstract]
    
    Returns:
        Tuple of (pubmed_query, explanation)
    """
    query_parts = []
    explanation_parts = []
    
    # If query already has PubMed syntax, use it
    if any(tag in query for tag in ["[", " AND ", " OR ", " NOT "]):
        return query, "使用用户提供的 PubMed 检索式"
    
    # 1. Genes - search in Title/Abstract (these are reliable, keep field tag)
    for gene in elements.get("genes", []):
        query_parts.append(f'{gene}[Title/Abstract]')
        explanation_parts.append(f'Gene "{gene}" in title/abstract')
    
    # 2. MeSH terms (these are reliable, keep field tag)
    for mesh in elements.get("mesh", []):
        query_parts.append(f'"{mesh}"[MeSH]')
        explanation_parts.append(f'MeSH term "{mesh}"')
    
    # 3. Other terms — P1 fix: pass as RAW keywords, NO [Title/Abstract] wrapping
    # PubMed's search engine naturally handles them (MeSH auto-mapping, stemming, etc.)
    # Words that are already handled as article type filters — don't duplicate
    type_filter_words = {"review", "reviews", "trial", "clinical", "randomized", "rct",
                         "meta-analysis", "meta", "case", "case report", "case study"}
    
    processed_terms = set()
    raw_keyword_parts = []
    for term in elements.get("terms", []):
        term_lower = term.lower()
        # Skip if already processed as gene or mesh
        if term.upper() in elements.get("genes", []):
            continue
        if term_lower in [m.lower() for m in MESH_TERMS.keys()]:
            continue
        if term_lower in STOP_WORDS:
            continue
        if term_lower in type_filter_words:
            continue  # Already handled by article_type filter
        if term_lower in processed_terms:
            continue
        processed_terms.add(term_lower)
        raw_keyword_parts.append(term)
    
    if raw_keyword_parts:
        # Join raw keywords as a phrase/group — PubMed handles them naturally
        raw_query = " ".join(raw_keyword_parts)
        query_parts.append(f'({raw_query})')
        explanation_parts.append(f'Keywords: {raw_query}')
    
    # 4. Authors
    for author in elements.get("authors", []):
        query_parts.append(f'{author}[Author]')
        explanation_parts.append(f'Author "{author}"')
    
    # 5. Article type
    atype = article_type or elements.get("article_type")
    if atype:
        type_map = {
            "review": "Review[pt]",
            "clinical_trial": "Clinical Trial[pt]",
            "randomized": "Randomized Controlled Trial[pt]",
            "meta_analysis": "Meta-Analysis[pt]",
            "case_report": "Case Reports[pt]",
        }
        if atype in type_map:
            query_parts.append(type_map[atype])
            explanation_parts.append(f'Article type: {atype.replace("_", " ").title()}')
    
    # 6. Date range
    year_range = years or elements.get("year_range")
    if year_range:
        end = datetime.now()
        start = end - timedelta(days=year_range * 365)
        date_filter = f"{start.strftime('%Y/%m/%d')}:{end.strftime('%Y/%m/%d')}[PDat]"
        query_parts.append(date_filter)
        explanation_parts.append(f'Last {year_range} years')
    
    # 7. Additional MeSH filter
    if mesh_filter:
        query_parts.append(f'"{mesh_filter}"[MeSH]')
        explanation_parts.append(f'MeSH filter: "{mesh_filter}"')
    
    # Combine with AND
    if not query_parts:
        # Fallback: use raw query with stop words removed
        words = [w for w in query.split() if w.lower() not in STOP_WORDS and len(w) > 1]
        raw_query = " ".join(words[:8])
        query_parts = [f'({raw_query})']
    
    pubmed_query = " AND ".join(query_parts)
    explanation = " -> ".join(explanation_parts) if explanation_parts else "Keywords search"
    
    return pubmed_query, explanation


def search_pubmed(
    query: str,
    max_results: int = 10,
    api_key: Optional[str] = None,
    sort: str = "relevance",
    verbose: bool = False
) -> Dict[str, Any]:
    """Search PubMed and return PMIDs using shared http_get utility."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": sort  # P3 fix: allow sort order
    }
    
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
        if verbose or total_batches > 1:
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


def parse_pubmed_xml(xml_text: str) -> List[Dict[str, Any]]:
    """
    Parse PubMed XML response into structured data.
    
    P2 fix: Uses ElementTree instead of regex for robust XML parsing.
    Handles:
    - Structured abstracts (AbstractText with Label attribute)
    - Missing authors / CollectiveName authors
    - Inline tags in titles and abstracts (<i>, <b>, <sub>, etc.)
    - Various DOI formats
    """
    articles = []
    
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        # Fallback: if ElementTree fails, log warning and return empty
        print(f"Warning: Failed to parse PubMed XML: {e}", file=sys.stderr)
        return articles
    
    # Handle both <PubmedArticleSet> wrapper and bare articles
    article_elements = root.findall('.//PubmedArticle')
    if not article_elements:
        # Some responses may have <PubmedBookArticle> instead
        article_elements = root.findall('.//PubmedBookArticle')
    
    for article_elem in article_elements:
        article = {}
        
        medline_citation = article_elem.find('MedlineCitation')
        pubmed_data = article_elem.find('PubmedData')
        
        # PMID
        pmid_elem = None
        if medline_citation is not None:
            pmid_elem = medline_citation.find('PMID')
        if pmid_elem is not None and pmid_elem.text:
            article["pmid"] = pmid_elem.text
        
        # Title — handle inline tags via get_element_text
        article_elem_inner = medline_citation.find('Article') if medline_citation is not None else None
        if article_elem_inner is not None:
            title_elem = article_elem_inner.find('ArticleTitle')
            if title_elem is not None:
                article["title"] = get_element_text(title_elem)
        
        # Authors — handle both individual and collective authors
        authors = []
        if article_elem_inner is not None:
            author_list = article_elem_inner.find('AuthorList')
            if author_list is not None:
                for author_elem in author_list.findall('Author'):
                    collective = author_elem.find('CollectiveName')
                    if collective is not None and collective.text:
                        authors.append(collective.text)
                        continue
                    
                    last_name = author_elem.find('LastName')
                    fore_name = author_elem.find('ForeName')
                    if last_name is not None and last_name.text:
                        last = last_name.text
                        initial = ""
                        if fore_name is not None and fore_name.text:
                            initial = fore_name.text[0]
                        authors.append(f"{last} {initial}")
        article["authors"] = authors
        
        # Journal
        if article_elem_inner is not None:
            journal_elem = article_elem_inner.find('Journal')
            if journal_elem is not None:
                journal_title = journal_elem.find('Title')
                if journal_title is not None and journal_title.text:
                    article["journal"] = journal_title.text
        
        # Publication Year
        year = None
        if article_elem_inner is not None:
            journal_elem = article_elem_inner.find('Journal')
            if journal_elem is not None:
                journal_issue = journal_elem.find('JournalIssue')
                if journal_issue is not None:
                    pub_date = journal_issue.find('PubDate')
                    if pub_date is not None:
                        year_elem = pub_date.find('Year')
                        if year_elem is not None and year_elem.text:
                            year = year_elem.text
                        else:
                            # Try MedlineDate format (e.g., "2024 Jan-Feb")
                            medline_date = pub_date.find('MedlineDate')
                            if medline_date is not None and medline_date.text:
                                year_match = re.search(r'(\d{4})', medline_date.text)
                                if year_match:
                                    year = year_match.group(1)
        if year:
            article["year"] = year
        
        # Abstract — handles structured abstracts with Label attributes
        abstract_parts = []
        if article_elem_inner is not None:
            abstract_elem = article_elem_inner.find('Abstract')
            if abstract_elem is not None:
                for abstract_text in abstract_elem.findall('AbstractText'):
                    label = abstract_text.get('Label')
                    text_content = get_element_text(abstract_text)
                    if label and text_content:
                        abstract_parts.append(f"{label}: {text_content}")
                    elif text_content:
                        abstract_parts.append(text_content)
        if abstract_parts:
            article["abstract"] = " ".join(abstract_parts)
        
        # DOI — search in PubmedData ArticleIdList (more reliable)
        doi = None
        if pubmed_data is not None:
            article_id_list = pubmed_data.find('ArticleIdList')
            if article_id_list is not None:
                for article_id in article_id_list.findall('ArticleId'):
                    if article_id.get('IdType') == 'doi' and article_id.text:
                        doi = article_id.text
                        break
        # Fallback: search in ELocationID within Article
        if doi is None and article_elem_inner is not None:
            for elocation in article_elem_inner.findall('ELocationID'):
                if elocation.get('EIdType') == 'doi' and elocation.text:
                    doi = elocation.text
                    break
        if doi:
            article["doi"] = doi
        
        # MeSH Terms
        mesh_terms = []
        if medline_citation is not None:
            mesh_heading_list = medline_citation.find('MeshHeadingList')
            if mesh_heading_list is not None:
                for mesh_heading in mesh_heading_list.findall('MeshHeading'):
                    descriptor = mesh_heading.find('DescriptorName')
                    if descriptor is not None and descriptor.text:
                        mesh_terms.append(descriptor.text)
        if mesh_terms:
            article["mesh_terms"] = list(dict.fromkeys(mesh_terms))
        
        # URL
        if article.get("pmid"):
            article["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{article['pmid']}/"
        
        if article.get("pmid"):
            articles.append(article)
    
    return articles


def format_output(
    articles: List[Dict[str, Any]],
    total_count: int,
    query: str,
    explanation: str,
    format: str = "summary",
    full_abstract: bool = False,
    abstract_mode: str = DEFAULT_ABSTRACT_MODE
) -> str:
    """Format output for display.
    
    P1 fix: Abstract preview length raised from 200 to 1000 chars.
    full_abstract=True bypasses truncation entirely (backward compatible).
    abstract_mode: 'none' (no abstract), 'preview' (1000 chars), 'full' (complete).
    --full-abstract flag takes priority over abstract_mode.
    """
    
    if format == "json":
        output = {
            "pubmed_query": query,
            "query_explanation": explanation,
            "total_results": total_count,
            "returned": len(articles),
            "search_date": datetime.now().isoformat(),
            "articles": articles
        }
        return json.dumps(output, indent=2, ensure_ascii=False)
    
    # Summary format (default)
    lines = []
    lines.append("=" * 70)
    lines.append("PubMed Search Results")
    lines.append("=" * 70)
    lines.append(f"Query: {query}")
    lines.append(f"Parsed: {explanation}")
    lines.append(f"Total: {total_count} articles")
    lines.append(f"Returned: {len(articles)} articles")
    lines.append("=" * 70)
    
    for i, article in enumerate(articles, 1):
        lines.append(f"\n[{i}] PMID: {article.get('pmid', 'N/A')}")
        lines.append(f"Title: {article.get('title', 'N/A')}")
        
        authors = article.get("authors", [])
        if authors:
            author_str = ", ".join(authors[:5])
            if len(authors) > 5:
                author_str += f" et al. ({len(authors)} authors)"
            lines.append(f"Authors: {author_str}")
        
        journal = article.get("journal", "N/A")
        year = article.get("year", "N/A")
        lines.append(f"Journal: {journal} ({year})")
        
        if article.get("doi"):
            lines.append(f"DOI: {article['doi']}")
        
        if article.get("mesh_terms"):
            mesh_str = ", ".join(article["mesh_terms"][:5])
            if len(article["mesh_terms"]) > 5:
                mesh_str += " ..."
            lines.append(f"MeSH: {mesh_str}")
        
        # Determine effective abstract mode (--full-abstract takes priority)
        effective_mode = ABSTRACT_FULL if full_abstract else abstract_mode
        if effective_mode != ABSTRACT_NONE and article.get("abstract"):
            abstract = article["abstract"]
            if effective_mode == ABSTRACT_FULL:
                lines.append(f"Abstract: {abstract}")
            else:  # preview
                preview = abstract[:DEFAULT_ABSTRACT_LENGTH] + "..." if len(abstract) > DEFAULT_ABSTRACT_LENGTH else abstract
                lines.append(f"Abstract: {preview}")
        
        lines.append(f"URL: {article.get('url', 'N/A')}")
        lines.append("-" * 70)
    
    return "\n".join(lines)


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
    parser.add_argument("--max", type=int, default=10, help="最大返回结果数 (默认: 10)")
    parser.add_argument("--years", type=int, help="限制最近 N 年")
    parser.add_argument("--type", help="文章类型: review, clinical_trial, randomized, meta_analysis")
    parser.add_argument("--mesh", help="MeSH 主题词筛选")
    parser.add_argument("--sort", choices=["relevance", "pub_date", "Author", "Journal"], default="relevance",
                        help="排序方式: relevance(相关性), pub_date(日期), Author(作者), Journal(期刊)")
    parser.add_argument("--full-abstract", action="store_true", help="显示完整摘要（不截断）[向后兼容，等同 --abstract full]")
    parser.add_argument("--abstract", choices=ABSTRACT_CHOICES, default=DEFAULT_ABSTRACT_MODE,
                        help="摘要显示级别: none(仅标题元数据), preview(前1000字符,默认), full(完整摘要)")
    parser.add_argument("--format", choices=["json", "summary"], default="summary", help="输出格式")
    parser.add_argument("--output", "-o", help="保存到文件")
    parser.add_argument("--api-key", help="NCBI API key")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细信息")
    
    args = parser.parse_args()
    
    api_key = get_api_key(args)
    
    # P2 fix: Network error handling
    try:
        # Detect query elements
        elements = detect_query_elements(args.query)
        
        if args.verbose:
            print(f"检测到的元素: {json.dumps(elements, ensure_ascii=False, indent=2)}", file=sys.stderr)
        
        # Build PubMed query
        pubmed_query, explanation = build_pubmed_query(
            args.query,
            elements,
            years=args.years,
            article_type=args.type,
            mesh_filter=args.mesh
        )
        
        if args.verbose:
            print(f"PubMed 检索式: {pubmed_query}", file=sys.stderr)
        
        # Search
        search_result = search_pubmed(pubmed_query, args.max, api_key, args.sort, args.verbose)
        pmids = search_result["ids"]
        total = search_result["count"]
        
        if args.verbose:
            print(f"找到 {total} 篇文献, 获取 {len(pmids)} 篇...", file=sys.stderr)
        
        # Fetch articles
        articles = fetch_articles(pmids, api_key, args.verbose) if pmids else []
        
        # Format output
        output = format_output(articles, total, pubmed_query, explanation, args.format, args.full_abstract, args.abstract)
        
        # Print or save
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"已保存到 {args.output}", file=sys.stderr)
        else:
            print(output)
    
    except requests.exceptions.ConnectionError:
        print("Error: 无法连接到 NCBI 服务器，请检查网络连接。", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("Error: NCBI 服务器响应超时，请稍后重试或减少结果数(--max)。", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"Error: NCBI 服务器返回错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
