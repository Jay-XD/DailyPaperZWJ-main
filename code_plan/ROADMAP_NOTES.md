# Roadmap Notes

更新时间：`2026-03-31`

## 建议增加功能

- 建议增加：补一份 OpenReview secret 配置说明图或模板
  - 代码侧已经支持 `token` 与 `username/password`
  - 但 GitHub Secrets 和本地环境变量仍建议给出更直观的配置示例

- 建议增加：提高 DBLP venue 查询精度
  - 目前 DBLP 已能抓到较多正式会议记录
  - 后续可改成更严格的 venue 过滤或 key 级规则，减少关键词搜索噪声

- 建议增加：IEEE Xplore 可选插件模式
  - 前提是用户主动提供 `IEEE_API_KEY`
  - 不进入默认主流程
  - 作用是进一步补强 IEEE metadata，而不是替代 Crossref

- 建议增加：`code_plan/` 的变更日志条目
  - 如果后续结构调整频繁，可以再加一个 `CHANGELOG.md`
  - 用于记录“这次改了什么结构、为什么改”

- 建议增加：前端显示 source 统计或切换
  - 当前页面中论文卡片会显示 source provider pill
  - 但还没有单独的 source facet

- 建议增加：review 识别的 metadata 优先策略
  - 如果后续某些 publisher 明确提供 article-type
  - 可以改成 “显式 metadata 优先 + 关键词兜底”

## 建议暂缓功能

- 建议暂缓：真正的 publisher 卡片
  - 当前你的例子本质上是 venue，而不是 publisher
  - 在现阶段加 publisher 维度，信息增益有限

- 建议暂缓：更细的论文体裁分类
  - 例如 `tutorial / survey / benchmark / challenge paper`
  - 当前先用 `review` 这一层足够

- 建议暂缓：复杂前端可视化
  - 例如统计图表、时序趋势图、venue 对比图
  - 当前先保证抓取、筛选、正确性

## 建议忽略功能

- 建议忽略：校园账号自动登录
  - 不做 SSO / VPN / cookie / 浏览器态模拟
  - 技术脆弱且合规风险高

- 建议忽略：受限全文抓取
  - 当前目标是 metadata 与链接，而不是全文采集

- 建议忽略：直接双击 `docs/index.html` 作为正式使用路径
  - 当前前端依赖 `fetch`
  - 正式模式应是 GitHub Pages 或本地静态服务器

- 建议忽略：让 OpenReview 替代 IEEE/期刊源
  - 它只适合覆盖使用 OpenReview 的 venue
  - 不应作为 `JSAC/TWC/TMC/IoTJ` 的替代

## 近期优先级建议

### 高优先级

- DBLP query 精度清理
- 补充 README / DEPLOYMENT 文档，使其反映多源抓取和新筛选卡片
- OpenReview 认证接入说明补强

### 中优先级

- source facet
- `CHANGELOG.md`
- IEEE Xplore 可选集成

### 低优先级

- UI 细节美化
- 更细粒度文献体裁分类
- 图表化统计面板
