# -*- coding: utf-8 -*-
"""
ArXiv 论文追踪 Web 前端 (Flask)

独立于后端流水线运行的只读 Web 服务:
  - 从 src/data/ 下的 JSON 文件读取数据 (由流水线并行写入)
  - 对外暴露 REST API
  - 通过 Flask 模板渲染单页应用 (SPA)

设计要点:
  - 所有数据文件或字段缺失时都优雅降级: 返回 4xx + {"message": "暂无数据"},
    绝不因文件不存在而 500 崩溃。
  - 数据契约兼容两种字段风格 (如 wordcloud 对象 与 wordcloud_path 字符串),
    读取时尽量宽容, 以适配后端可能不同的写法。
"""
import os
import json
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

try:
    import markdown as md_lib
    HAS_MARKDOWN = True
except Exception:  # pragma: no cover - markdown 不可用时的兜底
    HAS_MARKDOWN = False


WEB_DIR = Path(__file__).resolve().parent          # src/web
DATA_DIR = WEB_DIR.parent / "data"                 # src/data
PAPERS_DIR = DATA_DIR / "papers"
SUMMARIES_DIR = DATA_DIR / "summaries"
ANALYSIS_DIR = DATA_DIR / "analysis"
RECORDS_INDEX = DATA_DIR / "records" / "index.json"

app = Flask(__name__)

EMPTY = "暂无数据"


def load_json(path):
    """安全加载 JSON 文件; 不存在或解析失败时返回 None (不抛异常)。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def empty_error(msg=EMPTY):
    """统一的数据缺失响应体。"""
    return jsonify({"error": msg, "message": msg})


def markdown_to_html(text):
    """将 Markdown 文本转为 HTML; markdown 库不可用时退化为纯文本。"""
    if not text:
        return ""
    if HAS_MARKDOWN:
        return md_lib.markdown(str(text), extensions=["tables", "fenced_code", "nl2br"])
    return "<p>" + str(text).replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"


def normalize_keywords(keywords):
    """统一关键词结构, 使每条同时含 word 与 score 字段。

    兼容 {"word", "score"} 与 {"keyword", "score"} 两种写法。
    """
    result = []
    for kw in keywords or []:
        if not isinstance(kw, dict):
            continue
        word = kw.get("word") or kw.get("keyword")
        if word is None:
            continue
        result.append({"word": word, "score": kw.get("score", 0)})
    return result


def get_record_dates():
    """从 records/index.json 提取全部已完成日期 (total_days 依据之一)。"""
    data = load_json(RECORDS_INDEX)
    records = data.get("records", []) if isinstance(data, dict) else []
    return [r.get("date") for r in records if r.get("date")]


def count_daily_files():
    """按 papers_YYYY-MM-DD.json 文件数量估计总运行天数。"""
    if not PAPERS_DIR.is_dir():
        return 0
    return len(list(PAPERS_DIR.glob("papers_*.json")))


@app.route("/")
def index():
    """渲染单页应用首页。"""
    return render_template("index.html")


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/api/stats")
def get_stats():
    """概览统计; 部分文件缺失时仍返回 200 + 零值, 供前端展示空态。"""
    papers_data = load_json(PAPERS_DIR / "latest.json")
    summaries_data = load_json(SUMMARIES_DIR / "latest.json")
    analysis_data = load_json(ANALYSIS_DIR / "latest.json")

    papers = papers_data.get("papers", []) if isinstance(papers_data, dict) else []
    summaries = summaries_data.get("papers", []) if isinstance(summaries_data, dict) else []

    keywords = []
    if isinstance(analysis_data, dict):
        keywords = normalize_keywords(analysis_data.get("keywords", []))

    last_update = None
    if isinstance(papers_data, dict) and papers_data.get("date"):
        last_update = papers_data.get("date")
    elif isinstance(analysis_data, dict) and analysis_data.get("date"):
        last_update = analysis_data.get("date")

    category_set = set()
    for p in papers:
        for c in p.get("categories", []) or []:
            category_set.add(c)

    record_dates = get_record_dates()
    total_days = len(record_dates) if record_dates else count_daily_files()

    return jsonify({
        "papers_count": len(papers),
        "summaries_count": len([p for p in summaries if p.get("summary")]),
        "categories_count": len(category_set),
        "keywords_count": len(keywords),
        "last_update": last_update,
        "total_days": total_days,
    })


@app.route("/api/papers")
def get_papers():
    """论文列表: 支持分页、类别过滤、关键词搜索。"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    category = request.args.get("category", "", type=str).strip()
    q = request.args.get("q", "", type=str).strip()

    papers_data = load_json(PAPERS_DIR / "latest.json")
    if not isinstance(papers_data, dict) or not papers_data.get("papers"):
        return empty_error("暂无论文数据"), 404

    papers = papers_data["papers"]

    if category:
        papers = [p for p in papers if category in (p.get("categories", []) or [])]

    if q:
        ql = q.lower()
        matched = []
        for p in papers:
            hay = " ".join([
                str(p.get("title", "")),
                " ".join(p.get("authors", []) or []),
                str(p.get("abstract", "")),
            ]).lower()
            if ql in hay:
                matched.append(p)
        papers = matched

    total = len(papers)
    per_page = max(1, per_page)
    page = max(1, page)
    start = (page - 1) * per_page
    page_slice = papers[start:start + per_page]

    return jsonify({
        "papers": page_slice,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    })


