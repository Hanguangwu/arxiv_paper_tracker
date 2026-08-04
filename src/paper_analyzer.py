"""
Paper analysis module

Uses the OpenAI SDK (openai==2.41.0) to analyze a single paper, producing the
same six-section structured analysis as before plus a one-line summary in the
configured output language. Failures do not raise; they return a short error
marker so a single bad paper never crashes the pipeline.
"""
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_FALLBACK_NOTES = {
    "zh": "该论文分析生成失败，请稍后重试。",
    "en": "Analysis generation failed for this paper; please try again later.",
}


def _fallback_note(language: str) -> str:
    return _FALLBACK_NOTES.get(str(language).lower()[:2], _FALLBACK_NOTES["en"])


class PaperAnalyzer:
    """Analyze papers through an OpenAI-compatible interface."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, client: Optional[Any] = None):
        self.config = config or {}
        llm_cfg = config.get("llm", {}) if config else {}
        self.temperature = float(llm_cfg.get("temperature", 0.2))
        self.max_tokens = int(llm_cfg.get("max_tokens", 2048))
        self.language = str(config.get("language", "en") or "en").lower()

        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL")
        self.model_id = os.getenv("LLM_MODEL_ID")

        self.client = client or self._build_client()
        self.model = self.model_id if self.client else None

    def _build_client(self) -> Optional[Any]:
        """Lazily build an OpenAI client from env keys; None if not configured."""
        if not self.api_key:
            logger.warning("未配置 LLM_API_KEY，论文分析将被跳过")
            return None
        try:
            from openai import OpenAI
        except ImportError as exc:
            logger.error("未安装 openai 库 (pip install openai==2.41.0): %s", exc)
            return None
        return OpenAI(api_key=self.api_key, base_url=self.base_url)

    def available(self) -> bool:
        return self.client is not None and bool(self.model)

    def analyze(self, paper: Dict[str, Any]) -> Dict[str, str]:
        """Analyze a single paper, returning {"summary": str, "analysis": str}.

        On failure returns a short localized error marker instead of raising.
        """
        note = _fallback_note(self.language)
        if not self.available():
            note = f"{note} (LLM client not ready)"
            return {"summary": note, "analysis": f"**{note}**"}

        author_names = ", ".join(paper.get("authors", []) or [])
        categories = ", ".join(paper.get("categories", []) or [])
        abstract = paper.get("abstract", "") or "(no abstract)"

        prompt = self._build_prompt(
            title=paper.get("title", ""),
            authors=author_names,
            categories=categories,
            published=paper.get("published_date", "") or paper.get("published", ""),
            abstract=abstract,
        )

        system_prompt = (
            "You are a research assistant specializing in summarizing and "
            "analyzing academic papers. Please reply in English."
            if self.language != "zh"
            else "你是一位专门总结和分析学术论文的研究助手。请使用中文回复。"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            content = response.choices[0].message.content or ""
            analysis = content.strip()
            summary = self._extract_summary(analysis)
            logger.info("Paper analysis complete: %s", paper.get("id", paper.get("title", "")))
            return {"summary": summary, "analysis": analysis}
        except Exception as exc:  # noqa: BLE001 - single-paper failure must not stop the pipeline
            note = f"{_fallback_note(self.language)} ({exc})"
            logger.error("Failed to analyze paper %s: %s", paper.get("id", ""), exc)
            return {"summary": note, "analysis": f"**{note}**"}

    def _build_prompt(self, title: str, authors: str, categories: str, published: str, abstract: str) -> str:
        language_label = "English" if self.language != "zh" else "中文"
        return f"""Paper title: {title}
Authors: {authors or "Unknown"}
Categories: {categories}
Published: {published}
Abstract: {abstract}

Analyze this research paper. First, give a concise summary (3-5 sentences)
as a single line WITHOUT any title prefix, then provide the following
6 sections, each starting with a header like "## 2. Key Contributions and Innovations":
1. Concise Summary
2. Key Contributions and Innovations
3. Research Method (specific techniques, tools, datasets)
4. Experimental Results (datasets, setup, findings and conclusions)
5. Potential Impact
6. Limitations and Future Directions

Please reply entirely in {language_label} as plain paragraphs.
"""

    def _extract_summary(self, analysis: str) -> str:
        text = analysis.strip()
        if not text:
            return _fallback_note(self.language)
        first = next((p.strip() for p in text.split("\n") if p.strip()), "")
        return first.lstrip("# ").strip() if first else text[:120]