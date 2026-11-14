"""Segunda auditoría 2026-11: vista previa del PDF y métricas por proceso.

- DocumentsPage incrusta `/api/v1/documents/file/…` en un <iframe>, pero la API
  respondía `frame-ancestors 'none'` y nginx añadía `X-Frame-Options: DENY`.
- La API corre con 4 workers de uvicorn sin `PROMETHEUS_MULTIPROC_DIR`: cada
  scrape de /metrics devolvía solo el registro del worker que lo atendía.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _frame_ancestors(r) -> str:
    return re.search(r"frame-ancestors ([^;]+);", r.headers["content-security-policy"]).group(1)


def test_EL_HALLAZGO_el_fichero_del_documento_se_puede_incrustar_desde_el_propio_origen(client):
    r = client.get("/api/v1/documents/file/documents/1/v1/x.pdf")
    assert _frame_ancestors(r) == "'self'"
    assert r.headers["x-frame-options"] == "SAMEORIGIN"


def test_el_resto_de_la_api_sigue_sin_poder_incrustarse(client):
    r = client.get("/api/v1/projects")
    assert _frame_ancestors(r) == "'none'"
    assert r.headers["x-frame-options"] == "DENY"


def test_nginx_no_pisa_las_cabeceras_de_los_ficheros_de_documentos():
    conf = (REPO / "frontend/nginx.frontend.conf").read_text(encoding="utf-8")
    inicio = conf.index("location ^~ /api/v1/documents/file/")
    bloque = conf[inicio:conf.index("}", inicio)]
    # Con un add_header propio no se heredan el DENY ni la CSP del servidor.
    assert "add_header" in bloque
    assert "X-Frame-Options" not in bloque and "Content-Security-Policy" not in bloque
    assert "proxy_pass http://contecflow_api" in bloque


def test_compose_da_a_la_api_un_directorio_multiproceso_vacio_en_cada_arranque():
    import yaml

    api = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))["services"]["api"]
    d = api["environment"]["PROMETHEUS_MULTIPROC_DIR"]
    assert d
    # El merge del ancla conserva el resto del entorno común.
    assert api["environment"]["ENABLE_APSCHEDULER"] == "0"
    cmd = api["command"][-1]
    assert api["command"][:2] == ["sh", "-c"]
    assert cmd.index('rm -rf "$$PROMETHEUS_MULTIPROC_DIR"') < cmd.index('mkdir -p') < cmd.index("exec python -m uvicorn")
    assert '--workers "${API_WORKERS:-4}"' in cmd


def test_la_variable_de_compose_es_la_que_lee_la_configuracion(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", "/tmp/prometheus-multiproc")
    assert Settings().METRICS_MULTIPROC_DIR == "/tmp/prometheus-multiproc"


# ── pillow 13: lo que abre subidas de usuarios sigue funcionando ─────────────

def _png(w=640, h=360) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (w, h), (200, 30, 30, 255)).save(buf, format="PNG")
    return buf.getvalue()


def test_pillow_13_miniatura_y_resumen_visual_de_una_subida():
    import io

    import PIL
    from PIL import Image

    from app.services.collaboration._thumbnails import THUMB_MAX_DIM, _image_thumbnail
    from app.services.documents_service import _visual_summary_from_image_bytes

    assert int(PIL.__version__.split(".")[0]) >= 13
    jpeg = _image_thumbnail(_png())
    with Image.open(io.BytesIO(jpeg)) as im:
        assert im.format == "JPEG" and max(im.size) <= THUMB_MAX_DIM
    assert "horizontal" in _visual_summary_from_image_bytes(_png(), file_name="foto.png")
