# 参数详解

> 本文件是 `SKILL.md` §4 核心参数速查的完整版。需要精确参数语义、默认值或参数组合合法性时查阅。

## 1. ncbi_search.py 参数

| 参数 | 类型 | 默认值 | 适用数据库 | 说明 |
|------|------|--------|-----------|------|
| `query` | 必填 | - | 全部 | 搜索查询（自然语言或标准检索式） |
| `--db` | 可选 | auto-detect | 全部 | 指定数据库，不指定则自动识别 |
| `--max` | int | 10 | 全部 | 最大返回结果数（1-200） |
| `--offset` | int | 0 | 搜索类 | 跳过前 N 条结果（翻页） |
| `--years` | int | - | **仅 pubmed** | 限制最近 N 年（滚动窗口） |
| `--min-year` / `--max-year` | int | - | **仅 pubmed** | 精确年份区间（优先于 `--years`） |
| `--type` | str | - | **仅 pubmed** | 文章类型过滤 |
| `--organism` | str | - | **仅 gene** | 物种过滤（自动映射：human→Homo sapiens、mouse→Mus musculus 等） |
| `--sort` | str | relevance | **仅 pubmed** | 排序方式：relevance, pub_date, Author, Journal |
| `--full-abstract` | bool | false | **仅 pubmed** | 显示完整摘要（不截断）[等同 --abstract full] |
| `--abstract` | str | none | **仅 pubmed** | 摘要分级：none(仅标题,默认), preview(按句截断 ~400 字符), full(完整) |
| `--format` | str | summary | 全部 | 输出格式：summary 或 json |
| `--count-only` | bool | false | 全部 | 只输出命中数（不抓取记录） |
| `--output` / `-o` | str | - | 全部 | 保存结果到文件 |
| `--api-key` | str | env var | 全部 | NCBI API Key |
| `--verbose` / `-v` | bool | false | 全部 | 显示详细信息 |

## 2. pubmed_search.py 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | 必填 | - | 自然语言检索词或 PubMed 检索式 |
| `--max` | int | 10 | 最大返回结果数（1-200） |
| `--offset` | int | 0 | 跳过前 N 条结果（翻页） |
| `--years` | int | - | 限制最近 N 年（滚动窗口） |
| `--min-year` / `--max-year` | int | - | 精确年份区间（优先于 `--years`） |
| `--type` | str | - | 文章类型：review, clinical_trial, randomized, meta_analysis, case_report |
| `--mesh` | str | - | MeSH 主题词筛选（运行时校验，无效词打印警告） |
| `--sort` | str | relevance | 排序方式：relevance, pub_date, Author, Journal |
| `--full-abstract` | bool | false | 显示完整摘要（不截断）[等同 --abstract full] |
| `--abstract` | str | none | 摘要分级：none(仅标题,默认), preview(按句截断 ~400 字符), full(完整) |
| `--format` | str | summary | 输出格式：summary 或 json |
| `--count-only` | bool | false | 只输出命中数（不抓取记录） |
| `--output` / `-o` | str | - | 保存结果到文件 |
| `--api-key` | str | env var | NCBI API Key |
| `--verbose` / `-v` | bool | false | 显示详细信息 |

## 3. pubmed_fetch.py 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pmids` | 必填 | - | PMID 列表 |
| `--file` / `-f` | str | - | 从文件读取 PMID 列表 |
| `--format` | str | summary | 输出格式：summary 或 json |
| `--full-abstract` | bool | false | 显示完整摘要（不截断）[等同 --abstract full] |
| `--abstract` | str | none | 摘要分级：none(仅标题,默认), preview(按句截断 ~400 字符), full(完整) |
| `--batch-size` | int | 200 | 每批获取的最大 PMID 数（1-200） |
| `--output` / `-o` | str | - | 保存结果到文件 |
| `--api-key` | str | env var | NCBI API Key |
| `--verbose` / `-v` | bool | false | 显示详细信息 |

## 4. pmc_fetch.py 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `ids` | 必填 | - | PMC ID 列表（如 PMC8241728 或 8241728），或配合 `--pmid` 传入 PMID |
| `--file` / `-f` | str | - | 从文件读取 ID 列表（每行一个） |
| `--pmid` | bool | false | 将输入视为 PMID，经 ELink 批量转换为 PMCID |
| `--outline` | bool | false | 仅显示章节大纲（不含正文段落），最省 Token |
| `--sections` | str | - | 只保留标题匹配的章节（逗号分隔子串，如 `results,conclusion`） |
| `--max-chars` | int | 6000 | 截断正文到 N 字符（0 = 不限制） |
| `--abstract` | str | preview | 摘要分级：none, preview(~400 字符,默认), full |
| `--batch-size` | int | 20 | 每批获取的最大 PMC ID 数（1-200） |
| `--format` | str | summary | 输出格式：summary 或 json |
| `--output` / `-o` | str | - | 保存结果到文件 |
| `--api-key` | str | env var | NCBI API Key |
| `--verbose` / `-v` | bool | false | 显示详细信息 |

