# ArXiv 论文追踪与分析器 📚🤖

一个基于 **GitHub Actions** 的自动化工具：**每周日**定时追踪 arXiv 最新论文，使用 **LLM** 智能总结与趋势分析，通过 **邮件** 推送报告，并将结果自动部署为 **GitHub Pages** 静态网站。

> ⚠️ 注意：本项目已从单脚本重构为**模块化流水线 + Web 展示**架构。原 `src/conclusion.md` 已停止追加并归档至 `docs/archive/conclusion_archive.md`，改为逐日独立报告 + 结构化 JSON + 前端历史记录。

## ✨ 功能特点

- 🔍 **自动抓取**：每周日定时拉取指定类别（cs.AI / cs.LG / cs.CL 等）最近 7 天的论文（默认 30 篇），支持关键词过滤
- 🤖 **LLM 智能分析**：使用 OpenAI-SDK 兼容接口（兼容 DeepSeek / OpenRouter / 自建 vLLM 等），生成论文**六段深度分析**（简明摘要 / 主要贡献 / 研究方法 / 实验结果 / 潜在影响 / 局限与展望），内容为英文
- 📊 **趋势分析**：TF-IDF 关键词提取 + 主题分组 + **词云图** + LLM 深度趋势解读（研究热点 / 技术趋势 / 未来方向）
- 🌐 **Web 前端**：纯 Bootstrap 5 响应式界面，四页签（概览 / 论文列表 / 趋势分析 / 历史记录），无需构建步骤；可部署到 **GitHub Pages**
- ⏱️ **运行历史**：每次运行写入历史索引，可在前端按日期回看当日总结
- 📧 **邮件推送**：多收件人 HTML 报告邮件，成功/失败通知开关，兼容 465 SSL 与 587 STARTTLS
- 💾 **结构化存储**：JSON 逐日归档 + `latest.json` + Markdown 每日报告，支持日期保留清理
- 🚀 **GitHub Actions 集成**：每周日自动运行、自动提交结果并自动部署 GitHub Pages

## 📂 项目结构

```
arxiv_paper_tracker/
├── .github/workflows/daily_paper_analysis.yml   # GitHub Actions 定时任务（每周日）
├── .env                                         # 环境变量（LLM / SMTP）
├── .gitignore                                   # 忽略 docs/ 构建产物、.env 等
├── requirements.txt                             # 依赖
├── docs/
│   └── archive/conclusion_archive.md            # 旧 conclusion.md 历史备份
└── src/
    ├── config.yaml                  # 主配置（类别/LLM/趋势/邮件/存储）
    ├── main.py                      # 流水线入口：抓取→分析→归档→趋势→报告→历史→邮件
    ├── arxiv_fetcher.py             # arXiv 论文抓取
    ├── paper_analyzer.py            # 单篇论文 LLM 六段分析
    ├── trend_analyzer.py            # 关键词 / 词云 / LLM 趋势
    ├── report_store.py              # JSON + Markdown + 历史索引持久化
    ├── email_notifier.py            # 邮件推送
    ├── data/                        # 结构化产物（见下）
    └── web/
        ├── app.py                   # Flask REST API
        ├── export_static.py         # 构建 GitHub Pages 静态站点
        ├── templates/index.html    # Bootstrap 单页前端
        └── static/js/main.js       # 前端逻辑
```

## 🚀 快速开始

### 1. 配置环境变量（`.env`）

创建 `.env`，填入：

```bash
# LLM（OpenAI-SDK 兼容：OpenAI / DeepSeek / OpenRouter / vLLM...）
LLM_API_KEY="sk-..."
LLM_BASE_URL="https://api.deepseek.com/v1"
LLM_MODEL_ID="deepseek-chat"

# 邮件（可选，未配置则跳过推送）
SMTP_SERVER=smtp.qq.com
SMTP_PORT=587
SMTP_USERNAME=you@qq.com
SMTP_PASSWORD=授权码或应用专用密码
EMAIL_FROM=you@qq.com
EMAIL_TO=recv1@example.com,recv2@example.com   # 支持多收件人，逗号分隔
```

### 2. 配置文件（`src/config.yaml`）

```yaml
language: "en"                  # 输出语言：zh / en（默认 en，论文内容为英文）

arxiv:
  categories: ["cs.LG", "cs.AI"] # 研究类别
  keywords: []                  # 关键词过滤（为空则不过滤）
  max_results: 30               # 单次抓取上限
  days_back: 7                  # 回溯天数

trend_analysis:
  enabled: true                 # 是否启用趋势分析
  generate_wordcloud: true      # 是否生成词云（缺依赖时自动跳过）
  use_llm: true                 # 是否用 LLM 生成深度趋势解读

email:
  enabled: true
  notify_success: true
  notify_failure: true

storage:
  retention_days: 30            # 归档保留天数（0 = 永久保留）
```

### 3. 运行流水线

```bash
pip install -r requirements.txt
python src/main.py
```

### 4. 启动 Web 前端

```bash
python src/web/app.py
# 访问 http://localhost:5000
```

## 🖥️ GitHub Actions 配置

在仓库 `Settings → Secrets and variables → Actions` 配置以下 Secrets（与 `.env` 对应）：

