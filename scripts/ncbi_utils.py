#!/usr/bin/env python3
"""
NCBI Utility Functions

Shared utilities for NCBI E-Utilities API calls with built-in SQLite caching.
"""

import os
import sys

# P0 fix: Windows GBK encoding crash — reconfigure stdout/stderr to UTF-8
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        # Python < 3.7 doesn't have reconfigure; fallback to wrapper
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# P3 fix: Check for requests library with helpful error message
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("Error: 'requests' library is required but not installed.", file=sys.stderr)
    print("Please install it with: pip install requests", file=sys.stderr)
    sys.exit(1)

import re
import time
import sqlite3
import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional

# Rate limiting state
LAST_REQUEST_TIME = 0
MIN_REQUEST_INTERVAL = 0.34  # ~3 requests/second without API key
SESSION = None

# Token budget for the "preview" abstract tier (sentence-aware, not a hard cut).
PREVIEW_CHARS = 400

# Canonical version marker (keep in sync with references/changelog.md).
__version__ = "4.0.0"

# Cache Settings
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".ncbi_cache")
CACHE_DB_PATH = os.path.join(CACHE_DIR, "cache.db")
try:
    CACHE_EXPIRE_HOURS = int(os.environ.get("NCBI_CACHE_EXPIRE_HOURS", 24))
except ValueError:
    CACHE_EXPIRE_HOURS = 24


class NCBIError(RuntimeError):
    """Raised when NCBI returns an E-Utilities error body (HTTP 200 + <ERROR>).

    These responses must never be cached: they would poison the cache for
    CACHE_EXPIRE_HOURS and silently turn every search into "0 results".
    """


def create_session():
    """Create a session with retry logic (GET only; honours Retry-After)."""
    session = requests.Session()
    retry_strategy = Retry(
        total=4,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        respect_retry_after_header=True,
        allowed_methods=frozenset(["GET"]),
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_session():
    """Get or create the global session."""
    global SESSION
    if SESSION is None:
        SESSION = create_session()
    return SESSION


def rate_limit(api_key: Optional[str] = None):
    """Enforce rate limiting (monotonic clock: NTP jumps cannot produce negative sleeps)."""
    global LAST_REQUEST_TIME
    interval = 0.11 if api_key else MIN_REQUEST_INTERVAL
    now = time.monotonic()
    elapsed = now - LAST_REQUEST_TIME
    if elapsed < interval:
        time.sleep(interval - elapsed)
        now = time.monotonic()
    LAST_REQUEST_TIME = now


_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+')
_ABSTRACT_LABEL_RE = re.compile(
    r'\b(BACKGROUND|INTRODUCTION|OBJECTIVE[S]?|AIM[S]?|PURPOSE|METHOD[S]?|MATERIALS|'
    r'DESIGN|SETTING|PARTICIPANTS?|PATIENTS|INTERVENTIONS?|MAIN OUTCOME MEASURES?|'
    r'MEASUREMENTS?|RESULTS?|FINDINGS?|DISCUSSION|CONCLUSIONS?|SIGNIFICANCE|IMPORTANCE|'
    r'LIMITATIONS?|EVIDENCE|CONTEXT|FUNDING)\s*:\s*',
    re.IGNORECASE,
)


def _cut_soft(text: str, limit: int) -> str:
    """Cut text at a sentence/space boundary, never beyond ``limit`` chars."""
    if len(text) <= limit:
        return text
    window = text[:limit]
    cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "), window.rfind("; "))
    if cut > limit // 2:
        return window[: cut + 1]
    cut = window.rfind(" ")
    return window[:cut] if cut > 0 else window


def date_filter(years: Optional[int] = None,
                min_year: Optional[int] = None,
                max_year: Optional[int] = None) -> Optional[str]:
    """Build a PubMed [PDat] filter.

    --min-year/--max-year win over --years when both are given.
    Returns None when no date constraint was requested.
    """
    if min_year or max_year:
        start = min_year or 1900
        end = max_year or datetime.now().year
        return f"{start}:{end}[PDat]"
    if years:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=years * 365)
        return f"{start_dt.strftime('%Y/%m/%d')}:{end_dt.strftime('%Y/%m/%d')}[PDat]"
    return None