## 5. --type 参数可选值

| 值 | 含义 | PubMed 标签 |
|----|------|-------------|
| `review` | 综述 | `Review[pt]` |
| `clinical_trial` | 临床试验 | `Clinical Trial[pt]` |
| `randomized` | 随机对照试验 | `Randomized Controlled Trial[pt]` |
| `meta_analysis` | Meta 分析 | `Meta-Analysis[pt]` |
| `case_report` | 病例报告 | `Case Reports[pt]` |

> `--type` 值大小写不敏感（`--type Review` 等价于 `--type review`）。

## 6. --sort 参数可选值

| 值 | 含义 | 适用场景 |
|----|------|---------|
| `relevance` | 相关性排序（默认） | 一般检索 |
| `pub_date` | 按出版日期排序 | 查看最新文献 |
| `Author` | 按作者排序 | 查找某作者的文献 |
| `Journal` | 按期刊排序 | 期刊浏览 |

## 7. 参数组合规则

| 组合 | 是否合法 | 说明 |
|------|---------|------|
| `--db pubmed --years 5` | ✅ 合法 | PubMed 限定年份 |
| `--db pubmed --type review` | ✅ 合法 | PubMed 限定文章类型 |
| `--db pubmed --full-abstract` | ✅ 合法 | PubMed 显示完整摘要（等同 --abstract full） |
| `--db pubmed --abstract none` | ✅ 合法 | 仅标题+元数据（默认，最省 token） |
| `--db pubmed --abstract full` | ✅ 合法 | 完整摘要 + DOI + MeSH |
| `--db pubmed --sort pub_date` | ✅ 合法 | PubMed 按日期排序 |
| `--db gene --organism human` | ✅ 合法 | Gene 限定物种 |
| `--db snp --years 5` | ❌ 无效 | `--years` 仅适用于 PubMed |
| `--db protein --organism human` | ❌ 无效 | `--organism` 仅适用于 Gene |
| `--db gene --full-abstract` | ❌ 无效 | `--full-abstract` 仅适用于 PubMed |

## 8. 批量处理

### 8.1 批量获取文献详情

`pubmed_fetch.py` 通过 PMID 列表批量获取，自动分批处理（每批 200 个），大量 PMID 不会导致请求失败：

```bash
# 通过 PMID 列表获取
python scripts/pubmed_fetch.py 33597265 34239348 35022842 --abstract full

# 从文件读取大量 PMID（自动分批处理）
python scripts/pubmed_fetch.py -f pmids.txt --format summary --abstract full -o results.txt

# 获取完整摘要并保存
python scripts/pubmed_fetch.py 33597265 -f pmids.txt --abstract full -o full_results.txt
```

### 8.2 多次查询结果合并

```bash
# 分步查询不同数据库
python scripts/ncbi_search.py "APOE" --db gene --format json -o gene_result.json
python scripts/ncbi_search.py "APOE" --db pubmed --max 5 --abstract full --format json -o pubmed_result.json

# 使用 pubmed_search.py 获取详细信息
python scripts/pubmed_search.py "APOE gene Alzheimer" --max 10 --abstract full -o detailed_results.txt
```

## 9. 特殊查询

- **批量 rsID**：`python scripts/ncbi_search.py "rs429358, rs7412" --db snp` → `429358[UID] OR 7412[UID]`（自动去重；仅当查询由 rsID 与分隔符组成时转换）。
- **中文术语**：约 80 个常见生物医学中文词自动英译（阿尔茨海默病→Alzheimer disease、综述→review 等）；词表外中文保留原样并提示翻译。
- **MeSH 校验**：`--mesh` 会先查 `db=mesh` 确认词存在，无效词打印警告后继续检索。
- **年份区间**：`--min-year 2020 --max-year 2023` → `2020:2023[PDat]`；与 `--years` 同时给出时以区间为准。
- **翻页**：`--max 10 --offset 10` 取第 11–20 条（基于 ESearch retstart）。

## 10. 数据导出格式

| 格式 | 适用场景 | 命令 |
|------|---------|------|
| **summary**（默认） | 人类阅读 | `--format summary` |
| **JSON** | 程序处理 | `--format json` |
| **保存到文件** | 持久化 | `-o filename.txt` |
