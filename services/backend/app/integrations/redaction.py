import re
from collections.abc import Iterable


_HTML_DOCUMENT = re.compile(r"<html\b.*?</html\s*>", re.IGNORECASE | re.DOTALL)
_HTML_TAG = re.compile(r"<[^>]*>", re.IGNORECASE | re.DOTALL)
_ACCESS_HEADER = re.compile(
    r"(?i)(cf-access-client-(?:id|secret)\s*[:=]\s*)[^\s,;]+"
)


def redact(value: object, secrets: Iterable[str] = ()) -> str:
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = _ACCESS_HEADER.sub(r"\1[REDACTED]", text)
    text = _HTML_DOCUMENT.sub("[REMOTE_CONTENT]", text)
    text = _HTML_TAG.sub("[REMOTE_CONTENT]", text)
    return text[:240]


def public_message(value: object) -> str:
    text = redact(value)
    if "[REMOTE_CONTENT]" in text or len(text) > 96:
        return "远程服务返回了不可用的响应"
    return text
