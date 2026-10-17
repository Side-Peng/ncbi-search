# 更新日志

> 版本历史存档。了解功能演进时查阅，运行时无需读取。

## v3.0.0 (2026-10-17) — 检索准确性与 token 效率重构

**破坏性变更（默认行为）**
- 默认摘要层级改为 `none`（仅标题+元数据）；`preview` 改为按句截断 ~400 字符（结论优先）
- 输出改为紧凑单行格式：去掉 URL 行与装饰分隔线；MeSH/DOI 仅在 `--abstract full` 输出
- JSON 结构变化：`total_count`→`total`、`_id`→`id`、去掉 `search_date`/`query_explanation`、新增分页 `offset`

**准确性修复**
- 作者解析仅在线索词（author/by）出现时触发：`Vitamin D deficiency` 3→44,191 条
- 小写布尔词映射 `OR/AND/NOT`；文章类型改词边界匹配；连字符/引号短语整体保留
- 解剖词不再强标 `[MeSH]`（`brain tumor treatment` 39,754→148,464）；年份→`[PDat]`
- 多库路由重写：移除裸 `rs` 关键词、泛基因正则收紧、文献词优先；`blood pressure` 等正确落 PubMed
- Gene 库用 `[Gene Name]` + 学名映射（`APOE` 1,401 条文本噪音→409 个真实基因；`--organism human`→1 条）
- dbSNP 纯 rsID 走 `[UID]`（排除 merged 旧记录），支持批量 rsID（`rs429358, rs7412`）

**效率与健壮性**
- PMID→PMCID 改 ELink 批量（≤200/次，约 100 倍提速）
- NCBI 错误体（HTTP 200 + ERROR XML）不写缓存；ESearch ERROR 显式报错
- Tier1 改用 ESummary v2.0（带宽 -80~90%）；ESummary 按 200 分批
- SQLite WAL + busy_timeout + 容量上限（`NCBI_CACHE_MAX_ROWS`）；重试 4 次且尊重 Retry-After
- 所有请求携带 `tool=ncbi-search`（可选 `NCBI_EMAIL`）；错误信息不再回显 api_key
- `--max`/`--batch-size` 钳制；`sort` 仅对 PubMed 发送

**新功能**
- `--count-only`（只取命中数）、`--offset`（翻页）、`--min-year/--max-year`（年份区间）
- `--sections`（PMC 只取指定章节）、中文术语自动英译（~80 词）、`--mesh` 在线校验
- 各库专用单行输出（ClinVar/SRA/Assembly/BioSample/Taxonomy/dbSNP 字段增强）

**文档与测试**
- SKILL.md 瘦身：~700 行 → ~300 行，参数表/查询语法/结果解析/更新日志拆分到 `references/`（渐进披露，降低每次触发 token 开销）
- SKILL/parameters/result_format/README/AGENTS 全面同步；新增 OPTIMIZATION_PLAN.md
- 单测 7→27 项（转换层回归、各库格式化、sections、helper）

## v2.0.2 (2026-08-02) — PMC 全文获取与 EFetch 分批

**功能增强：**
- ✅ **PMC 开放获取全文获取**: 新增 `pmc_fetch.py`，通过 EFetch(`db=pmc`) 直接下载 PubMed Central 开放获取文献的 JATS XML 并解析为分节正文
- ✅ **PMID 自动转 PMCID**: `--pmid` 选项经 ELink(`linkname=pubmed_pmc`) 将 PMID 转换为其对应 PMCID
- ✅ **Token 友好**: `--outline` 仅显示章节大纲，`--max-chars` 截断超长正文，`--abstract` 三级摘要
- ✅ **优雅降级**: 非开放获取文献标注 `Open Access Full Text: No` 并保留元数据+摘要；不在 PMC 的 PMID 提示 `Not in PMC`
- ✅ 新增 PMC 解析与 PMC ID 归一化的离线单元测试

## v2 (2026-07-08)

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
