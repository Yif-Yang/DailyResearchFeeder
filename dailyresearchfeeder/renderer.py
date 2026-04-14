from __future__ import annotations

import html
from zoneinfo import ZoneInfo

from dailyresearchfeeder.config import Settings
from dailyresearchfeeder.models import CandidateItem, DailyDigest, ItemKind


PAPER_HEADLINE_LIMIT = 5
NEWS_HEADLINE_LIMIT = 5


def render_digest_html(digest: DailyDigest, settings: Settings) -> str:
    local_time = digest.generated_at.astimezone(ZoneInfo(settings.timezone))
    overview = _paragraphize(digest.overview)
    takeaways = "".join(f"<li>{html.escape(item)}</li>" for item in digest.takeaways)

    paper_watch = [item for item in digest.watchlist if item.kind == ItemKind.PAPER]
    news_watch = [item for item in digest.watchlist if item.kind != ItemKind.PAPER]
    paper_headlines, paper_related = _split_primary(digest.paper_picks, PAPER_HEADLINE_LIMIT)
    news_headlines, news_related = _split_primary(digest.news_picks, NEWS_HEADLINE_LIMIT)

    return f"""<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>{html.escape(digest.subject)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f8fc;
      --card: #ffffff;
      --card-soft: #f8fbfe;
      --text: #16324a;
      --muted: #61788e;
      --line: #d3e1ed;
      --primary: #0d5e8c;
      --primary-soft: #e6f2fb;
      --accent: #177d61;
      --accent-soft: #e8f8f1;
      --warn: #b6781f;
      --warn-soft: #fff5df;
      --headline: #d14b1b;
      --headline-soft: #fff0e9;
      --shadow: rgba(15, 23, 42, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 24px 12px;
      background:
        radial-gradient(circle at top left, rgba(167, 243, 208, 0.22), transparent 30%),
        radial-gradient(circle at top right, rgba(147, 197, 253, 0.22), transparent 32%),
        linear-gradient(180deg, #eef5fb 0%, var(--bg) 100%);
      color: var(--text);
      font-family: \"Segoe UI\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif;
      line-height: 1.7;
    }}
    .shell {{
      max-width: 1080px;
      margin: 0 auto;
      background: rgba(255, 255, 255, 0.92);
      border: 1px solid rgba(211, 225, 237, 0.95);
      box-shadow: 0 18px 64px var(--shadow);
      border-radius: 28px;
      overflow: hidden;
    }}
    .hero {{
      padding: 38px 30px 28px;
      background: linear-gradient(135deg, #eaf6ff 0%, #f9fcff 58%, #eefcf5 100%);
      border-bottom: 1px solid var(--line);
    }}
    .hero h1 {{
      margin: 0;
      font-size: 40px;
      line-height: 1.05;
      color: var(--primary);
      letter-spacing: -0.03em;
    }}
    .hero .meta {{
      margin-top: 14px;
      color: var(--muted);
      font-size: 18px;
      font-weight: 700;
    }}
    .hero .sub {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 15px;
    }}
    .section {{ padding: 28px 28px 10px; }}
    .section h2 {{
      margin: 0 0 14px;
      font-size: 28px;
      color: var(--text);
      letter-spacing: -0.02em;
    }}
    .section h3 {{
      margin: 0 0 12px;
      font-size: 22px;
      color: var(--text);
    }}
    .summary-box {{
      background: linear-gradient(180deg, #ffffff 0%, #f7fbfe 100%);
      border: 1px solid #cfe0ee;
      border-radius: 22px;
      padding: 22px;
    }}
    .summary-box p {{ margin: 0; font-size: 18px; }}
    .summary-box ul {{ margin: 16px 0 0; padding-left: 22px; }}
    .summary-box li {{ margin: 8px 0; }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .stat {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 16px;
    }}
    .stat strong {{ display: block; font-size: 28px; color: var(--primary); }}
    .stat span {{ color: var(--muted); font-size: 14px; }}
    .brief-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 14px;
    }}
    .brief-card {{
      background: var(--card-soft);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px 18px 12px;
    }}
    .brief-card.paper {{ border-top: 5px solid var(--primary); }}
    .brief-card.news {{ border-top: 5px solid var(--accent); }}
    .brief-card ul {{ margin: 0; padding-left: 20px; }}
    .brief-card li {{ margin: 10px 0; }}
    .brief-card a {{ color: #1a51cf; text-decoration: none; }}
    .brief-card a:hover {{ text-decoration: underline; }}
    .group {{ padding: 0 28px 8px; }}
    .group-title {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin: 0 0 12px;
      font-size: 21px;
      font-weight: 800;
      color: var(--text);
    }}
    .group-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 5px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 800;
      color: var(--headline);
      background: var(--headline-soft);
    }}
    .cards {{ display: grid; gap: 16px; }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-left: 6px solid var(--primary);
      border-radius: 18px;
      padding: 22px;
      box-shadow: 0 8px 22px rgba(15, 23, 42, 0.04);
    }}
    .card.news {{ border-left-color: var(--accent); }}
    .card.watch {{ border-left-color: var(--warn); }}
    .card-top {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .eyebrow {{ font-size: 14px; color: var(--muted); font-weight: 700; }}
    .grade {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 44px;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 900;
      color: var(--primary);
      background: var(--primary-soft);
    }}
    .grade.news {{ color: var(--accent); background: var(--accent-soft); }}
    .grade.watch {{ color: var(--warn); background: var(--warn-soft); }}
    .title {{ margin: 10px 0 8px; font-size: 28px; line-height: 1.25; }}
    .title a {{ color: #1b4fd1; text-decoration: none; }}
    .title a:hover {{ text-decoration: underline; }}
    .meta-line {{ color: var(--muted); font-size: 15px; }}
    .source-link {{ margin-top: 8px; font-size: 14px; color: var(--muted); }}
    .source-link a {{ color: #2455b3; text-decoration: none; }}
    .source-link a:hover {{ text-decoration: underline; }}
    .score-line {{ margin-top: 14px; font-size: 14px; font-weight: 700; color: var(--muted); }}
    .body-copy {{ margin-top: 14px; font-size: 17px; color: var(--text); }}
    .body-copy p {{ margin: 0 0 12px; }}
    .keywords {{ margin-top: 12px; }}
    .tag {{
      display: inline-block;
      margin: 0 8px 8px 0;
      padding: 5px 10px;
      border-radius: 999px;
      background: #f0f7ff;
      color: #315d7c;
      font-size: 13px;
      font-weight: 700;
    }}
    .empty {{
      background: var(--card-soft);
      border: 1px dashed var(--line);
      border-radius: 18px;
      padding: 16px 18px;
      color: var(--muted);
      font-size: 15px;
    }}
    .footer {{
      padding: 18px 28px 30px;
      color: var(--muted);
      font-size: 14px;
      text-align: center;
    }}
    @media (max-width: 720px) {{
      .hero h1 {{ font-size: 32px; }}
      .title {{ font-size: 23px; }}
      .section, .group, .footer {{ padding-left: 16px; padding-right: 16px; }}
    }}
  </style>
</head>
<body>
  <div class=\"shell\">
    <div class=\"hero\">
      <h1>Daily Research Feeder</h1>
      <div class=\"meta\">{local_time:%Y年%m月%d日} · 北京时间日报</div>
      <div class=\"sub\">默认 GPT-5.4 · 论文与新闻分层整理 · 头条优先级排序</div>
    </div>

    <div class=\"section\">
      <h2>今日总览</h2>
      <div class=\"summary-box\">
        <p>{overview}</p>
        <ul>{takeaways}</ul>
        <div class=\"stats\">
          <div class=\"stat\"><strong>{digest.stats.get('fetched', 0)}</strong><span>原始抓取条目</span></div>
          <div class=\"stat\"><strong>{digest.stats.get('after_seen_filter', 0)}</strong><span>去重与历史过滤后</span></div>
          <div class=\"stat\"><strong>{digest.stats.get('keyword_hits', 0)}</strong><span>关键词或语义命中</span></div>
          <div class=\"stat\"><strong>{digest.stats.get('review_candidates', 0)}</strong><span>进入模型评审</span></div>
          <div class=\"stat\"><strong>{len(digest.paper_picks)}</strong><span>正式论文推荐</span></div>
          <div class=\"stat\"><strong>{len(digest.news_picks)}</strong><span>正式新闻推荐</span></div>
        </div>
      </div>
    </div>

    <div class=\"section\">
      <h2>带出处的快速结论</h2>
      <div class=\"brief-grid\">
        {_render_brief_card('paper', '论文结论', digest.paper_picks, '今天没有达到阈值的论文结论。')}
        {_render_brief_card('news', '新闻结论', digest.news_picks, '今天没有达到阈值的新闻结论。')}
      </div>
    </div>

    <div class=\"section\"><h2>论文情报</h2></div>
    <div class=\"group\">
      <div class=\"group-title\"><span class=\"group-badge\">Top 5</span>论文头条</div>
      <div class=\"cards\">{_render_cards(paper_headlines, variant='paper', empty_label='今天没有形成论文头条。')}</div>
    </div>
    <div class=\"group\">
      <div class=\"group-title\">论文相关</div>
      <div class=\"cards\">{_render_cards(paper_related, variant='paper', empty_label='今天没有额外高相关论文。')}</div>
    </div>
    <div class=\"group\">
      <div class=\"group-title\">论文可能感兴趣</div>
      <div class=\"cards\">{_render_cards(paper_watch, variant='watch', empty_label='今天没有额外保留的论文观察项。')}</div>
    </div>

    <div class=\"section\"><h2>新闻情报</h2></div>
    <div class=\"group\">
      <div class=\"group-title\"><span class=\"group-badge\">Top 5</span>新闻头条</div>
      <div class=\"cards\">{_render_cards(news_headlines, variant='news', empty_label='今天没有形成新闻头条。')}</div>
    </div>
    <div class=\"group\">
      <div class=\"group-title\">新闻相关</div>
      <div class=\"cards\">{_render_cards(news_related, variant='news', empty_label='今天没有额外高相关新闻。')}</div>
    </div>
    <div class=\"group\">
      <div class=\"group-title\">新闻可能感兴趣</div>
      <div class=\"cards\">{_render_cards(news_watch, variant='watch', empty_label='今天没有额外保留的新闻观察项。')}</div>
    </div>

    <div class=\"footer\">
      关键词: {html.escape(', '.join(digest.keywords))}<br>
      本邮件由 Daily Research Feeder 自动生成。
    </div>
  </div>
</body>
</html>
"""


