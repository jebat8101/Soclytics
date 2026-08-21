from core.date_filters import filter_dated_items, item_in_date_range, normalize_date_range


def test_normalize_date_range_accepts_iso_values():
    assert normalize_date_range('2026-08-01', '2026-08-31') == ('2026-08-01', '2026-08-31')


def test_normalize_date_range_rejects_inverted_window():
    try:
        normalize_date_range('2026-08-31', '2026-08-01')
        assert False, 'expected ValueError'
    except ValueError as e:
        assert 'on or before' in str(e)


def test_item_in_date_range_accepts_facebook_absolute_date():
    assert item_in_date_range('15 March 2024', '2024-03-01', '2024-03-31') is True


def test_item_in_date_range_excludes_missing_dates_when_filtering():
    assert item_in_date_range(None, '2026-08-01', '2026-08-31') is False


def test_filter_dated_items_keeps_only_matching_items():
    items = [
        {'post_url': 'a', 'date': '2026-08-01'},
        {'post_url': 'b', 'date': '2026-08-15'},
        {'post_url': 'c', 'date': None},
    ]
    assert filter_dated_items(items, '2026-08-10', '2026-08-20') == [
        {'post_url': 'b', 'date': '2026-08-15'}
    ]
