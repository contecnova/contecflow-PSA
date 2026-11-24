"""
Semantic engine service — business logic extracted from semantic_engine.py router.
"""
from sqlalchemy.orm import Session
import json
from app.models.service_desk._enums import ESTADOS_DE_TICKET_RESUELTOS
from app.models.project import ProjectMember
from app.models.semantic_engine import SemConfig
from app.models.semantic_engine import SemEmbeddingCache
from app.models.semantic_engine import SemProfile, perfil_semantico
from app.models.semantic_engine import SemAssignment, SemFeedback
from app.models.service_desk import Ticket
from app.models.task import Task
from app.models.user import User
from app.services.semantic_classifier import SemanticAssigner
from sqlalchemy import func
from app.core.config import settings


VALID_ENGINE_MODES = {"semantic", "llm", "hybrid", "rules_only"}


def ids_de_usuarios_del_ambito(db, current_user):
    """Los ids de usuario a los que el asignador semantico puede asignar.

    `None` significa «sin restriccion» y lo usa el asignador para mirar a todos:
    es lo que corresponde a un superadmin y a un sujeto sin organizacion.

    Auditoria 2026-08 (hallazgo 22): la consulta estaba en el endpoint. El
    `["__none__"]` del final tampoco es decorativo: una organizacion sin usuarios
    activos tiene que dar **cero candidatos**, y una lista vacia significaria
    «sin restriccion», que es justo lo contrario.
    """
    from app.models.user import User

    if bool(getattr(current_user, "is_superadmin", False)):
        return None
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        return None
    return [
        u.id for u in db.query(User.id).filter(
            User.is_active == True,  # noqa: E712
            User.organization_id == org_id,
        ).all()
    ] or ["__none__"]


def resolve_embeddings_backend_and_model(cfg) -> tuple[str, str]:
    """Return normalized embeddings backend and model name for UI/runtime visibility."""
    model = (getattr(cfg, "local_model_name", "") or "").strip()
    if model and model.lower() != "tfidf":
        return "transformer", model
    return "tfidf", settings.EMBEDDING_MODEL_NAME


def backend_en_uso(cfg) -> str:
    """El backend que el motor usa de verdad: `transformer` o `tfidf`.

    Revisión 2026-11: la pantalla enseñaba el configurado; sin
    sentence-transformers instalado (la imagen Docker) o sin el modelo
    descargado, el motor cae a TF-IDF en silencio.
    """
    import importlib.util
    from app.services import semantic_classifier as sc
    configurado, modelo = resolve_embeddings_backend_and_model(cfg)
    if configurado != "transformer":
        return "tfidf"
    if sc._MODEL_INSTANCE is not None and sc._MODEL_NAME in (modelo, "tfidf"):
        return "transformer" if sc._USE_TRANSFORMER else "tfidf"
    return "transformer" if importlib.util.find_spec("sentence_transformers") else "tfidf"


def get_assigner(db: Session):
    return SemanticAssigner(db)


def get_or_create_config(db: Session):
    cfg = db.query(SemConfig).first()
    if not cfg:
        cfg = SemConfig()
        # 24-11-2026 (migración 208): la configuración es por empresa. Sin
        # empresa en la sesión (precarga del arranque, trabajo de sistema) se
        # usan los valores por defecto en memoria, sin guardar una fila «de nadie».
        from app.db.empresa_obligatoria import empresa_para_registro
        if not empresa_para_registro(db):
            return cfg
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def serialize_config(cfg) -> dict:
    embeddings_backend, effective_model_name = resolve_embeddings_backend_and_model(cfg)
    return {
        "engine_mode":            str(cfg.engine_mode.value if hasattr(cfg.engine_mode, "value") else cfg.engine_mode),
        "threshold_ticket":       cfg.threshold_ticket,
        "threshold_task":         cfg.threshold_task,
        "threshold_expert_cache": cfg.threshold_expert_cache,
        "load_balance_weight":    cfg.load_balance_weight,
        "threshold_critical":     getattr(cfg, "threshold_critical", 0.80),
        "threshold_high":         getattr(cfg, "threshold_high", 0.70),
        "threshold_medium":       getattr(cfg, "threshold_medium", 0.55),
        "threshold_low":          getattr(cfg, "threshold_low", 0.45),
        "history_decay_days":     getattr(cfg, "history_decay_days", 90.0),
        "auto_assign_tickets":    cfg.auto_assign_tickets,
        "auto_assign_tasks":      cfg.auto_assign_tasks,
        "embeddings_backend":     embeddings_backend,
        "local_model_name":       cfg.local_model_name,
        "effective_model_name":   effective_model_name,
        "backend_en_uso":         backend_en_uso(cfg),
    }


