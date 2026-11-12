"""ITSM-P06 – RCA Wizard Service

Provides guided, multi-step Root Cause Analysis workflows for Problems using
three standard ITIL-compatible templates:

  • five_whys       — 5 sequential "Why?" questions (Sakichi Toyoda method)
  • fishbone        — Ishikawa diagram: 6 cause categories (People, Process,
                      Technology, Environment, Materials, Measurement)
  • itil_standard   — 4-step ITIL process: Timeline → Contributing factors →
                      Root-cause statement → Prevention actions

Public API:
  start_wizard(db, problem, template) → dict (wizard state)
  get_wizard_state(problem) → dict | None
  submit_wizard_step(db, problem, step_num, answer) → dict (updated state)
  ai_assist_step(db, problem, step_num) → dict {"hint": str, "provider": str}
  complete_wizard(db, problem) → dict (derived RCA fields)
  classify_from_wizard(db, problem) → str (rca_type label)
"""
from __future__ import annotations

import json as _json
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from sqlalchemy.orm import Session

from app.models.service_desk import Problem, ProblemRcaTemplate
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)

# ── Template definitions ──────────────────────────────────────────────────────

_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "five_whys": [
        {
            "step": 1,
            "label": "Why #1",
            "prompt": (
                "¿Por qué ocurrió el problema? "
                "Describe el síntoma observable inicial."
            ),
        },
        {
            "step": 2,
            "label": "Why #2",
            "prompt": (
                "¿Por qué ocurrió lo que describiste en el paso anterior? "
                "Profundiza un nivel más."
            ),
        },
        {
            "step": 3,
            "label": "Why #3",
            "prompt": (
                "¿Por qué se produjo esa causa? "
                "Continúa explorando hacia atrás en la cadena causal."
            ),
        },
        {
            "step": 4,
            "label": "Why #4",
            "prompt": (
                "¿Por qué existía esa condición? "
                "Busca el factor sistémico o de proceso subyacente."
            ),
        },
        {
            "step": 5,
            "label": "Why #5 — Causa Raíz",
            "prompt": (
                "¿Por qué existía ese factor? "
                "Esta respuesta debería apuntar directamente a la causa raíz. "
                "Resume la causa raíz final aquí."
            ),
        },
    ],
    "fishbone": [
        {
            "step": 1,
            "label": "Personas",
            "prompt": (
                "¿Qué factores humanos o de equipo pudieron contribuir al problema? "
                "(falta de formación, errores humanos, comunicación deficiente, etc.)"
            ),
        },
        {
            "step": 2,
            "label": "Proceso",
            "prompt": (
                "¿Qué fallos en procesos o procedimientos contribuyeron? "
                "(procedimientos ausentes, obsoletos, no seguidos, etc.)"
            ),
        },
        {
            "step": 3,
            "label": "Tecnología",
            "prompt": (
                "¿Qué factores tecnológicos o de infraestructura influyeron? "
                "(bugs de software, fallos de hardware, configuración incorrecta, etc.)"
            ),
        },
        {
            "step": 4,
            "label": "Entorno",
            "prompt": (
                "¿Qué factores del entorno o externos afectaron? "
                "(condiciones de red, proveedores externos, cambios de carga, etc.)"
            ),
        },
        {
            "step": 5,
            "label": "Materiales / Datos",
            "prompt": (
                "¿Problemas con datos, configuraciones, dependencias o insumos del sistema? "
                "(datos corruptos, configuraciones incorrectas, librerías desactualizadas, etc.)"
            ),
        },
        {
            "step": 6,
            "label": "Métricas / Monitorización",
            "prompt": (
                "¿Existían alertas, umbrales o métricas que fallaron en detectar o prevenir el problema? "
                "(falta de alertas, umbrales mal calibrados, ausencia de observabilidad, etc.)"
            ),
        },
    ],
    "itil_standard": [
        {
            "step": 1,
            "label": "Cronología",
            "prompt": (
                "Describe la cronología del incidente: "
                "¿cuándo comenzó, qué eventos sucedieron, cuándo fue detectado y resuelto? "
                "Incluye timestamps aproximados."
            ),
        },
        {
            "step": 2,
            "label": "Factores Contribuyentes",
            "prompt": (
                "Lista todos los factores que contribuyeron al problema. "
                "Considera: cambios recientes, carga inusual, deuda técnica, "
                "dependencias externas y cualquier condición preexistente."
            ),
        },
        {
            "step": 3,
            "label": "Enunciado de Causa Raíz",
            "prompt": (
                "Formula un enunciado claro y conciso de la causa raíz. "
                "Debe responder a: ¿qué falló exactamente y por qué ocurrió? "
                "Evita síntomas — apunta al origen."
            ),
        },
        {
            "step": 4,
            "label": "Acciones de Prevención",
            "prompt": (
                "¿Qué acciones concretas evitarán la recurrencia? "
                "Incluye: cambios de configuración, mejoras de proceso, "
                "actualizaciones de monitorización y responsables."
            ),
        },
    ],
}

