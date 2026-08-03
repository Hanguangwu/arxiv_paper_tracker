"""
论文分析模块

使用 OpenAI SDK (openai==2.41.0) 分析单篇论文，生成与原有 main.py 一致的
六节结构分析，并从中抽取一句式中文小结。分析失败时不会抛出异常，而是返回
一个简短的错误标记，保证整条流水线不会因单篇论文而崩溃。
"""
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_FALLBACK_NOTE = "该论文分析生成失败，请稍后重试。"


class PaperAnalyzer:
    """基于 OpenAI 兼容接口的论文分析器。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None, client: Optional[Any] = None):
        self.config = config or {}
        llm_cfg = config.get("llm", {}) if config else {}
        self.temperature = float(llm_cfg.get("temperature", 0.2))
        self.max_tokens = int(llm_cfg.get("max_tokens", 2048))

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
        """分析单篇论文。

        Args:
            paper: 规范化的论文 dict。

        Returns:
            形如 {"summary": str, "analysis": str}；失败时返回中文错误占位。
        """
        if not self.available():
            note = _FALLBACK_NOTE + "（LLM 客户端未就绪）"
            return {"summary": note, "analysis": "**" + note + "**"}

        author_names = ", ".join(paper.get("authors", []) or [])
        categories = ", ".join(paper.get("categories", []) or [])
        abstract = paper.get("abstract", "") or "（无摘要）"

        prompt = self._build_prompt(
            title=paper.get("title", ""),
            authors=author_names,
            categories=categories,
            published=paper.get("published_date", "") or paper.get("published", ""),
            abstract=abstract,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": "你是一位专门总结和分析学术论文的研究助手。请使用中文回复。"},
                    {"role": "user", "content": prompt},
                ],
            )
            content = response.choices[0].message.content or ""
            analysis = content.strip()
            summary = self._extract_summary(analysis)
            logger.info("论文分析完成: %s", paper.get("id", paper.get("title", "")))
            return {"summary": summary, "analysis": analysis}
        except Exception as exc:  # noqa: BLE001 - 单篇失败不应中断整个流水线
            note = f"{_FALLBACK_NOTE}（{exc}）"
            logger.error("分析论文失败 %s: %s", paper.get("id", ""), exc)
            return {"summary": note, "analysis": "**" + note + "**"}

    @staticmethod
    def _build_prompt(title: str, authors: str, categories: str, published: str, abstract: str) -> str:
        return f"""论文标题: {title}
        作者: {authors or "未知"}
        类别: {categories}
        发布时间: {published}
        摘要: {abstract}

        请分析这篇研究论文。首先单独用一行给出"简明摘要"（3-5 句话），
        不要添加任何标题前缀，随后依次给出以下 6 节（每节以类似 "## 2. 主要贡献与创新" 的标题开头）：
        1. 简明摘要
        2. 主要贡献与创新
        3. 研究方法（具体技术、工具、数据集）
        4. 实验结果（数据集、实验设置、结果与结论）
        5. 潜在影响
        6. 局限性与未来方向

        请全程使用中文，以纯文本按自然段落输出。
        """

    @staticmethod
    def _extract_summary(analysis: str) -> str:
        """Extract the concise summary from the analysis text (first non-empty line)."""
        text = analysis.strip()
        if not text:
            return _FALLBACK_NOTE
        first = next((p.strip() for p in text.split("\n") if p.strip()), "")
        return first.lstrip("# ").strip() if first else text[:120]