def cache_item_embedding(db: Session, item_id: str, item_type: str,
                         text: str, user_id: str, *, commit: bool = True,
                         calidad: float | None = None):
    """Guarda el embedding de un ítem resuelto y quién lo resolvió (historial del nivel 3).

    23-11-2026: si el texto ya estaba, se renueva la fecha (el decaimiento cuenta
    desde la última resolución) y la persona; con `commit=False` solo `flush`
    (lo usa el cierre en segundo plano, que confirma una vez).
    """
    import hashlib
    from app.core.timeutil import utcnow
    text = (text or "").strip()
    if not text or not user_id:
        return None
    h = hashlib.sha256(" ".join(text.lower().split()).encode()).hexdigest()
    exist = db.query(SemEmbeddingCache).filter(
        SemEmbeddingCache.text_hash == h).first()
    if exist:
        exist.assigned_user_id = user_id
        exist.item_type = item_type
        exist.item_id = item_id or exist.item_id
        exist.created_at = utcnow()
        if calidad is not None:
            exist.resolution_quality = calidad
        cache = exist
    else:
        # 24-11-2026 (migración 208): `assigned_user_id` no es clave ajena y el
        # sellado no deduce nada; la empresa es la de la sesión o la de quien
        # resolvió. Sin ninguna, no se guarda (cortaría el cierre del ítem).
        from app.db.empresa_obligatoria import empresa_para_registro
        from app.models.user import User as _Usuario
        org = empresa_para_registro(db)
        if not org:
            with db.no_autoflush:
                org = getattr(db.get(_Usuario, user_id), "organization_id", None)
        if not org:
            import logging as _logging
            _logging.getLogger(__name__).warning("Embedding de %s sin empresa: no se guarda en la caché", item_type)
            return None
        assigner = get_assigner(db)
        emb = assigner._encode_single(text)
        cache = SemEmbeddingCache(
            organization_id=org,
            item_type=item_type, item_id=item_id or "",
            text_hash=h, text_snippet=text[:300],
            embedding=json.dumps(emb), assigned_user_id=user_id,
            resolution_quality=calidad,
        )
        db.add(cache)
    if commit:
        db.commit()
    else:
        db.flush()
    return cache


def auto_generate_profiles(db: Session, *, organization_id=None, is_superadmin: bool = False) -> dict:
    """Auto-generate semantic profiles for active users.

    Si ``organization_id`` es provisto y el caller no es superadmin, solo
    procesa users de esa organización. Antes este servicio iteraba
    User.is_active=True sin filtro → cross-tenant verificado (9 perfiles en
    2 orgs distintas).
    """
    q = db.query(User).filter(User.is_active == True)
    if organization_id and not is_superadmin:
        q = q.filter(User.organization_id == organization_id)
    users = q.all()
    assigner = get_assigner(db)
    created = updated = 0

    for u in users:
        parts = []
        if u.full_name:  parts.append(u.full_name)
        if u.job_title:  parts.append(u.job_title)
        if u.department: parts.append(u.department)

        resolved = db.query(Ticket).filter(
            Ticket.assigned_to_user_id == u.id,
            Ticket.status.in_(ESTADOS_DE_TICKET_RESUELTOS)
        ).order_by(Ticket.resolved_at.desc()).limit(20).all()
        for t in resolved[:5]:
            parts.append(f"Ticket resuelto: {t.title}")

        done = db.query(Task).filter(
            Task.assignee_id == u.id,
            Task.status == "done"
        ).order_by(Task.updated_at.desc()).limit(20).all()
        for t in done[:5]:
            parts.append(f"Tarea completada: {t.title}")

        profile_text = ". ".join(parts)
        if not profile_text.strip():
            continue

        profile = perfil_semantico(db, u.id)
        if not profile:
            profile = perfil_semantico(db, u.id, crear=True)
            created += 1
        else:
            updated += 1

        profile.profile_text = profile_text
        emb = assigner._encode_single(profile_text)
        profile.embedding = json.dumps(emb)

    db.commit()
    return {"created": created, "updated": updated, "total": created + updated}


