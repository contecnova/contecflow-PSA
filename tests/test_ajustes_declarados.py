"""Ajustes que el código lee y la configuración no declara.

Auditoría 2026-08. `getattr(settings, "X", defecto)` sobre un ajuste **no
declarado** devuelve siempre el defecto: la perilla no se puede tocar ni por
`.env` ni por variable de entorno, y quien la busque en la configuración no la
encuentra. Salieron **18**, y dos de ellas no eran una perilla ausente sino un
**nombre equivocado con el correcto al lado**:

| Leía | Existe | Consecuencia |
|---|---|---|
| `SMTP_PASSWORD` | `SMTP_PASS` | `smtp_pass` era siempre `None`, el `if smtp_user and smtp_pass` siempre falso y **`server.login()` no se llamaba nunca**: todos los correos de notificación salían sin autenticar. Contra cualquier servidor que exija autenticación, rechazados |
| `EMAILS_FROM_EMAIL` | `SMTP_FROM` | el remitente configurado se ignoraba |

Lo que delata el primero: en `notification_service.send_email`, la línea de
arriba lee **bien** `SMTP_FROM` y la de abajo **mal** `SMTP_PASSWORD`. La misma
función acertaba un nombre y fallaba el otro.

De las demás, once se han declarado con **exactamente el valor por defecto que
tenían** —así que el comportamiento no cambia, lo que cambia es que ahora se
pueden configurar— y cinco eran ramas muertas de datos de demostración en el
seed, retiradas en vez de convertidas en perillas.

Este test es el que impide que vuelva a entrar una.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from app.core.config import settings

#: Nombres que se leen con `getattr(settings, …)` a propósito sin declararlos.
#: Vacío: si algún día hace falta uno, va aquí con su motivo escrito, no
#: silenciosamente.
TOLERADOS: dict[str, str] = {}


def _lecturas_de_ajustes() -> list[tuple[str, int, str, str]]:
    """Los `getattr`/`hasattr` sobre algo que se llame «settings».

    Se mira el nombre del objeto y no su tipo porque el objeto llega con varios
    alias en el repo (`settings`, `_settings`, `s`, `app.core.config.settings`).
    Filtrar por nombre da algún falso negativo —un alias raro— pero ningún falso
    positivo, que es el lado por el que conviene equivocarse en un test que
    bloquea.
    """
    encontrados = []
    for f in sorted(pathlib.Path("app").rglob("*.py")):
        if "__pycache__" in f.as_posix():
            continue
        try:
            arbol = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for n in ast.walk(arbol):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id in ("getattr", "hasattr")):
                continue
            if len(n.args) < 2 or not isinstance(n.args[1], ast.Constant):
                continue
            obj = n.args[0]
            nombre_obj = (obj.id if isinstance(obj, ast.Name)
                          else obj.attr if isinstance(obj, ast.Attribute) else "")
            if "settings" not in nombre_obj.lower():
                continue
            clave = n.args[1].value
            if isinstance(clave, str):
                encontrados.append((f.as_posix(), n.lineno, clave, n.func.id))
    return encontrados


def test_EL_ESTRUCTURAL_todo_ajuste_que_se_lee_esta_declarado():
    """El que impide que vuelva a entrar una perilla que no se puede tocar.

    Un ajuste no declarado no da error: devuelve el defecto. Así que nadie se
    entera de que la configuración no se aplica — ni quien la escribe en el
    `.env` ni quien lee el código.
    """
    declarados = set(dir(settings))
    faltan = []
    for ruta, ln, clave, fn in _lecturas_de_ajustes():
        if clave in declarados or clave in TOLERADOS:
            continue
        faltan.append("%s:%d  %s(settings, %r)" % (ruta, ln, fn, clave))
    assert not faltan, (
        "hay %d ajustes que el código lee y `Settings` no declara:\n  %s\n\n"
        "Un `getattr` sobre un ajuste no declarado devuelve siempre el defecto: "
        "la perilla no se puede tocar por `.env` ni por entorno, y nadie se "
        "entera. Decláralo en app/core/config.py con el mismo valor por defecto "
        "que tenga el `getattr`, o quita la lectura si era una rama muerta."
        % (len(faltan), "\n  ".join(faltan))
    )


def test_el_detector_encuentra_lecturas():
    """Control de que el detector mira de verdad. Si devolviera lista vacía, el
    estructural de arriba pasaría sin comprobar nada."""
    lecturas = _lecturas_de_ajustes()
    assert len(lecturas) > 20, (
        "el detector sólo ha encontrado %d lecturas de ajustes: algo lo ha roto"
        % len(lecturas)
    )


# ── Los dos nombres equivocados, fijados ────────────────────────────────────

def test_EL_HALLAZGO_el_ajuste_de_contrasena_smtp_se_llama_SMTP_PASS():
    """El nombre que existe, y el que se leía.

    Si alguien renombra el ajuste, este test falla y obliga a mirar los dos
    sitios que lo leen — que es lo que no pasó cuando se escribió
    `SMTP_PASSWORD`.
    """
    assert hasattr(settings, "SMTP_PASS")
    assert not hasattr(settings, "SMTP_PASSWORD"), (
        "se ha creado `SMTP_PASSWORD`: ahora hay dos ajustes para lo mismo, que "
        "es peor que el defecto original"
    )


def test_EL_HALLAZGO_el_remitente_se_llama_SMTP_FROM():
    assert hasattr(settings, "SMTP_FROM")
    assert not hasattr(settings, "EMAILS_FROM_EMAIL")


def test_nadie_lee_ya_los_nombres_inexistentes():
    """Fija que los dos nombres malos no vuelven al código, ni en un sitio nuevo."""
    malos = {"SMTP_PASSWORD", "EMAILS_FROM_EMAIL"}
    usos = [
        "%s:%d  %r" % (ruta, ln, clave)
        for ruta, ln, clave, _ in _lecturas_de_ajustes() if clave in malos
    ]
    assert not usos, "vuelven a leerse nombres de ajuste inexistentes:\n  %s" % "\n  ".join(usos)


# ── Los once declarados, con su valor de antes ──────────────────────────────

@pytest.mark.parametrize("clave,esperado", [
    ("TWILIO_ACCOUNT_SID", None),
    ("TWILIO_AUTH_TOKEN", None),
    ("TWILIO_FROM_NUMBER", None),
    ("CLIENT_TOKEN_EXPIRE_HOURS", 72),
    ("PORTAL_SHARE_LINK_EXPIRE_HOURS", 72),
    ("JWT_ALGORITHM", "HS256"),
    ("PBKDF2_ITERATIONS", 260000),
    ("MAX_APPS_PER_USER", 10),
    ("WEBHOOK_CB_THRESHOLD", 5),
    ("AI_REVENUE_HOURLY_RATE_FALLBACK", 85.0),
    ("UPLOAD_DIR", "uploads"),
])
def test_los_declarados_conservan_el_defecto_que_tenian(clave, esperado):
    """Declararlos no podía cambiar ningún comportamiento.

    Cada uno se declaró con **exactamente** el valor que devolvía su `getattr`,
    comprobado uno a uno. Este test lo fija: si alguien cambia un defecto, tiene
    que ser una decisión y no un efecto colateral de haberlos movido.
    """
    assert getattr(settings, clave) == esperado


@pytest.mark.parametrize("clave,valor,esperado", [
    ("PBKDF2_ITERATIONS", "999000", 999000),
    ("CLIENT_TOKEN_EXPIRE_HOURS", "6", 6),
    ("PORTAL_SHARE_LINK_EXPIRE_HOURS", "1", 1),
    ("WEBHOOK_CB_THRESHOLD", "2", 2),
    ("MAX_APPS_PER_USER", "3", 3),
    ("AI_REVENUE_HOURLY_RATE_FALLBACK", "120.5", 120.5),
    ("UPLOAD_DIR", "/datos/subidas", "/datos/subidas"),
    ("TWILIO_ACCOUNT_SID", "AC123", "AC123"),
    ("JWT_ALGORITHM", "HS512", "HS512"),
])
def test_los_declarados_SE_PUEDEN_configurar_de_verdad(monkeypatch, clave, valor,
                                                       esperado):
    """Lo que de verdad se ganó, comprobado poniendo la variable de entorno.

    No basta con que el campo esté declarado: la afirmación es «ahora esta
    perilla se puede tocar». Así que se toca — se pone la variable, se
    reconstruye `Settings` y se mira el valor. Antes de declararlos esto habría
    dado el defecto en los nueve casos, porque el `getattr` no miraba el
    entorno.
    """
    from app.core.config import Settings

    monkeypatch.setenv(clave, valor)
    assert getattr(Settings(), clave) == esperado, (
        "%s no se puede configurar por entorno: la perilla sigue sin existir"
        % clave
    )


def test_la_lista_de_tolerados_esta_vacia():
    """Si algún día se añade uno, tiene que llevar motivo escrito.

    Una lista de excepciones sin motivos es donde se esconden los ajustes rotos
    nuevos — el mismo razonamiento que en `test_importes_diferidos.py`.
    """
    for clave, motivo in TOLERADOS.items():
        assert motivo.strip(), "%s está tolerado sin motivo escrito" % clave
