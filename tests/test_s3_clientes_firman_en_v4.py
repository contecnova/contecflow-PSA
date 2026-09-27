"""Los tres clientes S3 tienen que funcionar contra un S3 compatible, no solo contra AWS.

Salió al cambiar MinIO por versitygw (27-09-2026). MinIO era permisivo y tapaba
tres fallos que cualquier S3 estricto —versitygw, o AWS en regiones y buckets
nuevos— destapa:

1. `S3Service` presignaba con la firma v2 heredada. boto3 solo usa la v4 en las
   URLs firmadas si se le pide; las peticiones normales iban en v4 y por eso subir
   funcionaba y descargar daba un 400.
2. El almacén de colaboración, lo mismo, y sin direccionamiento por ruta, que es
   lo único que entiende un servidor de un solo host.
3. eSign leía el documento con un `boto3.client("s3")` recién creado, sin
   endpoint ni credenciales: con el almacén del stack preguntaba a AWS, fallaba y
   caía al disco, donde el documento no está.

Ninguna necesita red: una URL firmada se calcula en local.
"""

from __future__ import annotations

import types

from app.core.config import settings


def test_s3service_presigna_en_v4_y_por_ruta(monkeypatch):
    monkeypatch.setattr(settings, "AWS_S3_BUCKET", "contecflow-documents")
    monkeypatch.setattr(settings, "AWS_S3_ENDPOINT_URL", "http://127.0.0.1:9003")
    monkeypatch.setattr(settings, "AWS_ACCESS_KEY", "k")
    monkeypatch.setattr(settings, "AWS_SECRET_KEY", "s")
    from app.services.s3_service import S3Service

    url = S3Service().generate_presigned_url("documents/d/v1/x.pdf")

    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url, f"URL firmada en v2: {url}"
    assert url.startswith("http://127.0.0.1:9003/contecflow-documents/"), (
        f"no va por ruta, y un servidor de un solo host no resuelve `bucket.host`: {url}"
    )


def test_s3service_firma_en_v4_tambien_contra_aws(monkeypatch):
    """Sin endpoint propio no se fuerza la ruta, pero la v4 sí: AWS rechaza la v2
    en las regiones y buckets nuevos."""
    monkeypatch.setattr(settings, "AWS_S3_BUCKET", "contecflow-documents")
    monkeypatch.setattr(settings, "AWS_S3_ENDPOINT_URL", None)
    monkeypatch.setattr(settings, "AWS_ACCESS_KEY", "k")
    monkeypatch.setattr(settings, "AWS_SECRET_KEY", "s")
    from app.services.s3_service import S3Service

    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in S3Service().generate_presigned_url("x")


def test_colaboracion_presigna_en_v4_y_por_ruta(monkeypatch):
    monkeypatch.setenv("COLLAB_S3_BUCKET", "contecflow-documents")
    monkeypatch.setenv("COLLAB_S3_ENDPOINT", "http://127.0.0.1:9003")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "s")
    from app.services.collaboration._storage_s3 import S3FileStorage

    url = S3FileStorage().signed_url("t/a.txt")

    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url, f"URL firmada en v2: {url}"
    assert url.startswith("http://127.0.0.1:9003/contecflow-documents/"), url


def test_esign_lee_con_el_cliente_configurado(monkeypatch):
    """Antes creaba `boto3.client("s3")` sin endpoint ni credenciales."""
    from app.services import esign_service, s3_service

    leidos = []

    class _Cliente:
        def get_object(self, Bucket, Key):
            leidos.append((Bucket, Key))
            return {"Body": types.SimpleNamespace(read=lambda: b"%PDF firmado")}

    almacen = s3_service.S3Service.__new__(s3_service.S3Service)
    almacen.client = _Cliente()
    almacen.bucket = "contecflow-documents"
    almacen._access_key, almacen._secret_key = "k", "s"
    monkeypatch.setattr(s3_service, "file_storage", almacen)

    import boto3

    def _prohibido(*a, **kw):
        raise AssertionError("eSign no debe crear su propio cliente S3 sin configurar")

    monkeypatch.setattr(boto3, "client", _prohibido)

    version = types.SimpleNamespace(version_num=1, file_name="contrato.pdf", file_key="documents/d/v1/x.pdf")
    doc = types.SimpleNamespace(id="d", versions=[version])

    contenido, nombre, ext = esign_service._read_document_bytes(doc, None)

    assert contenido == b"%PDF firmado"
    assert (nombre, ext) == ("contrato.pdf", "pdf")
    assert leidos == [("contecflow-documents", "documents/d/v1/x.pdf")]
