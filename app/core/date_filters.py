from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

_MONTH_FORMATS = (
    '%d %B %Y',
    '%d %b %Y',
    '%B %d %Y',
    '%b %d %Y',
    '%B %d, %Y',
    '%b %d, %Y',
)
_MONTH_FORMATS_NO_YEAR = (
    '%d %B',
    '%d %b',
    '%B %d',
    '%b %d',
)


def _coerce_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    text = text.replace(',', ', ')
    text = ' '.join(text.split())
    if len(text) >= 10:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass
    for marker in (' at ', ' · '):
        if marker in text:
            text = text.split(marker, 1)[0].strip()
    for fmt in _MONTH_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    for fmt in _MONTH_FORMATS_NO_YEAR:
        try:
            current = datetime.now(timezone.utc).date()
            parsed = datetime.strptime(text, fmt).date().replace(year=current.year)
            if parsed > current:
                parsed = parsed.replace(year=current.year - 1)
            return parsed
        except ValueError:
            continue
    rel = re.match(
        r'^(?:about\s+)?(?:(\d+|a|an)\s*(second|minute|min|hour|hr|day|week|month|year)s? ago|(\d+)([smhdwy]))$',
        text.lower(),
    )
    if rel:
        raw_amount = rel.group(1) or rel.group(3) or 0
        amount = 1 if raw_amount in ('a', 'an') else int(raw_amount)
        unit = rel.group(2) or rel.group(4)
        now = datetime.now(timezone.utc).date()
        if unit in ('second', 'minute', 'min', 'hour', 'hr', 's', 'm', 'h'):
            return now
        if unit in ('day', 'd'):
            return now - timedelta(days=amount)
        if unit in ('week', 'w'):
            return now - timedelta(weeks=amount)
        if unit in ('month',):
            return now - timedelta(days=30 * amount)
        if unit in ('year', 'y'):
            return now - timedelta(days=365 * amount)
    if text.lower() in {'yesterday'}:
        return datetime.now(timezone.utc).date() - timedelta(days=1)
    if text.lower() in {'moments ago', 'moment ago', 'just now'}:
        return datetime.now(timezone.utc).date()
    return None


def normalize_date_range(
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[str | None, str | None]:
    start = _coerce_iso_date(start_date)
    end = _coerce_iso_date(end_date)
    if start_date and start is None:
        raise ValueError('start_date must be YYYY-MM-DD')
    if end_date and end is None:
        raise ValueError('end_date must be YYYY-MM-DD')
    if start and end and start > end:
        raise ValueError('start_date must be on or before end_date')
    return (
        start.isoformat() if start else None,
        end.isoformat() if end else None,
    )


def item_in_date_range(
    item_date: str | None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> bool:
    if not start_date and not end_date:
        return True
    current = _coerce_iso_date(item_date)
    if current is None:
        return False
    start = _coerce_iso_date(start_date)
    end = _coerce_iso_date(end_date)
    if start and current < start:
        return False
    if end and current > end:
        return False
    return True


def filter_dated_items(
    items: list[dict],
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    if not start_date and not end_date:
        return items
    return [
        item for item in items
        if item_in_date_range(item.get('date'), start_date, end_date)
    ]
