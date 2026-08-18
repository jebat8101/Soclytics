"""ConvoMetrics-style text analytics over Telegram SOCMINT corpora.

Builds a message corpus from captions, comments, and day-thread transcripts,
then exposes activity timelines, word frequency, and word search.
"""
from __future__ import annotations

import os
import re
import sqlite3
import string
from collections import Counter
from datetime import datetime

from platforms.telegram.constants import BASE_DIR

# English stopwords + chat / collector artifacts (no NLTK dependency).
_STOPWORDS = frozenset({
    'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and',
    'any', 'are', 'as', 'at', 'be', 'because', 'been', 'before', 'being', 'below',
    'between', 'both', 'but', 'by', 'can', 'did', 'do', 'does', 'doing', 'down',
    'during', 'each', 'few', 'for', 'from', 'further', 'had', 'has', 'have',
    'having', 'he', 'her', 'here', 'hers', 'herself', 'him', 'himself', 'his',
    'how', 'i', 'if', 'in', 'into', 'is', 'it', 'its', 'itself', 'just', 'me',
    'more', 'most', 'my', 'myself', 'no', 'nor', 'not', 'now', 'of', 'off', 'on',
    'once', 'only', 'or', 'other', 'our', 'ours', 'ourselves', 'out', 'over',
    'own', 'same', 'she', 'should', 'so', 'some', 'such', 'than', 'that', 'the',
    'their', 'theirs', 'them', 'themselves', 'then', 'there', 'these', 'they',
    'this', 'those', 'through', 'to', 'too', 'under', 'until', 'up', 'very',
    'was', 'we', 'were', 'what', 'when', 'where', 'which', 'while', 'who',
    'whom', 'why', 'will', 'with', 'you', 'your', 'yours', 'yourself',
    'yourselves',
    # Malay function words (common in local Telegram corpora)
    'ada', 'adalah', 'akan', 'aku', 'anda', 'atau', 'bagi', 'bahawa', 'banyak',
    'baru', 'beliau', 'boleh', 'buat', 'bukan', 'dalam', 'dan', 'dapat', 'dari',
    'daripada', 'dengan', 'dia', 'juga', 'kalau', 'kami', 'kamu', 'karena',
    'kerana', 'ke', 'kepada', 'kita', 'lagi', 'lain', 'lebih', 'masih', 'maka',
    'mereka', 'nah', 'oleh', 'pada', 'para', 'per', 'perlu', 'satu', 'saya',
    'sebagai', 'sebuah', 'sedang', 'sudah', 'tak', 'telah', 'tentang', 'tersebut',
    'itu', 'ini', 'untuk', 'yang', 'ya', 'dah', 'nak', 'ni', 'tu', 'je', 'lah',
    'kah', 'pun', 'sahaja', 'saja', 'semua', 'serta', 'setiap', 'seperti',
    'selepas', 'sebelum', 'namun', 'walaupun', 'supaya', 'agar', 'ia', 'ialah',
    'kami', 'engkau', 'kalian',
    # chat / collector noise
    'media', 'omitted', 'deleted', 'image', 'video', 'sticker', 'gif', 'voice',
    'call', 'missed', 'reacted', 'mentioned', 'forwarded', 'engagement',
    'original', 'author', 'message', 'reply', 'replied', 'http', 'https', 'www',
    'tme', 'telegram',
})

_NOISE_PREFIXES = (
    'reacted ',
    'mentioned in ',
    'original author of forwarded',
    'forwarded source of',
    'replied to by',
    '[engagement]',
)

_TRANSCRIPT_RE = re.compile(
    r'^\[(?P<id>\d+)\]\s+(?P<time>\d{1,2}:\d{2})\s+(?P<sender>[^:]+):\s*(?P<text>.*)$'
)

_DAY_NAMES = (
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
)

_PUNCT_TABLE = str.maketrans('', '', string.punctuation + '“”‘’…—–')


def _is_noise_text(text: str) -> bool:
    t = (text or '').strip()
    if not t or t == '[media]':
        return True
    low = t.lower()
    return any(low.startswith(p) for p in _NOISE_PREFIXES)


def _clean_caption(text: str) -> str:
    """Strip engagement trailer / prefix from channel captions."""
    t = (text or '').strip()
    if t.lower().startswith('[engagement]'):
        # keep any body after the engagement header line if present
        parts = t.split('\n', 1)
        t = parts[1].strip() if len(parts) > 1 else ''
    # drop trailing engagement footer lines
    lines = [ln for ln in t.splitlines() if not ln.strip().lower().startswith('[engagement]')]
    return '\n'.join(lines).strip()


def _resolve_path(rel: str | None) -> str | None:
    if not rel:
        return None
    if os.path.isabs(rel) and os.path.isfile(rel):
        return rel
    candidate = os.path.join(BASE_DIR, rel.lstrip('/'))
    if os.path.isfile(candidate):
        return candidate
    # collector may store just the filename under post_screenshots/
    bare = os.path.join(BASE_DIR, 'post_screenshots', os.path.basename(rel))
    if os.path.isfile(bare):
        return bare
    return None


