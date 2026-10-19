# NCBI Search 插件优化方案

> 目标：极致检索效率 · 极致省 token · 极致准确性
> 方法：三个子代理并行审计（E-Utilities API 层 / token 消耗 / 检索式 23 组实测 + 15 组人工 esearch 对照），主模型通读全部源码并独立实测复核。所有结论均已交叉验证。
> 日期：2026-10-17 ｜ 状态：P0–P4 已实施（2026-10-17）

---

## 实施记录（P4，2026-10-17）

- **批量 rsID**：`--db snp` 接受逗号/空格分隔的多个 rsID → `id1[UID] OR id2[UID]`（去重；仅当查询由 rsID 与分隔符组成时转换）。实测 `rs429358, rs7412` → 2 条精确记录。
- **年份区间**：`--min-year/--max-year` → `2020:2023[PDat]`，优先于 `--years`；两脚本一致。
- **翻页**：`--offset N` → ESearch `retstart`（不用 usehistory，避免 WebEnv 过期）；两个搜索脚本均支持，JSON 带 offset。
- **中文自动英译**：`ncbi_utils.CHINESE_TERMS`（~80 词）+ `translate_chinese()`；两个入口均先翻译再解析；词表外中文保留并提示。
- **MeSH 校验**：`--mesh` 先查 `db=mesh`，无效词打印警告（不阻塞检索）。
- **测试**：新增 3 项 helper 测试（snp UID、date_filter、CSV），共 29 项全部通过。
- **文档**：SKILL.md / parameters.md / README 同步新参数、批量 rsID、翻页说明。
- **后续调整（按用户决定）**：中文自动英译（`CHINESE_TERMS`）已移除——中文查询改为提示 agent 直接翻译；MeSH 默认不强制标注（交给 ATM）；新增跨进程共享限速、CSV 导出、PMC license 解析。

---

## 实施记录（P3，2026-10-17）

- **非 PubMed 库结果增强**：ClinVar（VCV/变异名/临床意义+审核状态/位置/疾病）、SRA（Experiment/Study/物种/策略/spots/日期）、Assembly（accession/名称/物种/级别/reference 类别/日期）、BioSample（accession/标题/物种/提交机构/日期）、Taxonomy（taxid/学名+常用名/等级/分类组）、dbSNP（rsID/基因/chrpos/MAF 3 位小数/临床意义/merged 标记）。
- **dbSNP 精确查询**：纯 `rsXXXX` 查询改用 `{digits}[UID]`（原先会连带返回 merged 旧记录：rs429358 返回 3 条 → 1 条）。
- **PMC `--sections`**：按标题子串只取指定章节（支持嵌套子节），配合 `--max-chars` 进一步压 token。
- **JSON 修复**：`trim_json_record` 不再丢掉非 PubMed 记录的 ID（`_id` → `id`）。
- **测试**：新增 7 项（formatter × 5、sections 过滤、JSON id），共 24 项全部通过。
- **文档**：SKILL.md / parameters.md / result_format.md / README 同步新参数与新输出格式。

---

## 实施记录（P1/P2，2026-10-17）

- **G1 Gene 库字段修复**：裸基因符号改用 `[Gene Name]`（`APOE` 从 1,401 条文本噪音 → 精确基因记录），`--organism` 支持 common name → 学名映射（human→Homo sapiens 等），0 命中自动回退全文搜索。
- **G2 重试/超时**：`Retry(total=4, backoff_factor=0.5, respect_retry_after_header=True, allowed_methods=GET)`；timeout 拆为 `(10, read)`。
- **G3 缓存并发**：SQLite `timeout=10` + `PRAGMA journal_mode=WAL` + `busy_timeout`；新增 `NCBI_CACHE_MAX_ROWS`（默认 5000）容量上限。
- **G5 转换层测试**：P0 已补 10 项（本轮随 P0 完成，共 17 项）。
- **G6 无结果诊断**：中文→英文提示、`--mesh` 无效词提示。
- **G7 relevance+日期文档**：query_syntax.md 注明"窗口内重排"，建议配 `--sort pub_date`。
- **G9 XML 解析去重**：`parse_pubmed_xml` 移入 `ncbi_utils` 单一实现（两侧副本已分叉，现统一）。
- **P2**：`--count-only`（两个搜索脚本）、pubmed_fetch PMID 去重 + 非数字提示、pmc 输入去重、`PMC` 前缀剥离修正、query_syntax.md 示例全部同步为真实输出、新增 `AGENTS.md`（仓库指令入口/测试命令/变更边界）。