| Secret | 说明 |
|---|---|
| `LLM_API_KEY`（或兼容的 `DEEPSEEK_API_KEY`）| LLM 密钥 |
| `LLM_BASE_URL` / `LLM_MODEL_ID` | LLM 端点与模型 |
| `SMTP_SERVER` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` | SMTP 配置 |
| `EMAIL_FROM` / `EMAIL_TO` | 发件人 / 收件人 |

工作流默认**每周日上午 UTC 00:00**运行，回溯最近 7 天、抓取最多 30 篇论文。运行结果自动提交至仓库（含 `src/data/**` 与归档文件），并自动构建静态站点部署到 **GitHub Pages**。如需修改时间，编辑 `.github/workflows/daily_paper_analysis.yml` 的 cron 表达式。

> 动作使用最新版本：`actions/checkout@v6`、`actions/setup-python@v6`（Node 24，不再触发 Node 20 弃用告警）、`actions/upload-pages-artifact@v4` / `actions/deploy-pages@v4`、`stefanzweifel/git-auto-commit-action@v7`。

## 🌐 GitHub Pages 部署

1. 在仓库 `Settings → Pages` 中，将 **Source** 选择为 **GitHub Actions**。
2. 工作流会在每次分析后：
   - 运行 `src/web/export_static.py`，将 Bootstrap 前端 + 生成的 JSON 数据打包到 `docs/` 目录；
   - 用 `actions/upload-pages-artifact` + `actions/deploy-pages` 自动部署。
3. 站点地址为 `https://<用户名>.github.io/<仓库名>/`。前端会自动按仓库名设置 base path，也可通过工作流中的 `BASE_PATH` 环境变量调整。

本地预览静态站点可直接打开 `docs/index.html`，或运行 `python src/web/export_static.py && python -m http.server -d docs`。

## 📡 REST API

| 端点 | 说明 |
|---|---|
| `GET /` | 前端页面 |
| `GET /api/stats` | 概览统计 |
| `GET /api/papers?page&per_page&category&q` | 论文列表（分页/筛选/搜索）|
| `GET /api/papers/<id>` | 论文详情（含六段分析）|
| `GET /api/categories` | 类别及计数 |
| `GET /api/analysis` | 趋势分析数据 |
| `GET /api/wordcloud` | 词云图片 URL |
| `GET /api/history` | 历史记录 |
| `GET /api/history/<date>` | 某日总结 |

## 🗂️ 生成产物

```
src/data/                            # 运行后自动生成
├── papers/papers_YYYY-MM-DD.json    # 当日论文
├── papers/latest.json                # 最新论文
├── summaries/summaries_YYYY-MM-DD.json
├── summaries/latest.json
├── analysis/analysis_YYYY-MM-DD.json # 趋势分析
├── analysis/wordcloud_YYYY-MM-DD.png # 词云图
├── analysis/latest.json
├── reports/report_YYYY-MM-DD.md      # 每日 Markdown 报告
└── records/index.json                # ★ 历史记录索引
```

## ⚙️ 配置要点

- **论文类别**：在 `src/config.yaml` 的 `arxiv.categories` 中调整（常见：`cs.AI / cs.LG / cs.CV / cs.CL / cs.NE / stat.ML`）。
- **邮件**：支持 QQ 邮箱（需开启 SMTP 获取授权码）、Gmail（应用专用密码）等主流服务；端口 465 用隐式 SSL，其余用 STARTTLS。
- **可选依赖**：趋势分析与词云需要 `scikit-learn / wordcloud / matplotlib`；缺失时流水线自动降级（跳过词云、退回纯词频关键词），不会中断。

## 🛠️ 更新记录

### 2026-08-04 · 修复与增强

1. **修复邮件模板 `KeyError: 'font-family'`**
   - 根因：`src/email_notifier.py` 的 HTML 模板使用 `str.format()` 填充占位符，内嵌 CSS 中的 `body{font-family:...}` 被 Python 误解析为格式字段，导致发送邮件时报 `KeyError`。
   - 修复：模板改用 token 占位符（`__DATE__` 等）+ `str.replace()`，CSS 大括号不再被误解析；邮件文案同步转为英文。

2. **输出内容全部英文**
   - `src/config.yaml` 默认 `language: "en"`；
   - `paper_analyzer.py` / `trend_analyzer.py` 的 LLM 提示词按配置语言生成英文六段分析、趋势解读（含错误占位文案）；
   - `main.py` 生成的 Markdown 报告内容为英文。

3. **定时任务改为每周日运行**
   - 工作流 cron 由每日 `0 0 * * *` 改为每周日 `0 0 * * 0`（UTC 00:00）；
   - `src/config.yaml`：`max_results: 30`、`days_back: 7`，即每次回溯最近 7 天、抓取最多 30 篇论文。

4. **GitHub Actions 升级到最新版本**
   - `actions/checkout@v5 → v6`、`actions/setup-python@v5 → v6`（Node 24 运行时，消除 Node 20 弃用告警）；
   - 新增 `actions/upload-pages-artifact@v4` + `actions/deploy-pages@v4` 自动部署 GitHub Pages。

5. **新增 GitHub Pages 静态部署**
   - 新增 `src/web/export_static.py`：将 Bootstrap 前端 + 生成的 JSON / 词云图打包为 `docs/` 静态站点，并生成 `stats.json` / `categories.json`；
   - 前端支持双模式（Flask 动态 API 模式 / Pages 静态 JSON 模式，通过 `window.APP_BASE` / `window.STATIC_MODE` 切换），界面文案转为英文，静态模式下用 `marked` 在客户端渲染 Markdown；
   - 新增根 `.gitignore`，排除 `docs/` 构建产物与 `.env` 等敏感文件。

## 📝 说明

- 内容由 AI 生成，请仔细甄别后再使用。
- GitHub Actions 每月提供 2000 分钟免费额度，足以支撑日常运行。

## 📄 License

MIT License