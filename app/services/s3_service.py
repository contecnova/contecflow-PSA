"""
Document storage service.

Uses AWS S3 when credentials are configured (AWS_ACCESS_KEY + AWS_SECRET_KEY),
otherwise falls back to local disk storage under ``<project_root>/uploads/``.

Both backends expose the same interface so the rest of the codebase never
needs to know which backend is active.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Tuple

from app.core.config import settings
from app.core.security import create_access_token
from botocore.exceptions import ClientError

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
        """Return a short-lived API URL with a scoped access token for local files."""
        ttl_minutes = max(1, int((expiration_hours or 1) * 60))
        token = create_access_token(
            subject="document-file",
            extra={"document_file_access": True, "file_key": file_key},
            expires_delta=timedelta(minutes=ttl_minutes),
        )
        return f"/api/v1/documents/file/{file_key}?access={token}"

    def get_file_bytes(self, file_key: str) -> bytes:
        # Audit #C4: previous check used `startswith(str(upload_root)+"/")`
        # which is broken on Windows (Path.resolve() returns `\` separators).
        # `is_relative_to` performs the comparison on Path components, OS-agnostic.
        upload_root = _LOCAL_UPLOAD_ROOT.resolve()
        path = (upload_root / file_key).resolve()
        if not path.is_relative_to(upload_root):
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
    """AWS S3 file storage service.

    Initial config comes from env vars; if a Settings → Credenciales → AWS S3
    entry is set, calling ``reload_from_db(db, org_id)`` rebuilds the boto3
    client with those values. Call it from endpoints/services before the first
    S3 op of the request lifecycle (cheap thanks to the 60s creds cache).
    """

    def __init__(self):
        self.bucket = settings.AWS_S3_BUCKET
        self.region = settings.AWS_REGION
        self.url_expiration_hours = settings.S3_URL_EXPIRATION_HOURS
        self.client = None
        self._access_key = settings.AWS_ACCESS_KEY
        self._secret_key = settings.AWS_SECRET_KEY

        self._endpoint_url = settings.AWS_S3_ENDPOINT_URL
        try:
            self.client = self._build_client()
            logger.info(
                "S3Service initialized: bucket=%s, region=%s, endpoint=%s",
                self.bucket, self.region, self._endpoint_url or "AWS",
            )
        except Exception as e:
            logger.warning(f"S3 client could not be initialised: {e}")

    def _build_client(self):
        """Construye el cliente boto3. ÚNICO sitio donde se hace.

        Antes había dos bloques idénticos (aquí y en `reload_from_db`) y añadir
        un parámetro en uno y olvidarlo en el otro dejaba el cliente recargado
        con una configuración distinta a la inicial — el tipo de divergencia que
        sólo se manifiesta después de cambiar credenciales en caliente.
        """
        import boto3
        from botocore.config import Config as BotoConfig

        kwargs = {
            "region_name": self.region,
            "aws_access_key_id": self._access_key,
            "aws_secret_access_key": self._secret_key,
        }
        endpoint = getattr(self, "_endpoint_url", None)
        if endpoint:
            kwargs["endpoint_url"] = endpoint

        # Direccionamiento por ruta: obligatorio en MinIO y compatibles, que no
        # resuelven `bucket.host`. Si no se fuerza explícitamente, se deduce:
        # con endpoint propio, por ruta; contra AWS, el suyo por defecto.
        forzar_ruta = settings.AWS_S3_FORCE_PATH_STYLE
        if forzar_ruta is None:
            forzar_ruta = bool(endpoint)

        # Firma v4 SIEMPRE, también en las URLs firmadas. Sin pedirla, boto3
        # presigna con la v2 heredada (`AWSAccessKeyId=…&Signature=…`) aunque las
        # peticiones normales vayan en v4. MinIO la aceptaba y lo tapaba;
        # versitygw la rechaza («Please use AWS4-HMAC-SHA256») y AWS también en
        # las regiones y buckets nuevos. El síntoma era un 400 al descargar un
        # documento que se había subido bien.
        kwargs["config"] = BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"} if forzar_ruta else {},
        )

        return boto3.client("s3", **kwargs)

    def reload_from_db(self, db, org_id=None) -> None:
        """Re-read credentials from `app_settings` + integration_credentials registry.

        Falls back to env values when the DB row is absent. Safe to call on
        every request — the underlying lookup is cached.
        """
        try:
            from app.services.integration_credentials_service import get_provider_config
            from app.services.settings_service import get_runtime_int
            cfg = get_provider_config(db, "aws_s3", org_id=org_id)
            new_bucket = cfg.get("bucket") or settings.AWS_S3_BUCKET
            new_region = cfg.get("region") or settings.AWS_REGION
            new_access = cfg.get("access_key") or settings.AWS_ACCESS_KEY
            new_secret = cfg.get("secret_key") or settings.AWS_SECRET_KEY
            self.url_expiration_hours = get_runtime_int(db, "S3_URL_EXPIRATION_HOURS", org_id) or settings.S3_URL_EXPIRATION_HOURS

            # El endpoint entra en la comparación: si sólo cambiara él, el
            # early-return dejaría el cliente apuntando al almacén anterior.
            new_endpoint = cfg.get("endpoint_url") or settings.AWS_S3_ENDPOINT_URL
            if (new_bucket, new_region, new_access, new_secret, new_endpoint) == (
                self.bucket, self.region, self._access_key, self._secret_key,
                getattr(self, "_endpoint_url", None),
            ):
                return  # sin cambios, se conserva el cliente actual
            self.bucket, self.region = new_bucket, new_region
            self._access_key, self._secret_key = new_access, new_secret
            # El endpoint también puede venir de la configuración por
            # organización: un cliente puede tener su propio almacén S3.
            self._endpoint_url = new_endpoint
            self.client = self._build_client()
            logger.info(
                "S3Service reloaded: bucket=%s, region=%s, endpoint=%s",
                self.bucket, self.region, self._endpoint_url or "AWS",
            )
        except Exception as exc:
            logger.warning("S3Service reload failed: %s", exc)

    def is_available(self) -> bool:
        return (
            self.client is not None
            and bool(self._access_key)
            and bool(self._secret_key)
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
            logger.warning("Error obteniendo tamaño de archivo S3 key=%s", s3_key, exc_info=True)
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
