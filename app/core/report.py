"""
Soclytics — Full PDF / JSON intelligence report (no LLM).
Mirrors analysis UI coverage: about, posts, interactors, Top-7,
co-comment network, timeline, comments sample, face clusters.
Telegram also includes ConvoMetrics-style activity / word / search sections.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core.scoring import (
    get_all_interactors,
    get_cocomment_graph,
    get_interaction_timeline,
    get_post_type_counts,
    get_profile_summary,
    get_top7,
)

# core/ is under app/; reports + icons live next to platform DBs
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(APP_DIR, "reports")
_LOGO_PNG = os.path.join(APP_DIR, "icons", "logo.png")
_LOGO_JPEG = os.path.join(APP_DIR, "icons", "logo.jpeg")
LOGO_PATH = _LOGO_PNG if os.path.isfile(_LOGO_PNG) else _LOGO_JPEG

W, H = A4

C_WHITE = colors.white
C_DARK = colors.HexColor("#1a1a2e")
C_ACCENT = colors.HexColor("#c0392b")
C_ACCENT2 = colors.HexColor("#2c3e50")
C_LIGHT_BG = colors.HexColor("#f8f9fa")
C_LIGHT_BG2 = colors.HexColor("#eef0f2")
C_BORDER = colors.HexColor("#dee2e6")
C_TEXT = colors.HexColor("#212529")
C_SUBTEXT = colors.HexColor("#6c757d")
C_DASH_BG = colors.HexColor("#1a1a1d")
C_DASH_ELEV = colors.HexColor("#141416")
C_DASH_GOLD = colors.HexColor("#f4c46b")
C_DASH_FAINT = colors.HexColor("#8a8a92")
C_DASH_BORDER = colors.HexColor("#2a2a2e")
_DASH_BG = "#1a1a1d"
_DASH_ELEV = "#141416"
_DASH_TEXT = "#c0c0c8"
_DASH_FAINT = "#8a8a92"
_DASH_TITLE = "#f5f5f7"
_DASH_BORDER = "#2a2a2e"
_DASH_LIKE = "#f91880"
_DASH_COMMENT = "#1d9bf0"
_DASH_REPOST = "#00ba7c"

# Short meaning blurbs under every report title so a reader knows what
# each heading is for without opening the analysis UI.
SECTION_MEANINGS = {
    "cover": (
        "Cover sheet identifying the investigation subject, source profile URL, "
        "internal case id, when data was scraped, and when this report was generated."
    ),
    "subject": "Display name of the target account, channel, group or chat under investigation.",
    "profile": "Canonical public URL (or synthetic URI) used as the collection key.",
    "case_id": "Internal Soclytics case number for this profile row in the local database.",
    "scraped": "Timestamp of the collection run that produced the data in this report.",
    "generated": "UTC time this PDF/DOCX file was written — may be later than the scrape.",
    "locked": "Whether the source surface was restricted / private at collection time.",
    "00": (
        "Formal executive briefing: overview and objectives, collection outcomes, "
        "content and network findings, limitations, and recommended follow-up. "
        "Prose is composed from local metrics only — no LLM narrative."
    ),
    "01": (
        "High-level snapshot of everything collected for this subject. Counts match the "
        "analysis console: posts by type, unique interactors, total interactions, face "
        "clusters and how many Top-7 slots are filled."
    ),
    "01_x": (
        "High-level snapshot of collected X.com statuses. Header counts are the tweet "
        "inventory plus summed Reply, Repost, Like and View figures shown on each post."
    ),
    "about": (
        "Structured profile fields scraped from the target (biography, members, admins, "
        "active participants, verification flags, etc.). Labels and sections come from "
        "the platform collector."
    ),
    "posts_stat": "Total photo + reel + text items stored for this profile.",
    "photos_stat": "Image / photo posts (or media messages) downloaded or referenced.",
    "reels_stat": "Short-video / reel items (thumbnails only for large Telegram videos).",
    "text_stat": "Text-only posts or day-thread transcripts without a primary image.",
    "interactors_stat": "Distinct people or accounts that interacted with the subject’s content.",
    "comments_stat": "Total interaction rows (comments, messages, reactions, forwards, mentions).",
    "faces_stat": "Unique face identities clustered by the local CNN/HOG pipeline.",
    "top7_stat": "How many of the seven highest-frequency interactor slots are occupied.",
    "02": (
        "Shows how interactors relate to each other through shared activity. Two people "
        "form an edge when they appear on the same post (co-comment / co-occurrence). "
        "Dense clusters often indicate coordinated groups or recurring discussion circles."
    ),
    "matrix": (
        "Heatmap of shared-post counts between the most active interactors. Darker cells "
        "mean more posts where both people appear. The threshold filters out weak one-off pairs."
    ),
    "force": (
        "Force-directed graph of the same co-occurrence network. Node size reflects "
        "activity; edge thickness reflects how often a pair co-appears. Useful to spot hubs."
    ),
    "pairs": (
        "Ranked table of the strongest interactor pairs and how many posts they share. "
        "Read this when you need exact names and weights instead of the chart."
    ),
    "03": (
        "Complete roster of every interactor seen on this profile, ranked by total "
        "interaction frequency. Ph / Re / Tx break the count down by photo, reel and "
        "text posts. Use this as the master identity list for follow-up."
    ),
    "04": (
        "The seven highest-frequency interactors with any scraped about-metadata. "
        "These are the priority persons of interest for deeper manual review."
    ),
    "05": (
        "Inventory of every collected post item — photos, reels and text — with dates, "
        "captions/URLs and how many interactions were attached to each."
    ),
    "photos_posts": "Individual photo or image posts used for media review and face clustering.",
    "reels_posts": "Short-form video posts; local copies are usually thumbnails, not full video files.",
    "text_posts": (
        "Text posts or aggregated day transcripts (e.g. Telegram group day threads). "
        "Interactors listed on a day thread co-occurred in that day’s conversation."
    ),
    "x_posts": (
        "X.com posts in native engagement order: the tweet text/media plus Reply, "
        "Repost, Like and View counts scraped from each status."
    ),
    "06": (
        "Sample of stored comment / message text with author and post type. Empty stubs "
        "are omitted. Useful for tone, language, slogans and named references."
    ),
    "07": (
        "Activity over time: how many interactions fall on each dated post day, split by "
        "photo / reel / text. Spikes mark campaigns, news events or coordinated bursts."
    ),
    "08": (
        "Message-level activity from captions, comments and day-thread transcripts "
        "(ConvoMetrics-style). Charts show volume by calendar day, weekday and hour."
    ),
    "08_engagement": (
        "Same Like / Comment / Repost series as the analysis dashboard Activity Timeline. "
        "Stacked charts by calendar day, weekday and hour."
    ),
    "09": (
        "Lexical fingerprint of the collected corpus after stopword filtering. Includes a "
        "visual word cloud plus ranked top-word tables to surface themes, slogans and jargon."
    ),
    "10": (
        "Who said the highest-frequency content words, with sample excerpts. "
        "Mirrors the analysis Word Searcher for the top corpus terms."
    ),
    "11": (
        "Faces automatically grouped across collected images. Each cluster is a likely "
        "unique person; appearance_count is how often that face was seen. Labels may be "
        "auto-assigned or left as Person N until an analyst names them."
    ),
    "12": (
        "Legal and operational limits of this report: open-source / session-authenticated "
        "data only, point-in-time, not legal advice, authorized use required."
    ),
}


def section_meaning(key: str) -> str:
    return SECTION_MEANINGS.get(key, "")


def _esc(text) -> str:
    if text is None:
        return ""
    s = str(text)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _safe_name(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (name or "profile").strip())[:80]
    return s or "profile"


def _clip(text, n=220) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _meaning_para(key: str, S):
    text = section_meaning(key)
    if not text:
        return None
    return Paragraph(_esc(text), S["meaning"])


def make_styles():
    return {
        "cover_title": ParagraphStyle(
            "cover_title", fontName="Helvetica-Bold", fontSize=28,
            textColor=C_DARK, alignment=TA_CENTER, spaceAfter=8, leading=34,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", fontName="Helvetica", fontSize=11,
            textColor=C_SUBTEXT, alignment=TA_CENTER, spaceAfter=4, leading=15,
        ),
        "section": ParagraphStyle(
            "section", fontName="Helvetica-Bold", fontSize=15,
            textColor=C_ACCENT, spaceBefore=6, spaceAfter=4, leading=19,
        ),
        "meaning": ParagraphStyle(
            "meaning", fontName="Helvetica-Oblique", fontSize=8.5,
            textColor=C_SUBTEXT, spaceAfter=6, leading=11,
        ),
        "sub": ParagraphStyle(
            "sub", fontName="Helvetica-Bold", fontSize=11,
            textColor=C_ACCENT2, spaceBefore=6, spaceAfter=2, leading=14,
        ),
        "body": ParagraphStyle(
            "body", fontName="Helvetica", fontSize=9,
            textColor=C_TEXT, spaceAfter=3, leading=12,
        ),
        "meta_l": ParagraphStyle(
            "meta_l", fontName="Helvetica-Bold", fontSize=9,
            textColor=C_ACCENT, alignment=TA_RIGHT,
        ),
        "meta_v": ParagraphStyle(
            "meta_v", fontName="Helvetica", fontSize=9,
            textColor=C_TEXT, alignment=TA_LEFT,
        ),
        "th": ParagraphStyle(
            "th", fontName="Helvetica-Bold", fontSize=8,
            textColor=C_WHITE, alignment=TA_CENTER, leading=10,
        ),
        "td": ParagraphStyle(
            "td", fontName="Helvetica", fontSize=7.5,
            textColor=C_TEXT, alignment=TA_LEFT, leading=10,
        ),
        "td_c": ParagraphStyle(
            "td_c", fontName="Helvetica", fontSize=7.5,
            textColor=C_TEXT, alignment=TA_CENTER, leading=10,
        ),
        "stat_l": ParagraphStyle(
            "stat_l", fontName="Helvetica-Bold", fontSize=7,
            textColor=C_SUBTEXT, alignment=TA_CENTER,
        ),
        "stat_v": ParagraphStyle(
            "stat_v", fontName="Helvetica-Bold", fontSize=16,
            textColor=C_DARK, alignment=TA_CENTER,
        ),
        "dash_stat_l": ParagraphStyle(
            "dash_stat_l", fontName="Helvetica-Bold", fontSize=8,
            textColor=C_DASH_FAINT, alignment=TA_CENTER,
        ),
        "dash_stat_v": ParagraphStyle(
            "dash_stat_v", fontName="Helvetica-Bold", fontSize=18,
            textColor=C_DASH_GOLD, alignment=TA_CENTER,
        ),
        "confidential": ParagraphStyle(
            "confidential", fontName="Helvetica-Bold", fontSize=10,
            textColor=C_ACCENT, alignment=TA_CENTER, spaceAfter=6,
        ),
    }


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(C_BORDER)
    canvas.line(16 * mm, 11 * mm, W - 16 * mm, 11 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(C_SUBTEXT)
    canvas.drawString(16 * mm, 6 * mm, "Soclytics · Full Report · No LLM")
    canvas.drawRightString(W - 16 * mm, 6 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _cover_canvas(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(C_WHITE)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    canvas.setFillColor(C_ACCENT)
    canvas.rect(0, H - 16 * mm, W, 16 * mm, fill=1, stroke=0)
    canvas.setFillColor(C_DARK)
    canvas.rect(0, 0, W, 12 * mm, fill=1, stroke=0)
    canvas.setFillColor(C_WHITE)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawCentredString(W / 2, H - 10 * mm, "CONFIDENTIAL · FOR AUTHORIZED USE ONLY")
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(W / 2, 4 * mm, "Generated locally · Soclytics")
    canvas.restoreState()


def _table_style(header=True):
    cmds = [
        ("GRID", (0, 0), (-1, -1), 0.3, C_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        cmds += [
            ("BACKGROUND", (0, 0), (-1, 0), C_DARK),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_LIGHT_BG2]),
        ]
    else:
        cmds.append(("ROWBACKGROUNDS", (0, 0), (-1, -1), [C_WHITE, C_LIGHT_BG2]))
    return TableStyle(cmds)


def _stat_box(label: str, value, S) -> Table:
    data = [
        [Paragraph(_esc(str(value)), S["stat_v"])],
        [Paragraph(_esc(label), S["stat_l"])],
    ]
    t = Table(data, colWidths=[36 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), C_LIGHT_BG),
                ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    return t


def _dashboard_stat_box(label: str, value, S) -> Table:
    data = [
        [Paragraph(_esc(str(value)), S["dash_stat_v"])],
        [Paragraph(_esc(label), S["dash_stat_l"])],
    ]
    t = Table(data, colWidths=[50 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), C_DASH_ELEV),
                ("BOX", (0, 0), (-1, -1), 0.6, C_DASH_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    return t


# ── data fetchers ─────────────────────────────────────────────────────────────

def _fetch_posts(db_file: str, profile_id: int) -> dict:
    con = sqlite3.connect(db_file)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute(
        """
        SELECT pp.id, pp.photo_url AS url, pp.date_text, pp.caption, pp.image_src,
               pp.scraped_at,
               COALESCE(pp.like_count, 0) AS like_count,
               COALESCE(pp.reply_count, 0) AS reply_count,
               COALESCE(pp.repost_count, 0) AS repost_count
        FROM photo_posts pp
        WHERE pp.profile_id = ?
        ORDER BY pp.id
        """,
        (profile_id,),
    )
    photos = [dict(r) for r in cur.fetchall()]

    cur.execute(
        """
        SELECT rp.id, rp.reel_url AS url, NULL AS date_text, NULL AS caption,
               NULL AS image_src, rp.scraped_at,
               COALESCE(rp.like_count, 0) AS like_count,
               COALESCE(rp.reply_count, 0) AS reply_count,
               COALESCE(rp.repost_count, 0) AS repost_count
        FROM reel_posts rp
        WHERE rp.profile_id = ?
        ORDER BY rp.id
        """,
        (profile_id,),
    )
    reels = [dict(r) for r in cur.fetchall()]

    text_cols = {r[1] for r in cur.execute("PRAGMA table_info(text_posts)")}
    caption_sql = "tp.body AS caption" if "body" in text_cols else "NULL AS caption"
    image_sql = (
        "tp.image_src" if "image_src" in text_cols else "tp.screenshot_path AS image_src"
    )
    cur.execute(
        f"""
        SELECT tp.id, tp.post_url AS url, tp.date_text, {caption_sql},
               {image_sql}, tp.scraped_at,
               COALESCE(tp.like_count, 0) AS like_count,
               COALESCE(tp.reply_count, 0) AS reply_count,
               COALESCE(tp.repost_count, 0) AS repost_count
        FROM text_posts tp
        WHERE tp.profile_id = ?
        ORDER BY tp.id
        """,
        (profile_id,),
    )
    texts = [dict(r) for r in cur.fetchall()]
    con.close()
    return {"photos": photos, "reels": reels, "texts": texts}


def _fetch_x_posts(db_file: str, profile_id: int) -> dict:
    """All X tweets from text_posts with native Reply / Repost / Like / View counts."""
    con = sqlite3.connect(db_file)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        """
        SELECT tp.id, tp.post_url AS url, tp.date_text, tp.body AS caption,
               tp.image_src, tp.media_type, tp.scraped_at,
               COALESCE(tp.like_count, 0) AS like_count,
               COALESCE(tp.reply_count, 0) AS reply_count,
               COALESCE(tp.repost_count, 0) AS repost_count,
               COALESCE(tp.view_count, 0) AS view_count
        FROM text_posts tp
        WHERE tp.profile_id = ?
        ORDER BY tp.id DESC
        """,
        (profile_id,),
    )
    texts = [dict(r) for r in cur.fetchall()]
    con.close()
    return {"photos": [], "reels": [], "texts": texts}


def _fetch_threads_posts(db_file: str, profile_id: int) -> dict:
    """Threads text_posts — same fields as /threads/api/text-posts."""
    con = sqlite3.connect(db_file)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    text_cols = {r[1] for r in cur.execute("PRAGMA table_info(text_posts)")}
    source_sql = (
        "COALESCE(tp.source_tab, 'threads') AS source_tab"
        if "source_tab" in text_cols
        else "'threads' AS source_tab"
    )
    media_sql = "tp.media_type" if "media_type" in text_cols else "NULL AS media_type"
    image_sql = (
        "tp.image_src" if "image_src" in text_cols else "tp.screenshot_path AS image_src"
    )
    cur.execute(
        f"""
        SELECT tp.id, tp.post_url AS url, tp.date_text, tp.body AS caption,
               {image_sql}, {media_sql}, tp.scraped_at,
               COALESCE(tp.like_count, 0) AS like_count,
               COALESCE(tp.reply_count, 0) AS reply_count,
               COALESCE(tp.repost_count, 0) AS repost_count,
               {source_sql}
        FROM text_posts tp
        WHERE tp.profile_id = ?
        ORDER BY tp.id DESC
        """,
        (profile_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    photos = [r for r in rows if r.get("media_type") in ("image", "video")]
    reels = [r for r in rows if r.get("media_type") == "video"]
    texts_only = [r for r in rows if (r.get("media_type") or "text") == "text"]
    return {"photos": photos, "reels": reels, "texts": rows, "text_only": texts_only}


THREADS_PROFILE_TABS = ("threads", "replies", "media", "reposts")


def _threads_tab_kind(row: dict) -> str:
    return row.get("source_tab") or "threads"


def _posts_for_threads_tab(rows: list, tab: str) -> list:
    """Mirror threads/analysis.html postsForTab()."""
    if tab == "replies":
        return [r for r in rows if _threads_tab_kind(r) == "replies"]
    if tab == "reposts":
        return [r for r in rows if _threads_tab_kind(r) == "reposts"]
    if tab == "media":
        return [
            r for r in rows
            if r.get("media_type") in ("image", "video")
            and _threads_tab_kind(r) != "reposts"
        ]
    return [r for r in rows if _threads_tab_kind(r) in ("threads", "media")]


def _fetch_x_timeline(db_file: str, profile_id: int) -> list:
    """Date-wise Reply / Repost / Like / View for the X PDF timeline."""
    from platforms.x.db import get_x_timeline
    return get_x_timeline(db_file, profile_id)


def _fetch_comment_samples(db_file: str, profile_id: int, limit: int = 120) -> list:
    """Recent / representative comments across post types with author."""
    con = sqlite3.connect(db_file)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = []

    cur.execute(
        """
        SELECT co.name, pc.comment_text AS text, 'photo' AS kind, pp.photo_url AS url
        FROM photo_comments pc
        JOIN commentors co ON co.id = pc.commentor_id
        JOIN photo_posts pp ON pp.id = pc.photo_post_id
        WHERE pp.profile_id = ? AND TRIM(COALESCE(pc.comment_text,'')) != ''
        ORDER BY pc.id DESC LIMIT ?
        """,
        (profile_id, limit // 3 + 10),
    )
    rows.extend(dict(r) for r in cur.fetchall())

    cur.execute(
        """
        SELECT co.name, rc.comment_text AS text, 'reel' AS kind, rp.reel_url AS url
        FROM reel_comments rc
        JOIN commentors co ON co.id = rc.commentor_id
        JOIN reel_posts rp ON rp.id = rc.reel_post_id
        WHERE rp.profile_id = ? AND TRIM(COALESCE(rc.comment_text,'')) != ''
        ORDER BY rc.id DESC LIMIT ?
        """,
        (profile_id, limit // 3 + 10),
    )
    rows.extend(dict(r) for r in cur.fetchall())

    cur.execute(
        """
        SELECT co.name, tc.comment_text AS text, 'text' AS kind, tp.post_url AS url
        FROM text_comments tc
        JOIN commentors co ON co.id = tc.commentor_id
        JOIN text_posts tp ON tp.id = tc.text_post_id
        WHERE tp.profile_id = ? AND TRIM(COALESCE(tc.comment_text,'')) != ''
        ORDER BY tc.id DESC LIMIT ?
        """,
        (profile_id, limit // 3 + 10),
    )
    rows.extend(dict(r) for r in cur.fetchall())
    con.close()
    return rows[:limit]


def _face_clusters(db_file: str, profile_id: int) -> list:
    con = sqlite3.connect(db_file)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        """
        SELECT DISTINCT fc.id, fc.person_label, fc.appearance_count,
               fc.representative_face, fc.post_ids, fc.created_at
        FROM face_clusters fc
        WHERE fc.id IN (
            SELECT DISTINCT df.person_id
            FROM detected_faces df
            LEFT JOIN photo_posts pp ON pp.id = df.photo_post_id
            LEFT JOIN text_posts  tp ON tp.id = df.text_post_id
            WHERE df.person_id IS NOT NULL
              AND (pp.profile_id = ? OR tp.profile_id = ?)
        )
        ORDER BY fc.appearance_count DESC
        """,
        (profile_id, profile_id),
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


# ── co-comment charts (matrix + force-directed) ───────────────────────────────

def _filter_cocomment(coco: dict, threshold: int = 1, max_nodes: int = 24) -> tuple[list, list]:
    """Same rule as analysis UI: edges with weight >= T; nodes on those edges."""
    all_nodes = coco.get("nodes") or []
    all_edges = coco.get("edges") or []
    edges = [e for e in all_edges if (e.get("weight") or 0) >= threshold]
    keep = set()
    for e in edges:
        keep.add(e["source"])
        keep.add(e["target"])
    # Prefer highest-frequency nodes that appear in kept edges
    nodes = [n for n in all_nodes if n.get("commentor_id") in keep]
    nodes = sorted(nodes, key=lambda n: n.get("comment_count") or 0, reverse=True)[:max_nodes]
    keep2 = {n["commentor_id"] for n in nodes}
    edges = [
        e for e in edges
        if e["source"] in keep2 and e["target"] in keep2
    ]
    return nodes, edges


def chart_x_engagement_mix(eng: dict):
    """Donut matching the X dashboard Engagement Mix (Reply / Repost / Like)."""
    reply = int((eng or {}).get("reply") or 0)
    repost = int((eng or {}).get("repost") or 0)
    like = int((eng or {}).get("like") or 0)
    if reply + repost + like <= 0:
        return None
    fig, ax = plt.subplots(figsize=(5.4, 3.4))
    fig.patch.set_facecolor("white")
    ax.pie(
        [reply, repost, like],
        labels=["Reply", "Repost", "Like"],
        colors=["#d4a24c", "#ff7a29", "#ff4d88"],
        autopct=lambda p: f"{p:.0f}%" if p >= 4 else "",
        startangle=90,
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 2},
        textprops={"fontsize": 9, "fontweight": "bold"},
    )
    ax.set_title("Engagement Mix · Reply / Repost / Like", fontsize=11, fontweight="bold", color="#1a1a2e")
    plt.tight_layout()
    return _chart_buf(fig)


def chart_x_timeline(rows: list):
    """Date-wise bars + view line matching the X dashboard timeline."""
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(8.4, 3.2))
    fig.patch.set_facecolor("white")
    xs = [str(r.get("date") or "") for r in rows]
    reply = [int(r.get("reply") or r.get("replies") or 0) for r in rows]
    repost = [int(r.get("repost") or r.get("reposts") or 0) for r in rows]
    like = [int(r.get("like") or r.get("likes") or 0) for r in rows]
    view = [int(r.get("view") or r.get("views") or 0) for r in rows]
    idx = list(range(len(xs)))
    ax.bar(idx, reply, color="#d4a24c", label="Reply")
    ax.bar(idx, repost, bottom=reply, color="#ff7a29", label="Repost")
    ax.bar(idx, like, bottom=[a + b for a, b in zip(reply, repost)], color="#ff4d88", label="Like")
    ax.set_xticks(idx)
    ax.set_xticklabels(xs, rotation=55, ha="right", fontsize=7)
    ax.set_ylabel("Reply / Repost / Like", fontsize=8)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax2 = ax.twinx()
    ax2.plot(idx, view, color="#555", marker="o", markersize=3.5, linewidth=1.6, label="View")
    ax2.set_ylabel("View", fontsize=8, color="#555")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8)
    ax.set_title("Engagement · Date-wise", fontsize=12, fontweight="bold", color="#1a1a2e")
    plt.tight_layout()
    return _chart_buf(fig)


def _chart_buf(fig, tight: bool = True):
    import io
    buf = io.BytesIO()
    kwargs = dict(format="png", dpi=140, facecolor=fig.get_facecolor())
    if tight:
        kwargs["bbox_inches"] = "tight"
    fig.savefig(buf, **kwargs)
    plt.close(fig)
    buf.seek(0)
    return buf


def _initials(name: str) -> str:
    parts = [p for p in str(name or "?").split() if p]
    if not parts:
        return "?"
    return "".join(p[0] for p in parts)[:2].upper()


def chart_cocomment_matrix(coco: dict, threshold: int = 1):
    """Heatmap matrix matching analysis 'Co-Commentor Matrix'."""
    nodes, edges = _filter_cocomment(coco, threshold=threshold, max_nodes=20)
    if not nodes or not edges:
        return None

    ids = [n["commentor_id"] for n in nodes]
    idx = {cid: i for i, cid in enumerate(ids)}
    n = len(ids)
    mat = np.zeros((n, n), dtype=float)
    for e in edges:
        i, j = idx.get(e["source"]), idx.get(e["target"])
        if i is None or j is None:
            continue
        w = float(e.get("weight") or 0)
        mat[i, j] = w
        mat[j, i] = w
    for i in range(n):
        mat[i, i] = mat.max() if mat.max() > 0 else 1

    labels = [_initials(n.get("name")) for n in nodes]
    fig, ax = plt.subplots(figsize=(8.2, 7.2))
    fig.patch.set_facecolor("white")
    im = ax.imshow(mat, cmap="YlOrBr", aspect="equal")
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(labels, rotation=55, ha="right", fontsize=8, fontweight="bold")
    ax.set_yticklabels(labels, fontsize=8, fontweight="bold")
    ax.set_title(
        f"Co-Commentor Matrix  ·  threshold {threshold}+",
        fontsize=13, fontweight="bold", color="#1a1a2e", pad=12,
    )
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Shared posts", fontsize=9)
    # value annotations for small matrices
    if n <= 14:
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                v = int(mat[i, j])
                if v:
                    ax.text(j, i, str(v), ha="center", va="center", fontsize=7, color="#333")
    plt.tight_layout()
    return _chart_buf(fig)


def chart_cocomment_force(coco: dict, threshold: int = 1):
    """Force-directed co-comment graph (stable spring layout) for PDF."""
    nodes, edges = _filter_cocomment(coco, threshold=threshold, max_nodes=28)
    if not nodes or not edges:
        return None

    ids = [n["commentor_id"] for n in nodes]
    idx = {cid: i for i, cid in enumerate(ids)}
    n = len(ids)

    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    pos = np.stack([np.cos(ang), np.sin(ang)], axis=1).astype(float)
    rng = np.random.default_rng(42)
    pos += rng.normal(0, 0.04, pos.shape)

    W = np.zeros((n, n), dtype=float)
    for e in edges:
        i, j = idx.get(e["source"]), idx.get(e["target"])
        if i is None or j is None:
            continue
        W[i, j] = W[j, i] = float(e.get("weight") or 1)

    k = 1.15 / max(np.sqrt(n), 1.0)
    temp = 0.35
    for _ in range(120):
        disp = np.zeros_like(pos)
        for i in range(n):
            delta = pos[i] - pos
            dist = np.sqrt(np.sum(delta * delta, axis=1)) + 1e-4
            force = (k * k) / dist
            vec = (delta.T / dist * force).T
            vec[i] = 0
            disp[i] += np.sum(vec, axis=0)
        ii, jj = np.where(np.triu(W, 1) > 0)
        for i, j in zip(ii.tolist(), jj.tolist()):
            delta = pos[i] - pos[j]
            dist = float(np.sqrt(np.dot(delta, delta)) + 1e-4)
            strength = min(float(W[i, j]), 6.0) / 3.0
            attr = (dist * dist) / k * strength * 0.15
            force = delta / dist * attr
            disp[i] -= force
            disp[j] += force
        length = np.sqrt(np.sum(disp * disp, axis=1)) + 1e-9
        scale = np.minimum(1.0, temp / length)
        pos += (disp.T * scale).T
        pos = np.nan_to_num(pos, nan=0.0, posinf=0.0, neginf=0.0)
        pos -= pos.mean(axis=0)
        temp *= 0.96

    span = float(np.max(np.abs(pos))) or 1.0
    pos = pos / span * 1.2

    counts = [max(1, int(nd.get("comment_count") or 1)) for nd in nodes]
    max_c = max(counts)
    sizes = [220 + 700 * (c / max_c) for c in counts]
    max_w = max((e.get("weight") or 1) for e in edges)

    fig, ax = plt.subplots(figsize=(7.6, 6.8))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#fafafa")
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(-1.55, 1.55)
    ax.set_ylim(-1.55, 1.55)

    for e in edges:
        i, j = idx[e["source"]], idx[e["target"]]
        w = float(e.get("weight") or 1)
        lw = 0.5 + 2.8 * (w / max_w)
        ax.plot(
            [pos[i, 0], pos[j, 0]], [pos[i, 1], pos[j, 1]],
            color="#c0392b", alpha=0.22 + 0.4 * (w / max_w), linewidth=lw, zorder=1,
        )

    ax.scatter(
        pos[:, 0], pos[:, 1], s=sizes, c="#2c3e50",
        edgecolors="white", linewidths=1.2, zorder=3, alpha=0.95,
    )
    for i, node in enumerate(nodes):
        ax.text(
            pos[i, 0], pos[i, 1], _initials(node.get("name")),
            ha="center", va="center", fontsize=6.5, fontweight="bold",
            color="white", zorder=4,
        )
        r = float(np.linalg.norm(pos[i]) + 1e-6)
        off = pos[i] / r * 0.16
        ax.text(
            pos[i, 0] + off[0], pos[i, 1] + off[1],
            _clip(node.get("name"), 14),
            ha="center", va="center", fontsize=6, color="#333", zorder=5,
            bbox=dict(boxstyle="round,pad=0.12", facecolor="white", edgecolor="#ddd", alpha=0.92),
        )

    ax.set_title(
        f"Co-Commentor · Force-Directed  ·  threshold {threshold}+",
        fontsize=12, fontweight="bold", color="#1a1a2e", pad=8,
    )
    ax.text(
        0.5, 0.01,
        "Node size ∝ interaction count · Edge thickness ∝ shared posts",
        transform=ax.transAxes, ha="center", fontsize=7.5, color="#777",
    )
    plt.tight_layout()
    return _chart_buf(fig)


def chart_activity_day(activity: dict):
    rows = activity.get("by_date") or []
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(8.4, 3.2))
    fig.patch.set_facecolor("white")
    xs = [r.get("date") for r in rows]
    ys = [int(r.get("messages") or 0) for r in rows]
    ax.plot(xs, ys, color="#c0392b", linewidth=2.2, marker="o", markersize=3.5)
    ax.fill_between(range(len(ys)), ys, color="#c0392b", alpha=0.12)
    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels(xs, rotation=55, ha="right", fontsize=7)
    ax.set_ylabel("Messages", fontsize=9)
    ax.set_title("Messages per Day", fontsize=12, fontweight="bold", color="#1a1a2e")
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    plt.tight_layout()
    return _chart_buf(fig)


def chart_activity_weekday_hour(activity: dict):
    week = activity.get("by_weekday") or []
    hours = activity.get("by_hour") or []
    if not week and not hours:
        return None
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.4, 3.0))
    fig.patch.set_facecolor("white")
    if week:
        ax1.bar(
            [str(r.get("day") or "")[:3] for r in week],
            [int(r.get("messages") or 0) for r in week],
            color="#2a6a8a",
        )
        ax1.set_title("By Weekday", fontsize=11, fontweight="bold")
        ax1.tick_params(axis="x", labelsize=8)
        ax1.grid(axis="y", linestyle="--", alpha=0.35)
    if hours:
        ax2.bar(
            [int(r.get("hour") or 0) for r in hours],
            [int(r.get("messages") or 0) for r in hours],
            color="#ff4d88",
            width=0.85,
        )
        ax2.set_title("By Hour", fontsize=11, fontweight="bold")
        ax2.set_xticks(range(0, 24, 2))
        ax2.tick_params(axis="x", labelsize=8)
        ax2.grid(axis="y", linestyle="--", alpha=0.35)
        if not activity.get("has_hour_data"):
            ax2.text(
                0.5, 0.5, "No hour timestamps in corpus",
                transform=ax2.transAxes, ha="center", va="center",
                fontsize=9, color="#888",
            )
    plt.tight_layout()
    return _chart_buf(fig)


def _style_dashboard_ax(ax, title: str = ""):
    ax.set_facecolor(_DASH_BG)
    for spine in ax.spines.values():
        spine.set_color(_DASH_BORDER)
    ax.tick_params(colors=_DASH_FAINT, labelsize=7)
    ax.yaxis.grid(True, linestyle="-", color="white", alpha=0.08)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, fontsize=10, fontweight="bold", color=_DASH_TITLE, pad=22)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.16),
        ncol=3,
        frameon=False,
        fontsize=8,
        labelcolor=_DASH_TEXT,
    )


def _stack_engagement_bars(ax, rows: list, xlabels: list, title: str = ""):
    like = [int(r.get("like") or 0) for r in rows]
    comment = [int(r.get("comment") or 0) for r in rows]
    repost = [int(r.get("repost") or 0) for r in rows]
    idx = list(range(len(xlabels)))
    ax.bar(idx, like, color=_DASH_LIKE, label="Like", width=0.72)
    ax.bar(idx, comment, bottom=like, color=_DASH_COMMENT, label="Comment", width=0.72)
    ax.bar(
        idx, repost,
        bottom=[a + b for a, b in zip(like, comment)],
        color=_DASH_REPOST, label="Repost", width=0.72,
    )
    ax.set_xticks(idx)
    rotate = 40 if len(xlabels) > 8 else 0
    ha = "right" if rotate else "center"
    tick_size = 6 if len(xlabels) > 12 else 8
    ax.set_xticklabels(xlabels, rotation=rotate, ha=ha, fontsize=tick_size)
    _style_dashboard_ax(ax, title)


def chart_engagement_activity_day(activity: dict):
    """Stacked Like / Comment / Repost by date — dashboard Activity Timeline."""
    rows = activity.get("by_date") or []
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(8.4, 3.4))
    fig.patch.set_facecolor(_DASH_ELEV)
    _stack_engagement_bars(ax, rows, [str(r.get("date") or "") for r in rows], "")
    fig.subplots_adjust(top=0.82, bottom=0.22, left=0.08, right=0.98)
    return _chart_buf(fig, tight=False)


def chart_engagement_activity_weekday_hour(activity: dict):
    week = activity.get("by_weekday") or []
    hours = activity.get("by_hour") or []
    if not week and not hours:
        return None
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.4, 3.2))
    fig.patch.set_facecolor(_DASH_ELEV)
    if week:
        _stack_engagement_bars(
            ax1, week, [str(r.get("day") or "")[:3] for r in week],
            "Activity by Day of Week",
        )
    if hours:
        _stack_engagement_bars(
            ax2, hours, [str(int(r.get("hour") or 0)).zfill(2) for r in hours],
            "Activity by Hour of Day",
        )
    fig.subplots_adjust(top=0.78, bottom=0.16, wspace=0.22, left=0.06, right=0.98)
    return _chart_buf(fig, tight=False)


def chart_top_words(word_stats: dict):
    words = list(reversed((word_stats.get("top_words") or [])[:15]))
    if not words:
        return None
    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    fig.patch.set_facecolor("white")
    labels = [w.get("word") for w in words]
    vals = [int(w.get("count") or 0) for w in words]
    ax.barh(labels, vals, color="#2a8a96")
    ax.set_title("Top Words (stopwords excluded)", fontsize=12, fontweight="bold", color="#1a1a2e")
    ax.set_xlabel("Count", fontsize=9)
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(axis="x", linestyle="--", alpha=0.35)
    plt.tight_layout()
    return _chart_buf(fig)


def chart_word_cloud(word_stats: dict):
    """ConvoMetrics-style visual word cloud for the PDF Word Analysis section."""
    import io
    rows = word_stats.get("cloud_words") or word_stats.get("top_words") or []
    freqs = {str(w.get("word")): int(w.get("count") or 0) for w in rows if w.get("word")}
    if not freqs:
        return None
    try:
        from platforms.telegram.text_metrics import render_word_cloud_png
        png = render_word_cloud_png(freqs, width=1200, height=520)
        if not png:
            return None
        buf = io.BytesIO(png)
        buf.seek(0)
        return buf
    except Exception:
        # Fallback: draw a simple frequency scatter-style cloud with matplotlib only
        fig, ax = plt.subplots(figsize=(8.4, 3.8))
        fig.patch.set_facecolor("white")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        ax.set_title("Visual Word Cloud", fontsize=12, fontweight="bold", color="#1a1a2e", pad=8)
        items = sorted(freqs.items(), key=lambda x: x[1], reverse=True)[:40]
        max_c = items[0][1] if items else 1
        rng = np.random.default_rng(7)
        for i, (word, count) in enumerate(items):
            size = 8 + 22 * (count / max_c)
            ax.text(
                rng.uniform(0.05, 0.95), rng.uniform(0.08, 0.92), word,
                fontsize=size, ha="center", va="center",
                color=plt.cm.viridis(0.2 + 0.7 * (count / max_c)),
                fontweight="bold", alpha=0.9,
            )
        plt.tight_layout()
        return _chart_buf(fig)


def chart_word_who(term: str, by_sender: list):
    rows = (by_sender or [])[:8]
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(4.2, 3.4))
    fig.patch.set_facecolor("white")
    labels = [_clip(r.get("sender"), 18) for r in rows]
    vals = [int(r.get("count") or 0) for r in rows]
    colors_pie = ["#ff7a29", "#ff4d88", "#d4a24c", "#5fd4e0", "#f4c430", "#3dd68c", "#6ab6d4", "#c0392b"]
    ax.pie(
        vals, labels=labels, autopct=lambda p: f"{p:.0f}%" if p >= 8 else "",
        colors=colors_pie[: len(vals)], startangle=90,
        textprops={"fontsize": 7},
    )
    ax.set_title(f"Who said '{term}'?", fontsize=10, fontweight="bold")
    plt.tight_layout()
    return _chart_buf(fig)


def _pdf_image(buf, width_mm: float = 155):
    if buf is None:
        return None
    try:
        from PIL import Image as PILImage
        import io
        buf.seek(0)
        pil = PILImage.open(buf)
        pw, ph = pil.size
        aspect = (ph / float(pw)) if pw else 0.85
        height_mm = min(width_mm * aspect, 185)
        out = io.BytesIO()
        pil.save(out, format="PNG")
        out.seek(0)
        img = Image(out, width=width_mm * mm, height=height_mm * mm)
        img.hAlign = "CENTER"
        return img
    except Exception:
        try:
            buf.seek(0)
            img = Image(buf, width=width_mm * mm, height=130 * mm)
            img.hAlign = "CENTER"
            return img
        except Exception:
            return None


# ── builders ──────────────────────────────────────────────────────────────────

def build_cover(profile: dict, S, platform: str = "facebook") -> list:
    story = [Spacer(1, 24 * mm)]
    if os.path.isfile(LOGO_PATH):
        try:
            logo_w, logo_h = 48 * mm, 41 * mm
            try:
                from PIL import Image as PILImage
                with PILImage.open(LOGO_PATH) as im:
                    iw, ih = im.size
                if iw and ih:
                    logo_w = 48 * mm
                    logo_h = logo_w * (ih / iw)
            except Exception:
                pass
            img = Image(LOGO_PATH, width=logo_w, height=logo_h)
            img.hAlign = "CENTER"
            story.append(img)
            story.append(Spacer(1, 6 * mm))
        except Exception:
            pass

    story.append(Paragraph("Soclytics", S["cover_title"]))
    story.append(Paragraph("Full Soclytics Report", S["cover_sub"]))
    story.append(Paragraph("NO LLM · LOCAL COMPLETE DUMP", S["confidential"]))
    m = _meaning_para("cover", S)
    if m:
        story.append(m)
    story.append(HRFlowable(width="80%", thickness=1, color=C_ACCENT, spaceAfter=10))

    owner = profile.get("owner_name") or "Unknown Subject"
    url = profile.get("profile_url") or ""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    meta = [
        [Paragraph("SUBJECT", S["meta_l"]), Paragraph(_esc(owner), S["meta_v"])],
        [Paragraph("PROFILE", S["meta_l"]), Paragraph(_esc(_clip(url, 95)), S["meta_v"])],
        [Paragraph("CASE ID", S["meta_l"]), Paragraph(f"BE-{profile.get('id', '—')}", S["meta_v"])],
        [Paragraph("SCRAPED", S["meta_l"]), Paragraph(_esc(profile.get("scraped_at") or "—"), S["meta_v"])],
        [Paragraph("GENERATED", S["meta_l"]), Paragraph(generated, S["meta_v"])],
        [Paragraph("LOCKED", S["meta_l"]), Paragraph("Yes" if profile.get("is_locked") else "No", S["meta_v"])],
    ]
    mt = Table(meta, colWidths=[32 * mm, 125 * mm])
    mt.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [C_LIGHT_BG, C_WHITE]),
                ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
                ("LINEBEFORE", (0, 0), (0, -1), 2.5, C_ACCENT),
            ]
        )
    )
    story.append(mt)
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Cover field meanings", S["sub"]))
    gloss = [[
        Paragraph("Field", S["th"]),
        Paragraph("Meaning", S["th"]),
    ]]
    for label, key in (
        ("SUBJECT", "subject"),
        ("PROFILE", "profile"),
        ("CASE ID", "case_id"),
        ("SCRAPED", "scraped"),
        ("GENERATED", "generated"),
        ("LOCKED", "locked"),
    ):
        gloss.append([
            Paragraph(label, S["td"]),
            Paragraph(_esc(section_meaning(key)), S["td"]),
        ])
    gt = Table(gloss, colWidths=[32 * mm, 125 * mm])
    gt.setStyle(_table_style())
    story.append(gt)
    story.append(Spacer(1, 6 * mm))
    if platform == "telegram":
        contents = (
            "Contents: Executive Summary · Profile · Co-Comment Matrix · Force Graph · "
            "All Interactors · Top-7 · Full Post Inventory · Comment Samples · Timeline · "
            "Activity Timeline · Word Analysis · Word Searcher · Face Clusters"
        )
    elif platform == "x":
        contents = (
            "Contents: Profile · Engagement Mix · Timeline · X Posts "
            "(Reply · Repost · Like · View)"
        )
    elif platform == "threads":
        contents = (
            "Contents: Profile · Co-Comment Matrix · Force Graph · All Interactors · Top-7 · "
            "Profile Post Feed · Comment Samples · Timeline · Activity Timeline · Face Clusters"
        )
    else:
        contents = (
            "Contents: Profile · Co-Comment Matrix · Force Graph · All Interactors · Top-7 · "
            "Full Post Inventory · Comment Samples · Timeline · Face Clusters"
        )
    story.append(Paragraph(contents, S["cover_sub"]))
    story.append(PageBreak())
    return story


def compose_executive_summary(data: dict) -> dict:
    """
    Formal executive briefing for Telegram content reports (no LLM).

    Structure:
      1. Overview & Objectives
      2. Collection Outcomes
      3. Content & Network Findings
      4. Limitations & Gaps
      5. Recommended Follow-up
    """
    profile = data.get("profile") or {}
    counts = data.get("counts") or {}
    posts = data.get("posts") or {}
    faces = data.get("faces") or []
    interactors = data.get("interactors") or []
    top7 = data.get("top7") or []
    coco = data.get("coco") or {}
    activity = data.get("activity") or {}
    word_stats = data.get("word_stats") or {}
    meta = data.get("meta") or {}

    photo_n = len(posts.get("photos") or [])
    reel_n = len(posts.get("reels") or [])
    text_n = len(posts.get("texts") or [])
    total_posts = photo_n + reel_n + text_n
    ix = counts.get("interactions") or {}
    total_ix = int(ix.get("total") or 0)

    subject = {
        "name": profile.get("owner_name") or "Unknown Subject",
        "url": profile.get("profile_url") or "",
        "case_id": profile.get("id"),
        "scraped_at": profile.get("scraped_at") or "—",
        "locked": bool(profile.get("is_locked")),
    }

    collection = {
        "posts_total": total_posts,
        "photos": photo_n,
        "reels": reel_n,
        "texts": text_n,
        "interactors": len(interactors),
        "interactions": total_ix,
        "face_clusters": len(faces),
        "messages": int(activity.get("total_messages") or 0),
        "participants": int(activity.get("participants") or 0),
        "active_days": len(activity.get("by_date") or []),
        "words": int(word_stats.get("total_words") or 0),
        "unique_words": int(word_stats.get("unique_words") or 0),
    }

    name = subject["name"]
    url = subject["url"] or "(URL unavailable)"
    case_id = subject["case_id"]
    scraped = subject["scraped_at"]
    generated = (meta.get("generated_at") or "")[:19].replace("T", " ") or "this run"
    lock_clause = (
        " The source surface was locked or restricted at the time of collection."
        if subject["locked"]
        else ""
    )

    msg_n = collection["messages"]
    top_words = word_stats.get("top_words") or []
    by_date = activity.get("by_date") or []
    top_senders = activity.get("top_senders") or []
    edges = sorted(
        coco.get("edges") or [],
        key=lambda e: e.get("weight") or 0,
        reverse=True,
    )
    nodes = {n["commentor_id"]: n for n in (coco.get("nodes") or [])}

    # --- 1. Overview & Objectives ---
    overview = (
        f"This report presents the outcomes of a data collection and scraping initiative "
        f"conducted against the Telegram subject \"{name}\" ({url}). The objective was to "
        f"assemble a point-in-time SOCMINT corpus — posts, interactions, participant "
        f"activity, and lexical signals — suitable for investigative review under case "
        f"BE-{case_id}. Collection was recorded at {scraped}; this briefing was composed "
        f"at {generated} UTC from locally stored metrics only (no remote LLM enrichment)."
        f"{lock_clause}"
    )

    # --- 2. Collection Outcomes ---
    outcomes = (
        f"The initiative recovered {total_posts} post items "
        f"({photo_n} photos, {reel_n} reels, {text_n} text), "
        f"{len(interactors)} unique interactors, and {total_ix} interaction records. "
        f"Face clustering produced {len(faces)} cluster(s)."
    )
    if msg_n:
        outcomes += (
            f" The derived message corpus contains {msg_n} messages from "
            f"{collection['participants']} participant(s) across "
            f"{collection['active_days']} active day(s), totalling "
            f"{collection['words']} words ({collection['unique_words']} unique after "
            f"stopword filtering)."
        )
    else:
        outcomes += (
            " A usable message corpus for activity and word analytics was not available "
            "from the collected captions, comments, or day-thread transcripts."
        )

    # --- 3. Content & Network Findings ---
    findings_parts: list[str] = []
    if msg_n and by_date:
        peak = max(by_date, key=lambda r: int(r.get("messages") or 0))
        findings_parts.append(
            f"Peak message volume occurred on {peak.get('date') or '—'} "
            f"({int(peak.get('messages') or 0)} messages)."
        )
    if top_senders:
        lead = ", ".join(
            f"{s.get('sender') or '?'} ({int(s.get('messages') or 0)})"
            for s in top_senders[:5]
        )
        findings_parts.append(f"Highest-volume participants were {lead}.")
    if top_words:
        themes = ", ".join(
            f"{w.get('word')} ({int(w.get('count') or 0)})"
            for w in top_words[:8]
        )
        findings_parts.append(
            f"Dominant content terms in the filtered corpus were {themes}."
        )
    else:
        findings_parts.append(
            "No dominant content terms could be derived from the available text."
        )

    if top7:
        poi = ", ".join(
            f"#{t.get('rank') or i} {t.get('name') or 'Unknown'} "
            f"({int(t.get('comment_count') or 0)} interactions)"
            for i, t in enumerate(top7[:7], 1)
        )
        findings_parts.append(
            f"Priority interactors identified for follow-up (Top-7) are {poi}."
        )
    elif interactors:
        findings_parts.append(
            f"Top-7 ranking is empty; {len(interactors)} interactors appear in the "
            f"full registry for manual triage."
        )
    else:
        findings_parts.append("No interactors were recorded for this subject.")

    if edges:
        pair_bits = []
        for e in edges[:3]:
            a = nodes.get(e.get("source"), {})
            b = nodes.get(e.get("target"), {})
            an = a.get("name") or e.get("source")
            bn = b.get("name") or e.get("target")
            pair_bits.append(
                f"{an} and {bn} ({int(e.get('weight') or 0)} shared posts)"
            )
        findings_parts.append(
            f"The co-comment network contains {len(edges)} edge(s); the strongest "
            f"pairs are {'; '.join(pair_bits)}."
        )
    else:
        findings_parts.append(
            "No co-comment pairs were detected, indicating limited shared-post "
            "overlap among interactors in this collection window."
        )

    findings = " ".join(findings_parts)

    # --- 4. Limitations & Gaps ---
    gaps: list[str] = []
    if subject["locked"]:
        gaps.append("the source was locked or restricted at scrape time")
    if not msg_n:
        gaps.append("message-level activity and word analytics could not be computed")
    if not top_words:
        gaps.append("lexical theme extraction was unavailable")
    if not faces:
        gaps.append("no face clusters were produced")
    if not interactors:
        gaps.append("no interactors were recorded")
    if gaps:
        limitations = (
            "This briefing is point-in-time and may be incomplete. Automated checks "
            "flagged the following gaps: " + "; ".join(gaps) + ". "
            "Findings should be corroborated against the full inventory, comment "
            "samples, and source platform before operational use."
        )
    else:
        limitations = (
            "Automated checks did not flag major collection gaps; the report remains "
            "point-in-time and may still omit deleted, restricted, or unscrapeable "
            "material. Findings should be corroborated against the full inventory "
            "before operational use."
        )

    # --- 5. Recommended Follow-up ---
    follow: list[str] = []
    if top7:
        follow.append(
            "Deep-dive Top-7 interactors (about fields, profile URLs, and comment samples)."
        )
    if top_words:
        follow.append(
            "Review Word Analysis / Word Searcher excerpts for slogan, entity, and "
            "campaign language around the dominant terms."
        )
    if edges:
        follow.append(
            "Inspect strongest co-comment pairs for coordination or recurring circles."
        )
    if by_date:
        follow.append(
            "Align peak activity dates with external events or known campaign windows."
        )
    if not faces and (photo_n or reel_n):
        follow.append(
            "Re-run face clustering after verifying media downloads if identity "
            "matching is required."
        )
    if not follow:
        follow.append(
            "Expand the scrape window or collect additional message history to "
            "strengthen content and network coverage."
        )
    follow_up = " ".join(f"{i}. {item}" for i, item in enumerate(follow, 1))

    sections = [
        {
            "number": 1,
            "title": "Overview & Objectives",
            "body": overview,
        },
        {
            "number": 2,
            "title": "Collection Outcomes",
            "body": outcomes,
        },
        {
            "number": 3,
            "title": "Content & Network Findings",
            "body": findings,
        },
        {
            "number": 4,
            "title": "Limitations & Gaps",
            "body": limitations,
        },
        {
            "number": 5,
            "title": "Recommended Follow-up",
            "body": follow_up,
        },
    ]

    # Keep legacy "bullets" as section titles + first sentence for older consumers.
    bullets = [f"{s['number']}. {s['title']}: {s['body']}" for s in sections]

    return {
        "subject": subject,
        "collection": collection,
        "sections": sections,
        "bullets": bullets,
        "top_words": [
            {"word": w.get("word"), "count": int(w.get("count") or 0)}
            for w in top_words[:10]
        ],
        "top_senders": top_senders[:8],
        "top7": [
            {
                "rank": t.get("rank"),
                "name": t.get("name"),
                "comment_count": t.get("comment_count"),
                "profile_url": t.get("profile_url"),
            }
            for t in top7[:7]
        ],
    }


def build_executive_summary(data: dict, S) -> list:
    """PDF section 00 — formal Telegram content executive briefing."""
    exec_data = data.get("executive_summary") or compose_executive_summary(data)
    sections = exec_data.get("sections") or []
    collection = exec_data.get("collection") or {}
    subject = exec_data.get("subject") or {}

    story = [
        Paragraph("00 / EXECUTIVE SUMMARY", S["section"]),
    ]
    m = _meaning_para("00", S)
    if m:
        story.append(m)
    story.append(Spacer(1, 2 * mm))

    story.append(
        Paragraph(
            f"<b>{_esc(subject.get('name') or 'Unknown Subject')}</b> · "
            f"BE-{_esc(subject.get('case_id'))} · "
            f"{_esc(_clip(subject.get('url'), 90))}",
            S["body"],
        )
    )
    story.append(Spacer(1, 2 * mm))

    row = Table(
        [[
            _stat_box("Posts", collection.get("posts_total") or 0, S),
            _stat_box("Messages", collection.get("messages") or 0, S),
            _stat_box("Interactors", collection.get("interactors") or 0, S),
            _stat_box("Top Terms", len(exec_data.get("top_words") or []), S),
        ]],
        colWidths=[40 * mm] * 4,
    )
    row.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    story.append(row)
    story.append(Spacer(1, 4 * mm))

    if not sections:
        story.append(Paragraph("No executive summary could be composed.", S["body"]))
    else:
        for sec in sections:
            story.append(
                Paragraph(
                    f"{int(sec.get('number') or 0)}. {_esc(sec.get('title') or '')}",
                    S["sub"],
                )
            )
            story.append(Paragraph(_esc(sec.get("body") or ""), S["body"]))
            story.append(Spacer(1, 2 * mm))

    top_words = exec_data.get("top_words") or []
    if top_words:
        story.append(Paragraph("Theme snapshot (top terms)", S["sub"]))
        tw = [[Paragraph("Word", S["th"]), Paragraph("Count", S["th"])]]
        for w in top_words[:8]:
            tw.append([
                Paragraph(_esc(w.get("word") or ""), S["td"]),
                Paragraph(str(w.get("count") or 0), S["td_c"]),
            ])
        t = Table(tw, colWidths=[120 * mm, 40 * mm])
        t.setStyle(_table_style())
        story.append(t)

    story.append(PageBreak())
    return story


def _engagement_totals(posts: dict) -> dict:
    like = comment = repost = 0
    n = 0
    for bucket in ("photos", "reels", "texts"):
        for r in posts.get(bucket) or []:
            n += 1
            like += int(r.get("like_count") or 0)
            comment += int(r.get("reply_count") or r.get("comment_count") or 0)
            repost += int(r.get("repost_count") or 0)
    return {"posts": n, "like": like, "comment": comment, "repost": repost}


def _x_engagement_totals(posts: dict) -> dict:
    texts = posts.get("texts") or []
    return {
        "posts": len(texts),
        "reply": sum(int(t.get("reply_count") or 0) for t in texts),
        "repost": sum(int(t.get("repost_count") or 0) for t in texts),
        "like": sum(int(t.get("like_count") or 0) for t in texts),
        "view": sum(int(t.get("view_count") or 0) for t in texts),
    }


def build_summary(profile: dict, counts: dict, posts: dict, faces: list, interactors: list, S, platform: str = "facebook") -> list:
    posts_c = counts.get("posts") or {}
    ix = counts.get("interactions") or {}
    photo_n = len(posts.get("photos") or [])
    reel_n = len(posts.get("reels") or [])
    text_n = len(posts.get("texts") or [])
    total_posts = photo_n + reel_n + text_n
    total_ix = int(ix.get("total") or 0)
    commentors = len(interactors)

    story = [
        Paragraph("01 / PROFILE SUMMARY", S["section"]),
    ]
    m = _meaning_para("01_x" if platform == "x" else "01", S)
    if m:
        story.append(m)
    story.append(Spacer(1, 2 * mm))
    if platform == "x":
        xt = _x_engagement_totals(posts)
        row = Table(
            [[
                _stat_box("Posts", xt["posts"], S),
                _stat_box("Reply", xt["reply"], S),
                _stat_box("Repost", xt["repost"], S),
                _stat_box("Like", xt["like"], S),
                _stat_box("View", xt["view"], S),
            ]],
            colWidths=[32 * mm] * 5,
        )
    else:
        row = Table(
        [
            [
                _stat_box("Posts", total_posts, S),
                _stat_box("Photos", photo_n, S),
                _stat_box("Reels", reel_n, S),
                _stat_box("Text", text_n, S),
            ],
            [
                _stat_box("Interactors", commentors, S),
                _stat_box("Comments", total_ix, S),
                _stat_box("Faces", len(faces), S),
                _stat_box("Top-7", min(7, commentors), S),
            ],
        ],
        colWidths=[40 * mm] * 4,
    )
    row.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("LEFTPADDING", (0, 0), (-1, -1), 2)]))
    story.append(row)
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Metric meanings", S["sub"]))
    metric_gloss = [[Paragraph("Metric", S["th"]), Paragraph("Meaning", S["th"])]]
    x_metrics = (
        ("Posts", "Collected X.com status items for this profile."),
        ("Reply", "Sum of reply counts shown on each tweet."),
        ("Repost", "Sum of repost / retweet counts shown on each tweet."),
        ("Like", "Sum of like counts shown on each tweet."),
        ("View", "Sum of view counts shown on each tweet."),
    )
    default_metrics = (
        ("Posts", "posts_stat"),
        ("Photos", "photos_stat"),
        ("Reels", "reels_stat"),
        ("Text", "text_stat"),
        ("Interactors", "interactors_stat"),
        ("Comments", "comments_stat"),
        ("Faces", "faces_stat"),
        ("Top-7", "top7_stat"),
    )
    for label, key in (x_metrics if platform == "x" else default_metrics):
        metric_gloss.append([
            Paragraph(label, S["td"]),
            Paragraph(_esc(key if platform == "x" else section_meaning(key)), S["td"]),
        ])
    mg = Table(metric_gloss, colWidths=[28 * mm, 142 * mm])
    mg.setStyle(_table_style())
    story.append(mg)

    fields = profile.get("fields") or []
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("About / Profile Fields", S["sub"]))
    am = _meaning_para("about", S)
    if am:
        story.append(am)
    if fields:
        data = [[Paragraph("Section", S["th"]), Paragraph("Label", S["th"]), Paragraph("Value", S["th"])]]
        for f in fields:
            data.append(
                [
                    Paragraph(_esc(f.get("section") or ""), S["td"]),
                    Paragraph(_esc(f.get("label") or ""), S["td"]),
                    Paragraph(_esc(_clip(f.get("value"), 280)), S["td"]),
                ]
            )
        t = Table(data, colWidths=[32 * mm, 40 * mm, 98 * mm])
        t.setStyle(_table_style())
        story.append(t)
    else:
        story.append(Paragraph("No about fields scraped for this profile.", S["body"]))
    story.append(PageBreak())
    return story


def build_network(interactors: list, coco: dict, S) -> list:
    edges = sorted(coco.get("edges") or [], key=lambda e: e.get("weight") or 0, reverse=True)
    nodes = {n["commentor_id"]: n for n in (coco.get("nodes") or [])}
    story = [
        Paragraph("02 / NETWORK OVERVIEW", S["section"]),
    ]
    m = _meaning_para("02", S)
    if m:
        story.append(m)
    story.append(
        Paragraph(
            f"{len(interactors)} unique interactors · {len(edges)} co-comment edges "
            f"(shared posts between pairs).",
            S["body"],
        )
    )
    story.append(Spacer(1, 2 * mm))

    # Pick a useful threshold: prefer 2+ if that still yields pairs, else 1+
    thr = 1
    n2, e2 = _filter_cocomment(coco, threshold=2, max_nodes=20)
    if e2:
        thr = 2

    story.append(Paragraph(f"Co-Commentor Matrix  (threshold {thr}+)", S["sub"]))
    mx = _meaning_para("matrix", S)
    if mx:
        story.append(mx)
    matrix_img = _pdf_image(chart_cocomment_matrix(coco, threshold=thr))
    if matrix_img:
        story.append(matrix_img)
    else:
        story.append(Paragraph("No co-comment matrix data at this threshold.", S["body"]))
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph(f"Co-Commentor · Force-Directed  (threshold {thr}+)", S["sub"]))
    fx = _meaning_para("force", S)
    if fx:
        story.append(fx)
    force_img = _pdf_image(chart_cocomment_force(coco, threshold=thr), width_mm=170)
    if force_img:
        story.append(force_img)
    else:
        story.append(Paragraph("No force-directed graph data at this threshold.", S["body"]))

    story.append(PageBreak())
    story.append(Paragraph("Strongest Co-Comment Pairs (table)", S["sub"]))
    px = _meaning_para("pairs", S)
    if px:
        story.append(px)
    if not edges:
        story.append(Paragraph("No co-comment pairs detected.", S["body"]))
    else:
        data = [[
            Paragraph("#", S["th"]),
            Paragraph("Interactor A", S["th"]),
            Paragraph("Interactor B", S["th"]),
            Paragraph("Shared posts", S["th"]),
        ]]
        for i, e in enumerate(edges[:40], 1):
            a = nodes.get(e["source"], {})
            b = nodes.get(e["target"], {})
            data.append(
                [
                    Paragraph(str(i), S["td_c"]),
                    Paragraph(_esc(a.get("name") or e["source"]), S["td"]),
                    Paragraph(_esc(b.get("name") or e["target"]), S["td"]),
                    Paragraph(str(e.get("weight") or 0), S["td_c"]),
                ]
            )
        t = Table(data, colWidths=[12 * mm, 65 * mm, 65 * mm, 28 * mm])
        t.setStyle(_table_style())
        story.append(t)
    story.append(PageBreak())
    return story


def build_interactors(interactors: list, S) -> list:
    story = [
        Paragraph("03 / FULL INTERACTOR REGISTRY", S["section"]),
    ]
    m = _meaning_para("03", S)
    if m:
        story.append(m)
    story.append(Paragraph(f"All {len(interactors)} interactors ranked by total interaction frequency.", S["body"]))
    story.append(Spacer(1, 2 * mm))
    # chunk tables so ReportLab stays happy
    chunk = 55
    for start in range(0, max(len(interactors), 1), chunk):
        part = interactors[start : start + chunk]
        data = [[
            Paragraph("#", S["th"]),
            Paragraph("Name", S["th"]),
            Paragraph("Profile URL", S["th"]),
            Paragraph("Ph", S["th"]),
            Paragraph("Re", S["th"]),
            Paragraph("Tx", S["th"]),
            Paragraph("Total", S["th"]),
        ]]
        for i, row in enumerate(part, start + 1):
            data.append(
                [
                    Paragraph(str(i), S["td_c"]),
                    Paragraph(_esc(_clip(row.get("name"), 36)), S["td"]),
                    Paragraph(_esc(_clip(row.get("profile_url"), 55)), S["td"]),
                    Paragraph(str(row.get("photo_count") or 0), S["td_c"]),
                    Paragraph(str(row.get("reel_count") or 0), S["td_c"]),
                    Paragraph(str(row.get("text_count") or 0), S["td_c"]),
                    Paragraph(str(row.get("total_count") or 0), S["td_c"]),
                ]
            )
        if len(interactors) == 0:
            data.append([Paragraph("—", S["td_c"])] * 7)
        t = Table(data, colWidths=[10 * mm, 38 * mm, 72 * mm, 12 * mm, 12 * mm, 12 * mm, 14 * mm])
        t.setStyle(_table_style())
        story.append(t)
        if start + chunk < len(interactors):
            story.append(Spacer(1, 4 * mm))
            story.append(Paragraph(f"… continued ({start + chunk + 1}–{min(start + 2 * chunk, len(interactors))})", S["body"]))
    story.append(PageBreak())
    return story


def build_top7_section(top7: list, S) -> list:
    story = [
        Paragraph("04 / TOP-7 INTERACTORS", S["section"]),
    ]
    m = _meaning_para("04", S)
    if m:
        story.append(m)
    story.append(Spacer(1, 2 * mm))
    if not top7:
        story.append(Paragraph("No Top-7 data.", S["body"]))
        story.append(PageBreak())
        return story

    for t7 in top7:
        block = [
            Paragraph(
                f"#{t7.get('rank') or '—'} · {_esc(t7.get('name') or 'Unknown')} · "
                f"{t7.get('comment_count') or 0} interactions",
                S["sub"],
            ),
            Paragraph(_esc(t7.get("profile_url") or ""), S["body"]),
        ]
        fields = t7.get("fields") or []
        if fields:
            rows = [
                [
                    Paragraph(_esc(f.get("section") or ""), S["td"]),
                    Paragraph(_esc(f.get("label") or ""), S["td"]),
                    Paragraph(_esc(_clip(f.get("value"), 200)), S["td"]),
                ]
                for f in fields
            ]
            ft = Table(rows, colWidths=[28 * mm, 38 * mm, 104 * mm])
            ft.setStyle(_table_style(header=False))
            block.append(ft)
        else:
            block.append(Paragraph("No about metadata for this interactor.", S["body"]))
        block.append(Spacer(1, 3 * mm))
        story.append(KeepTogether(block))
    story.append(PageBreak())
    return story


def _post_table(title: str, rows: list, S, meaning_key: str | None = None) -> list:
    out = [Paragraph(title, S["sub"])]
    if meaning_key:
        meaning = _meaning_para(meaning_key, S)
        if meaning:
            out.append(meaning)
    out.append(Spacer(1, 1 * mm))
    if not rows:
        out.append(Paragraph("None collected.", S["body"]))
        out.append(Spacer(1, 4 * mm))
        return out
    data = [[
        Paragraph("#", S["th"]),
        Paragraph("Date", S["th"]),
        Paragraph("Engagement", S["th"]),
        Paragraph("URL / Caption", S["th"]),
    ]]
    for i, r in enumerate(rows, 1):
        comment_n = int(r.get("reply_count") or r.get("comment_count") or 0)
        repost_n = int(r.get("repost_count") or 0)
        like_n = int(r.get("like_count") or 0)
        data.append(
            [
                Paragraph(str(i), S["td_c"]),
                Paragraph(_esc(_clip(r.get("date_text") or r.get("scraped_at"), 18)), S["td_c"]),
                Paragraph(
                    f"Comment {comment_n} · Repost {repost_n} · Like {like_n}",
                    S["td_c"],
                ),
                Paragraph(
                    _esc(_clip((r.get("url") or "") + " — " + (r.get("caption") or ""), 160)),
                    S["td"],
                ),
            ]
        )
    t = Table(data, colWidths=[10 * mm, 28 * mm, 42 * mm, 90 * mm])
    t.setStyle(_table_style())
    out.append(t)
    out.append(Spacer(1, 4 * mm))
    return out


def build_x_engagement_mix(posts: dict, S) -> list:
    """Dashboard card: Engagement Mix · Reply / Repost / Like / View."""
    xt = _x_engagement_totals(posts)
    mix = xt["reply"] + xt["repost"] + xt["like"]
    story = [
        Paragraph("02 / ENGAGEMENT MIX", S["section"]),
        Paragraph(
            "Same totals as the analysis dashboard donut. View is listed separately "
            "because impression volume dwarfs Reply / Repost / Like.",
            S["meaning"],
        ),
    ]
    row = Table(
        [[
            _stat_box("Reply", xt["reply"], S),
            _stat_box("Repost", xt["repost"], S),
            _stat_box("Like", xt["like"], S),
            _stat_box("View", xt["view"], S),
        ]],
        colWidths=[40 * mm] * 4,
    )
    row.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    story.append(row)
    story.append(Spacer(1, 3 * mm))
    img = _pdf_image(chart_x_engagement_mix(xt), width_mm=120)
    if img:
        story.append(img)
        story.append(Spacer(1, 2 * mm))
    denom = mix or 1
    data = [[
        Paragraph("Metric", S["th"]),
        Paragraph("Count", S["th"]),
        Paragraph("Share of mix", S["th"]),
    ]]
    for label, key in (("Reply", "reply"), ("Repost", "repost"), ("Like", "like")):
        n = xt[key]
        data.append([
            Paragraph(label, S["td"]),
            Paragraph(str(n), S["td_c"]),
            Paragraph(f"{round(n / denom * 100)}%", S["td_c"]),
        ])
    data.append([
        Paragraph("View", S["td"]),
        Paragraph(str(xt["view"]), S["td_c"]),
        Paragraph("impressions (not in mix %)", S["td"]),
    ])
    t = Table(data, colWidths=[40 * mm, 40 * mm, 90 * mm])
    t.setStyle(_table_style())
    story.append(t)
    story.append(PageBreak())
    return story


def build_x_posts(posts: dict, S) -> list:
    """Dashboard X Posts feed: each tweet with Reply · Repost · Like · View."""
    rows = posts.get("texts") or []
    xt = _x_engagement_totals(posts)
    story = [
        Paragraph("04 / X POSTS", S["section"]),
    ]
    m = _meaning_para("x_posts", S)
    if m:
        story.append(m)
    story.append(
        Paragraph(
            f"{xt['posts']} posts · Reply {xt['reply']} · Repost {xt['repost']} · "
            f"Like {xt['like']} · View {xt['view']}",
            S["body"],
        )
    )
    story.append(Spacer(1, 2 * mm))
    if not rows:
        story.append(Paragraph("No X posts collected.", S["body"]))
        story.append(PageBreak())
        return story

    for i, r in enumerate(rows, 1):
        url = r.get("url") or r.get("post_url") or ""
        caption = (r.get("caption") or r.get("body") or "").strip() or url or "(no text)"
        media = r.get("media_type") or ("image" if r.get("image_src") else "text")
        head = Table(
            [[
                Paragraph(f"#{i}", S["th"]),
                Paragraph(_esc(r.get("date_text") or "—"), S["th"]),
                Paragraph(_esc(media), S["th"]),
            ]],
            colWidths=[18 * mm, 40 * mm, 112 * mm],
        )
        head.setStyle(_table_style())
        metrics = Table(
            [[
                Paragraph(f"Reply  {int(r.get('reply_count') or 0)}", S["td_c"]),
                Paragraph(f"Repost  {int(r.get('repost_count') or 0)}", S["td_c"]),
                Paragraph(f"Like  {int(r.get('like_count') or 0)}", S["td_c"]),
                Paragraph(f"View  {int(r.get('view_count') or 0)}", S["td_c"]),
            ]],
            colWidths=[42.5 * mm] * 4,
        )
        metrics.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.Color(0.96, 0.94, 0.90)),
            ("BOX", (0, 0), (-1, -1), 0.4, C_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, C_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        block = [
            head,
            Spacer(1, 1.5 * mm),
            Paragraph(_esc(caption), S["body"]),
        ]
        if r.get("image_src"):
            block.append(Paragraph(_esc(r.get("image_src")), S["meaning"]))
        if url:
            block.append(Paragraph(_esc(url), S["meaning"]))
        block.extend([Spacer(1, 1.5 * mm), metrics, Spacer(1, 4 * mm)])
        story.append(KeepTogether(block))
    story.append(PageBreak())
    return story


def _tweet_blocks(title: str, rows: list, S, meaning_key: str | None = None) -> list:
    """Dashboard-style post cards: Comment · Repost · Like (no Views)."""
    out = [Paragraph(title, S["sub"])]
    if meaning_key:
        meaning = _meaning_para(meaning_key, S)
        if meaning:
            out.append(meaning)
    out.append(Spacer(1, 1 * mm))
    if not rows:
        out.append(Paragraph("None collected.", S["body"]))
        out.append(Spacer(1, 4 * mm))
        return out
    for i, r in enumerate(rows, 1):
        url = r.get("url") or r.get("post_url") or r.get("photo_url") or ""
        caption = (r.get("caption") or r.get("body") or "").strip() or url or "(no text)"
        head = Table(
            [[
                Paragraph(f"#{i}", S["th"]),
                Paragraph(_esc(r.get("date_text") or r.get("scraped_at") or "—"), S["th"]),
            ]],
            colWidths=[18 * mm, 152 * mm],
        )
        head.setStyle(_table_style())
        metrics = Table(
            [[
                Paragraph(f"Comment  {int(r.get('reply_count') or r.get('comment_count') or 0)}", S["td_c"]),
                Paragraph(f"Repost  {int(r.get('repost_count') or 0)}", S["td_c"]),
                Paragraph(f"Like  {int(r.get('like_count') or 0)}", S["td_c"]),
            ]],
            colWidths=[56.6 * mm] * 3,
        )
        metrics.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.Color(0.96, 0.94, 0.90)),
            ("BOX", (0, 0), (-1, -1), 0.4, C_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, C_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        block = [
            head,
            Spacer(1, 1.5 * mm),
            Paragraph(_esc(caption), S["body"]),
        ]
        if r.get("image_src"):
            block.append(Paragraph(_esc(str(r.get("image_src"))), S["meaning"]))
        if url and url != caption:
            block.append(Paragraph(_esc(url), S["meaning"]))
        block.extend([Spacer(1, 1.5 * mm), metrics, Spacer(1, 4 * mm)])
        out.append(KeepTogether(block))
    return out


def build_threads_posts(posts: dict, S) -> list:
    """Dashboard-style feed: Threads / Replies / Media / Reposts tabs."""
    rows = posts.get("texts") or []
    eng = _engagement_totals(posts)
    story = [
        Paragraph("05 / PROFILE POST FEED", S["section"]),
        Paragraph(
            "Same layout as the analysis dashboard: native profile tabs with "
            "Comment · Repost · Like on each post (no Views).",
            S["meaning"],
        ),
        Paragraph(
            f"Total {len(rows)} posts · Comment {eng['comment']} · "
            f"Repost {eng['repost']} · Like {eng['like']}",
            S["body"],
        ),
        Spacer(1, 2 * mm),
    ]
    tab_titles = {
        "threads": "Threads",
        "replies": "Replies",
        "media": "Media",
        "reposts": "Reposts",
    }
    for tab in THREADS_PROFILE_TABS:
        tab_rows = _posts_for_threads_tab(rows, tab)
        label = tab_titles[tab]
        story.extend(_tweet_blocks(f"{label} · {len(tab_rows)} posts", tab_rows, S))
    story.append(PageBreak())
    return story


def build_posts(posts: dict, S, tweet_cards: bool = False) -> list:
    eng = _engagement_totals(posts)
    story = [
        Paragraph("05 / FULL POST INVENTORY", S["section"]),
    ]
    m = _meaning_para("05", S)
    if m:
        story.append(m)
    story.append(
        Paragraph(
            f"Photos {len(posts['photos'])} · Reels {len(posts['reels'])} · "
            f"Text {len(posts['texts'])} · Comment {eng['comment']} · "
            f"Repost {eng['repost']} · Like {eng['like']}",
            S["body"],
        )
    )
    story.append(Spacer(1, 2 * mm))
    if tweet_cards:
        story.extend(_tweet_blocks("Photo / Media Posts", posts["photos"], S, "photos_posts"))
        story.extend(_post_table("Reels", posts["reels"], S, "reels_posts"))
        story.extend(_tweet_blocks("Text Posts", posts["texts"], S, "text_posts"))
    else:
        story.extend(_post_table("Photo / Media Posts", posts["photos"], S, "photos_posts"))
        story.extend(_post_table("Reels", posts["reels"], S, "reels_posts"))
        story.extend(_post_table("Text Posts", posts["texts"], S, "text_posts"))
    story.append(PageBreak())
    return story


def build_comments(samples: list, S) -> list:
    story = [
        Paragraph("06 / COMMENT SAMPLES", S["section"]),
    ]
    m = _meaning_para("06", S)
    if m:
        story.append(m)
    story.append(
        Paragraph(
            f"Up to {len(samples)} recent comments with text (empty stubs omitted).",
            S["body"],
        )
    )
    story.append(Spacer(1, 2 * mm))
    if not samples:
        story.append(Paragraph("No comment text stored for this profile.", S["body"]))
        story.append(PageBreak())
        return story

    data = [[
        Paragraph("#", S["th"]),
        Paragraph("Type", S["th"]),
        Paragraph("Author", S["th"]),
        Paragraph("Comment", S["th"]),
    ]]
    for i, c in enumerate(samples, 1):
        data.append(
            [
                Paragraph(str(i), S["td_c"]),
                Paragraph(_esc(c.get("kind") or ""), S["td_c"]),
                Paragraph(_esc(_clip(c.get("name"), 28)), S["td"]),
                Paragraph(_esc(_clip(c.get("text"), 240)), S["td"]),
            ]
        )
    t = Table(data, colWidths=[10 * mm, 16 * mm, 36 * mm, 108 * mm])
    t.setStyle(_table_style())
    story.append(t)
    story.append(PageBreak())
    return story


def build_x_timeline(timeline: list, S) -> list:
    story = [
        Paragraph("03 / ENGAGEMENT TIMELINE", S["section"]),
    ]
    m = _meaning_para("x_posts", S)
    if m:
        story.append(m)
    story.append(Paragraph(
        "Same date-wise series as the analysis dashboard: stacked Reply / Repost / Like, View as a line.",
        S["meaning"],
    ))
    story.append(Spacer(1, 2 * mm))
    if not timeline:
        story.append(Paragraph("No dated tweet rows available.", S["body"]))
        story.append(PageBreak())
        return story

    rows = list(timeline.values()) if isinstance(timeline, dict) else timeline
    rows = sorted(rows, key=lambda r: str(r.get("date") or ""))
    img = _pdf_image(chart_x_timeline(rows), width_mm=170)
    if img:
        story.append(img)
        story.append(Spacer(1, 3 * mm))
    data = [[
        Paragraph("Date", S["th"]),
        Paragraph("Reply", S["th"]),
        Paragraph("Repost", S["th"]),
        Paragraph("Like", S["th"]),
        Paragraph("View", S["th"]),
    ]]
    for r in rows:
        data.append([
            Paragraph(_esc(r.get("date") or "—"), S["td"]),
            Paragraph(str(r.get("reply") or r.get("replies") or 0), S["td_c"]),
            Paragraph(str(r.get("repost") or r.get("reposts") or 0), S["td_c"]),
            Paragraph(str(r.get("like") or r.get("likes") or 0), S["td_c"]),
            Paragraph(str(r.get("view") or r.get("views") or 0), S["td_c"]),
        ])
    t = Table(data, colWidths=[50 * mm, 28 * mm, 28 * mm, 28 * mm, 28 * mm])
    t.setStyle(_table_style())
    story.append(t)
    story.append(PageBreak())
    return story


def build_timeline(timeline: list, S) -> list:
    story = [
        Paragraph("07 / INTERACTION TIMELINE", S["section"]),
    ]
    m = _meaning_para("07", S)
    if m:
        story.append(m)
    story.append(Spacer(1, 2 * mm))
    if not timeline:
        story.append(Paragraph("No dated timeline rows available.", S["body"]))
        story.append(PageBreak())
        return story

    # normalize list of dicts
    rows = timeline
    if isinstance(timeline, dict):
        rows = list(timeline.values())
    rows = sorted(rows, key=lambda r: str(r.get("date") or ""))

    data = [[
        Paragraph("Date", S["th"]),
        Paragraph("Photo", S["th"]),
        Paragraph("Reel", S["th"]),
        Paragraph("Text", S["th"]),
        Paragraph("Total", S["th"]),
    ]]
    for r in rows:
        data.append(
            [
                Paragraph(_esc(r.get("date") or "—"), S["td"]),
                Paragraph(str(r.get("photo") or 0), S["td_c"]),
                Paragraph(str(r.get("reel") or 0), S["td_c"]),
                Paragraph(str(r.get("text") or 0), S["td_c"]),
                Paragraph(str(r.get("total") or 0), S["td_c"]),
            ]
        )
    t = Table(data, colWidths=[50 * mm, 28 * mm, 28 * mm, 28 * mm, 28 * mm])
    t.setStyle(_table_style())
    story.append(t)
    story.append(PageBreak())
    return story


def build_activity_timeline(activity: dict | None, S) -> list:
    story = [
        Paragraph("08 / ACTIVITY TIMELINE", S["section"]),
    ]
    m = _meaning_para("08", S)
    if m:
        story.append(m)
    story.append(Spacer(1, 2 * mm))
    if not activity or not int(activity.get("total_messages") or 0):
        story.append(Paragraph("No message corpus available for activity metrics.", S["body"]))
        story.append(PageBreak())
        return story

    by_date = activity.get("by_date") or []
    row = Table(
        [[
            _stat_box("Messages", activity.get("total_messages") or 0, S),
            _stat_box("Participants", activity.get("participants") or 0, S),
            _stat_box("Active Days", len(by_date), S),
            _stat_box("Hour Data", "Yes" if activity.get("has_hour_data") else "No", S),
        ]],
        colWidths=[40 * mm] * 4,
    )
    row.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    story.append(row)
    story.append(Spacer(1, 3 * mm))

    img = _pdf_image(chart_activity_day(activity), width_mm=170)
    if img:
        story.append(img)
        story.append(Spacer(1, 2 * mm))
    img2 = _pdf_image(chart_activity_weekday_hour(activity), width_mm=170)
    if img2:
        story.append(img2)
        story.append(Spacer(1, 3 * mm))

    story.append(Paragraph("Messages by date", S["sub"]))
    data = [[
        Paragraph("Date", S["th"]),
        Paragraph("Messages", S["th"]),
        Paragraph("Weekday", S["th"]),
    ]]
    for r in by_date[-40:]:
        d = r.get("date") or "—"
        wd = "—"
        try:
            wd = datetime.strptime(str(d)[:10], "%Y-%m-%d").strftime("%A")
        except ValueError:
            pass
        data.append([
            Paragraph(_esc(d), S["td"]),
            Paragraph(str(r.get("messages") or 0), S["td_c"]),
            Paragraph(_esc(wd), S["td_c"]),
        ])
    t = Table(data, colWidths=[55 * mm, 40 * mm, 55 * mm])
    t.setStyle(_table_style())
    story.append(t)

    top_senders = activity.get("top_senders") or []
    if top_senders:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Top participants by message volume", S["sub"]))
        sdata = [[
            Paragraph("#", S["th"]),
            Paragraph("Sender", S["th"]),
            Paragraph("Messages", S["th"]),
        ]]
        for i, s in enumerate(top_senders[:15], 1):
            sdata.append([
                Paragraph(str(i), S["td_c"]),
                Paragraph(_esc(_clip(s.get("sender"), 70)), S["td"]),
                Paragraph(str(s.get("messages") or 0), S["td_c"]),
            ])
        st = Table(sdata, colWidths=[12 * mm, 120 * mm, 28 * mm])
        st.setStyle(_table_style())
        story.append(st)

    story.append(PageBreak())
    return story


def build_engagement_activity_timeline(activity: dict | None, S) -> list:
    """Dashboard Activity Timeline: stacked Like / Comment / Repost."""
    story = [
        Paragraph("08 / ACTIVITY TIMELINE", S["section"]),
    ]
    m = _meaning_para("08_engagement", S)
    if m:
        story.append(m)
    story.append(Spacer(1, 2 * mm))
    if not activity:
        story.append(Paragraph("No engagement activity metrics available.", S["body"]))
        story.append(PageBreak())
        return story

    total_like = int(activity.get("total_like") or 0)
    total_comment = int(activity.get("total_comment") or 0)
    total_repost = int(activity.get("total_repost") or 0)
    stats = Table(
        [[
            _dashboard_stat_box("LIKE", total_like, S),
            _dashboard_stat_box("COMMENT", total_comment, S),
            _dashboard_stat_box("REPOST", total_repost, S),
        ]],
        colWidths=[54 * mm, 54 * mm, 54 * mm],
    )
    stats.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("BACKGROUND", (0, 0), (-1, -1), C_DASH_BG),
    ]))

    card_rows = [[stats]]
    img = _pdf_image(chart_engagement_activity_day(activity), width_mm=162)
    if img:
        card_rows.append([Spacer(1, 3 * mm)])
        card_rows.append([img])
    img2 = _pdf_image(chart_engagement_activity_weekday_hour(activity), width_mm=162)
    if img2:
        card_rows.append([Spacer(1, 2 * mm)])
        card_rows.append([img2])
    card = Table(card_rows, colWidths=[166 * mm])
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_DASH_BG),
        ("BOX", (0, 0), (-1, -1), 0.8, C_DASH_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (0, 0), 8),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(card)
    story.append(PageBreak())
    return story


def build_word_analysis(word_stats: dict | None, S) -> list:
    story = [
        Paragraph("09 / WORD ANALYSIS", S["section"]),
    ]
    m = _meaning_para("09", S)
    if m:
        story.append(m)
    story.append(Spacer(1, 2 * mm))
    if not word_stats or not (word_stats.get("top_words") or []):
        story.append(Paragraph("Not enough textual data for word analysis.", S["body"]))
        story.append(PageBreak())
        return story

    row = Table(
        [[
            _stat_box("Messages", word_stats.get("total_messages") or 0, S),
            _stat_box("Words", word_stats.get("total_words") or 0, S),
            _stat_box("Unique", word_stats.get("unique_words") or 0, S),
            _stat_box("Senders", max(0, len(word_stats.get("senders") or []) - 1), S),
        ]],
        colWidths=[40 * mm] * 4,
    )
    row.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    story.append(row)
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph("Visual Word Cloud", S["sub"]))
    story.append(
        Paragraph(
            "Most frequent words across the collected corpus (stopwords excluded).",
            S["body"],
        )
    )
    cloud = _pdf_image(chart_word_cloud(word_stats), width_mm=170)
    if cloud:
        story.append(cloud)
        story.append(Spacer(1, 3 * mm))
    else:
        story.append(Paragraph("Word cloud unavailable (install wordcloud).", S["body"]))
        story.append(Spacer(1, 2 * mm))

    story.append(Paragraph("Top Words Used", S["sub"]))
    img = _pdf_image(chart_top_words(word_stats), width_mm=165)
    if img:
        story.append(img)
        story.append(Spacer(1, 3 * mm))

    story.append(Paragraph("Top words (All participants)", S["sub"]))
    data = [[
        Paragraph("#", S["th"]),
        Paragraph("Word", S["th"]),
        Paragraph("Count", S["th"]),
    ]]
    for i, w in enumerate((word_stats.get("top_words") or [])[:30], 1):
        data.append([
            Paragraph(str(i), S["td_c"]),
            Paragraph(_esc(w.get("word") or ""), S["td"]),
            Paragraph(str(w.get("count") or 0), S["td_c"]),
        ])
    t = Table(data, colWidths=[14 * mm, 110 * mm, 30 * mm])
    t.setStyle(_table_style())
    story.append(t)
    story.append(PageBreak())
    return story


def build_word_searcher(searches: list | None, S) -> list:
    story = [
        Paragraph("10 / WORD SEARCHER", S["section"]),
    ]
    m = _meaning_para("10", S)
    if m:
        story.append(m)
    story.append(Spacer(1, 2 * mm))
    if not searches:
        story.append(Paragraph("No high-frequency terms available to search.", S["body"]))
        story.append(PageBreak())
        return story

    story.append(
        Paragraph(
            "Auto-searched the highest-frequency content words in the corpus "
            "(same engine as the analysis Word Searcher).",
            S["body"],
        )
    )
    story.append(Spacer(1, 2 * mm))

    summary = [[
        Paragraph("Word", S["th"]),
        Paragraph("Uses", S["th"]),
        Paragraph("Top speaker", S["th"]),
        Paragraph("Top count", S["th"]),
    ]]
    for item in searches:
        top = (item.get("by_sender") or [{}])[0]
        summary.append([
            Paragraph(_esc(item.get("term") or ""), S["td"]),
            Paragraph(str(item.get("total") or 0), S["td_c"]),
            Paragraph(_esc(_clip(top.get("sender"), 42)), S["td"]),
            Paragraph(str(top.get("count") or 0), S["td_c"]),
        ])
    st = Table(summary, colWidths=[35 * mm, 20 * mm, 80 * mm, 25 * mm])
    st.setStyle(_table_style())
    story.append(st)
    story.append(Spacer(1, 4 * mm))

    for item in searches[:6]:
        term = item.get("term") or ""
        block = [
            Paragraph(f"Term · '{_esc(term)}' · {int(item.get('total') or 0)} uses", S["sub"]),
        ]
        who_img = _pdf_image(chart_word_who(term, item.get("by_sender") or []), width_mm=95)
        if who_img:
            block.append(who_img)
            block.append(Spacer(1, 1.5 * mm))

        who_rows = [[
            Paragraph("Sender", S["th"]),
            Paragraph("Count", S["th"]),
        ]]
        for s in (item.get("by_sender") or [])[:8]:
            who_rows.append([
                Paragraph(_esc(_clip(s.get("sender"), 55)), S["td"]),
                Paragraph(str(s.get("count") or 0), S["td_c"]),
            ])
        wt = Table(who_rows, colWidths=[130 * mm, 25 * mm])
        wt.setStyle(_table_style())
        block.append(wt)

        samples = item.get("samples") or []
        if samples:
            block.append(Spacer(1, 1.5 * mm))
            block.append(Paragraph("Samples", S["body"]))
            for s in samples[:3]:
                block.append(
                    Paragraph(
                        f"<b>{_esc(_clip(s.get('sender'), 40))}</b>"
                        f"{' · ' + _esc(s.get('date')) if s.get('date') else ''}"
                        f" — {_esc(_clip(s.get('message'), 180))}",
                        S["body"],
                    )
                )
        block.append(Spacer(1, 3 * mm))
        story.append(KeepTogether(block))

    story.append(PageBreak())
    return story


def build_faces(face_clusters: list, S, face_sec: str = "08", disc_sec: str = "09") -> list:
    story = [
        Paragraph(f"{face_sec} / FACE CLUSTERS", S["section"]),
    ]
    # 11 = telegram numbering; non-telegram still uses the face blurb text
    face_blurb = section_meaning("11") or (
        "Faces automatically grouped across collected images. Each cluster is a likely "
        "unique person; appearance_count is how often that face was seen."
    )
    story.append(Paragraph(_esc(face_blurb), S["meaning"]))
    story.append(Spacer(1, 2 * mm))
    if not face_clusters:
        story.append(Paragraph("No face clusters for this profile.", S["body"]))
    else:
        data = [[
            Paragraph("#", S["th"]),
            Paragraph("Label", S["th"]),
            Paragraph("Appearances", S["th"]),
            Paragraph("Post IDs", S["th"]),
            Paragraph("Created", S["th"]),
        ]]
        for i, fc in enumerate(face_clusters, 1):
            data.append(
                [
                    Paragraph(str(i), S["td_c"]),
                    Paragraph(_esc(fc.get("person_label") or f"Person {fc.get('id')}"), S["td"]),
                    Paragraph(str(fc.get("appearance_count") or 0), S["td_c"]),
                    Paragraph(_esc(_clip(fc.get("post_ids"), 60)), S["td"]),
                    Paragraph(_esc(str(fc.get("created_at") or "—")[:19]), S["td_c"]),
                ]
            )
        t = Table(data, colWidths=[10 * mm, 45 * mm, 28 * mm, 55 * mm, 32 * mm])
        t.setStyle(_table_style())
        story.append(t)
    story.append(Spacer(1, 8 * mm))
    story.append(HRFlowable(width="100%", thickness=0.6, color=C_BORDER, spaceAfter=6))
    story.append(Paragraph(f"{disc_sec} / DISCLAIMER", S["section"]))
    disc_blurb = section_meaning("12") or (
        "Legal and operational limits of this report: open-source / session-authenticated "
        "data only, point-in-time, not legal advice, authorized use required."
    )
    story.append(Paragraph(_esc(disc_blurb), S["meaning"]))
    story.append(
        Paragraph(
            "This report is a full dump of locally collected open-source / session-authenticated "
            "social data for authorized investigative or educational use. It is point-in-time, "
            "may be incomplete, and is not legal advice. Comply with applicable law and platform terms.",
            S["body"],
        )
    )
    return story


def _telegram_text_metrics(db_file: str, profile_id: int) -> dict:
    """Activity / word / search payloads for Telegram PDF+JSON reports."""
    try:
        from platforms.telegram.text_metrics import (
            get_activity_metrics,
            get_word_stats,
            search_word,
        )
    except ImportError:
        return {"activity": None, "word_stats": None, "word_searches": []}

    activity = get_activity_metrics(db_file, profile_id)
    word_stats = get_word_stats(db_file, profile_id, sender="All", limit=40)
    searches = []
    for w in (word_stats.get("top_words") or [])[:8]:
        term = w.get("word")
        if not term:
            continue
        result = search_word(db_file, profile_id, term)
        if result.get("total"):
            searches.append(result)
    return {
        "activity": activity,
        "word_stats": word_stats,
        "word_searches": searches,
    }


def gather_report_data(profile_id: int, db_file: str, platform: str = "facebook") -> dict:
    """Collect everything PDF and JSON builders need."""
    if not db_file:
        raise ValueError("db_file required")
    profile = get_profile_summary(db_file, profile_id)
    if not profile or not profile.get("id"):
        raise ValueError(f"Profile {profile_id} not found")
    is_x = platform == "x"
    data = {
        "meta": {
            "platform": platform,
            "tool": "Soclytics",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report_version": 2 if platform in ("telegram", "x") else 1,
        },
        "profile": profile,
        "counts": get_post_type_counts(db_file, profile_id),
        "interactors": [] if is_x else get_all_interactors(db_file, profile_id),
        "top7": [] if is_x else get_top7(db_file, profile_id),
        "coco": {"nodes": [], "edges": []} if is_x else get_cocomment_graph(db_file, profile_id),
        "timeline": (
            _fetch_x_timeline(db_file, profile_id)
            if is_x
            else get_interaction_timeline(db_file, profile_id)
        ),
        "posts": (
            _fetch_x_posts(db_file, profile_id)
            if is_x
            else _fetch_threads_posts(db_file, profile_id)
            if platform == "threads"
            else _fetch_posts(db_file, profile_id)
        ),
        "engagement": None,
        "comments": [] if is_x else _fetch_comment_samples(db_file, profile_id, limit=150),
        "faces": [] if is_x else _face_clusters(db_file, profile_id),
        "activity": None,
        "word_stats": None,
        "word_searches": [],
    }
    if is_x:
        data["engagement"] = _x_engagement_totals(data["posts"])
    else:
        data["engagement"] = _engagement_totals(data["posts"])
    if platform == "telegram":
        data.update(_telegram_text_metrics(db_file, profile_id))
        data["executive_summary"] = compose_executive_summary(data)
    elif platform == "threads":
        from core.engagement_metrics import get_activity_metrics
        data["activity"] = get_activity_metrics(db_file, profile_id)
    return data


def _report_stem(profile: dict, platform: str = "facebook") -> str:
    owner = profile.get("owner_name") or f"profile_{profile.get('id')}"
    return f"report_{platform}_{_safe_name(owner)}_{profile.get('id')}"


def generate_report(
    profile_id: int,
    db_file: str,
    out_path: str | None = None,
    platform: str = "facebook",
) -> str:
    """Build a full PDF for profile_id. Returns absolute path."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    data = gather_report_data(profile_id, db_file, platform=platform)
    profile = data["profile"]
    owner = profile.get("owner_name") or f"profile_{profile_id}"
    if not out_path:
        out_path = os.path.join(REPORTS_DIR, f"{_report_stem(profile, platform)}.pdf")

    S = make_styles()
    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f"Soclytics Full Report — {owner}",
        author="Soclytics",
    )

    story: list = []
    story.extend(build_cover(profile, S, platform=platform))
    if platform == "telegram":
        story.extend(build_executive_summary(data, S))
    story.extend(build_summary(
        profile, data["counts"], data["posts"], data["faces"], data["interactors"], S,
        platform=platform,
    ))
    if platform == "x":
        story.extend(build_x_engagement_mix(data["posts"], S))
        story.extend(build_x_timeline(data["timeline"], S))
        story.extend(build_x_posts(data["posts"], S))
    else:
        story.extend(build_network(data["interactors"], data["coco"], S))
        story.extend(build_interactors(data["interactors"], S))
        story.extend(build_top7_section(data["top7"], S))
        if platform == "threads":
            story.extend(build_threads_posts(data["posts"], S))
        else:
            story.extend(build_posts(
                data["posts"], S,
                tweet_cards=platform in ("facebook", "instagram"),
            ))
        story.extend(build_comments(data["comments"], S))
        story.extend(build_timeline(data["timeline"], S))
        if platform == "telegram":
            story.extend(build_activity_timeline(data.get("activity"), S))
            story.extend(build_word_analysis(data.get("word_stats"), S))
            story.extend(build_word_searcher(data.get("word_searches"), S))
            story.extend(build_faces(data["faces"], S, face_sec="11", disc_sec="12"))
        elif platform == "threads":
            story.extend(build_engagement_activity_timeline(data.get("activity"), S))
            story.extend(build_faces(data["faces"], S, face_sec="09", disc_sec="10"))
        else:
            story.extend(build_faces(data["faces"], S, face_sec="08", disc_sec="09"))

    doc.build(story, onFirstPage=_cover_canvas, onLaterPages=_footer)
    return out_path


