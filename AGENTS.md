# AGENTS.md — ncbi-search

面向 AI agent 的仓库指令入口。改动前先读本文件。

## 项目结构

- `scripts/ncbi_search.py` — 多库检索入口（10+ NCBI 库自动路由；PubMed Tier1 用 ESummary，preview/full 用 EFetch；Gene 库用 `[Gene Name]` + 学名映射）
- `scripts/pubmed_search.py` — PubMed 专用入口（自然语言 → 检索式；作者线索词门控、小写布尔映射、连字符/引号短语保留）
- `scripts/pubmed_fetch.py` — 按 PMID 批量获取（每批 200，自动去重）
- `scripts/pmc_fetch.py` — PMC 开放获取全文（JATS 解析；ELink 批量 PMID→PMCID；默认截断 6000 字符）
- `scripts/ncbi_utils.py` — 共享层：HTTP（重试/限速/缓存/错误体检测/工具标识）、按句摘要截断、PubMed XML 解析
- `scripts/test_ncbi.py` — 离线单元测试（27 项）
- `references/` — 参数、检索式、结果字段文档
- `dist/` — 打包目录；发布前必须与 `scripts/`、`SKILL.md` 同步

## 运行

- 依赖：Python 3.7+，仅 `requests`。
- 环境变量（均可选）：`NCBI_API_KEY`（10 req/s，无 Key 为 3 req/s）、`NCBI_EMAIL`（合规标识）、`NCBI_NO_CACHE=1`（禁用缓存）、`NCBI_CACHE_EXPIRE_HOURS`（默认 24）、`NCBI_CACHE_MAX_ROWS`（默认 5000）。

## 测试与验收

```bash
python -m unittest scripts/test_ncbi.py -v
```

任何修改后必须：
1. `python -m py_compile scripts/*.py` 通过；
2. 全部单测通过（27 项）；
3. 同步 `dist/` 与已安装技能目录 `C:\Users\13049\.agents\skills\ncbi-search`（三处 SHA256 一致）；
4. 输出格式改动需在真实 API 上抽查至少 1 条（缓存可命中，注意限速）。

## 变更边界

- 输出直达 AI agent 上下文，token 成本敏感：新增字段前确认 `--abstract` 分级与 JSON 裁剪逻辑（`trim_json_*`）。
- 检索式转换规则（作者线索词、布尔词、连字符、MeSH 表）有回归测试保护，改动需同步 `scripts/test_ncbi.py`。
- 默认值（`--abstract none`、pmc `--max-chars 6000`）与 SKILL.md / references / README 保持一致。
- 修改后若未同步 `dist/`，发布版本与源码分叉。
