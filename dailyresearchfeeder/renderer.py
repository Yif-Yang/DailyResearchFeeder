from __future__ import annotations

import html
from zoneinfo import ZoneInfo

from dailyresearchfeeder.config import Settings
from dailyresearchfeeder.models import CandidateItem, DailyDigest, ItemKind


PAPER_HEADLINE_LIMIT = 5
NEWS_HEADLINE_LIMIT = 5

# ── Colour tokens (no CSS variables – email-safe) ──────────────────
_C = dict(
    bg="#f0f4f8",
    card="#ffffff",
    card_alt="#f7f9fc",
    text="#1e293b",
    muted="#64748b",
    border="#e2e8f0",
    primary="#4f46e5",       # indigo – papers
    primary_light="#eef2ff",
    accent="#059669",        # emerald – news
    accent_light="#ecfdf5",
    warn="#d97706",          # amber – watch
    warn_light="#fffbeb",
    headline="#dc2626",
    headline_light="#fef2f2",
    link="#4338ca",
    link_hover="#3730a3",
    grade_s="#7c3aed",       # violet
    grade_s_bg="#f5f3ff",
    grade_a="#2563eb",       # blue
    grade_a_bg="#eff6ff",
    grade_b="#0891b2",       # cyan
    grade_b_bg="#ecfeff",
    grade_c="#6b7280",       # gray
    grade_c_bg="#f9fafb",
)

_FONT = '"Inter", "SF Pro Display", "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif'


def render_digest_html(digest: DailyDigest, settings: Settings) -> str:
    local_time = digest.generated_at.astimezone(ZoneInfo(settings.timezone))
    overview = _paragraphize(digest.overview)
    takeaways_html = "".join(
        f'<li style="margin:6px 0;padding-left:4px;">{html.escape(t)}</li>'
        for t in digest.takeaways
    )

    paper_watch = [i for i in digest.watchlist if i.kind == ItemKind.PAPER]
    news_watch_all = [i for i in digest.watchlist if i.kind != ItemKind.PAPER]
    internet_watch = [i for i in news_watch_all if i.source_group == "internet_insights"]
    news_watch = [i for i in news_watch_all if i.source_group != "internet_insights"]
    internet_picks = [i for i in digest.news_picks if i.source_group == "internet_insights"]
    news_only_picks = [i for i in digest.news_picks if i.source_group != "internet_insights"]
    paper_headlines, paper_related = _split_primary(digest.paper_picks, PAPER_HEADLINE_LIMIT)
    news_headlines, news_related = _split_primary(news_only_picks, NEWS_HEADLINE_LIMIT)
    internet_headlines, internet_related = _split_primary(internet_picks, NEWS_HEADLINE_LIMIT)

    # ── Stats row (table for email compat) ──
    stats = [
        (digest.stats.get("fetched", 0), "原始抓取"),
        (digest.stats.get("after_seen_filter", 0), "去重过滤"),
        (digest.stats.get("keyword_hits", 0), "关键词命中"),
        (digest.stats.get("review_candidates", 0), "模型评审"),
        (len(digest.paper_picks), "论文推荐"),
        (len(digest.news_picks), "新闻推荐"),
    ]
    stat_cells = "".join(
        f'<td style="text-align:center;padding:14px 8px;background:{_C["card"]};'
        f'border:1px solid {_C["border"]};border-radius:12px;">'
        f'<div style="font-size:26px;font-weight:800;color:{_C["primary"]};line-height:1.2;">{v}</div>'
        f'<div style="font-size:12px;color:{_C["muted"]};margin-top:4px;letter-spacing:0.02em;">{l}</div>'
        f"</td>"
        for v, l in stats
    )

    date_str = local_time.strftime("%Y 年 %m 月 %d 日")
    weekday_zh = "一二三四五六日"[local_time.weekday()]

    return f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{html.escape(digest.subject)}</title>