def truncate_abstract(text: str, limit: int = PREVIEW_CHARS) -> str:
    """Token-cheap abstract preview that keeps the *conclusion*, not just the intro.

    Structured abstracts are re-assembled in priority order
    (CONCLUSIONS -> RESULTS -> DISCUSSION -> rest) and cut at sentence
    boundaries, so a 400-char preview is far more useful for literature
    screening than the first 400 characters of BACKGROUND.
    """
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text

    matches = list(_ABSTRACT_LABEL_RE.finditer(text))
    if matches:
        segments = []
        for i, match in enumerate(matches):
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                segments.append((match.group(1).upper(), body))
    else:
        segments = [("", text)]

    priority = ("CONCLUSIONS", "CONCLUSION", "DISCUSSION", "RESULTS", "FINDINGS",
                "SIGNIFICANCE", "IMPORTANCE")
    ordered = []
    for label in priority:
        for segment in segments:
            if segment[0] == label and segment not in ordered:
                ordered.append(segment)
    for segment in segments:
        if segment not in ordered:
            ordered.append(segment)

    out = ""
    for _, body in ordered:
        for sentence in _SENT_SPLIT.split(body):
            candidate = (out + " " + sentence).strip() if out else sentence
            if len(candidate) > limit:
                if not out:
                    out = _cut_soft(sentence, limit)
                return out.rstrip(". ") + " ..."
            out = candidate
        if len(out) >= limit * 0.8:
            break
    return out


def _inject_metadata(params: dict):
    """Add NCBI-required tool identifier (and email when configured).

    NCBI asks every E-Utilities caller to identify itself with ``tool`` and
    ``email``; omitted tool IDs can be throttled without notice.
    """
    params.setdefault("tool", "ncbi-search")
    email = os.environ.get("NCBI_EMAIL")
    if email:
        params.setdefault("email", email)


def _looks_like_error_body(text: str) -> bool:
    """Detect E-Utilities error XML served with HTTP 200."""
    head = text.lstrip()[:5000]
    if not head:
        return False
    low = head.lower()
    if low.startswith("{") or low.startswith("["):
        return False  # JSON bodies are validated by the callers
    return "<error" in low or "error>" in low


def _error_text(text: str, limit: int = 300) -> str:
    plain = re.sub(r"<[^>]+>", " ", text[:5000])
    return " ".join(plain.split())[:limit]


# Best-effort Chinese -> English mapping for common biomedical terms.
# PubMed/Gene/... index English text only; a Chinese query otherwise returns 0.
# Longest entries win ("阿尔茨海默病" before "阿尔茨海默", "蛋白质" before "蛋白").
CHINESE_TERMS = {
    # Diseases
    "阿尔茨海默病": "Alzheimer disease",
    "阿尔茨海默": "Alzheimer",
    "帕金森病": "Parkinson disease",
    "帕金森": "Parkinson",
    "神经退行性疾病": "neurodegenerative disease",
    "心血管疾病": "cardiovascular disease",
    "慢性阻塞性肺疾病": "chronic obstructive pulmonary disease",
    "多发性硬化": "multiple sclerosis",
    "系统性红斑狼疮": "systemic lupus erythematosus",
    "类风湿关节炎": "rheumatoid arthritis",
    "冠心病": "coronary heart disease",
    "心肌梗死": "myocardial infarction",
    "心力衰竭": "heart failure",
    "脑卒中": "stroke",
    "中风": "stroke",
    "糖尿病": "diabetes",
    "高血压": "hypertension",
    "抑郁症": "depression",
    "精神分裂症": "schizophrenia",
    "癫痫": "epilepsy",
    "自闭症": "autism",
    "肥胖": "obesity",
    "哮喘": "asthma",
    "肝硬化": "liver cirrhosis",
    "肾衰竭": "kidney failure",
    "骨质疏松": "osteoporosis",
    "痛风": "gout",
    "贫血": "anemia",
    "白血病": "leukemia",
    "淋巴瘤": "lymphoma",
    "乳腺癌": "breast cancer",
    "肺癌": "lung cancer",
    "肝癌": "liver cancer",
    "胃癌": "gastric cancer",
    "结直肠癌": "colorectal cancer",
    "前列腺癌": "prostate cancer",
    "宫颈癌": "cervical cancer",
    "癌症": "cancer",
    "肿瘤标志物": "tumor marker",
    "肿瘤": "tumor",
    "癌": "cancer",
    # Biology
    "单核苷酸多态性": "single nucleotide polymorphism",
    "神经退行性": "neurodegenerative",
    "生物标志物": "biomarker",
    "标志物": "marker",
    "信号通路": "signaling pathway",
    "通路": "pathway",
    "转录组": "transcriptome",
    "基因组": "genome",
    "表观遗传": "epigenetics",
    "蛋白质": "protein",
    "蛋白": "protein",
    "基因": "gene",
    "突变": "mutation",
    "变异": "variant",
    "免疫": "immune",
    "炎症": "inflammation",
    "靶点": "target",
    "细胞": "cell",
    "组织": "tissue",
    "血液": "blood",
    "脑": "brain",
    "心脏": "heart",
    "肝脏": "liver",
    "肾脏": "kidney",
    "肺": "lung",
    "人类": "human",
    "小鼠": "mouse",
    "大鼠": "rat",
    "斑马鱼": "zebrafish",
    "酵母": "yeast",
    "果蝇": "fruit fly",
    "线虫": "C. elegans",
    # Methods / clinical
    "随机对照试验": "randomized controlled trial",
    "荟萃分析": "meta-analysis",
    "Meta分析": "meta-analysis",
    "临床试验": "clinical trial",
    "病例报告": "case report",
    "队列研究": "cohort study",
    "横断面研究": "cross-sectional study",
    "不良反应": "adverse event",
    "安全性": "safety",
    "机制": "mechanism",
    "疗效": "efficacy",
    "预后": "prognosis",
    "诊断": "diagnosis",
    "治疗": "treatment",
    "药物": "drug",
    "剂量": "dose",
    "综述": "review",
}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def translate_chinese(query: str) -> str:
    """Map common Chinese biomedical terms to English (best effort).

    Unknown Chinese text is left untouched; callers can hint at translation.
    """
    if not _CJK_RE.search(query):
        return query
    result = query
    for zh in sorted(CHINESE_TERMS, key=len, reverse=True):
        if zh in result:
            result = result.replace(zh, f" {CHINESE_TERMS[zh]} ")
    for punct in "，、。；：（）【】":
        result = result.replace(punct, " ")
    return " ".join(result.split())


