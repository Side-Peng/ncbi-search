# 更新日志

> 版本历史存档。了解功能演进时查阅，运行时无需读取。

## v3 (2026-07-29)

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

## v3.1 (2026-08-31) — 文档重构

- ✅ **SKILL.md 瘦身**: 从 ~700 行精简到 ~300 行，参数表/查询语法/结果解析/更新日志拆分到 `references/`（渐进披露，降低每次触发的 token 开销）
- ✅ **frontmatter 规范化**: 移除 ZCode 不识别的 `allowed-tools`/`trigger-keywords`，新增 `when_to_use`，触发语句前置（ZCode 展示 description 时只取前 ~250 字符）
- ✅ **路径约定**: 明确脚本路径相对于技能安装目录而非当前工作目录