---

## 实施记录（P0，2026-10-17）

已全部落地并验证：
- **准确性 A1–A10**：作者线索词门控、小写布尔保留、类型词边界、连字符/引号短语、解剖词不标 MeSH、停用词扩充、年份→`[PDat]`、0 结果提示、路由重写（`rs` 关键词移除、泛基因正则收紧、文献词优先）。
- **Token T1–T7**：JSON 按 tier 裁剪（`separators` 紧凑）、pmc 默认 6000 字符 + preview、默认 `--abstract none`、按句截断 400 字符（CONCLUSIONS→RESULTS 优先）、记录精简（去 URL/装饰线/MeSH·DOI 分层、作者 3 人、单行头）、错误短格式、SKILL/parameters/README 同步。
- **效率 E1–E5**：ELink 按 200 批量、NCBI 错误体检测（不写缓存）、Tier1 改 ESummary v2.0、ESummary 分批、tool/email、api_key 脱敏、`--max`/`--batch-size` 钳制、sort 仅 PubMed、ESearch ERROR 处理。
- **验证**：17/17 单测通过（新增 10 个转换层回归用例）；在线实测 `vitamin D deficiency` 44,191（修复前 3）、`alzheimer or parkinson` OR 生效、`blood pressure`→PubMed、`brain tumor treatment` 148,464（修复前 39,754）、Tier1 ESummary / JSON / PMC 截断 / ELink --pmid 均正常；`dist/` 与已安装 skill 哈希一致（0 diff）。

---

## 0. 结论速览

| 维度 | 核心问题 | 预期收益 |
|------|---------|---------|
| 准确性 | 自然语言→检索式转换层存在 9 类致命缺陷，常见查询召回损失 78%–99.99%（如 "Vitamin D deficiency" 从 44,183 掉到 3 条）；多库路由 8/9 常见文献查询被误路由到 Gene/dbSNP/Nucleotide | 修复后所有高频查询恢复到正确召回 |
| 省 token | JSON 输出无视 `--abstract` 分级（20 条 none+json 实际 10,700 token）；pmc_fetch 默认全量正文倾泻（单次 8,000–15,000 token）；默认 preview 1000 字符硬切 | 典型三步工作流 **-43%**；最坏场景 **-84%～-87%**；pmc 单篇 **-75%～-85%** |
| 效率/健壮 | PMID→PMCID 逐条 ELink（100 个 PMID = 100 次请求 ≈33 秒）；Tier1 仍下载 EFetch 全量 XML；NCBI 错误响应被静默吞掉并缓存 24 小时 | ELink 提速 ~100 倍；Tier1 带宽 -80%～-90% |

**已确认无需改动**（审计通过项）：速率限制数值（3/s、10/s）、Session 连接池复用、gzip、EFetch 200 分批、ELink `linkname=pubmed_pmc` 选择、缓存键排除 api_key、Windows UTF-8 处理、dist/ 与已安装 skill 哈希一致。

---

## 1. P0 — 准确性（致命缺陷，修复即可恢复 78%–99.99% 的召回）

