from app.parsers.common import find_debit_down, find_debit_up


def test_find_debit_from_unyc_speedtest_style_text():
    # Format observé sur les captures d'écran speedtest.unyc.io (OCR).
    text = "Download 7.85 Mbps Upload 3.54 Mbps Latence 44.24 ms"
    assert find_debit_down(text) == 7.85
    assert find_debit_up(text) == 3.54
