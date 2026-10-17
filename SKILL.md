---
name: ncbi-search
description: "Search biomedical literature and NCBI databases via the official free E-Utilities API. Use whenever the user mentions PubMed, papers, literature, reviews (论文/文献/综述), genes (基因), proteins, DNA/RNA sequences, SNPs or variants (rsID, 变异), ClinVar, taxonomy, or wants PubMed Central full text — even if they don't say 'NCBI'. Auto-routes queries to 10+ databases (PubMed, Gene, Protein, Nucleotide, dbSNP, ClinVar, Taxonomy, BioSample, Assembly, SRA), converts natural language to PubMed query syntax, and returns tiered abstracts (none/preview/full) for token-efficient progressive search, plus PMC Open Access full text via EFetch."
when_to_use: "Any biomedical or life-science information need: finding papers or reviews on a disease or therapy, gene function, protein/nucleotide sequences, SNP or clinical variant interpretation (rsID/VCV IDs), species taxonomy, sequencing data, or PMC Open Access full text. Triggers on words like paper, article, review, literature, gene, protein, variant, sequence, genome, PubMed, PMC, NCBI, and their Chinese equivalents (论文, 文献, 综述, 基因, 蛋白, 变异, 序列, 基因组). Prefer this skill over generic web search for biomedical questions."
---

# NCBI Search — AI Agent 工具文档

> **一句话描述**: NCBI 多数据库智能检索工具，使用官方 E-Utilities API，免费、可靠、零外部依赖（除 requests）。

> **路径约定（重要）**: 本文档所有命令中的 `scripts/*.py` 均相对于**本技能安装目录**（技能加载时给出的 base directory），而非当前工作目录。实际执行时请拼接为绝对路径，例如 `python "<技能根目录>/scripts/ncbi_search.py" "APOE gene"`。本地缓存同样写入技能目录下的 `.ncbi_cache/`，不会污染用户当前项目。

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
| 用户提到"基因"时用 `--db gene` | 不要对纯数字查询（如"348"）自动路由到 Gene |
| 用户提到"文献/论文"时用 `--db pubmed` | 不要对含基因符号的查询直接路由到 Gene（先检查是否要查文献） |
| 用户给 rsID 时用 `--db snp` | 不要用 `--db snp` 查非 SNP 内容 |
| 不确定时默认用 PubMed | 不要同时查多个数据库（需分步执行） |
| 初步搜索用 `--abstract none` 节省 token | 不要默认获取完整摘要再自己截断 |
| 筛选阶段用 `--abstract preview`（默认） | 不要对大量结果都用 `--abstract full` |
| 最终选定论文后用 `--abstract full` 或 `--full-abstract` | 不要假设摘要会自动截断到 200 字符（现为 1000） |

---

## 2. 数据库总览

| 数据库 | 命令行名称 | 用途 | ID 格式 | 链接模板 |
|--------|-----------|------|---------|---------|
| **PubMed** | `pubmed` | 生物医学文献检索 | PMID（数字） | `https://pubmed.ncbi.nlm.nih.gov/{PMID}/` |
| **Gene** | `gene` | 基因信息查询 | Gene ID（数字） | `https://www.ncbi.nlm.nih.gov/gene/{ID}` |
| **Protein** | `protein` | 蛋白质序列 | Accession（字母+数字） | `https://www.ncbi.nlm.nih.gov/protein/{ACC}` |
| **Nucleotide** | `nucleotide` | 核酸序列 | Accession（字母+数字） | `https://www.ncbi.nlm.nih.gov/nuccore/{ACC}` |
| **dbSNP** | `snp` | SNP 变异查询 | rsID（rs+数字） | `https://www.ncbi.nlm.nih.gov/snp/{rsID}` |
| **ClinVar** | `clinvar` | 临床变异 | Variation ID（数字） | `https://www.ncbi.nlm.nih.gov/clinvar/variation/{ID}` |
| **Taxonomy** | `taxonomy` | 物种分类 | TaxID（数字） | `https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id={ID}` |
| **BioSample** | `biosample` | 生物样本信息 | Sample ID | `https://www.ncbi.nlm.nih.gov/biosample/{ID}` |
| **Assembly** | `assembly` | 基因组组装 | Assembly ID | `https://www.ncbi.nlm.nih.gov/assembly/{ID}` |
| **SRA** | `sra` | 测序数据归档 | SRA ID（SRR/ERR/DRR） | `https://www.ncbi.nlm.nih.gov/sra/{ID}` |