### A1. 作者正则误报（最严重）
- 位置：`scripts/pubmed_search.py:248-250`
- 现状：`\b([A-Z][a-z]+)\s+([A-Z](?:\s|$|,))` 把 "Vitamin D"、"Hepatitis B"、"Influenza A" 当作者。
- 实测：`"Vitamin D deficiency"` → `(Vitamin deficiency) AND Vitamin D[Author]` → **3 条**（人工对照 44,183 条，**召回损失 99.99%**）。
- 改法：仅当查询含 `author`/`by`/`written by`/`et al` 线索词时才启用作者解析；解析后把姓氏与线索词从关键词组中剔除（当前 `(Smith author)` 残留，`Smith J author Alzheimer` 25 条 vs 应得 291 条）。

### A2. 小写布尔词被吞 → OR 变 AND
- 位置：`scripts/pubmed_search.py:118-129`（STOP_WORDS 含 and/or/not）、`:278`（透传检测只认大写）
- 实测：`"alzheimer or parkinson"` → AND 连接 → 5,452 条（人工 OR 式 236,342 条，**语义反转**）。
- 改法：识别独立小写 `or/and/not` 映射为 `OR/AND/NOT`；透传检测不区分大小写。

### A3. 文章类型子串匹配
- 位置：`scripts/pubmed_search.py:232-245`
- 实测：`"industrial chemical exposure"` 中 indus**"trial"** 触发 `Clinical Trial[pt]` → 170 条（人工 31,561 条）。
- 改法：`\b` 词边界匹配；`--type` 值大小写归一化（当前 `--type Review` 静默失效）。

### A4. 连字符词拆坏 + 单字母词丢弃
- 位置：`scripts/pubmed_search.py:190,215`
- 实测：`"IL-6 inflammation"` → `(IL inflammation)` → 189,313 条且语义漂移到全部白介素；`p-tau217` 丢 "p"；`"B cell lymphoma"` → `(cell lymphoma)` 丢 "B"。
- 改法：分词正则允许连字符（整体保留 `IL-6`/`p-tau217`/`COVID-19`）；单字母词元不因长度丢弃（作为短语一部分透传）。

### A5. 引号/连字符短语被拆散后逐词标 MeSH
- 位置：`scripts/pubmed_search.py:52-100,287-289,315-319`
- 实测：`"blood-brain barrier" disruption` → `"Blood"[MeSH] AND "Brain"[MeSH] AND (barrier disruption)` → 426 条（人工 11,617 条，**-96%**）。
- 改法：检测到引号/连字符短语时整体原样透传，不逐词加 `[MeSH]`。

### A6. 解剖学单词误标 MeSH + 树爆炸
- 位置：`scripts/pubmed_search.py:76-81`（brain/heart/blood/liver/kidney 单字标 `[MeSH]`）
- 实测：`"brain tumor treatment"` 39,754 vs 183,787（-78%）；`"heart failure beta blockers"` 1,507 vs 13,262（-89%）。
- 改法：解剖词不单字标 `[MeSH]`（交还 PubMed ATM 自动映射），或改用 `[MeSH:noexp]` 防树爆炸。

### A7. 停用词/线索词缺漏
- 位置：`scripts/pubmed_search.py:118-129`
- 实测：`"Alzheimer last 5 years"` → `AND (last years)` → 279 条（应 93,445，**-99.7%**）；`"APOE gene"` 多出 `AND (gene)` 噪声。
- 改法：扩充 `last/years/author/gene/paper/article/study/studies` 等；`last N years` 模式命中后移除对应词。

### A8. 年份检测是死代码
- 位置：`scripts/pubmed_search.py:222-224`（`elements["year"]` 从不被使用）
- 实测：`"cancer 2020"` → `(2020)` 当全文词 → 213,321 条。
- 改法：4 位年份映射为 `YYYY[PDat]`。

### A9. 中文/非 ASCII 查询 0 结果无提示
- 位置：`scripts/pubmed_search.py:190,617-625`
- 实测：`"阿尔茨海默病 综述"` → 0 条且只打印空表头（英文等价 64,437 条）；SKILL.md 6.1 声称的"友好提示"不存在。
- 改法：0 结果时输出"请译为英文 + 放宽过滤"建议；检测到中文时直接提示。

