#!/usr/bin/env python3
"""
NCBI Multi-Database Search

Intelligent search across NCBI databases using E-Utilities API.
Automatically detects search intent and routes to appropriate database.

Supported databases:
- pubmed: Literature search (uses EFetch for full abstracts)
- gene: Gene information
- protein: Protein sequences
- nucleotide: Nucleotide sequences
- snp: SNP variants
- clinvar: Clinical variants
- taxonomy: Taxonomy
- biosample: Biological samples
- assembly: Genome assemblies
- sra: Sequence Read Archive

Usage:
    python ncbi_search.py "your query" [options]
    python ncbi_search.py "APOE gene" --db gene
    python ncbi_search.py "diabetes review" --db pubmed --years 5
"""

import os
import sys
import json
import argparse
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# Ensure we can import ncbi_utils and pubmed_search from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from ncbi_utils import (
        http_get, get_element_text, parse_pubmed_xml, truncate_abstract,
        NCBIError, PREVIEW_CHARS, date_filter, translate_chinese,
    )
except ImportError:
    print("Error: Could not import ncbi_utils.py from the scripts directory.", file=sys.stderr)
    sys.exit(1)

try:
    import requests
except ImportError:
    # ncbi_utils already handles this, but just in case
    print("Error: 'requests' library is required. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)

# NCBI E-Utilities Base URLs
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ESEARCH_URL = f"{EUTILS_BASE}/esearch.fcgi"
ESUMMARY_URL = f"{EUTILS_BASE}/esummary.fcgi"
EFETCH_URL = f"{EUTILS_BASE}/efetch.fcgi"

# Maximum IDs per EFetch request (NCBI recommended limit)
BATCH_SIZE = 200

# Database configurations
DATABASES = {
    "pubmed": {
        "name": "PubMed",
        "description": "Biomedical literature",
        "keywords": ["paper", "article", "review", "publication", "journal", "study", 
                     "论文", "文献", "研究", "发表", "文章", "综述"],
        "id_field": "PMID",
        "link_template": "https://pubmed.ncbi.nlm.nih.gov/{}/",
    },
    "gene": {
        "name": "Gene",
        "description": "Gene information",
        "keywords": ["gene", "symbol", "编码", "基因", "mrna", "expression", "转录"],
        "id_field": "Gene ID",
        "link_template": "https://www.ncbi.nlm.nih.gov/gene/{}",
    },
    "protein": {
        "name": "Protein",
        "description": "Protein sequences",
        "keywords": ["protein", "peptide", "amino", "蛋白", "多肽", "氨基酸", "sequence"],
        "id_field": "Accession",
        "link_template": "https://www.ncbi.nlm.nih.gov/protein/{}",
    },
    "nucleotide": {
        "name": "Nucleotide",
        "description": "Nucleotide sequences",
        "keywords": ["nucleotide", "dna", "rna", "sequence", "cdna",
                     "核酸", "序列", "基因组"],
        "id_field": "Accession",
        "link_template": "https://www.ncbi.nlm.nih.gov/nuccore/{}",
    },
    "snp": {
        "name": "dbSNP",
        "description": "SNP variants",
        "keywords": ["snp", "variant", "polymorphism", "allele",
                     "变异", "多态性", "突变"],
        "id_field": "rsID",
        "link_template": "https://www.ncbi.nlm.nih.gov/snp/{}",
    },
    "clinvar": {
        "name": "ClinVar",
        "description": "Clinical variants",
        "keywords": ["clinvar", "clinical variant", "pathogenic", "致病", "临床变异"],
        "id_field": "Variation ID",
        "link_template": "https://www.ncbi.nlm.nih.gov/clinvar/variation/{}",
    },
    "taxonomy": {
        "name": "Taxonomy",
        "description": "Taxonomy database",
        "keywords": ["species", "taxonomy", "organism", "classification", 
                     "物种", "分类", "物种分类"],
        "id_field": "TaxID",
        "link_template": "https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id={}",
    },
    "biosample": {
        "name": "BioSample",
        "description": "Biological samples",
        "keywords": ["biosample", "sample", "样本"],
        "id_field": "Sample ID",
        "link_template": "https://www.ncbi.nlm.nih.gov/biosample/{}",
    },
    "assembly": {
        "name": "Assembly",
        "description": "Genome assemblies",
        "keywords": ["assembly", "genome assembly", "基因组组装"],
        "id_field": "Assembly ID",
        "link_template": "https://www.ncbi.nlm.nih.gov/assembly/{}",
    },
    "sra": {
        "name": "SRA",
        "description": "Sequence Read Archive",
        "keywords": ["sra", "sequencing", "reads", "测序数据"],
        "id_field": "SRA ID",
        "link_template": "https://www.ncbi.nlm.nih.gov/sra/{}",
    },
}

# Known gene symbols (commonly referenced in neuroscience & cancer)
GENE_SYMBOLS = [
    "APOE", "APP", "PSEN1", "PSEN2", "TREM2", "MAPT", "SNCA", "TARDBP",
    "BRCA1", "BRCA2", "TP53", "EGFR", "KRAS", "MYC", "PTEN", "VEGF",
    "IL6", "TNF", "IFNG", "IL1B", "IL10", "TGFB1", "BDNF", "NGF",
]

# Academic stop words that look like genes but are not
ACADEMIC_STOP_WORDS = {
    "DNA", "RNA", "PCR", "SNP", "SRA", "PMID", "DOI", "URL", "PDF", 
    "AND", "OR", "NOT", "VS", "THE", "GENE", "GENOME", "CELL", "BODY", "N/A",
    "COVID", "COVID-19", "SARS", "SARS-COV-2", "MERS", "HIV"
}

# Abstract display tiers for progressive search (token optimization for AI agents)
ABSTRACT_NONE = "none"       # Tier 1: Title + metadata only (lowest token cost)
ABSTRACT_PREVIEW = "preview" # Tier 2: Sentence-aware abstract preview (~400 chars)
ABSTRACT_FULL = "full"       # Tier 3: Complete abstract (final selection)
ABSTRACT_CHOICES = [ABSTRACT_NONE, ABSTRACT_PREVIEW, ABSTRACT_FULL]
DEFAULT_ABSTRACT_MODE = ABSTRACT_NONE

# Article-type filters shared by both PubMed entry points
TYPE_FILTER = {
    "review": "Review[pt]",
    "clinical_trial": "Clinical Trial[pt]",
    "randomized": "Randomized Controlled Trial[pt]",
    "meta_analysis": "Meta-Analysis[pt]",
    "case_report": "Case Reports[pt]",
}


def get_api_key(args: argparse.Namespace) -> Optional[str]:
    """Get NCBI API key from args or environment."""
    if args.api_key:
        return args.api_key
    return os.environ.get("NCBI_API_KEY")


def _keyword_hit(keyword: str, query_lower: str) -> bool:
    """Match a database keyword; short keywords need word boundaries.

    Plain substring matching made any word containing "rs" (years, first,
    nurses) score for dbSNP, so <=3 char keywords are matched as words.
    """
    if len(keyword) <= 3:
        return re.search(r"\b" + re.escape(keyword) + r"\b", query_lower) is not None
    return keyword in query_lower


GENE_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9-]*\d[A-Z0-9-]*$")


