import json
from collections.abc import Iterable
from typing import Any


def encode_sse(events: Iterable[Any]) -> str:
    chunks: list[str] = []
    for event in events:
        data = json.dumps(
            {"message": event.message, "progress": event.progress},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        chunks.append(f"id: {event.id}\nevent: {event.kind}\ndata: {data}\n\n")
    return "".join(chunks)
