"""Notifier template rendering + render safety tests."""


from bagbot.notifier import render_message


def test_zh_template_renders_with_kwargs():
    out = render_message("zh-CN", "key_claimed", headroom=12.5)
    assert "12.50" in out
    assert "领取" in out


def test_en_template_renders():
    out = render_message("en", "key_claimed", headroom=12.5)
    assert "12.50" in out
    assert "Claimed" in out


def test_unknown_kind_returns_raw_key():
    """If a kind is not in the template table, we return the kind itself."""
    out = render_message("zh-CN", "weird_unknown_kind", foo=1)
    assert out == "weird_unknown_kind"


def test_missing_kwargs_does_not_crash():
    """If a template needs {foo} and we don't pass it, .format() will KeyError.
    Our current implementation just returns the template string — verify that
    behavior is graceful (no exception)."""
    out = render_message("zh-CN", "key_claimed")  # headroom missing
    # Should not raise; either returns unformatted template or the kind
    assert isinstance(out, str)


def test_balance_low_template():
    out = render_message("zh-CN", "balance_low",
                         unclaimed=2.5, threshold=5.0)
    assert "2.50" in out
    assert "5.00" in out


def test_burn_high_template():
    out = render_message("zh-CN", "burn_high",
                         rate=25.0, threshold=20.0)
    assert "25.00" in out


def test_tick_template():
    out = render_message("zh-CN", "tick",
                         balance=10.0, used=0.85, rate=15.0)
    assert "85%" in out or "0.85" in out


def test_locale_falls_back_to_english_for_unknown_lang():
    out = render_message("ja", "key_claimed", headroom=1.0)
    assert "Claimed" in out  # english fallback