def clean_xml_tags(text: str) -> str:
    """Remove XML tags and clean whitespace."""
    import re
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def get_element_text(element) -> str:
    """Recursively extract all text content from an ElementTree element.
    
    Handles mixed content (text with inline tags like <i>, <b>, <sub>).
    """
    text_parts = []
    if element.text:
        text_parts.append(element.text)
    for child in element:
        text_parts.append(get_element_text(child))
        if child.tail:
            text_parts.append(child.tail)
    return "".join(text_parts).strip()


def parse_pubmed_xml(xml_text: str) -> list:
    """Parse an EFetch (db=pubmed) XML response into article dicts.

    Single shared implementation used by ncbi_search.py, pubmed_search.py and
    pubmed_fetch.py (the two local copies had already drifted apart).
    Handles PubmedBookArticle records, structural abstracts, collective authors
    and inline formatting tags.
    """
    articles = []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"Warning: Failed to parse PubMed XML: {e}", file=sys.stderr)
        return articles

    article_elements = root.findall('.//PubmedArticle')
    if not article_elements:
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

        article_elem_inner = medline_citation.find('Article') if medline_citation is not None else None

        # Title (inline tags flattened)
        if article_elem_inner is not None:
            title_elem = article_elem_inner.find('ArticleTitle')
            if title_elem is not None:
                article["title"] = get_element_text(title_elem)

        # Authors (individual + collective)
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
                        initial = ""
                        if fore_name is not None and fore_name.text:
                            initial = fore_name.text[0]
                        authors.append(f"{last_name.text} {initial}")
        article["authors"] = authors

        # Journal
        if article_elem_inner is not None:
            journal_elem = article_elem_inner.find('Journal')
            if journal_elem is not None:
                journal_title = journal_elem.find('Title')
                if journal_title is not None and journal_title.text:
                    article["journal"] = journal_title.text

        # Publication year (Year or MedlineDate fallback)
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
                            medline_date = pub_date.find('MedlineDate')
                            if medline_date is not None and medline_date.text:
                                year_match = re.search(r'(\d{4})', medline_date.text)
                                if year_match:
                                    year = year_match.group(1)
        if year:
            article["year"] = year

        # Abstract (structured labels preserved)
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

        # DOI (PubmedData id list first, ELocationID fallback)
        doi = None
        if pubmed_data is not None:
            article_id_list = pubmed_data.find('ArticleIdList')
            if article_id_list is not None:
                for article_id in article_id_list.findall('ArticleId'):
                    if article_id.get('IdType') == 'doi' and article_id.text:
                        doi = article_id.text
                        break
        if doi is None and article_elem_inner is not None:
            for elocation in article_elem_inner.findall('ELocationID'):
                if elocation.get('EIdType') == 'doi' and elocation.text:
                    doi = elocation.text
                    break
        if doi:
            article["doi"] = doi

        # MeSH terms
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
            articles.append(article)

    return articles


