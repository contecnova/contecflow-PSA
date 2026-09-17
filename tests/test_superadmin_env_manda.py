"""El `.env` manda sobre la contraseña del superadmin.

Reportado en `contecmind` el 2026-09-17 —«uso las credenciales que aparecen en
.env y no funcionan»— y encontrado aquí al revisar el resto de soluciones.

Aquí era peor que allí. `SUPERADMIN_PASSWORD`:

  · estaba declarada en `.env`,
  · estaba VALIDADA en `app/core/config.py`, que se niega a arrancar si es
    débil o si conserva un valor de ejemplo,
  · y NO se usaba para poner ninguna contraseña.

El superadmin recibía `DEFAULT_USER_PASSWORD` como cualquier otro usuario
semilla, y solo en el momento de crearlo: con la cuenta ya existente, ninguna de
las dos se aplicaba. O sea que el fichero bloqueaba el arranque por una
credencial que después ignoraba.

Estos tests miran el CÓDIGO y no el resultado de un seed completo a propósito:
`seed()` levanta media base de demostración, y lo que hay que fijar es la
decisión —qué contraseña recibe el superadmin y cuándo— no el contenido de la
demo, que ya cubren `test_seed_fases.py` y `test_seed_fixture_parity.py`.
"""

from __future__ import annotations

import inspect

from app.db.seed_parts import core


def _fuente_del_bucle_de_usuarios() -> str:
    """El código que crea/actualiza los usuarios semilla.

    Vive en `_sembrar_usuarios()`, no en `seed()`: la función se partió por
    fases en la auditoría 2026-08 (P3-18). Se busca por NOMBRE de función y no
    por posición para que una nueva partición no deje este test mirando al
    vacío y pasando en verde.
    """
    assert hasattr(core, "_sembrar_usuarios"), (
        "`_sembrar_usuarios` ya no existe: si la siembra de usuarios se ha "
        "movido, apunta este test a su nuevo sitio en vez de borrarlo."
    )
    return inspect.getsource(core._sembrar_usuarios)


def test_el_superadmin_recibe_la_contrasena_del_env() -> None:
    """Y no `DEFAULT_USER_PASSWORD`, que es la del resto de usuarios de demo."""
    tramo = _fuente_del_bucle_de_usuarios()

    assert "settings.SUPERADMIN_PASSWORD" in tramo, (
        "El superadmin no recibe `SUPERADMIN_PASSWORD`. Esa variable está "
        "declarada en el `.env` y VALIDADA en config (el arranque se niega si "
        "es débil): si además no se usa, el fichero anuncia una credencial que "
        "no deja entrar."
    )


def test_la_contrasena_se_reafirma_aunque_la_cuenta_ya_exista() -> None:
    """Una vía de recuperación que solo funciona la primera vez no es una vía.

    Antes el `if not u:` dejaba fuera por completo a la cuenta existente: ni
    contraseña, ni estado activo.
    """
    tramo = _fuente_del_bucle_de_usuarios()

    assert "elif es_superadmin:" in tramo, (
        "No hay rama para el superadmin YA EXISTENTE. Sin ella, cambiar "
        "`SUPERADMIN_PASSWORD` en el `.env` no surte efecto nunca."
    )
    assert tramo.count("get_password_hash(pwd_usuario)") >= 2, (
        "La contraseña debe fijarse tanto al crear la cuenta como al "
        "reencontrarla."
    )


def test_el_superadmin_se_reactiva_si_estaba_desactivado() -> None:
    """Quedarse fuera de la propia instalación debe tener salida por el `.env`."""
    tramo = _fuente_del_bucle_de_usuarios()

    assert "is_active = True" in tramo, (
        "El seed no reactiva al superadmin. Una cuenta desactivada deja al "
        "dueño de la instalación fuera sin más salida que tocar la base a mano."
    )


def test_el_resto_de_usuarios_semilla_no_usan_la_del_superadmin() -> None:
    """Son cuentas de DEMOSTRACIÓN: darles la del superadmin sería repartirla."""
    tramo = _fuente_del_bucle_de_usuarios()

    assert "if es_superadmin else seed_pwd" in tramo, (
        "Los usuarios de demo deben seguir recibiendo `DEFAULT_USER_PASSWORD`."
    )