def _parse_hour(time_str: str | None) -> int | None:
    if not time_str:
        return None
    try:
        return int(time_str.split(':', 1)[0]) % 24
    except (ValueError, IndexError):
        return None


def _weekday(date_str: str | None) -> str | None:
    if not date_str:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            return _DAY_NAMES[datetime.strptime(date_str[:10], fmt).weekday()]
        except ValueError:
            continue
    return None


def _tokenize_words(text: str) -> list[str]:
    clean = str(text).lower().translate(_PUNCT_TABLE)
    return [w for w in clean.split() if w not in _STOPWORDS and len(w) > 2 and not w.isdigit()]


def _append(corpus: list, *, sender: str, message: str, date: str | None,
            hour: int | None = None, source: str = ''):
    msg = (message or '').strip()
    if _is_noise_text(msg):
        return
    corpus.append({
        'sender': (sender or 'Unknown').strip() or 'Unknown',
        'message': msg,
        'date': date,
        'hour': hour,
        'source': source,
    })


def _owner_name(cur, profile_id: int) -> str:
    cur.execute('SELECT owner_name FROM profiles WHERE id = ?', (profile_id,))
    row = cur.fetchone()
    return (row[0] if row and row[0] else 'Channel').strip() or 'Channel'


def build_text_corpus(db_file: str, profile_id: int) -> list[dict]:
    """Union captions + comments + day-thread transcript lines for a profile."""
    con = sqlite3.connect(db_file)
    cur = con.cursor()
    owner = _owner_name(cur, profile_id)
    corpus: list[dict] = []

    # Photo captions (channel/owner voice)
    cur.execute("""
        SELECT caption, date_text FROM photo_posts WHERE profile_id = ?
    """, (profile_id,))
    for caption, date in cur.fetchall():
        body = _clean_caption(caption or '')
        _append(corpus, sender=owner, message=body, date=date, source='photo_caption')

    # Photo comments
    cur.execute("""
        SELECT c.name, pc.comment_text, pp.date_text
        FROM photo_comments pc
        JOIN photo_posts pp ON pp.id = pc.photo_post_id
        JOIN commentors c ON c.id = pc.commentor_id
        WHERE pp.profile_id = ?
    """, (profile_id,))
    for name, text, date in cur.fetchall():
        _append(corpus, sender=name or 'Unknown', message=text or '',
                date=date, source='photo_comment')

    # Reel comments
    cur.execute("""
        SELECT c.name, rc.comment_text, date(rp.scraped_at) as d
        FROM reel_comments rc
        JOIN reel_posts rp ON rp.id = rc.reel_post_id
        JOIN commentors c ON c.id = rc.commentor_id
        WHERE rp.profile_id = ?
    """, (profile_id,))
    for name, text, date in cur.fetchall():
        _append(corpus, sender=name or 'Unknown', message=text or '',
                date=date, source='reel_comment')

    # Text-post comments (often day-bucketed group speakers)
    cur.execute("""
        SELECT c.name, tc.comment_text, tp.date_text
        FROM text_comments tc
        JOIN text_posts tp ON tp.id = tc.text_post_id
        JOIN commentors c ON c.id = tc.commentor_id
        WHERE tp.profile_id = ?
    """, (profile_id,))
    for name, text, date in cur.fetchall():
        # Prefer granular transcript lines when available; still keep comment
        # aggregates as fallback if transcript parse yields nothing for that day.
        _append(corpus, sender=name or 'Unknown', message=text or '',
                date=date, source='text_comment')

    # Day-thread / text-post transcript files — richest hour + speaker data
    cur.execute("""
        SELECT screenshot_path, date_text FROM text_posts WHERE profile_id = ?
    """, (profile_id,))
    transcript_rows = cur.fetchall()
    con.close()

    transcript_msgs = 0
    for path, date in transcript_rows:
        full = _resolve_path(path)
        if not full:
            continue
        try:
            with open(full, encoding='utf-8', errors='replace') as fh:
                content = fh.read()
        except OSError:
            continue
        for line in content.splitlines():
            m = _TRANSCRIPT_RE.match(line.strip())
            if not m:
                continue
            text = m.group('text').strip()
            if _is_noise_text(text):
                continue
            _append(
                corpus,
                sender=m.group('sender').strip(),
                message=text,
                date=date,
                hour=_parse_hour(m.group('time')),
                source='transcript',
            )
            transcript_msgs += 1

    # If transcripts expanded the day threads, drop coarse text_comment aggregates
    # for the same dates to avoid double-counting merged "a | b | c" blobs.
    if transcript_msgs:
        transcript_dates = {
            r['date'] for r in corpus if r['source'] == 'transcript' and r.get('date')
        }
        corpus = [
            r for r in corpus
            if not (r['source'] == 'text_comment' and r.get('date') in transcript_dates)
        ]

    return corpus


