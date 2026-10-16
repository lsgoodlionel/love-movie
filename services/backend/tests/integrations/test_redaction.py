from app.integrations.redaction import public_message, redact


def test_redacts_access_headers_html_and_long_remote_payloads() -> None:
    source = "CF-Access-Client-Secret: super-secret <html><body>internal hostname</body></html>"
    cleaned = redact(source, secrets=["super-secret"])
    assert "super-secret" not in cleaned
    assert "internal hostname" not in cleaned
    assert "html" not in cleaned.lower()
    assert len(public_message(source)) < 100