_VALID_TEMPLATES = set(_TEMPLATES.keys())

# Stable UUIDs of the seeded system templates (migration 045)
_SYSTEM_TEMPLATE_IDS: dict[str, str] = {
    "five_whys":     "00000001-0000-0000-0000-000000000001",
    "fishbone":      "00000001-0000-0000-0000-000000000002",
    "itil_standard": "00000001-0000-0000-0000-000000000003",
}
_SYSTEM_ID_TO_SLUG = {v: k for k, v in _SYSTEM_TEMPLATE_IDS.items()}


# ── Internal helpers ──────────────────────────────────────────────────────────


def _texto(resultado) -> str:
    """`call_ai` devuelve texto; antes se hacia `.get("content")` sobre el
    texto y la pista de IA fallaba siempre (auditoria 2026-11)."""
    if isinstance(resultado, dict):
        return resultado.get("content") or ""
    return resultado or ""

def _load_state(problem: Problem) -> dict[str, Any] | None:
    """Parse rca_wizard_state JSON; return None if empty or invalid."""
    if not problem.rca_wizard_state:
        return None
    try:
        return _json.loads(problem.rca_wizard_state)
    except Exception:
        logger.debug("_load_state: excepcion ignorada", exc_info=True)
        return None


def _save_state(problem: Problem, state: dict[str, Any]) -> None:
    """Persist wizard state to problem (caller must flush/commit)."""
    problem.rca_wizard_state = _json.dumps(state, ensure_ascii=False)
    problem.rca_template = state.get("template")


def _build_initial_state(template: str, steps_def: list[dict] | None = None) -> dict[str, Any]:
    """Build wizard state from built-in or custom steps.

    *template* is the display key stored in the state (slug or UUID).
    *steps_def* is passed explicitly for DB-backed custom templates;
    if None, falls back to the built-in _TEMPLATES dict.
    """
    if steps_def is None:
        steps_def = _TEMPLATES[template]
    return {
        "template": template,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "current_step": 1,
        "total_steps": len(steps_def),
        "completed": False,
        "steps": [
            {
                "step": s["step"],
                "label": s["label"],
                "prompt": s["prompt"],
                "answer": None,
                "ai_hint": None,
            }
            for s in steps_def
        ],
        "derived_root_cause": None,
        "derived_workaround": None,
        "derived_classification": None,
        "completed_at": None,
    }


def _derive_root_cause_from_state(state: dict[str, Any]) -> str:
    """Synthesize root_cause text from wizard answers."""
    template = state.get("template", "")
    steps = state.get("steps", [])
    answered = [s for s in steps if s.get("answer")]

    if not answered:
        return ""

    if template == "five_whys":
        # Root cause = last answered Why
        last = answered[-1]
        return last["answer"]

    if template == "fishbone":
        parts = []
        for s in answered:
            parts.append(f"[{s['label']}] {s['answer']}")
        return "Análisis Fishbone:\n" + "\n".join(parts)

    if template == "itil_standard":
        # Step 3 is the root-cause statement
        root_step = next((s for s in steps if s["step"] == 3 and s.get("answer")), None)
        if root_step:
            return root_step["answer"]
        # Fallback: step 2 contributing factors
        contrib = next((s for s in steps if s["step"] == 2 and s.get("answer")), None)
        if contrib:
            return contrib["answer"]

    # Generic: join all answers
    return "\n\n".join(f"[{s['label']}]\n{s['answer']}" for s in answered)


