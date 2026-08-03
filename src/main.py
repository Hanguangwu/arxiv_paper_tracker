#!/usr/bin/env python3
"""
ArXiv 论文追踪与分析器 - 后端流水线入口

职责:
  加载配置与 .env -> 抓取论文 -> (关键词过滤) -> 逐篇分析 -> 保存 papers/summaries
  -> 趋势分析/词云 -> 生成每日 Markdown 报告 -> 更新历史索引 -> 发送邮件。

运行方式:  python src/main.py  或  python -m src.main
"""
import logging
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
for _p in (PROJECT_ROOT, SRC_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from src import report_store as store  # noqa: E402
from src.arxiv_fetcher import fetch_papers  # noqa: E402
from src.paper_analyzer import PaperAnalyzer  # noqa: E402
from src.trend_analyzer import TrendAnalyzer  # noqa: E402
from src.email_notifier import EmailNotifier  # noqa: E402

logger = logging.getLogger(__name__)


def load_config(config_path: str) -> dict:
    """Load the YAML config; fall back to a minimal default on failure."""
    try:
        import yaml

        with open(config_path, "r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
    except ImportError:
        logger.warning("未安装 PyYAML，使用内置默认配置")
        config = {}
    except (OSError, ValueError) as exc:
        logger.error("加载配置文件失败，使用内置默认配置: %s", exc)
        config = {}
    return _with_defaults(config)


def _with_defaults(config: dict) -> dict:
    defaults = {
        "language": "zh",
        "arxiv": {"categories": ["cs.LG", "cs.AI"], "keywords": [], "max_results": 20, "days_back": 5},
        "llm": {"temperature": 0.2, "max_tokens": 2048},
        "trend_analysis": {"enabled": True, "generate_wordcloud": True, "use_llm": True},
        "email": {"enabled": True, "notify_success": True, "notify_failure": True},
        "storage": {"retention_days": 30},
    }
    for key, value in defaults.items():
        config.setdefault(key, value)
    for key, value in defaults["arxiv"].items():
        config["arxiv"].setdefault(key, value)
    return config


def keyword_filter(papers: list, keywords: list) -> list:
    """Filter papers whose title/abstract contains any configured keyword."""
    terms = [k.lower().strip() for k in (keywords or []) if k and k.strip()]
    if not terms:
        return papers
    matched = [
        p for p in papers
        if any(t in f"{p.get('title', '')} {p.get('abstract', '')}".lower() for t in terms)
    ]
    logger.info("关键词过滤: %d/%d 篇保留", len(matched), len(papers))
    return matched


def main() -> int:
    """Run the full daily pipeline. Returns 0 on success, 1 on fatal errors."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    try:
        from dotenv import load_dotenv
    except ImportError:
        from src.email_notifier import load_dotenv
    env_path = SRC_DIR / ".env" if (SRC_DIR / ".env").exists() else PROJECT_ROOT / ".env"
    load_dotenv(env_path)

    start = time.monotonic()
    date = store.today_str()
    config_path = str(SRC_DIR / "config.yaml")

    result = {"papers": 0, "summaries": 0, "report_path": "", "error": ""}
    try:
        config = load_config(config_path)
        _run_pipeline(config, result)
    except Exception as exc:  # noqa: BLE001 - record failure and still notify
        logger.exception("流水线运行出错: %s", exc)
        result["error"] = str(exc)

    config = load_config(config_path)
    email_sent = _send_result_email(config, date, result)

    record = {
        "date": date,
        "status": "failed" if result["error"] else "success",
        "papers_count": result["papers"],
        "summaries_count": result["summaries"],
        "email_sent": email_sent,
        "took_seconds": round(time.monotonic() - start, 2),
        "error": result["error"],
    }
    record["duration_seconds"] = record["took_seconds"]
    if result["report_path"]:
        record["report_link"] = result["report_path"]

    store.add_record(record)
    store.prune_old_files(int(config.get("storage", {}).get("retention_days", 30)))
    logger.info("本次运行结束，耗时 %.2f 秒", record["took_seconds"])
    return 0 if not result["error"] else 1


def _run_pipeline(config: dict, result: dict) -> None:
    """Run the pipeline steps, filling the shared result dict."""
    date = store.today_str()
    arxiv_cfg = config.get("arxiv", {})
    max_results = int(arxiv_cfg.get("max_results", 20))

    papers = fetch_papers(config)
    result["papers"] = len(papers)

    papers = keyword_filter(papers, arxiv_cfg.get("keywords", []))
    papers = papers[:max_results]

    store.save_papers(date, papers)

    if not papers:
        logger.info("没有符合条件的论文，跳过分析与报告")
        return

    analyzer = PaperAnalyzer(config)

    summaries = []
    for paper in papers:
        analysis = analyzer.analyze(paper)
        entry = dict(paper)
        entry["summary"] = analysis.get("summary", "")
        summaries.append(entry)

    store.save_summaries(date, summaries)
    result["summaries"] = len([s for s in summaries if s.get("summary")])

    trend_analysis = {}
    trend_cfg = config.get("trend_analysis", {}) or {}
    if trend_cfg.get("enabled", True):
        trend = TrendAnalyzer(
            config=config,
            llm_client=analyzer.client if analyzer.available() else None,
            model_id=analyzer.model if analyzer.available() else "",
            analysis_dir=store.ANALYSIS_DIR,
        )
        trend_analysis = trend.analyze(papers)
        store.save_analysis(date, trend_analysis)

    report_content = build_report(config, date, papers, summaries, trend_analysis)
    result["report_path"] = store.write_report(date, report_content)


def _send_result_email(config: dict, date: str, result: dict) -> int:
    """Send the daily report email according to config flags; returns 1 if sent."""
    email_cfg = config.get("email", {}) or {}
    if not email_cfg.get("enabled", True):
        return 0

    notifier = EmailNotifier(config)
    report_link = result.get("report_path") or f"{store.REPORTS_DIR.name}/report_{date}.md"

    if result["error"]:
        if not email_cfg.get("notify_failure", True):
            return 0
        stats = {"total_papers": result["papers"], "categories_count": 0, "error": result["error"]}
        return int(notifier.send(date, [], [], stats, report_link))

    if not email_cfg.get("notify_success", True):
        return 0
    papers_dir = store.PAPERS_DIR / "latest.json"
    papers_data = store.load_json(papers_dir) or {"papers": []}
    summaries_data = store.load_json(store.SUMMARIES_DIR / "latest.json") or {"papers": []}
    stats = {"total_papers": len(papers_data.get("papers", []))}
    return int(notifier.send(date, papers_data.get("papers", []), summaries_data.get("papers", []), stats, report_link))


def build_report(config: dict, date: str, papers: list, summaries: list, analysis: dict) -> str:
    """Assemble the per-day Markdown report content."""
    summary_map = {s.get("id"): s.get("summary", "") for s in summaries}
    lines = [f"# ArXiv 论文分析报告 - {date}", "", f"- 论文总数: {len(papers)}", "", "## 单篇分析", ""]
    for paper in papers:
        lines.append(f"### {paper.get('title', '')}")
        lines.append(f"**作者**: {', '.join(paper.get('authors', []) or []) or '未知'}")
        lines.append(f"**类别**: {', '.join(paper.get('categories', []) or [])}")
        lines.append(f"**发布时间**: {paper.get('published_date', '')}")
        lines.append(f"**链接**: {paper.get('entry_url', '')}")
        lines.append("")
        lines.append(summary_map.get(paper.get("id")) or "（暂无摘要）")
        if paper.get("abstract"):
            lines.append("")
            lines.append(f"<details><summary>摘要</summary>\n\n{paper.get('abstract')}\n\n</details>")
        lines.append("")
        lines.append("---")
        lines.append("")

    keywords = analysis.get("keywords", [])
    if keywords:
        lines.append("## 高频关键词")
        lines.append("")
        for kw in keywords[:20]:
            lines.append(f"- {kw.get('word', '')} (score: {kw.get('score', 0):.4f})")
        lines.append("")

    llm = analysis.get("llm_analysis", {}) or {}
    if llm.get("hotspots"):
        lines.append("## 研究热点")
        lines.append(llm.get("hotspots", ""))
        lines.append("")
    if llm.get("analysis_summary"):
        lines.append("## 分析总结")
        lines.append(llm.get("analysis_summary", ""))
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())