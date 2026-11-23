"""Auditoría 22-11-2026, informe 01, segunda ronda: guardas por capacidad (M9) y bajos.

- M9: ninguna ruta de `app/api` se guarda ya por rol (`Depends(require_admin)` y
  compañía) ni con una guarda hecha a mano en el cuerpo; todas por capacidad del
  catálogo (`requiere_capacidad("x")`), con los mismos roles que tenían.
- B1: /health y /ready no dicen versión ni entorno en staging/producción.
- B2: el arranque local escucha en 127.0.0.1 (BACKEND_HOST para abrirlo).
- B3: docker-clean dice la verdad sobre los volúmenes externos.
- B4/B5: la imagen sin curl; Prometheus sin la API de ciclo de vida.
- B9: la IP del cliente sale siempre de `extract_client_ip` (proxy de confianza).
- B11: el JWT se decodifica una vez por petición.
- B14: la traza del log no lleva datos personales en el mensaje.
- M10: las revisiones destructivas están marcadas en NAMING_CONVENTION.md.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
API = RAIZ / "app" / "api"

GUARDA_DE_ROL = re.compile(
    r"\bDepends\(\s*require_(admin_or_pm|admin_or_hr|any_manager|internal_user|worker|admin)\s*\)")


def _fuentes_api():
    for p in sorted(API.rglob("*.py")):
        yield p, p.read_text(encoding="utf-8")


# ── M9 ───────────────────────────────────────────────────────────────────────

def test_ninguna_ruta_se_guarda_ya_por_rol():
    """1 425 pares (método, ruta) guardados solo por rol el 22-11-2026; 0 desde el 23-11-2026."""
    malas = [f"{p.relative_to(RAIZ)}:{t[:m.start()].count(chr(10)) + 1}"
             for p, t in _fuentes_api() for m in GUARDA_DE_ROL.finditer(t)]
    assert not malas, "Guarda de rol en vez de capacidad (usa requiere_capacidad):\n  " + "\n  ".join(malas)


def test_no_quedan_guardas_hechas_a_mano():
    """`_require_admin` (predictive_observability), `verify_admin_or_governance_role`
    (ABAC, gobierno de IA, SOC), `_permiso_de_gobierno` y `require_gestor_de_personas`
    pasaron a capacidades en la firma."""
    prohibidas = re.compile(r"\b(_require_admin|verify_admin_or_governance_role|_permiso_de_gobierno"
                            r"|require_gestor_de_personas)\s*\(")
    malas = [f"{p.relative_to(RAIZ)}" for p, t in _fuentes_api() if prohibidas.search(t)]
    assert not malas, malas


def test_ningun_endpoint_empieza_con_un_403_por_rol_en_el_cuerpo():
    """Un `if current_user.role not in (...)`/`!= ...` → 403 como primera decisión del
    cuerpo es una guarda a mano: la pantalla (capacidades) y la API discrepan. Las
    condiciones mixtas (propietario o admin) son control de objeto y se quedan."""
    malas = []
    for p, t in _fuentes_api():
        for fn in ast.walk(ast.parse(t)):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for st in fn.body:
                if (isinstance(st, ast.If) and isinstance(st.test, ast.Compare) and len(st.body) == 1
                        and isinstance(st.body[0], ast.Raise)
                        and isinstance(st.test.left, ast.Attribute) and st.test.left.attr == "role"
                        and isinstance(st.test.ops[0], (ast.NotIn, ast.NotEq))):
                    malas.append(f"{p.relative_to(RAIZ)}::{fn.name}")
    assert not malas, malas


def test_las_capacidades_de_guarda_no_tienen_modulo_y_sus_roles_existen():
    """Las capacidades creadas por la migración de guardas (bloque generado del catálogo)
    no llevan `modulo`: así no cierran más que la `require_*` de antes."""
    from app.core.capacidades import CAPACIDADES, ROLES
    texto = (RAIZ / "app" / "core" / "capacidades.py").read_text(encoding="utf-8")
    bloque = texto[texto.index("# >>> guardas_a_capacidades"):texto.index("# <<< guardas_a_capacidades")]
    nombres = re.findall(r'^\s+"([a-z_]+\.[a-z_]+)": _c\(', bloque, re.M)
    assert len(nombres) >= 95
    for n in nombres:
        assert CAPACIDADES[n].modulo is None, n
        assert set(CAPACIDADES[n].roles) <= set(ROLES) and CAPACIDADES[n].roles, n


def test_el_frontend_conoce_todas_las_capacidades():
    from app.core.capacidades import CAPACIDADES
    ts = (RAIZ / "frontend" / "src" / "permisos" / "capacidades.ts").read_text(encoding="utf-8")
    lista = set(re.findall(r"'([a-z_]+\.[a-z_]+)'", ts[:ts.index("] as const")]))
    assert lista == set(CAPACIDADES), (sorted(set(CAPACIDADES) - lista), sorted(lista - set(CAPACIDADES)))


def test_misma_audiencia_que_la_guarda_de_rol():
    """Muestra de la equivalencia rol → capacidad (mismos roles que la `require_*`)."""
    from app.core.capacidades import CAPACIDADES
    esperado = {
        "sd.administrar": {"admin"}, "sd.gestionar": {"admin", "pm", "team_lead", "hr"},
        "sd.completo": {"admin", "pm", "team_lead", "hr", "employee"},
        "proyectos.dirigir": {"admin", "pm"}, "personas.rrhh": {"admin", "hr"},
        "tareas.trabajar": {"admin", "pm", "team_lead", "hr", "employee", "subcontractor"},
        "observabilidad.administrar": {"admin"}, "gobierno.administrar": {"admin"},
        "clientes.dirigir": {"admin", "pm"}, "alm.personas": {"admin", "pm", "hr"},
    }
    for cap, roles in esperado.items():
        assert set(CAPACIDADES[cap].roles) == roles, cap


@pytest.mark.parametrize("rol, puede", [("admin", True), ("pm", True), ("hr", False), ("employee", False)])
def test_guarda_de_capacidad_deniega_como_la_de_rol(rol, puede):
    from app.core.deps import requiere_capacidad
    from app.models.user import UserRole

    class _U:
        is_superadmin = False
        role = UserRole(rol)

    guarda = requiere_capacidad("proyectos.dirigir")
    if puede:
        guarda(current_user=_U(), db=None)
    else:
        with pytest.raises(Exception) as e:
            guarda(current_user=_U(), db=None)
        assert e.value.status_code == 403 and e.value.code == "capacidad_requerida"


# ── Bajos del informe 01 ─────────────────────────────────────────────────────

def test_health_y_ready_sin_version_ni_entorno_en_produccion(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    h = client.get("/health").json()
    assert "version" not in h and "project" not in h and h["status"] == "ok"
    r = client.get("/ready").json()
    assert "environment" not in r
    assert all(set(v) == {"status"} for v in r["checks"].values())


def test_health_con_detalle_en_desarrollo(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    assert "version" in client.get("/health").json()


def test_arranque_local_en_127_0_0_1():
    sh = (RAIZ / "setup.sh").read_text(encoding="utf-8")
    bat = (RAIZ / "setup.bat").read_text(encoding="utf-8")
    assert '--host "${BACKEND_HOST:-127.0.0.1}"' in sh and "--host 0.0.0.0" not in sh
    assert 'if not defined BACKEND_HOST set "BACKEND_HOST=127.0.0.1"' in bat and "--host 0.0.0.0" not in bat
    assert "\r" not in sh
    assert not re.search(rb"\r(?!\n)", (RAIZ / "setup.bat").read_bytes())


def test_docker_clean_dice_la_verdad():
    sh = (RAIZ / "setup.sh").read_text(encoding="utf-8")
    bat = (RAIZ / "setup.bat").read_text(encoding="utf-8")
    for t in (sh, bat):
        assert "borra todos los datos" not in t
        assert "contecflow_postgres_data" in t and "--profile observability" in t


def test_imagen_sin_curl_y_prometheus_sin_lifecycle():
    df = (RAIZ / "deploy" / "Dockerfile.backend").read_text(encoding="utf-8")
    assert "apt-get install" not in df and "ARG PYTHON_IMAGE" in df
    compose = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    assert "--web.enable-lifecycle\n" not in compose.replace("\r\n", "\n")


def test_la_ip_del_cliente_sale_del_extractor_comun():
    malas = [str(p.relative_to(RAIZ)) for p, t in _fuentes_api() if "request.client.host" in t]
    assert not malas, malas


def test_ip_del_cliente_tras_proxy_de_confianza(monkeypatch):
    from types import SimpleNamespace
    from app.core import network
    monkeypatch.setattr(network.settings, "TRUST_PROXY_HEADERS", True, raising=False)
    monkeypatch.setattr(network.settings, "TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    peticion = SimpleNamespace(client=SimpleNamespace(host="10.1.2.3"),
                               headers={"x-forwarded-for": "203.0.113.9"})
    assert network.ip_del_cliente(peticion) in ("203.0.113.9", "10.1.2.3")
    assert network.ip_del_cliente(SimpleNamespace(client=None, headers={})) is None


def test_el_jwt_se_decodifica_una_vez_por_peticion(monkeypatch):
    from types import SimpleNamespace
    from app.core import security
    llamadas = []
    monkeypatch.setattr(security, "decode_token", lambda t: llamadas.append(t) or {"sub": "u", "type": "access"})
    peticion = SimpleNamespace(state=SimpleNamespace())
    for _ in range(5):
        assert security.decode_token_de_peticion(peticion, "tok")["sub"] == "u"
    assert llamadas == ["tok"]
    otra = SimpleNamespace(state=SimpleNamespace())
    security.decode_token_de_peticion(otra, "tok")
    assert llamadas == ["tok", "tok"]  # el memo no sobrevive a la petición


def test_traza_del_log_sin_datos_personales():
    from app.main import _traza_saneada
    try:
        raise ValueError("fallo con ana.garcia@example.com")
    except ValueError as exc:
        traza = _traza_saneada(exc)
    assert "ana.garcia@example.com" not in traza and "ValueError" in traza and "test_traza" in traza


def test_revisiones_destructivas_marcadas():
    import sys
    sys.path.insert(0, str(RAIZ / "scripts"))
    from copia_antes_de_migrar import _DESTRUCTIVA, _upgrade_de
    detectadas = {p.stem for p in (RAIZ / "alembic" / "versions").glob("*.py")
                  if _DESTRUCTIVA.search(_upgrade_de(str(p)))}
    doc = (RAIZ / "alembic" / "NAMING_CONVENTION.md").read_text(encoding="utf-8")
    seccion = doc[doc.index("## Destructive revisions"):doc.index("## Quick checklist")]
    marcadas = set(re.findall(r"^\| `([0-9a-z_]+)` \|", seccion, re.M))
    assert detectadas == marcadas, (sorted(detectadas - marcadas), sorted(marcadas - detectadas))


def test_scripts_de_arranque_antiguos_retirados():
    for nombre in ("start.sh", "start.bat", "clean_and_start.sh", "test_and_report.sh",
                   "update_endpoints_table.sh", "smoke_test_simple.py"):
        assert not (RAIZ / "scripts" / nombre).exists(), nombre


def test_filtro_de_tenant_sin_ramas_muertas():
    texto = (RAIZ / "app" / "db" / "session.py").read_text(encoding="utf-8")
    for nombre in ("_tenant_filter_for_model", "_tenant_where_for_model"):
        cuerpo = texto[texto.index(f"def {nombre}("):]
        cuerpo = cuerpo[:cuerpo.index("\n\n\n")]
        assert "hasattr(model, \"project_id\")" not in cuerpo and "actor_id" not in cuerpo.split('"""')[-1]
