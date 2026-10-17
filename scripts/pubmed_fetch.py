#!/usr/bin/env python3
"""
PubMed Fetch - Batch retrieve articles by PMID

Fetch full article details from PubMed given a list of PMIDs.
P3 fix: Supports batch processing (200 PMIDs per EFetch request) for large lists.

Usage:
    python pubmed_fetch.py PMID1 PMID2 PMID3 ...
    python pubmed_fetch.py --file pmids.txt
    python pubmed_fetch.py 12345678 --format summary --full-abstract
"""

import os
import sys
import json
import argparse
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from ncbi_utils import NCBIError

# Import from pubmed_search
from pubmed_search import (
    fetch_articles, get_api_key, format_output,
    ABSTRACT_CHOICES, DEFAULT_ABSTRACT_MODE
)

# P3 fix: Maximum PMIDs per EFetch request (NCBI recommended limit)
BATCH_SIZE = 200


def read_pmids_from_file(filepath: str) -> List[str]:
    """Read PMIDs from file (one per line)."""
    pmids = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and line.isdigit():
                pmids.append(line)
    return pmids


def fetch_articles_batched(
    pmids: List[str],
    api_key: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
    verbose: bool = False
) -> list:
    """
    P3 fix: Fetch articles in batches to avoid NCBI EFetch limits.
    NCBI recommends max 200 IDs per EFetch request.
    """
    if not pmids:
        return []
    
    all_articles = []
    total_batches = (len(pmids) + batch_size - 1) // batch_size
    
    for i in range(total_batches):
        batch = pmids[i * batch_size : (i + 1) * batch_size]
        if verbose:
            print(f"Fetching batch {i + 1}/{total_batches} ({len(batch)} PMIDs)...", file=sys.stderr)
        
        articles = fetch_articles(batch, api_key, verbose)
        all_articles.extend(articles)
        
        # Small delay between batches to respect rate limits
        if i < total_batches - 1:
            import time
            time.sleep(0.5)
    
    return all_articles


def main():
    parser = argparse.ArgumentParser(
        description="Fetch PubMed articles by PMID",
        epilog="""
Examples:
    %(prog)s 12345678 98765432
    %(prog)s --file pmids.txt --output results.json
    %(prog)s 12345678 --format summary --full-abstract
    %(prog)s --file large_pmids.txt  # auto-batches 200 PMIDs per request
        """
    )
    
    parser.add_argument("pmids", nargs="*", help="PMIDs to fetch")
    parser.add_argument("--file", "-f", help="File containing PMIDs (one per line)")
    parser.add_argument("--format", choices=["json", "summary"], default="summary")
    parser.add_argument("--full-abstract", action="store_true", help="显示完整摘要（不截断）[等同 --abstract full]")
    parser.add_argument("--abstract", choices=ABSTRACT_CHOICES, default=DEFAULT_ABSTRACT_MODE,
                        help="摘要显示级别: none(仅标题元数据, 默认), preview(~400字符按句截断), full(完整摘要)")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, 
                        help=f"每批获取的最大 PMID 数 (默认: {BATCH_SIZE}, 上限 200)")
    parser.add_argument("--output", "-o", help="Save to file")
    parser.add_argument("--api-key", help="NCBI API key")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细信息")
    
    args = parser.parse_args()

    if args.batch_size < 1 or args.batch_size > 200:
        args.batch_size = max(1, min(args.batch_size, 200))
        print(f"Warning: --batch-size adjusted to {args.batch_size} (allowed 1-200)", file=sys.stderr)
    
    # Collect PMIDs
    pmids = args.pmids
    if args.file:
        pmids.extend(read_pmids_from_file(args.file))
    
    if not pmids:
        print("Error: No PMIDs provided", file=sys.stderr)
        sys.exit(1)
    
    # Validate PMIDs (dedupe, drop non-numeric with a hint)
    raw_count = len(pmids)
    pmids = list(dict.fromkeys(p for p in pmids if p.isdigit()))
    skipped = raw_count - len(pmids)
    if skipped:
        print(f"Warning: {skipped} duplicate or non-numeric PMID(s) skipped", file=sys.stderr)
    
    if not pmids:
        print("Error: No valid PMIDs found", file=sys.stderr)
        sys.exit(1)
    
    api_key = get_api_key(args)
    
    try:
        if args.verbose:
            print(f"Fetching {len(pmids)} articles...", file=sys.stderr)
        
        # Use batched fetching for large lists
        articles = fetch_articles_batched(pmids, api_key, args.batch_size, args.verbose)
        
        output = format_output(articles, len(articles), "PMID fetch", "Batch fetch by PMID", args.format, args.full_abstract, args.abstract)
        
        # Output
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
        print("Error: NCBI request timed out; retry or lower --batch-size.", file=sys.stderr)
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
