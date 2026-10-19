# PubMed Query Syntax Guide

## Natural Language Conversion (pubmed_search.py)

`pubmed_search.py` 将自然语言转换为 PubMed 检索式：**默认不强制字段标签**，识别出的概念（含 MeSH 主题词）统一作为裸关键词组传入，由 PubMed 的 **ATM（Automatic Term Mapping，自动语词映射）** 完成同义词扩展、MeSH 树扩展和最新文献召回。只有显式 `--mesh` 时才强制 `[MeSH]` 过滤。

为什么默认不标 `[MeSH]`：`[MeSH]` 会旁路 ATM 的裸词扩展，且刚上线尚未标引的文献（In-Process）没有 MeSH 标签，纯 MeSH 过滤会漏检；实测多个常见查询反而降召回。

| 自然语言 | 转换后（3.0.0 实际输出） | 说明 |
|---------|--------|------|
| `Alzheimer disease` | `(Alzheimer Disease)` | 裸关键词组，交 ATM 扩展（含 MeSH 同义词） |
| `APOE gene` | `APOE[Title/Abstract]`（`gene` 作为停用词剔除） | 识别为基因符号（标题/摘要精确匹配） |
| `p-tau217 Abeta42 Alzheimer biomarker` | `(p-tau217 Abeta42 biomarker Alzheimer Disease)` | 连字符词整体保留；概念词进关键词组 |
| `Smith J author Alzheimer` | `(Alzheimer Disease) AND Smith J[Author]` | 仅在线索词（author/by/written by）存在时才解析作者 |
| `last 5 years` | `2021/10/18:2026/10/17[PDat]`（滚动 N 年窗口） | 日期范围；日期按运行当天计算 |
| `review` | `Review[pt]` | 文章类型（词边界匹配，不会误触 `industrial` 中的 `trial`） |
| `Vitamin D deficiency` | `(Vitamin D deficiency)` | 作者正则不再误伤；单字母 D 保留 |
| `alzheimer or parkinson` | `alzheimer OR parkinson` | 小写布尔词自动转大写并透传 |
| `"blood-brain barrier" disruption` | `"blood-brain barrier" AND (disruption)` | 引号短语整体透传（注意：引号会关闭 ATM，只做字面短语匹配） |

> **引号的代价**：加双引号后 PubMed 不再做 ATM 同义词扩展，同义写法（如 hypovitaminosis D）会漏检；仅对必须精确匹配的专有名词使用引号。
> **最新文献**：刚发表、尚未 MeSH 标引的文献只能靠裸关键词命中，这也是默认不加强制 MeSH 的原因之一。

## Passing Manual Queries

如果自动转换不满足需求，可以直接向 `ncbi_search.py` / `pubmed_search.py` 传入标准 PubMed 检索式——脚本检测到字段标签（`[...]`）或布尔运算符（`AND`/`OR`/`NOT`）时会跳过自动转换，原样透传：

```bash
# 复杂布尔检索
python scripts/ncbi_search.py "(Alzheimer[Title/Abstract]) AND (APOE[Title/Abstract]) AND (Review[pt])"

# 多字段组合
python scripts/ncbi_search.py "(diabetes[MeSH]) AND (insulin[Title/Abstract]) AND (2020[PDat]:2025[PDat])"

# 排除检索
python scripts/ncbi_search.py "(Alzheimer[Title/Abstract]) NOT (mouse[Title/Abstract])"
```

## Quick Reference

| Field | Syntax | Example |
|-------|--------|---------|
| Title | `[Title]` or `[ti]` | `Alzheimer[ti]` |
| Abstract | `[Abstract]` or `[ab]` | `treatment[ab]` |
| Title/Abstract | `[Title/Abstract]` or `[tiab]` | `dementia[tiab]` |
| MeSH | `[MeSH]` or `[mh]` | `"Cerebrovascular Circulation"[mh]` |
| Author | `[Author]` or `[au]` | `Smith J[au]` |
| Journal | `[Journal]` or `[ta]` | `Nature[ta]` |
| Year | `[PDat]` | `2020:2025[PDat]` |
| PMID | `[PMID]` | `12345678[PMID]` |
| DOI | `[DOI]` | `10.1038/s12345[DOI]` |

## Boolean Operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `AND` | Both must appear | `Alzheimer AND dementia` |
| `OR` | Either may appear | `Alzheimer OR dementia` |
| `NOT` | Exclude term | `Alzheimer NOT review` |

**Operator Precedence**: NOT > AND > OR

Use parentheses to group: `(Alzheimer OR dementia) AND treatment`

## Date Filters

### Publication Date Range
```
2020:2025[PDat]        # 2020 to 2025
2024/01/01:2024/12/31[PDat]  # Specific date range
```