def _looks_like_gene_symbol(token: str) -> bool:
    """True only for whitelist hits or digit-bearing symbols (BRCA1/SHANK3/P53).

    Pure alphabetic words (BLOOD, CANCER, STROKE, INSULIN) are ordinary
    English, not gene symbols, and must never route a query to the Gene
    database.
    """
    upper = token.upper()
    if upper in ACADEMIC_STOP_WORDS:
        return False
    if upper in GENE_SYMBOLS:
        return True
    return bool(GENE_TOKEN_RE.match(upper)) and 3 <= len(upper) <= 9


def detect_database(query: str) -> str:
    """
    Detect which NCBI database to search based on query.

    Priority:
    1. rs number pattern -> snp
    2. VCV number pattern (ClinVar variant) -> clinvar
    3. Known gene symbols (explicit whitelist) -> pubmed if literature words present
    4. Database keyword scoring; literature keywords force PubMed first
    5. Gene-symbol pattern (requires a digit, or a whitelist hit) -> gene
    6. Default -> pubmed
    """
    query_lower = query.lower()

    # 1. Check for rs number (dbSNP)
    if re.search(r'\brs\d+\b', query_lower):
        return "snp"

    # 2. Check for ClinVar variant identifier (e.g. VCV000242862)
    if re.search(r'\bVCV\d+\b', query, re.IGNORECASE):
        return "clinvar"

    # Common literature keywords used for routing
    literature_keywords = [
        "paper", "article", "review", "journal", "study", "trial", "trials", "clinical",
        "文献", "论文", "文章", "研究", "综述", "临床", "试验"
    ]

    # 3. Check for Known Gene Symbols (Explicit match)
    words = re.findall(r'\b[A-Za-z][A-Za-z0-9-]{1,8}\b', query)
    has_known_gene = any(word.upper() in GENE_SYMBOLS for word in words)
    if has_known_gene:
        if any(kw in query_lower for kw in literature_keywords):
            return "pubmed"
        return "gene"

    # 4. Check database keywords (literature intent wins over keyword scoring)
    db_scores = {}
    for db_name, db_info in DATABASES.items():
        if db_name == "pubmed":
            continue  # PubMed is the default fallback
        score = sum(1 for keyword in db_info["keywords"] if _keyword_hit(keyword, query_lower))
        if score > 0:
            db_scores[db_name] = score

    if db_scores:
        if any(kw in query_lower for kw in literature_keywords):
            return "pubmed"
        return max(db_scores, key=db_scores.get)

    # 5. Check for general gene-symbol patterns (digit required)
    if any(_looks_like_gene_symbol(word) for word in words):
        if any(kw in query_lower for kw in literature_keywords):
            return "pubmed"
        return "gene"

    # Default to PubMed
    return "pubmed"