---

## 3. 脚本与用法

项目包含 5 个脚本（4 个可直接调用 + 1 个共享工具模块）：

| 脚本 | 功能 | 适用场景 |
|------|------|---------|
| `ncbi_search.py` | **主脚本**：多数据库智能搜索，自动意图识别，PubMed 使用 EFetch 获取完整摘要 | 大多数情况，推荐使用 |
| `pubmed_search.py` | **PubMed 专用**：自然语言转检索式，MeSH 词识别（含多词短语） | 仅 PubMed 检索，需要智能解析 |
| `pubmed_fetch.py` | **批量获取**：通过 PMID 列表批量获取文献详情，支持 200 PMID 分批 | 已有 PMID 列表，需要批量获取摘要 |
| `pmc_fetch.py` | **PMC 全文获取**：EFetch(db=pmc) 下载开放获取文献全文，解析 JATS XML 为分节正文，支持 PMID 自动转 PMCID | 需要文献**正文全文**（而非仅摘要） |
| `ncbi_utils.py` | 工具函数：缓存、编码修复 | 被其他脚本调用，不直接使用 |

### 3.1 搜索（ncbi_search.py / pubmed_search.py）

```bash
# 自动判断搜索意图
python scripts/ncbi_search.py "APOE gene"                    # → Gene
python scripts/ncbi_search.py "Alzheimer disease review"     # → PubMed
python scripts/ncbi_search.py "rs429358"                     # → dbSNP
python scripts/ncbi_search.py "insulin protein"              # → Protein

# 指定数据库 + 高级过滤
python scripts/ncbi_search.py "APOE" --db gene --organism human
python scripts/ncbi_search.py "diabetes treatment" --db pubmed --years 5 --type review --max 20 --abstract full
python scripts/ncbi_search.py "COVID-19 vaccine" --type clinical_trial --max 50
python scripts/ncbi_search.py "alzheimer" --db pubmed --min-year 2020 --max-year 2023 --max 10
python scripts/ncbi_search.py "alzheimer" --db pubmed --max 10 --offset 10   # 翻页：跳过前 10 条
python scripts/ncbi_search.py "rs429358, rs7412" --db snp --max 5            # 批量 rsID

# PubMed 自然语言智能检索（宽松策略：MeSH/基因符号加标签，普通词原样传入）
python scripts/pubmed_search.py "Alzheimer disease cerebrovascular mechanisms"
python scripts/pubmed_search.py "APOE gene and Alzheimer disease" --years 5
python scripts/pubmed_search.py "Smith J author Alzheimer" --max 20
python scripts/pubmed_search.py "cancer immunotherapy" --mesh "Neoplasms" --years 3 --sort pub_date

# 特殊字符（连字符等）均可
python scripts/ncbi_search.py "IL-6 gene" --db gene

# 用户用中文提问时：常见术语自动英译（词表覆盖 ~80 个高频词；词表外需手动翻译）
python scripts/ncbi_search.py "阿尔茨海默病 综述"   # → "Alzheimer Disease"[MeSH] AND Review[pt]
python scripts/ncbi_search.py "Alzheimer disease review" --db pubmed   # 等价写法（推荐）
```

### 3.2 批量获取（pubmed_fetch.py）

```bash
# 通过 PMID 列表获取（自动分批，每批 200 个）
python scripts/pubmed_fetch.py 33597265 34239348 35022842 --abstract full

# 从文件读取大量 PMID
python scripts/pubmed_fetch.py -f pmids.txt --abstract full -o results.txt
```

### 3.3 PMC 全文获取（pmc_fetch.py）

当用户需要文献**正文全文**（不只是摘要）时使用：

```bash
# 先用 --outline 看章节大纲（最省 Token），确认需要再取正文
python scripts/pmc_fetch.py PMC8241728 --outline

# 只取指定章节（按标题子串匹配，如 results/conclusion/methods）
python scripts/pmc_fetch.py PMC8241728 --sections conclusion --max-chars 2000

# 取正文（默认截断到 6000 字符；--max-chars 0 取完整正文）
python scripts/pmc_fetch.py PMC8241728
python scripts/pmc_fetch.py PMC8241728 --max-chars 12000

# 用 PMID 获取（自动经 ELink 批量转换为 PMCID）
python scripts/pmc_fetch.py 34239348 33597265 --pmid --abstract full

# JSON 结构化输出（正文只存一份）
python scripts/pmc_fetch.py PMC8241728 --format json -o fulltext.json
```

