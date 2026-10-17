#!/usr/bin/env python3
"""
NCBI Search Skill Unit Tests

Test suite to verify database detection, rate limiting, and SQLite caching.
"""

import os
import sys
import unittest
import time
import shutil
import sqlite3
from datetime import datetime

# Adjust paths to import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ncbi_utils import get_cached_response, set_cache_response, get_cache_key, rate_limit
import ncbi_utils
from ncbi_search import detect_database
from pmc_fetch import normalize_pmcid, parse_pmc_xml


class TestNCBISearchSkill(unittest.TestCase):
    
    def setUp(self):
        """Prepare isolation for tests."""
        # Isolate cache database to a test database
        self.original_cache_dir = ncbi_utils.CACHE_DIR
        self.original_cache_db = ncbi_utils.CACHE_DB_PATH
        
        self.test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".test_ncbi_cache")
        ncbi_utils.CACHE_DIR = self.test_dir
        ncbi_utils.CACHE_DB_PATH = os.path.join(self.test_dir, "test_cache.db")
        
        # Clean potential leftovers
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
            
        os.makedirs(self.test_dir, exist_ok=True)
        
        # Ensure NCBI_NO_CACHE is not active during cache tests
        self.original_no_cache = os.environ.get("NCBI_NO_CACHE")
        if "NCBI_NO_CACHE" in os.environ:
            del os.environ["NCBI_NO_CACHE"]

    def tearDown(self):
        """Restore global states and clean up test files."""
        ncbi_utils.CACHE_DIR = self.original_cache_dir
        ncbi_utils.CACHE_DB_PATH = self.original_cache_db
        
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
            
        if self.original_no_cache is not None:
            os.environ["NCBI_NO_CACHE"] = self.original_no_cache
        elif "NCBI_NO_CACHE" in os.environ:
            del os.environ["NCBI_NO_CACHE"]

    def test_database_detection(self):
        """Test the intelligence and routing of detect_database."""
        # 1. dbSNP rs patterns
        self.assertEqual(detect_database("rs429358"), "snp")
        self.assertEqual(detect_database("Show me details of rs1112"), "snp")
        
        # 2. ClinVar VCV patterns
        self.assertEqual(detect_database("VCV000242862"), "clinvar")
        self.assertEqual(detect_database("clinvar variation VCV000012345"), "clinvar")
        
        # 3. Known Genes
        self.assertEqual(detect_database("APOE gene"), "gene")
        self.assertEqual(detect_database("BRCA1 expression"), "gene")
        
        # 4. Universal Gene Regex Match (un-hardcoded genes)
        self.assertEqual(detect_database("SHANK3 function"), "gene")
        self.assertEqual(detect_database("FMR1 mutation"), "gene")
        
        # 5. Gene/Disease combined with publication keywords -> PubMed
        self.assertEqual(detect_database("APOE review"), "pubmed")
        self.assertEqual(detect_database("SHANK3 paper on autism"), "pubmed")
        self.assertEqual(detect_database("COVID-19 vaccine clinical trial"), "pubmed")
        
        # 6. Database keywords
        self.assertEqual(detect_database("Escherichia coli taxonomy"), "taxonomy")
        self.assertEqual(detect_database("human protein sequence"), "protein")
        self.assertEqual(detect_database("yeast genome assembly"), "assembly")
        
        # 7. Default fallback to PubMed
        self.assertEqual(detect_database("flu treatment and prevention"), "pubmed")

    def test_sqlite_cache_write_and_read(self):
        """Test that data can be correctly saved to and loaded from local SQLite cache."""
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {"db": "pubmed", "term": "Alzheimer"}
        response_text = '{"esearchresult": {"count": "150000", "idlist": ["123", "456"]}}'
        
        # Verify first check is a miss
        self.assertIsNone(get_cached_response(url, params))
        
        # Set cache
        set_cache_response(url, params, response_text)
        
        # Verify second check is a hit
        cached = get_cached_response(url, params)
        self.assertEqual(cached, response_text)

    def test_cache_invalidation_by_no_cache_env(self):
        """Test that setting NCBI_NO_CACHE=1 bypasses caching."""
        os.environ["NCBI_NO_CACHE"] = "1"
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {"db": "pubmed", "term": "Alzheimer"}
        response_text = '{"some": "data"}'
        
        # Should not write to cache when disabled
        set_cache_response(url, params, response_text)
        self.assertIsNone(get_cached_response(url, params))

    def test_rate_limiting(self):
        """Test rate limiting interval mechanism."""
        # Temporarily shorten default interval to speed up tests, but keeping it measurable
        ncbi_utils.MIN_REQUEST_INTERVAL = 0.1
        
        start_time = time.time()
        rate_limit()  # 1st call
        rate_limit()  # 2nd call (should block until 0.1s elapsed)
        rate_limit()  # 3rd call (should block until 0.2s elapsed)
        duration = time.time() - start_time
        
        # The total time for 3 calls with 2 intervals of 0.1s should be at least 0.2s
        self.assertGreaterEqual(duration, 0.18)

    def test_pmc_id_normalization(self):
        """Test normalize_pmcid strips the PMC prefix and validates numeric ids."""
        self.assertEqual(normalize_pmcid("PMC8241728"), "8241728")
        self.assertEqual(normalize_pmcid("pmc8241728"), "8241728")
        self.assertEqual(normalize_pmcid("8241728"), "8241728")
        self.assertEqual(normalize_pmcid("  PMC123  "), "123")
        with self.assertRaises(ValueError):
            normalize_pmcid("not-an-id")
        with self.assertRaises(ValueError):
            normalize_pmcid("")

    def test_parse_pmc_fulltext_xml(self):
        """Test parse_pmc_xml extracts metadata and full body text from JATS XML."""
        xml = """<?xml version="1.0"?><pmc-articleset><article>
          <front><journal-meta><journal-title-group><journal-title>Test Journal</journal-title></journal-title-group></journal-meta>
            <article-meta>
              <article-id pub-id-type="pmcid">PMC999999</article-id>
              <article-id pub-id-type="pmid">12345678</article-id>
              <article-id pub-id-type="doi">10.1000/test.001</article-id>
              <title-group><article-title>A Study of <i>Something</i> Important</article-title></title-group>
              <contrib-group>
                <contrib contrib-type="author"><name><surname>Zhang</surname><given-names>Huiqin</given-names></name></contrib>
                <contrib contrib-type="author"><name><surname>Wei</surname><given-names>Wei</given-names></name></contrib>
              </contrib-group>
              <pub-date><year>2021</year></pub-date>
              <abstract><p>This is the abstract text.</p></abstract>
            </article-meta></front>
          <body>
            <sec><title>Introduction</title><p>First intro paragraph.</p>
              <sec><title>Background</title><p>Nested background paragraph.</p></sec>
            </sec>
            <sec><title>Conclusion</title><p>Final conclusion paragraph.</p></sec>
          </body></article></pmc-articleset>"""
        articles = parse_pmc_xml(xml)
        self.assertEqual(len(articles), 1)
        art = articles[0]
        self.assertEqual(art["pmcid"], "999999")
        self.assertEqual(art["pmid"], "12345678")
        self.assertEqual(art["doi"], "10.1000/test.001")
        self.assertEqual(art["title"], "A Study of Something Important")
        self.assertEqual(art["authors"], ["Zhang H", "Wei W"])
        self.assertEqual(art["year"], "2021")
        self.assertEqual(art["abstract"], "This is the abstract text.")
        self.assertTrue(art["open_access"])
        # Full text should contain all paragraphs, in order
        self.assertIn("First intro paragraph.", art["full_text"])
        self.assertIn("Nested background paragraph.", art["full_text"])
        self.assertIn("Final conclusion paragraph.", art["full_text"])
        # Headings should be captured as heading blocks
        headings = [b["text"] for b in art["content"] if b["type"] == "heading"]
        self.assertIn("Introduction", headings)
        self.assertIn("Background", headings)
        self.assertIn("Conclusion", headings)
        # Nested section heading should have a deeper level than its parent
        levels = {b["text"]: b["level"] for b in art["content"] if b["type"] == "heading"}
        self.assertEqual(levels["Introduction"], 1)
        self.assertEqual(levels["Background"], 2)

    def test_parse_pmc_no_body_is_metadata_only(self):
        """Test parse_pmc_xml flags open_access=False when the body is absent."""
        xml = """<?xml version="1.0"?><pmc-articleset><article>
          <!--The publisher of this article does not allow downloading of the full text in XML form.-->
          <front><article-meta>
            <article-id pub-id-type="pmcid">PMC555555</article-id>
            <title-group><article-title>Paywalled Paper</article-title></title-group>
            <abstract><p>Only the abstract is available here.</p></abstract>
          </article-meta></front></article></pmc-articleset>"""
        articles = parse_pmc_xml(xml)
        self.assertEqual(len(articles), 1)
        art = articles[0]
        self.assertEqual(art["pmcid"], "555555")
        self.assertFalse(art["open_access"])
        self.assertEqual(art["full_text"], "")
        self.assertEqual(art["char_count"], 0)
        self.assertEqual(art["abstract"], "Only the abstract is available here.")


