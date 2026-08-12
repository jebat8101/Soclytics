"""
Telegram collector for Soclytics.

Primary: Telethon (MTProto) — channel posts with discussion-group comments,
group activity bucketed by day, named reactors, forward sources, mentions,
the admin roster and profile photos. This is the only path that yields real
interactor identities for the graph.

Fallback: the public web preview at https://t.me/s/<name> — posts, media and
view counts without login. Commenters are not exposed there, so the interactor
graph is limited to forward sources, reply targets and @mentions.

Outputs JSON compatible with socmint_lite_db (about / photos / reels / posts).
Authorized use only — public/visible data; operator-supplied session when used.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, timezone

import requests

from core.urls import extract_telegram_username, normalize_telegram_target

from platforms.telegram.constants import (
    BASE_DIR, ROOT_DIR, ABOUT_OUT, PHOTOS_OUT, REELS_OUT, POSTS_OUT,
    TEXT_DIR, MEDIA_DIR, CONFIG_CANDIDATES as _CFG_CANDIDATES,
)

# Re-export for login script compatibility
CONFIG_CANDIDATES = _CFG_CANDIDATES

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

MAX_COMMENTS_PER_POST = 40
MAX_PREVIEW_PAGES = 12
# Peer lookups cost API calls, so reactors / forwards / id-mentions share a budget
MAX_PEER_LOOKUPS = 120
MAX_ADMINS = 25
MAX_DAY_TRANSCRIPT_LINES = 250
MAX_TRANSCRIPT_CHARS = 8000
MAX_COMMENT_CHARS = 400
# A group message per post gives one interactor per post, which produces no
# co-occurrence at all. Scanning wider and bucketing by day fixes that.
GROUP_SCAN_FACTOR = 25
CHANNEL_SCAN_FACTOR = 3
MAX_SCAN_WINDOW = 500

RE_MENTION = re.compile(r"(?<![\w@/])@([A-Za-z][A-Za-z0-9_]{4,31})")



class TelegramAuthError(RuntimeError):
    """Raised when API credentials or the session file are unusable."""


# ─────────────────────────────────────────────────────────────
#  Config / availability
# ─────────────────────────────────────────────────────────────

def telethon_available() -> bool:
    try:
        import telethon  # noqa: F401
        return True
    except Exception:
        return False


def load_config() -> dict | None:
    """
    Resolve api_id / api_hash / session from TG_* env vars or a JSON config.

    Session names are resolved relative to the config file that declared them,
    so an existing telegram_osint setup keeps working untouched.
    """
    api_id = os.environ.get("TG_API_ID")
    api_hash = os.environ.get("TG_API_HASH")
    session = os.environ.get("TG_SESSION")
    source = "environment"

    if not (api_id and api_hash):
        for path in CONFIG_CANDIDATES:
            if not path or not os.path.exists(path):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                continue
            if not isinstance(cfg, dict):
                continue
            # placeholder configs exist purely to keep the Docker mount a file,
            # so keep scanning until one actually carries credentials
            found_id = api_id or cfg.get("api_id")
            found_hash = api_hash or cfg.get("api_hash")
            if not (found_id and found_hash):
                continue
            api_id, api_hash = found_id, found_hash
            session = session or cfg.get("session_name") or cfg.get("session")
            source = path
            break

    if not (api_id and api_hash):
        return None
    try:
        api_id = int(api_id)
    except (TypeError, ValueError):
        return None

    session = session or "birdy_tg"
    if not os.path.isabs(session):
        anchor = os.path.dirname(source) if os.path.exists(source) else BASE_DIR
        session = os.path.join(anchor, session)

    return {
        "api_id": api_id,
        "api_hash": str(api_hash),
        "session": session,
        "source": source,
    }


def _session_file_exists(session_path: str) -> bool:
    return os.path.exists(session_path) or os.path.exists(session_path + ".session")


# ─────────────────────────────────────────────────────────────
#  Shared helpers
# ─────────────────────────────────────────────────────────────

def _safe(token) -> str:
    return re.sub(r"[^\w.-]+", "_", str(token))[:80]


def _rel_under_app(path: str | None) -> str | None:
    """Store media/caption paths relative to app/ so Flask routes can resolve them."""
    if not path:
        return path
    if not os.path.isabs(path):
        return path.replace("\\", "/")
    try:
        rel = os.path.relpath(path, BASE_DIR)
    except ValueError:
        return path
    return rel.replace("\\", "/")


def _write_caption_txt(code, caption) -> str:
    os.makedirs(TEXT_DIR, exist_ok=True)
    path = os.path.join(TEXT_DIR, f"telegram_{_safe(code)}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(caption or "")
    return _rel_under_app(path)


def _field(label, value, field_type="name", sub_label=None) -> dict:
    return {
        "field_type": field_type,
        "label": label,
        "value": "" if value is None else str(value),
        "sub_label": sub_label,
    }


def _engagement_caption(text: str, eng: dict) -> str:
    parts = []
    if eng.get("views"):
        parts.append(f"👁 {eng['views']}")
    if eng.get("reply_count"):
        parts.append(f"💬 {eng['reply_count']}")
    if eng.get("forwards"):
        parts.append(f"🔁 {eng['forwards']}")
    if eng.get("reactions"):
        parts.append(f"❤️ {eng['reactions']}")
    text = (text or "").strip()
    if not parts:
        return text
    return f"{text}\n\n[engagement] {' · '.join(parts)}".strip()


def _download_file(url: str, dest: str) -> str | None:
    if not url or not str(url).startswith("http"):
        return None
    try:
        os.makedirs(MEDIA_DIR, exist_ok=True)
        if os.path.exists(dest) and os.path.getsize(dest) > 500:
            return _rel_under_app(dest)
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=40)
        if r.status_code != 200 or len(r.content) < 200:
            return None
        with open(dest, "wb") as f:
            f.write(r.content)
        return _rel_under_app(dest)
    except Exception:
        return None


def _dedupe_comments(comments: list) -> list:
    seen, out = set(), []
    for c in comments:
        key = (c.get("profile_url"), (c.get("comment_text") or "")[:120])
        if not c.get("profile_url") or key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


# ─────────────────────────────────────────────────────────────
#  Telethon (MTProto) path
# ─────────────────────────────────────────────────────────────

def _peer_identity(peer) -> dict | None:
    """Map a Telethon User/Channel to the {name, profile_url} the DB expects."""
    if peer is None:
        return None
    username = getattr(peer, "username", None)
    if getattr(peer, "first_name", None) is not None or getattr(peer, "bot", False):
        name = " ".join(
            p for p in (getattr(peer, "first_name", ""), getattr(peer, "last_name", "")) if p
        ).strip()
        name = name or username or f"user{peer.id}"
        url = f"https://t.me/{username}" if username else f"tg://user?id={peer.id}"
    else:
        name = getattr(peer, "title", None) or username or f"peer{peer.id}"
        url = f"https://t.me/{username}" if username else f"tg://channel?id={peer.id}"
    return {"name": name, "profile_url": url}


def _entity_kind(entity) -> str:
    if getattr(entity, "broadcast", False):
        return "Channel"
    if getattr(entity, "megagroup", False):
        return "Supergroup"
    if getattr(entity, "bot", False):
        return "Bot"
    if getattr(entity, "first_name", None) is not None:
        return "User"
    return "Group"


def _message_engagement(msg) -> dict:
    reactions = 0
    results = getattr(getattr(msg, "reactions", None), "results", None) or []
    for r in results:
        reactions += getattr(r, "count", 0) or 0
    return {
        "views": getattr(msg, "views", None),
        "forwards": getattr(msg, "forwards", None),
        "reply_count": getattr(getattr(msg, "replies", None), "replies", None),
        "reactions": reactions or None,
    }


def _media_kind(msg) -> str:
    """Classify a message without downloading anything."""
    if getattr(msg, "photo", None):
        return "photo"
    if getattr(msg, "video", None) or getattr(msg, "video_note", None) or getattr(msg, "gif", None):
        return "reel"
    doc = getattr(msg, "document", None)
    if doc is not None and str(getattr(doc, "mime_type", "")).startswith("image/"):
        return "photo"
    return "text"


async def _download_message_media(client, msg, username) -> str | None:
    os.makedirs(MEDIA_DIR, exist_ok=True)
    dest = os.path.join(MEDIA_DIR, f"telegram_{_safe(username)}_{msg.id}.jpg")
    if os.path.exists(dest) and os.path.getsize(dest) > 500:
        return _rel_under_app(dest)
    try:
        if _media_kind(msg) == "reel":
            # thumbnail only — full videos are large and add nothing to face work
            path = await client.download_media(msg, file=dest, thumb=-1)
        else:
            path = await client.download_media(msg, file=dest)
        return _rel_under_app(path or dest) if path or os.path.exists(dest) else None
    except Exception as e:
        print(f"   media {msg.id}: {e}")
        return None


async def _resolve_peer(client, peer, cache: dict, budget: dict):
    """Resolve a peer to an entity, caching results and bounding API calls."""
    if peer is None:
        return None
    key = str(peer)
    if key in cache:
        return cache[key]
    if budget["left"] <= 0:
        return None
    budget["left"] -= 1
    try:
        entity = await client.get_entity(peer)
    except Exception:
        entity = None
    cache[key] = entity
    return entity


async def _reaction_interactors(client, msg, cache, budget) -> list:
    """
    Named reactors, when Telegram exposes them.

    Reaction totals are always visible but identities only come through
    recent_reactions, which Telegram populates for non-anonymous reactions.
    """
    reactions = getattr(msg, "reactions", None)
    recent = getattr(reactions, "recent_reactions", None) or []
    out = []
    for item in recent:
        entity = await _resolve_peer(client, getattr(item, "peer_id", None), cache, budget)
        ident = _peer_identity(entity)
        if not ident:
            continue
        emoji = getattr(getattr(item, "reaction", None), "emoticon", "") or ""
        out.append({
            **ident,
            "comment_text": f"Reacted {emoji}".strip(),
            "interaction_type": "reaction",
        })
    return out


async def _forward_interactors(client, msg, cache, budget) -> list:
    """Whoever a post was forwarded from — an amplification edge."""
    fwd = getattr(msg, "fwd_from", None)
    if not fwd:
        return []
    entity = await _resolve_peer(client, getattr(fwd, "from_id", None), cache, budget)
    ident = _peer_identity(entity)
    if not ident:
        name = getattr(fwd, "from_name", None)
        if not name:
            return []
        ident = {"name": name, "profile_url": f"tg://forward?name={_safe(name)}"}
    return [{
        **ident,
        "comment_text": f"Original author of forwarded message {msg.id}",
        "interaction_type": "forward_source",
    }]


async def _mention_interactors(client, msg, self_username, cache, budget) -> list:
    """@handles in the text, plus inline mentions of users who have no handle."""
    from telethon.tl.types import MessageEntityMentionName

    text = (getattr(msg, "message", None) or "").strip()
    out = []
    for handle in dict.fromkeys(RE_MENTION.findall(text)):
        if self_username and handle.lower() == self_username.lower():
            continue
        out.append({
            "name": f"@{handle}",
            "profile_url": f"https://t.me/{handle}",
            "comment_text": f"Mentioned in message {msg.id}",
            "interaction_type": "mention",
        })
    for entity_ref in (getattr(msg, "entities", None) or []):
        if not isinstance(entity_ref, MessageEntityMentionName):
            continue
        peer = await _resolve_peer(client, entity_ref.user_id, cache, budget)
        ident = _peer_identity(peer)
        if ident:
            out.append({
                **ident,
                "comment_text": f"Mentioned in message {msg.id}",
                "interaction_type": "mention",
            })
    return out


async def _extra_interactors(client, msg, self_username, cache, budget) -> list:
    """Reactors, forward source and mentions — signals beyond the author."""
    found = []
    found += await _reaction_interactors(client, msg, cache, budget)
    found += await _forward_interactors(client, msg, cache, budget)
    found += await _mention_interactors(client, msg, self_username, cache, budget)
    return found


async def _admin_fields(client, entity) -> list:
    """The admin roster is small, bounded, and names the people who matter."""
    from telethon.tl.types import ChannelParticipantsAdmins

    try:
        admins = await client.get_participants(
            entity, filter=ChannelParticipantsAdmins, limit=MAX_ADMINS
        )
    except Exception as e:
        detail = "requires admin rights" if "admin privileges" in str(e) else str(e)
        print(f"   Admin roster not visible ({detail})")
        return []
    fields = []
    for admin in admins:
        ident = _peer_identity(admin)
        if ident:
            fields.append(_field(ident["name"], ident["profile_url"], sub_label="Administrator"))
    if fields:
        print(f"   Admins listed: {len(fields)}")
    return fields


async def _sender_avatar_photos(client, profile_url, counts, entities, budget) -> list:
    """
    Profile photos of the most active interactors.

    Message media alone rarely shows the participants themselves, so this is
    what makes face clustering useful on a chat.
    """
    photos = []
    for url, hits in counts.most_common():
        if len(photos) >= budget:
            break
        entity = entities.get(url)
        if entity is None:
            continue
        dest = os.path.join(MEDIA_DIR, f"telegram_avatar_{_safe(url)}.jpg")
        try:
            os.makedirs(MEDIA_DIR, exist_ok=True)
            path = await client.download_profile_photo(entity, file=dest)
        except Exception:
            path = None
        if not path:
            continue
        ident = _peer_identity(entity) or {"name": url}
        photos.append({
            "photo_url": f"{profile_url}#avatar-{_safe(url)}",
            "date": None,
            "image_src": _rel_under_app(path),
            "caption": f"Profile photo of {ident['name']} — {hits} "
                       f"interaction{'s' if hits != 1 else ''} in this chat",
            "comments": [],
        })
    if photos:
        print(f"   Interactor avatars: {len(photos)}")
    return photos


async def _channel_comments(client, entity, msg, limit=MAX_COMMENTS_PER_POST,
                            entities=None) -> list:
    """Replies from the linked discussion group — the real interactor source."""
    replies = getattr(msg, "replies", None)
    if not replies or not getattr(replies, "comments", False):
        return []
    out = []
    try:
        async for reply in client.iter_messages(entity, reply_to=msg.id, limit=limit):
            sender = await reply.get_sender()
            ident = _peer_identity(sender)
            if not ident:
                continue
            if entities is not None:
                _remember(entities, ident, sender)
            out.append({
                **ident,
                "comment_text": (reply.message or "").strip(),
                "interaction_type": "comment",
            })
    except Exception as e:
        print(f"   comments {msg.id}: {e}")
    return _dedupe_comments(out)


async def _about_from_entity(client, entity, profile_url, username, mode) -> dict:
    from telethon.tl.functions.channels import GetFullChannelRequest
    from telethon.tl.functions.users import GetFullUserRequest

    kind = _entity_kind(entity)
    title = (
        getattr(entity, "title", None)
        or " ".join(
            p for p in (getattr(entity, "first_name", ""), getattr(entity, "last_name", "")) if p
        ).strip()
        or username
    )

    description = ""
    members = None
    linked_chat = None
    try:
        if kind in ("Channel", "Supergroup", "Group"):
            full = await client(GetFullChannelRequest(entity))
            description = getattr(full.full_chat, "about", "") or ""
            members = getattr(full.full_chat, "participants_count", None)
            linked_chat = getattr(full.full_chat, "linked_chat_id", None)
        else:
            full = await client(GetFullUserRequest(entity))
            description = getattr(getattr(full, "full_user", None), "about", "") or ""
    except Exception as e:
        print(f"   full-entity lookup failed: {e}")

    avatar_path = None
    try:
        os.makedirs(MEDIA_DIR, exist_ok=True)
        avatar_path = await client.download_profile_photo(
            entity, file=os.path.join(MEDIA_DIR, f"telegram_{_safe(username)}_avatar.jpg")
        )
    except Exception:
        pass

    created = getattr(entity, "date", None)

    details = [
        _field("Username", f"@{username}"),
        _field("Telegram ID", getattr(entity, "id", "")),
        _field("Account Type", kind),
    ]
    if members is not None:
        details.append(_field("Subscribers" if kind == "Channel" else "Members", members))
    if getattr(entity, "verified", False):
        details.append(_field("Verified", "Yes"))
    if getattr(entity, "scam", False):
        details.append(_field("Flagged", "Marked as scam by Telegram"))
    if getattr(entity, "fake", False):
        details.append(_field("Flagged", "Marked as fake by Telegram"))
    if getattr(entity, "restricted", False):
        details.append(_field("Restricted", "Yes"))
    if linked_chat:
        details.append(_field("Linked Discussion Group", linked_chat))
    if created:
        details.append(_field("Created", created.strftime("%Y-%m-%d")))
    if avatar_path:
        details.append(_field("Avatar", avatar_path))

    sections = {
        "directory_names": [_field("Full Name", title)],
        "directory_personal_details": details,
        "overview": [
            _field("Profile Link", profile_url, field_type="link"),
            _field("Collection Mode", mode),
        ],
    }
    if description:
        sections["directory_intro"] = [
            _field("Biography" if kind in ("User", "Bot") else "Description",
                   description, field_type="intro")
        ]

    return {
        "profile_url": profile_url,
        "owner_name": title,
        "is_locked": bool(getattr(entity, "restricted", False)),
        "platform": "telegram",
        "sections": sections,
    }


async def _collect_user_photos(client, entity, profile_url, username, max_photos) -> list:
    """Users have no public feed — their profile photo history is the usable trail."""
    photos = []
    try:
        os.makedirs(MEDIA_DIR, exist_ok=True)
        async for pic in client.iter_profile_photos(entity, limit=max_photos):
            dest = os.path.join(MEDIA_DIR, f"telegram_{_safe(username)}_pp{pic.id}.jpg")
            path = await client.download_media(pic, file=dest)
            if not path:
                continue
            photos.append({
                "photo_url": f"{profile_url}#photo{pic.id}",
                "date": pic.date.strftime("%Y-%m-%d") if getattr(pic, "date", None) else None,
                "image_src": _rel_under_app(path),
                "caption": f"Profile photo of @{username}",
                "comments": [],
            })
    except Exception as e:
        print(f"   profile photos: {e}")
    return photos


def _has_room(kind: str, photos: list, reels: list, max_photos: int, max_reels: int) -> bool:
    """Only download media the matching bucket can still hold."""
    if kind == "photo":
        return len(photos) < max_photos
    if kind == "reel":
        return len(reels) < max_reels
    return False


def _remember(entities: dict, ident: dict | None, entity) -> None:
    if ident and entity is not None:
        entities.setdefault(ident["profile_url"], entity)


def _absorb(people: dict, ident: dict | None, text: str, interaction_type: str) -> None:
    """Merge one person's activity within a day thread into a single row."""
    if not ident or not ident.get("profile_url"):
        return
    entry = people.setdefault(
        ident["profile_url"], {"ident": ident, "texts": [], "type": interaction_type}
    )
    if interaction_type == "message":
        entry["type"] = "message"  # speaking outranks a reaction or mention
    if text:
        entry["texts"].append(text)