# Common-name -> scientific-name mapping for the Gene database's [Organism]
# field (NCBI indexes scientific names only: "human" matches nothing useful).
ORGANISM_ALIASES = {
    "human": "Homo sapiens",
    "homo sapiens": "Homo sapiens",
    "mouse": "Mus musculus",
    "mice": "Mus musculus",
    "mus musculus": "Mus musculus",
    "rat": "Rattus norvegicus",
    "rattus norvegicus": "Rattus norvegicus",
    "zebrafish": "Danio rerio",
    "yeast": "Saccharomyces cerevisiae",
    "fly": "Drosophila melanogaster",
    "drosophila": "Drosophila melanogaster",
    "worm": "Caenorhabditis elegans",
    "pig": "Sus scrofa",
    "cow": "Bos taurus",
    "cattle": "Bos taurus",
    "dog": "Canis lupus familiaris",
    "chicken": "Gallus gallus",
    "monkey": "Macaca mulatta",
    "rhesus": "Macaca mulatta",
}

# Filler words allowed around a bare gene symbol ("APOE gene", "human APOE").
GENE_QUERY_FILLER = {
    "gene", "genes", "symbol", "name", "human", "mouse", "mice", "rat",
    "yeast", "fly", "worm", "pig", "cow", "dog", "chicken", "monkey",
    "zebrafish",
}


def _organism_term(organism: str) -> str:
    """Quote and map an organism filter for the Gene database."""
    name = ORGANISM_ALIASES.get(organism.strip().lower(), organism.strip())
    return f'"{name}"[Organism]'


def _gene_field_symbol(query: str) -> Optional[str]:
    """Return a gene symbol when the query is just "SYMBOL [gene|organism]".

    Gene DB free-text search for "APOE" matches 1,401 records (GeneRIF
    mentions, interactions, references). The authoritative field is
    [Gene Name]: APOE[Gene Name] AND "Homo sapiens"[Organism] returns exactly
    the gene record. Fall back to free text when the field search is empty.
    """
    tokens = re.findall(r"\b[A-Za-z][A-Za-z0-9-]*\b", query)
    symbols = []
    others = []
    for token in tokens:
        upper = token.upper()
        if upper in GENE_SYMBOLS or (
            GENE_TOKEN_RE.match(upper) and 3 <= len(upper) <= 9
            and upper not in ACADEMIC_STOP_WORDS
        ):
            symbols.append(token)
        else:
            others.append(token.lower())
    if len(symbols) != 1:
        return None
    if any(token not in GENE_QUERY_FILLER for token in others):
        return None
    return symbols[0]


_SNP_ID_RE = re.compile(r"\brs(\d+)\b", re.IGNORECASE)


def _snp_uid_term(query: str) -> Optional[str]:
    """Turn bare rsIDs (single or several) into a UID OR query.

    "rs429358"           -> "429358[UID]"
    "rs429358, rs7412"   -> "429358[UID] OR 7412[UID]"
    Free-text "rs429358" also matches old IDs merged into it (merged=1
    records), so rsID queries must use [UID]. Only converts when the whole
    query consists of rsIDs and separators.
    """
    ids = _SNP_ID_RE.findall(query)
    if not ids:
        return None
    remainder = _SNP_ID_RE.sub("", query)
    if remainder.strip(" ,;\t\r\n"):
        return None
    return " OR ".join(f"{uid}[UID]" for uid in dict.fromkeys(ids))