<!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
<style>
  /* ── Web-only enhancements (email clients may strip) ── */
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 0;
    background: {_C["bg"]};
    -webkit-text-size-adjust: 100%;
    -ms-text-size-adjust: 100%;
  }}
  a {{ color: {_C["link"]}; }}
  a:hover {{ color: {_C["link_hover"]}; }}
  @media only screen and (max-width: 680px) {{
    .shell {{ width: 100% !important; border-radius: 0 !important; }}
    .hero-inner {{ padding: 28px 20px 22px !important; }}
    .sec {{ padding: 20px 18px 8px !important; }}
    .grp {{ padding: 0 18px 8px !important; }}
    .card-inner {{ padding: 18px !important; }}
    h1 {{ font-size: 26px !important; }}
    .stat-table td {{ display: block !important; width: 100% !important; margin-bottom: 8px; }}
    .brief-table td {{ display: block !important; width: 100% !important; margin-bottom: 12px; }}
    .ftr {{ padding: 18px !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:{_C["bg"]};font-family:{_FONT};color:{_C["text"]};line-height:1.65;-webkit-font-smoothing:antialiased;">

<!-- Outer wrapper for background -->
<div style="background:{_C["bg"]};padding:24px 12px;min-height:100%;">

<!-- Shell -->
<div class="shell" style="max-width:720px;margin:0 auto;background:{_C["card"]};border-radius:20px;overflow:hidden;box-shadow:0 4px 24px rgba(15,23,42,0.06),0 1px 3px rgba(15,23,42,0.08);">

  <!-- ════════ HERO ════════ -->
  <div style="background:linear-gradient(135deg,{_C["primary"]} 0%,#6366f1 50%,#818cf8 100%);padding:0;">
    <div class="hero-inner" style="padding:42px 36px 32px;">
      <div style="display:inline-block;background:rgba(255,255,255,0.18);border-radius:999px;padding:5px 14px;font-size:12px;font-weight:700;color:#ffffff;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:16px;">
        DAILY RESEARCH FEEDER
      </div>
      <h1 style="margin:0;font-size:32px;font-weight:900;color:#ffffff;line-height:1.15;letter-spacing:-0.02em;">
        {date_str}（周{weekday_zh}）
      </h1>
      <p style="margin:12px 0 0;font-size:15px;color:rgba(255,255,255,0.78);font-weight:500;">
        AI 驱动 · 论文 &amp; 新闻分层整理 · 头条优先级排序
      </p>
    </div>
  </div>

  <!-- ════════ OVERVIEW ════════ -->
  <div class="sec" style="padding:28px 32px 12px;">
    <h2 style="margin:0 0 16px;font-size:22px;font-weight:800;color:{_C["text"]};letter-spacing:-0.01em;">
      📋 今日总览
    </h2>
    <div style="background:{_C["card_alt"]};border:1px solid {_C["border"]};border-radius:16px;padding:22px 24px;">
      <div style="font-size:15px;color:{_C["text"]};line-height:1.75;">{overview}</div>
      <ul style="margin:16px 0 0;padding-left:20px;font-size:15px;color:{_C["text"]};">
        {takeaways_html}
      </ul>
    </div>
    <!-- Stats -->
    <table class="stat-table" width="100%" cellpadding="0" cellspacing="6" border="0" style="margin-top:18px;border-collapse:separate;">
      <tr>{stat_cells}</tr>
    </table>
  </div>

  <!-- ════════ QUICK CONCLUSIONS ════════ -->
  <div class="sec" style="padding:28px 32px 12px;">
    <h2 style="margin:0 0 16px;font-size:22px;font-weight:800;color:{_C["text"]};">
      ⚡ 带出处的快速结论
    </h2>
    <table class="brief-table" width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr>
        <td style="width:50%;padding-right:8px;vertical-align:top;">
          {_render_brief_card('paper', '📄 论文结论', digest.paper_picks, '今天没有达到阈值的论文结论。')}
        </td>
        <td style="width:50%;padding-left:8px;vertical-align:top;">
          {_render_brief_card('news', '📰 新闻结论', digest.news_picks, '今天没有达到阈值的新闻结论。')}
        </td>
      </tr>
    </table>
  </div>

  <!-- ════════ PAPERS ════════ -->
  <div class="sec" style="padding:28px 32px 6px;">
    <h2 style="margin:0;font-size:22px;font-weight:800;color:{_C["text"]};">📄 论文情报</h2>
  </div>
  <div class="grp" style="padding:0 32px 12px;">
    {_section_label('🏆', 'Top {len(paper_headlines)}', '论文头条')}
    {_render_cards(paper_headlines, variant='paper', empty_label='今天没有形成论文头条。')}
  </div>
  <div class="grp" style="padding:0 32px 12px;">
    {_section_label('📎', '', '论文相关')}
    {_render_cards(paper_related, variant='paper', empty_label='今天没有额外高相关论文。')}
  </div>
  <div class="grp" style="padding:0 32px 12px;">
    {_section_label('👀', '', '论文可能感兴趣')}
    {_render_cards(paper_watch, variant='watch', empty_label='今天没有额外保留的论文观察项。')}
  </div>

  <!-- ════════ NEWS ════════ -->
  <div class="sec" style="padding:28px 32px 6px;">
    <h2 style="margin:0;font-size:22px;font-weight:800;color:{_C["text"]};">📰 新闻情报</h2>
  </div>
  <div class="grp" style="padding:0 32px 12px;">
    {_section_label('🔥', 'Top {len(news_headlines)}', '新闻头条')}
    {_render_cards(news_headlines, variant='news', empty_label='今天没有形成新闻头条。')}
  </div>
  <div class="grp" style="padding:0 32px 12px;">
    {_section_label('📎', '', '新闻相关')}
    {_render_cards(news_related, variant='news', empty_label='今天没有额外高相关新闻。')}
  </div>
  <div class="grp" style="padding:0 32px 12px;">
    {_section_label('👀', '', '新闻可能感兴趣')}
    {_render_cards(news_watch, variant='watch', empty_label='今天没有额外保留的新闻观察项。')}
  </div>

  <!-- ════════ INTERNET INSIGHTS ════════ -->
  <div class="sec" style="padding:28px 32px 6px;">
    <h2 style="margin:0;font-size:22px;font-weight:800;color:{_C["text"]};">🌐 互联网观察</h2>
    <p style="margin:6px 0 0;font-size:13px;color:{_C["muted"]};">来自 Hacker News 首页 &amp; GitHub 新热门仓库，用于捕捉论文/新闻之外的社区信号。</p>
  </div>
  <div class="grp" style="padding:0 32px 12px;">
    {_section_label('⭐', 'Top {len(internet_headlines)}', '互联网头条')}
    {_render_cards(internet_headlines, variant='news', empty_label='今天没有形成互联网头条。')}
  </div>
  <div class="grp" style="padding:0 32px 12px;">
    {_section_label('📎', '', '互联网相关')}
    {_render_cards(internet_related, variant='news', empty_label='今天没有额外的互联网条目。')}
  </div>
  <div class="grp" style="padding:0 32px 12px;">
    {_section_label('👀', '', '互联网观察项')}
    {_render_cards(internet_watch, variant='watch', empty_label='今天没有额外的互联网观察项。')}
  </div>

  <!-- ════════ FOOTER ════════ -->
  <div class="ftr" style="padding:24px 32px 30px;text-align:center;border-top:1px solid {_C["border"]};">
    <div style="font-size:12px;color:{_C["muted"]};line-height:1.8;">
      关键词: {html.escape(', '.join(digest.keywords))}<br>
      由 <strong>Daily Research Feeder</strong> 自动生成 · 使用 GPT 驱动
    </div>
  </div>

</div>
<!-- /Shell -->

</div>
<!-- /Outer -->

</body>
</html>"""


# ── helpers ─────────────────────────────────────────────────────────

def _split_primary(items: list[CandidateItem], limit: int) -> tuple[list[CandidateItem], list[CandidateItem]]:
    return items[:limit], items[limit:]


def _section_label(emoji: str, badge_text: str, title: str) -> str:
    badge = ""
    if badge_text:
        badge = (
            f'<span style="display:inline-block;background:{_C["headline_light"]};color:{_C["headline"]};'
            f'font-size:11px;font-weight:800;padding:3px 10px;border-radius:999px;margin-right:8px;'
            f'letter-spacing:0.03em;">{html.escape(badge_text)}</span>'
        )
    return (
        f'<div style="margin:0 0 14px;font-size:17px;font-weight:800;color:{_C["text"]};">'
        f'{emoji} {badge}{html.escape(title)}'
        f'</div>'
    )


def _render_brief_card(kind: str, title: str, items: list[CandidateItem], empty_label: str) -> str:
    accent = _C["primary"] if kind == "paper" else _C["accent"]
    accent_light = _C["primary_light"] if kind == "paper" else _C["accent_light"]
    if not items:
        body = f'<p style="font-size:14px;color:{_C["muted"]};margin:8px 0 0;">{html.escape(empty_label)}</p>'
    else:
        lines = []
        for item in items[:3]:
            summary = item.importance or item.digest_summary or item.summary or item.title
            lines.append(
                f'<li style="margin:10px 0;font-size:14px;line-height:1.6;">'
                f'<a href="{html.escape(item.url)}" style="color:{_C["link"]};text-decoration:none;font-weight:700;">'
                f'{html.escape(item.title)}</a><br>'
                f'<span style="color:{_C["text"]};">{html.escape(summary)}</span><br>'
                f'<span style="color:{_C["muted"]};font-size:12px;">'
                f'via {html.escape(item.source_name)}</span>'
                f"</li>"
            )
        body = f'<ul style="margin:8px 0 0;padding-left:18px;">{"".join(lines)}</ul>'
    return (
        f'<div style="background:{accent_light};border:1px solid {_C["border"]};'
        f'border-top:4px solid {accent};border-radius:14px;padding:18px 20px;">'
        f'<div style="font-size:16px;font-weight:800;color:{_C["text"]};margin:0 0 4px;">{html.escape(title)}</div>'
        f'{body}'
        f'</div>'
    )


def _render_cards(items: list[CandidateItem], variant: str, empty_label: str) -> str:
    if not items:
        return (
            f'<div style="background:{_C["card_alt"]};border:2px dashed {_C["border"]};'
            f'border-radius:14px;padding:18px 22px;color:{_C["muted"]};font-size:14px;">'
            f'{html.escape(empty_label)}</div>'
        )
    return "".join(_render_card(item, variant) for item in items)


def _render_card(item: CandidateItem, variant: str) -> str:
    # pick accent colour
    if variant == "news":
        bar_color, badge_bg, badge_fg = _C["accent"], _C["accent_light"], _C["accent"]
    elif variant == "watch":
        bar_color, badge_bg, badge_fg = _C["warn"], _C["warn_light"], _C["warn"]
    else:
        bar_color, badge_bg, badge_fg = _C["primary"], _C["primary_light"], _C["primary"]

    authors = ", ".join(item.authors[:6]) if item.authors else "—"
    pub_text = item.published_at.strftime("%Y-%m-%d %H:%M UTC") if item.published_at else ""
    kind_label = {
        ItemKind.PAPER: "论文", ItemKind.BLOG: "博客",
        ItemKind.SOCIAL: "社交", ItemKind.RELEASE: "发布",
    }[item.kind]

    grade, grade_fg, grade_bg = _score_grade(item.relevance_score)

    # tags
    tags_html = "".join(
        f'<span style="display:inline-block;margin:0 6px 6px 0;padding:3px 10px;'
        f'border-radius:999px;background:#eef2ff;color:#4338ca;font-size:12px;font-weight:600;">'
        f'{html.escape(t)}</span>'
        for t in item.matched_keywords[:6]
    )

    # body
    body_parts = []
    summary_text = item.digest_summary or item.summary or item.title
    body_parts.append(
        f'<div style="font-size:14px;color:{_C["text"]};line-height:1.7;margin-top:14px;">'
        f'{html.escape(summary_text)}</div>'
    )
    if item.importance:
        body_parts.append(
            f'<div style="margin-top:10px;padding:12px 16px;background:#faf5ff;border-left:3px solid #a78bfa;'
            f'border-radius:0 10px 10px 0;font-size:14px;color:{_C["text"]};line-height:1.65;">'
            f'<strong style="color:#7c3aed;">💡 核心判断</strong><br>{html.escape(item.importance)}</div>'
        )
    if item.why_now:
        body_parts.append(
            f'<div style="margin-top:10px;padding:12px 16px;background:#eff6ff;border-left:3px solid #60a5fa;'
            f'border-radius:0 10px 10px 0;font-size:14px;color:{_C["text"]};line-height:1.65;">'
            f'<strong style="color:#2563eb;">⏰ 为什么现在值得看</strong><br>{html.escape(item.why_now)}</div>'
        )
    if item.reasoning:
        body_parts.append(
            f'<div style="margin-top:10px;font-size:13px;color:{_C["muted"]};line-height:1.65;">'
            f'<strong>补充说明：</strong>{html.escape(item.reasoning)}</div>'
        )
    body_html = "".join(body_parts)

    return f"""\
<div class="card-outer" style="margin-bottom:16px;background:{_C["card"]};border:1px solid {_C["border"]};border-left:5px solid {bar_color};border-radius:14px;overflow:hidden;box-shadow:0 1px 4px rgba(15,23,42,0.04);">
  <div class="card-inner" style="padding:22px 24px;">
    <!-- top row -->
    <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td style="vertical-align:top;">
        <div style="font-size:12px;font-weight:700;color:{_C["muted"]};letter-spacing:0.03em;text-transform:uppercase;">
          {html.escape(kind_label)} · {html.escape(item.source_name)}
        </div>
      </td>
      <td style="vertical-align:top;text-align:right;white-space:nowrap;">
        <span style="display:inline-block;padding:4px 12px;border-radius:999px;font-size:12px;font-weight:800;color:{grade_fg};background:{grade_bg};">
          {html.escape(grade)}
        </span>
      </td>
    </tr></table>
    <!-- title -->
    <div style="margin:10px 0 6px;font-size:20px;font-weight:800;line-height:1.3;">
      <a href="{html.escape(item.url)}" style="color:{_C["link"]};text-decoration:none;">{html.escape(item.title)}</a>
    </div>
    <!-- meta -->
    <div style="font-size:13px;color:{_C["muted"]};line-height:1.5;">
      {html.escape(authors)}{f' · {html.escape(pub_text)}' if pub_text else ''}
    </div>
    <div style="margin-top:4px;font-size:13px;color:{_C["muted"]};">
      相关度 {item.relevance_score:.1f}/10 · {html.escape(item.decision)}
    </div>
    <!-- body -->
    {body_html}
    <!-- tags -->
    <div style="margin-top:14px;">{tags_html}</div>
  </div>
</div>"""


def _score_grade(score: float) -> tuple[str, str, str]:
    """Return (label, text_color, bg_color)."""
    if score >= 9.2:
        return "S 级", _C["grade_s"], _C["grade_s_bg"]
    if score >= 8.4:
        return "A 级", _C["grade_a"], _C["grade_a_bg"]
    if score >= 7.4:
        return "B 级", _C["grade_b"], _C["grade_b_bg"]
    if score >= 6.4:
        return "C 级", _C["grade_c"], _C["grade_c_bg"]
    return "观察", _C["grade_c"], _C["grade_c_bg"]


def _paragraphize(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")
