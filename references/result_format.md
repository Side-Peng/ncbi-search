# 结果格式解析

> 本文件说明各数据库返回结果的字段含义与提取建议。解析输出、提取特定字段时查阅。
> 所有库统一使用紧凑单行输出；URL 可由 ID + 模板推导，summary 模式不再打印（JSON 保留）。

## 1. PubMed 结果字段

| 字段 | 说明 | 提取建议 |
|------|------|---------|
| `PMID` | PubMed 唯一标识符 | 用于生成引用与链接 `https://pubmed.ncbi.nlm.nih.gov/{PMID}/` |
| `Title` | 文章标题 | 判断相关性 |
| `Authors` | 前 3 位作者 + `et al.` | 提取第一作者/通讯作者 |
| `Journal` / `Year` | 期刊与出版年 | 判断影响力与时效性 |
| `Abstract` | `none` 不显示；`preview` 按句截断 ~400 字符（CONCLUSIONS/RESULTS 优先）；`full` 完整 | 判断论文是否支持特定论点 |
| `DOI` / `MeSH` | 仅 `full` 层显示 | 引用定位、主题分类 |

> Tier1（`--abstract none`，默认）用 ESummary v2.0（无摘要、轻量）；preview/full 用 EFetch。`--full-abstract` 等同 `--abstract full`。

## 2. Gene 结果字段

| 字段 | 说明 |
|------|------|
| `GeneID` | 基因唯一标识符（URL: `ncbi.nlm.nih.gov/gene/{ID}`） |
| `Symbol` | 基因符号 |
| `Description` | 基因描述 |
| `Chromosome` / `Organism` | 染色体位置、物种（学名） |

> 裸基因符号查询走 `{SYMBOL}[Gene Name]`；`--organism human` 自动映射为 `"Homo sapiens"[Organism]`（支持 human/mouse/rat/zebrafish/yeast/fly/worm/pig/cow/dog/chicken/monkey）。

## 3. dbSNP 结果字段（单行）

```
[1] rs429358 | APOE | chr19:44908684 | MAF C=0.151 (1000Genomes) | association, drug-response, ...
```

| 字段 | 说明 |
|------|------|
| `rsID` | rs 编号（纯 rsID 查询自动用 `{digits}[UID]`，避免合并记录噪音） |
| `Genes` | 关联基因 |
| `chrpos` | 染色体:位置 |
| `MAF` | 首个人群频率（3 位小数，附人群） |
| `clinical` | 临床意义（最多 4 项） |
| `merged->rs…` | 该记录已合并到目标 rsID（旧编号） |

## 4. ClinVar 结果字段（单行）

```
[1] VCV005016490 | Single allele | Likely pathogenic, criteria provided, single submitter | chr17:43095510-43114978 (GRCh38) | Breast-ovarian cancer, familial, susceptibility to, 1
```

| 字段 | 说明 |
|------|------|
| `VCV` accession | 变异记录编号（URL: `ncbi.nlm.nih.gov/clinvar/variation/{ID}`） |
| `variation_name` | 变异名称 |
| `classification` | 胚系/临床意义 + 审核状态 |
| `location` | 染色体区间（含组装版本） |
| `trait` | 关联疾病（最多 2 个） |

## 5. SRA 结果字段（单行）

```
[1] DRX783447 | sn-RNA seq of AHN dysfunction AD model mice | Mus musculus | RNA-Seq | 196,233,032 spots | 2026-09-25
```

| 字段 | 说明 |
|------|------|
| `Experiment` accession | 实验编号（DRX/SRX/ERX） |
| `Study` | 研究名称 |
| `Organism` | 物种 |
| `Strategy` | 文库策略（RNA-Seq 等） |
| `spots` | 读数（总 spots） |
| `createdate` | 发布日期 |

## 6. Assembly 结果字段（单行）

```
[1] GCF_000001405.40 | GRCh38.p14 | Homo sapiens (human) | Chromosome | reference genome | 2022-02-08
```

| 字段 | 说明 |
|------|------|
| `accession` | 组装编号（GCF_/GCA_） |
| `name` | 组装名称 |
| `organism` | 物种 |
| `status` | 组装级别（Chromosome/Scaffold…） |
| `refseq_category` | reference genome / representative genome 等 |
| `date` | 发布日期 |

## 7. BioSample 结果字段（单行）

```
[1] SAMN64254054 | One Health Enteric sample from Salmonella enterica | Salmonella enterica | PulseNet ... | 2026-10-16
```

| 字段 | 说明 |
|------|------|
| `accession` | 样本编号（SAMN/SAMEA） |
| `title` | 样本标题 |
| `organism` | 物种 |
| `organization` | 提交机构 |
| `date` | 公开发布日期 |

## 8. Taxonomy 结果字段（单行）

```
[1] 9606 | Homo sapiens (human) | species | primates
```

| 字段 | 说明 |
|------|------|
| `taxid` | 分类学 ID（URL: `ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id={ID}`） |
| `scientificname` / `commonname` | 学名 / 常用名 |
| `rank` | 分类等级 |
| `division` | GenBank 分类组 |

## 9. PMC 全文结果字段

| 字段 | 说明 |
|------|------|
| `PMCID` / `PMID` | 双标识符 |
| `Title` / `Authors` / `Journal` / `Year` / `DOI` | 元数据（作者前 3 位 + et al.） |
| `Full text` | `yes (N chars)` 或 `no (publisher blocked XML download)` |
| `Abstract` | `none` / `preview`（~400 字符）/ `full` |
| `Section Outline` | 章节大纲（`--outline`） |
| `Full Text` | 分节正文（JATS 解析）；`--sections` 只保留匹配章节；`--max-chars` 截断 |

> 非开放获取文献仅返回元数据+摘要并标注 `Full text: no`；不在 PMC 的 PMID 提示 `Not in PMC`。

## 10. 结果排序规则（PubMed）

| 排序方式 | 说明 | 命令参数 |
|---------|------|---------|
| relevance | 相关性排序（默认） | `--sort relevance` |
| pub_date | 按出版日期排序 | `--sort pub_date` |
| Author | 按作者排序 | `--sort Author` |
| Journal | 按期刊排序 | `--sort Journal` |

> 带 `--years` 时 relevance 为"窗口内重排"，需要最新文献请用 `--sort pub_date`。