def _split_primary(items: list[CandidateItem], headline_limit: int) -> tuple[list[CandidateItem], list[CandidateItem]]:
    return items[:headline_limit], items[headline_limit:]


def _render_brief_card(kind: str, title: str, items: list[CandidateItem], empty_label: str) -> str:
    if not items:
        body = f"<p>{html.escape(empty_label)}</p>"
    else:
        lines = []
        for item in items[:3]:
            citation = f"{item.source_name} | {item.url}"
            summary = item.importance or item.digest_summary or item.summary or item.title
            lines.append(
                "<li>"
                f"<strong>{html.escape(item.title)}</strong><br>"
                f"{html.escape(summary)}<br>"
                f"<span style=\"color:#61788e;font-size:13px;\">出处：<a href=\"{html.escape(item.url)}\">{html.escape(citation)}</a></span>"
                "</li>"
            )
        body = f"<ul>{''.join(lines)}</ul>"
    return f"<div class=\"brief-card {kind}\"><h3>{html.escape(title)}</h3>{body}</div>"


def _render_cards(items: list[CandidateItem], variant: str, empty_label: str) -> str:
    if not items:
        return f'<div class=\"empty\">{html.escape(empty_label)}</div>'
    return "".join(_render_card(item, variant) for item in items)


def _render_card(item: CandidateItem, variant: str) -> str:
    authors = ", ".join(item.authors[:6]) if item.authors else "未知"
    published_text = item.published_at.strftime("%Y-%m-%d %H:%M UTC") if item.published_at else "unknown time"
    tags = "".join(f'<span class=\"tag\">{html.escape(tag)}</span>' for tag in item.matched_keywords[:6])
    grade = _score_grade(item.relevance_score)
    kind_label = {
        ItemKind.PAPER: "论文",
        ItemKind.BLOG: "博客",
        ItemKind.SOCIAL: "社交",
        ItemKind.RELEASE: "发布",
    }[item.kind]

    body_segments = [f"<p>{html.escape(item.digest_summary or item.summary or item.title)}</p>"]
    if item.importance:
        body_segments.append(f"<p><strong>核心判断：</strong>{html.escape(item.importance)}</p>")
    if item.why_now:
        body_segments.append(f"<p><strong>为什么现在值得看：</strong>{html.escape(item.why_now)}</p>")
    if item.reasoning:
        body_segments.append(f"<p><strong>补充说明：</strong>{html.escape(item.reasoning)}</p>")

    grade_class = "news" if variant == "news" else "watch" if variant == "watch" else "paper"
    return f"""
    <div class=\"card {variant}\">
      <div class=\"card-top\">
        <div class=\"eyebrow\">{html.escape(kind_label)} · {html.escape(item.source_name)} · {html.escape(item.source_group)}</div>
        <div class=\"grade {grade_class}\">{html.escape(grade)}</div>
      </div>
      <div class=\"title\"><a href=\"{html.escape(item.url)}\">{html.escape(item.title)}</a></div>
      <div class=\"meta-line\">作者/来源: {html.escape(authors)} · 时间: {html.escape(published_text)}</div>
      <div class=\"source-link\">出处: <a href=\"{html.escape(item.url)}\">{html.escape(item.url)}</a></div>
      <div class=\"score-line\">重要度与相关度排序分数: {item.relevance_score:.1f}/10 · 决策: {html.escape(item.decision)}</div>
      <div class=\"body-copy\">{''.join(body_segments)}</div>
      <div class=\"keywords\">{tags}</div>
    </div>
    """



def _score_grade(score: float) -> str:
    if score >= 9.2:
        return "S 级"
    if score >= 8.4:
        return "A 级"
    if score >= 7.4:
        return "B 级"
    if score >= 6.4:
        return "C 级"
    return "观察"



def _paragraphize(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")