def _tally(items: list) -> Counter:
    counts = Counter()
    for item in items:
        for comment in item.get("comments") or []:
            counts[comment["profile_url"]] += 1
    return counts


async def _channel_items(client, entity, username, profile_url, messages,
                         max_posts, max_photos, max_reels, cache, budget, entities):
    """One post per channel message, with its discussion-group commenters."""
    photos, reels, posts = [], [], []

    for msg in messages:
        if len(photos) >= max_photos and len(reels) >= max_reels and len(posts) >= max_posts:
            break
        kind = _media_kind(msg)
        text = (msg.message or "").strip()
        if kind == "text" and not text:
            continue

        comments = await _channel_comments(client, entity, msg, entities=entities)
        comments += await _extra_interactors(client, msg, username, cache, budget)
        comments = _dedupe_comments(comments)[:MAX_COMMENTS_PER_POST]

        post_url = f"https://t.me/{username}/{msg.id}"
        date = msg.date.strftime("%Y-%m-%d") if msg.date else None
        caption = _engagement_caption(text, _message_engagement(msg))

        path = None
        if _has_room(kind, photos, reels, max_photos, max_reels):
            path = await _download_message_media(client, msg, username)

        if path and kind == "photo" and len(photos) < max_photos:
            photos.append({"photo_url": post_url, "date": date, "image_src": path,
                           "caption": caption, "comments": comments})
        elif path and kind == "reel" and len(reels) < max_reels:
            reels.append({"reel_url": post_url, "date": date, "image_src": path,
                          "caption": caption, "comments": comments})
        elif len(posts) < max_posts:
            posts.append({"post_url": post_url, "date": date,
                          "screenshot_path": _write_caption_txt(f"{username}_{msg.id}", caption),
                          "comments": comments})

    return photos, reels, posts