### A10. 多库路由重写（ncbi_search.py）
- 位置：`scripts/ncbi_search.py:94,193-246`
- 实测（主模型独立复核 8/9 误判）：
  - `"blood pressure"`→Gene、`"cancer treatment"`→Gene、`"cell cycle"`→Gene、`"insulin resistance"`→Gene（原因：泛基因正则 `^[A-Z][A-Z0-9-]{3,7}$` 匹配任意 4–8 位词）；
  - `"human genome project"`→Nucleotide；`"DNA repair review"`→Nucleotide（文献关键词不参与 db 打分）；
  - `"rs"` 裸关键词 + 子串匹配使任何含 "rs" 的词（years/first/course）误入 dbSNP。
- 改法：
  1. 删除裸 `"rs"` 关键词（`\brs\d+\b` 已覆盖 rsID），短关键词改词边界匹配；
  2. 潜在基因只认 ① 已知符号白名单 ② 含数字的混合串（BRCA1/SHANK3/P53），纯字母 4–8 位词不再视为基因；
  3. 文献关键词优先于数据库关键词打分。

---

## 2. P0 — 省 token（默认路径与隐性陷阱）

### T1. JSON 输出无视 `--abstract` 分级（最大隐性 bug）
- 位置：`scripts/ncbi_search.py:764-770`、`pubmed_search.py:605-614`、`pubmed_fetch.py:88`、`pmc_fetch.py:358-367`
- 现状：records 全量 dump——abstract 全文、MeSH 全列表、作者全列表内嵌；`--abstract none` 完全不生效；pubmed_fetch 默认格式就是 json；indent=2 额外 +15-20% 空白。
- 实测估算：`--abstract none --format json --max 20` 预期 ~1,300 token，实际 **~10,700 token**。
- 改法：格式化前按 tier 裁剪字段（none 省略 abstract，preview 截 400 字符，MeSH 截 5、作者截 3）；pubmed_fetch 默认格式改 summary；JSON 用 `separators=(",",":")`；pmc JSON 正文去重（content blocks 与 full_text 二选一）。

### T2. pmc_fetch 默认全量正文倾泻
- 位置：`scripts/pmc_fetch.py:451-453`（`--max-chars 0`=无限、`--abstract full`）、`SKILL.md:138` 首例裸调用
- 现状：单篇 OA 文章 ≈ 8,000–15,000 token/次。
- 改法：`--max-chars` 默认 6000（显式 0 才无限）；`--abstract` 默认 preview；SKILL 首例改 `--outline`。截断提示可续取，精度无损。

### T3. 搜索脚本默认 `--abstract preview`（1000 字符）与省 token 指引矛盾
- 位置：`scripts/ncbi_search.py:152,159`、`pubmed_search.py:132,139`
- 现状：默认 `--max 10` 一次调用 ≈ 3,170 token（其中 2,500 是摘要）；agent 忘传 `--abstract none` 即踩坑。
- 改法：默认改 `none`；SKILL 明示"给出最终答案前必须对入选文献取 full"。

### T4. preview 前 1000 字符句中硬切 → 按句截断 + 结论优先
- 位置：`scripts/ncbi_search.py:553`、`pubmed_search.py:658`
- 现状：结构化摘要（BACKGROUND/METHODS/RESULTS/CONCLUSIONS）硬切后恰好丢掉对筛选最关键的 CONCLUSIONS。
- 改法：按句截断 ≤400 字符，Label 存在时按 CONCLUSIONS→RESULTS→其余 优先级拼接；去掉 "BACKGROUND:" 等标签。省一半摘要 token 且提升筛选质量。

### T5. 每条记录精简
- 位置：`scripts/ncbi_search.py:508-564`、`pubmed_search.py:618-662`、`pmc_fetch.py:374-423`
- 现状：每条 ~65 token，其中 ~28 冗余。
- 改法：summary 模式删 URL 行（JSON 保留，URL 可由 PMID+模板推导）；MeSH/DOI 仅 `--abstract full` 层打印；作者 5 人→3 人 + "et al."；3×70"=" 装饰头 → 单行紧凑头 `# PubMed | query | total N | shown M`；70"-" 分隔线 → 空行；dbSNP 删重复的 `Reference SNP` 行。