def save_config(db: Session, cfg) -> None:
    """Commit and refresh a config object."""
    db.commit()
    db.refresh(cfg)


def enrich_suggestion(db: Session, result: dict, *, organization_id=None,
                       is_superadmin: bool = False) -> dict:
    """Add user name fields to a suggestion result dict (mutates in place).

    Multi-tenant: si ``organization_id`` se provee y el caller no es
    superadmin, solo expone full_name de users de esa org. Antes este enrich
    leía cualquier user.id sin filtro → leak menor de full_name cross-tenant.
    """
    def _safe_user(uid):
        if not uid:
            return None
        q = db.query(User).filter(User.id == uid)
        if organization_id and not is_superadmin:
            q = q.filter(User.organization_id == organization_id)
        return q.first()

    if result.get("suggested_user_id"):
        u = _safe_user(result["suggested_user_id"])
        result["suggested_user_name"] = u.full_name if u else None
    if result.get("top_scores"):
        enriched = {}
        for uid, score in result["top_scores"].items():
            u = _safe_user(uid)
            enriched[uid] = {"score": score, "name": u.full_name if u else "(fuera de tu organización)"}
        result["top_candidates"] = enriched
    return result


def get_project_member_ids(db: Session, project_id) -> list:
    """Return user_ids of all members of a project."""
    members = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id).all()
    return [m.user_id for m in members]


def list_profiles_with_users(db: Session) -> list:
    """Return all semantic profiles enriched with user names."""
    from app.models.user import User
    org_id = db.info.get("organization_id")
    is_superadmin = db.info.get("is_superadmin", False)
    query = db.query(SemProfile)
    if not is_superadmin:
        # Non-superadmins without an organisation must see zero rows (not all rows)
        if not org_id:
            return []
        # Segunda auditoría 2026-11 (#11): el perfil es por (usuario,
        # organización); se listan los de ESTA organización (incluye a los
        # miembros por pertenencia, que antes quedaban fuera por su ficha).
        query = query.filter(SemProfile.organization_id == org_id)
    profiles = query.all()
    result = []
    for p in profiles:
        u = db.query(User).filter(User.id == p.user_id).first()
        result.append({
            "id":            p.id,
            "user_id":       p.user_id,
            "user_name":     u.full_name if u else None,
            "profile_text":  p.profile_text[:200] if p.profile_text else "",
            "has_embedding": bool(p.embedding),
            "open_tickets":  p.open_tickets,
            "open_tasks":    p.open_tasks,
            "max_load":      p.max_load,
            "is_available":  p.is_available,
        })
    return result


