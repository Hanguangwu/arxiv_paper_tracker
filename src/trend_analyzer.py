"""
趋势分析模块 - 对已抓取论文的摘要做整体分析

  - TF-IDF 关键词提取（sklearn 可用时优先使用，否则退化为纯词频 + 停用词过滤）
  - 主题分组 (topics)
  - 可视化统计 (statistics)
  - 可选 LLM 深度解读 (hotspots / trends / future_directions / analysis_summary)
  - 可选词云 PNG（仅当 wordcloud + matplotlib 均可导入时才生成）

所有可选依赖缺失时均会优雅降级，保证流水线仍可运行。
"""
import logging
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

N_TOPICS = 5
STOPWORDS = {
    "paper", "papers", "study", "research", "approach", "method", "methods",
    "propose", "proposed", "present", "presented", "show", "shows", "demonstrate",
    "arxiv", "preprint", "preprints", "et", "al", "also", "based", "using",
    "used", "use", "new", "work", "results", "result", "performance", "model",
    "models", "however", "well", "one", "thus", "often", "way", "many", "can",
    "may", "first", "two", "would", "within", "across", "these", "those",
}


def _tokenize(text: str) -> List[str]:
    """Lowercase the text and return word tokens of length >= 3."""
    return [w for w in re.findall(r"[a-zA-Z]{3,}", text.lower()) if len(w) >= 3]