### T6. 错误/帮助输出瘦身
- 位置：`scripts/ncbi_search.py:789`、`pubmed_search.py:749`、`pubmed_fetch.py:145`、`pmc_fetch.py:530`（HTTPError 回显完整 URL 含 api_key ≈ 50-70 token）；各 `--help` epilog ≈ 230 token
- 改法：错误改 `HTTP {code} {reason}` 短格式（顺带解决 F-10 api_key 泄漏）；epilog 精简到 2 行；进度行（`pubmed_fetch.py:120`、`pmc_fetch.py:485,511`）门控到 `-v`。

### T7. SKILL.md 精简与指引修正
- 现状：本体 ≈ 4,000 token/次加载（每次会话一次）；§2 与决策树重复、§6/§8 agent 基本不用。
- 改法：精简到 ~2,300 token；Tier1 字段表改为"标题/作者/期刊/年份"（与省 token 目标一致）；步骤3 示例补 `--format summary`；全部示例同步新默认值。

---

## 3. P0 — 检索效率与健壮性

### E1. PMID→PMCID 逐条 ELink → 批量化
- 位置：`scripts/pmc_fetch.py:96-140`
- 现状：100 个 PMID = 100 次请求（无 Key 限速下 ≥33 秒）。
- 改法：按 200 分批，单请求 `id=1,2,3...`，`linksets[].ids[]` 与 `linksetdbs[].links[]` 按位置对应。**速度 ~100 倍**。

### E2. NCBI 错误响应（HTTP 200 + ERROR XML）被静默吞掉并缓存 24 小时
- 位置：`scripts/ncbi_utils.py:206-214`、`scripts/ncbi_search.py:366-374`、`scripts/pmc_fetch.py:230-234`
- 现状：EFetch 对无效 ID 返回 HTTP 200 + 错误 XML → 解析 0 条 → 只显示 "Total: 0" 无原因，且错误 XML 被写入缓存。
- 改法：`http_get` 中心化检测 `<error`（或 `esearchresult.ERROR`）→ 抛异常、**不写缓存**。

### E3. Tier1（`--abstract none`）仍下载 EFetch 全量 XML → 改用 ESummary v2.0
- 位置：`scripts/ncbi_search.py:758-761`、`fetch_summary` 缺 `version=2.0`
- 现状：Tier1 下载完整 MedlineCitation XML（含 MeSH/资助/化学物质，5–15 KB/条）。
- 改法：`none → ESummary(version=2.0)`（~1 KB/条，含标题/期刊/pubdate/作者/DOI）；`preview/full → EFetch`。**带宽 -80%～-90%**。

### E4. fetch_summary 不按 200 分批
- 位置：`scripts/ncbi_search.py:291-321`
- 现状：`--max > 200` 时非 PubMed 库直接触发 NCBI 错误（PubMed 路径已正确分批）。
- 改法：循环 200/批。

### E5. 合规与安全（低改动高价值）
- 所有请求加 `tool="ncbi-search"`，`email` 读 `NCBI_EMAIL` 环境变量（防无预警限流/封 IP）；
- 异常输出剔除 `api_key` 参数（当前 ConnectionError/HTTPError 回显完整 URL）；
- `--max` 钳制 1–200、`--batch-size` 钳制 1–200（当前可传 0 触发除零崩溃）；
- `sort` 参数仅对 PubMed 发送（其他库可能报错）；
- ESearch 响应含 `ERROR` 字段时抛异常而非显示 "Total: 0"。

---

## 4. P1 — 中等优先级