def _derive_workaround_from_state(state: dict[str, Any]) -> str | None:
    """For ITIL standard, step 4 contains prevention/workaround actions."""
    if state.get("template") != "itil_standard":
        return None
    steps = state.get("steps", [])
    step4 = next((s for s in steps if s["step"] == 4 and s.get("answer")), None)
    return step4["answer"] if step4 else None


# ── Public API ────────────────────────────────────────────────────────────────

def _load_db_template(db: Session, key: str) -> ProblemRcaTemplate | None:
    """Resolve *key* (slug or UUID) to a ProblemRcaTemplate row, or None."""
    # Check if key is a system slug mapped to a UUID
    uuid_key = _SYSTEM_TEMPLATE_IDS.get(key, key)
    row = (
        db.query(ProblemRcaTemplate)
        .filter(ProblemRcaTemplate.id == uuid_key, ProblemRcaTemplate.is_active.is_(True))
        .first()
    )
    return row


def start_wizard(db: Session, problem: Problem, template: str) -> dict[str, Any]:
    """Initialise or reset the RCA wizard for *problem* with *template*.

    *template* can be:
      • A built-in slug: 'five_whys', 'fishbone', 'itil_standard'
      • A UUID of a custom active ProblemRcaTemplate row in DB

    A new wizard can always be started, even if a previous one exists —
    the prior state is discarded.

    Returns the initial wizard state.
    """
    import json as _j

    # Try DB first (covers both system templates by UUID and custom ones)
    db_tpl = _load_db_template(db, template)
    if db_tpl is not None:
        try:
            steps_def = _j.loads(db_tpl.steps_json)
        except Exception:
            logger.debug("start_wizard: excepcion ignorada", exc_info=True)
            steps_def = None
        # Canonical key stored in state: slug if system template, else UUID
        canonical = _SYSTEM_ID_TO_SLUG.get(db_tpl.id, db_tpl.id)
        state = _build_initial_state(canonical, steps_def=steps_def)
        _save_state(problem, state)
        db.flush()
        return state

    # Fall back to hard-coded built-in templates (offline / DB not yet seeded)
    if template not in _VALID_TEMPLATES:
        raise ErrorDeDominio(
            status_code=400,
            detail=(
                f"Unknown template '{template}'. "
                f"Built-in options: {sorted(_VALID_TEMPLATES)}. "
                "You may also pass the UUID of a custom template."
            ),
        )
    state = _build_initial_state(template)
    _save_state(problem, state)
    db.flush()
    return state


def get_wizard_state(problem: Problem) -> dict[str, Any] | None:
    """Return the current wizard state or None if not yet started."""
    return _load_state(problem)


def submit_wizard_step(
    db: Session, problem: Problem, step_num: int, answer: str
) -> dict[str, Any]:
    """Record the analyst's answer for *step_num* and advance current_step.

    Answers can be overwritten by re-submitting the same step_num.
    Returns the updated wizard state.
    """
    state = _load_state(problem)
    if state is None:
        raise ErrorDeDominio(status_code=400, detail="RCA wizard not started for this problem")
    if state.get("completed"):
        raise ErrorDeDominio(status_code=400, detail="RCA wizard already completed")

    steps = state["steps"]
    total = state["total_steps"]

    if step_num < 1 or step_num > total:
        raise ErrorDeDominio(
            status_code=400,
            detail=f"step_num must be between 1 and {total}",
        )

    answer = (answer or "").strip()
    if not answer:
        raise ErrorDeDominio(status_code=400, detail="answer cannot be empty")

    # Record answer
    for s in steps:
        if s["step"] == step_num:
            s["answer"] = answer
            break

    # Advance current_step to the next unanswered step
    next_unanswered = next(
        (s["step"] for s in steps if s.get("answer") is None),
        None,
    )
    state["current_step"] = next_unanswered if next_unanswered else total

    _save_state(problem, state)
    db.flush()
    return state


