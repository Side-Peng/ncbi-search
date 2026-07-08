---
name: ncbi-search
description: "Search NCBI databases using E-Utilities API (official, free). Supports 10+ databases: PubMed (literature), Gene, Protein, Nucleotide, dbSNP, ClinVar, Taxonomy, BioSample, Assembly, SRA. Automatically detects search intent and routes to appropriate database. Returns formatted results with tiered abstract display (none/preview/full) for token-efficient progressive search. Use for biomedical literature, gene information, protein sequences, genetic variants, and more."
allowed-tools: [Bash]
trigger-keywords: [ncbi, pubmed, gene, protein, snp, clinvar, literature, paper, article, review, variant, genome, sequence, taxonomy, dna, rna]
---

# NCBI Search — AI Agent 工具文档

> **一句话描述**: NCBI 多数据库智能检索工具，使用官方 E-Utilities API，免费、可靠、零外部依赖（除 requests）。

---

## 目录

1. [快速决策树](#1-快速决策树)
2. [数据库总览](#2-数据库总览)
3. [使用方式](#3-使用方式)
4. [参数详解](#4-参数详解)
5. [完整示例集](#5-完整示例集)
6. [高级查询技巧](#6-高级查询技巧)
7. [结果解析说明](#7-结果解析说明)
8. [错误处理指南](#8-错误处理指南)
9. [批量处理能力](#9-批量处理能力)
10. [缓存机制](#10-缓存机制)
11. [API Key 配置](#11-api-key-配置)
12. [文件结构](#12-文件结构)
13. [更新日志](#13-更新日志)

---

## 1. 快速决策树

AI Agent 请按以下优先级判断使用哪个数据库：

```
用户查询
│
├─ 包含 rs\d+ 模式（如 rs429358）? → dbSNP
│
├─ 包含 VCV\d+ 模式（如 VCV000242862）? → ClinVar
│
├─ 包含已知基因符号（APOE, BRCA1 等）或 4-8 位潜在基因正则（如 SHANK3）?
│   ├─ 同时包含文献关键字（paper/review/trial/文献/论文/临床等）? → PubMed
│   └─ 否则 → Gene
│
├─ 包含数据库关键词?
│   ├─ paper/article/review/journal/trial/文献/论文/临床/综述 → PubMed
│   ├─ protein/peptide/amino acid/蛋白/多肽/氨基酸/sequence → Protein
│   ├─ nucleotide/DNA/RNA/genome/cDNA/核酸/序列/基因组 → Nucleotide
│   ├─ SNP/variant/polymorphism/allele/变异/多态性/突变 → dbSNP
│   ├─ clinvar/clinical variant/pathogenic/致病/临床变异 → ClinVar
│   ├─ species/taxonomy/organism/classification/物种/分类 → Taxonomy
│   ├─ biosample/sample/样本 → BioSample
│   ├─ assembly/genome assembly/基因组组装 → Assembly
│   └─ SRA/sequencing/reads/测序数据 → SRA
│
└─ 以上都不匹配 → PubMed（默认）
```

### 触发规则优先级

| 优先级 | 匹配条件 | 路由目标 |
|--------|---------|---------|
| 🔴 最高 | `rs\d+` 正则匹配 | dbSNP |
| 🔴 最高 | `VCV\d+` 正则匹配 | ClinVar |
| 🟠 高 | 已知基因符号或 4-8 位大写混合字母（非普通英文短词） | Gene |
| 🟡 中 | 数据库关键词高特异性打分匹配 | 对应数据库 |
| 🟢 默认 | 无明确匹配 | PubMed |

### Do / Don't

| ✅ Do | ❌ Don't |
|-------|----------|
| 用户提到“基因”时用 `--db gene` | 不要对纯数字查询（如“348”）自动路由到 Gene |
| 用户提到“文献/论文”时用 `--db pubmed` | 不要对含基因符号的查询直接路由到 Gene（先检查是否要查文献） |
| 用户给 rsID 时用 `--db snp` | 不要用 `--db snp` 查非 SNP 内容 |
| 不确定时默认用 PubMed | 不要同时查多个数据库（需分步执行） |
| 初步搜索用 `--abstract none` 节省 token | 不要默认获取完整摘要再自己截断 |
| 筛选阶段用 `--abstract preview`（默认） | 不要对大量结果都用 `--abstract full` |
| 最终选定论文后用 `--abstract full` 或 `--full-abstract` | 不要假设摘要会自动截断到 200 字符（现已改为 1000） |

---

## 2. 数据库总览

### 2.1 完整数据库列表

| 数据库 | 命令行名称 | 用途 | 触发关键词 | ID 格式 | 链接模板 |
|--------|-----------|------|-----------|---------|---------|
| **PubMed** | `pubmed` | 生物医学文献检索 | paper, article, review, publication, journal, study, 论文, 文献, 研究, 发表, 文章, 综述 | PMID（数字） | `https://pubmed.ncbi.nlm.nih.gov/{PMID}/` |
| **Gene** | `gene` | 基因信息查询 | gene, symbol, 编码, 基因, mRNA, expression, 转录 | Gene ID（数字） | `https://www.ncbi.nlm.nih.gov/gene/{ID}` |
| **Protein** | `protein` | 蛋白质序列 | protein, peptide, amino, 蛋白, 多肽, 氨基酸, sequence | Accession（字母+数字） | `https://www.ncbi.nlm.nih.gov/protein/{ACC}` |
| **Nucleotide** | `nucleotide` | 核酸序列 | nucleotide, DNA, RNA, sequence, genome, cDNA, 核酸, 序列, 基因组 | Accession（字母+数字） | `https://www.ncbi.nlm.nih.gov/nuccore/{ACC}` |
| **dbSNP** | `snp` | SNP 变异查询 | SNP, variant, polymorphism, allele, rs, 变异, 多态性, 突变 | rsID（rs+数字） | `https://www.ncbi.nlm.nih.gov/snp/{rsID}` |
| **ClinVar** | `clinvar` | 临床变异 | clinvar, clinical variant, pathogenic, 致病, 临床变异 | Variation ID（数字） | `https://www.ncbi.nlm.nih.gov/clinvar/variation/{ID}` |
| **Taxonomy** | `taxonomy` | 物种分类 | species, taxonomy, organism, classification, 物种, 分类, 物种分类 | TaxID（数字） | `https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id={ID}` |
| **BioSample** | `biosample` | 生物样本信息 | biosample, sample, 样本 | Sample ID | `https://www.ncbi.nlm.nih.gov/biosample/{ID}` |
| **Assembly** | `assembly` | 基因组组装 | assembly, genome assembly, 基因组组装 | Assembly ID | `https://www.ncbi.nlm.nih.gov/assembly/{ID}` |
| **SRA** | `sra` | 测序数据归档 | SRA, sequencing, reads, 测序数据 | SRA ID（SRR/ERR/DRR） | `https://www.ncbi.nlm.nih.gov/sra/{ID}` |

---

## 3. 使用方式

### 3.1 脚本说明

项目包含 4 个脚本，各有侧重：

| 脚本 | 功能 | 适用场景 |
|------|------|---------|
| `ncbi_search.py` | **主脚本**：多数据库智能搜索，自动意图识别，PubMed 使用 EFetch 获取完整摘要 | 大多数情况，推荐使用 |
| `pubmed_search.py` | **PubMed 专用**：自然语言转检索式，MeSH 词识别（含多词短语） | 仅 PubMed 检索，需要智能解析 |
| `pubmed_fetch.py` | **批量获取**：通过 PMID 列表批量获取文献详情，支持 200 PMID 分批 | 已有 PMID 列表，需要批量获取 |
| `ncbi_utils.py` | **工具函数**：共享工具函数、缓存、编码修复 | 被其他脚本调用，不直接使用 |

### 3.2 自动模式（推荐）

```bash
# 自动判断搜索意图（PubMed 现在返回完整摘要！）
python scripts/ncbi_search.py "APOE gene"
python scripts/ncbi_search.py "Alzheimer disease review"
python scripts/ncbi_search.py "insulin protein"
python scripts/ncbi_search.py "rs429358"
```

### 3.3 指定数据库

```bash
python scripts/ncbi_search.py "APOE" --db gene
python scripts/ncbi_search.py "diabetes" --db pubmed --abstract full
python scripts/ncbi_search.py "rs429358" --db snp
```

### 3.4 PubMed 专用脚本（自然语言检索）

```bash
# 自然语言查询 — 现采用宽松策略，不强制每个词加 [Title/Abstract]
python scripts/pubmed_search.py "Alzheimer disease cerebrovascular mechanisms"
python scripts/pubmed_search.py "p-tau217 Abeta42 blood plasma Alzheimer biomarker" --abstract full
python scripts/pubmed_search.py "APOE gene and Alzheimer disease" --years 5
python scripts/pubmed_search.py "Smith J author Alzheimer" --max 20
python scripts/pubmed_search.py "diabetes treatment" --sort pub_date --max 20
```

---

## 4. 参数详解

### 4.1 ncbi_search.py 参数

| 参数 | 类型 | 默认值 | 适用数据库 | 说明 |
|------|------|--------|-----------|------|
| `query` | 必填 | - | 全部 | 搜索查询（自然语言或标准检索式） |
| `--db` | 可选 | auto-detect | 全部 | 指定数据库，不指定则自动识别 |
| `--max` | int | 10 | 全部 | 最大返回结果数（1-100） |
| `--years` | int | - | **仅 pubmed** | 限制最近 N 年 |
| `--type` | str | - | **仅 pubmed** | 文章类型过滤 |
| `--organism` | str | - | **仅 gene** | 物种过滤 |
| `--sort` | str | relevance | 全部 | 排序方式：relevance, pub_date, Author, Journal |
| `--full-abstract` | bool | false | **仅 pubmed** | 显示完整摘要（不截断）[向后兼容，等同 --abstract full] |
| `--abstract` | str | preview | **仅 pubmed** | 摘要显示级别：none(仅标题), preview(前1000字符), full(完整) |
| `--format` | str | summary | 全部 | 输出格式：summary 或 json |
| `--output` / `-o` | str | - | 全部 | 保存结果到文件 |
| `--api-key` | str | env var | 全部 | NCBI API Key |
| `--verbose` / `-v` | bool | false | 全部 | 显示详细信息 |

### 4.2 pubmed_search.py 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | 必填 | - | 自然语言检索词或 PubMed 检索式 |
| `--max` | int | 10 | 最大返回结果数 |
| `--years` | int | - | 限制最近 N 年 |
| `--type` | str | - | 文章类型：review, clinical_trial, randomized, meta_analysis |
| `--mesh` | str | - | MeSH 主题词筛选 |
| `--sort` | str | relevance | 排序方式：relevance, pub_date, Author, Journal |
| `--full-abstract` | bool | false | 显示完整摘要（不截断）[向后兼容，等同 --abstract full] |
| `--abstract` | str | preview | 摘要显示级别：none(仅标题), preview(前1000字符), full(完整) |
| `--format` | str | summary | 输出格式：summary 或 json |
| `--output` / `-o` | str | - | 保存结果到文件 |
| `--api-key` | str | env var | NCBI API Key |
| `--verbose` / `-v` | bool | false | 显示详细信息 |

### 4.3 pubmed_fetch.py 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pmids` | 必填 | - | PMID 列表 |
| `--file` / `-f` | str | - | 从文件读取 PMID 列表 |
| `--format` | str | json | 输出格式：summary 或 json |
| `--full-abstract` | bool | false | 显示完整摘要（不截断）[向后兼容，等同 --abstract full] |
| `--abstract` | str | preview | 摘要显示级别：none(仅标题), preview(前1000字符), full(完整) |
| `--batch-size` | int | 200 | 每批获取的最大 PMID 数 |
| `--output` / `-o` | str | - | 保存结果到文件 |
| `--api-key` | str | env var | NCBI API Key |
| `--verbose` / `-v` | bool | false | 显示详细信息 |

### 4.4 --type 参数可选值

| 值 | 含义 | PubMed 标签 |
|----|------|-------------|
| `review` | 综述 | `Review[pt]` |
| `clinical_trial` | 临床试验 | `Clinical Trial[pt]` |
| `randomized` | 随机对照试验 | `Randomized Controlled Trial[pt]` |
| `meta_analysis` | Meta 分析 | `Meta-Analysis[pt]` |

### 4.5 --sort 参数可选值

| 值 | 含义 | 适用场景 |
|----|------|---------|
| `relevance` | 相关性排序（默认） | 一般检索 |
| `pub_date` | 按出版日期排序 | 查看最新文献 |
| `Author` | 按作者排序 | 查找某作者的文献 |
| `Journal` | 按期刊排序 | 期刊浏览 |

### 4.6 参数组合规则

| 组合 | 是否合法 | 说明 |
|------|---------|------|
| `--db pubmed --years 5` | ✅ 合法 | PubMed 限定年份 |
| `--db pubmed --type review` | ✅ 合法 | PubMed 限定文章类型 |
| `--db pubmed --full-abstract` | ✅ 合法 | PubMed 显示完整摘要（等同 --abstract full） |
| `--db pubmed --abstract none` | ✅ 合法 | PubMed 仅显示标题（节省 token） |
| `--db pubmed --abstract full` | ✅ 合法 | PubMed 显示完整摘要 |
| `--db pubmed --sort pub_date` | ✅ 合法 | PubMed 按日期排序 |
| `--db gene --organism human` | ✅ 合法 | Gene 限定物种 |
| `--db snp --years 5` | ❌ 无效 | `--years` 仅适用于 PubMed |
| `--db protein --organism human` | ❌ 无效 | `--organism` 仅适用于 Gene |
| `--db gene --full-abstract` | ❌ 无效 | `--full-abstract` 仅适用于 PubMed |

---

## 5. 完整示例集

### 5.1 基础示例

```bash
# 自动模式（PubMed 现在返回完整摘要）
python scripts/ncbi_search.py "APOE gene"                    # → Gene
python scripts/ncbi_search.py "Alzheimer disease review"     # → PubMed (with abstract)
python scripts/ncbi_search.py "rs429358"                     # → dbSNP
python scripts/ncbi_search.py "insulin protein"              # → Protein
python scripts/ncbi_search.py "Escherichia coli taxonomy"    # → Taxonomy

# 指定数据库
python scripts/ncbi_search.py "APOE" --db gene --organism human
python scripts/ncbi_search.py "insulin" --db protein
python scripts/ncbi_search.py "BRCA1" --db nucleotide
```

### 5.2 组合参数示例

```bash
# PubMed 高级过滤（含完整摘要）
python scripts/ncbi_search.py "diabetes treatment" --years 5 --type review --max 20 --abstract full
python scripts/ncbi_search.py "Alzheimer amyloid beta" --years 3 --max 5 --sort pub_date
python scripts/ncbi_search.py "COVID-19 vaccine" --type clinical_trial --max 50

# Gene 高级过滤
python scripts/ncbi_search.py "APOE" --db gene --organism human
python scripts/ncbi_search.py "TP53" --db gene --organism mouse

# JSON 格式输出
python scripts/ncbi_search.py "BRCA1" --db gene --format json

# 保存到文件
python scripts/ncbi_search.py "Alzheimer disease" --years 5 --max 100 -o results.txt
```

### 5.3 PubMed 自然语言检索示例

```bash
# 自然语言查询（宽松策略，不再强制每个词加 [Title/Abstract]）
python scripts/pubmed_search.py "Alzheimer disease cerebrovascular mechanisms"
python scripts/pubmed_search.py "p-tau217 Abeta42 ratio blood plasma Alzheimer" --abstract full
python scripts/pubmed_search.py "APOE gene and Alzheimer disease" --years 5
python scripts/pubmed_search.py "Smith J author Alzheimer" --max 20
python scripts/pubmed_search.py "diabetes treatment review" --type review
python scripts/pubmed_search.py "cancer immunotherapy" --mesh "Neoplasms" --years 3 --sort pub_date
```

### 5.4 批量获取示例

```bash
# 通过 PMID 列表获取（自动分批，每批 200 个）
python scripts/pubmed_fetch.py 33597265 34239348 35022842 --abstract full

# 从文件读取大量 PMID（自动分批处理）
python scripts/pubmed_fetch.py -f pmids.txt --format summary --abstract full -o results.txt

# 指定输出格式
python scripts/pubmed_fetch.py 33597265 34239348 --format json
```

### 5.5 渐进式检索策略（推荐 AI Agent 使用）

为节省 Token 消耗，AI Agent 应采用三步渐进式检索：

```bash
# Step 1 — 广泛搜索（Tier 1, 最低 token）：仅返回标题和元数据
python scripts/ncbi_search.py "Alzheimer APOE" --db pubmed --max 20 --abstract none

# Step 2 — 筛选摘要（Tier 2, 默认行为）：返回前1000字符摘要
python scripts/ncbi_search.py "Alzheimer APOE" --db pubmed --max 10 --abstract preview

# Step 3 — 获取完整摘要（Tier 3, 仅选中的论文）
python scripts/pubmed_fetch.py 34239348 33597265 --abstract full
```

| 级别 | `--abstract` 值 | 输出内容 | 使用场景 | Token 成本 |
|------|----------------|---------|---------|----------|
| Tier 1 | `none` | 标题、作者、期刊、DOI、URL、MeSH | 广泛搜索，初筛 | 最低 |
| Tier 2 | `preview`（默认） | Tier 1 + 前 1000 字符摘要 | 二次筛选 | 中等 |
| Tier 3 | `full` | Tier 2 + 完整摘要 | 最终选定论文 | 最高 |

> **重要提示**: `--full-abstract` 仍可用作 `--abstract full` 的简写（向后兼容）。

### 5.6 边界情况示例

```bash
# 无结果查询
python scripts/ncbi_search.py "xyzabc123nonexistent" --db gene

# 大量结果（仅返回前 N 条）
python scripts/ncbi_search.py "cancer" --db pubmed --max 5

# 特殊字符查询
python scripts/ncbi_search.py "IL-6 gene" --db gene
python scripts/ncbi_search.py "p53 protein" --db protein

# 中文查询
python scripts/ncbi_search.py "阿尔茨海默病 综述" --db pubmed
python scripts/ncbi_search.py "APOE 基因" --db gene
```

---

## 6. 高级查询技巧

### 6.1 PubMed 检索式构建

`pubmed_search.py` 的自然语言转换采用**宽松策略**（v2 修复）：

| 自然语言 | 转换后 | 说明 |
|---------|--------|------|
| `Alzheimer disease` | `"Alzheimer Disease"[MeSH]` | 多词 MeSH 短语匹配 |
| `APOE gene` | `APOE[Title/Abstract]` | 识别为基因符号 |
| `p-tau217 Abeta42 Alzheimer` | `(p-tau217 Abeta42) AND "Alzheimer Disease"[MeSH]` | 非MeSH词作为原始关键词组 |
| `Smith J` | `Smith J[Author]` | 识别为作者 |
| `last 5 years` | `2021/01/01:2026/01/01[PDat]` | 日期范围 |
| `review` | `Review[pt]` | 文章类型 |

**关键变化：** 非MeSH词、非基因符号的普通关键词不再强制加 `[Title/Abstract]` 字段标签，而是作为原始关键词组传入，让 PubMed 的搜索引擎自然处理。这避免了专有名词查询返回 0 篇的问题。

### 6.2 手动构建检索式

如果自动转换不满足需求，可以直接传入标准 PubMed 检索式：

```bash
# 复杂布尔检索
python scripts/ncbi_search.py "(Alzheimer[Title/Abstract]) AND (APOE[Title/Abstract]) AND (Review[pt])"

# 多字段组合
python scripts/ncbi_search.py "(diabetes[MeSH]) AND (insulin[Title/Abstract]) AND (2020[PDat]:2025[PDat])"

# 排除检索
python scripts/ncbi_search.py "(Alzheimer[Title/Abstract]) NOT (mouse[Title/Abstract])"
```

### 6.3 常用 PubMed 字段标签

| 标签 | 含义 | 示例 |
|------|------|------|
| `[Title/Abstract]` | 标题/摘要 | `Alzheimer[Title/Abstract]` |
| `[MeSH]` | MeSH 主题词 | `"Alzheimer Disease"[MeSH]` |
| `[Author]` | 作者 | `Smith J[Author]` |
| `[Journal]` | 期刊名 | `Nature[Journal]` |
| `[PDat]` | 出版日期 | `2020/01/01:2025/01/01[PDat]` |
| `[pt]` | 文章类型 | `Review[pt]` |
| `[Organism]` | 物种 | `human[Organism]` |
| `[Gene]` | 基因名 | `APOE[Gene]` |

### 6.4 布尔运算符

| 运算符 | 含义 | 示例 |
|--------|------|------|
| `AND` | 与（必须同时包含） | `Alzheimer AND APOE` |
| `OR` | 或（包含任一即可） | `Alzheimer OR dementia` |
| `NOT` | 非（排除） | `Alzheimer NOT mouse` |

---

## 7. 结果解析说明

### 7.1 PubMed 结果字段（EFetch — 现包含完整摘要）

| 字段 | 说明 | 提取建议 |
|------|------|---------|
| `PMID` | PubMed 唯一标识符 | 用于生成链接和引用 |
| `Title` | 文章标题 | 判断相关性 |
| `Authors` | 作者列表（前 5 位） | 提取第一作者和通讯作者 |
| `Journal` | 期刊名称 | 判断期刊影响力 |
| `Year` | 出版年份 | 判断时效性 |
| `DOI` | 数字对象标识符 | 用于查找全文 |
| `Abstract` | 摘要（根据 `--abstract` 级别显示：`none` 不显示、`preview` 前1000字符、`full` 完整） | 判断论文是否支持特定论点 |
| `MeSH` | MeSH 主题词（最多 5 个） | 了解文章主题分类 |
| `URL` | PubMed 链接 | 直接访问 |

> **重要更新**: `ncbi_search.py` 的 PubMed 结果使用 EFetch API，支持三级摘要显示：`--abstract none`（仅标题）、`preview`（1000字符预览，默认）、`full`（完整摘要）。`--full-abstract` 仍可用作 `--abstract full` 的简写。

### 7.2 Gene 结果字段

| 字段 | 说明 | 提取建议 |
|------|------|---------|
| `Gene ID` | 基因唯一标识符 | 用于生成链接 |
| `Symbol` | 基因符号 | 标准命名 |
| `Description` | 基因描述 | 了解基因功能 |
| `Chromosome` | 染色体位置 | 基因组定位 |
| `Organism` | 物种信息 | 判断物种 |

### 7.3 dbSNP 结果字段

| 字段 | 说明 | 提取建议 |
|------|------|---------|
| `rsID` | SNP 标识符 | 标准命名 |
| `Genes` | 关联基因 | 了解变异所在基因 |
| `Alleles` | 等位基因 | 判断变异类型 |
| `Clinical` | 临床意义 | 判断致病性 |
| `Frequency` | 人群频率 | 判断稀有程度 |

### 7.4 结果排序规则

| 排序方式 | 说明 | 命令参数 |
|---------|------|---------|
| relevance | 相关性排序（默认） | `--sort relevance` |
| pub_date | 按出版日期排序 | `--sort pub_date` |
| Author | 按作者排序 | `--sort Author` |
| Journal | 按期刊排序 | `--sort Journal` |

---

## 8. 错误处理指南

### 8.1 常见错误码

| 错误 | 原因 | 处理方式 |
|------|------|---------|
| `HTTP 429` | 请求过于频繁 | 等待 1 秒后重试（自动处理） |
| `HTTP 500` | NCBI 服务器错误 | 等待后重试（自动重试 3 次） |
| `HTTP 502/503/504` | 网关超时 | 等待后重试（自动重试 3 次） |
| `ConnectionError` | 网络连接失败 | 脚本现在输出友好提示，检查网络连接 |
| `Timeout` | 请求超时 | 脚本现在输出友好提示，减少结果数或重试 |
| `0 results` | 无匹配结果 | 尝试更宽泛的查询词 |
| `ModuleNotFoundError: requests` | requests 库未安装 | `pip install requests`（脚本自动提示） |

### 8.2 Windows 编码问题（已修复）

> **已修复**: 脚本现在在 Windows 环境下自动将 stdout/stderr 配置为 UTF-8 编码，不再因 `\xa0` 等字符崩溃。

### 8.3 速率限制

| 情况 | 限制 | 说明 |
|------|------|------|
| 无 API Key | 3 次/秒 | 脚本自动限流，无需手动处理 |
| 有 API Key | 10 次/秒 | 建议配置 API Key 提高效率 |

### 8.4 降级策略

当 API Key 缺失或请求失败时：

```bash
# 1. 无 API Key 时自动降速（脚本自动处理）
# 2. 减少请求量
python scripts/ncbi_search.py "query" --max 5

# 3. 使用更精确的查询减少结果数
python scripts/ncbi_search.py "Alzheimer APOE" --db pubmed --max 10

# 4. 检查 API Key 是否配置
echo $env:NCBI_API_KEY  # Windows PowerShell
```

### 8.5 无结果时的应对策略

| 情况 | 建议操作 |
|------|---------|
| 查询太具体 | 使用更宽泛的术语，或直接用自然语言（不加字段标签） |
| 拼写错误 | 检查拼写，尝试同义词 |
| 数据库不对 | 尝试其他数据库 |
| 过滤太严格 | 减少过滤条件（去掉 --years, --type 等） |
| 自然语言转换问题 | 用 `ncbi_search.py` 直接传入查询（不做词拆解），或手动构建检索式 |

---

## 9. 批量处理能力

### 9.1 批量获取文献详情

使用 `pubmed_fetch.py` 通过 PMID 列表批量获取（自动分批处理）：

```bash
# 通过 PMID 列表获取
python scripts/pubmed_fetch.py 33597265 34239348 35022842

# 从文件读取 PMID 列表（自动分批，每批 200 个）
python scripts/pubmed_fetch.py -f pmids.txt

# 指定输出格式
python scripts/pubmed_fetch.py 33597265 34239348 --format json

# 获取完整摘要
python scripts/pubmed_fetch.py 33597265 -f pmids.txt --abstract full -o full_results.txt
```

> **重要更新**: `pubmed_fetch.py` 现在自动分批处理（每批 200 个 PMID），不再需要担心大量 PMID 导致请求失败。

### 9.2 多次查询结果合并

```bash
# 分步查询不同数据库
python scripts/ncbi_search.py "APOE" --db gene --format json -o gene_result.json
python scripts/ncbi_search.py "APOE" --db pubmed --max 5 --abstract full --format json -o pubmed_result.json

# 使用 pubmed_search.py 获取详细信息
python scripts/pubmed_search.py "APOE gene Alzheimer" --max 10 --abstract full -o detailed_results.txt
```

### 9.3 数据导出格式

| 格式 | 适用场景 | 命令 |
|------|---------|------|
| **summary**（默认） | 人类阅读 | `--format summary` |
| **JSON** | 程序处理 | `--format json` |
| **保存到文件** | 持久化 | `-o filename.txt` |

---

## 10. 缓存机制

### 10.1 缓存说明

脚本内置了**零依赖的 SQLite 本地持久化缓存**，可自动优化检索速度并防止触发 NCBI 速率限制：

1. **自动缓存机制**: ESearch、ESummary 和 EFetch 的所有 HTTP 响应都会被自动持久化存储在工作区下的 `.ncbi_cache/cache.db`。
2. **零网络延迟**: 重复进行相同的查询时，数据会瞬间从本地数据库返回（耗时由数百毫秒缩短至数毫秒），完全无网络请求。
3. **缓存有效期**: 缓存默认有效期为 **24 小时**。可以通过 `NCBI_CACHE_EXPIRE_HOURS` 环境变量调整过期时长。
4. **API Key 不影响缓存**: 缓存键不包含 API Key，同一查询的结果在不同 API Key 之间共享。

### 10.2 缓存控制与配置

```bash
# 1. 调整缓存有效期（例如设为 48 小时）
# Windows PowerShell
$env:NCBI_CACHE_EXPIRE_HOURS = "48"

# 2. 临时禁用缓存（绕过缓存，强制向网络发起实时请求）
# Windows PowerShell
$env:NCBI_NO_CACHE = "1"
python scripts/ncbi_search.py "APOE gene"
```

### 10.3 速率限制（内置）

即使在缓存未命中（Cache Miss）时，脚本也会自动处理 NCBI 的速率限制：

- **无 API Key**: 每次请求间隔 ≥ 0.34 秒（≤ 3 次/秒）
- **有 API Key**: 每次请求间隔 ≥ 0.11 秒（≤ 10 次/秒）
- **自动重试**: 遇到 429/500/502/503/504 错误时自动重试 3 次

---

## 11. API Key 配置

### 11.1 获取 API Key

1. 注册 [NCBI 账号](https://www.ncbi.nlm.nih.gov/account/)
2. 进入 Settings → API Key Management → Create API Key
3. 复制生成的 API Key

### 11.2 配置方式

```powershell
# Windows PowerShell（当前会话）
$env:NCBI_API_KEY = "your-api-key-here"

# Windows PowerShell（永久）
[Environment]::SetEnvironmentVariable("NCBI_API_KEY", "your-api-key", "User")

# 命令行指定
python scripts/ncbi_search.py "query" --api-key "your-api-key"
```

### 11.3 速率对比

| 方式 | 速率 | 建议 |
|------|------|------|
| 无 API Key | 3 次/秒 | 临时使用 |
| 有 API Key | 10 次/秒 | ✅ 推荐，效率提升 3 倍+ |

---

## 12. 文件结构

```
ncbi-search/
├── SKILL.md                    # 本文档（AI Agent 技能说明）
├── README.md                   # 用户文档
├── scripts/
│   ├── ncbi_search.py          # 主脚本：多数据库智能搜索（PubMed 用 EFetch）
│   ├── pubmed_search.py        # PubMed 专用：自然语言转检索式（宽松策略 + ElementTree）
│   ├── pubmed_fetch.py         # 批量获取：分批处理 + 完整摘要
│   ├── ncbi_utils.py           # 工具函数（缓存 + 编码修复 + ElementTree 辅助）
│   └── test_ncbi.py            # 单元测试
└── references/
    └── query_syntax.md         # PubMed 检索语法指南
```

---

## 13. 更新日志

### v2 (2026-07-08)

**P0 修复（致命问题）:**
- ✅ **Windows GBK 编码崩溃**: 自动将 stdout/stderr 配置为 UTF-8，不再因 `\xa0` 等字符崩溃
- ✅ **PubMed 结果无摘要**: `ncbi_search.py` 对 PubMed 改用 EFetch API，默认返回摘要

**P1 修复（重要问题）:**
- ✅ **摘要截断太短**: 从 200 字符提高到 1000 字符，新增 `--abstract` 三级摘要显示（none/preview/full），`--full-abstract` 保留向后兼容
- ✅ **自然语言转换过于激进**: 非MeSH词/基因符号不再强制加 `[Title/Abstract]`，改为原始关键词组传入 PubMed

**P2 修复（代码质量问题）:**
- ✅ **XML 正则解析脆弱**: `parse_pubmed_xml` 改用 `xml.etree.ElementTree`，支持结构化摘要、机构作者、内联标签
- ✅ **detect_database 死代码**: 删除重复的数据库关键词评分代码块
- ✅ **多词 MeSH 匹配失效**: 新增贪婪短语匹配（最长优先），`"alzheimer disease"` 等多词 key 现在可命中
- ✅ **网络错误无处理**: 所有脚本 `main()` 加 try-except，输出友好中文错误提示

**P3 修复（功能增强）:**
- ✅ **缺少 --sort 选项**: `ncbi_search.py` 和 `pubmed_search.py` 新增 `--sort` 参数
- ✅ **批量 PMID 无分批**: `pubmed_fetch.py` 自动分批（每批 200 个 PMID）
- ✅ **缓存未区分 API Key**: 缓存键排除 `api_key` 参数，不同 Key 的查询结果共享缓存
- ✅ **requests 库缺失提示**: 导入失败时输出 `pip install requests` 安装指引

---

**技能状态**: 就绪
**API 要求**: NCBI API Key（免费，推荐配置）
**费用**: 完全免费
**依赖**: 仅需 Python 3.7+ 和 `requests` 库