def search_database(
    query: str,
    database: str,
    max_results: int = 10,
    api_key: Optional[str] = None,
    organism: Optional[str] = None,
    sort: str = "relevance",
    verbose: bool = False,
    offset: int = 0,
) -> Dict[str, Any]:
    """Search any NCBI database using shared http_get utility."""
    search_query = query
    
    # Add organism filter for gene database (common names -> scientific names)
    if database == "gene" and organism:
        search_query = f"({query}) AND {_organism_term(organism)}"
    
    params = {
        "db": database,
        "term": search_query,
        "retmax": max_results,
        "retmode": "json",
    }
    if offset > 0:
        params["retstart"] = offset
    if database == "pubmed":
        # ESearch only honours sort for PubMed; other databases reject values
        # like pub_date/Author and may fail the whole request.
        params["sort"] = sort

    if api_key:
        params["api_key"] = api_key

    response_text = http_get(ESEARCH_URL, params=params, api_key=api_key, timeout=30, verbose=verbose)
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        if "<error" in response_text.lower():
            raise NCBIError("NCBI ESearch returned an error: " + " ".join(response_text.split())[:300])
        raise
    result = data.get("esearchresult") or {}
    if result.get("ERROR"):
        raise NCBIError(f"NCBI ESearch error: {result['ERROR']}")

    return {
        "database": database,
        "query": search_query,
        "count": int(result.get("count", 0)),
        "ids": result.get("idlist", []),
    }


def fetch_summary(
    ids: List[str],
    database: str,
    api_key: Optional[str] = None,
    verbose: bool = False
) -> List[Dict[str, Any]]:
    """Fetch summary for records using ESummary (batched, max 200 UIDs per call)."""
    if not ids:
        return []

    records = []
    for i in range(0, len(ids), BATCH_SIZE):
        batch = ids[i:i + BATCH_SIZE]
        params = {
            "db": database,
            "id": ",".join(batch),
            "retmode": "json",
        }
        if database == "pubmed":
            # v2.0 returns the full author list / pubdate / sortpubdate.
            params["version"] = "2.0"
        if api_key:
            params["api_key"] = api_key

        response_text = http_get(ESUMMARY_URL, params=params, api_key=api_key, timeout=60, verbose=verbose)
        data = json.loads(response_text)
        result = data.get("result", {})

        for id_ in batch:
            if id_ in result and isinstance(result[id_], dict):
                record = result[id_]
                record["_id"] = id_
                records.append(record)

    return records