def upsert_profile(db: Session, user_id, profile_text: str,
                   max_load=None, is_available: bool = True,
                   *, current_user=None) -> dict:
    """Create or update a semantic profile and return status dict.

    Authorization: si ``current_user`` se provee, sólo permite que el propio
    usuario, un admin/HR de su organización o un superadmin modifique el
    perfil. Antes cualquier user autenticado podía editar el perfil de otro
    pasando ``user_id`` en el body.
    """
    if current_user is not None:
        is_super = bool(getattr(current_user, "is_superadmin", False))
        is_self  = str(getattr(current_user, "id", "")) == str(user_id)
        role     = getattr(current_user, "role", None)
        role_val = role.value if hasattr(role, "value") else role
        is_priv  = role_val in ("admin", "hr")
        if not (is_super or is_self or is_priv):
            raise PermissionError("No tienes permisos para modificar este perfil")
        # Validación adicional para admin/hr: solo de su org
        target = db.query(User).filter(User.id == user_id).first()
        if (not is_super and is_priv and target
                and target.organization_id != getattr(current_user, "organization_id", None)):
            raise PermissionError("Solo puedes modificar perfiles de tu organización")

    profile = perfil_semantico(db, user_id, crear=True)
    profile.profile_text = profile_text
    profile.max_load     = max_load if max_load is not None else (profile.max_load or 10)
    profile.is_available = is_available
    if profile_text:
        assigner = get_assigner(db)
        emb = assigner._encode_single(profile_text)
        profile.embedding = json.dumps(emb)
    db.commit()
    db.refresh(profile)
    return {"ok": True, "has_embedding": bool(profile.embedding)}


def get_stats(db: Session) -> dict:
    """Compute and return semantic engine statistics."""
    total    = db.query(func.count(SemAssignment.id)).scalar() or 0
    accepted = db.query(func.count(SemAssignment.id)).filter(
        SemAssignment.was_accepted == True).scalar() or 0
    rejected = db.query(func.count(SemAssignment.id)).filter(
        SemAssignment.was_accepted == False).scalar() or 0
    pending  = db.query(func.count(SemAssignment.id)).filter(
        SemAssignment.was_accepted == None).scalar() or 0
    profiles   = db.query(func.count(SemProfile.id)).scalar() or 0
    cache_size = db.query(func.count(SemEmbeddingCache.id)).scalar() or 0
    feedback   = db.query(func.count(SemFeedback.id)).scalar() or 0
    # 23-11-2026: aceptadas y rechazadas REALES. Antes la pantalla de alta
    # registraba `was_accepted=True` al sugerir y nada pasaba a False si la
    # persona se reasignaba después: la precisión salía 100 % por construcción.
    # Ahora una sugerencia nace pendiente (None), se confirma al cerrar con la
    # misma persona y se rechaza al reasignar o al corregir.
    accuracy   = round(accepted / (accepted + rejected) * 100) \
                 if (accepted + rejected) > 0 else None
    by_mode_rows = db.query(
        SemAssignment.engine_mode,
        func.count(SemAssignment.id)
    ).group_by(SemAssignment.engine_mode).all()
    return {
        "total_suggestions": total,
        "accepted":          accepted,
        "rejected":          rejected,
        "pending":           pending,
        "accuracy_pct":      accuracy,
        "profiles":          profiles,
        "cache_size":        cache_size,
        "expert_feedback":   feedback,
        "by_mode":           {r[0]: r[1] for r in by_mode_rows},
        "resolved":          accepted + rejected,
    }