def ai_assist_step(db: Session, problem: Problem, step_num: int) -> dict[str, str]:
    """Ask the AI for a suggestion for *step_num* given the wizard context.

    The hint is persisted in the step's ai_hint field.
    Returns {"hint": str, "provider": str}.
    """
    from app.services.ai_provider_service import call_ai

    state = _load_state(problem)
    if state is None:
        raise ErrorDeDominio(status_code=400, detail="RCA wizard not started for this problem")

    steps = state["steps"]
    total = state["total_steps"]

    if step_num < 1 or step_num > total:
        raise ErrorDeDominio(
            status_code=400, detail=f"step_num must be between 1 and {total}"
        )

    target_step = next((s for s in steps if s["step"] == step_num), None)
    if target_step is None:
        raise ErrorDeDominio(status_code=400, detail=f"Step {step_num} not found")

    # Build context from previous answers
    prev_answers = [
        f"[{s['label']}]: {s['answer']}"
        for s in steps
        if s["step"] < step_num and s.get("answer")
    ]
    prev_context = "\n".join(prev_answers) if prev_answers else "(sin respuestas previas)"

    template_name = state.get("template", "unknown")
    prompt = (
        f"Eres un gestor de problemas ITIL certificado.\n\n"
        f"Problema: {problem.title}\n"
        f"Descripción: {(problem.description or '')[:400]}\n\n"
        f"Template activo: {template_name}\n"
        f"Respuestas anteriores del wizard:\n{prev_context}\n\n"
        f"El analista está en el paso {step_num} — '{target_step['label']}':\n"
        f"{target_step['prompt']}\n\n"
        f"Proporciona una sugerencia concisa (3-5 líneas) para ayudar al analista "
        f"a responder este paso basándote en el contexto del problema. "
        f"Responde SOLO con el texto de sugerencia, sin JSON ni formato adicional."
    )

    provider_used = "unknown"
    hint = ""

    try:
        result = call_ai(
            db=db,
            messages=[{"role": "user", "content": prompt}],
            system="You are an ITIL problem manager. Provide concise, actionable RCA guidance.",
            max_tokens=300,
        )
        provider_used = result.get("provider", "unknown")
        hint = (_texto(result)).strip()
    except Exception as exc:
        logger.warning("ai_assist_step: AI call failed: %s", exc)
        hint = (
            "No se pudo obtener sugerencia de IA. "
            "Analiza el contexto del problema manualmente."
        )

    # Persist hint
    for s in steps:
        if s["step"] == step_num:
            s["ai_hint"] = hint
            break

    _save_state(problem, state)
    db.flush()
    return {"hint": hint, "provider": provider_used}


def complete_wizard(db: Session, problem: Problem) -> dict[str, Any]:
    """Finalise the wizard and write derived fields to *problem*.

    Derives:
      - problem.root_cause     ← synthesized from answers
      - problem.workaround     ← from step 4 (ITIL) or kept if already set
      - problem.rca_type       ← AI-classified from wizard answers

    Returns summary of derived fields.
    Raises 400 if any step is unanswered.
    """
    state = _load_state(problem)
    if state is None:
        raise ErrorDeDominio(status_code=400, detail="RCA wizard not started for this problem")
    if state.get("completed"):
        raise ErrorDeDominio(status_code=400, detail="RCA wizard already completed")

    steps = state["steps"]
    unanswered = [s["step"] for s in steps if not s.get("answer")]
    if unanswered:
        raise ErrorDeDominio(
            status_code=400,
            detail=f"Steps not yet answered: {unanswered}. Complete all steps before finishing.",
        )

    # Derive fields from answers
    root_cause = _derive_root_cause_from_state(state)
    workaround = _derive_workaround_from_state(state)
    rca_type = classify_from_wizard(db, problem, state)

    # Write to problem
    problem.root_cause = root_cause
    if workaround and not problem.workaround:
        problem.workaround = workaround
    problem.rca_type = rca_type

    # Mark wizard complete
    state["completed"] = True
    state["completed_at"] = datetime.now(timezone.utc).isoformat()
    state["derived_root_cause"] = root_cause
    state["derived_workaround"] = workaround
    state["derived_classification"] = rca_type
    _save_state(problem, state)

    db.flush()
    return {
        "root_cause": root_cause,
        "workaround": workaround,
        "rca_type": rca_type,
        "template": state["template"],
        "completed_at": state["completed_at"],
    }


