# NCBI Search

<div align="center">

[![NCBI](https://img.shields.io/badge/NCBI-E--Utilities-blue)](https://www.ncbi.nlm.nih.gov/books/NBK25501/)
[![Python](https://img.shields.io/badge/Python-3.7+-green)](https://www.python.org/)
[![Free](https://img.shields.io/badge/API-Free-success)](https://www.ncbi.nlm.nih.gov/account/)

**智能多数据库检索工具 | 直接调用NCBI官方API | 无需第三方服务**

[English](#english) | [中文](#中文)

</div>

---

## 中文

### ✨ 功能特性

- 🎯 **智能意图识别** - 自动判断搜索目标数据库（文献/基因/变异等），支持通用基因正则匹配
- 📚 **多数据库支持** - PubMed, Gene, Protein, dbSNP, ClinVar 等 10+ 数据库
- 🔄 **自然语言转换** - 宽松策略：MeSH词和基因符号加字段标签，普通关键词原样传入 PubMed
- 📄 **分级摘要输出** - PubMed 结果支持三级摘要显示：`none`（仅标题+元数据，默认）、`preview`（按句截断约 400 字符，结论优先）、`full`（完整摘要+DOI+MeSH），渐进式检索节省 Token
- 📖 **PMC 全文获取** - 通过 EFetch 直接下载 PubMed Central 开放获取（Open Access）文献全文，自动解析 JATS XML 为分节正文，支持 PMID 自动转 PMCID
- 🏗️ **ElementTree 解析** - 结构化 XML 解析替代脆弱正则，支持结构化摘要和机构作者
- ⚡ **零外部依赖** - 仅需 `requests`，直接调用 NCBI 官方 E-Utilities API
- 💾 **SQLite 本地缓存** - 自动缓存查询结果，二次查询毫秒级响应
- 💰 **完全免费** - 使用自己的 NCBI API Key，无任何费用
- 🚀 **速率优化** - 自动重试、智能限流、支持高并发
- 🛡️ **Windows 编码安全** - 自动处理 GBK/UTF-8 编码，不再因特殊字符崩溃
- 🔀 **排序与分批** - `--sort` 按相关性/日期排序，批量 PMID 自动分批处理；支持 `--min-year/--max-year` 年份区间与 `--offset` 翻页
- 📊 **CSV 导出** - `--format csv` 导出 rank/PMID/标题/作者/期刊/年份/DOI/URL/摘要，便于综述筛选
- 🧬 **批量 rsID** - `--db snp` 支持逗号分隔的多个 rsID（如 APOE rs429358, rs7412），一次精确取回
- 🧪 **单元测试覆盖** - 内置自动化测试套件

### 📦 安装

```bash
# 克隆仓库
git clone https://github.com/Side-Peng/ncbi-search.git
cd ncbi-search

# 安装依赖（仅需 requests）
pip install requests
```

> 如果未安装 `requests`，脚本会自动输出安装提示。

### 🔑 配置 API Key

1. 注册 [NCBI 账号](https://www.ncbi.nlm.nih.gov/account/)
2. 进入 Settings → API Key Management → Create API Key
3. 配置环境变量：

```bash
# Linux/macOS
export NCBI_API_KEY="your-api-key-here"

# Windows PowerShell (永久)
[Environment]::SetEnvironmentVariable("NCBI_API_KEY", "your-api-key", "User")

# 或在命令行指定
python scripts/ncbi_search.py "query" --api-key "your-api-key"
```

**速率限制**：无 API Key 3次/秒，有 API Key 10次/秒

### 🚀 快速开始

```bash
# 自动识别搜索意图（PubMed 现在返回完整摘要！）
python scripts/ncbi_search.py "APOE gene"                    # → Gene 数据库
python scripts/ncbi_search.py "Alzheimer disease review"     # → PubMed (含摘要)
python scripts/ncbi_search.py "rs429358"                     # → dbSNP
python scripts/ncbi_search.py "VCV000242862"                 # → ClinVar

# 指定数据库
python scripts/ncbi_search.py "APOE" --db gene --organism human
python scripts/ncbi_search.py "insulin" --db protein

# PubMed 高级过滤
python scripts/ncbi_search.py "diabetes treatment" --years 5 --type review --max 20 --abstract full
python scripts/ncbi_search.py "Alzheimer amyloid beta" --sort pub_date --max 10

# 渐进式检索（节省 Token，推荐 AI Agent 使用）
python scripts/ncbi_search.py "Alzheimer APOE" --db pubmed --max 20 --abstract none    # Step 1: 仅标题
python scripts/ncbi_search.py "Alzheimer APOE" --db pubmed --max 10 --abstract preview  # Step 2: 摘要预览
python scripts/pubmed_fetch.py 34239348 33597265 --abstract full                         # Step 3: 完整摘要
```

### 📖 使用示例

#### PubMed 文献检索

```bash
# 近5年阿尔茨海默病综述（含完整摘要）
python scripts/ncbi_search.py "Alzheimer disease" --years 5 --type review --abstract full

# 按出版日期排序
python scripts/ncbi_search.py "COVID-19 vaccine" --sort pub_date --max 20

# 指定作者和期刊
python scripts/ncbi_search.py "Smith J[Author] AND Nature[Journal]"

# 临床试验
python scripts/ncbi_search.py "diabetes" --type clinical_trial

# 自然语言查询（宽松策略，不再强制每个词加字段标签）
python scripts/pubmed_search.py "p-tau217 Abeta42 blood plasma Alzheimer biomarker"
```

输出示例：
```
======================================================================
PubMed Search Results
======================================================================
Query: "Alzheimer Disease"[MeSH] AND Review[pt] AND 2021/07/08:2026/07/08[PDat]
Total: 21355 articles | Returned: 10 articles
======================================================================

[1] PMID: 34239348
Title: Interaction between Aβ and Tau in the Pathogenesis...
Authors: Zhang H, Wei W, Zhao M et al.
Journal: International journal of biological sciences (2021)
DOI: 10.7150/ijbs.58296
Abstract: Alzheimer's disease (AD) is a neurodegenerative disorder
characterized by progressive memory loss and cognitive decline.
The pathogenesis of AD involves complex interactions between
amyloid-beta (Aβ) plaques and tau neurofibrillary tangles...
MeSH: Alzheimer Disease; Amyloid beta-Peptides; Tau Proteins
URL: https://pubmed.ncbi.nlm.nih.gov/34239348/
----------------------------------------------------------------------
```

> **v2 更新**：PubMed 结果现在支持三级摘要显示：`none`（仅标题+元数据，默认）、`preview`（约 400 字符按句截断，结论优先）、`full`（完整摘要+DOI+MeSH）。`--full-abstract` 仍可用作 `--abstract full` 的简写。

#### Gene 基因检索

```bash
python scripts/ncbi_search.py "APOE gene" --organism human

# 输出
======================================================================
Gene Search Results
======================================================================
Query: APOE AND human[Organism]
Total: 1 gene
======================================================================

[1] Gene ID: 348
Symbol: APOE
Description: apolipoprotein E
Chromosome: 19
URL: https://www.ncbi.nlm.nih.gov/gene/348
----------------------------------------------------------------------
```

#### dbSNP 变异检索

```bash
python scripts/ncbi_search.py "rs429358"

# 输出
======================================================================
dbSNP Search Results
======================================================================
Query: rs429358
Total: 1 variant
======================================================================

[1] rsID: rs429358
Genes: APOE
URL: https://www.ncbi.nlm.nih.gov/snp/rs429358
----------------------------------------------------------------------
```

#### 批量获取文献详情

```bash
# 通过 PMID 列表获取（自动分批，每批 200 个）
python scripts/pubmed_fetch.py 33597265 34239348 35022842 --abstract full

# 从文件读取大量 PMID（自动分批处理）
python scripts/pubmed_fetch.py -f pmids.txt --format summary --abstract full -o results.txt

# 指定分批大小
python scripts/pubmed_fetch.py -f pmids.txt --batch-size 100
```

#### PMC 开放获取全文获取

`pubmed_fetch.py` 只能拿到摘要；如需**正文全文**，使用 `pmc_fetch.py`，它通过 EFetch（`db=pmc`）直接下载 PubMed Central 开放获取文献的 JATS XML 并解析为分节正文。

```bash
# 直接用 PMC ID 获取全文（PMC 前缀可选）
python scripts/pmc_fetch.py PMC8241728
python scripts/pmc_fetch.py 8241728 5334499

# 用 PMID 获取（自动经 ELink 转换为 PMCID）
python scripts/pmc_fetch.py 34239348 33597265 --pmid --abstract full

# 只看章节大纲（节省 Token，先判断结构再决定是否取全文）
python scripts/pmc_fetch.py PMC8241728 --outline

# 只取指定章节（按标题子串匹配，最省 Token）
python scripts/pmc_fetch.py PMC8241728 --sections conclusion --max-chars 2000

# 截断超长正文（默认 6000 字符；0 = 完整正文）
python scripts/pmc_fetch.py PMC8241728 --max-chars 3000

# JSON 结构化输出（content 分块，不再重复存 full_text）
python scripts/pmc_fetch.py PMC8241728 --format json -o fulltext.json
```

> **注意**: 只有属于 **PMC 开放获取子集（Open Access Subset）** 的文献才能返回正文全文；其他文献仅返回元数据与摘要，并标注 `Open Access Full Text: No`（出版商不允许下载 XML 全文）。不在 PMC 中的 PMID 会被跳过并提示 `Not in PMC`。

### 💾 本地缓存机制

工具内置了零外部依赖的 SQLite 本地自动缓存，所有 NCBI API 响应结果会自动持久化存储在 `.ncbi_cache/cache.db` 中。

| 特性 | 说明 |
|------|------|
| **自动缓存** | ESearch、ESummary、EFetch 响应全部自动存储 |
| **缓存有效期** | 默认 24 小时，支持自定义 |
| **二次查询** | 命中缓存时 1-5ms 响应，零网络请求 |
| **API Key 共享** | 缓存键不包含 API Key，同一查询在不同 Key 间共享 |
| **禁用方式** | 设置 `NCBI_NO_CACHE=1` 环境变量 |

```bash
# 调整缓存有效期（例如 48 小时）
$env:NCBI_CACHE_EXPIRE_HOURS = "48"    # Windows PowerShell

# 临时禁用缓存
$env:NCBI_NO_CACHE = "1"
python scripts/ncbi_search.py "APOE gene"

# 使用 verbose 模式查看缓存命中情况
python scripts/ncbi_search.py "APOE gene" -v
```

### 🗄️ 支持的数据库

| 数据库 | 用途 | 触发关键词 |
|--------|------|-----------|
| **pubmed** | 文献检索 | paper, article, review, 论文, 文献 |
| **gene** | 基因信息 | gene, 基因, symbol, 或自动识别基因符号 |
| **protein** | 蛋白质序列 | protein, 蛋白, sequence |
| **nucleotide** | 核酸序列 | DNA, RNA, 序列, genome |
| **snp** | SNP变异 | SNP, rs, 变异, variant |
| **clinvar** | 临床变异 | clinvar, pathogenic, 致病, 或 VCV 编号 |
| **taxonomy** | 物种分类 | species, 物种, taxonomy |
| **biosample** | 生物样本 | biosample, 样本 |
| **assembly** | 基因组组装 | genome assembly, 组装 |
| **sra** | 测序数据 | SRA, sequencing |

### 🎯 智能路由优先级

```
用户查询
│
├─ 包含 rs\d+ 模式（如 rs429358）? → dbSNP
├─ 包含 VCV\d+ 模式（如 VCV000242862）? → ClinVar
├─ 包含已知/通用基因符号?
│   ├─ 同时含文献关键字? → PubMed
│   └─ 否则 → Gene
├─ 包含特定数据库关键词? → 对应数据库
└─ 以上都不匹配 → PubMed（默认）
```

### 📝 命令行参数

#### ncbi_search.py（主脚本）

```
python scripts/ncbi_search.py <query> [options]

必需参数:
  query                 搜索查询（自然语言或标准检索式）

可选参数:
  --db DATABASE         指定数据库（不指定则自动识别）
  --max N               最大返回结果数（默认: 10）
  --years N             限制最近 N 年（仅 PubMed）
  --type TYPE           文章类型: review, clinical_trial 等（仅 PubMed）
  --sort SORT           排序方式: relevance, pub_date, Author, Journal（默认: relevance）
  --full-abstract       显示完整摘要（不截断，仅 PubMed）[向后兼容]
  --abstract MODE       摘要分级: none(仅标题,默认), preview(约400字符按句截断), full(完整)
  --organism ORGANISM   限制物种（仅 Gene）
  --format FORMAT       输出格式: summary, json（默认: summary）
  --output FILE         保存到文件
  --api-key KEY         NCBI API Key
  --verbose             显示详细信息（含缓存命中状态）
```

#### pubmed_search.py（PubMed 专用）

```
python scripts/pubmed_search.py <query> [options]

必需参数:
  query                 自然语言检索词或 PubMed 检索式

可选参数:
  --max N               最大返回结果数（默认: 10）
  --years N             限制最近 N 年
  --type TYPE           文章类型: review, clinical_trial, randomized, meta_analysis
  --mesh MESH           MeSH 主题词筛选
  --sort SORT           排序方式: relevance, pub_date, Author, Journal（默认: relevance）
  --full-abstract       显示完整摘要（不截断）[向后兼容]
  --abstract MODE       摘要分级: none(仅标题,默认), preview(约400字符按句截断), full(完整)
  --format FORMAT       输出格式: summary, json（默认: summary）
  --output FILE         保存到文件
  --api-key KEY         NCBI API Key
  --verbose             显示详细信息
```

#### pubmed_fetch.py（批量获取）

```
python scripts/pubmed_fetch.py <pmids...> [options]

必需参数:
  pmids                 PMID 列表（空格分隔）

可选参数:
  --file / -f FILE      从文件读取 PMID 列表
  --format FORMAT       输出格式: summary, json（默认: json）
  --full-abstract       显示完整摘要（不截断）[向后兼容]
  --abstract MODE       摘要分级: none(仅标题,默认), preview(约400字符按句截断), full(完整)
  --batch-size N        每批获取的最大 PMID 数（默认: 200）
  --output FILE         保存到文件
  --api-key KEY         NCBI API Key
  --verbose             显示详细信息
```

#### pmc_fetch.py（PMC 全文获取）

```
python scripts/pmc_fetch.py <ids...> [options]

必需参数:
  ids                   PMC ID 列表（如 PMC8241728 或 8241728），或配合 --pmid 传入 PMID

可选参数:
  --file / -f FILE      从文件读取 ID 列表（每行一个）
  --pmid                将输入视为 PMID，自动经 ELink 转换为 PMCID
  --outline             仅显示章节大纲（不含正文段落），节省 Token
  --max-chars N         截断正文到 N 字符（默认 6000，0 = 不限制）
  --abstract MODE       摘要分级: none, preview(约400字符,默认), full
  --batch-size N        每批获取的最大 PMC ID 数（默认: 20）
  --format FORMAT       输出格式: summary, json（默认: summary）
  --output FILE         保存到文件
  --api-key KEY         NCBI API Key
  --verbose             显示详细信息
```

### 🔄 自然语言转换策略（v2）

`pubmed_search.py` 的自然语言转换采用**宽松策略**：

| 元素类型 | 转换方式 | 示例 |
|---------|---------|------|
| **MeSH 词**（含多词短语） | 加 `[MeSH]` 后缀 | `"Alzheimer Disease"[MeSH]` |
| **基因符号** | 加 `[Title/Abstract]` | `APOE[Title/Abstract]` |
| **作者** | 加 `[Author]` | `Smith J[Author]` |
| **普通关键词** | 原样传入（不加字段标签） | `(p-tau217 Abeta42 biomarker)` |
| **文章类型** | 加 `[pt]` | `Review[pt]` |

> 与 v1 的区别：v1 把所有词都加 `[Title/Abstract]` AND 连接，导致专有名词查询返回 0 篇。v2 只对 MeSH 和基因加字段标签，普通关键词让 PubMed 自然处理。

### 📁 项目结构

```
ncbi-search/
├── README.md                   # 本文档
├── SKILL.md                    # AI Agent 技能说明文档（精简版：决策树 + 用法 + 速查）
├── .ncbi_cache/                # 本地 SQLite 缓存目录（自动生成）
│   └── cache.db                # 缓存数据库
├── scripts/
│   ├── ncbi_search.py          # 主脚本（多数据库智能搜索，PubMed 用 EFetch）
│   ├── pubmed_search.py        # PubMed 专用（自然语言转检索式 + ElementTree）
│   ├── pubmed_fetch.py         # PMID 批量获取（分批处理 + 完整摘要）
│   ├── pmc_fetch.py            # PMC 开放获取全文获取（EFetch db=pmc + JATS 解析）
│   ├── ncbi_utils.py           # 共享工具函数（缓存 + 编码修复 + ElementTree 辅助）
│   └── test_ncbi.py            # 单元测试套件
└── references/                 # 渐进披露：技能触发时按需加载，降低 token 开销
    ├── parameters.md           # 完整参数表与批量处理
    ├── query_syntax.md         # PubMed 检索语法指南（含自然语言转换规则）
    ├── result_format.md        # 结果字段解析
    └── changelog.md            # 更新日志
```

### 🧪 运行测试

```bash
python scripts/test_ncbi.py
```

测试覆盖：意图路由准确性、SQLite 缓存读写、缓存禁用环境变量、速率限制机制。

### 🔧 作为 Agent Skill 使用

本项目设计为 AI Agent（如 Claude、Gemini 等）的技能插件。在 SKILL.md 中定义了详细的触发规则和使用说明。

### 📋 更新日志

#### 3.0.0 (2026-10-17) — 准确性与 token 效率重构

- ✅ **准确性**：作者线索词门控、小写布尔映射、类型词边界、连字符/引号短语、MeSH 默认不强制标注（交给 ATM）、年份→`[PDat]`、路由重写、Gene `[Gene Name]`、dbSNP `[UID]`/`[RS]` 回退
- ✅ **Token**：默认 `--abstract none`、JSON 分级裁剪、按句摘要截断（结论优先）、PMC 默认 6000 字符、`--sections`
- ✅ **效率**：ELink 批量、NCBI 错误体不缓存、Tier1 改 ESummary v2.0、SQLite WAL、跨进程共享限速（文件锁）、tool/email 合规标识
- ✅ **功能**：`--count-only`、`--offset` 翻页、`--min-year/--max-year`、批量 rsID、CSV 导出、MeSH 校验、PMC license 解析、各库专用格式化
- ⚠️ **破坏性变更**：默认输出层级与紧凑格式、JSON 字段调整（`total`/`id`/`offset`）
- ✅ 文档同步（SKILL/parameters/result_format/AGENTS）+ 新增 OPTIMIZATION_PLAN.md；单测 7→29 项

#### v2.0.2 (2026-08-02) — PMC 全文获取与 EFetch 分批

**功能增强：**
- ✅ **PMC 开放获取全文获取**: 新增 `pmc_fetch.py`，通过 EFetch（`db=pmc`）直接下载 PubMed Central 开放获取文献的 JATS XML 并解析为分节正文
- ✅ **PMID 自动转 PMCID**: `--pmid` 选项经 ELink（`linkname=pubmed_pmc`）自动将 PMID 转换为其对应 PMCID
- ✅ **Token 友好**: `--outline` 仅显示章节大纲，`--max-chars` 截断超长正文，`--abstract` 三级摘要
- ✅ **优雅降级**: 非开放获取文献标注 `Open Access Full Text: No`，仍返回元数据与摘要；不在 PMC 的 PMID 提示 `Not in PMC`
- ✅ 新增 PMC 解析与 PMC ID 归一化的离线单元测试

#### v2 (2026-07-08)

**致命问题修复：**
- ✅ Windows GBK 编码崩溃 — 自动配置 stdout/stderr 为 UTF-8
- ✅ PubMed 结果无摘要 — 改用 EFetch API，默认返回摘要

**重要问题修复：**
- ✅ 摘要截断太短 — 200→1000 字符，新增 `--full-abstract`
- ✅ 自然语言转换过于激进 — 宽松策略，普通关键词不加字段标签

**代码质量改进：**
- ✅ XML 正则解析 → ElementTree（支持结构化摘要、机构作者）
- ✅ detect_database 死代码删除
- ✅ 多词 MeSH 匹配修复（贪婪短语匹配）
- ✅ 网络错误 try-except（友好中文提示）

**功能增强：**
- ✅ `--sort` 排序选项（relevance/pub_date/Author/Journal）
- ✅ 批量 PMID 分批处理（每批 200 个）
- ✅ 缓存键排除 API Key（跨 Key 共享）
- ✅ requests 缺失自动提示安装

### 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

### 🙏 致谢

- [NCBI E-Utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/) - 官方 API

---

## English

### ✨ Features

- 🎯 **Smart Intent Detection** - Automatically routes queries to appropriate databases, with universal gene symbol regex matching
- 📚 **Multi-Database Support** - PubMed, Gene, Protein, dbSNP, ClinVar, and 10+ more
- 🔄 **Relaxed NL Strategy** - MeSH terms and gene symbols get field tags; plain keywords pass through to PubMed naturally
- 📄 **Tiered Abstract Output** - Three-level abstract display: `none` (title + metadata, default), `preview` (~400 chars, sentence-aware, conclusions first), `full` (complete abstract + DOI + MeSH) for progressive token-efficient search
- 📖 **PMC Full Text** - Download PubMed Central Open Access full text directly via EFetch, parsing JATS XML into readable sections; supports PMID→PMCID auto-conversion
- 🏗️ **ElementTree Parsing** - Structured XML parsing replaces fragile regex, supporting structured abstracts and collective authors
- ⚡ **Minimal Dependencies** - Only `requests` needed; direct NCBI E-Utilities API calls
- 💾 **SQLite Local Cache** - Automatic query caching with millisecond-level repeat lookups
- 💰 **Completely Free** - Uses your own NCBI API key
- 🚀 **Rate Optimized** - Auto-retry, smart throttling, high concurrency support
- 🛡️ **Windows Encoding Safe** - Auto UTF-8 stdout/stderr configuration; no crashes from special characters
- 🔀 **Sort & Batch** - `--sort` by relevance/date; batch PMID fetch (200 per batch)
- 🧪 **Unit Tested** - Built-in test suite for routing and caching logic

### 📦 Installation

```bash
git clone https://github.com/Side-Peng/ncbi-search.git
cd ncbi-search
pip install requests
```

> The script will prompt you to install `requests` if it's missing.

### 🔑 API Key Setup

1. Register at [NCBI](https://www.ncbi.nlm.nih.gov/account/)
2. Go to Settings → API Key Management → Create API Key
3. Configure:

```bash
# Linux/macOS
export NCBI_API_KEY="your-api-key"

# Windows PowerShell (permanent)
[Environment]::SetEnvironmentVariable("NCBI_API_KEY", "your-api-key", "User")

# Or specify on command line
python scripts/ncbi_search.py "query" --api-key "your-api-key"
```

**Rate limits**: 3 req/s without API key, 10 req/s with API key

### 🚀 Quick Start

```bash
# Auto-detect database (PubMed now includes abstracts!)
python scripts/ncbi_search.py "APOE gene"                # → Gene database
python scripts/ncbi_search.py "Alzheimer disease review" # → PubMed (with abstract)
python scripts/ncbi_search.py "rs429358"                 # → dbSNP
python scripts/ncbi_search.py "VCV000242862"             # → ClinVar

# Specify database
python scripts/ncbi_search.py "APOE" --db gene --organism human

# PubMed filters with full abstracts
python scripts/ncbi_search.py "diabetes" --years 5 --type review --max 20 --abstract full

# Sort by publication date
python scripts/ncbi_search.py "COVID-19 vaccine" --sort pub_date --max 20

# Natural language query (relaxed strategy)
python scripts/pubmed_search.py "p-tau217 Abeta42 blood plasma Alzheimer biomarker"
```

### 📖 Usage Examples

#### PubMed Literature Search

```bash
# Recent Alzheimer reviews with full abstracts
python scripts/ncbi_search.py "Alzheimer disease" --years 5 --type review --abstract full

# Sort by publication date
python scripts/ncbi_search.py "COVID-19 vaccine" --sort pub_date --max 20

# Complex Boolean query
python scripts/ncbi_search.py "(Alzheimer[Title/Abstract]) AND (APOE[Title/Abstract]) AND (Review[pt])"

# Clinical trials
python scripts/ncbi_search.py "diabetes" --type clinical_trial
```

Output example:
```
======================================================================
PubMed Search Results
======================================================================
Query: "Alzheimer Disease"[MeSH] AND Review[pt] AND 2021/07/08:2026/07/08[PDat]
Total: 21355 articles | Returned: 10 articles
======================================================================

[1] PMID: 34239348
Title: Interaction between Aβ and Tau in the Pathogenesis...
Authors: Zhang H, Wei W, Zhao M et al.
Journal: International journal of biological sciences (2021)
DOI: 10.7150/ijbs.58296
Abstract: Alzheimer's disease (AD) is a neurodegenerative disorder
characterized by progressive memory loss and cognitive decline...
MeSH: Alzheimer Disease; Amyloid beta-Peptides; Tau Proteins
URL: https://pubmed.ncbi.nlm.nih.gov/34239348/
----------------------------------------------------------------------
```

> **v2 update**: PubMed results now support three-level abstract display: `none` (title + metadata, default), `preview` (~400-char sentence-aware preview, conclusions first), `full` (complete + DOI + MeSH). `--full-abstract` still works as shorthand for `--abstract full`.

#### Batch Fetching

```bash
# Fetch by PMID list (auto-batched, 200 per batch)
python scripts/pubmed_fetch.py 33597265 34239348 35022842 --abstract full

# From file (auto-batched)
python scripts/pubmed_fetch.py -f pmids.txt --format summary --abstract full -o results.txt

# Custom batch size
python scripts/pubmed_fetch.py -f pmids.txt --batch-size 100
```

### 💾 Local Cache

All NCBI API responses are automatically cached in a local SQLite database (`.ncbi_cache/cache.db`). Repeat queries return instantly (1-5ms) with zero network requests. Cache expires after 24 hours by default. Cache keys exclude API keys, so the same query shares results across different keys.

```bash
# Customize cache TTL (hours)
export NCBI_CACHE_EXPIRE_HOURS=48    # Linux/macOS
$env:NCBI_CACHE_EXPIRE_HOURS = "48"  # Windows PowerShell

# Disable cache
export NCBI_NO_CACHE=1
```

### 🔄 Natural Language Strategy (v2)

`pubmed_search.py` uses a **relaxed strategy**:

| Element | Conversion | Example |
|---------|-----------|---------|
| **MeSH terms** (including multi-word) | Add `[MeSH]` suffix | `"Alzheimer Disease"[MeSH]` |
| **Gene symbols** | Add `[Title/Abstract]` | `APOE[Title/Abstract]` |
| **Authors** | Add `[Author]` | `Smith J[Author]` |
| **Plain keywords** | Pass through as-is (no field tag) | `(p-tau217 Abeta42 biomarker)` |
| **Article types** | Add `[pt]` | `Review[pt]` |

> v1 added `[Title/Abstract]` to every word AND-connected, causing zero results for specialized term queries. v2 only tags MeSH/gene terms; plain keywords are handled by PubMed's native search engine.

### 📋 Changelog

#### 3.0.0 (2026-10-17) — Accuracy & token-efficiency refactor

- ✅ **Accuracy**: clue-word-gated author parsing, lower-case boolean mapping, type word boundaries, hyphen/quote phrase preservation, MeSH tagging off by default (leave it to ATM), year → `[PDat]`, routing rewrite, Gene `[Gene Name]`, dbSNP `[UID]`/`[RS]` fallback
- ✅ **Tokens**: default `--abstract none`, tier-aware JSON trimming, sentence-aware abstract preview (conclusions first), PMC 6000-char default, `--sections`
- ✅ **Efficiency**: batched ELink, NCBI error bodies never cached, Tier-1 ESummary v2.0, SQLite WAL, cross-process shared rate limiting (file lock), tool/email identification
- ✅ **Features**: `--count-only`, `--offset` paging, `--min-year/--max-year`, batch rsIDs, CSV export, MeSH validation, PMC license parsing, per-database formatters
- ⚠️ **Breaking**: default output tier/format and JSON fields (`total`/`id`/`offset`)
- ✅ Docs synced (SKILL/parameters/result_format/AGENTS) + OPTIMIZATION_PLAN.md; tests 7→29

#### v2 (2026-07-08)

**Critical fixes:**
- ✅ Windows GBK encoding crash — auto UTF-8 stdout/stderr configuration
- ✅ PubMed results missing abstracts — switched to EFetch API

**Important fixes:**
- ✅ Abstract truncation too short — 200→1000 chars, added `--full-abstract`
- ✅ Overly aggressive NL conversion — relaxed strategy, plain keywords pass through

**Quality improvements:**
- ✅ Fragile regex XML parsing → ElementTree (structured abstracts, collective authors)
- ✅ Removed duplicate `detect_database` dead code
- ✅ Multi-word MeSH matching (greedy phrase matching)
- ✅ Network error try-except (friendly error messages)

**Feature enhancements:**
- ✅ `--sort` option (relevance/pub_date/Author/Journal)
- ✅ Batch PMID processing (200 per batch)
- ✅ Cache key excludes API key (cross-key sharing)
- ✅ Auto-install prompt for missing `requests`

### 🧪 Run Tests

```bash
python scripts/test_ncbi.py
```

### 🤝 Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Create a Pull Request

### 🙏 Acknowledgments

- [NCBI E-Utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/) - Official API

---

<div align="center">

**Made with ❤️ for researchers**

[⬆ Back to Top](#ncbi-search)

</div>