def init_cache():
    """Initialize the SQLite database for caching."""
    if os.environ.get("NCBI_NO_CACHE") == "1":
        return
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_cache (
                key TEXT PRIMARY KEY,
                value TEXT,
                expires_at REAL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_expires_at ON api_cache(expires_at)")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: Failed to initialize cache database: {e}", file=sys.stderr)


def _connect():
    """Open the cache DB with a busy timeout and WAL (safe for parallel scripts)."""
    conn = sqlite3.connect(CACHE_DB_PATH, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
    except Exception:
        pass
    return conn


# Cap cache growth (PMC full-text XML adds up quickly). 0 disables pruning.
try:
    CACHE_MAX_ROWS = int(os.environ.get("NCBI_CACHE_MAX_ROWS", 5000))
except ValueError:
    CACHE_MAX_ROWS = 5000


def _prune_cache(cursor):
    if CACHE_MAX_ROWS <= 0:
        return
    try:
        cursor.execute("SELECT COUNT(*) FROM api_cache")
        count = cursor.fetchone()[0]
        if count > CACHE_MAX_ROWS:
            cursor.execute(
                "DELETE FROM api_cache WHERE key IN ("
                "SELECT key FROM api_cache ORDER BY expires_at ASC LIMIT ?)",
                (count - CACHE_MAX_ROWS,),
            )
    except Exception:
        pass


def get_cache_key(url: str, params: dict) -> str:
    """Generate a unique SHA256 key for URL and sorted params."""
    # P3 fix: Exclude api_key from cache key to share cache across different keys
    # (NCBI returns the same data regardless of which API key is used)
    cache_params = {k: v for k, v in params.items() if k != "api_key"}
    serialized_params = json.dumps(cache_params, sort_keys=True)
    raw_key = f"{url}?{serialized_params}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def get_cached_response(url: str, params: dict) -> Optional[str]:
    """Retrieve cached response if it exists and has not expired."""
    if os.environ.get("NCBI_NO_CACHE") == "1":
        return None
    
    init_cache()
    
    try:
        conn = _connect()
        cursor = conn.cursor()
        
        # Clean up expired items
        cursor.execute("DELETE FROM api_cache WHERE expires_at < ?", (time.time(),))
        conn.commit()
        
        key = get_cache_key(url, params)
        cursor.execute("SELECT value FROM api_cache WHERE key = ? AND expires_at >= ?", (key, time.time()))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return row[0]
    except Exception as e:
        print(f"Warning: Failed to read from cache: {e}", file=sys.stderr)
        
    return None


def set_cache_response(url: str, params: dict, value: str):
    """Save response to local cache with an expiration time."""
    if os.environ.get("NCBI_NO_CACHE") == "1":
        return
        
    init_cache()
    
    try:
        conn = _connect()
        cursor = conn.cursor()
        key = get_cache_key(url, params)
        expires_at = time.time() + (CACHE_EXPIRE_HOURS * 3600)
        cursor.execute(
            "INSERT OR REPLACE INTO api_cache (key, value, expires_at) VALUES (?, ?, ?)",
            (key, value, expires_at)
        )
        _prune_cache(cursor)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: Failed to write to cache: {e}", file=sys.stderr)


def http_get(url: str, params: dict, api_key: Optional[str] = None, timeout: int = 30, verbose: bool = False) -> str:
    """
    Perform a GET request with rate limiting and local SQLite caching.
    Returns response text.

    Raises NCBIError (and does NOT cache) when NCBI returns an error body,
    so a bad query can never be silently cached as an empty result set.
    """
    _inject_metadata(params)

    # Try local cache first
    cached = get_cached_response(url, params)
    if cached is not None:
        if verbose:
            print(f"[Cache Hit] {url.split('/')[-1]}", file=sys.stderr)
        return cached

    if verbose:
        print(f"[Cache Miss] Fetching from NCBI: {url.split('/')[-1]}", file=sys.stderr)

    # Enforce rate limit
    rate_limit(api_key)

    # Request from NCBI (connect timeout 10 s, read timeout from the caller)
    session = get_session()
    response = session.get(url, params=params, timeout=(10, timeout))
    response.raise_for_status()

    response_text = response.text

    if _looks_like_error_body(response_text):
        raise NCBIError(f"NCBI returned an error: {_error_text(response_text)}")

    # Save to cache (only valid responses)
    set_cache_response(url, params, response_text)

    return response_text
