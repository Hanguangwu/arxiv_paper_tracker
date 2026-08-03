"""
ArXiv 论文抓取模块

封装 arXiv client (arxiv==4.0.1) 的搜索逻辑，返回结构化、可 JSON 序列化的论文字典列表，
供流水线后续的分析 / 存储 / 邮件环节使用。
"""
import datetime
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _to_paper_dict(entry: Any) -> Dict[str, Any]:
    """将 arxiv.Result 对象转换为统一的论文字典。"""
    categories = list(getattr(entry, "categories", None) or [])
    published = getattr(entry, "published", None)
    updated = getattr(entry, "updated", None)

    published_date = ""
    if published is not None:
        published_date = published.strftime("%Y-%m-%d")

    def _fmt(dt):
        if dt is None:
            return ""
        return dt.isoformat()

    return {
        "id": entry.get_short_id() if hasattr(entry, "get_short_id") else _entry_id(entry),
        "title": (getattr(entry, "title", "") or "").replace("\n", " ").strip(),
        "authors": [a.name for a in (getattr(entry, "authors", None) or [])],
        "abstract": (getattr(entry, "summary", "") or "").replace("\n", " ").strip(),
        "categories": categories,
        "primary_category": getattr(entry, "primary_category", "") or (categories[0] if categories else ""),
        "published": _fmt(published),
        "updated": _fmt(updated),
        "pdf_url": getattr(entry, "pdf_url", None) or "",
        "entry_url": getattr(entry, "entry_id", None) or "",
        "published_date": published_date,
    }


def _entry_id(entry: Any) -> str:
    """从 entry_id URL 中提取 arxiv 标识，作为稳定主键。"""
    entry_id = getattr(entry, "entry_id", "") or ""
    return entry_id.rstrip("/").split("/")[-1]


def fetch_papers(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """根据配置抓取最近 N 天的 arXiv 论文。

    Args:
        config: 顶层配置字典，使用 ``config["arxiv"]`` 子配置。

    Returns:
        规范化的论文字典列表，可能为空；网络或解析异常时返回空列表并记录日志。
    """
    try:
        import arxiv
    except ImportError:
        logger.error("未安装 arxiv 库 (pip install arxiv==4.0.1)，无法抓取论文")
        return []

    arxiv_cfg = config.get("arxiv", {})
    categories = list(arxiv_cfg.get("categories") or [])
    max_results = int(arxiv_cfg.get("max_results", 20))
    days_back = int(arxiv_cfg.get("days_back", 5))

    if not categories:
        logger.warning("未配置任何 arXiv 类别，跳过抓取")
        return []

    today = datetime.datetime.now()
    start = today - datetime.timedelta(days=days_back)
    start_str = start.strftime("%Y%m%d%H%M%S")
    end_str = today.strftime("%Y%m%d%H%M%S")

    category_query = " OR ".join(f"cat:{cat}" for cat in categories)
    query = f"({category_query}) AND submittedDate:[{start_str} TO {end_str}]"

    logger.info("构建 arXiv 查询: max_results=%s, days_back=%s, %s", max_results, days_back,
                ", ".join(categories))

    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    try:
        client = arxiv.Client()
        results = list(client.results(search))
    except Exception as exc:  # noqa: BLE001 - 网络/解析失败不应中断流水线
        logger.error("抓取 arXiv 论文失败: %s", exc)
        return []

    papers = [_to_paper_dict(entry) for entry in results]
    logger.info("抓取到 %d 篇论文", len(papers))
    return papers