class TestQueryConversion(unittest.TestCase):
    """Conversion-layer regressions: each case maps to a measured recall bug."""

    @classmethod
    def setUpClass(cls):
        from pubmed_search import detect_query_elements, build_pubmed_query
        cls.detect = staticmethod(detect_query_elements)
        cls.build = staticmethod(build_pubmed_query)

    def convert(self, query):
        return self.build(query, self.detect(query))[0]

    def test_author_regex_requires_clue_word(self):
        # "Vitamin D" used to become "Vitamin D[Author]" -> 3 results vs 44,183.
        for query in ("Vitamin D deficiency",
                      "Hepatitis B virus treatment",
                      "Influenza A vaccine"):
            self.assertNotIn("[Author]", self.convert(query), query)
        self.assertIn("Smith J[Author]", self.convert("Smith J author Alzheimer"))

    def test_lowercase_boolean_preserved(self):
        # Lower-case "or" used to be dropped, turning OR into AND.
        self.assertEqual(self.convert("alzheimer or parkinson"),
                         "alzheimer OR parkinson")

    def test_article_type_word_boundary(self):
        # indusTRIAL must not inject Clinical Trial[pt].
        self.assertNotIn("Clinical Trial[pt]",
                         self.convert("industrial chemical exposure"))
        self.assertIn("Review[pt]", self.convert("cancer review"))

    def test_hyphenated_tokens_preserved(self):
        self.assertIn("IL-6", self.convert("IL-6 inflammation"))
        self.assertIn("p-tau217", self.convert("p-tau217 biomarker"))
        self.assertIn("B cell lymphoma", self.convert("B cell lymphoma"))

    def test_quoted_phrase_passthrough(self):
        output = self.convert('"blood-brain barrier" disruption')
        self.assertIn('"blood-brain barrier"', output)
        self.assertNotIn('"Blood"[MeSH]', output)
        self.assertNotIn('"Brain"[MeSH]', output)

    def test_anatomy_words_not_mesh_tagged(self):
        # "Brain"[MeSH] expanded the anatomy tree and halved recall.
        output = self.convert("brain tumor treatment")
        self.assertNotIn('"Brain"[MeSH]', output)

    def test_stopwords_do_not_leak(self):
        output = self.convert("Alzheimer last 5 years")
        self.assertNotIn("(last years)", output)
        self.assertIn("[PDat]", output)
        self.assertIn('"Alzheimer Disease"[MeSH]', output)
        output2 = self.convert("APOE gene and Alzheimer disease")
        self.assertNotIn("(gene)", output2)

    def test_year_maps_to_pdat(self):
        self.assertIn("2020[PDat]", self.convert("cancer 2020"))

    def test_routing_fixes(self):
        from ncbi_search import detect_database
        self.assertEqual(detect_database("blood pressure"), "pubmed")
        self.assertEqual(detect_database("cancer treatment"), "pubmed")
        self.assertEqual(detect_database("cell cycle"), "pubmed")
        self.assertEqual(detect_database("DNA repair review"), "pubmed")
        self.assertEqual(detect_database("human genome project"), "pubmed")
        self.assertEqual(detect_database("APOE gene"), "gene")
        self.assertEqual(detect_database("SHANK3 function"), "gene")
        self.assertEqual(detect_database("rs429358"), "snp")

    def test_abstract_preview_keeps_conclusions(self):
        from ncbi_utils import truncate_abstract
        structured = (
            "BACKGROUND: Alzheimer disease is common. METHODS: We studied patients. "
            "RESULTS: APOE4 carriers declined faster. CONCLUSIONS: APOE4 predicts decline."
        )
        preview = truncate_abstract(structured, 60)
        self.assertLessEqual(len(preview), 70)
        self.assertIn("APOE4", preview)
        self.assertNotIn("BACKGROUND:", preview)


