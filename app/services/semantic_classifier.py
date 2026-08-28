"""
semantic_classifier.py — Contecflow Semantic Assignment Engine
Equivalente al classifier_engine.py + expert_cache.py + active_learning.py de Ficosa,
adaptado para asignacion de tickets/tareas en lugar de clasificacion de requerimientos.

Pipeline de 4 niveles (identico a Ficosa):
  Nivel 1 — Expert Cache exacto (hash SHA-256)          ~20-40% resuelto sin modelo
  Nivel 2 — Expert Cache semantico (coseno >= 0.92)     ~20-30% adicional
  Nivel 3 — Motor semantico (perfiles de usuarios)      ~30% adicional
  Nivel 4 — LLM (si esta configurado y nivel 3 falla)   resto

Si sentence-transformers NO esta instalado:
  Usa TF-IDF + similitud coseno (puro Python, sin GPU, sin dependencias).
  Precision menor (~60-70%) pero funcional de inmediato.
"""

import hashlib
import json
import logging
import math
import re
from collections import defaultdict
from typing import Optional

from app.core.config import settings
from app.models.resources import UserSkill
from app.models.semantic_engine import SemConfig, SemEmbeddingCache, SemFeedback, SemProfile
from app.models.service_desk import Ticket
from app.models.task import Task
from app.models.user import User
from app.services.base import ServiceBase
from app.services.resource_analytics import ResourceAnalyticsService
from datetime import datetime, timezone
from app.core import timeutil

logger = logging.getLogger("semantic_classifier")

# ── Modelo singleton (equivalente a ModelRegistry de Ficosa) ─────────────────
_MODEL_INSTANCE = None
_MODEL_NAME     = None
_USE_TRANSFORMER = False

def _get_model(model_name: str = "all-MiniLM-L6-v2", backend_override: str | None = None):
    """Singleton del modelo (se carga UNA sola vez, como el ModelRegistry de Ficosa)."""
    global _MODEL_INSTANCE, _MODEL_NAME, _USE_TRANSFORMER
    if _MODEL_INSTANCE is not None and _MODEL_NAME == model_name:
        return _MODEL_INSTANCE, _USE_TRANSFORMER
    backend = (backend_override or settings.SEMANTIC_EMBEDDINGS_BACKEND or "tfidf").strip().lower()
    if backend != "transformer":
        _MODEL_INSTANCE = TFIDFEncoder()
        _MODEL_NAME = "tfidf"
        _USE_TRANSFORMER = False
        return _MODEL_INSTANCE, _USE_TRANSFORMER
    try:
        from sentence_transformers import SentenceTransformer
        _MODEL_INSTANCE = SentenceTransformer(model_name)
        _MODEL_NAME     = model_name
        _USE_TRANSFORMER = True
    except ImportError:
        _MODEL_INSTANCE = TFIDFEncoder()
        _MODEL_NAME     = "tfidf"
        _USE_TRANSFORMER = False
    return _MODEL_INSTANCE, _USE_TRANSFORMER