async def _group_items(client, entity, username, profile_url, messages,
                       max_posts, max_photos, max_reels, cache, budget, entities):
    """
    Group activity bucketed into one post per day.

    A post per message would put a single sender on each post and produce no
    co-occurrence, so text traffic is threaded by day while media keeps its own
    post (face clustering needs the individual image).
    """
    replies_by_parent = defaultdict(list)
    for msg in messages:
        parent = getattr(getattr(msg, "reply_to", None), "reply_to_msg_id", None)
        if parent:
            replies_by_parent[parent].append(msg)

    photos, reels = [], []
    by_day = OrderedDict()

    for msg in messages:  # newest first
        kind = _media_kind(msg)
        text = (msg.message or "").strip()
        if kind == "text" and not text:
            continue

        date = msg.date.strftime("%Y-%m-%d") if msg.date else None
        sender = await msg.get_sender()
        ident = _peer_identity(sender)
        _remember(entities, ident, sender)
        extras = await _extra_interactors(client, msg, username, cache, budget)

        replies = []
        for reply in replies_by_parent.get(msg.id, []):
            reply_sender = await reply.get_sender()
            reply_ident = _peer_identity(reply_sender)
            if not reply_ident:
                continue
            _remember(entities, reply_ident, reply_sender)
            replies.append({
                **reply_ident,
                "comment_text": (reply.message or "").strip(),
                "interaction_type": "reply",
            })

        if _has_room(kind, photos, reels, max_photos, max_reels):
            path = await _download_message_media(client, msg, username)
            if path:
                comments = []
                if ident:
                    comments.append({**ident, "comment_text": text or "[media]",
                                     "interaction_type": "message"})
                comments = _dedupe_comments(comments + replies + extras)[:MAX_COMMENTS_PER_POST]
                item = {
                    "date": date,
                    "image_src": path,
                    "caption": _engagement_caption(text, _message_engagement(msg)),
                    "comments": comments,
                }
                url = f"https://t.me/{username}/{msg.id}"
                if kind == "photo" and len(photos) < max_photos:
                    photos.append({"photo_url": url, **item})
                    continue
                if kind == "reel" and len(reels) < max_reels:
                    reels.append({"reel_url": url, **item})
                    continue

        if not date:
            continue
        bucket = by_day.setdefault(date, {"lines": [], "people": OrderedDict()})
        stamp = msg.date.strftime("%H:%M") if msg.date else ""
        who = ident["name"] if ident else "unknown"
        bucket["lines"].append(f"[{msg.id}] {stamp} {who}: {text or '[media]'}")
        _absorb(bucket["people"], ident, text, "message")
        for extra in replies + extras:
            _absorb(bucket["people"], extra, extra["comment_text"], extra["interaction_type"])

    posts = []
    for date in list(by_day)[:max_posts]:
        bucket = by_day[date]
        lines = list(reversed(bucket["lines"]))[:MAX_DAY_TRANSCRIPT_LINES]
        body = "\n".join(lines)[:MAX_TRANSCRIPT_CHARS]
        comments = [{
            **entry["ident"],
            "comment_text": " | ".join(entry["texts"])[:MAX_COMMENT_CHARS],
            "interaction_type": entry["type"],
        } for entry in bucket["people"].values()][:MAX_COMMENTS_PER_POST]
        posts.append({
            "post_url": f"https://t.me/{username}#day-{date}",
            "date": date,
            "screenshot_path": _write_caption_txt(f"{username}_{date}", body or date),
            "comments": comments,
        })
    if posts:
        print(f"   Day threads: {len(posts)} of {len(by_day)} active days")
    return photos, reels, posts