def classify_from_wizard(
    db: Session, problem: Problem, state: dict[str, Any] | None = None
) -> str:
    """Classify problem rca_type using AI based on wizard answers + problem context.

    Returns one of: hardware|software|process|human|network|unknown
    Falls back to 'unknown' on any AI error.
    """
    from app.services.ai_provider_service import call_ai

    if state is None:
        state = _load_state(problem)

    answers_text = ""
    if state:
        answered = [s for s in state.get("steps", []) if s.get("answer")]
        answers_text = "\n".join(
            f"[{s['label']}]: {s['answer']}" for s in answered
        )

    prompt = (
        "Clasifica la causa raíz de este problema de TI en UNA de estas categorías: "
        "hardware, software, process, human, network, unknown.\n\n"
        f"Título del problema: {problem.title}\n"
        f"Descripción: {(problem.description or '')[:400]}\n"
        f"Causa raíz identificada: {problem.root_cause or '(pendiente)'}\n"
        f"Análisis del wizard:\n{answers_text or '(sin respuestas)'}\n\n"
        "Responde SOLO con una de estas palabras exactas: "
        "hardware, software, process, human, network, unknown"
    )

    valid_types = {"hardware", "software", "process", "human", "network", "unknown"}
    try:
        result = call_ai(
            db=db,
            messages=[{"role": "user", "content": prompt}],
            system="Classify the root cause. Reply with exactly one word from the allowed list.",
            max_tokens=settings.AI_SHORT_ANSWER_MAX_TOKENS,
        )
        raw = (_texto(result)).strip().lower()
        # Accept first word that matches a valid type
        for word in raw.split():
            clean = word.strip(".,;:\"'")
            if clean in valid_types:
                return clean
    except Exception as exc:
        logger.warning("classify_from_wizard: AI call failed: %s", exc)

    return "unknown"


def list_available_templates(db: Session | None = None) -> list[dict[str, Any]]:
    """Return metadata for all available RCA templates.

    When *db* is provided the DB-backed ``sd_problem_rca_templates`` table is
    queried first.  Built-in hard-coded templates are used as fallback when
    the DB is unavailable or not yet seeded.
    """
    import json as _j

    if db is not None:
        try:
            rows = (
                db.query(ProblemRcaTemplate)
                .filter(ProblemRcaTemplate.is_active.is_(True))
                .order_by(ProblemRcaTemplate.is_system.desc(), ProblemRcaTemplate.name)
                .all()
            )
            if rows:
                result = []
                for row in rows:
                    try:
                        steps = _j.loads(row.steps_json)
                    except Exception:
                        logger.debug("list_available_templates: excepcion ignorada", exc_info=True)
                        steps = []
                    # Use slug as public id for system templates for backwards compat
                    public_id = _SYSTEM_ID_TO_SLUG.get(row.id, row.id)
                    result.append({
                        "id": public_id,
                        "uuid": row.id,
                        "name": row.name,
                        "template_type": row.template_type,
                        "description": row.description,
                        "total_steps": len(steps),
                        "is_system": row.is_system,
                        "is_active": row.is_active,
                    })
                return result
        except Exception as exc:
            logger.warning("list_available_templates: DB query failed, using built-ins: %s", exc)

    # Hard-coded fallback (no DB or not yet seeded)
    return [
        {
            "id": "five_whys",
            "uuid": _SYSTEM_TEMPLATE_IDS["five_whys"],
            "name": "5 Whys (Toyota)",
            "template_type": "five_whys",
            "description": (
                "Técnica iterativa de 5 preguntas '¿Por qué?' para llegar a la causa raíz. "
                "Ideal para problemas simples con cadena causal lineal."
            ),
            "total_steps": 5,
            "is_system": True,
            "is_active": True,
        },
        {
            "id": "fishbone",
            "uuid": _SYSTEM_TEMPLATE_IDS["fishbone"],
            "name": "Diagrama de Ishikawa (Fishbone)",
            "template_type": "fishbone",
            "description": (
                "Analiza 6 categorías de causas: Personas, Proceso, Tecnología, Entorno, "
                "Materiales/Datos, Métricas. Ideal para problemas multifactoriales."
            ),
            "total_steps": 6,
            "is_system": True,
            "is_active": True,
        },
        {
            "id": "itil_standard",
            "uuid": _SYSTEM_TEMPLATE_IDS["itil_standard"],
            "name": "Análisis ITIL Estándar",
            "template_type": "itil_standard",
            "description": (
                "Proceso ITIL de 4 pasos: Cronología → Factores contribuyentes → "
                "Enunciado de causa raíz → Acciones de prevención."
            ),
            "total_steps": 4,
            "is_system": True,
            "is_active": True,
        },
    ]
