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
    except Exception as exc:
        # No solo ImportError: sin red y sin el modelo en cache, SentenceTransformer
        # lanza OSError/HTTPError al ir a huggingface.co. Se cae a TF-IDF.
        if not isinstance(exc, ImportError):
            logging.getLogger(__name__).warning("Modelo %s no disponible (%s); uso TF-IDF", model_name, exc)
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
                logger.debug("_resolve_embeddings_runtime: excepcion ignorada", exc_info=True)
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
            logger.debug("__init__: excepcion ignorada", exc_info=True)
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

    # ── Sugerencia de asignatario: cuatro niveles ────────────────────────────
    #
    # Auditoria 2026-08 (hallazgo 18). `_suggest` era complejidad 17: los cuatro
    # niveles del pipeline —cache exacta, cache semantica, motor de puntuacion y
    # LLM— en un solo ambito de 130 lineas.
    #
    # Dos cosas que se vieron al separarlos:
    #
    #   · la tabla de umbrales por prioridad se CONSTRUIA EN CADA LLAMADA, con
    #     sus ocho entradas y cuatro lecturas de ajustes de ejecucion. Ahora las
    #     lecturas siguen siendo por llamada —los umbrales son configurables en
    #     caliente— pero la forma de la tabla es una constante;
    #   · la formula de carga por items estaba escrita TRES VECES: en la mezcla
    #     ponderada, en la rama sin datos de disponibilidad y en el `except`.

    # Peso de la carga horaria frente a la carga por items en la mezcla. La hora
    # pesa mas porque mide tiempo real disponible; el recuento de items solo dice
    # cuantas cosas tiene abiertas, que no es lo mismo.
    _PESO_CARGA_HORARIA = 0.6
    _PESO_CARGA_POR_ITEMS = 0.4

    # Cuantos candidatos se devuelven en `top_scores` para que la interfaz
    # pueda ofrecer alternativas.
    _CANDIDATOS_MOSTRADOS = 5

    # Las prioridades que NO permiten asignacion automatica, y de que umbral
    # tiran. Un P1 se revisa siempre: el coste de un critico mal asignado es
    # mayor que el de una revision.
    _UMBRAL_POR_PRIORIDAD = {
        "critical":    ("critical", False),
        "p1_critical": ("critical", False),
        "high":        ("high", True),
        "p2_high":     ("high", True),
        "medium":      ("medium", True),
        "p3_medium":   ("medium", True),
        "low":         ("low", True),
        "p4_low":      ("low", True),
    }

    def _modo(self) -> str:
        """El modo del motor, normalizado.

        El `split` sobre el punto es porque el valor puede llegar como el nombre
        completo de un Enum (`EngineMode.hybrid`) y no como su valor.
        """
        modo = str(getattr(self.config, "engine_mode", "hybrid") or "hybrid").lower()
        return modo.split(".", 1)[1] if "." in modo else modo

    def _nivel_1_cache_exacta(self, text: str, item_type: str):
        """Coincidencia exacta por hash: alguien ya corrigio ESTE texto."""
        exact = self.db.query(SemFeedback).filter(
            SemFeedback.text_hash == _text_hash(text),
            SemFeedback.item_type == item_type,
        ).first()
        if exact and exact.correct_user_id:
            return self._result(exact.correct_user_id, 1.0, "expert_cache_exact",
                                {}, False, "Expert cache (coincidencia exacta)")
        return None

    def _nivel_2_cache_semantica(self, text: str, item_type: str):
        """Coincidencia por parecido con algo que ya se corrigio."""
        from app.services.settings_service import get_runtime_float as _rt_f

        umbral = (self.config.threshold_expert_cache
                  or _rt_f(self.db, "SEM_THRESHOLD_EXPERT_CACHE"))
        hit = self._semantic_lookup_feedback(text, item_type, umbral)
        if hit:
            return self._result(
                hit["user_id"], hit["score"], "expert_cache_semantic", {}, False,
                f"Expert cache semantico (sim={hit['score']:.2f})",
            )
        return None

    def _perfiles_candidatos(self, candidate_user_ids: list | None) -> list:
        q = self.db.query(SemProfile).filter(SemProfile.is_available == True)  # noqa: E712
        if candidate_user_ids:
            q = q.filter(SemProfile.user_id.in_(candidate_user_ids))
        return q.all()

    def _umbral_y_revision(self, item_type: str, priority: str) -> tuple[float, bool]:
        """El umbral efectivo y si hay que revisar de todas formas.

        El umbral global del tipo de item SIEMPRE se aplica; el de la prioridad
        solo puede hacerlo mas estricto, nunca mas laxo. Con `max()` de los dos
        no hay forma de que configurar una prioridad relaje el umbral general.
        """
        from app.services.settings_service import get_runtime_float as _rt_f

        base = (self.config.threshold_ticket if item_type == "ticket"
                else self.config.threshold_task)

        clave, automatico = self._UMBRAL_POR_PRIORIDAD.get(
            str(priority).lower(), (None, True)
        )
        if clave is None:
            minimo = base
        else:
            minimo = (getattr(self.config, f"threshold_{clave}", None)
                      or _rt_f(self.db, f"SEM_THRESHOLD_{clave.upper()}"))

        return max(float(base or 0.0), float(minimo or 0.0)), not automatico

    @staticmethod
    def _carga_por_items(p) -> float:
        """Cuanto de su capacidad de items tiene ocupada, entre 0 y 1.

        Estaba escrita tres veces en el original.
        """
        return min(1.0, (p.open_tickets + p.open_tasks) / max(p.max_load, 1))

    def _carga_del_perfil(self, p, current_week: str) -> float:
        """La carga de la persona, mezclando horas disponibles y items abiertos.

        Si no se puede saber la disponibilidad horaria —o falla el servicio— se
        cae a la carga por items, que siempre esta en el perfil. Degradar es
        preferible a no sugerir: una sugerencia peor sigue siendo util.
        """
        try:
            avail = ResourceAnalyticsService.get_user_availability(
                self.db, p.user_id, current_week
            )
        except Exception:
            logger.debug(
                "ResourceAnalyticsService.get_user_availability failed for user=%s; "
                "falling back to item-load ratio", p.user_id, exc_info=True,
            )
            return self._carga_por_items(p)

        if not avail:
            return self._carga_por_items(p)

        carga_horaria = 1.0 - (avail["available_hours"] / max(avail["capacity_hours"], 1))
        return min(1.0, self._PESO_CARGA_HORARIA * carga_horaria
                   + self._PESO_CARGA_POR_ITEMS * self._carga_por_items(p))

    def _puntuar_perfiles(self, profiles: list, item_emb, item_type: str,
                          modo: str, current_week: str) -> dict:
        """La puntuacion final de cada candidato.

        En `rules_only` la parte semantica vale cero y solo pesa la carga; en los
        demas modos se mezcla el parecido con el perfil y su historial. La
        penalizacion por concentracion evita que a la misma persona le caiga todo
        de un tipo.
        """
        scores = {}
        for p in profiles:
            if modo == "rules_only":
                score = 0.0
            else:
                if not p.embedding:
                    # Un perfil sin embedding no se puede puntuar: se descarta en
                    # vez de darle cero, que lo pondria al final del ranking como
                    # si fuera un mal candidato en vez de un candidato sin datos.
                    continue
                score = self._hybrid_score(
                    item_emb, self._vector_comparable(p.embedding, p.profile_text, len(item_emb)),
                    self._get_history_embeddings(p.user_id, item_type, len(item_emb)),
                )

            carga = self._carga_del_perfil(p, current_week)
            bruto = (score * (1 - self.load_weight)
                     + (1 - carga) * self.load_weight)
            scores[p.user_id] = max(
                0.0, round(bruto - self._diversity_penalty(p, item_type), 4)
            )
        return scores

    def _suggest(self, text: str, item_type: str,
                 candidate_user_ids: list = None,
                 priority: str = "medium") -> dict:
        """Pipeline de 4 niveles (igual que Ficosa)."""
        modo = self._modo()

        # Nivel 1 — Expert Cache exacto (hash SHA-256)
        resultado = self._nivel_1_cache_exacta(text, item_type)
        if resultado:
            return resultado

        # Nivel 2 — Expert Cache semantico (coseno >= threshold)
        resultado = self._nivel_2_cache_semantica(text, item_type)
        if resultado:
            return resultado

        profiles = self._perfiles_candidatos(candidate_user_ids)
        if not profiles:
            return self._result(None, 0.0, "no_profiles", {}, True,
                                "Sin perfiles configurados")

        threshold, force_review = self._umbral_y_revision(item_type, priority)

        # "Solo LLM" bypasses semantic scoring and delegates directly.
        if modo == "llm":
            llm_result = self._llm_suggest(text, profiles, item_type)
            if llm_result:
                llm_result["engine_mode"] = "llm"
                return llm_result
            return self._result(None, 0.0, "llm", {}, True, "LLM no disponible")

        # Nivel 3 — Motor semantico (o solo reglas, segun el modo)
        current_week = ResourceAnalyticsService.get_week_iso(timeutil.today())
        item_emb = self._encode_single(text)
        scores = self._puntuar_perfiles(
            profiles, item_emb, item_type, modo, current_week
        )
        if not scores:
            return self._result(None, 0.0, "no_embeddings", {}, True,
                                "Perfiles sin embeddings. Ejecuta 'Reconstruir perfiles'.")

        best_uid = max(scores, key=scores.get)
        best_score = scores[best_uid]
        needs_review = force_review or (best_score < threshold)
        top_scores = dict(
            sorted(scores.items(), key=lambda x: -x[1])[:self._CANDIDATOS_MOSTRADOS]
        )

        etiqueta = "Reglas/carga" if modo == "rules_only" else "Semantico"
        reasoning = f"{etiqueta} (score={best_score:.2f}, umbral={threshold})"

        # Nivel 4 — LLM si el score es bajo y el modo es hibrido. No se consulta
        # cuando la prioridad ya obliga a revision humana: el LLM no puede
        # levantar esa obligacion, asi que gastar la llamada no aporta nada.
        if needs_review and not force_review and modo == "hybrid":
            llm_result = self._llm_suggest(text, profiles, item_type)
            if llm_result:
                return {**llm_result, "top_scores": top_scores,
                        "sem_score": best_score}

        return self._result(best_uid, best_score, modo,
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
                fb_emb = self._vector_comparable(fb.embedding, fb.text_snippet, len(item_emb))
                sim    = _cosine(item_emb, fb_emb)
                if sim >= threshold:
                    if best is None or sim > best["score"]:
                        best = {"user_id": fb.correct_user_id, "score": sim}
            except Exception as e:
                logger.debug(f"Similarity calculation failed for item: {str(e)[:50]}")
                continue
        return best

    def _vector_comparable(self, guardado, texto, dimension: int) -> list:
        """El vector guardado, o el de su texto si no es comparable con el actual.

        Revisión 2026-11. Con TF-IDF el vocabulario se fija al crear cada
        asignador (perfiles + caché, que crecen), pero los vectores de perfiles,
        historial y correcciones se guardaron con un vocabulario anterior: de
        otra longitud, el coseno da 0 y el ranking quedaba en manos de la carga.
        """
        try:
            vector = json.loads(guardado) if isinstance(guardado, str) else (guardado or [])
        except (TypeError, ValueError):
            vector = []
        if len(vector) != dimension and texto:
            return self._encode_single(texto)
        return vector

    def _get_history_embeddings(self, user_id: str, item_type: str, dimension: Optional[int] = None) -> list:
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
                vector = (self._vector_comparable(r.embedding, r.text_snippet, dimension)
                          if dimension is not None else json.loads(r.embedding))
                result.append((vector, r.created_at))
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
            # Revisión 2026-11: sin usuario se llamaba sin empresa (proveedor,
            # tope de gasto y registro de otra o de ninguna); ahora, la de la sesión.
            kwargs = {"is_superadmin": False, "organization_id": self.db.info.get("organization_id")}
            if cu is not None:
                kwargs["is_superadmin"] = bool(getattr(cu, "is_superadmin", False))
                kwargs["organization_id"] = getattr(cu, "organization_id", None)
                kwargs["user_id"] = getattr(cu, "id", None)
            from app.services.ai_provider_service import es_aviso_de_ia
            resp = call_ai(self.db, messages, system=system,
                           module="semantic_assign", max_tokens=200, **kwargs)
            if es_aviso_de_ia(resp):
                return None
            import re
            m = re.search(r'\{[^}]+\}', resp)
            if m:
                try:
                    data = json.loads(m.group(0))
                except json.JSONDecodeError as parse_err:
                    logger.error(f"Invalid JSON from LLM response: {parse_err}")
                    return None
                uid  = str(data.get("user_id") or "")
                reason = data.get("reason", "LLM suggestion")
                # Revisión 2026-11. Sólo vale un candidato: el modelo puede
                # devolver cualquier identificador. Y ya no se guarda como
                # corrección de experto: `record_feedback` sobrescribía la de un
                # experto para el mismo texto y la respuesta del modelo pasaba a
                # contestar en el nivel 1 como si fuera de una persona.
                candidatos = {str(p.user_id) for p in profiles}
                if uid not in candidatos:
                    logger.warning("El LLM devolvió un usuario que no es candidato: %s", uid[:40])
                    return None
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