async def _telethon_collect(username, profile_url, max_posts, max_photos, max_reels):
    from telethon import TelegramClient

    cfg = load_config()
    if not cfg:
        raise TelegramAuthError(
            "No Telegram API credentials — set TG_API_ID / TG_API_HASH "
            "or create app/telegram_config.json"
        )
    if not _session_file_exists(cfg["session"]):
        raise TelegramAuthError(
            f"Telethon session not found at {cfg['session']}.session — "
            "authorize once with the Telegram CLI tool, then retry"
        )

    client = TelegramClient(cfg["session"], cfg["api_id"], cfg["api_hash"],
                            flood_sleep_threshold=60)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise TelegramAuthError(
                "Telethon session is not authorized — log in once outside the web UI"
            )

        entity = await client.get_entity(username)
        about = await _about_from_entity(client, entity, profile_url, username, "MTProto (Telethon)")
        kind = _entity_kind(entity)

        if kind in ("User", "Bot"):
            photos = await _collect_user_photos(client, entity, profile_url, username, max_photos)
            return about, photos, [], []

        is_group = kind in ("Supergroup", "Group")
        factor = GROUP_SCAN_FACTOR if is_group else CHANNEL_SCAN_FACTOR
        window = min(max(max_posts, max_photos, max_reels) * factor, MAX_SCAN_WINDOW)
        messages = []
        async for msg in client.iter_messages(entity, limit=window):
            messages.append(msg)
        print(f"   Scanned {len(messages)} messages ({kind.lower()}, window {window})")

        cache, budget, entities = {}, {"left": MAX_PEER_LOOKUPS}, {}
        builder = _group_items if is_group else _channel_items
        photos, reels, posts = await builder(
            client, entity, username, profile_url, messages,
            max_posts, max_photos, max_reels, cache, budget, entities,
        )

        # peers resolved for reactions / forwards / mentions can also be ranked
        for resolved in cache.values():
            _remember(entities, _peer_identity(resolved), resolved)

        counts = _tally(photos + reels + posts)
        photos += await _sender_avatar_photos(
            client, profile_url, counts, entities, max(3, max_photos // 2)
        )

        admin_fields = await _admin_fields(client, entity)
        if admin_fields:
            about["sections"]["administrators"] = admin_fields

        names = {c["profile_url"]: c["name"]
                 for item in photos + reels + posts for c in (item.get("comments") or [])}
        roster = [
            _field(names.get(url, url), f"{hits} interaction" + ("s" if hits != 1 else ""),
                   sub_label=url)
            for url, hits in counts.most_common(15)
        ]
        if roster:
            about["sections"]["active_participants"] = roster

        return about, photos, reels, posts
    finally:
        await client.disconnect()


# ─────────────────────────────────────────────────────────────
#  Public web-preview path (no login)
# ─────────────────────────────────────────────────────────────

def _bg_image_url(style: str) -> str | None:
    m = re.search(r"url\(['\"]?(https?://[^'\")]+)['\"]?\)", style or "")
    return m.group(1) if m else None


def _preview_about(soup, profile_url, username) -> dict:
    info = soup.select_one("div.tgme_channel_info")
    title = username
    description = ""
    counters = []
    avatar_url = None

    if info:
        node = info.select_one(".tgme_channel_info_header_title")
        if node:
            title = node.get_text(" ", strip=True) or username
        node = info.select_one(".tgme_channel_info_description")
        if node:
            description = node.get_text("\n", strip=True)
        for c in info.select(".tgme_channel_info_counter"):
            value = c.select_one(".counter_value")
            ctype = c.select_one(".counter_type")
            if value and ctype:
                counters.append((ctype.get_text(strip=True).title(),
                                 value.get_text(strip=True)))
        img = info.select_one("img")
        if img:
            avatar_url = img.get("src")
    else:
        node = soup.select_one("div.tgme_page_title span")
        if node:
            title = node.get_text(" ", strip=True) or username
        node = soup.select_one("div.tgme_page_description")
        if node:
            description = node.get_text("\n", strip=True)

    avatar_path = None
    if avatar_url:
        avatar_path = _download_file(
            avatar_url, os.path.join(MEDIA_DIR, f"telegram_{_safe(username)}_avatar.jpg")
        )

    details = [_field("Username", f"@{username}")]
    for label, value in counters:
        details.append(_field(label, value))
    if avatar_path:
        details.append(_field("Avatar", avatar_path))

    sections = {
        "directory_names": [_field("Full Name", title)],
        "directory_personal_details": details,
        "overview": [
            _field("Profile Link", profile_url, field_type="link"),
            _field("Collection Mode", "Public web preview (no commenter identities)"),
        ],
    }
    if description:
        sections["directory_intro"] = [_field("Description", description, field_type="intro")]

    return {
        "profile_url": profile_url,
        "owner_name": title,
        "is_locked": info is None,
        "platform": "telegram",
        "sections": sections,
    }


def _preview_message(node, username) -> dict | None:
    post = node.get("data-post") or ""
    msg_id = post.split("/")[-1] if "/" in post else None
    if not msg_id or not msg_id.isdigit():
        return None

    text_node = node.select_one("div.tgme_widget_message_text")
    text = text_node.get_text("\n", strip=True) if text_node else ""

    time_node = node.select_one("div.tgme_widget_message_info time") or node.select_one("time")
    date = None
    if time_node and time_node.get("datetime"):
        try:
            date = datetime.fromisoformat(
                time_node["datetime"].replace("Z", "+00:00")
            ).strftime("%Y-%m-%d")
        except ValueError:
            date = time_node["datetime"][:10]

    views_node = node.select_one("span.tgme_widget_message_views")
    eng = {"views": views_node.get_text(strip=True) if views_node else None}
    reaction_nodes = node.select("span.tgme_widget_message_reactions_count") or node.select(
        "span.tgme_reactions_count"
    )
    if reaction_nodes:
        eng["reactions"] = " ".join(n.get_text(strip=True) for n in reaction_nodes if n.get_text(strip=True))

    image_url = None
    bucket = "text"
    photo = node.select_one("a.tgme_widget_message_photo_wrap")
    if photo:
        image_url = _bg_image_url(photo.get("style", ""))
        bucket = "photo"
    if not image_url:
        video = (node.select_one("i.tgme_widget_message_video_thumb")
                 or node.select_one("i.tgme_widget_message_roundvideo_thumb"))
        if video:
            image_url = _bg_image_url(video.get("style", ""))
            bucket = "reel"

    comments = []
    fwd = node.select_one("a.tgme_widget_message_forwarded_from_name")
    if fwd and fwd.get("href"):
        src_user = extract_telegram_username(fwd["href"])
        if src_user:
            comments.append({
                "name": fwd.get_text(" ", strip=True) or src_user,
                "profile_url": f"https://t.me/{src_user}",
                "comment_text": f"Forwarded source of post {msg_id}",
                "interaction_type": "forward_source",
            })
    reply = node.select_one("a.tgme_widget_message_reply")
    if reply and reply.get("href"):
        target = extract_telegram_username(reply["href"])
        author = reply.select_one("span.tgme_widget_message_author_name")
        if target and target.lower() != username.lower():
            comments.append({
                "name": author.get_text(" ", strip=True) if author else target,
                "profile_url": f"https://t.me/{target}",
                "comment_text": f"Replied to by post {msg_id}",
                "interaction_type": "reply_target",
            })
    # @handles are the only interactor signal the preview gives away for free
    for handle in dict.fromkeys(RE_MENTION.findall(text)):
        if handle.lower() == username.lower():
            continue
        comments.append({
            "name": f"@{handle}",
            "profile_url": f"https://t.me/{handle}",
            "comment_text": f"Mentioned in post {msg_id}",
            "interaction_type": "mention",
        })

    return {
        "id": int(msg_id),
        "url": f"https://t.me/{username}/{msg_id}",
        "date": date,
        "caption": _engagement_caption(text, eng),
        "image_url": image_url,
        "bucket": bucket,
        "comments": comments,
    }


def _public_collect(username, profile_url, max_posts, max_photos, max_reels):
    from bs4 import BeautifulSoup

    sess = requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})

    about = None
    parsed, seen_ids = [], set()
    before = None
    wanted = max_posts + max_photos + max_reels

    for _ in range(MAX_PREVIEW_PAGES):
        url = f"https://t.me/s/{username}"
        if before:
            url += f"?before={before}"
        try:
            r = sess.get(url, timeout=40)
        except Exception as e:
            print(f"   preview fetch failed: {e}")
            break
        if r.status_code != 200:
            print(f"   preview HTTP {r.status_code}")
            break

        soup = BeautifulSoup(r.text, "html.parser")
        if about is None:
            about = _preview_about(soup, profile_url, username)

        nodes = soup.select("div.tgme_widget_message")
        if not nodes:
            break
        page_ids = []
        for node in nodes:
            item = _preview_message(node, username)
            if not item or item["id"] in seen_ids:
                continue
            seen_ids.add(item["id"])
            page_ids.append(item["id"])
            parsed.append(item)
        if not page_ids or len(parsed) >= wanted:
            break
        before = min(page_ids)

    if about is None:
        raise RuntimeError(f"Telegram preview unavailable for @{username}")

    parsed.sort(key=lambda x: x["id"], reverse=True)
    photos, reels, posts = [], [], []
    for item in parsed:
        if item["bucket"] == "photo" and len(photos) < max_photos:
            dest = os.path.join(MEDIA_DIR, f"telegram_{_safe(username)}_{item['id']}.jpg")
            photos.append({
                "photo_url": item["url"],
                "date": item["date"],
                "image_src": _download_file(item["image_url"], dest),
                "caption": item["caption"],
                "comments": item["comments"],
            })
        elif item["bucket"] == "reel" and len(reels) < max_reels:
            dest = os.path.join(MEDIA_DIR, f"telegram_{_safe(username)}_{item['id']}.jpg")
            reels.append({
                "reel_url": item["url"],
                "date": item["date"],
                "image_src": _download_file(item["image_url"], dest),
                "caption": item["caption"],
                "comments": item["comments"],
            })
        elif len(posts) < max_posts and item["caption"]:
            posts.append({
                "post_url": item["url"],
                "date": item["date"],
                "screenshot_path": _write_caption_txt(f"{username}_{item['id']}", item["caption"]),
                "comments": item["comments"],
            })

    return about, photos, reels, posts


