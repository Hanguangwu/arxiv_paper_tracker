"""
Build a static GitHub Pages bundle from the Flask frontend + generated data.

Reuses the Flask app's data-loading helpers (src/web/app.py) to emit the same
JSON the API would return, so the static site and the Flask site stay
consistent. Renders index.html with Jinja in "static mode" (window.APP_BASE
set to the repo base path, window.STATIC_MODE=true).

Usage:
    python src/web/export_static.py
    env BASE_PATH=/my-repo/ python src/web/export_static.py
"""
import json
import os
import shutil
import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
SRC_DIR = WEB_DIR.parent
ROOT = SRC_DIR.parent
DATA_DIR = SRC_DIR / "data"
TEMPLATES_DIR = WEB_DIR / "templates"
JS_DIR = WEB_DIR / "static" / "js"
DEFAULT_OUT = ROOT / "docs"

sys.path.insert(0, str(WEB_DIR))
import app as flask_app  # noqa: E402


def _jinja_env():
    from jinja2 import Environment, FileSystemLoader
    from markupsafe import Markup

    def tojson(value):
        return Markup(json.dumps(value))

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
        keep_trailing_newline=True,
    )
    env.filters["tojson"] = tojson
    env.globals["url_for"] = lambda endpoint, **kw: ("js/main.js" if endpoint == "static" else "")
    return env


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _build_stats_payload():
    papers_data = flask_app.load_json(flask_app.PAPERS_DIR / "latest.json") or {}
    papers = papers_data.get("papers", []) if isinstance(papers_data, dict) else []
    summaries_data = flask_app.load_json(flask_app.SUMMARIES_DIR / "latest.json") or {}
    summaries = summaries_data.get("papers", []) if isinstance(summaries_data, dict) else []
    analysis_data = flask_app.load_json(flask_app.ANALYSIS_DIR / "latest.json") or {}

    keywords = (
        flask_app.normalize_keywords(analysis_data.get("keywords", []))
        if isinstance(analysis_data, dict)
        else []
    )
    last_update = None
    if isinstance(papers_data, dict) and papers_data.get("date"):
        last_update = papers_data.get("date")
    elif isinstance(analysis_data, dict) and analysis_data.get("date"):
        last_update = analysis_data.get("date")

    category_set = set()
    for p in papers:
        category_set.update(p.get("categories", []) or [])

    record_dates = flask_app.get_record_dates()
    total_days = len(record_dates) if record_dates else flask_app.count_daily_files()

    return {
        "papers_count": len(papers),
        "summaries_count": len([s for s in summaries if s.get("summary")]),
        "categories_count": len(category_set),
        "keywords_count": len(keywords),
        "last_update": last_update,
        "total_days": total_days,
    }


def _build_categories_payload():
    papers_data = flask_app.load_json(flask_app.PAPERS_DIR / "latest.json") or {}
    papers = papers_data.get("papers", []) if isinstance(papers_data, dict) else []

    counter = {}
    for p in papers:
        for c in p.get("categories", []) or []:
            counter[c] = counter.get(c, 0) + 1
    items = [{"name": name, "count": count} for name, count in counter.items()]
    items.sort(key=lambda x: x["count"], reverse=True)
    return items


def build(base_path: str = "/", out_dir: Path = None) -> Path:
    if not base_path.startswith("/"):
        base_path = "/" + base_path
    if not base_path.endswith("/"):
        base_path = base_path + "/"

    out = Path(out_dir) if out_dir else DEFAULT_OUT
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    html = _jinja_env().get_template("index.html").render(
        base_path=base_path,
        static_mode=True,
    )
    (out / "index.html").write_text(html, encoding="utf-8")

    shutil.copytree(JS_DIR, out / "js", dirs_exist_ok=True)

    for sub in ("papers", "summaries", "analysis", "records"):
        src = DATA_DIR / sub
        if src.is_dir():
            shutil.copytree(src, out / "data" / sub, dirs_exist_ok=True)

    _write_json(out / "data" / "stats.json", _build_stats_payload())
    _write_json(out / "data" / "categories.json", _build_categories_payload())

    print(f"Static GitHub Pages site built at: {out} (base_path={base_path})")
    return out


if __name__ == "__main__":
    build(base_path=os.getenv("BASE_PATH", "/"))