def record_assignment(db: Session, data: dict, created_by_id) -> dict:
    """Registra una sugerencia aceptada en pantalla y suma la carga del asignado.

    23-11-2026: el resultado lo decide el servidor, no el cliente: nace pendiente
    (`None`) si se aceptó a la persona sugerida y rechazada (`False`) si se eligió
    otra. Se confirma al cerrar (`cerrar_item`) y se rechaza al reasignar
    (`resolver_por_reasignacion`). El ítem tiene que ser de la empresa.
    """
    item_type = str(data.get("item_type") or "ticket")
    item_id = str(data.get("item_id") or "")
    if item_type not in ("ticket", "task") or _item_de_la_empresa(db, item_type, item_id) is None:
        from app.core.codigos_de_error import error
        raise error(404, "no_encontrado", detail="Elemento no encontrado", que=item_type)
    sugerido = data.get("suggested_user_id")
    aceptado = data.get("accepted_user_id") or sugerido
    sa = SemAssignment(
        item_type         = item_type,
        item_id           = item_id,
        item_title        = (data.get("item_title") or "")[:500],
        suggested_user_id = sugerido,
        accepted_user_id  = aceptado,
        was_accepted      = None if (not sugerido or aceptado == sugerido) else False,
        confidence        = data.get("confidence"),
        top_scores        = json.dumps(data.get("top_scores") or {}),
        engine_mode       = data.get("engine_mode"),
        estimated_hours   = data.get("estimated_hours"),
        complexity        = data.get("complexity"),
        reasoning         = (data.get("reasoning") or "")[:1000],
        needs_review      = bool(data.get("needs_review", False)),
        created_by        = created_by_id,
    )
    db.add(sa)
    if aceptado:
        p = perfil_semantico(db, aceptado)
        if p:
            if item_type == "ticket":
                p.open_tickets = max(0, (p.open_tickets or 0) + 1)
            else:
                p.open_tasks = max(0, (p.open_tasks or 0) + 1)
    db.commit()
    return {"ok": True}


def estimate_sprint_backlog(tasks: list, capacity_h: float, db: Session) -> dict:
    """Estimate effort for a list of sprint tasks."""
    assigner = get_assigner(db)
    estimates = []
    total_hours = 0.0
    complex_count = 0

    for t in tasks:
        est = assigner.estimate_effort(
            t.get("title", ""),
            t.get("description", ""),
            t.get("role_hint", "default"),
        )
        total_hours += est["base_hours"]
        if est["complexity"] == "complex":
            complex_count += 1
        estimates.append({
            "task_id": t.get("id"),
            "title": t.get("title", "")[:100],
            "story_points": t.get("story_points"),
            **est,
        })

    risk_pct = 10
    if complex_count / max(len(tasks), 1) > 0.3:
        risk_pct += 10
    recommended = round(total_hours * (1 + risk_pct / 100), 1)

    return {
        "estimates": estimates,
        "total_base_hours": round(total_hours, 1),
        "risk_premium_pct": risk_pct,
        "recommended_hours": recommended,
        "capacity_hours": capacity_h,
        "fit_in_sprint": recommended <= capacity_h,
        "utilization_pct": round(recommended / capacity_h * 100) if capacity_h else 0,
        "complex_task_count": complex_count,
    }


# ── Bucle de aprendizaje (23-11-2026) ─────────────────────────────────────────
#
# Lo que faltaba para que el motor aprenda de verdad (docs y README, «Motor
# semántico»):
#
# - cada asignación hecha por la IA deja un `SemAssignment` PENDIENTE
#   (`was_accepted=None`), también en tickets (antes solo tareas, y nacían
#   aceptadas);
# - se CONFIRMA (True) si la persona sugerida lo mantiene hasta resolverlo o
#   cerrarlo, y se RECHAZA (False) si se reasigna a otra persona, aunque ya
#   valiera True (antes solo se tocaba si era None);
# - al resolver o cerrar, el texto y quien lo resolvió van a
#   `SemEmbeddingCache`: es el historial con decaimiento del nivel 3, que
#   estaba vacío porque nada lo alimentaba;
# - «Corregir asignación» guarda la persona correcta en la caché de experto
#   (`SemFeedback`, niveles 1 y 2) y rechaza la asignación.

TIPOS_DE_ITEM = ("ticket", "task")


def _item_de_la_empresa(db: Session, item_type: str, item_id: str):
    """El ticket o la tarea si existen en la empresa de la sesión; si no, None.

    El filtro de empresa de la sesión (`app/db/session.py`) acota la consulta.
    """
    if not item_id:
        return None
    if item_type == "ticket":
        return db.query(Ticket).filter(Ticket.id == item_id).first()
    if item_type == "task":
        return db.query(Task).filter(Task.id == item_id).first()
    return None


