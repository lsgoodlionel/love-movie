import hashlib
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.integrations.errors import RemoteServiceError


@dataclass(frozen=True)
class StoredObject:
    key: str
    content_type: str
    size_bytes: int
    sha256: str


class StorageAdapter:
    ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp", "video/mp4", "video/webm"}

    def __init__(self, client: Any, bucket: str, *, presign_client: Any | None = None, max_bytes: int = 2 * 1024**3) -> None:
        self._client = client
        self._presign_client = presign_client or client
        self._bucket = bucket
        self._max_bytes = max_bytes

    async def put_stream(
        self,
        key: str,
        source: AsyncIterator[bytes],
        content_type: str,
        *,
        declared_size: int | None = None,
    ) -> StoredObject:
        if content_type not in self.ALLOWED_TYPES:
            raise RemoteServiceError("UNSUPPORTED_MEDIA_TYPE", "不支持的媒体类型")
        digest = hashlib.sha256()
        size = 0
        try:
            with tempfile.TemporaryFile() as fileobj:
                async for chunk in source:
                    size += len(chunk)
                    if size > self._max_bytes:
                        raise RemoteServiceError("ASSET_TOO_LARGE", "生成结果超过存储上限")
                    digest.update(chunk)
                    fileobj.write(chunk)
                if declared_size is not None and size != declared_size:
                    raise RemoteServiceError("DOWNLOAD_INTERRUPTED", "生成结果下载不完整")
                fileobj.seek(0)
                signature = fileobj.read(16)
                self._validate_signature(content_type, signature)
                fileobj.seek(0)
                self._client.upload_fileobj(
                    fileobj,
                    self._bucket,
                    key,
                    ExtraArgs={"ContentType": content_type},
                )
        except RemoteServiceError:
            raise
        except Exception as exc:
            raise RemoteServiceError("STORAGE_WRITE_FAILED", "生成结果保存失败") from exc
        return StoredObject(key, content_type, size, digest.hexdigest())

    @staticmethod
    def _validate_signature(content_type: str, signature: bytes) -> None:
        valid = {
            "image/png": signature.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/jpeg": signature.startswith(b"\xff\xd8\xff"),
            "image/webp": signature.startswith(b"RIFF") and signature[8:12] == b"WEBP",
            "video/mp4": len(signature) >= 12 and signature[4:8] == b"ftyp",
            "video/webm": signature.startswith(b"\x1a\x45\xdf\xa3"),
        }[content_type]
        if not valid:
            raise RemoteServiceError("INVALID_MEDIA_CONTENT", "生成结果内容与媒体类型不匹配")

    def presign_get(self, key: str, ttl_seconds: int = 300) -> str:
        try:
            return str(
                self._presign_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self._bucket, "Key": key},
                    ExpiresIn=ttl_seconds,
                )
            )
        except Exception as exc:
            raise RemoteServiceError("STORAGE_READ_FAILED", "无法创建素材预览地址") from exc

    def get_bytes(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            content = response["Body"].read(self._max_bytes + 1)
            if len(content) > self._max_bytes:
                raise RemoteServiceError("ASSET_TOO_LARGE", "素材超过读取上限")
            return bytes(content)
        except RemoteServiceError:
            raise
        except Exception as exc:
            raise RemoteServiceError("STORAGE_READ_FAILED", "无法读取已保存素材") from exc
