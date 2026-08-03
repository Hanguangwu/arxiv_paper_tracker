"""
邮件通知模块

从 .env 读取 SMTP_* / EMAIL_* 配置，支持多收件人（逗号分隔）以及
465(隐式 SSL) / 587(STARTTLS) 双模式发送 HTML 邮件。

配置缺失时仅记录警告并返回 False，绝不抛出异常。
"""
import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<style>
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;
line-height:1.6;max-width:1000px;margin:0 auto;padding:20px;background-color:#f5f5f5;}
.container{background-color:white;padding:30px;border-radius:8px;
box-shadow:0 2px 4px rgba(0,0,0,0.1);}
h1{color:#2c3e50;border-bottom:2px solid #3498db;padding-bottom:10px;margin-bottom:20px;}
.stats{display:flex;gap:15px;flex-wrap:wrap;margin:15px 0;}
.stat{background:#f8f9fa;padding:12px 18px;border-radius:6px;border-left:4px solid #3498db;}
.stat strong{color:#2c3e50;}
.paper{background-color:#f8f9fa;padding:15px;border-left:4px solid #3498db;margin-bottom:15px;}
.paper p{margin:5px 0;}
a{color:#3498db;text-decoration:none;}
a:hover{text-decoration:underline;}
.footer{color:#7f8c8d;font-size:12px;margin-top:30px;}
</style>
</head>
<body>
<div class="container">
<h1>ArXiv 论文分析报告 - {date}</h1>
<div class="stats">
<div class="stat"><strong>{papers_count}</strong> 篇论文</div>
<div class="stat"><strong>{summaries_count}</strong> 篇已总结</div>
<div class="stat"><strong>{categories_count}</strong> 个类别</div>
</div>
{paper_html}
<div class="footer">
<p><a href="{report_link}">查看分析报告</a></p>
<p>这是一封自动发送的邮件，请勿回复。</p>
</div>
</div>
</body>
</html>
"""

_PAPER_TEMPLATE = """\
<div class="paper">
<h3><a href="{url}">{title}</a></h3>
<p><strong>{publication_date}</strong> | {categories} | {authors}</p>
<p>{summary}</p>
</div>
"""


class EmailNotifier:
    """Send the daily HTML report email with graceful degradation."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("email", {}) or {}
        load_dotenv()
        self._read_env()

    def _read_env(self) -> None:
        self.smtp_server = os.getenv("SMTP_SERVER", "").strip()
        self.smtp_port = int(os.getenv("SMTP_PORT", "587") or "587")
        self.smtp_username = os.getenv("SMTP_USERNAME", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_addr = os.getenv("EMAIL_FROM", "")
        self.to_addrs = [a.strip() for a in os.getenv("EMAIL_TO", "").split(",") if a.strip()]

    def configured(self) -> bool:
        """Whether all required SMTP fields are present."""
        return bool(
            self.smtp_server
            and self.smtp_username
            and self.smtp_password
            and self.from_addr
            and self.to_addrs
        )

    def send(
        self,
        date: str,
        papers: List[Dict[str, Any]],
        summaries: List[Dict[str, Any]],
        statistics: Optional[Dict[str, Any]] = None,
        report_link: str = "#",
    ) -> bool:
        """Build the HTML body and send the daily report email.

        Returns True only if the message was accepted and sent by the SMTP server.
        """
        if not self.config.get("enabled", True):
            logger.info("邮件功能在配置中已禁用，跳过发送")
            return False

        if not self.configured():
            logger.warning("SMTP/EMAIL 配置不完整，跳过发送邮件")
            return False

        html = self._build_html_body(date, papers, summaries, statistics, report_link)
        subject = f"ArXiv 论文分析报告 - {date}"

        message = MIMEMultipart()
        message["From"] = self.from_addr
        message["To"] = ", ".join(self.to_addrs)
        message["Subject"] = subject
        message.attach(MIMEText(html, "html", "utf-8"))

        try:
            context = ssl.create_default_context()
            if self.smtp_port == 465:
                with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=30, context=context) as server:
                    server.login(self.smtp_username, self.smtp_password)
                    server.send_message(message)
            else:
                with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                    server.starttls(context=context)
                    server.login(self.smtp_username, self.smtp_password)
                    server.send_message(message)
            logger.info("邮件发送成功，收件人: %s", ", ".join(self.to_addrs))
            return True
        except Exception as exc:  # noqa: BLE001 - send failure must not crash the pipeline
            logger.error("发送邮件失败: %s: %s", type(exc).__name__, exc)
            return False

    def _build_html_body(
        self,
        date: str,
        papers: List[Dict[str, Any]],
        summaries: List[Dict[str, Any]],
        statistics: Optional[Dict[str, Any]],
        report_link: str,
    ) -> str:
        summary_map = {s.get("id"): s.get("summary", "") for s in (summaries or [])}
        categories = set()
        blocks = []
        for paper in papers or []:
            paper_id = paper.get("id")
            categories.update(paper.get("categories", []) or [])
            blocks.append(_PAPER_TEMPLATE.format(
                url=paper.get("entry_url") or paper.get("pdf_url") or "#",
                title=paper.get("title", ""),
                publication_date=paper.get("published_date", ""),
                categories=", ".join(paper.get("categories", []) or []),
                authors=", ".join(paper.get("authors", []) or []) or "未知",
                summary=summary_map.get(paper_id) or "（暂无摘要）",
            ))

        stats = statistics or {}
        paper_html = "\n".join(blocks) or "<p>暂无论文总结。</p>"
        return _HTML_TEMPLATE.format(
            date=date,
            papers_count=stats.get("total_papers", len(papers or [])),
            summaries_count=sum(1 for s in summaries or [] if s.get("summary")),
            categories_count=stats.get("categories_count", len(categories)),
            paper_html=paper_html,
            report_link=report_link or "#",
        )