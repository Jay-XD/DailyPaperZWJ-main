# Project Snapshot

更新时间：`2026-03-31`

## 项目定位

`DailyPaperZWJ` 是一个面向 `RL + 通信` 主线、兼顾 `LLM / 多模态 / 神经网络` 更新的论文雷达项目。

项目做三件事：

1. 抓取论文元数据
2. 统一做 venue / 标签 /兴趣轨 / 文献类型归一化
3. 生成静态网页并发布到 GitHub Pages

## 当前运行模型

- 环境管理：`Conda`
- 主要环境名：`dailypaper`
- 生成物目录：`docs/`
- 正式访问模式：`GitHub Pages`
- 本地预览模式：静态文件服务器访问 `docs/`
- 不支持的正式使用方式：直接双击 `docs/index.html`

## 当前核心数据链路

### 数据源

- `ArXiv`
  - 负责 preprint 和早期版本补充
- `Crossref`
  - 负责正式期刊 metadata
- `DBLP`
  - 负责正式会议 metadata
- `OpenReview`
  - 已接入 adapter
  - 当前实现是 `匿名 GET /notes` 优先，失败后自动回退到 `token` 或 `username/password` 认证

### 当前多源抓取结论

本地最近一次 live fetch 后的数据快照：

- 总论文数：`13151`
- `arxiv`: `8932`
- `dblp`: `2107`
- `crossref`: `2112`
- `openreview`: `0`
  - 当前这份 live fetch 快照仍为 `0`
  - 原因不是 adapter 缺失，而是 `2026-03-31` 实测匿名 REST 返回 `403`，且当时未配置认证

### 当前重点 venue 抓取情况

最近一次站点索引里的部分 Venue 计数：

- `NeurIPS`: `610`
- `IoTJ`: `393`
- `ICLR`: `393`
- `WCNC`: `364`
- `Globecom`: `359`
- `INFOCOM`: `346`
- `AAAI`: `339`
- `ICML`: `312`
- `TMC`: `302`
- `TWC`: `298`
- `TVT`: `329`
- `WCL`: `264`
- `JSAC`: `252`
- `TCOM`: `283`

## 当前前端筛选能力

已支持：

- 月份
- 兴趣轨
- 发表状态
- 文献类型
- Venue
- Venue 层级
- Topic
- Method
- Scenario
- 排序
- 搜索
- BibTeX 导出

其中新增且比较关键的两个维度：

- `文献类型`
  - `conference | journal | review | other`
- `Venue`
  - 优先展示 registry 中的重点 venue，例如 `JSAC/TWC/TMC/IoTJ/INFOCOM/NeurIPS/ICLR`

## 当前 schema 重点字段

当前 `Paper` 记录中，重点看这些字段：

- `source_provider`
- `doi`
- `venue_name`
- `venue_acronym`
- `venue_type`
- `publication_status`
- `venue_tier`
- `paper_type`
- `topic_tags`
- `method_tags`
- `scenario_tags`
- `interest_track`
- `relevance_score`
- `venue_filter_value`
- `venue_filter_label`

兼容字段仍保留：

- `conference`
- `tags`
- `venue_type`

## 常用命令

```bash
conda activate dailypaper
python scripts/fetch_papers.py
python scripts/reindex_papers.py
python scripts/generate_html.py
python -m unittest discover -s tests -v
```

本地预览：

```bash
conda run -n dailypaper python -m http.server 8000 --directory docs
```

## 当前已知限制

- `OpenReview` 在 `2026-03-31` 实测匿名 REST 查询返回 `403`。
- 现已补成“匿名尝试 + 认证回退”模式，但要真正产出 `ICLR/ICML/NeurIPS` 数据，仍需要配置 `OPENREVIEW_ACCESS_TOKEN` 或 `OPENREVIEW_USERNAME/OPENREVIEW_PASSWORD`。
- `IEEE Xplore` 没有接入主流程。
- 当前不做校园账号、SSO、VPN、cookie 自动登录。
- 当前不抓受限全文，只抓 metadata 和公开链接。
- `review` 仍是关键词规则，不是 publisher article-type 精确标注。

## 当前部署状态

- GitHub Actions 已配置 Conda 环境和 Pages 发布链路
- 当前 workflow 支持：
  - 每天自动更新一次
  - 手动触发
- Pages 使用 `gh-pages` 分支