# ── TF-IDF fallback (sin dependencias externas) ──────────────────────────────
class TFIDFEncoder:
    """
    Encoder TF-IDF puro Python como fallback cuando sentence-transformers
    no esta instalado. Menos preciso pero funcional sin GPU/pip extra.

    Diseño:
      - ``fit_global(texts)``: fija el vocabulario una sola vez con un corpus
        representativo (perfiles de usuarios + ítems históricos). Tras esto,
        cada ``encode([texto])`` proyecta sobre ese vocabulario sin re-fit.
      - ``encode(texts)``: si nunca se hizo fit, hace fit con los textos
        recibidos (compatibilidad). Después de eso solo proyecta.

    Bug histórico corregido: la versión anterior re-fiteaba el vocabulario en
    cada llamada single. El vocabulario crecía con cada texto nuevo, así que
    embeddings calculados en momentos distintos no eran comparables — todos
    los scores cosine colapsaban a 0 y el motor semántico no diferenciaba
    candidatos. Ahora el fit es estable.
    """
    def __init__(self):
        self._corpus: list  = []
        self._vocab: dict   = {}
        self._idf: dict     = {}
        self._fitted        = False

    def _tokenize(self, text: str) -> list:
        return re.findall(r'\b\w{3,}\b', text.lower())

    def _fit(self, texts: list):
        N = max(1, len(texts))
        df = defaultdict(int)
        tokenized = [self._tokenize(t) for t in texts]
        all_words = set(w for toks in tokenized for w in toks)
        # Vocabulario ordenado para ser determinista entre sesiones
        self._vocab = {w: i for i, w in enumerate(sorted(all_words))}
        for toks in tokenized:
            for w in set(toks):
                df[w] += 1
        self._idf = {w: math.log((N + 1) / (df[w] + 1)) + 1 for w in self._vocab}
        self._fitted = True
        self._corpus = list(texts)

    def fit_global(self, texts: list) -> None:
        """Fija el vocabulario con un corpus de referencia. Llamar una sola
        vez al construir el assigner (con perfiles + items resueltos)."""
        if not texts:
            return
        self._fit(texts)

    def _vectorize(self, text: str) -> list:
        toks   = self._tokenize(text)
        if not toks or not self._vocab:
            return []
        tf     = defaultdict(int)
        for t in toks: tf[t] += 1
        vec = [0.0] * len(self._vocab)
        for w, count in tf.items():
            if w in self._vocab:
                vec[self._vocab[w]] = (count / len(toks)) * self._idf.get(w, 1)
        norm = math.sqrt(sum(x*x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def encode(self, texts: list, **_) -> list:
        """Encodea respetando el vocabulario global. Si nunca se hizo fit,
        usa los textos recibidos como corpus inicial (modo bootstrap)."""
        if not self._fitted:
            self._fit(list(texts))
        return [self._vectorize(t) for t in texts]


# ── Similitud coseno ──────────────────────────────────────────────────────────
def _cosine(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x*y for x, y in zip(a, b))  # noqa: B905
    na  = math.sqrt(sum(x*x for x in a))
    nb  = math.sqrt(sum(x*x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def _text_hash(text: str) -> str:
    normalized = " ".join(text.strip().lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


# ── Estimacion de complejidad (identico a Ficosa) ────────────────────────────
def estimate_complexity(text: str, n_skills_required: int = 0) -> str:
    """Clasifica complejidad en simple/medium/complex igual que el EffortEstimator de Ficosa."""
    n_words = len(text.split())
    score   = 0
    if n_words > 150: score += 2
    elif n_words > 60: score += 1
    if n_skills_required > 2: score += 2
    elif n_skills_required > 1: score += 1
    # Palabras que indican complejidad
    complex_kw = ["integra", "migra", "architect", "refactor", "securit",
                  "performan", "escalab", "critico", "urgent", "bloqueante"]
    if any(k in text.lower() for k in complex_kw): score += 2
    if score >= 4: return "complex"
    if score >= 2: return "medium"
    return "simple"


EFFORT_HOURS = {
    # (simple, medium, complex)
    "developer":    (2.0, 4.0,  8.0),
    "qa":           (1.0, 2.5,  5.0),
    "pm":           (0.5, 1.0,  2.0),
    "devops":       (2.0, 5.0, 10.0),
    "designer":     (1.5, 3.0,  6.0),
    "analyst":      (1.5, 3.0,  6.0),
    "support_l1":   (0.5, 1.0,  2.0),
    "support_l2":   (1.0, 2.0,  4.0),
    "default":      (2.0, 4.0,  8.0),
}
from app.core.config import settings as _cfg


def _get_multi_role_factor(db=None) -> float:
    """Resolve SEM_MULTI_ROLE_FACTOR with runtime override → env fallback."""
    if db is not None:
        try:
            from app.services.settings_service import get_runtime_float
            v = get_runtime_float(db, "SEM_MULTI_ROLE_FACTOR")
            if v is not None:
                return v
        except Exception:
            logger.debug("_get_multi_role_factor: fallo best-effort ignorado", exc_info=True)
    return _cfg.SEM_MULTI_ROLE_FACTOR


# Class-level fallback kept for legacy module-level reads (e.g. from other
# modules that imported MULTI_ROLE_FACTOR by name). Prefer the function form.
MULTI_ROLE_FACTOR = _cfg.SEM_MULTI_ROLE_FACTOR


# ── Motor de asignacion semantica ─────────────────────────────────────────────
class SemanticAssigner(ServiceBase):
    """
    Motor principal de asignacion semantica.
    Equivalente a RequirementClassifier de Ficosa pero orientado a
    asignar items (tickets/tareas) a personas en lugar de clasificar roles.

    Score final = sem_score * (1 - load_weight) + (1 - load_ratio) * load_weight

    Donde sem_score = WEIGHT_PROFILE * sim(desc_perfil) + WEIGHT_HISTORY * mean(top-K historial)

    Extends ServiceBase for a consistent service-layer interface. Tuning knobs
    (WEIGHT_PROFILE / WEIGHT_HISTORY / TOP_K_HISTORY / MULTI_ROLE_FACTOR) are
    instance attributes resolved from runtime flags (Settings → Config.
    dinámica → Semantic) with env fallback.
    """

    # Class-level defaults left for backward compatibility — overridden per
    # instance in __init__ based on the live runtime flags.
    WEIGHT_PROFILE   = _cfg.SEM_WEIGHT_PROFILE
    WEIGHT_HISTORY   = _cfg.SEM_WEIGHT_HISTORY
    TOP_K_HISTORY    = _cfg.SEM_TOP_K_HISTORY

    @staticmethod
    def _resolve_embeddings_runtime(config, db=None) -> tuple[str, str]:
        """
        Resolve backend/model with runtime priority:
        1) SemConfig.local_model_name (supports explicit "tfidf")
        2) Runtime override SEMANTIC_EMBEDDINGS_BACKEND from app_settings
        3) ENV SEMANTIC_EMBEDDINGS_BACKEND fallback
        """
        configured_model = (getattr(config, "local_model_name", "") or "").strip()
        if configured_model:
            if configured_model.lower() == "tfidf":
                return "tfidf", "all-MiniLM-L6-v2"
            return "transformer", configured_model

        backend = None
        if db is not None:
            try:
                from app.services.settings_service import get_runtime_str
                backend = get_runtime_str(db, "SEMANTIC_EMBEDDINGS_BACKEND")
            except Exception:
                backend = None
        backend = (backend or settings.SEMANTIC_EMBEDDINGS_BACKEND or "tfidf").strip().lower()
        if backend == "transformer":
            return "transformer", "all-MiniLM-L6-v2"
        return "tfidf", "all-MiniLM-L6-v2"

    def __init__(self, db, config=None, current_user=None):
        # ServiceBase stores db and current_user; we pass None for current_user
        # by default since this service is called without authentication context.
        super().__init__(db, current_user)
        # Item #59: si no hay SemConfig en DB, creamos uno y lo persistimos
        # para que el siguiente arranque NO repita el camino sin defaults
        # (antes se creaba en memoria y se perdía al final del request).
        self.config = config or db.query(SemConfig).first()
        if not self.config:
            self.config = SemConfig()
            try:
                db.add(self.config)
                db.commit()
                db.refresh(self.config)
            except Exception:
                logger.warning("Concurrent SemConfig insert race; re-reading", exc_info=True)
                db.rollback()  # otra request lo creó concurrentemente — re-leer
                self.config = db.query(SemConfig).first() or SemConfig()
        runtime_backend, runtime_model_name = self._resolve_embeddings_runtime(self.config, db=self.db)
        self.model, self.use_transformer = _get_model(
            runtime_model_name,
            backend_override=runtime_backend,
        )
        self.load_weight = self.config.load_balance_weight or 0.20
        # Tuning knobs: runtime override → class default → env.
        try:
            from app.services.settings_service import get_runtime_float, get_runtime_int
            self.WEIGHT_PROFILE     = get_runtime_float(self.db, "SEM_WEIGHT_PROFILE") or self.__class__.WEIGHT_PROFILE
            self.WEIGHT_HISTORY     = get_runtime_float(self.db, "SEM_WEIGHT_HISTORY") or self.__class__.WEIGHT_HISTORY
            self.TOP_K_HISTORY      = get_runtime_int(self.db, "SEM_TOP_K_HISTORY") or self.__class__.TOP_K_HISTORY
            self.MULTI_ROLE_FACTOR  = get_runtime_float(self.db, "SEM_MULTI_ROLE_FACTOR") or _cfg.SEM_MULTI_ROLE_FACTOR
        except Exception:
            self.WEIGHT_PROFILE    = self.__class__.WEIGHT_PROFILE
            self.WEIGHT_HISTORY    = self.__class__.WEIGHT_HISTORY
            self.TOP_K_HISTORY     = self.__class__.TOP_K_HISTORY
            self.MULTI_ROLE_FACTOR = _cfg.SEM_MULTI_ROLE_FACTOR

        # TF-IDF: fijamos el vocabulario una sola vez con un corpus
        # representativo (perfiles + cache de items resueltos). Sin esto el
        # encoder re-fiteaba en cada llamada y los embeddings de perfiles
        # quedaban en un espacio vectorial distinto al embedding del nuevo
        # ticket → todos los scores cosine colapsaban a 0.
        if not self.use_transformer and hasattr(self.model, "fit_global"):
            self._fit_tfidf_global()

    def _fit_tfidf_global(self) -> None:
        """Construye el corpus de referencia para TF-IDF a partir de
        perfiles de usuarios + snippets de items resueltos en la caché."""
        corpus = []
        try:
            profile_texts = [
                p.profile_text for p in self.db.query(SemProfile)
                .filter(SemProfile.profile_text.isnot(None)).limit(500).all()
                if p.profile_text
            ]
            corpus.extend(profile_texts)
        except Exception:
            logger.warning("Failed to load SemProfile texts for TF-IDF corpus", exc_info=True)
        try:
            cache_texts = [
                c.text_snippet for c in self.db.query(SemEmbeddingCache)
                .filter(SemEmbeddingCache.text_snippet.isnot(None)).limit(500).all()
                if c.text_snippet
            ]
            corpus.extend(cache_texts)
        except Exception:
            logger.warning("Failed to load SemEmbeddingCache snippets for TF-IDF corpus", exc_info=True)
        if corpus:
            try:
                self.model.fit_global(corpus)
            except Exception:
                # Si falla, el encode() hará bootstrap fit con los textos que
                # reciba — peor calidad pero no rompe el flujo.
                logger.warning("TF-IDF fit_global failed, falling back to lazy fit")

    # ── API publica ──────────────────────────────────────────────────────────

    def suggest_for_ticket(self, ticket_title: str, ticket_desc: str,
                           candidate_user_ids: list = None,
                           priority: str = "medium") -> dict:
        """Sugiere el mejor agente para un ticket."""
        text = f"{ticket_title}. {ticket_desc or ''}"
        return self._suggest(text, "ticket", candidate_user_ids, priority=priority)

    def suggest_for_task(self, task_title: str, task_desc: str,
                         candidate_user_ids: list = None,
                         priority: str = "medium") -> dict:
        """Sugiere el mejor miembro de equipo para una tarea."""
        text = f"{task_title}. {task_desc or ''}"
        return self._suggest(text, "task", candidate_user_ids, priority=priority)

    def estimate_effort(self, title: str, description: str,
                        role_hint: str = "default") -> dict:
        """
        Estima horas de esfuerzo para una tarea.
        Equivalente al EffortEstimator de Ficosa.
        """
        text       = f"{title}. {description or ''}"
        complexity = estimate_complexity(text)
        idx        = {"simple": 0, "medium": 1, "complex": 2}[complexity]
        key        = role_hint.lower() if role_hint else "default"
        hours_table = EFFORT_HOURS.get(key, EFFORT_HOURS["default"])
        base_hours  = hours_table[idx]
        return {
            "complexity":  complexity,
            "base_hours":  base_hours,
            "role_hint":   key,
            "confidence":  0.70 if self.use_transformer else 0.50,
        }

    def prioritize_queue(self, items: list) -> list:
        """
        Prioriza una cola de tickets/tareas por valor de aprendizaje.
        Equivalente al ActiveLearningPrioritizer de Ficosa.
        Puntuacion 0-100: incertidumbre(40) + novedad(30) + urgencia(20) + carga_baja(10)
        """
        if not items: return []
        scored = []
        for item in items:
            score = self._priority_score(item)
            scored.append({**item, "priority_score": score["total"],
                           "priority_breakdown": score["breakdown"]})
        scored.sort(key=lambda x: x["priority_score"], reverse=True)
        return scored

    def record_feedback(self, item_id: str, item_type: str,
                        item_text: str, correct_user_id: str,
                        corrected_by: str):
        """
        Guarda una correccion de experto en sem_feedback.
        Equivalente a guardar en el Expert Cache de Ficosa.
        """
        h     = _text_hash(item_text)
        emb   = self._encode_single(item_text)
        exist = self.db.query(SemFeedback).filter(
            SemFeedback.text_hash == h).first()
        if exist:
            exist.correct_user_id = correct_user_id
            exist.corrected_by    = corrected_by
            exist.times_used      += 1
        else:
            fb = SemFeedback(text_hash=h,
                             text_snippet=item_text[:300],
                             embedding=json.dumps(emb),
                             item_type=item_type,
                             correct_user_id=correct_user_id,
                             corrected_by=corrected_by)
            self.db.add(fb)
        self.db.commit()

    def rebuild_profiles(self):
        """
        Reconstruye los embeddings de todos los perfiles de usuario.
        Llamar cuando cambian los skills o historial de un usuario.

        Re-fitea el vocabulario TF-IDF antes de regenerar embeddings para
        que todos compartan el mismo espacio vectorial.
        """
        profiles = self.db.query(SemProfile).all()
        # Refit con los profile_texts actualizados
        if not self.use_transformer and hasattr(self.model, "fit_global"):
            texts = [p.profile_text for p in profiles if p.profile_text]
            if texts:
                self.model.fit_global(texts)
        for p in profiles:
            if p.profile_text:
                emb = self._encode_single(p.profile_text)
                p.embedding = json.dumps(emb)
        self.db.commit()

    def refresh_user_profile(self, user_id: str) -> bool:
        """
        Regenera el perfil semantico de un usuario concreto a partir de su
        job_title, department y el historial reciente de tareas/tickets completados.
        Se llama en background tras completar una tarea o resolver un ticket.
        Retorna True si el perfil fue actualizado, False si no habia datos suficientes.
        """

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return False

        parts = []
        if user.full_name:   parts.append(user.full_name)
        if user.job_title:   parts.append(user.job_title)
        if user.department:  parts.append(user.department)

        # Mejora 2: skills via relationship + etiquetas en español
        _LEVEL_ES = {
            "basic": "básico", "intermediate": "intermedio",
            "advanced": "avanzado", "expert": "experto",
        }
        user_skills = (
            self.db.query(UserSkill)
            .filter(UserSkill.user_id == user_id)
            .all()
        )
        for us in user_skills:
            label = _LEVEL_ES.get(us.level.value, us.level.value)
            parts.append(f"Skill {label}: {us.skill.name}")

        resolved = self.db.query(Ticket).filter(
            Ticket.assigned_to_user_id == user_id,
            Ticket.status.in_(["resolved", "closed"])
        ).order_by(Ticket.resolved_at.desc()).limit(30).all()
        for t in resolved[:15]:  # Bug 5 fix: use 15 items instead of 5
            parts.append(f"Ticket resuelto: {t.title}")

        done_tasks = self.db.query(Task).filter(
            Task.assignee_id == user_id,
            Task.status == "done"
        ).order_by(Task.updated_at.desc()).limit(30).all()
        for t in done_tasks[:15]:  # Bug 5 fix: use 15 items instead of 5
            parts.append(f"Tarea completada: {t.title}")

        profile_text = ". ".join(parts)
        if not profile_text.strip():
            return False

        profile = self.db.query(SemProfile).filter(SemProfile.user_id == user_id).first()
        if not profile:
            profile = SemProfile(user_id=user_id)
            self.db.add(profile)

        profile.profile_text = profile_text
        profile.embedding = json.dumps(self._encode_single(profile_text))
        self.db.commit()
        return True

    # ── Internos ─────────────────────────────────────────────────────────────

    def _suggest(self, text: str, item_type: str,
                 candidate_user_ids: list = None,
                 priority: str = "medium") -> dict:
        """Pipeline de 4 niveles (igual que Ficosa)."""

        mode = str(getattr(self.config, "engine_mode", "hybrid") or "hybrid").lower()
        if "." in mode:
            mode = mode.split(".", 1)[1]

        h = _text_hash(text)

        # Nivel 1 — Expert Cache exacto (hash SHA-256)
        exact = self.db.query(SemFeedback).filter(
            SemFeedback.text_hash == h,
            SemFeedback.item_type == item_type
        ).first()
        if exact and exact.correct_user_id:
            return self._result(exact.correct_user_id, 1.0, "expert_cache_exact",
                                {}, False, "Expert cache (coincidencia exacta)")

        # Nivel 2 — Expert Cache semantico (coseno >= threshold)
        from app.services.settings_service import get_runtime_float as _rt_f
        sem_thr = self.config.threshold_expert_cache or _rt_f(self.db, "SEM_THRESHOLD_EXPERT_CACHE")
        feedback_hit = self._semantic_lookup_feedback(text, item_type, sem_thr)
        if feedback_hit:
            return self._result(feedback_hit["user_id"], feedback_hit["score"],
                                "expert_cache_semantic", {},
                                False, f"Expert cache semantico (sim={feedback_hit['score']:.2f})")

        # Cargar perfiles candidatos
        q = self.db.query(SemProfile).filter(SemProfile.is_available == True)
        if candidate_user_ids:
            q = q.filter(SemProfile.user_id.in_(candidate_user_ids))
        profiles = q.all()

        if not profiles:
            return self._result(None, 0.0, "no_profiles", {}, True,
                                "Sin perfiles configurados")

        # Mejora 4: thresholds dinámicos con bandera auto/manual por prioridad
        _thr_crit = getattr(self.config, "threshold_critical", None) or _rt_f(self.db, "SEM_THRESHOLD_CRITICAL")
        _thr_high = getattr(self.config, "threshold_high", None) or _rt_f(self.db, "SEM_THRESHOLD_HIGH")
        _thr_med  = getattr(self.config, "threshold_medium", None) or _rt_f(self.db, "SEM_THRESHOLD_MEDIUM")
        _thr_low  = getattr(self.config, "threshold_low", None) or _rt_f(self.db, "SEM_THRESHOLD_LOW")
        PRIORITY_THRESHOLDS = {
            "critical":    {"auto": False, "min": _thr_crit},
            "p1_critical": {"auto": False, "min": _thr_crit},
            "high":        {"auto": True,  "min": _thr_high},
            "p2_high":     {"auto": True,  "min": _thr_high},
            "medium":      {"auto": True,  "min": _thr_med},
            "p3_medium":   {"auto": True,  "min": _thr_med},
            "low":         {"auto": True,  "min": _thr_low},
            "p4_low":      {"auto": True,  "min": _thr_low},
        }
        base_threshold = (
            self.config.threshold_ticket if item_type == "ticket" else self.config.threshold_task
        )
        pth = PRIORITY_THRESHOLDS.get(
            str(priority).lower(),
            {"auto": True, "min": base_threshold},
        )
        # Global item threshold always applies; priority thresholds can only
        # make auto-assignment stricter, never weaker.
        threshold = max(float(base_threshold or 0.0), float(pth["min"] or 0.0))
        force_review = not pth["auto"]

        # "Solo LLM" bypasses semantic scoring and delegates directly.
        if mode == "llm":
            llm_result = self._llm_suggest(text, profiles, item_type)
            if llm_result:
                llm_result["engine_mode"] = "llm"
                return llm_result
            return self._result(None, 0.0, "llm", {}, True, "LLM no disponible")

        # Bug 1 fix: real-time load from ResourceAnalyticsService
        current_week = ResourceAnalyticsService.get_week_iso(timeutil.today())

        # Nivel 3 — Motor semantico (or rules-only, see branch below)
        item_emb = self._encode_single(text)
        scores   = {}
        for p in profiles:
            if mode == "rules_only":
                score = 0.0
            else:
                if not p.embedding:
                    continue
                profile_emb = json.loads(p.embedding)
                history_tuples = self._get_history_embeddings(p.user_id, item_type)  # Bug 3: now returns (emb, ts) tuples
                score = self._hybrid_score(item_emb, profile_emb, history_tuples)
            # Mejora 1: weighted blend de carga horaria + carga por ítems
            try:
                avail = ResourceAnalyticsService.get_user_availability(
                    self.db, p.user_id, current_week
                )
                if avail:
                    hour_load = 1.0 - (avail["available_hours"] / max(avail["capacity_hours"], 1))
                    item_load = min(1.0, (p.open_tickets + p.open_tasks) / max(p.max_load, 1))
                    load_ratio = min(1.0, 0.6 * hour_load + 0.4 * item_load)
                else:
                    load_ratio = min(1.0, (p.open_tickets + p.open_tasks) / max(p.max_load, 1))
            except Exception:
                logger.debug("ResourceAnalyticsService.get_user_availability failed for user=%s; falling back to item-load ratio", p.user_id, exc_info=True)
                load_ratio = min(1.0, (p.open_tickets + p.open_tasks) / max(p.max_load, 1))

            # Mejora 6: penalización por concentración excesiva del mismo tipo
            diversity_pen = self._diversity_penalty(p, item_type)
            raw_final = score * (1 - self.load_weight) + (1 - load_ratio) * self.load_weight
            final = max(0.0, round(raw_final - diversity_pen, 4))
            scores[p.user_id] = final

        if not scores:
            return self._result(None, 0.0, "no_embeddings", {}, True,
                                "Perfiles sin embeddings. Ejecuta 'Reconstruir perfiles'.")

        best_uid   = max(scores, key=scores.get)
        best_score = scores[best_uid]

        needs_review = force_review or (best_score < threshold)
        top_scores   = dict(sorted(scores.items(), key=lambda x: -x[1])[:5])

        # Nivel 4 — LLM si score bajo y modo hybrid
        if mode == "rules_only":
            reasoning = f"Reglas/carga (score={best_score:.2f}, umbral={threshold})"
        else:
            reasoning = f"Semantico (score={best_score:.2f}, umbral={threshold})"

        if needs_review and not force_review and mode == "hybrid":
            llm_result = self._llm_suggest(text, profiles, item_type)
            if llm_result:
                return {**llm_result, "top_scores": top_scores,
                        "sem_score": best_score}

        return self._result(best_uid, best_score, mode,
                            top_scores, needs_review, reasoning)

    def _hybrid_score(self, item_emb: list, profile_emb: list,
                      history_tuples: list) -> float:
        """
        Score híbrido = WEIGHT_PROFILE * sim(perfil) + WEIGHT_HISTORY * weighted_mean(historial).

        **Historial: TODOS los embeddings cacheados, no solo top-N**. (Item #58:
        un comentario obsoleto decía "top-3 del historial"; la implementación
        siempre fue weighted mean global con decay exponencial.)

        Decay: ``weight_i = 0.5^(age_days / history_decay_days)`` (Mejora 3 —
        semivida explícita). Al llegar a ``history_decay_days`` un embedding
        vale exactamente la mitad que uno reciente.

        Si no hay historial, devuelve solo ``sim(perfil)``.
        """
        score_profile = _cosine(item_emb, profile_emb)
        if not history_tuples:
            return score_profile

        decay_days = (
            getattr(self.config, "history_decay_days", None) or 90.0
        )
        now = datetime.now(timezone.utc)
        weighted_pairs = []
        for emb, created_at in history_tuples:
            sim = _cosine(item_emb, emb)
            if created_at:
                ct = (created_at if created_at.tzinfo
                      else created_at.replace(tzinfo=timezone.utc))
                age_days = max(0, (now - ct).days)
            else:
                age_days = 0
            weight = 0.5 ** (age_days / decay_days)  # Mejora 3: semivida explícita
            weighted_pairs.append((sim, weight))

        # Weighted mean of all history embeddings (not just top-3)
        total_w = sum(w for _, w in weighted_pairs)
        if total_w < 1e-12:
            return score_profile
        score_hist = sum(s * w for s, w in weighted_pairs) / total_w
        return self.WEIGHT_PROFILE * score_profile + self.WEIGHT_HISTORY * score_hist

    def _semantic_lookup_feedback(self, text: str, item_type: str,
                                  threshold: float) -> Optional[dict]:
        """Nivel 2B: busqueda semantica en feedback de expertos."""
        feedbacks = self.db.query(SemFeedback).filter(
            SemFeedback.item_type == item_type,
            SemFeedback.embedding.isnot(None)
        ).limit(500).all()
        if not feedbacks: return None
        item_emb = self._encode_single(text)
        best = None
        for fb in feedbacks:
            try:
                fb_emb = json.loads(fb.embedding)
                sim    = _cosine(item_emb, fb_emb)
                if sim >= threshold:
                    if best is None or sim > best["score"]:
                        best = {"user_id": fb.correct_user_id, "score": sim}
            except Exception as e:
                logger.debug(f"Similarity calculation failed for item: {str(e)[:50]}")
                continue
        return best

    def _get_history_embeddings(self, user_id: str, item_type: str) -> list:
        """Recupera embeddings del historial resuelto por este usuario.
        Bug 3 fix: returns list of (embedding, created_at) tuples for temporal decay."""
        rows = self.db.query(SemEmbeddingCache).filter(
            SemEmbeddingCache.assigned_user_id == user_id,
            SemEmbeddingCache.item_type == item_type,
            SemEmbeddingCache.embedding.isnot(None)
        ).order_by(SemEmbeddingCache.created_at.desc()).limit(50).all()
        result = []
        for r in rows:
            try:
                result.append((json.loads(r.embedding), r.created_at))
            except Exception as e:
                logger.warning(f"Failed to parse embedding cache: {e}", exc_info=True)
                continue
        return result

    def _encode_single(self, text: str) -> list:
        """Genera embedding para un texto."""
        try:
            emb = self.model.encode([text], show_progress_bar=False)
            if hasattr(emb, 'tolist'):
                return emb[0].tolist()
            return emb[0] if isinstance(emb[0], list) else list(emb[0])
        except Exception:
            logger.error(f"Embedding encoding failed for text: {text[:50]}...", exc_info=True)
            return []

    def _llm_suggest(self, text: str, profiles: list,
                     item_type: str) -> Optional[dict]:
        """Nivel 4: usa el LLM configurado para desempatar."""
        try:
            from app.services.ai_provider_service import call_ai
            profile_descs = "\n".join(
                f"- user_id={p.user_id}: {p.profile_text[:200]}"
                for p in profiles if p.profile_text
            )
            system = (
                "Eres un sistema de asignacion de trabajo. "
                "Responde SOLO con el user_id del mejor candidato en formato JSON: "
                '{"user_id": "xxx", "reason": "motivo breve"}'
            )
            messages = [{
                "role": "user",
                "content": (
                    f"Asigna este {item_type} al mejor candidato:\n\n"
                    f"ITEM: {text[:500]}\n\n"
                    f"CANDIDATOS:\n{profile_descs}"
                )
            }]
            # Pasamos is_superadmin/organization_id si tenemos current_user.
            # Antes sin estos kwargs, call_ai filtraba mal cuando había
            # providers scoped por org → fallo silencioso del modo hybrid.
            cu = getattr(self, "current_user", None)
            kwargs = {}
            if cu is not None:
                kwargs["is_superadmin"] = bool(getattr(cu, "is_superadmin", False))
                kwargs["organization_id"] = getattr(cu, "organization_id", None)
                kwargs["user_id"] = getattr(cu, "id", None)
            resp = call_ai(self.db, messages, system=system,
                           module="semantic_assign", max_tokens=200, **kwargs)
            import re
            m = re.search(r'\{[^}]+\}', resp)
            if m:
                try:
                    data = json.loads(m.group(0))
                except json.JSONDecodeError as parse_err:
                    logger.error(f"Invalid JSON from LLM response: {parse_err}")
                    return None
                uid  = data.get("user_id")
                reason = data.get("reason", "LLM suggestion")
                # Bug 6 fix: cache LLM result into expert feedback so future
                # identical/similar items hit level 1/2 instead of paying LLM cost
                if uid:
                    try:
                        self.record_feedback(
                            item_id=None,
                            item_type=item_type,
                            item_text=text,
                            correct_user_id=uid,
                            corrected_by="llm_auto",
                        )
                    except Exception:
                        logger.debug("Best-effort cache of LLM suggestion as feedback failed", exc_info=True)
                return self._result(uid, 0.75, "llm", {}, False,
                                    f"LLM: {reason}")
        except Exception:
            logger.error(f"LLM suggestion failed for item_type={item_type}", exc_info=True)
        return None

    def _diversity_penalty(self, profile, item_type: str) -> float:
        """Mejora 6: penaliza concentración excesiva del mismo tipo de ítem.
        Si >60% del trabajo activo es del mismo tipo, aplica penalización
        progresiva para fomentar la diversidad de asignaciones."""
        total = (profile.open_tickets or 0) + (profile.open_tasks or 0)
        if total < 3:
            return 0.0
        same_type = profile.open_tickets if item_type == "ticket" else profile.open_tasks
        concentration = (same_type or 0) / total
        return max(0.0, concentration - 0.60) * 0.3

    def _priority_score(self, item: dict) -> dict:
        """
        Score de prioridad 0-100 para la cola.
        Identico al ActiveLearningPrioritizer de Ficosa:
          incertidumbre(40) + novedad(30) + urgencia(20) + carga_baja(10)
        """
        bd = {}
        # Incertidumbre: confianza baja = mas valioso revisar
        conf = item.get("confidence", 0.5) or 0.5
        bd["uncertainty"] = round(40 * max(0, 1.0 - conf), 1)
        # Urgencia/prioridad del item
        priority_map = {"critical": 20, "p1_critical": 20, "high": 15,
                        "p2_high": 15, "medium": 8, "p3_medium": 8, "low": 3}
        bd["urgency"] = priority_map.get(str(item.get("priority", "")), 8)
        # Novedad: si no tiene asignacion previa
        bd["novelty"] = 30 if not item.get("assigned_to") else 10
        # Carga baja: favorece items de agentes con poca carga
        bd["low_load"] = 10 if item.get("queue_size", 10) < 3 else 0
        total = round(sum(bd.values()))
        return {"total": min(100, total), "breakdown": bd}

    @staticmethod
    def _result(user_id, confidence, engine_mode, top_scores,
                needs_review, reasoning) -> dict:
        return {
            "suggested_user_id": user_id,
            "confidence":        round(confidence, 4),
            "engine_mode":       engine_mode,
            "top_scores":        top_scores,
            "needs_review":      needs_review,
            "reasoning":         reasoning,
        }
