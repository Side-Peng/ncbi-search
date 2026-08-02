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
    from ncbi_utils import http_get, get_element_text
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
        "keywords": ["nucleotide", "dna", "rna", "sequence", "genome", "cdna",
                     "核酸", "序列", "基因组"],
        "id_field": "Accession",
        "link_template": "https://www.ncbi.nlm.nih.gov/nuccore/{}",
    },
    "snp": {
        "name": "dbSNP",
        "description": "SNP variants",
        "keywords": ["snp", "variant", "polymorphism", "allele", "rs", 
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

# Default abstract preview length (raised from 200 to 1000)
DEFAULT_ABSTRACT_LENGTH = 1000

# Abstract display tiers for progressive search (token optimization for AI agents)
ABSTRACT_NONE = "none"       # Tier 1: Title + metadata only (lowest token cost)
ABSTRACT_PREVIEW = "preview" # Tier 2: First 1000 chars of abstract (current default)
ABSTRACT_FULL = "full"       # Tier 3: Complete abstract (final selection)
ABSTRACT_CHOICES = [ABSTRACT_NONE, ABSTRACT_PREVIEW, ABSTRACT_FULL]
DEFAULT_ABSTRACT_MODE = ABSTRACT_PREVIEW


def get_api_key(args: argparse.Namespace) -> Optional[str]:
    """Get NCBI API key from args or environment."""
    if args.api_key:
        return args.api_key
    return os.environ.get("NCBI_API_KEY")


def detect_database(query: str) -> str:
    """
    Detect which NCBI database to search based on query.
    
    Priority:
    1. rs number pattern -> snp
    2. VCV number pattern (ClinVar variant) -> clinvar
    3. Known Gene symbols (explicit match) -> gene / pubmed (if has paper keywords)
    4. Database keywords matching (non-pubmed high specificity keywords)
    5. General Gene symbol pattern (regex match) -> gene / pubmed
    6. Default -> pubmed
    
    P2 fix: Removed duplicate dead code block (old lines 224-236).
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
    has_known_gene = False
    for word in words:
        if word.upper() in GENE_SYMBOLS:
            has_known_gene = True
            break
    if has_known_gene:
        if any(kw in query_lower for kw in literature_keywords):
            return "pubmed"
        return "gene"
        
    # 4. Check database keywords (focus on specific ones — P2 fix: no duplicate)
    db_scores = {}
    for db_name, db_info in DATABASES.items():
        if db_name == "pubmed":
            continue  # PubMed is default fallback, only evaluate specific DBs here
        score = 0
        for keyword in db_info["keywords"]:
            if keyword in query_lower:
                score += 1
        if score > 0:
            db_scores[db_name] = score
            
    if db_scores:
        # Return highest scoring specific database
        return max(db_scores, key=db_scores.get)
        
    # 5. Check for General Gene Symbols (Regex match)
    has_potential_gene = False
    for word in words:
        word_upper = word.upper()
        # Pattern A: 4-8 chars (e.g. BRCA1, SHANK3)
        is_pattern_a = re.match(r'^[A-Z][A-Z0-9-]{3,7}$', word_upper)
        # Pattern B: 3 chars but containing digit (e.g. P53, IL6)
        is_pattern_b = re.match(r'^[A-Z][A-Z0-9-]{2}$', word_upper) and any(c.isdigit() for c in word_upper)
        
        if (is_pattern_a or is_pattern_b) and (
            word_upper not in ACADEMIC_STOP_WORDS
            and not word_upper.isdigit()
        ):
            has_potential_gene = True
            break
            
    if has_potential_gene:
        if any(kw in query_lower for kw in literature_keywords):
            return "pubmed"
        return "gene"
    
    # Default to PubMed
    return "pubmed"


def search_database(
    query: str,
    database: str,
    max_results: int = 10,
    api_key: Optional[str] = None,
    organism: Optional[str] = None,
    sort: str = "relevance",
    verbose: bool = False
) -> Dict[str, Any]:
    """Search any NCBI database using shared http_get utility."""
    search_query = query
    
    # Add organism filter for gene database
    if database == "gene" and organism:
        search_query = f"({query}) AND {organism}[Organism]"
    
    params = {
        "db": database,
        "term": search_query,
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
    """Fetch summary for records using ESummary and shared http_get."""
    if not ids:
        return []
    
    params = {
        "db": database,
        "id": ",".join(ids),
        "retmode": "json"
    }
    
    if api_key:
        params["api_key"] = api_key
        
    response_text = http_get(ESUMMARY_URL, params=params, api_key=api_key, timeout=60, verbose=verbose)
    data = json.loads(response_text)
    result = data.get("result", {})
    
    records = []
    for id_ in ids:
        if id_ in result and isinstance(result[id_], dict):
            record = result[id_]
            record["_id"] = id_
            records.append(record)
    
    return records


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
    """Parse PubMed XML response using ElementTree for robustness."""
    articles = []
    
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"Warning: Failed to parse PubMed XML: {e}", file=sys.stderr)
        return articles
    
    article_elements = root.findall('.//PubmedArticle')
    
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
        
        # Title
        article_elem_inner = medline_citation.find('Article') if medline_citation is not None else None
        if article_elem_inner is not None:
            title_elem = article_elem_inner.find('ArticleTitle')
            if title_elem is not None:
                article["title"] = get_element_text(title_elem)
        
        # Authors
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
                            medline_date = pub_date.find('MedlineDate')
                            if medline_date is not None and medline_date.text:
                                year_match = re.search(r'(\d{4})', medline_date.text)
                                if year_match:
                                    year = year_match.group(1)
        if year:
            article["year"] = year
        
        # Abstract (P0 fix: now included in PubMed results!)
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
        
        # DOI
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


def format_pubmed_results(records: List[Dict], total: int, query: str, full_abstract: bool = False, abstract_mode: str = DEFAULT_ABSTRACT_MODE) -> str:
    """Format PubMed results — P0 fix: now includes abstracts.
    
    abstract_mode: 'none' (no abstract), 'preview' (1000 chars), 'full' (complete).
    --full-abstract flag takes priority over abstract_mode.
    """
    lines = []
    lines.append("=" * 70)
    lines.append("PubMed Search Results")
    lines.append("=" * 70)
    lines.append(f"Query: {query}")
    lines.append(f"Total: {total} articles | Returned: {len(records)} articles")
    lines.append("=" * 70)
    
    for i, record in enumerate(records, 1):
        lines.append(f"\n[{i}] PMID: {record.get('pmid', record.get('_id', 'N/A'))}")
        lines.append(f"Title: {record.get('title', 'N/A')}")
        
        # Authors — handle both EFetch format (list of strings) and ESummary format (list of dicts)
        authors = record.get("authors", [])
        if authors:
            if isinstance(authors[0], dict):
                # ESummary format
                author_names = [a.get("name", "") for a in authors[:5] if isinstance(a, dict)]
                author_str = ", ".join(author_names)
            else:
                # EFetch format
                author_str = ", ".join(authors[:5])
            if len(authors) > 5:
                author_str += f" et al. ({len(authors)} authors)"
            lines.append(f"Authors: {author_str}")
        
        # Year — handle both formats
        year = record.get("year", "N/A")
        if year == "N/A":
            pubdate = record.get("pubdate", "")
            year = pubdate.split()[0] if pubdate else "N/A"
        
        # Journal — handle both formats
        journal = record.get("journal", record.get("fulljournalname", record.get("source", "N/A")))
        lines.append(f"Journal: {journal} ({year})")
        
        if record.get("doi"):
            lines.append(f"DOI: {record['doi']}")
        
        # P0 fix: Abstract is now included! Determine effective mode (--full-abstract takes priority)
        effective_mode = ABSTRACT_FULL if full_abstract else abstract_mode
        if effective_mode != ABSTRACT_NONE and record.get("abstract"):
            abstract = record["abstract"]
            if effective_mode == ABSTRACT_FULL:
                lines.append(f"Abstract: {abstract}")
            else:  # preview
                preview = abstract[:DEFAULT_ABSTRACT_LENGTH] + "..." if len(abstract) > DEFAULT_ABSTRACT_LENGTH else abstract
                lines.append(f"Abstract: {preview}")
        
        # MeSH terms (only from EFetch)
        if record.get("mesh_terms"):
            mesh_str = ", ".join(record["mesh_terms"][:5])
            if len(record["mesh_terms"]) > 5:
                mesh_str += " ..."
            lines.append(f"MeSH: {mesh_str}")
        
        lines.append(f"URL: https://pubmed.ncbi.nlm.nih.gov/{record.get('pmid', record.get('_id'))}/")
        lines.append("-" * 70)
    
    return "\n".join(lines)


def format_gene_results(records: List[Dict], total: int, query: str) -> str:
    """Format Gene results."""
    lines = []
    lines.append("=" * 70)
    lines.append("Gene Search Results")
    lines.append("=" * 70)
    lines.append(f"Query: {query}")
    lines.append(f"Total: {total} genes | Returned: {len(records)} genes")
    lines.append("=" * 70)
    
    for i, record in enumerate(records, 1):
        lines.append(f"\n[{i}] Gene ID: {record.get('_id', 'N/A')}")
        lines.append(f"Symbol: {record.get('name', 'N/A')}")
        lines.append(f"Description: {record.get('description', 'N/A')}")
        
        if record.get("chromosome"):
            lines.append(f"Chromosome: {record['chromosome']}")
        
        if record.get("organism"):
            organism = record["organism"]
            if isinstance(organism, dict):
                lines.append(f"Organism: {organism.get('scientificname', 'N/A')}")
            else:
                lines.append(f"Organism: {organism}")
        
        lines.append(f"URL: https://www.ncbi.nlm.nih.gov/gene/{record.get('_id')}")
        lines.append("-" * 70)
    
    return "\n".join(lines)


def format_snp_results(records: List[Dict], total: int, query: str) -> str:
    """Format SNP results."""
    lines = []
    lines.append("=" * 70)
    lines.append("dbSNP Search Results")
    lines.append("=" * 70)
    lines.append(f"Query: {query}")
    lines.append(f"Total: {total} variants | Returned: {len(records)} variants")
    lines.append("=" * 70)
    
    for i, record in enumerate(records, 1):
        snp_id = record.get("_id", "N/A")
        lines.append(f"\n[{i}] rsID: rs{snp_id}")
        
        if record.get("snp_id"):
            lines.append(f"Reference SNP: {record['snp_id']}")
        
        if record.get("genes"):
            genes = record["genes"]
            if isinstance(genes, list):
                gene_names = [g.get("name", "") for g in genes if isinstance(g, dict)]
                lines.append(f"Genes: {', '.join(gene_names)}")
        
        lines.append(f"URL: https://www.ncbi.nlm.nih.gov/snp/rs{snp_id}")
        lines.append("-" * 70)
    
    return "\n".join(lines)


def format_generic_results(records: List[Dict], total: int, query: str, database: str) -> str:
    """Format results for any database."""
    db_name = DATABASES.get(database, {}).get("name", database.upper())
    
    lines = []
    lines.append("=" * 70)
    lines.append(f"{db_name} Search Results")
    lines.append("=" * 70)
    lines.append(f"Query: {query}")
    lines.append(f"Total: {total} records | Returned: {len(records)} records")
    lines.append("=" * 70)
    
    for i, record in enumerate(records, 1):
        lines.append(f"\n[{i}] ID: {record.get('_id', 'N/A')}")
        
        # Common fields
        if record.get("title"):
            lines.append(f"Title: {record['title']}")
        if record.get("name"):
            lines.append(f"Name: {record['name']}")
        if record.get("description"):
            lines.append(f"Description: {record['description']}")
        
        link_template = DATABASES.get(database, {}).get("link_template", "")
        if link_template:
            lines.append(f"URL: {link_template.format(record.get('_id', ''))}")
        
        lines.append("-" * 70)
    
    return "\n".join(lines)


def format_results(records: List[Dict], total: int, query: str, database: str, full_abstract: bool = False, abstract_mode: str = DEFAULT_ABSTRACT_MODE) -> str:
    """Format results based on database type."""
    if database == "pubmed":
        return format_pubmed_results(records, total, query, full_abstract, abstract_mode)
    elif database == "gene":
        return format_gene_results(records, total, query)
    elif database == "snp":
        return format_snp_results(records, total, query)
    else:
        return format_generic_results(records, total, query, database)


def main():
    parser = argparse.ArgumentParser(
        description="NCBI Multi-Database Search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Literature search (auto-detect)
    %(prog)s "Alzheimer disease review"
    
    # Gene search (auto-detect)
    %(prog)s "APOE gene"
    
    # SNP search (auto-detect)
    %(prog)s "rs429358"
    
    # Specify database
    %(prog)s "APOE" --db gene --organism human
    %(prog)s "insulin" --db protein
    
    # PubMed with filters and full abstracts
    %(prog)s "diabetes" --db pubmed --years 5 --type review --full-abstract
    
    # Sort by date
    %(prog)s "Alzheimer" --db pubmed --sort pub_date --max 20
        """
    )
    
    parser.add_argument("query", help="Search query")
    parser.add_argument("--db", choices=list(DATABASES.keys()), help="Database to search (auto-detected if not specified)")
    parser.add_argument("--max", type=int, default=10, help="Maximum results (default: 10)")
    parser.add_argument("--years", type=int, help="Years filter (PubMed only)")
    parser.add_argument("--type", help="Article type (PubMed only): review, clinical_trial, etc.")
    parser.add_argument("--organism", help="Organism filter (Gene only)")
    parser.add_argument("--sort", choices=["relevance", "pub_date", "Author", "Journal"], default="relevance",
                        help="Sort order: relevance, pub_date, Author, Journal")
    parser.add_argument("--full-abstract", action="store_true", help="Show full abstracts without truncation (PubMed only) [backward compatible, same as --abstract full]")
    parser.add_argument("--abstract", choices=ABSTRACT_CHOICES, default=DEFAULT_ABSTRACT_MODE,
                        help="Abstract display level: none(title+metadata only), preview(first 1000 chars, default), full(complete abstract). PubMed only.")
    parser.add_argument("--format", choices=["json", "summary"], default="summary")
    parser.add_argument("--output", "-o", help="Save to file")
    parser.add_argument("--api-key", help="NCBI API key")
    parser.add_argument("--verbose", "-v", action="store_true")
    
    args = parser.parse_args()
    
    api_key = get_api_key(args)
    
    # P2 fix: Network error handling
    try:
        # Detect or use specified database
        database = args.db if args.db else detect_database(args.query)
        
        if args.verbose:
            print(f"Database: {DATABASES[database]['name']}", file=sys.stderr)
            print(f"Query: {args.query}", file=sys.stderr)
        
        # Build query with filters
        query = args.query
        
        # PubMed-specific filters
        if database == "pubmed":
            if args.years:
                end = datetime.now()
                start = end - timedelta(days=args.years * 365)
                query = f"({query}) AND {start.strftime('%Y/%m/%d')}:{end.strftime('%Y/%m/%d')}[PDat]"
            if args.type:
                type_map = {
                    "review": "Review[pt]",
                    "clinical_trial": "Clinical Trial[pt]",
                    "randomized": "Randomized Controlled Trial[pt]",
                    "meta_analysis": "Meta-Analysis[pt]",
                }
                if args.type in type_map:
                    query = f"({query}) AND {type_map[args.type]}"
        
        # Search
        search_result = search_database(query, database, args.max, api_key, args.organism, args.sort, args.verbose)
        ids = search_result["ids"]
        total = search_result["count"]
        
        if args.verbose:
            print(f"Found {total} results", file=sys.stderr)
        
        # P0 fix: For PubMed, use EFetch (returns full abstracts)
        # For other databases, use ESummary
        if database == "pubmed":
            records = fetch_pubmed_articles(ids, api_key, args.verbose) if ids else []
        else:
            records = fetch_summary(ids, database, api_key, args.verbose) if ids else []
        
        # Format output
        if args.format == "json":
            output = json.dumps({
                "database": database,
                "query": query,
                "total_count": total,
                "records": records
            }, indent=2, ensure_ascii=False)
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