def get_activity_metrics(db_file: str, profile_id: int) -> dict:
    corpus = build_text_corpus(db_file, profile_id)
    by_date: Counter = Counter()
    by_weekday: Counter = Counter()
    by_hour: Counter = Counter()
    by_sender: Counter = Counter()

    for row in corpus:
        if row.get('date'):
            by_date[row['date']] += 1
            wd = _weekday(row['date'])
            if wd:
                by_weekday[wd] += 1
        if row.get('hour') is not None:
            by_hour[int(row['hour'])] += 1
        by_sender[row['sender']] += 1

    return {
        'total_messages': len(corpus),
        'participants': len(by_sender),
        'by_date': [
            {'date': d, 'messages': n}
            for d, n in sorted(by_date.items(), key=lambda x: x[0])
        ],
        'by_weekday': [
            {'day': d, 'messages': by_weekday.get(d, 0)} for d in _DAY_NAMES
        ],
        'by_hour': [
            {'hour': h, 'messages': by_hour.get(h, 0)} for h in range(24)
        ],
        'has_hour_data': sum(by_hour.values()) > 0,
        'top_senders': [
            {'sender': s, 'messages': n}
            for s, n in by_sender.most_common(15)
        ],
    }


def get_word_stats(db_file: str, profile_id: int, sender: str | None = None,
                   limit: int = 40) -> dict:
    corpus = build_text_corpus(db_file, profile_id)
    senders = sorted({r['sender'] for r in corpus})
    subset = corpus
    if sender and sender != 'All':
        subset = [r for r in corpus if r['sender'] == sender]

    counter: Counter = Counter()
    for row in subset:
        counter.update(_tokenize_words(row['message']))

    all_text = ' '.join(r['message'] for r in subset)
    return {
        'sender': sender or 'All',
        'senders': ['All'] + senders,
        'total_messages': len(subset),
        'total_words': sum(counter.values()),
        'unique_words': len(counter),
        'top_words': [{'word': w, 'count': n} for w, n in counter.most_common(limit)],
        'cloud_words': [
            {'word': w, 'count': n} for w, n in counter.most_common(min(80, limit * 2))
        ],
        'sample_chars': len(all_text),
    }


def word_frequencies(db_file: str, profile_id: int, sender: str | None = None,
                     limit: int = 120) -> dict[str, int]:
    """Frequency map for WordCloud (stopwords already filtered)."""
    stats = get_word_stats(db_file, profile_id, sender=sender, limit=limit)
    return {w['word']: int(w['count']) for w in (stats.get('cloud_words') or stats.get('top_words') or [])}


def render_word_cloud_png(freqs: dict[str, int], *, width: int = 1200, height: int = 520,
                          background_color: str = 'white', colormap: str = 'viridis',
                          max_words: int = 150) -> bytes | None:
    """Return PNG bytes for a ConvoMetrics-style visual word cloud."""
    if not freqs:
        return None
    try:
        from wordcloud import WordCloud
        import io
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            'wordcloud package not installed — pip install wordcloud'
        ) from exc

    wc = WordCloud(
        width=width,
        height=height,
        background_color=background_color,
        colormap=colormap,
        max_words=max_words,
        prefer_horizontal=0.85,
        relative_scaling=0.45,
        min_font_size=10,
    ).generate_from_frequencies(freqs)

    fig, ax = plt.subplots(figsize=(width / 140, height / 140))
    fig.patch.set_facecolor(background_color)
    ax.imshow(wc, interpolation='bilinear')
    ax.axis('off')
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=140, bbox_inches='tight',
                facecolor=background_color, pad_inches=0.15)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def search_word(db_file: str, profile_id: int, term: str) -> dict:
    term_clean = (term or '').lower().strip().translate(_PUNCT_TABLE)
    if not term_clean:
        return {
            'term': '',
            'total': 0,
            'by_sender': [],
            'by_date': [],
            'samples': [],
        }

    corpus = build_text_corpus(db_file, profile_id)
    by_sender: Counter = Counter()
    by_date: Counter = Counter()
    samples = []

    for row in corpus:
        clean = str(row['message']).lower().translate(_PUNCT_TABLE)
        count = clean.split().count(term_clean)
        if count <= 0:
            continue
        by_sender[row['sender']] += count
        if row.get('date'):
            by_date[row['date']] += count
        if len(samples) < 12:
            samples.append({
                'sender': row['sender'],
                'date': row.get('date'),
                'message': row['message'][:280],
                'count': count,
            })

    return {
        'term': term_clean,
        'total': int(sum(by_sender.values())),
        'by_sender': [
            {'sender': s, 'count': n}
            for s, n in by_sender.most_common()
        ],
        'by_date': [
            {'date': d, 'count': n}
            for d, n in sorted(by_date.items(), key=lambda x: x[0])
        ],
        'samples': samples,
    }
