# AGENTS.md — NCBI Search 代理指令

本文件是编码代理的仓库级入口：声明项目结构、运行方式、变更边界与验证要求。
领域知识、参数详解与示例请查阅 [README.md](README.md) 与 [SKILL.md](SKILL.md)，本文件不重复其内容。

## 项目结构

- `scripts/ncbi_search.py` — 主检索入口：智能意图识别，自动路由到 PubMed、Gene、Protein、dbSNP、ClinVar 等 10+ 数据库，支持分级摘要显示
- `scripts/pubmed_search.py` — PubMed 专用检索：自然语言转换、MeSH 筛选、排序与分级摘要
- `scripts/pubmed_fetch.py` — 按 PMID 批量获取文献元数据与摘要
- `scripts/pmc_fetch.py` — PubMed Central 全文获取：EFetch + JATS XML 解析，支持 PMID 自动转 PMCID
- `scripts/ncbi_utils.py` — 共享工具：SQLite 缓存、NCBI 限流、Windows 编码处理（不可被脚本私有复制）
- `scripts/test_ncbi.py` — 验证套件（unittest，覆盖意图路由、缓存、PMC 解析等）
- `.ncbi_cache/` — 运行时生成的 SQLite 缓存目录，不入库

## 运行方式

依赖仅需 `requests`（缺失时脚本会提示安装）。API Key 通过环境变量 `NCBI_API_KEY` 或各脚本 `--api-key` 传入。

```bash
# 主检索入口（自动检测数据库）
python scripts/ncbi_search.py "阿尔茨海默病" --max 10

# PubMed 专用检索
python scripts/pubmed_search.py "crispr" --years 5 --sort relevance --abstract preview

# 按 PMID 获取
python scripts/pubmed_fetch.py 12345678 87654321 --format json

# PMC 全文获取（PMCID 或 PMID+--pmid）
python scripts/pmc_fetch.py PMC8241728 --outline
python scripts/pmc_fetch.py 12345678 --pmid --max-chars 5000

# 运行验证套件
python scripts/test_ncbi.py
python -m unittest scripts.test_ncbi
```

环境变量：`NCBI_NO_CACHE=1` 绕过缓存；`NCBI_CACHE_EXPIRE_HOURS` 设置缓存过期（默认 24）。

## 变更边界

- `scripts/` 为受影响核心目录；修改任一脚本职责前先阅读该文件与其调用方
- 共享逻辑（缓存/限流/编码）必须放 `ncbi_utils.py`，不得在脚本内复制
- 新脚本加入 `scripts/` 需纳入版本控制，并同步 README/SKILL.md 的相关描述
- `.ncbi_cache/`、`__pycache__/` 等生成物不得提交
- 运行时网络行为（API 调用）属外部效果，变更前确认不破坏限流与缓存约定

## 验证要求

- 任何 `scripts/` 变更必须运行 `python scripts/test_ncbi.py`，保留通过/失败输出
- 新增或修改 CLI 参数时，用 `--help` 验证命令面可用
- 变更涉及缓存/限流逻辑时，在 `NCBI_NO_CACHE=1` 与默认缓存两种模式下各验证一次
- 交付前确认变更已进入版本控制（无 untracked 源码文件），并声明测试结果