### Relative Dates (use script options)
```bash
--years 5    # Last 5 years
--years 1    # Last 1 year
```

> **注意（relevance + 日期）**：带 `--years` 时 `--sort relevance` 是"窗口内重排"，不是全库最相关的结果（top-N 与不带日期时完全不同；PubMed 网站会强制 Most Recent）。需要"最新文献"语义时请显式用 `--sort pub_date`。

## Article Type Filters

| Type | Query Syntax |
|------|-------------|
| Review | `Review[pt]` |
| Clinical Trial | `Clinical Trial[pt]` |
| Randomized Controlled Trial | `Randomized Controlled Trial[pt]` |
| Meta-Analysis | `Meta-Analysis[pt]` |
| Case Report | `Case Reports[pt]` |
| Editorial | `Editorial[pt]` |
| Letter | `Letter[pt]` |
| Practice Guideline | `Practice Guideline[pt]` |

**Use `--type` option for convenience:**
```bash
--type review
--type clinical_trial
```

## MeSH Terms

MeSH (Medical Subject Headings) are controlled vocabulary terms assigned by NLM indexers.

### Search MeSH Terms
```
"Cerebrovascular Circulation"[MeSH]
"Alzheimer Disease"[MeSH]
```

### MeSH Subheadings
```
"Alzheimer Disease/therapy"[MeSH]
"Alzheimer Disease/pathology"[MeSH]
```

### MeSH Qualifiers
| Qualifier | Use |
|-----------|-----|
| `/therapy` | Treatment approaches |
| `/diagnosis` | Diagnostic methods |
| `/pathology` | Disease mechanisms |
| `/etiology` | Causes |
| `/epidemiology` | Population studies |
| `/genetics` | Genetic aspects |

## Author Search

### Last Name Only
```
Smith[Author]
```

### Last Name + Initial
```
Smith J[Author]
```

### Multiple Authors
```
Smith J[Author] OR Jones K[Author]
```

## Journal Search

### Journal Name
```
"Nature Medicine"[Journal]
```

### Journal Abbreviation
```
JAMA[Journal]
```

## Advanced Examples

### Recent Reviews on Topic
```
"Alzheimer disease"[MeSH] AND Review[pt] AND 2022:2025[PDat]
```

### Clinical Trials for a Condition
```
"Alzheimer disease"[MeSH] AND "Clinical Trial"[pt]
```

### Gene-Disease Association
```
APOE[Title/Abstract] AND "Alzheimer disease"[MeSH]
```

### Specific Author in Specific Journal
```
Smith J[Author] AND Nature[Journal]
```

### Exclude Article Types
```
"Alzheimer disease"[MeSH] NOT (Review[pt] OR Editorial[pt])
```

### Free Full Text Available
```
"Alzheimer disease"[MeSH] AND "free full text"[sb]
```

## Search Field Descriptions

| Tag | Full Name | Description |
|-----|-----------|-------------|
| `[ti]` | Title | Article title |
| `[ab]` | Abstract | Article abstract |
| `[tiab]` | Title/Abstract | Combined title and abstract |
| `[mh]` | MeSH Terms | Controlled vocabulary |
| `[au]` | Author | Author names |
| `[ta]` | Journal | Journal title/abbreviation |
| `[pt]` | Publication Type | Article type |
| `[dp]` | Date of Publication | Publication date |
| `[edat]` | Entrez Date | Date added to PubMed |
| `[pmid]` | PMID | PubMed ID |
| `[doi]` | DOI | Digital Object Identifier |

## Wildcards

### Truncation (`*`)
```
diabet*    # diabetes, diabetic, diabetology
```

### Phrase Search (quotes)
```
"Alzheimer disease"
```

## Tips for Better Searches

1. **Start broad, then narrow** - Begin with simple keywords, add filters as needed
2. **Use MeSH terms** - More precise than keyword searching
3. **Combine with Boolean** - Use AND/OR/NOT strategically
4. **Check synonyms** - Different authors use different terms
5. **Use parentheses** - Group related terms: `(Alzheimer OR dementia)`
6. **Limit by date** - Recent literature for current knowledge
7. **Limit by type** - Reviews for overview, trials for evidence

## Common Search Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| `Alzheimer disease` | Searches all fields | `"Alzheimer disease"[Title/Abstract]` |
| `Smith` (author) | Too common | `Smith J[Author]` |
| `2024` | Searches all fields | `2024[PDat]` |
| `review` | Searches for word | `Review[pt]` |

## Resources

- PubMed Help: https://pubmed.ncbi.nlm.nih.gov/help/
- MeSH Browser: https://meshb.nlm.nih.gov/
- PubMed Advanced Search Builder: https://pubmed.ncbi.nlm.nih.gov/advanced/