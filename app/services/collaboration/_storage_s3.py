"""S3 / MinIO file storage.

Variables:
  COLLAB_S3_BUCKET     — nombre del bucket
  COLLAB_S3_REGION     — eu-west-1 (default)
  COLLAB_S3_ENDPOINT   — opcional (S3 compatible: http://127.0.0.1:9003)
  AWS_ACCESS_KEY_ID    — credenciales
  AWS_SECRET_ACCESS_KEY
  COLLAB_S3_PREFIX     — prefijo opcional (default: 'collaboration/')
"""
from __future__ import annotations

import io
import logging
import os
from typing import BinaryIO

from app.services.collaboration._storage import FileStorage, StoredFile

logger = logging.getLogger(__name__)


class S3FileStorage(FileStorage):
    provider = "s3"

    def __init__(self) -> None:
        super().__init__()
        try:
            import boto3
            self._bucket = os.environ.get("COLLAB_S3_BUCKET")
            self._prefix = os.environ.get("COLLAB_S3_PREFIX", "collaboration/")
            kwargs = {
                "region_name": os.environ.get("COLLAB_S3_REGION", "eu-west-1"),
            }
            endpoint = os.environ.get("COLLAB_S3_ENDPOINT")
            if endpoint:
                kwargs["endpoint_url"] = endpoint
            # Lo mismo que `S3Service._build_client`: firma v4 también en las
            # URLs firmadas (sin pedirla, boto3 presigna en v2 y versitygw o AWS
            # en regiones nuevas la rechazan) y, con endpoint propio,
            # direccionamiento por ruta, que es lo que entiende un servidor de
            # un solo host.
            from botocore.config import Config as BotoConfig
            kwargs["config"] = BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": "path"} if endpoint else {},
            )
            self._client = boto3.client("s3", **kwargs)
            if not self._bucket:
                raise RuntimeError("COLLAB_S3_BUCKET no configurado")
        except Exception as exc:
            logger.error("S3 storage init failed: %s", exc)
            raise

    def _full(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def save(self, key: str, fp: BinaryIO) -> StoredFile:
        import hashlib
        h = hashlib.sha256()
        buf = io.BytesIO()
        size = 0
        while True:
            chunk = fp.read(64 * 1024)
            if not chunk:
                break
            buf.write(chunk)
            h.update(chunk)
            size += len(chunk)
        buf.seek(0)
        self._client.upload_fileobj(buf, self._bucket, self._full(key))
        return StoredFile(self.provider, key, size, h.hexdigest())

    def save_bytes(self, key: str, data: bytes) -> StoredFile:
        import hashlib
        self._client.put_object(Bucket=self._bucket, Key=self._full(key), Body=data)
        return StoredFile(self.provider, key, len(data), hashlib.sha256(data).hexdigest())

    def read(self, key: str) -> bytes:
        obj = self._client.get_object(Bucket=self._bucket, Key=self._full(key))
        return obj["Body"].read()

    def open(self, key: str) -> BinaryIO:
        return io.BytesIO(self.read(key))

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=self._full(key))
            return True
        except Exception:
            logger.debug("exists: excepcion ignorada", exc_info=True)
            return False

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=self._full(key))
        # intentional: cleanup path, logging would cascade
        except Exception:
            logger.debug("delete: fallo best-effort ignorado", exc_info=True)

    def size(self, key: str) -> int:
        try:
            obj = self._client.head_object(Bucket=self._bucket, Key=self._full(key))
            return int(obj["ContentLength"])
        except Exception:
            logger.debug("size: excepcion ignorada", exc_info=True)
            return 0

    def signed_url(self, key: str, *, ttl_seconds: int = 3600, mode: str = "download") -> str:
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": self._full(key)},
                ExpiresIn=ttl_seconds,
            )
        except Exception:
            logger.debug("signed_url: excepcion ignorada", exc_info=True)
            return super().signed_url(key, ttl_seconds=ttl_seconds, mode=mode)