def generate_json_report(
    profile_id: int,
    db_file: str,
    out_path: str | None = None,
    platform: str = "facebook",
) -> str:
    """Build a full JSON dump for profile_id. Returns absolute path."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    data = gather_report_data(profile_id, db_file, platform=platform)
    if not out_path:
        out_path = os.path.join(
            REPORTS_DIR, f"{_report_stem(data['profile'], platform)}.json"
        )
    payload = _x_dashboard_payload(data) if platform == "x" else data
    if platform == "threads":
        rows = (data.get("posts") or {}).get("texts") or []
        payload["feed"] = _threads_dashboard_feed(rows)
    elif platform in ("facebook", "instagram"):
        payload["feed"] = _dashboard_feed(data.get("posts") or {})
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    return out_path


def _dashboard_feed(posts: dict) -> dict:
    """Tweet-card JSON for Facebook / Instagram / Threads (no Views)."""
    def item(row: dict) -> dict:
        return {
            "post_url": row.get("url") or row.get("post_url") or row.get("photo_url"),
            "date_text": row.get("date_text"),
            "body": row.get("caption") or row.get("body") or "",
            "image_src": row.get("image_src"),
            "reply_count": int(row.get("reply_count") or 0),
            "repost_count": int(row.get("repost_count") or 0),
            "like_count": int(row.get("like_count") or 0),
        }

    return {
        "photos": [item(r) for r in posts.get("photos") or []],
        "texts": [item(r) for r in posts.get("texts") or []],
    }


def _threads_feed_item(row: dict) -> dict:
    return {
        "post_url": row.get("url") or row.get("post_url"),
        "date_text": row.get("date_text"),
        "body": row.get("caption") or row.get("body") or "",
        "image_src": row.get("image_src"),
        "media_type": row.get("media_type") or ("image" if row.get("image_src") else "text"),
        "source_tab": _threads_tab_kind(row),
        "reply_count": int(row.get("reply_count") or 0),
        "repost_count": int(row.get("repost_count") or 0),
        "like_count": int(row.get("like_count") or 0),
    }


def _threads_dashboard_feed(rows: list) -> dict:
    """JSON feed matching threads/analysis.html profile tabs."""
    return {
        tab: [_threads_feed_item(r) for r in _posts_for_threads_tab(rows, tab)]
        for tab in THREADS_PROFILE_TABS
    }


def _x_dashboard_payload(data: dict) -> dict:
    """JSON matches the X analysis dashboard: header, mix, timeline, tweet feed."""
    profile = data.get("profile") or {}
    eng = data.get("engagement") or _x_engagement_totals(data.get("posts") or {})
    feed = []
    for t in (data.get("posts") or {}).get("texts") or []:
        feed.append({
            "post_url": t.get("url") or t.get("post_url"),
            "date_text": t.get("date_text"),
            "body": t.get("caption") or t.get("body"),
            "image_src": t.get("image_src"),
            "media_type": t.get("media_type") or ("image" if t.get("image_src") else "text"),
            "reply_count": int(t.get("reply_count") or 0),
            "repost_count": int(t.get("repost_count") or 0),
            "like_count": int(t.get("like_count") or 0),
            "view_count": int(t.get("view_count") or 0),
        })
    timeline = []
    for r in data.get("timeline") or []:
        timeline.append({
            "date": r.get("date"),
            "reply": int(r.get("reply") or r.get("replies") or 0),
            "repost": int(r.get("repost") or r.get("reposts") or 0),
            "like": int(r.get("like") or r.get("likes") or 0),
            "view": int(r.get("view") or r.get("views") or 0),
        })
    return {
        "meta": data.get("meta"),
        "profile": {
            "id": profile.get("id"),
            "owner_name": profile.get("owner_name"),
            "profile_url": profile.get("profile_url"),
            "is_locked": profile.get("is_locked"),
            "scraped_at": profile.get("scraped_at"),
            "fields": profile.get("fields") or [],
        },
        "engagement": eng,
        "timeline": timeline,
        "posts": feed,
    }


def generate_all_reports(
    db_file: str,
    formats: tuple = ("pdf", "json"),
    platform: str = "facebook",
) -> list:
    """Regenerate PDF and/or JSON for every profile in the database."""
    con = sqlite3.connect(db_file)
    ids = [r[0] for r in con.execute("SELECT id FROM profiles ORDER BY id").fetchall()]
    con.close()
    results = []
    for pid in ids:
        entry = {"profile_id": pid, "pdf": None, "json": None, "error": None}
        try:
            if "pdf" in formats:
                entry["pdf"] = generate_report(pid, db_file=db_file, platform=platform)
            if "json" in formats:
                entry["json"] = generate_json_report(pid, db_file=db_file, platform=platform)
        except Exception as e:
            entry["error"] = str(e)
        results.append(entry)
    return results