class TestFormatters(unittest.TestCase):
    """Output formatters for non-PubMed databases and PMC (offline, synthetic records)."""

    def test_snp_formatter_merged_and_maf(self):
        from ncbi_search import format_snp_results
        records = [{
            "_id": "429358", "snp_id": 429358,
            "genes": [{"name": "APOE", "gene_id": "348"}],
            "chrpos": "19:44908684",
            "global_mafs": [{"study": "1000Genomes", "freq": "C=0.1505591/754"}],
            "clinical_significance": "association,drug-response,risk-factor,protective",
        }]
        out = format_snp_results(records, 3, "rs429358")
        self.assertIn("rs429358", out)
        self.assertIn("APOE", out)
        self.assertIn("chr19:44908684", out)
        self.assertIn("MAF C=0.151 (1000Genomes)", out)
        self.assertIn("association, drug-response, risk-factor, protective", out)

    def test_snp_formatter_merged_marker(self):
        from ncbi_search import format_snp_results
        records = [{"_id": "61228756", "snp_id": 429358, "merged": 1,
                    "genes": [], "chrpos": "19:44908684"}]
        out = format_snp_results(records, 3, "rs429358")
        self.assertIn("merged->rs429358", out)

    def test_clinvar_formatter(self):
        from ncbi_search import format_clinvar_results
        records = [{
            "uid": "5016490", "accession": "VCV005016490", "title": "Single allele",
            "variation_set": [{
                "variation_name": "Single allele",
                "variation_loc": [{"chr": "17", "start": "43095510",
                                   "stop": "43114978", "assembly_name": "GRCh38"}],
            }],
            "germline_classification": {
                "description": "Likely pathogenic",
                "review_status": "criteria provided, single submitter",
                "trait_set": [{"trait_name": "Breast-ovarian cancer, familial, susceptibility to, 1"}],
            },
        }]
        out = format_clinvar_results(records, 1, "BRCA1")
        self.assertIn("VCV005016490", out)
        self.assertIn("Likely pathogenic", out)
        self.assertIn("chr17:43095510-43114978 (GRCh38)", out)
        self.assertIn("Breast-ovarian", out)

    def test_assembly_and_taxonomy_formatters(self):
        from ncbi_search import format_assembly_results, format_taxonomy_results
        asm = [{"_id": "11968211", "assemblyaccession": "GCF_000001405.40",
                "assemblyname": "GRCh38.p14", "organism": "Homo sapiens (human)",
                "assemblystatus": "Chromosome", "refseq_category": "reference genome",
                "asmreleasedate_refseq": "2022/02/08 00:00"}]
        out = format_assembly_results(asm, 16, "GRCh38")
        self.assertIn("GCF_000001405.40", out)
        self.assertIn("GRCh38.p14", out)
        self.assertIn("reference genome", out)

        tax = [{"_id": "9606", "scientificname": "Homo sapiens", "commonname": "human",
                "rank": "species", "division": "primates"}]
        out2 = format_taxonomy_results(tax, 1, "Homo sapiens")
        self.assertIn("9606", out2)
        self.assertIn("Homo sapiens (human)", out2)
        self.assertIn("species", out2)

    def test_sra_formatter(self):
        from ncbi_search import format_sra_results
        xml = ('<Summary><Title>t</Title><Statistics total_runs="1" total_spots="196233032"/></Summary>'
               '<Experiment acc="DRX783447" ver="1" status="public" name="n"/>'
               '<Study acc="DRP019600" name="sn-RNA seq of AHN dysfunction AD model mice"/>'
               '<Organism taxid="10090" ScientificName="Mus musculus"/>'
               '<Library_descriptor><LIBRARY_STRATEGY>RNA-Seq</LIBRARY_STRATEGY></Library_descriptor>')
        records = [{"_id": "46962526", "expxml": xml, "createdate": "2026/09/25"}]
        out = format_sra_results(records, 1320, "RNA-seq")
        self.assertIn("DRX783447", out)
        self.assertIn("sn-RNA seq", out)
        self.assertIn("Mus musculus", out)
        self.assertIn("RNA-Seq", out)
        self.assertIn("196,233,032 spots", out)

    def test_pmc_sections_filter(self):
        from pmc_fetch import _filter_sections
        blocks = [
            {"type": "heading", "level": 1, "text": "Introduction"},
            {"type": "paragraph", "text": "intro"},
            {"type": "heading", "level": 1, "text": "Results"},
            {"type": "paragraph", "text": "result"},
            {"type": "heading", "level": 2, "text": "Sub result"},
            {"type": "paragraph", "text": "sub"},
            {"type": "heading", "level": 1, "text": "Conclusions and future directions"},
            {"type": "paragraph", "text": "conclusion"},
        ]
        out = _filter_sections(blocks, ["conclusion", "results"])
        texts = [block["text"] for block in out]
        self.assertIn("Results", texts)
        self.assertIn("result", texts)
        self.assertIn("Conclusions and future directions", texts)
        self.assertIn("conclusion", texts)
        self.assertNotIn("Introduction", texts)

    def test_trim_json_keeps_record_id(self):
        from ncbi_search import trim_json_record
        record = {"_id": "348", "name": "APOE", "abstract": "x" * 600, "mesh_terms": ["a"]}
        out = trim_json_record(record, "none")
        self.assertEqual(out["id"], "348")
        self.assertNotIn("_id", out)
        self.assertNotIn("abstract", out)