def ultima_asignacion(db: Session, item_type: str, item_id: str):
    """El último `SemAssignment` del ítem (o None)."""
    return (db.query(SemAssignment)
            .filter(SemAssignment.item_id == item_id, SemAssignment.item_type == item_type)
            .order_by(SemAssignment.created_at.desc())
            .first())


def registrar_sugerencia_automatica(db: Session, *, item_type: str, item_id: str, item_title: str,
                                    sugerencia: dict, created_by=None):
    """La IA asignó sola al dar de alta: queda pendiente (`None`). No confirma."""
    sugerido = sugerencia.get("suggested_user_id")
    if not sugerido or not item_id:
        return None
    sa = SemAssignment(
        item_type=item_type, item_id=item_id, item_title=(item_title or "")[:500],
        suggested_user_id=sugerido, accepted_user_id=sugerido, was_accepted=None,
        confidence=sugerencia.get("confidence"),
        top_scores=json.dumps(sugerencia.get("top_scores") or {}),
        engine_mode=sugerencia.get("engine_mode"),
        reasoning=(sugerencia.get("reasoning") or "")[:1000],
        needs_review=bool(sugerencia.get("needs_review", False)),
        created_by=created_by,
    )
    db.add(sa)
    return sa


def resolver_por_reasignacion(db: Session, item_type: str, item_id: str, nuevo_user_id) -> "bool | None":
    """Reasignado a otra persona: la sugerencia se rechaza (también si ya valía True).

    Volver a la persona sugerida no la rechaza (ni la confirma: se decide al cerrar).
    Devuelve el nuevo `was_accepted`, o None si no había asignación de la IA. No confirma.
    """
    sa = ultima_asignacion(db, item_type, item_id)
    if sa is None:
        return None
    if nuevo_user_id and sa.suggested_user_id and str(nuevo_user_id) == str(sa.suggested_user_id):
        sa.accepted_user_id = nuevo_user_id
        return sa.was_accepted
    sa.was_accepted = False
    sa.accepted_user_id = nuevo_user_id or None
    return False


def cerrar_item(db: Session, item_type: str, item_id: str, *, texto: str, user_id, calidad=None) -> dict:
    """Al resolver o cerrar: historial del nivel 3 y veredicto de la sugerencia. No confirma.

    - `SemEmbeddingCache`: el texto y quien lo resolvió (`user_id`).
    - `SemAssignment` pendiente: True si lo cerró la persona sugerida, False si otra.
    """
    salida = {"historial": False, "veredicto": None}
    if user_id and (texto or "").strip():
        salida["historial"] = cache_item_embedding(db, item_id, item_type, texto, user_id,
                                                   commit=False, calidad=calidad) is not None
    sa = ultima_asignacion(db, item_type, item_id)
    if sa is not None and sa.was_accepted is None and user_id:
        sa.was_accepted = str(user_id) == str(sa.suggested_user_id or "")
        sa.accepted_user_id = user_id
        salida["veredicto"] = sa.was_accepted
    return salida


def texto_del_item(item) -> str:
    """Título y descripción, como los ve el clasificador."""
    return f"{getattr(item, 'title', '') or ''}. {getattr(item, 'description', '') or ''}".strip(". ").strip()