# ─────────────────────────────────────────────────────────────
#  Entry points
# ─────────────────────────────────────────────────────────────

def collect(profile_url, max_posts=10, max_photos=10, max_reels=10):
    username = extract_telegram_username(profile_url)
    if not username:
        raise ValueError(
            f"Could not parse a public Telegram username from: {profile_url} "
            "(private invite links are not supported)"
        )
    profile_url = normalize_telegram_target(profile_url)

    print(f"\n{'═'*65}")
    print(f"  TELEGRAM COLLECTOR — @{username}")
    print("═" * 65)

    about = photos = reels = posts = None
    mode = "public preview"

    if telethon_available() and load_config():
        try:
            print("   Trying MTProto (Telethon)...")
            about, photos, reels, posts = asyncio.run(
                _telethon_collect(username, profile_url, max_posts, max_photos, max_reels)
            )
            mode = "MTProto"
            print("   MTProto path OK")
        except TelegramAuthError as e:
            print(f"   MTProto unavailable: {e}")
        except Exception as e:
            print(f"   MTProto failed: {e}")
    else:
        print("   Telethon or credentials missing — using public preview")

    if about is None:
        about, photos, reels, posts = _public_collect(
            username, profile_url, max_posts, max_photos, max_reels
        )

    if not photos and not reels and not posts:
        bio = ""
        for field in (about.get("sections") or {}).get("directory_intro", []):
            if field.get("value"):
                bio = field["value"]
                break
        posts.append({
            "post_url": profile_url,
            "date": None,
            "screenshot_path": _write_caption_txt(
                f"{username}_about", bio or f"@{username} on Telegram"
            ),
            "comments": [],
        })
        print("   Added bio as text post (no feed items)")

    for path, payload in (
        (ABOUT_OUT, about), (PHOTOS_OUT, photos), (REELS_OUT, reels), (POSTS_OUT, posts)
    ):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    n_comments = sum(len(x.get("comments") or []) for x in photos + reels + posts)
    distinct = _tally(photos + reels + posts)
    breakdown = Counter(
        c.get("interaction_type") or "unknown"
        for x in photos + reels + posts for c in (x.get("comments") or [])
    )
    avatars = sum(1 for p in photos if "#avatar-" in (p.get("photo_url") or ""))
    photo_note = f"{len(photos)}" if not avatars else \
        f"{len(photos)} ({len(photos) - avatars} media + {avatars} avatars)"
    print(f"   Profile : {about.get('owner_name')} → {ABOUT_OUT}")
    print(f"   Photos : {photo_note}  Reels: {len(reels)}  Posts: {len(posts)}")
    print(f"   Interactors seeded: {n_comments} rows · {len(distinct)} distinct")
    if breakdown:
        print("   By type: " + " · ".join(f"{k} {v}" for k, v in breakdown.most_common()))
    print(f"   Mode   : {mode}")
    if mode != "MTProto" and n_comments == 0:
        print("   NOTE: public preview exposes no commenters — graph will be sparse")

    return {
        "about": ABOUT_OUT,
        "photos": PHOTOS_OUT,
        "reels": REELS_OUT,
        "posts": POSTS_OUT,
        "mode": mode,
        "counts": {
            "photos": len(photos),
            "reels": len(reels),
            "posts": len(posts),
            "comments": n_comments,
        },
    }


def check_session_valid():
    """
    Telegram needs no cookies. Report which collection mode is available so the
    operator knows whether the interactor graph will be populated.
    """
    if not telethon_available():
        return True, "Public preview ready — install telethon for comment collection"
    cfg = load_config()
    if not cfg:
        return True, "Public preview ready — set TG_API_ID / TG_API_HASH for MTProto"
    if not _session_file_exists(cfg["session"]):
        return True, (
            f"Credentials found ({cfg['source']}) but no authorized session at "
            f"{cfg['session']}.session — public preview will be used"
        )
    return True, f"MTProto session ready ({os.path.basename(cfg['session'])})"


def main(profile_url=None, max_posts=10, max_photos=None, max_reels=None):
    if not profile_url:
        profile_url = input("Enter Telegram channel/group URL: ").strip()
    max_photos = max_photos if max_photos is not None else max_posts
    max_reels = max_reels if max_reels is not None else max_posts
    return collect(profile_url, max_posts=max_posts, max_photos=max_photos, max_reels=max_reels)


if __name__ == "__main__":
    main()