> **重要**: 只有 **PMC 开放获取子集（Open Access Subset）** 的文献能返回正文；其他文献仅返回元数据+摘要并标注 `Full text: no`。典型工作流：先用 `ncbi_search.py`/`pubmed_search.py` 拿到 PMID，再用 `pmc_fetch.py <PMID> --pmid` 获取全文。

---

## 4. 核心参数速查

| 参数 | 适用脚本 | 说明 |
|------|---------|------|
| `--db <name>` | ncbi_search | 指定数据库（默认自动识别） |
| `--max N` | 搜索类 | 最大结果数（默认 10，1-200） |
| `--abstract none/preview/full` | pubmed 系 | 摘要分级：none 仅标题（默认）/ preview 按句截断 ~400 字符 / full 完整摘要+DOI+MeSH |
| `--years N` | 仅 pubmed | 限制最近 N 年（滚动窗口） |
| `--min-year` / `--max-year` | 仅 pubmed | 精确年份区间（优先于 `--years`） |
| `--offset N` | 搜索类 | 跳过前 N 条结果（翻页，如 `--max 10 --offset 10`） |
| `--type review/...` | 仅 pubmed | 文章类型过滤 |
| `--organism <sp>` | 仅 gene | 物种过滤（human→Homo sapiens 等自动映射） |
| `--mesh` | 仅 pubmed | MeSH 主题词筛选（无效词会打印警告） |
| `--sort relevance/pub_date/Author/Journal` | 仅 pubmed | 排序方式（默认 relevance） |
| `--format summary/json`、`-o <file>` | 全部 | 输出格式与保存 |
| `--count-only` | 搜索类 | 只输出命中数（不抓取记录，最省 token） |
| `--pmid` | pmc_fetch | 输入按 PMID 处理，经 ELink 批量转 PMCID |
| `--outline` / `--max-chars N` / `--sections` | pmc_fetch | 仅章节大纲 / 截断正文到 N 字符（默认 6000，0=不限）/ 只取匹配章节（逗号分隔） |
| `-f <file>`、`--batch-size N` | fetch 类 | 从文件读 ID / 分批大小（pubmed 200，pmc 20，上限 200） |

> `--full-abstract` 仍可用作 `--abstract full` 的简写（向后兼容）。
> 完整参数表、`--type`/`--sort` 可选值、参数组合合法性规则 → **`references/parameters.md`**。

---

## 5. 渐进式检索策略（Token 优化，推荐）

为节省 Token 消耗，AI Agent 应采用三步渐进式检索：

```bash
# Step 1 — 广泛搜索（Tier 1, 默认）：仅返回标题和元数据
python scripts/ncbi_search.py "Alzheimer APOE" --db pubmed --max 20

# Step 2 — 筛选摘要（Tier 2）：按句截断 ~400 字符，结论优先
python scripts/ncbi_search.py "Alzheimer APOE" --db pubmed --max 10 --abstract preview

# Step 3 — 获取完整摘要（Tier 3, 仅选中的论文）
python scripts/pubmed_fetch.py 34239348 33597265 --abstract full --format summary
```

| 级别 | `--abstract` 值 | 输出内容 | 使用场景 | Token 成本 |
|------|----------------|---------|---------|----------|
| Tier 1 | `none`（默认） | 标题、作者（3 人）、期刊、年份 | 广泛搜索，初筛 | 最低（~40 token/条） |
| Tier 2 | `preview` | Tier 1 + 按句截断 ~400 字符摘要（CONCLUSIONS/RESULTS 优先） | 二次筛选 | 中等（~150 token/条） |
| Tier 3 | `full` | Tier 2 + 完整摘要 + DOI + MeSH | 最终选定论文 | 最高（~450 token/条） |

PMC 全文同理：先 `--outline` 看结构，确认需要再取正文（默认截断 6000 字符），超长用 `--max-chars` 截断。

---

## 6. 错误与运维速查

### 6.1 常见错误

| 错误 | 原因 | 处理方式 |
|------|------|---------|
| `HTTP 429` | 请求过于频繁 | 等待 1 秒后重试（自动处理） |
| `HTTP 500/502/503/504` | 服务器/网关错误 | 自动重试 3 次 |
| `ConnectionError` / `Timeout` | 网络问题 | 检查网络；减少结果数或重试（脚本输出友好提示） |
| `0 results` | 无匹配结果 | 脚本自动打印提示（中文→英文 / 放宽过滤建议）；见 6.3 |
| `ModuleNotFoundError: requests` | 依赖缺失 | `pip install requests` |