def corregir_asignacion(db: Session, usuario, data: dict) -> dict:
    """«Corregir asignación»: la persona correcta para un ticket o una tarea.

    - La persona tiene que ser de la empresa (`ids_de_usuarios_del_ambito`).
    - El ítem tiene que ser de la empresa; su texto sale del ítem, no del cliente,
      salvo que no se dé `item_id` (corrección suelta desde la pantalla del motor).
    - `SemFeedback`: `corrected_by` = quien corrige; `correction_kind` =
      `confirmacion_responsable` si confirma una propuesta del modelo de lenguaje,
      `correccion` en otro caso.
    - El `SemAssignment` del ítem pasa a rechazado si la persona correcta no es
      la sugerida (o a aceptado si es una confirmación de la misma persona).
    - Auditado. Confirma.
    """
    from app.core.codigos_de_error import error
    from app.services.audit import audit_log

    item_type = str(data.get("item_type") or "ticket")
    item_id = str(data.get("item_id") or "")
    correcto = str(data.get("correct_user_id") or "")
    confirmado = bool(data.get("confirmed", False))
    modo_original = str(data.get("original_engine_mode") or "")
    if item_type not in TIPOS_DE_ITEM:
        raise error(400, "campo_no_valido_opciones", detail="item_type", campo="item_type",
                    opciones=", ".join(TIPOS_DE_ITEM))
    if not correcto:
        raise error(400, "campo_obligatorio", detail="correct_user_id requerido", campo="correct_user_id")
    ambito = ids_de_usuarios_del_ambito(db, usuario)
    if ambito is not None and correcto not in ambito:
        raise error(404, "no_encontrado", detail="Usuario no encontrado", que="usuario")
    texto = (data.get("item_text") or "").strip()
    item = None
    if item_id:
        item = _item_de_la_empresa(db, item_type, item_id)
        if item is None:
            raise error(404, "no_encontrado", detail="Elemento no encontrado", que=item_type)
        texto = texto_del_item(item) or texto
    if not texto:
        raise error(400, "campos_obligatorios", detail="item_text y correct_user_id requeridos",
                    campos="item_text, correct_user_id")

    sa = ultima_asignacion(db, item_type, item_id) if item_id else None
    sugerido = getattr(sa, "suggested_user_id", None)
    es_confirmacion = confirmado and (sugerido is None or str(sugerido) == correcto)
    tipo = "confirmacion_responsable" if (es_confirmacion and modo_original == "llm") else "correccion"
    antes = {"suggested_user_id": sugerido, "was_accepted": getattr(sa, "was_accepted", None)}

    get_assigner(db).record_feedback(item_id, item_type, texto, correcto, usuario.id,
                                     correction_kind=tipo, commit=False)
    cache_item_embedding(db, item_id, item_type, texto, correcto, commit=False)
    if sa is not None:
        sa.was_accepted = bool(es_confirmacion and sugerido and str(sugerido) == correcto)
        sa.accepted_user_id = correcto
    audit_log(db, usuario, "UPDATE", "sem_assignment", item_id or None,
              resource_name=(getattr(item, "title", None) or texto)[:200],
              old_values=antes,
              new_values={"correct_user_id": correcto, "correction_kind": tipo,
                          "was_accepted": getattr(sa, "was_accepted", None)},
              metadata={"item_type": item_type, "motivo": "corregir_asignacion_ia"})
    db.commit()
    return {"ok": True, "persisted_as_expert": tipo == "confirmacion_responsable",
            "correction_kind": tipo, "was_accepted": getattr(sa, "was_accepted", None)}


# ── Cola de casos dudosos (ActiveLearningPrioritizer) ─────────────────────────
#
# 23-11-2026: `POST /semantic/prioritize` puntuaba una lista que nadie le
# mandaba. Se usa donde aporta: las sugerencias PENDIENTES de la empresa
# (todavía sin veredicto), ordenadas por lo que más enseña al motor que un
# experto las etiquete (incertidumbre, novedad, urgencia y carga). La pantalla
# del motor las lista y el experto confirma o corrige (`corregir_asignacion`).

