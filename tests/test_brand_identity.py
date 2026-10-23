from seo_pulse_mcp.auth import _page


def test_sign_in_page_carries_brand_and_preserves_escaped_messages():
    response = _page(403, '<拒絕>', '<script>bad</script>')
    text = response.body.decode()
    assert 'ls-labs-logo-white.svg' in text
    assert 'background:#070B14' in text
    assert '&lt;script&gt;bad&lt;/script&gt;' in text
    assert response.status_code == 403
    assert response.headers['Cache-Control'] == 'no-store'
