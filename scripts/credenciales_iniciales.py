"""Banner de usuarios de prueba de setup.bat y setup.sh (23-11-2026).

Antes los dos setup anunciaban `DEFAULT_USER_PASSWORD` para todos, también
para `admin`, cuya contraseña la pone la semilla desde `SUPERADMIN_PASSWORD`:
el banner mentía justo para la cuenta que más importa. Además setup.bat leía la
contraseña con expansión retardada y perdía los `!`.

Ahora el banner sale de aquí, con la misma regla que la semilla y que
`scripts/sincronizar_contrasenas_demo.py`:

* `admin` (superadmin) → `SUPERADMIN_PASSWORD`;
* `ana.torres`, `luis.vega`, `rrhh` → `DEFAULT_USER_PASSWORD`.

Solo lista los usuarios que existen y están activos (en modo clean, solo admin).
Fuera de development/test NO imprime contraseñas: dice de qué variable salen.
Escribe directamente en la consola (sin pasar por `cmd`); los textos fijos van
en ASCII para la consola de Windows.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

USUARIOS = (
    ("admin", "Direccion (superadmin)", "SUPERADMIN_PASSWORD"),
    ("ana.torres", "PM", "DEFAULT_USER_PASSWORD"),
    ("luis.vega", "Empleado", "DEFAULT_USER_PASSWORD"),
    ("rrhh", "RRHH", "DEFAULT_USER_PASSWORD"),
)
ENTORNOS_QUE_MUESTRAN = {"development", "test"}


def usuarios_activos() -> set[str] | None:
    """Los de `USUARIOS` que existen y están activos; None si no se puede leer la base."""
    try:
        from app.db.session import SessionLocal, declarar_sistema
        from app.models.user import User

        db = declarar_sistema(SessionLocal(), "setup: banner de usuarios")
        try:
            filas = db.query(User.username, User.is_active).filter(
                User.username.in_([u for u, _, _ in USUARIOS])).all()
            return {nombre for nombre, activo in filas if activo}
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - el banner no puede tumbar el arranque
        return None


def lineas(entorno: str, valores: dict[str, str], existentes: set[str] | None) -> list[str]:
    mostrar = entorno in ENTORNOS_QUE_MUESTRAN
    salida = ["  Usuarios de prueba:"]
    for usuario, papel, variable in USUARIOS:
        if existentes is not None and usuario not in existentes:
            continue
        if mostrar and valores.get(variable):
            credencial = valores[variable]
        else:
            credencial = f"(la de {variable} en .env)"
        salida.append(f"    {usuario:<10} / {credencial}   - {papel}")
    if existentes is not None and not existentes:
        salida.append("    (ninguno de los usuarios de prueba existe en esta base)")
    if not mostrar:
        salida.append(f"  ENVIRONMENT={entorno}: las contrasenas no se muestran fuera de development/test.")
    else:
        salida.append("  admin usa SUPERADMIN_PASSWORD; el resto, DEFAULT_USER_PASSWORD (.env).")
    return salida


def main() -> int:
    try:
        from app.core.config import settings
        entorno = settings.ENVIRONMENT
        valores = {"SUPERADMIN_PASSWORD": settings.SUPERADMIN_PASSWORD or "",
                   "DEFAULT_USER_PASSWORD": settings.DEFAULT_USER_PASSWORD or ""}
    except Exception:  # noqa: BLE001
        entorno, valores = "production", {}
    for linea in lineas(entorno, valores, usuarios_activos()):
        print(linea)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
