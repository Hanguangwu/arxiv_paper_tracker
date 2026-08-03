# ArXiv 论文追踪与分析器 📚🤖

一个基于 **GitHub Actions** 的自动化工具：每天定时追踪 arXiv 最新论文，使用 **LLM** 智能总结与趋势分析，通过 **邮件** 推送报告，并提供 **Web 前端** 实时展示与**历史记录**浏览。

> ⚠️ 注意：本项目已从单脚本重构为**模块化流水线 + Web 展示**架构。原 `src/conclusion.md` 已停止追加并归档至 `docs/archive/conclusion_archive.md`，改为逐日独立报告 + 结构化 JSON + 前端历史记录。

## ✨ 功能特点

- 🔍 **自动抓取**：每天定时拉取指定类别（cs.AI / cs.LG / cs.CL 等）的最新论文，支持关键词过滤
- 🤖 **LLM 智能分析**：使用 OpenAI-SDK 兼容接口（兼容 DeepSeek / OpenRouter / 自建 vLLM 等），生成论文**六段深度分析**（简明摘要 / 主要贡献 / 研究方法 / 实验结果 / 潜在影响 / 局限与展望）
- 📊 **趋势分析**：TF-IDF 关键词提取 + 主题分组 + **词云图** + LLM 深度趋势解读（研究热点 / 技术趋势 / 未来方向）
- 🌐 **Web 前端**：纯 Bootstrap 5 响应式界面，四页签（概览 / 论文列表 / 趋势分析 / 历史记录），无需构建步骤
- ⏱️ **运行历史**：每次运行写入历史索引，可在前端按日期回看当日总结
- 📧 **邮件推送**：多收件人 HTML 报告邮件，成功/失败通知开关，兼容 465 SSL 与 587 STARTTLS
- 💾 **结构化存储**：JSON 逐日归档 + `latest.json` + Markdown 每日报告，支持日期保留清理
- 🚀 **GitHub Actions 集成**：每日自动运行并自动提交结果

## 📂 项目结构

```
arxiv_paper_tracker/
├── .github/workflows/daily_paper_analysis.yml   # GitHub Actions 定时任务
├── .env                                         # 环境变量（LLM / SMTP）
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
language: "zh"                  # 输出语言：zh / en

arxiv:
  categories: ["cs.LG", "cs.AI"] # 研究类别
  keywords: []                  # 关键词过滤（为空则不过滤）
  max_results: 20               # 单次抓取上限
  days_back: 5                  # 回溯天数

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

工作流默认每天 UTC 00:00（北京时间 08:00）运行，运行结果自动提交至仓库（含 `src/data/**` 与归档文件）。如需修改时间，编辑 `.github/workflows/daily_paper_analysis.yml` 的 cron 表达式。

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

## 📝 说明

- 内容由 AI 生成，请仔细甄别后再使用。
- GitHub Actions 每月提供 2000 分钟免费额度，足以支撑日常运行。

## 📄 License

MIT License