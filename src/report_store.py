"""
持久化存储模块

集中管理所有 JSON / Markdown 产物的读写，以及运行历史索引的维护。
所有 JSON 统一使用 ensure_ascii=False + indent=2，并保证父目录自动创建。
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
PAPERS_DIR = DATA_DIR / "papers"
SUMMARIES_DIR = DATA_DIR / "summaries"
ANALYSIS_DIR = DATA_DIR / "analysis"
REPORTS_DIR = DATA_DIR / "reports"
RECORDS_DIR = DATA_DIR / "records"
RECORDS_INDEX = RECORDS_DIR / "index.json"

_DATED_DIRS = (PAPERS_DIR, SUMMARIES_DIR, ANALYSIS_DIR, REPORTS_DIR)


def today_str() -> str:
    """返回当天日期 (YYYY-MM-DD)。"""
    return datetime.now().strftime("%Y-%m-%d")


def ensure_dirs() -> None:
    """Create all required storage directories if missing."""
    for path in (PAPERS_DIR, SUMMARIES_DIR, ANALYSIS_DIR, REPORTS_DIR, RECORDS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load a JSON file; return None on any failure (never raises)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def save_json(path: Path, data: Any) -> None:
    """Write JSON data with ensure_ascii=False and indent=2."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def save_papers(date: str, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Persist the dated papers file and refresh latest.json."""
    ensure_dirs()
    payload = {"date": date, "count": len(papers), "papers": papers}
    save_json(PAPERS_DIR / f"papers_{date}.json", payload)
    save_json(PAPERS_DIR / "latest.json", payload)
    return payload


def save_summaries(date: str, summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Persist dated summaries file and latest.json."""
    ensure_dirs()
    payload = {"date": date, "count": len(summaries), "papers": summaries}
    save_json(SUMMARIES_DIR / f"summaries_{date}.json", payload)
    save_json(SUMMARIES_DIR / "latest.json", payload)
    return payload


def save_analysis(date: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Persist dated analysis file (incl. wordcloud path) and latest.json."""
    ensure_dirs()
    payload = dict(analysis)
    payload["date"] = date
    save_json(ANALYSIS_DIR / f"analysis_{date}.json", payload)
    save_json(ANALYSIS_DIR / "latest.json", payload)
    return payload


def write_report(date: str, content: str) -> str:
    """Write the dated Markdown report and return its absolute path."""
    ensure_dirs()
    path = REPORTS_DIR / f"report_{date}.md"
    path.write_text(content, encoding="utf-8")
    logger.info("Markdown 报告已写入: %s", path)
    return str(path)


def init_records() -> None:
    """Scaffold records/index.json if it does not exist."""
    ensure_dirs()
    if not RECORDS_INDEX.exists():
        save_json(RECORDS_INDEX, {"records": []})


def add_record(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Append (or update) a run record, keeping the list newest-first.

    Existing date entries are updated in place instead of duplicated.
    """
    init_records()
    data = load_json(RECORDS_INDEX)
    records = list(data.get("records", [])) if isinstance(data, dict) else []

    date = record.get("date")
    kept = [r for r in records if r.get("date") != date]
    kept.insert(0, record)
    save_json(RECORDS_INDEX, {"records": kept})
    logger.info("运行历史已更新，共 %d 条记录", len(kept))
    return kept


def prune_old_files(retention_days: int) -> None:
    """Remove dated files older than retention_days (0 means keep forever)."""
    if retention_days <= 0:
        return
    cutoff = datetime.now() - timedelta(days=int(retention_days))
    jobs = (
        (PAPERS_DIR, "papers_*.json"),
        (SUMMARIES_DIR, "summaries_*.json"),
        (ANALYSIS_DIR, "analysis_*.json"),
        (REPORTS_DIR, "report_*.md"),
    )
    removed = 0
    for directory, pattern in jobs:
        if not directory.is_dir():
            continue
        for path in directory.glob(pattern):
            if _is_older(path, cutoff):
                path.unlink(missing_ok=True)
                removed += 1
    if removed:
        logger.info("已清理 %d 个过期历史文件 (保留 %d 天)", removed, retention_days)


def _is_older(path: Path, cutoff: datetime) -> bool:
    """Whether a dated-file's embedded date precedes the cutoff date."""
    parts = path.stem.split("_")
    if len(parts) < 2:
        return False
    date_part = parts[-1]
    try:
        file_date = datetime.strptime(date_part, "%Y-%m-%d")
    except ValueError:
        return False
    return file_date < cutoff