| # | 项 | 位置 | 说明 |
|---|----|------|------|
| G1 | Gene 库检索加 `[Gene Name]` 字段 + organism 学名映射 | `ncbi_search.py:262-266,569-597` | 主模型实测：裸 `APOE` 命中 1401 条文本噪音；`APOE[Gene Name] AND Homo sapiens[Organism]` 精确 1 条；`--organism human` 需映射为 "Homo sapiens"。已知符号白名单命中时用 `[Gene Name]`，0 命中回退全文搜索 |
| G2 | 重试/超时强化 | `ncbi_utils.py:52-60,206` | `Retry(total=4, backoff_factor=0.5, respect_retry_after_header=True)`；timeout 改 `(10, 60)` 二元组（connect/read 分离） |
| G3 | SQLite 并发健壮性 | `ncbi_utils.py:104-123` | `connect(timeout=10)` + `PRAGMA journal_mode=WAL`（并行跑多个脚本时 "database is locked"） |
| G4 | rate_limit 用 `time.monotonic()` | `ncbi_utils.py:71-78` | 墙钟 NTP 回拨时负 sleep 崩溃 |
| G5 | 转换层单元测试 | `scripts/test_ncbi.py` | A1-A9 全部漏网的根因：为 `detect_query_elements`/`build_pubmed_query` 补参数化单测（作者误报/子串类型/连字符/布尔/中文/MeSH 短语/年份） |
| G6 | 0 结果诊断增强 | `pubmed_search.py:617-625` | 输出"无效 MeSH 词警告（--mesh FooBarBaz）"、"中文→英文提示"、"放宽过滤建议" |
| G7 | relevance+日期组合文档化 | `references/query_syntax.md` | 实测：带 `--years` 时 relevance 是"窗口内重排"而非全库最相关（top5 与无日期完全不同） |
| G8 | `--type` 映射两脚本统一 | `ncbi_search.py:739-744` vs `pubmed_search.py:329-335` | ncbi_search 缺 `case_report`；共用一份映射 |
| G9 | `parse_pubmed_xml` 去重合并 | `ncbi_search.py:366-498` vs `pubmed_search.py:436-585` | 双副本已分叉（ncbi_search 缺 PubmedBookArticle 回退），提取到 `ncbi_utils` 共用 |

## 5. P2 — 打磨项（低优先级，按需做）

- 缓存容量上限/LRU（PMC 全文 XML 长期累积）；`NCBI_CACHE_EXPIRE_HOURS` 非法值 import 即崩溃 → try/except。
- `--count-only`（retmax=0 纯计数，可选功能）。
- PMID/PMCID 输入去重；文件内非纯数字行给出提示而非静默丢弃。
- `pmc_fetch.py:246` `replace("PMC","")` → 前缀剥离；`:408` preview 硬编码 1000 → 共用常量。
- `--years` 用 365×N 天近似 → 改为整年（如 `2021:2026[PDat]`），并注意显示年份（印刷年）可能超出过滤窗口的说明。
- 文档同步：`references/query_syntax.md:10-13` 四个转换示例均与实际输出不符；`parameters.md` 的 `--max 1-100`、`--sort 全部库`、`--type` 表。
- 仓库治理（qoder 审查遗留）：scripts/ 未 git 跟踪、无 AGENTS.md、测试命令未声明 → 建议 git add + 声明 `python -m unittest scripts/test_ncbi.py`。

---

## 6. 实施路线图建议

- **阶段 1（1 天）**：P0 全部——A1-A10（准确性）+ T1-T6（token）+ E1-E5（效率）。此阶段后：高频查询召回恢复、三步工作流 -43%、最坏场景 -84%+。
- **阶段 2（半天）**：P1 全部——G1-G9，含转换层单测补齐（防止回归）。
- **阶段 3（可选）**：P2 打磨 + 文档全面同步。

> 注意：任何修改需同步更新 `dist/`（打包目录）并重新安装 skill 到 harness（当前三处哈希一致，改动后必须保持一致），并跑 `python -m unittest scripts/test_ncbi.py`（当前 7/7 PASS 作为基线）。