> Windows 编码问题已修复：脚本自动将 stdout/stderr 配置为 UTF-8，`\xa0` 等字符不会导致崩溃。

### 6.2 速率限制（脚本内置，无需手动处理）

- 无 API Key：间隔 ≥ 0.34 秒（≤ 3 次/秒）；有 API Key：间隔 ≥ 0.11 秒（≤ 10 次/秒）
- 遇 429/500/502/503/504 自动重试 4 次（尊重 Retry-After；connect 10 秒超时 + 可配置 read 超时）

### 6.3 无结果应对

| 情况 | 建议操作 |
|------|---------|
| 中文查询返回 0 | PubMed 主要收录英文文献，将关键词译为英文重试（如"阿尔茨海默病 综述"→"Alzheimer disease review"） |
| 查询太具体 | 使用更宽泛的术语，或直接用自然语言（不加字段标签） |
| 拼写错误 | 检查拼写，尝试同义词 |
| 数据库不对 | 尝试其他数据库 |
| 过滤太严格 | 减少过滤条件（去掉 --years, --type 等） |
| 自然语言转换问题 | 用 `ncbi_search.py` 直接传入查询（不做词拆解），或手动构建检索式（见 references/query_syntax.md） |

### 6.4 缓存与 API Key

- **缓存**: ESearch/ESummary/EFetch 响应自动缓存到技能目录 `.ncbi_cache/cache.db`，有效期默认 24 小时（`NCBI_CACHE_EXPIRE_HOURS` 可调）；`NCBI_NO_CACHE=1` 强制实时请求；`NCBI_CACHE_MAX_ROWS`（默认 5000）限制缓存行数。
- **错误响应不缓存**: HTTP 200 + ERROR XML 会直接报错，不会污染缓存。
- **API Key**: 环境变量 `NCBI_API_KEY` 或 `--api-key` 传入。免费获取：注册 [NCBI 账号](https://www.ncbi.nlm.nih.gov/account/) → Settings → API Key Management。无 Key 也能用（限 3 次/秒）。

```powershell
# Windows PowerShell（永久配置）
[Environment]::SetEnvironmentVariable("NCBI_API_KEY", "your-api-key", "User")
```

---

## 7. 参考文件（按需阅读）

| 文件 | 内容 | 何时读 |
|------|------|--------|
| `references/parameters.md` | 4 个脚本的完整参数表、参数组合合法性、批量处理 | 需要精确参数语义或组合规则时 |
| `references/query_syntax.md` | PubMed 检索式语法：自然语言转换规则、字段标签、布尔运算、MeSH、通配符 | 构造复杂检索式或自动转换不理想时 |
| `references/result_format.md` | 各数据库结果字段含义与提取建议 | 解析输出、提取特定字段时 |
| `references/changelog.md` | v2-v4 版本历史 | 了解功能演进 |

---

## 8. 文件结构

```
ncbi-search/
├── SKILL.md                    # 本文档（精简版：决策树 + 用法 + 速查）
├── README.md                   # 用户文档
├── scripts/
│   ├── ncbi_search.py          # 主脚本：多数据库智能搜索（PubMed 用 EFetch）
│   ├── pubmed_search.py        # PubMed 专用：自然语言转检索式（宽松策略 + ElementTree）
│   ├── pubmed_fetch.py         # 批量获取：分批处理 + 完整摘要
│   ├── pmc_fetch.py            # PMC 全文获取：EFetch db=pmc + JATS 解析（PMID 自动转 PMCID）
│   ├── ncbi_utils.py           # 工具函数（缓存 + 编码修复 + ElementTree 辅助）
│   └── test_ncbi.py            # 单元测试（离线）
└── references/
    ├── parameters.md           # 完整参数表与批量处理
    ├── query_syntax.md         # PubMed 检索语法指南
    ├── result_format.md        # 结果字段解析
    └── changelog.md            # 更新日志
```

---

**版本**: v4.0.0
**技能状态**: 就绪
**API 要求**: NCBI API Key（免费，推荐配置）
**费用**: 完全免费
**依赖**: 仅需 Python 3.7+ 和 `requests` 库
