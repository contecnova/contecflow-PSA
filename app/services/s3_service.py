"""
Document storage service.

Uses AWS S3 when credentials are configured (AWS_ACCESS_KEY + AWS_SECRET_KEY),
otherwise falls back to local disk storage under ``<project_root>/uploads/``.

Both backends expose the same interface so the rest of the codebase never
needs to know which backend is active.
"""
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

# Root for local file uploads (sibling of app/)
_LOCAL_UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"


# ── Local storage backend ──────────────────────────────────────────────────────

class LocalFileStorage:
    """Stores files on the local filesystem under <project_root>/uploads/."""

    def is_available(self) -> bool:
        return True

    def upload_file(
        self,
        file_content: bytes,
        file_name: str,
        document_id: str,
        version_num: int,
        content_type: str = "application/octet-stream",
    ) -> Tuple[str, int]:
        ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "bin"
        unique_id = str(uuid.uuid4())[:8]
        # Key mirrors the S3 path convention so switching backends is painless
        relative_key = f"documents/{document_id}/v{version_num}/{unique_id}.{ext}"
        full_path = _LOCAL_UPLOAD_ROOT / relative_key
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(file_content)
        logger.info(f"File saved locally: {full_path}")
        return relative_key, len(file_content)

    def generate_presigned_url(self, file_key: str, expiration_hours: Optional[int] = None) -> str:
        """Return the API download URL for this file key."""
        return f"/api/v1/documents/file/{file_key}"

    def get_file_bytes(self, file_key: str) -> bytes:
        # Resolve the absolute path and ensure it stays within the upload root
        # (guards against path traversal like ../../etc/passwd)
        upload_root = _LOCAL_UPLOAD_ROOT.resolve()
        path = (upload_root / file_key).resolve()
        if not str(path).startswith(str(upload_root) + "/"):
            raise PermissionError("Access denied: path outside upload root")
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_key}")
        return path.read_bytes()

    def delete_file(self, file_key: str) -> bool:
        path = _LOCAL_UPLOAD_ROOT / file_key
        if path.exists():
            path.unlink()
            logger.info(f"Local file deleted: {file_key}")
            return True
        return False

    def get_file_size(self, file_key: str) -> Optional[int]:
        path = _LOCAL_UPLOAD_ROOT / file_key
        return path.stat().st_size if path.exists() else None


# ── S3 backend ─────────────────────────────────────────────────────────────────

class S3Service:
    """AWS S3 file storage service."""

    def __init__(self):
        self.bucket = settings.AWS_S3_BUCKET
        self.region = settings.AWS_REGION
        self.url_expiration_hours = settings.S3_URL_EXPIRATION_HOURS
        self.client = None

        try:
            import boto3
            self.client = boto3.client(
                "s3",
                region_name=self.region,
                aws_access_key_id=settings.AWS_ACCESS_KEY,
                aws_secret_access_key=settings.AWS_SECRET_KEY,
            )
            logger.info(f"S3Service initialized: bucket={self.bucket}, region={self.region}")
        except Exception as e:
            logger.warning(f"S3 client could not be initialised: {e}")

    def is_available(self) -> bool:
        return (
            self.client is not None
            and bool(settings.AWS_ACCESS_KEY)
            and bool(settings.AWS_SECRET_KEY)
        )

    def upload_file(
        self,
        file_content: bytes,
        file_name: str,
        document_id: str,
        version_num: int,
        content_type: str = "application/octet-stream",
    ) -> Tuple[str, int]:
        if not self.is_available():
            raise ValueError("S3 not configured. Check AWS credentials in settings.")

        from botocore.exceptions import ClientError
        ext = file_name.rsplit(".", 1)[-1] if "." in file_name else "bin"
        unique_id = str(uuid.uuid4())[:8]
        s3_key = f"documents/{document_id}/v{version_num}/{unique_id}.{ext}"

        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=file_content,
                ContentType=content_type,
                Metadata={
                    "original_filename": file_name,
                    "document_id": document_id,
                    "version_num": str(version_num),
                    "uploaded_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.info(f"File uploaded to S3: {s3_key}")
            return s3_key, len(file_content)
        except ClientError as e:
            logger.error(f"Failed to upload to S3: {e}")
            raise ValueError(f"S3 upload failed: {str(e)}")

    def generate_presigned_url(self, s3_key: str, expiration_hours: Optional[int] = None) -> str:
        if not self.is_available():
            raise ValueError("S3 not configured")

        from botocore.exceptions import ClientError
        expiration_seconds = (expiration_hours or self.url_expiration_hours) * 3600
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": s3_key},
                ExpiresIn=expiration_seconds,
            )
        except ClientError as e:
            raise ValueError(f"Failed to generate presigned URL: {str(e)}")

    def delete_file(self, s3_key: str) -> bool:
        if not self.is_available():
            return False
        try:
            from botocore.exceptions import ClientError
            self.client.delete_object(Bucket=self.bucket, Key=s3_key)
            return True
        except ClientError as e:
            logger.error(f"Failed to delete S3 file: {e}")
            return False

    def get_file_size(self, s3_key: str) -> Optional[int]:
        if not self.is_available():
            return None
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=s3_key)
            return response.get("ContentLength")
        except Exception:
            return None


# ── Active backend — auto-selected at startup ──────────────────────────────────

def _build_storage():
    """Return S3 backend if credentials are present, otherwise local disk."""
    s3 = S3Service()
    if s3.is_available():
        logger.info("Document storage: AWS S3")
        return s3
    logger.info("Document storage: local filesystem (uploads/)")
    return LocalFileStorage()


s3_service = _build_storage()  # legacy name kept for import compatibility
file_storage = s3_service       # preferred alias