def cola_de_revision(db: Session, limite: int = 50) -> list:
    pendientes = (db.query(SemAssignment)
                  .filter(SemAssignment.was_accepted.is_(None))
                  .order_by(SemAssignment.created_at.desc())
                  .limit(max(1, min(int(limite or 50), 200)) * 3)
                  .all())
    items = []
    for sa in pendientes:
        tipo = getattr(sa.item_type, "value", sa.item_type)
        item = _item_de_la_empresa(db, tipo, sa.item_id)
        if item is None:
            continue
        prioridad = getattr(item, "priority", None)
        items.append({
            "assignment_id": sa.id, "item_type": tipo, "item_id": sa.item_id,
            "item_title": sa.item_title or getattr(item, "title", ""),
            "suggested_user_id": sa.suggested_user_id, "confidence": sa.confidence or 0.0,
            "engine_mode": sa.engine_mode, "needs_review": bool(sa.needs_review),
            "priority": str(getattr(prioridad, "value", prioridad) or "medium"),
            "assigned_to": sa.suggested_user_id if sa.was_accepted else None,
            "created_at": sa.created_at.isoformat() if sa.created_at else None,
        })
    ordenados = get_assigner(db).prioritize_queue(items)
    nombres = {u.id: u.full_name for u in db.query(User).filter(
        User.id.in_([i["suggested_user_id"] for i in ordenados if i.get("suggested_user_id")] or ["__none__"]))}
    for i in ordenados:
        i["suggested_user_name"] = nombres.get(i.get("suggested_user_id"))
    return ordenados[: max(1, min(int(limite or 50), 200))]


# ── Reentrenamiento periódico ─────────────────────────────────────────────────

def toca_reentrenar(intervalo_horas: int, ahora=None) -> bool:
    """Sin estado: la tarea corre cada hora y reentrena cuando la hora UTC es múltiplo del intervalo.

    0 (o menos) lo apaga. Con 24, a las 00 UTC; con 168, una vez por semana.
    """
    from app.core.timeutil import utcnow
    if not intervalo_horas or intervalo_horas <= 0:
        return False
    ahora = ahora or utcnow()
    return int(ahora.timestamp() // 3600) % int(intervalo_horas) == 0


def reentrenar_empresa(db: Session, org_id, *, forzar: bool = False) -> dict:
    """Reconstruye los perfiles de la empresa (texto desde su historial y embeddings).

    Lo llama `app.worker.semantic_reentrenar` en cada empresa con su contexto
    publicado. El intervalo es `SEMANTIC_RETRAIN_INTERVAL_HOURS` de la empresa.
    """
    from app.services import settings_service as _ss
    intervalo = _ss.get_runtime_int(db, "SEMANTIC_RETRAIN_INTERVAL_HOURS", org_id)
    if intervalo is None:
        intervalo = settings.SEMANTIC_RETRAIN_INTERVAL_HOURS
    if not forzar and not toca_reentrenar(int(intervalo or 0)):
        return {"omitido": True, "intervalo_horas": intervalo}
    generados = auto_generate_profiles(db, organization_id=org_id, is_superadmin=False)
    reconstruidos = get_assigner(db).rebuild_profiles()
    return {"omitido": False, "perfiles": generados, "reconstruidos": reconstruidos}


def precargar_en_segundo_plano() -> None:
    """Carga el modelo configurado en un hilo, sin retrasar el arranque del backend.

    Solo si el motor está configurado con transformer (en la base o en el
    entorno); con TF-IDF no hay nada que precargar. Vivía en `semantic_classifier`,
    que importaba este módulo dentro de la función y cerraba un ciclo (prueba
    global 23-11-2026).
    """
    import logging
    import threading
    import time
    from app.services import semantic_classifier as sc
    log = logging.getLogger(__name__)

    def _precargar():
        try:
            from app.db.session import SessionLocal, declarar_sistema
            db = declarar_sistema(SessionLocal(), "arranque: precarga del modelo semántico")
            try:
                backend, modelo = resolve_embeddings_backend_and_model(get_or_create_config(db))
            finally:
                db.close()
            entorno = (settings.SEMANTIC_EMBEDDINGS_BACKEND or "tfidf").strip().lower()
            if backend != "transformer" and entorno != "transformer":
                return
            t0 = time.monotonic()
            sc._get_model(modelo, "transformer")
            log.info("Modelo semántico %s precargado en %.0f s", modelo, time.monotonic() - t0)
        except Exception as exc:  # noqa: BLE001 - la precarga es accesoria: el primer uso lo cargará
            log.warning("Precarga del modelo semántico no hecha: %s", exc)
    threading.Thread(target=_precargar, name="precarga-modelo-semantico", daemon=True).start()