class TrendAnalyzer:
    """Compute an overall trend analysis for a set of papers."""

    def __init__(
        self,
        config: Dict[str, Any],
        llm_client: Optional[Any] = None,
        model_id: str = "",
        analysis_dir: Optional[Path] = None,
    ):
        self.config = config.get("trend_analysis", {}) or {}
        self.llm_client = llm_client
        self.model_id = model_id
        self.language = str(config.get("language", "zh") or "zh").lower()
        self.temperature = float(config.get("llm", {}).get("temperature", 0.2))
        self.max_tokens = int(config.get("llm", {}).get("max_tokens", 2048))
        self.analysis_dir = Path(analysis_dir) if analysis_dir else Path("data/analysis")

    def analyze(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run the full trend analysis over a paper list."""
        if not papers:
            return {
                "keywords": [],
                "topics": [],
                "llm_analysis": {},
                "wordcloud": {"path": None},
                "statistics": {"total_papers": 0},
            }

        features = self._extract_keywords(papers)
        keywords = [{"word": word, "score": float(score)} for word, score in features]
        topics = self._extract_topics(keywords)
        statistics = self._statistics(papers, keywords)

        wordcloud_path = None
        if self.config.get("generate_wordcloud", True):
            wordcloud_path = self._generate_wordcloud(papers)

        llm_analysis = {}
        if self.config.get("use_llm", True) and self.llm_client:
            llm_analysis = self._llm_trend(papers, keywords)

        result = {
            "keywords": keywords,
            "topics": topics,
            "llm_analysis": llm_analysis,
            "wordcloud": {"path": wordcloud_path},
            "statistics": statistics,
        }
        logger.info("趋势分析完成: %d 篇论文, %d 个关键词", len(papers), len(keywords))
        return result

    def _documents(self, papers: List[Dict[str, Any]]) -> List[List[str]]:
        return [_tokenize(f"{p.get('title', '')} {p.get('abstract', '')}") for p in papers]

    def _extract_keywords(self, papers: List[Dict[str, Any]]) -> List[tuple]:
        """Return a ranked list of (word, score) tuples."""
        try:
            return self._tfidf_sklearn(self._documents(papers))
        except Exception as exc:  # noqa: BLE001 - sklearn is optional
            logger.warning("sklearn 不可用，退化为纯词频关键词: %s", exc)
            return self._frequency_fallback(self._documents(papers))

    @staticmethod
    def _frequency_fallback(documents: List[List[str]]) -> List[tuple]:
        """Pure-frequency ranking fallback when sklearn is unavailable."""
        counts: Counter = Counter()
        for tokens in documents:
            for word in tokens:
                if word not in STOPWORDS:
                    counts[word] += 1
        total = sum(counts.values()) or 1
        return [(word, count / total) for word, count in counts.most_common(60)]

    @staticmethod
    def _tfidf_sklearn(documents: List[List[str]]) -> List[tuple]:
        """TF-IDF keyword scoring via sklearn; raises ImportError if unavailable."""
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(
            max_features=60,
            stop_words="english",
            min_df=1,
            ngram_range=(1, 2),
        )
        matrix = vectorizer.fit_transform(" ".join(tokens) for tokens in documents)
        scores = matrix.mean(axis=0).A1
        names = vectorizer.get_feature_names_out()
        ranked = [
            (name, float(score))
            for name, score in zip(names, scores)
            if float(score) > 1e-6
        ]
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked[:60]

    def _extract_topics(self, keywords: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Bucket the top keywords into topic groups (pure-Python)."""
        size = math.ceil(len(keywords) / N_TOPICS) or 1
        topics = []
        for index in range(N_TOPICS):
            chunk = keywords[index * size:(index + 1) * size]
            if not chunk:
                continue
            topics.append({
                "id": index + 1,
                "words": [k["word"] for k in chunk],
                "score": round(sum(k["score"] for k in chunk) / len(chunk), 6),
            })
        return topics

    def _statistics(self, papers: List[Dict[str, Any]], keywords: List[Dict[str, Any]]) -> Dict[str, Any]:
        categories: Counter = Counter()
        authors: Counter = Counter()
        primary: Counter = Counter()
        for p in papers:
            for category in p.get("categories", []) or []:
                categories[category] += 1
            for author in p.get("authors", []) or []:
                authors[author] += 1
            pc = p.get("primary_category") or ""
            if pc:
                primary[pc] += 1

        return {
            "total_papers": len(papers),
            "total_authors": len(authors),
            "categories_count": len(categories),
            "category_distribution": dict(categories.most_common(10)),
            "primary_distribution": dict(primary.most_common(10)),
            "top_authors": dict(authors.most_common(10)),
            "top_keywords": [k["word"] for k in keywords[:10]],
        }

    def _generate_wordcloud(self, papers: List[Dict[str, Any]]) -> Optional[str]:
        """Generate a wordcloud PNG; return its path or None if deps are missing."""
        try:
            import matplotlib

            matplotlib.use("Agg")
            from matplotlib import pyplot as plt
            from wordcloud import WordCloud
        except ImportError as exc:
            logger.warning("缺少 wordcloud/matplotlib，跳过词云生成: %s", exc)
            return None

        tokens = [w for doc in self._documents(papers) for w in doc]
        text = " ".join(w for w in tokens if w not in STOPWORDS)

        wordcloud = WordCloud(
            width=1600,
            height=800,
            background_color="white",
            stopwords=STOPWORDS,
            max_words=100,
            max_font_size=120,
            relative_scaling=0.5,
            colormap="viridis",
            min_font_size=10,
        ).generate(text)

        self.analysis_dir.mkdir(parents=True, exist_ok=True)
        path = self.analysis_dir / f"wordcloud_{datetime.now().strftime('%Y-%m-%d')}.png"

        plt.figure(figsize=(16, 8))
        plt.imshow(wordcloud, interpolation="bilinear")
        plt.axis("off")
        plt.tight_layout(pad=0)
        plt.savefig(path, dpi=150, bbox_inches="tight", transparent=True)
        plt.close()

        logger.info("词云已保存: %s", path)
        return str(path)

    def _llm_trend(self, papers: List[Dict[str, Any]], keywords: List[Dict[str, Any]]) -> Dict[str, str]:
        """Generate a deep trend interpretation with the LLM client."""
        categories = self._uniq_categories(papers)
        top_keywords = ", ".join(k["word"] for k in keywords[:30])
        is_en = self.language != "zh"
        system_prompt = (
            "You are an experienced AI research analyst. Please answer in English."
            if is_en
            else "你是资深 AI 研究分析专家，请用中文回答。"
        )
        field_instruction = (
            "Please give a field-structured trend interpretation, returning the four fields, "
            "each on its own line formatted as 'hotspots: ...', 'trends: ...', "
            "'future_directions: ...', 'analysis_summary: ...'."
            if is_en
            else "请用中文给出字段化的趋势解读，分别返回四个字段，每项单独一行、"
            "形如 'hotspots: ...'、'trends: ...'、'future_directions: ...'、"
            "'analysis_summary: ...'。"
        )

        prompt = (
            f"Here are the latest {len(papers)} arXiv papers.\n"
            f"Research categories: {', '.join(categories)}\n"
            f"Top keywords: {top_keywords}\n\n"
            f"{field_instruction}"
        )

        try:
            response = self.llm_client.chat.completions.create(
                model=self.model_id,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = response.choices[0].message.content or ""
            return self._parse_llm_trend(raw)
        except Exception as exc:  # noqa: BLE001 - LLM failure must not abort the run
            logger.error("LLM trend analysis failed: %s", exc)
            note = "Trend analysis generation failed" if is_en else "趋势深度分析生成失败"
            return {"analysis_summary": f"{note}（{exc}）"}

    @staticmethod
    def _parse_llm_trend(raw: str) -> Dict[str, str]:
        """Parse 'hotspots: ...' style lines from the LLM trend response."""
        keys = ("hotspots", "trends", "future_directions", "analysis_summary")
        result = {key: "" for key in keys}
        for line in raw.splitlines():
            if ":" not in line:
                continue
            label, _, value = line.partition(":")
            label = label.strip().lower()
            for key in keys:
                if key in label and not result[key]:
                    result[key] = value.strip()
        return result

    @staticmethod
    def _uniq_categories(papers: List[Dict[str, Any]]) -> List[str]:
        """Flatten and de-dupe categories across papers."""
        seen = []
        for p in papers:
            for category in list(p.get("categories", []) or []) + [p.get("primary_category")]:
                if category and category not in seen:
                    seen.append(category)
        return seen[:10]