class TestQueryHelpers(unittest.TestCase):
    """Helpers added in P4: batch rsIDs, year ranges, Chinese translation."""

    def test_snp_uid_term(self):
        from ncbi_search import _snp_uid_term
        self.assertEqual(_snp_uid_term("rs429358"), "429358[UID]")
        self.assertEqual(_snp_uid_term("rs429358, rs7412"),
                         "429358[UID] OR 7412[UID]")
        self.assertIsNone(_snp_uid_term("APOE rs429358"))
        self.assertIsNone(_snp_uid_term("APOE"))

    def test_date_filter(self):
        from ncbi_utils import date_filter
        self.assertEqual(date_filter(None, 2020, 2023), "2020:2023[PDat]")
        self.assertEqual(date_filter(None, 2020, None),
                         f"2020:{datetime.now().year}[PDat]")
        self.assertIsNone(date_filter(None, None, None))
        self.assertIn("[PDat]", date_filter(5, None, None))

    def test_chinese_translation(self):
        from ncbi_utils import translate_chinese
        out = translate_chinese("阿尔茨海默病 综述")
        self.assertIn("Alzheimer disease", out)
        self.assertIn("review", out)
        self.assertEqual(translate_chinese("APOE"), "APOE")
        self.assertEqual(translate_chinese("焦亡"), "焦亡")


if __name__ == "__main__":
    unittest.main()
