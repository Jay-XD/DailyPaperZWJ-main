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
3. 在 `Build and deployment` 中选择 `Deploy from a branch`
4. 选择 `gh-pages` 分支和 `/ (root)`

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

## 5. 首次触发

### 方法一：手动触发

1. 打开仓库 `Actions`
2. 选择 `Update Papers Daily`
3. 点击 `Run workflow`

### 方法二：提交触发

```bash
git add .
git commit -m "Trigger workflow"
git push
```

## 6. 验证发布结果

1. 在 `Actions` 中确认 workflow 成功
2. 等待 GitHub Pages 完成更新
3. 访问：

```text
https://<your-github-username>.github.io/<repo-name>/
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
- 确认 workflow 已成功运行一次

### 页面打开但没有数据

- 检查 `docs/data/index.json` 是否已生成
- 检查浏览器开发者工具里对 `data/*.json` 的请求是否成功

### 本地双击 HTML 无法使用

- 这是预期行为，不是主支持路径
- 请改用本地静态服务器或 GitHub Pages
