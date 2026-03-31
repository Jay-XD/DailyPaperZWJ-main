# GitHub Pages Deployment

## 目标

这个项目的正式网页形态是 GitHub Pages 上的静态站点。

本地项目负责：

- 抓取论文
- 重建结构化数据
- 生成 `docs/` 静态站点

GitHub Pages 负责：

- 对外托管 `docs/`
- 在本地项目和 Python 进程关闭后继续提供网页访问

因此，只要最新的 `docs/` 已经发布到 GitHub Pages，网页就不依赖本地项目是否仍在运行。

## 1. 创建并推送仓库

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

## 2. 配置 GitHub Pages

1. 进入仓库 `Settings`
2. 打开 `Pages`
3. 当前先不要急着选 `main`
4. 先到 `Actions` 手动运行一次 `Update Papers Daily`
5. 等 workflow 成功后，它会按 [`.github/workflows/update-papers.yml`](.github/workflows/update-papers.yml) 自动创建 `gh-pages`
6. 再回到 `Pages`
7. 在 `Build and deployment` 中选择 `Deploy from a branch`
8. 选择 `gh-pages` 分支和 `/ (root)`

不要选择 `main` 和 `/ (root)`。

原因是当前站点首页不在仓库根目录，而 workflow 也已经约定把正式发布产物推到 `gh-pages`。如果你想完全不使用 `gh-pages`，那才应该改成 `main` + `/docs`，但这不是当前仓库的默认发布方式。

## 3. 配置 GitHub Actions 权限

1. 打开 `Settings > Actions > General`
2. 在 `Workflow permissions` 中选择 `Read and write permissions`
3. 勾选 `Allow GitHub Actions to create and approve pull requests`

## 4. 工作流行为

仓库中的 [`.github/workflows/update-papers.yml`](.github/workflows/update-papers.yml) 会在 GitHub Actions 中：

1. 检出仓库
2. 按 [`environment.yml`](environment.yml) 创建 `dailypaper` Conda 环境
3. 验证核心依赖
4. 运行 `scripts/fetch_papers.py`
5. 运行 `scripts/reindex_papers.py`
6. 运行 `scripts/generate_html.py`
7. 将新的数据文件提交回主分支
8. 将 `docs/` 发布到 `gh-pages`

默认还会每天自动运行一次，当前 cron 为 `0 1 * * *`，也就是每天 `01:00 UTC`，对应北京时间 `09:00`。

如果要让 `OpenReview` 也稳定进入主流程，需要额外配置 GitHub Actions secrets。因为在 `2026-03-31` 的实测里，OpenReview 匿名 REST 查询会返回 `403`。

推荐 secret：

- `OPENREVIEW_ACCESS_TOKEN`

兼容 fallback：

- `OPENREVIEW_USERNAME`
- `OPENREVIEW_PASSWORD`

工作流会先尝试匿名查询，失败后自动读取上述 secret 做认证重试；如果没有配置，则只跳过 OpenReview，不阻断 `ArXiv / Crossref / DBLP` 主流程。

## 5. 首次触发

1. 打开仓库 `Actions`
2. 选择 `Update Papers Daily`
3. 点击 `Run workflow`
4. 等待 workflow 成功执行
5. 确认远端已经出现 `gh-pages` 分支
6. 再到 `Settings > Pages` 里选择 `gh-pages` 和 `/ (root)`

注意：当前 workflow 支持“每天自动运行 + 手动触发”，但仍然没有配置“每次 push 自动触发”。

如果需要 OpenReview：

1. 打开 `Settings > Secrets and variables > Actions`
2. 新建 `OPENREVIEW_ACCESS_TOKEN`
3. 或者改为同时配置 `OPENREVIEW_USERNAME` 与 `OPENREVIEW_PASSWORD`

## 6. 验证发布结果

1. 在 `Actions` 中确认 workflow 成功
2. 等待 GitHub Pages 完成更新
3. 访问：

```text
https://Jay-XD.github.io/DailyPaperZWJ-main/
```

## 本地预览与线上访问的差异

### 本地预览

本地要先生成 `docs/`，再启动静态文件服务：

```bash
conda run -n dailypaper python -m http.server 8000 --directory docs
```

特点：

- 可以立即看到最新生成结果
- 依赖本地环境
- 关闭本地服务后页面不可访问

### GitHub Pages

特点：

- 页面持续可访问
- 不依赖本地项目是否开启
- 看到的是最近一次生成并发布后的静态快照

## 不推荐的方式

不要把“直接双击 `docs/index.html`”当作正式使用方式。

原因是前端会通过 `fetch("data/*.json")` 加载数据，很多浏览器在 `file://` 模式下会限制这类请求，导致页面空白或筛选失效。

## 常见问题

### Actions 里环境创建失败

- 检查 `environment.yml` 语法
- 检查 GitHub Actions 日志中是否有依赖解析失败

### Pages 打开后是 404

- 确认 `Pages` 配置的是 `gh-pages`
- 如果仓库现在只有 `main`，先手动运行一次 workflow，让它创建 `gh-pages`
- 确认 workflow 已成功运行一次

### 页面打开但没有数据

- 检查 `docs/data/index.json` 是否已生成
- 检查浏览器开发者工具里对 `data/*.json` 的请求是否成功

### 本地双击 HTML 无法使用

- 这是预期行为，不是主支持路径
- 请改用本地静态服务器或 GitHub Pages
