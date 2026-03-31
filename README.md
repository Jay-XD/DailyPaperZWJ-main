# DailyPaperZWJ

![GitHub Pages](https://img.shields.io/badge/GitHub-Pages-brightgreen)
![Python](https://img.shields.io/badge/Python-3.10-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

DailyPaperZWJ 是一个面向 RL+通信主线、兼顾 LLM/多模态/神经网络更新的论文雷达。项目会抓取论文、重建结构化标签与 venue 信息，并生成可部署到 GitHub Pages 的静态网站。

## 功能概览

- 自动抓取和增量整理论文数据
- 支持 `ArXiv + Crossref + DBLP + OpenReview` 多源抓取
- 按 venue、topic、method、scenario、发表状态进行结构化标注
- 生成 `docs/` 静态网站，支持筛选、搜索和 BibTeX 导出
- 支持 GitHub Pages 托管，网页与本地 Python 进程解耦

## 运行环境

项目默认使用 Conda 管理环境，环境定义见 [`environment.yml`](environment.yml)。

### 创建环境

```bash
conda env create -f environment.yml
conda activate dailypaper
```

### 验证依赖

```bash
python -c "import yaml, arxiv, requests"
```

### 常用命令

```bash
# 抓取论文
python scripts/fetch_papers.py

# 重建已有数据的结构化标签和 venue
python scripts/reindex_papers.py

# 生成静态网页
python scripts/generate_html.py

# 运行测试
python -m unittest discover -s tests -v
```

### OpenReview 认证

`OpenReview` 当前匿名 REST 查询不稳定。项目会先尝试匿名 `GET /notes`，如果被拒绝，再自动使用以下环境变量认证：

```bash
export OPENREVIEW_ACCESS_TOKEN="<your-openreview-token>"
# 或者
export OPENREVIEW_USERNAME="<your-openreview-email>"
export OPENREVIEW_PASSWORD="<your-openreview-password>"
```

建议优先使用 `OPENREVIEW_ACCESS_TOKEN`。如果不配置这些变量，主抓取流程仍可继续执行，但 `ICLR / ICML / NeurIPS` 的 OpenReview metadata 可能被跳过。

### 一键脚本

Linux/macOS 可直接运行：

```bash
./quickstart.sh
```

脚本会：

- 检查 Conda 是否可用
- 创建或复用 `dailypaper` 环境
- 验证核心依赖
- 运行测试
- 重建数据
- 生成静态站点

## 网页如何使用

### 本地预览

生成 `docs/` 后，用静态文件服务器预览：

```bash
conda run -n dailypaper python -m http.server 8000 --directory docs
```

然后访问 `http://127.0.0.1:8000`。

### 正式使用

正式访问方式是把 `docs/` 发布到 GitHub Pages。发布完成后，网页访问不依赖本地项目是否还在运行。

这意味着：

- 本地 Python 进程关闭后，GitHub Pages 上的网页仍然可访问
- 网页内容是最近一次生成并发布后的静态快照
- 本地重新抓取或重建后，需要再次发布，线上页面才会更新

### 关于直接双击 `docs/index.html`

这不是正式支持方式。当前前端会在浏览器里请求 `docs/data/*.json`，很多浏览器在 `file://` 场景下会拦截这类请求或行为不一致，因此不保证直接双击本地 HTML 可以正常工作。

## 项目结构

```text
DailyPaperZWJ/
├── .github/workflows/update-papers.yml
├── environment.yml
├── config.yaml
├── data/papers.json
├── docs/
├── scripts/
│   ├── fetch_papers.py
│   ├── reindex_papers.py
│   ├── generate_html.py
│   └── paper_processing.py
├── tests/
└── README.md
```

## GitHub Pages 部署

仓库已提供 GitHub Actions 工作流 [`update-papers.yml`](.github/workflows/update-papers.yml)，会在 GitHub Actions 中：

- 依据 `environment.yml` 创建 Conda 环境
- 抓取论文
- 重建结构化数据
- 生成静态网页
- 发布 `docs/` 到 `gh-pages`
- 每天 `09:00` 按计划自动更新一次，也支持手动触发

如果你希望 workflow 也稳定抓取 OpenReview，请在仓库 `Settings > Secrets and variables > Actions` 中配置以下 secret 之一：

- `OPENREVIEW_ACCESS_TOKEN`
- `OPENREVIEW_USERNAME` + `OPENREVIEW_PASSWORD`

详细步骤见 [`DEPLOYMENT.md`](DEPLOYMENT.md)。

## 使用差异

### GitHub Pages 模式

- 访问稳定
- 不需要本地环境持续运行
- 内容只在下一次生成并发布后更新

### 本地预览模式

- 可以立刻看到最新生成结果
- 需要本地 Conda 环境和静态文件服务器

### 直接打开本地 HTML

- 不作为支持模式
- 因 `fetch` 读取 JSON 的浏览器限制，兼容性不可靠

## 许可证

MIT License
