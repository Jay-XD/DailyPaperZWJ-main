# Feature Status

更新时间：`2026-03-31`

## 已完成功能

- ✅ Conda 环境接管
  - 已有 `environment.yml`
  - 本地与 GitHub Actions 环境基本统一

- ✅ GitHub Pages 静态托管
  - `docs/` 为正式网页构建产物
  - 项目不运行时，Pages 上网页仍可访问

- ✅ 多源抓取主链路
  - `ArXiv + Crossref + DBLP + OpenReview`
  - 统一抓取入口在 `scripts/fetch_papers.py`

- ✅ 多源去重合并
  - 按 `arxiv_id`
  - 按 `doi`
  - 按 `normalized_title + first_author + year`

- ✅ Venue 归一化
  - 已有 `venue_registry`
  - 能识别 `JSAC/TWC/TMC/IoTJ/ToN/TCOM/TVT/WCL`
  - 能识别 `INFOCOM/Globecom/WCNC/ICC`
  - 能识别 `NeurIPS/ICLR/ICML/AAAI`

- ✅ 结构化标签与兴趣轨
  - `topic_tags`
  - `method_tags`
  - `scenario_tags`
  - `interest_track`
  - `relevance_score`

- ✅ 文献类型识别
  - `paper_type = conference | journal | review | other`
  - `review` 基于关键词规则识别

- ✅ 前端动态筛选
  - 已支持 `paper_type`
  - 已支持 `Venue`
  - 其余筛选仍保持动态 facet 生成

- ✅ BibTeX 导出
  - 已根据 `venue_type` 区分 `article / inproceedings`
  - 已支持 `doi`

- ✅ 测试覆盖基础主链路
  - venue 归一化
  - `paper_type`
  - adapter mock
  - 多源 merge
  - 站点元数据生成

## 部分完成 / 当前不稳定

- ⚠️ OpenReview live 数据接入
  - adapter 已切到 `GET /notes` + `invitation/directReplies`
  - 已支持 `OPENREVIEW_ACCESS_TOKEN`
  - 已支持 `OPENREVIEW_USERNAME / OPENREVIEW_PASSWORD`
  - `2026-03-31` 实测匿名 REST 仍会 `403`
  - 如果未配置认证，现状仍是自动跳过，不阻断主流程

- ⚠️ DBLP 精度仍需继续观察
  - 当前已能稳定进入主流程
  - 但 query 仍是 venue 关键词搜索，不是最严格的 venue-only 拉取

- ⚠️ `review` 识别不是 publisher 级 article-type
  - 目前是规则法
  - 可用但不是最高精度

## 当前建议视为“已稳定可用”的能力

- `Crossref` 对正式期刊的补充
- `DBLP` 对正式会议的补充
- Venue 筛选卡片
- 文献类型筛选卡片
- Conda + Pages 的运行模型

## 当前已知行为细节

- 默认首页仍以 `core_rl_comms` 为主
- A 会论文很多会落在 `secondary_llm_mm_nn`
- 没有正式 venue 的 ArXiv-only 论文仍会保留
- 有正式 DOI / venue 的记录，优先保留正式 metadata

## 重要文件入口

- 核心抓取：`scripts/fetch_papers.py`
- 外部源：`scripts/source_adapters.py`
- 结构化处理：`scripts/paper_processing.py`
- 站点生成：`scripts/generate_html.py`
- 前端筛选：`docs/js/main.js`
- 测试：`tests/test_processing.py`
