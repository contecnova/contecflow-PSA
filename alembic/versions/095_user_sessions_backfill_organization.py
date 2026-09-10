"""El panel de sesiones activas estaba vacio: `user_sessions.organization_id` a NULL.

Auditoria 2026-08. La columna la anadio la auditoria #7 —lo dice el comentario
que lleva al lado en `app/models/sessions.py`— y **nadie la rellenaba**:
`register_or_rotate_user_session` construia la fila con `user_id`,
`refresh_token_jti`, `auth_method` y `created_at`, y nada mas.

El filtro de tenant es `organization_id == org`, y una fila con NULL **no la ve
su propia organizacion**: solo un superadmin. Medido de punta a punta:

    GET    /auth/sessions/active   -> 0 sesiones, siempre, a cualquier usuario
    DELETE /auth/sessions/{id}     -> ninguna fila que revocar

Sin un solo error en los registros: una lista vacia. Y «revocar este
dispositivo» no es una comodidad, es un control de seguridad — si un usuario ve
un inicio de sesion que no reconoce, esa es la palanca que tiene.

El arreglo del codigo va en `app/services/session_security.py`
(`_organizacion_del_usuario`) y ademas cura al rotar: una fila con NULL recibe
su organizacion la proxima vez que ese usuario refresca el token. Esta revision
es para las que no vuelvan pronto — una sesion abierta de hace semanas seguiria
invisible hasta que su dueno volviera a entrar.

## De donde sale la organizacion

De `users.organization_id`, por `user_sessions.user_id`. No hay ninguna otra
fuente y no hace falta: una sesion es de un usuario y un usuario tiene una
organizacion.

**No hay recurso a la organizacion por defecto**, y es deliberado. Las
revisiones 076 y 080 lo hacian, y eso reparte a un tenant las filas de los
demas; aqui una sesion cuyo usuario no existe o no tiene organizacion se queda
como esta. Una sesion huerfana no vale nada: no se puede usar para autenticarse
—el `refresh` busca por usuario— y lo que hay que hacer con ella es caducarla,
no adoptarla.

## Idempotente

Solo toca filas con `organization_id IS NULL`. Aplicarla dos veces no cambia
nada, y si la tabla no existe —una base anterior a la auditoria #7— no hace
nada.

## Downgrade

**No revierte el relleno**, y no puede. Volver a poner NULL en las filas que
esta revision arreglo exigiria saber cuales eran, y no se guarda esa lista;
ponerlo en todas volveria a esconder el panel a todo el mundo, incluidas las
sesiones que nacen ya con organizacion desde el arreglo del codigo. Es la misma
decision, y por la misma razon, que en las revisiones 092 y 093.

Revision ID: 095_user_sessions_backfill_organization
Revises: 094_columnas_que_el_codigo_leia_sin_existir
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa


revision = "095_user_sessions_backfill_organization"
down_revision = "094_columnas_que_el_codigo_leia_sin_existir"
branch_labels = None
depends_on = None

TABLA = "user_sessions"


def _existe_tabla(nombre: str) -> bool:
    return nombre in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not (_existe_tabla(TABLA) and _existe_tabla("users")):
        return

    conexion = op.get_bind()

    pendientes = conexion.execute(sa.text(
        f"SELECT COUNT(*) FROM {TABLA} WHERE organization_id IS NULL"
    )).scalar() or 0

    # Un UPDATE con subconsulta y no un JOIN: SQLite no acepta `UPDATE ... FROM`
    # en todas las versiones que este proyecto soporta, y la subconsulta
    # correlacionada funciona igual en SQLite y en PostgreSQL.
    conexion.execute(sa.text(f"""
        UPDATE {TABLA}
           SET organization_id = (
                   SELECT u.organization_id
                     FROM users u
                    WHERE u.id = {TABLA}.user_id
               )
         WHERE organization_id IS NULL
           AND EXISTS (
                   SELECT 1
                     FROM users u
                    WHERE u.id = {TABLA}.user_id
                      AND u.organization_id IS NOT NULL
               )
    """))

    restantes = conexion.execute(sa.text(
        f"SELECT COUNT(*) FROM {TABLA} WHERE organization_id IS NULL"
    )).scalar() or 0

    print(f"[095] {TABLA}: {pendientes - restantes} sesiones rellenadas, "
          f"{restantes} sin organizacion (usuario inexistente o sin org)")


def downgrade() -> None:
    """No revierte el relleno. El porque esta en la cabecera del modulo."""
    return