@app.route("/api/papers/<paper_id>")
def get_paper_detail(paper_id):
    """返回论文完整对象; 存在摘要时附加 Markdown->HTML 的 summary_html。"""
    papers = load_json(PAPERS_DIR / "latest.json")
    papers = papers.get("papers", []) if isinstance(papers, dict) else []

    paper = next((p for p in papers if p.get("id") == paper_id), None)
    if paper is None:
        return empty_error("该论文不存在"), 404

    summaries = load_json(SUMMARIES_DIR / "latest.json")
    summaries = summaries.get("papers", []) if isinstance(summaries, dict) else []
    for s in summaries:
        if s.get("id") == paper_id and s.get("summary"):
            paper = dict(paper)
            paper["summary"] = s["summary"]
            paper["summary_html"] = markdown_to_html(s["summary"])
            break

    return jsonify(paper)


@app.route("/api/categories")
def get_categories():
    """返回按数量降序排列的类别列表。"""
    papers_data = load_json(PAPERS_DIR / "latest.json")
    papers = papers_data.get("papers", []) if isinstance(papers_data, dict) else []

    if not papers:
        return empty_error("暂无论文数据"), 404

    counter = {}
    for p in papers:
        for c in p.get("categories", []) or []:
            counter[c] = counter.get(c, 0) + 1

    categories = [{"name": name, "count": count} for name, count in counter.items()]
    categories.sort(key=lambda x: x["count"], reverse=True)
    return jsonify(categories)


@app.route("/api/analysis")
def get_analysis():
    """返回趋势分析数据, 并为 LLM 分析的 markdown 字段附加 HTML 版本。"""
    data = load_json(ANALYSIS_DIR / "latest.json")
    if not isinstance(data, dict):
        return empty_error("暂无分析数据"), 404

    llm = data.get("llm_analysis", {}) or {}
    for key in ("hotspots", "trends", "future_directions", "analysis_summary",
                "research_ideas", "full_analysis"):
        if llm.get(key):
            llm[key + "_html"] = markdown_to_html(llm[key])

    wc_obj = data.get("wordcloud")
    if isinstance(wc_obj, dict):
        wc_path = wc_obj.get("path")
    else:
        wc_path = data.get("wordcloud_path") or (wc_obj if isinstance(wc_obj, str) else None)

    return jsonify({
        "date": data.get("date"),
        "keywords": normalize_keywords(data.get("keywords")),
        "topics": data.get("topics", []),
        "llm_analysis": llm,
        "wordcloud": {"path": wc_path} if wc_path else {},
        "statistics": data.get("statistics", {}),
    })


@app.route("/api/wordcloud")
def get_wordcloud():
    """返回词云图片 URL (基于 analysis json 中的 path 取 basename)。"""
    data = load_json(ANALYSIS_DIR / "latest.json")
    wc_obj = data.get("wordcloud") if isinstance(data, dict) else None
    if isinstance(wc_obj, dict):
        wc_path = wc_obj.get("path")
    else:
        wc_path = data.get("wordcloud_path") if isinstance(data, dict) else None

    if not wc_path:
        return jsonify({"url": None})

    filename = os.path.basename(str(wc_path).replace("\\", "/"))
    if not (ANALYSIS_DIR / filename).is_file():
        return jsonify({"url": None})

    return jsonify({"url": f"/api/analysis/images/{filename}"})


@app.route("/api/analysis/images/<path:filename>")
def analysis_image(filename):
    """仅从 src/data/analysis 目录服务图片, 防止路径穿越。"""
    safe_name = os.path.basename(str(filename).replace("\\", "/"))
    return send_from_directory(str(ANALYSIS_DIR), safe_name)


@app.route("/api/history")
def get_history():
    """返回运行历史记录, 按日期新到旧排序。"""
    data = load_json(RECORDS_INDEX)
    records = data.get("records", []) if isinstance(data, dict) else []

    records = [r for r in records if r.get("date")]
    records.sort(key=lambda r: str(r.get("date", "")), reverse=True)
    return jsonify({"records": records})


@app.route("/api/history/<date>")
def get_history_detail(date):
    """返回某一天已总结的论文 (每条附带六节分析 HTML)。"""
    summaries = load_json(SUMMARIES_DIR / f"summaries_{date}.json")
    if not isinstance(summaries, dict) or not summaries.get("papers"):
        return empty_error(f"{date} 无总结数据"), 404

    out = []
    for p in summaries["papers"]:
        item = dict(p)
        if p.get("summary"):
            item["summary_html"] = markdown_to_html(p["summary"])
        out.append(item)

    return jsonify({
        "date": summaries.get("date", date),
        "papers": out,
        "count": len(out),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)