def normalize_pubmed_summary(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map ESummary v2.0 records onto the EFetch-shaped dicts used by formatters."""
    out = []
    for rec in records:
        pmid = rec.get("uid") or rec.get("_id")
        if not pmid:
            continue
        item: Dict[str, Any] = {"pmid": str(pmid)}
        title = " ".join((rec.get("title") or "").split())
        if title:
            item["title"] = title
        authors = [a.get("name", "") for a in (rec.get("authors") or [])
                   if isinstance(a, dict) and a.get("name")]
        if authors:
            item["authors"] = authors
        journal = rec.get("fulljournalname") or rec.get("source")
        if journal:
            item["journal"] = " ".join(str(journal).split())
        pubdate = rec.get("pubdate") or rec.get("sortpubdate") or ""
        year_match = re.search(r"(\d{4})", str(pubdate))
        if year_match:
            item["year"] = year_match.group(1)
        doi = rec.get("elocationid") or ""
        doi = str(doi).strip()
        if doi.lower().startswith("doi:"):
            item["doi"] = doi[4:].strip()
        else:
            for aid in rec.get("articleids") or []:
                if isinstance(aid, dict) and aid.get("idtype") == "doi" and aid.get("value"):
                    item["doi"] = aid["value"]
                    break
        item["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        out.append(item)
    return out


def fetch_pubmed_articles(
    ids: List[str],
    api_key: Optional[str] = None,
    verbose: bool = False
) -> List[Dict[str, Any]]:
    """
    P0 fix: Fetch PubMed articles using EFetch instead of ESummary.
    ESummary does NOT return abstracts — EFetch does.
    P2 fix: Batch requests (max 200 IDs per EFetch) to avoid silent truncation.
    """
    if not ids:
        return []
    
    all_articles = []
    total_batches = (len(ids) + BATCH_SIZE - 1) // BATCH_SIZE
    
    for i in range(total_batches):
        batch = ids[i * BATCH_SIZE : (i + 1) * BATCH_SIZE]
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


def _meta_line(journal: Optional[str], year: Optional[str], authors: List[str]) -> str:
    """Compact one-line metadata: 'Journal (Year) | Author1, Author2, et al.'"""
    parts = []
    if journal:
        parts.append(f"{journal} ({year})" if year else str(journal))
    if authors:
        author_str = ", ".join(authors[:3])
        if len(authors) > 3:
            author_str += " et al."
        parts.append(author_str)
    return " | ".join(parts)


def format_pubmed_results(records: List[Dict], total: int, query: str, full_abstract: bool = False, abstract_mode: str = DEFAULT_ABSTRACT_MODE) -> str:
    """Format PubMed results (compact, token-optimized).

    abstract_mode: 'none' (title + metadata), 'preview' (sentence-aware ~400 chars),
    'full' (complete abstract + DOI + MeSH). URL is derivable from PMID and is
    intentionally omitted here (JSON keeps it).
    """
    effective_mode = ABSTRACT_FULL if full_abstract else abstract_mode
    lines = [f"# PubMed | query: {query} | total: {total} | shown: {len(records)}"]
    if not records:
        lines.append("No results.")
        return "\n".join(lines)

    for i, record in enumerate(records, 1):
        pmid = record.get("pmid", record.get("_id", "N/A"))
        authors = record.get("authors") or []
        if authors and isinstance(authors[0], dict):
            authors = [a.get("name", "") for a in authors if isinstance(a, dict)]
        journal = record.get("journal") or record.get("fulljournalname") or record.get("source")
        year = record.get("year")
        if not year:
            pubdate = record.get("pubdate", "")
            year = pubdate.split()[0] if pubdate else ""
        meta = _meta_line(journal, year, authors)

        lines.append("")
        lines.append(f"[{i}] PMID {pmid}" + (f" | {meta}" if meta else ""))
        lines.append(f"Title: {record.get('title', 'N/A')}")

        if effective_mode == ABSTRACT_FULL and record.get("abstract"):
            lines.append(f"Abstract: {record['abstract']}")
        elif effective_mode == ABSTRACT_PREVIEW and record.get("abstract"):
            lines.append(f"Abstract: {truncate_abstract(record['abstract'])}")

        if effective_mode == ABSTRACT_FULL:
            if record.get("doi"):
                lines.append(f"DOI: {record['doi']}")
            if record.get("mesh_terms"):
                mesh_str = ", ".join(record["mesh_terms"][:5])
                if len(record["mesh_terms"]) > 5:
                    mesh_str += " ..."
                lines.append(f"MeSH: {mesh_str}")

    return "\n".join(lines)


def format_gene_results(records: List[Dict], total: int, query: str) -> str:
    """Format Gene results (compact)."""
    lines = [f"# Gene | query: {query} | total: {total} | shown: {len(records)}"]
    if not records:
        lines.append("No results.")
        return "\n".join(lines)

    for i, record in enumerate(records, 1):
        lines.append("")
        lines.append(f"[{i}] GeneID {record.get('_id', 'N/A')} | {record.get('name', 'N/A')}")
        if record.get("description"):
            lines.append(f"  {record['description']}")
        extra = []
        if record.get("chromosome"):
            extra.append(f"chr{record['chromosome']}")
        organism = record.get("organism")
        if isinstance(organism, dict):
            organism = organism.get("scientificname")
        if organism:
            extra.append(str(organism))
        if extra:
            lines.append("  " + " | ".join(extra))

    return "\n".join(lines)


def format_snp_results(records: List[Dict], total: int, query: str) -> str:
    """Format dbSNP results (compact): rsID | genes | location | MAF | clinical."""
    lines = [f"# dbSNP | query: {query} | total: {total} | shown: {len(records)}"]
    if not records:
        lines.append("No results.")
        return "\n".join(lines)

    for i, record in enumerate(records, 1):
        snp_id = record.get("_id", "N/A")
        genes = [g.get("name", "") for g in (record.get("genes") or [])
                 if isinstance(g, dict) and g.get("name")]
        parts = [f"[{i}] rs{snp_id}"]
        if genes:
            parts.append("/".join(genes))
        loc = record.get("chrpos") or ""
        if loc:
            parts.append(loc if loc.startswith("chr") else f"chr{loc}")
        mafs = record.get("global_mafs") or []
        if mafs:
            freq = str(mafs[0].get("freq", "")).split("/")[0]
            if "=" in freq:
                allele, value = freq.split("=", 1)
                try:
                    value = f"{float(value):.3f}"
                except ValueError:
                    pass
                freq = f"{allele}={value}"
            study = str(mafs[0].get("study", ""))
            if freq:
                parts.append(f"MAF {freq}" + (f" ({study})" if study else ""))
        if str(record.get("merged")) == "1":
            parts.append(f"merged->rs{record.get('snp_id')}")
        clinical = record.get("clinical_significance") or ""
        if clinical:
            items = [item for item in str(clinical).split(",") if item]
            parts.append(", ".join(items[:4]) + (" ..." if len(items) > 4 else ""))
        lines.append("")
        lines.append(" | ".join(parts))

    return "\n".join(lines)


def _get(record: Dict[str, Any], *path, default=""):
    """Safe nested lookup: _get(rec, 'germline_classification', 'description')."""
    current = record
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def format_clinvar_results(records: List[Dict], total: int, query: str) -> str:
    """Format ClinVar results: VCV accession | variation | classification | location | trait."""
    lines = [f"# ClinVar | query: {query} | total: {total} | shown: {len(records)}"]
    if not records:
        lines.append("No results.")
        return "\n".join(lines)

    for i, record in enumerate(records, 1):
        acc = record.get("accession") or record.get("uid", "N/A")
        variations = _get(record, "variation_set", default=[]) or [{}]
        first = variations[0] if variations else {}
        name = first.get("variation_name") or record.get("title") or ""
        germline = record.get("germline_classification") or {}
        clinical = record.get("clinical_impact_classification") or {}
        classification = germline.get("description") or clinical.get("description") or ""
        review = germline.get("review_status") or clinical.get("review_status") or ""
        traits = [t.get("trait_name") for t in (germline.get("trait_set") or [])
                  if isinstance(t, dict) and t.get("trait_name")]
        locations = first.get("variation_loc") or []
        loc = ""
        if locations:
            first_loc = locations[0]
            loc = (f"chr{first_loc.get('chr', '')}:"
                   f"{first_loc.get('start', '')}-{first_loc.get('stop', '')} "
                   f"({first_loc.get('assembly_name', '')})").strip()

        parts = [f"[{i}] {acc}"]
        if name:
            parts.append(name)
        if classification:
            parts.append(classification + (f", {review}" if review else ""))
        if loc:
            parts.append(loc)
        if traits:
            parts.append("; ".join(traits[:2]))
        lines.append("")
        lines.append(" | ".join(parts))

    return "\n".join(lines)


def _sra_xml_field(xml: str, pattern: str) -> str:
    match = re.search(pattern, xml or "")
    return match.group(1) if match else ""


def format_sra_results(records: List[Dict], total: int, query: str) -> str:
    """Format SRA results: experiment accession | study | organism | strategy | spots."""
    lines = [f"# SRA | query: {query} | total: {total} | shown: {len(records)}"]
    if not records:
        lines.append("No results.")
        return "\n".join(lines)

    for i, record in enumerate(records, 1):
        xml = record.get("expxml") or ""
        acc = _sra_xml_field(xml, r'<Experiment acc="([^"]+)"') or record.get("_id", "N/A")
        study = _sra_xml_field(xml, r'<Study acc="[^"]*" name="([^"]*)"')
        organism = _sra_xml_field(xml, r'ScientificName="([^"]+)"')
        strategy = _sra_xml_field(xml, r"<LIBRARY_STRATEGY>([^<]*)</LIBRARY_STRATEGY>")
        spots = _sra_xml_field(xml, r'total_spots="(\d+)"')
        date = str(record.get("createdate", "")).split(" ")[0]

        parts = [f"[{i}] {acc}"]
        if study:
            parts.append(study)
        if organism:
            parts.append(organism)
        if strategy:
            parts.append(strategy)
        if spots:
            parts.append(f"{int(spots):,} spots")
        if date:
            parts.append(date)
        lines.append("")
        lines.append(" | ".join(parts))

    return "\n".join(lines)


def format_assembly_results(records: List[Dict], total: int, query: str) -> str:
    """Format Assembly results: accession | name | organism | status | category | date."""
    lines = [f"# Assembly | query: {query} | total: {total} | shown: {len(records)}"]
    if not records:
        lines.append("No results.")
        return "\n".join(lines)

    for i, record in enumerate(records, 1):
        acc = record.get("assemblyaccession") or record.get("_id", "N/A")
        name = record.get("assemblyname") or ""
        organism = record.get("organism") or ""
        status = record.get("assemblystatus") or ""
        category = record.get("refseq_category") or ""
        date = str(record.get("asmreleasedate_refseq")
                   or record.get("asmreleasedate_genbank") or "").split(" ")[0]
        parts = [f"[{i}] {acc}"]
        if name:
            parts.append(name)
        if organism:
            parts.append(organism)
        if status:
            parts.append(status)
        if category and category != "na":
            parts.append(category)
        if date:
            parts.append(date)
        lines.append("")
        lines.append(" | ".join(parts))

    return "\n".join(lines)


def format_biosample_results(records: List[Dict], total: int, query: str) -> str:
    """Format BioSample results: accession | title | organism | owner | date."""
    lines = [f"# BioSample | query: {query} | total: {total} | shown: {len(records)}"]
    if not records:
        lines.append("No results.")
        return "\n".join(lines)

    for i, record in enumerate(records, 1):
        acc = record.get("accession") or record.get("_id", "N/A")
        title = record.get("title") or ""
        organism = record.get("organism") or ""
        organization = record.get("organization") or ""
        date = str(record.get("publicationdate") or record.get("date") or "").split(" ")[0]
        parts = [f"[{i}] {acc}"]
        if title:
            parts.append(title)
        if organism:
            parts.append(organism)
        if organization:
            parts.append(organization)
        if date:
            parts.append(date)
        lines.append("")
        lines.append(" | ".join(parts))

    return "\n".join(lines)


def format_taxonomy_results(records: List[Dict], total: int, query: str) -> str:
    """Format Taxonomy results: taxid | scientific name (common) | rank | division."""
    lines = [f"# Taxonomy | query: {query} | total: {total} | shown: {len(records)}"]
    if not records:
        lines.append("No results.")
        return "\n".join(lines)

    for i, record in enumerate(records, 1):
        taxid = record.get("_id", "N/A")
        name = record.get("scientificname") or ""
        common = record.get("commonname") or ""
        rank = record.get("rank") or ""
        division = record.get("division") or record.get("genbankdivision") or ""
        display = name + (f" ({common})" if common else "")
        parts = [f"[{i}] {taxid}", display]
        if rank:
            parts.append(rank)
        if division:
            parts.append(division)
        lines.append("")
        lines.append(" | ".join(parts))

    return "\n".join(lines)


def format_generic_results(records: List[Dict], total: int, query: str, database: str) -> str:
    """Format results for any database (compact)."""
    db_name = DATABASES.get(database, {}).get("name", database.upper())
    lines = [f"# {db_name} | query: {query} | total: {total} | shown: {len(records)}"]
    if not records:
        lines.append("No results.")
        return "\n".join(lines)

    for i, record in enumerate(records, 1):
        record_id = record.get("_id", "N/A")
        title = record.get("title") or record.get("name") or record.get("description") or ""
        lines.append("")
        lines.append(f"[{i}] {record_id}" + (f" | {title}" if title else ""))

    return "\n".join(lines)


FORMATTERS = {
    "gene": format_gene_results,
    "snp": format_snp_results,
    "clinvar": format_clinvar_results,
    "sra": format_sra_results,
    "assembly": format_assembly_results,
    "biosample": format_biosample_results,
    "taxonomy": format_taxonomy_results,
}


def format_results(records: List[Dict], total: int, query: str, database: str, full_abstract: bool = False, abstract_mode: str = DEFAULT_ABSTRACT_MODE) -> str:
    """Format results based on database type."""
    if database == "pubmed":
        return format_pubmed_results(records, total, query, full_abstract, abstract_mode)
    formatter = FORMATTERS.get(database)
    if formatter:
        return formatter(records, total, query)
    return format_generic_results(records, total, query, database)


def trim_json_record(record: Dict[str, Any], mode: str) -> Dict[str, Any]:
    """Apply the --abstract tier to JSON output (it used to be ignored entirely)."""
    rec = dict(record)
    if "_id" in rec:
        rec["id"] = rec.pop("_id")
    if mode == ABSTRACT_NONE:
        for key in ("abstract", "mesh_terms", "doi"):
            rec.pop(key, None)
    elif mode == ABSTRACT_PREVIEW:
        rec.pop("mesh_terms", None)
        if rec.get("abstract"):
            rec["abstract"] = truncate_abstract(rec["abstract"])
    return rec


def main():
    parser = argparse.ArgumentParser(
        description="NCBI Multi-Database Search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s "Alzheimer disease review"
    %(prog)s "APOE gene" --db gene --organism human
    %(prog)s "diabetes" --db pubmed --years 5 --type review
    %(prog)s "Alzheimer" --db pubmed --sort pub_date --max 20
        """
    )
    
    parser.add_argument("query", help="Search query")
    parser.add_argument("--db", choices=list(DATABASES.keys()), help="Database to search (auto-detected if not specified)")
    parser.add_argument("--max", type=int, default=10, help="Maximum results (default: 10, max 200)")
    parser.add_argument("--years", type=int, help="Years filter (PubMed only)")
    parser.add_argument("--min-year", type=int, help="Earliest publication year (PubMed only; wins over --years)")
    parser.add_argument("--max-year", type=int, help="Latest publication year (PubMed only; wins over --years)")
    parser.add_argument("--offset", type=int, default=0, help="Skip the first N results (paging)")
    parser.add_argument("--type", help="Article type (PubMed only): review, clinical_trial, randomized, meta_analysis, case_report")
    parser.add_argument("--organism", help="Organism filter (Gene only)")
    parser.add_argument("--sort", choices=["relevance", "pub_date", "Author", "Journal"], default="relevance",
                        help="Sort order: relevance, pub_date, Author, Journal (PubMed only)")
    parser.add_argument("--full-abstract", action="store_true", help="Show full abstracts without truncation (PubMed only) [same as --abstract full]")
    parser.add_argument("--abstract", choices=ABSTRACT_CHOICES, default=DEFAULT_ABSTRACT_MODE,
                        help="Abstract tier: none(title+metadata, default), preview(~400 chars), full(complete)")
    parser.add_argument("--format", choices=["json", "summary"], default="summary")
    parser.add_argument("--count-only", action="store_true", help="Only print the result count (no record fetch)")
    parser.add_argument("--output", "-o", help="Save to file")
    parser.add_argument("--api-key", help="NCBI API key")
    parser.add_argument("--verbose", "-v", action="store_true")
    
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
        # Detect or use specified database
        database = args.db if args.db else detect_database(args.query)
        
        if args.verbose:
            print(f"Database: {DATABASES[database]['name']}", file=sys.stderr)
            print(f"Query: {args.query}", file=sys.stderr)
        
        # Build query with filters (common Chinese terms -> English first)
        query = translate_chinese(args.query)
        base_query = query
        if args.verbose and query != args.query:
            print(f"Translated query: {query}", file=sys.stderr)
        
        # PubMed-specific filters
        if database == "pubmed":
            date_part = date_filter(args.years, args.min_year, args.max_year)
            if date_part:
                query = f"({query}) AND {date_part}"
            if args.type:
                atype = args.type.strip().lower()
                if atype in TYPE_FILTER:
                    query = f"({query}) AND {TYPE_FILTER[atype]}"
                else:
                    print(f"Warning: unknown --type {args.type!r} ignored", file=sys.stderr)

        # dbSNP: bare rsIDs must be searched by UID; free text also matches
        # old IDs merged into them (merged=1 records).
        if database == "snp":
            snp_term = _snp_uid_term(args.query)
            if snp_term:
                query = snp_term

        # Search (Gene DB: use [Gene Name] for bare symbols, fall back to free text)
        if database == "gene":
            symbol = _gene_field_symbol(query)
            if symbol:
                term = f"{symbol}[Gene Name]"
                if args.organism:
                    term += f" AND {_organism_term(args.organism)}"
                search_result = search_database(term, "gene", args.max, api_key, None, args.sort, args.verbose, offset=args.offset)
                query = term
                if search_result["count"] == 0:
                    fallback = f"({base_query})"
                    if args.organism:
                        fallback += f" AND {_organism_term(args.organism)}"
                    search_result = search_database(fallback, "gene", args.max, api_key, None, args.sort, args.verbose, offset=args.offset)
                    query = fallback
            else:
                search_result = search_database(query, "gene", args.max, api_key, args.organism, args.sort, args.verbose, offset=args.offset)
        else:
            search_result = search_database(query, database, args.max, api_key, args.organism, args.sort, args.verbose, offset=args.offset)
        ids = search_result["ids"]
        total = search_result["count"]
        
        if args.verbose:
            print(f"Found {total} results", file=sys.stderr)
        
        effective_mode = ABSTRACT_FULL if args.full_abstract else args.abstract

        if args.count_only:
            print(f"# {DATABASES[database]['name']} | query: {query} | total: {total}")
            return

        # Tier 1 uses ESummary (small JSON, no abstracts); preview/full use EFetch XML.
        if database == "pubmed":
            if effective_mode == ABSTRACT_NONE and ids:
                records = normalize_pubmed_summary(fetch_summary(ids, "pubmed", api_key, args.verbose))
            else:
                records = fetch_pubmed_articles(ids, api_key, args.verbose) if ids else []
        else:
            records = fetch_summary(ids, database, api_key, args.verbose) if ids else []
        
        # Format output
        if args.format == "json":
            payload = {
                "database": database,
                "query": query,
                "total": total,
                "records": [trim_json_record(r, effective_mode) for r in records],
            }
            if args.offset:
                payload["offset"] = args.offset
            output = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        else:
            output = format_results(records, total, query, database, args.full_abstract, args.abstract)
        
        # Print or save
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"Saved to {args.output}", file=sys.stderr)
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
