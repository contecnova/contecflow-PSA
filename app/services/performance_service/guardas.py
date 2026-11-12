"""Busquedas acotadas a la organizacion de quien llama (pregunta, objetivo, plan, usuario); 404 si no es suya.

Parte de `app.services.performance_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from sqlalchemy.orm import Session
from app.models.performance import ReviewQuestion
from app.models.user import User
from app.core.errores import ErrorDeDominio
# ── Guardas por organizacion, movidas del endpoint ───────────────────────────
#
# Auditoria 2026-08 (hallazgo 22). Las consultas de `endpoints/performance.py`
# estaban ahi, y todas buscaban por id **sin acotar por organizacion**: la
# pregunta de un ciclo, el objetivo de un plan y el usuario evaluado. Lo unico
# que impedia editar o borrar la pregunta de otro cliente era el filtro
# implicito de `TenantSession`, y `organization_id` es nullable en todos estos
# modelos, asi que una fila sin organizacion queda fuera de ese filtro.
#
# Evaluaciones de desempeño: los datos son nominativos y sobre personas. Aqui la
# guarda explicita no es cosmetica.


from app.models.performance import DevGoal, DevelopmentPlan  # noqa: E402


def _org_de(user) -> "str | None":
    return getattr(user, "organization_id", None)


def pregunta_propia(db: Session, user, question_id: str) -> ReviewQuestion:
    """La pregunta, si es de la organizacion del usuario. 404 si no."""
    fila = (
        db.query(ReviewQuestion)
        .filter(
            ReviewQuestion.id == question_id,
            ReviewQuestion.organization_id == _org_de(user),
        )
        .first()
    )
    if not fila:
        raise ErrorDeDominio(404, "Pregunta no encontrada")
    return fila


def objetivo_propio(db: Session, user, goal_id: str) -> DevGoal:
    """El objetivo de desarrollo, si es de la organizacion del usuario."""
    fila = (
        db.query(DevGoal)
        .filter(
            DevGoal.id == goal_id,
            DevGoal.organization_id == _org_de(user),
        )
        .first()
    )
    if not fila:
        raise ErrorDeDominio(404, "Objetivo no encontrado")
    return fila


def plan_propio(db: Session, user, plan_id: str) -> DevelopmentPlan:
    """El plan de desarrollo, si es de la organizacion del usuario."""
    fila = (
        db.query(DevelopmentPlan)
        .filter(
            DevelopmentPlan.id == plan_id,
            DevelopmentPlan.organization_id == _org_de(user),
        )
        .first()
    )
    if not fila:
        raise ErrorDeDominio(404, "Plan no encontrado")
    return fila


def usuario_propio(db: Session, user, user_id: str) -> User:
    """El usuario evaluado, si es de la misma organizacion. 404 si no.

    Una evaluacion es nominativa: devolver 404 y no 403 evita confirmar que esa
    persona existe en otra organizacion.
    """
    fila = (
        db.query(User)
        .filter(User.id == user_id, User.organization_id == _org_de(user))
        .first()
    )
    if not fila:
        raise ErrorDeDominio(404, "Usuario no encontrado")
    return fila


def usuario_de_la_organizacion(db: Session, user, user_id: str):
    """El usuario si comparte organizacion, o `None`. Sin lanzar.

    La usan las comprobaciones de visibilidad, que resuelven al jefe del
    evaluado: sin acotar, la relacion de jefatura de otra organizacion decidia
    si se puede ver una evaluacion.
    """
    if not user_id:
        return None
    return (
        db.query(User)
        .filter(User.id == user_id, User.organization_id == _org_de(user))
        .first()
    )
