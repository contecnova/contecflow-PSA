"""El pipeline de sugerencia de asignatario, nivel por nivel.

Auditoría 2026-08 (P3-18). `_suggest` era complejidad 17: los cuatro niveles
—caché exacta, caché semántica, motor de puntuación y LLM— en un solo ámbito de
130 líneas. Al separarlos aparecieron dos cosas que estos tests fijan.

## 1. Un umbral de prioridad NO puede relajar el umbral del tipo de ítem

`threshold_low` vale 0.45 y `threshold_ticket` 0.55. Se podría leer que un
ticket de prioridad baja se auto-asigna con 0.45 — no: se aplica `max()` de los
dos, así que sigue exigiendo 0.55. El umbral de prioridad sólo puede endurecer.
Es la diferencia entre "los tickets sin importancia se asignan solos con
cualquier parecido" y lo que hace de verdad.

## 2. Un perfil sin embedding se DESCARTA, no puntúa cero

Puntuarlo a cero lo dejaría al final del ranking como si fuera un mal candidato,
cuando lo que pasa es que no hay datos para juzgarlo. Y si NINGÚN perfil tiene
embedding la respuesta es `no_embeddings` con su instrucción de reconstruir los
perfiles, no una sugerencia mala con cara de buena.

Los valores esperados de carga están calculados **a mano** en cada test, no
capturados del código: si se capturan, el test confirma lo que el código hace en
vez de lo que debería hacer.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.test_semantic_classifier import _make_assigner, _make_config


def _perfil(*, user_id=1, open_tickets=0, open_tasks=0, max_load=10, embedding=None):
    p = MagicMock()
    p.user_id = user_id
    p.open_tickets = open_tickets
    p.open_tasks = open_tasks
    p.max_load = max_load
    p.embedding = embedding
    return p


# ── El modo del motor ────────────────────────────────────────────────────────

@pytest.mark.parametrize("crudo,esperado", [
    ("hybrid", "hybrid"),
    ("HYBRID", "hybrid"),
    ("EngineMode.hybrid", "hybrid"),      # el nombre del Enum, no su valor
    ("EngineMode.RULES_ONLY", "rules_only"),
    ("llm", "llm"),
])
def test_el_modo_se_normaliza(crudo, esperado):
    a = _make_assigner(config=_make_config(engine_mode=crudo))
    assert a._modo() == esperado


@pytest.mark.parametrize("crudo", [None, "", 0])
def test_sin_modo_configurado_se_asume_hibrido(crudo):
    """Híbrido es el modo completo: si la configuración llega vacía, no se
    degrada silenciosamente a sólo-reglas."""
    a = _make_assigner(config=_make_config(engine_mode=crudo))
    assert a._modo() == "hybrid"


# ── El umbral efectivo y la revisión obligatoria ─────────────────────────────

@pytest.mark.parametrize("prioridad", ["critical", "p1_critical", "CRITICAL"])
def test_un_critico_se_revisa_siempre(prioridad):
    """El coste de un crítico mal asignado es mayor que el de una revisión."""
    a = _make_assigner()
    umbral, revisar = a._umbral_y_revision("ticket", prioridad)
    assert revisar is True
    assert umbral == 0.90   # max(threshold_ticket 0.55, threshold_critical 0.90)


@pytest.mark.parametrize("prioridad,esperado", [
    ("high", 0.72),        # max(0.55, 0.72)
    ("p2_high", 0.72),
    ("medium", 0.58),      # max(0.55, 0.58)
    ("p3_medium", 0.58),
])
def test_el_umbral_de_prioridad_endurece(prioridad, esperado):
    a = _make_assigner()
    umbral, revisar = a._umbral_y_revision("ticket", prioridad)
    assert umbral == esperado
    assert revisar is False


@pytest.mark.parametrize("prioridad", ["low", "p4_low"])
def test_EL_HALLAZGO_una_prioridad_baja_no_relaja_el_umbral(prioridad):
    """`threshold_low` es 0.45 y `threshold_ticket` 0.55.

    Se podría leer que un ticket de prioridad baja se auto-asigna con 0.45. No:
    se aplica `max()` de los dos, así que sigue exigiendo 0.55. Configurar una
    prioridad no puede abrir la puerta por debajo del umbral del tipo de ítem.
    """
    a = _make_assigner()
    umbral, _ = a._umbral_y_revision("ticket", prioridad)
    assert umbral == 0.55, "un umbral de prioridad ha relajado el del tipo de ítem"


@pytest.mark.parametrize("prioridad", ["urgentisimo", "", None, "P0"])
def test_una_prioridad_desconocida_usa_el_umbral_del_tipo(prioridad):
    """Sin caer a un umbral más laxo ni reventar: la etiqueta de prioridad puede
    venir de cualquier integración y una nueva no debe abrir la asignación."""
    a = _make_assigner()
    umbral, revisar = a._umbral_y_revision("task", prioridad)
    assert umbral == 0.60   # threshold_task
    assert revisar is False


def test_el_tipo_de_item_elige_su_propio_umbral_base():
    a = _make_assigner()
    assert a._umbral_y_revision("ticket", "low")[0] == 0.55
    assert a._umbral_y_revision("task", "low")[0] == 0.60


def test_sin_umbral_en_la_config_se_lee_de_los_ajustes_en_caliente():
    """Los umbrales son configurables sin reiniciar. Si la fila de configuración
    no lo trae, se cae al ajuste de ejecución."""
    a = _make_assigner(config=_make_config(threshold_high=None))
    with patch("app.services.settings_service.get_runtime_float",
               return_value=0.81) as rt:
        umbral, _ = a._umbral_y_revision("ticket", "high")
    assert umbral == 0.81
    assert rt.call_args[0][1] == "SEM_THRESHOLD_HIGH"


# ── La carga: por ítems, y mezclada con las horas ────────────────────────────

@pytest.mark.parametrize("tickets,tareas,tope,esperado", [
    (3, 2, 10, 0.5),     # 5/10 — calculado a mano
    (0, 0, 10, 0.0),
    (10, 0, 10, 1.0),
    (8, 7, 10, 1.0),     # 15/10 = 1.5, recortado a 1.0
    (5, 0, 0,  1.0),     # tope 0 → max(0,1)=1 → 5/1 = 5.0, recortado
])
def test_la_carga_por_items(tickets, tareas, tope, esperado):
    a = _make_assigner()
    assert a._carga_por_items(
        _perfil(open_tickets=tickets, open_tasks=tareas, max_load=tope)
    ) == esperado


def test_la_carga_mezcla_horas_al_60_e_items_al_40():
    """40 h de capacidad con 10 libres → 75 % de carga horaria.
    5 ítems sobre un tope de 10 → 50 % de carga por ítems.
    0.6 × 0.75 + 0.4 × 0.50 = 0.45 + 0.20 = **0.65**."""
    a = _make_assigner()
    p = _perfil(open_tickets=3, open_tasks=2, max_load=10)
    with patch("app.services.semantic_classifier.ResourceAnalyticsService."
               "get_user_availability",
               return_value={"available_hours": 10, "capacity_hours": 40}):
        assert a._carga_del_perfil(p, "2026-W01") == pytest.approx(0.65)


def test_una_persona_libre_de_horas_y_de_items_tiene_carga_cero():
    a = _make_assigner()
    with patch("app.services.semantic_classifier.ResourceAnalyticsService."
               "get_user_availability",
               return_value={"available_hours": 40, "capacity_hours": 40}):
        assert a._carga_del_perfil(_perfil(), "2026-W01") == pytest.approx(0.0)


def test_sin_datos_de_disponibilidad_se_usa_solo_la_carga_por_items():
    """Degradar es preferible a no sugerir: una sugerencia peor sigue siendo
    útil, y la carga por ítems está siempre en el perfil."""
    a = _make_assigner()
    p = _perfil(open_tickets=3, open_tasks=2, max_load=10)
    with patch("app.services.semantic_classifier.ResourceAnalyticsService."
               "get_user_availability", return_value=None):
        assert a._carga_del_perfil(p, "2026-W01") == 0.5


def test_si_el_servicio_de_disponibilidad_revienta_se_usa_la_carga_por_items():
    """La misma degradación, por la otra vía. Estaba escrita tres veces en el
    original: aquí y en las dos ramas de arriba."""
    a = _make_assigner()
    p = _perfil(open_tickets=3, open_tasks=2, max_load=10)
    with patch("app.services.semantic_classifier.ResourceAnalyticsService."
               "get_user_availability", side_effect=RuntimeError("caido")):
        assert a._carga_del_perfil(p, "2026-W01") == 0.5


def test_la_carga_mezclada_nunca_pasa_de_uno():
    """Sin capacidad horaria y con el triple de ítems del tope, la mezcla daría
    0.6 × 1.0 + 0.4 × 1.0 = 1.0 — el recorte lo garantiza aunque cambien los
    pesos."""
    a = _make_assigner()
    p = _perfil(open_tickets=15, open_tasks=15, max_load=10)
    with patch("app.services.semantic_classifier.ResourceAnalyticsService."
               "get_user_availability",
               return_value={"available_hours": 0, "capacity_hours": 0}):
        assert a._carga_del_perfil(p, "2026-W01") == 1.0


def test_los_pesos_de_la_mezcla_suman_uno():
    """Si no sumaran uno, la carga dejaría de ser una fracción y el término
    `(1 - carga)` de la puntuación cambiaría de escala."""
    from app.services.semantic_classifier import SemanticAssigner
    assert (SemanticAssigner._PESO_CARGA_HORARIA
            + SemanticAssigner._PESO_CARGA_POR_ITEMS) == pytest.approx(1.0)


# ── La puntuación de candidatos ──────────────────────────────────────────────

def test_EL_HALLAZGO_un_perfil_sin_embedding_se_descarta_no_puntua_cero():
    """Puntuarlo a cero lo dejaría al final del ranking como si fuera un mal
    candidato, cuando lo que pasa es que no hay datos para juzgarlo."""
    a = _make_assigner()
    perfiles = [_perfil(user_id=1, embedding=None),
                _perfil(user_id=2, embedding="[0.1, 0.2]")]
    with patch.object(a, "_hybrid_score", return_value=0.8), \
         patch.object(a, "_diversity_penalty", return_value=0.0), \
         patch.object(a, "_carga_del_perfil", return_value=0.0):
        scores = a._puntuar_perfiles(perfiles, [0.1, 0.2], "ticket",
                                     "hybrid", "2026-W01")
    assert 1 not in scores, "un perfil sin embedding ha entrado en el ranking"
    assert set(scores) == {2}


def test_en_solo_reglas_puntuan_los_perfiles_sin_embedding():
    """Sólo-reglas no usa la parte semántica, así que la falta de embedding no
    impide ordenar por carga."""
    a = _make_assigner()
    perfiles = [_perfil(user_id=1, embedding=None), _perfil(user_id=2, embedding=None)]
    with patch.object(a, "_diversity_penalty", return_value=0.0), \
         patch.object(a, "_carga_del_perfil", side_effect=[0.9, 0.1]):
        scores = a._puntuar_perfiles(perfiles, None, "ticket",
                                     "rules_only", "2026-W01")
    # load_weight 0.20 → 0 × 0.8 + (1 − carga) × 0.2
    assert scores == {1: pytest.approx(0.02), 2: pytest.approx(0.18)}
    assert scores[2] > scores[1], "en sólo-reglas debe ganar quien está más libre"


def test_la_puntuacion_mezcla_parecido_y_carga_con_el_peso_configurado():
    """Parecido 0.80, carga 0.50, peso de carga 0.20:
    0.80 × 0.80 + (1 − 0.50) × 0.20 = 0.64 + 0.10 = **0.74**."""
    a = _make_assigner()
    with patch.object(a, "_hybrid_score", return_value=0.80), \
         patch.object(a, "_diversity_penalty", return_value=0.0), \
         patch.object(a, "_carga_del_perfil", return_value=0.50):
        scores = a._puntuar_perfiles(
            [_perfil(user_id=7, embedding="[1]")], [1], "ticket",
            "hybrid", "2026-W01")
    assert scores[7] == pytest.approx(0.74)


def test_la_penalizacion_por_concentracion_se_resta():
    """La misma puntuación de arriba (0.74) menos una penalización de 0.10."""
    a = _make_assigner()
    with patch.object(a, "_hybrid_score", return_value=0.80), \
         patch.object(a, "_diversity_penalty", return_value=0.10), \
         patch.object(a, "_carga_del_perfil", return_value=0.50):
        scores = a._puntuar_perfiles(
            [_perfil(user_id=7, embedding="[1]")], [1], "ticket",
            "hybrid", "2026-W01")
    assert scores[7] == pytest.approx(0.64)


def test_la_penalizacion_no_deja_puntuaciones_negativas():
    """Una negativa rompería el orden frente a un 0.0 legítimo y ensuciaría los
    umbrales, que están definidos entre 0 y 1."""
    a = _make_assigner()
    with patch.object(a, "_hybrid_score", return_value=0.10), \
         patch.object(a, "_diversity_penalty", return_value=0.95), \
         patch.object(a, "_carga_del_perfil", return_value=1.0):
        scores = a._puntuar_perfiles(
            [_perfil(user_id=7, embedding="[1]")], [1], "ticket",
            "hybrid", "2026-W01")
    assert scores[7] == 0.0


# ── Los cuatro niveles, en orden ─────────────────────────────────────────────

def test_nivel_1_una_coincidencia_exacta_gana_sin_puntuar_nada():
    """Alguien ya corrigió ESTE texto: se respeta con confianza 1.0 y sin
    revisión. Es el nivel más barato y el más fiable."""
    a = _make_assigner()
    a.db.query.return_value.filter.return_value.first.return_value = MagicMock(
        correct_user_id=42)
    with patch.object(a, "_puntuar_perfiles") as puntuar:
        r = a._suggest("cae la vpn", "ticket")
    assert r["suggested_user_id"] == 42
    assert r["confidence"] == 1.0
    assert r["engine_mode"] == "expert_cache_exact"
    assert r["needs_review"] is False
    puntuar.assert_not_called()


def test_una_correccion_sin_usuario_no_cuenta_como_coincidencia():
    """Un registro de feedback puede existir sin usuario correcto (se corrigió a
    «sin asignar»). Tomarlo como acierto asignaría a nadie con confianza 1.0."""
    a = _make_assigner()
    a.db.query.return_value.filter.return_value.first.return_value = MagicMock(
        correct_user_id=None)
    assert a._nivel_1_cache_exacta("x", "ticket") is None


def test_nivel_2_una_coincidencia_semantica_gana_sin_puntuar():
    a = _make_assigner()
    with patch.object(a, "_semantic_lookup_feedback",
                      return_value={"user_id": 9, "score": 0.95}), \
         patch.object(a, "_puntuar_perfiles") as puntuar:
        r = a._suggest("la vpn se cae", "ticket")
    assert r["suggested_user_id"] == 9
    assert r["engine_mode"] == "expert_cache_semantic"
    assert r["needs_review"] is False
    puntuar.assert_not_called()


def test_sin_perfiles_disponibles_se_dice_por_que():
    """`no_profiles` y no una sugerencia vacía: quien configura el módulo tiene
    que saber que le faltan perfiles, no pensar que el motor no acierta."""
    a = _make_assigner()
    with patch.object(a, "_nivel_2_cache_semantica", return_value=None):
        r = a._suggest("algo", "ticket")
    assert r["engine_mode"] == "no_profiles"
    assert r["needs_review"] is True
    assert r["suggested_user_id"] is None


def test_EL_HALLAZGO_sin_ningun_embedding_se_pide_reconstruir_perfiles():
    """Con perfiles pero sin embeddings la respuesta lleva la instrucción de
    reconstruirlos. Sin ella el módulo parecería roto sin decir por qué."""
    a = _make_assigner()
    with patch.object(a, "_nivel_2_cache_semantica", return_value=None), \
         patch.object(a, "_perfiles_candidatos",
                      return_value=[_perfil(user_id=1, embedding=None)]), \
         patch.object(a, "_encode_single", return_value=[0.1]):
        r = a._suggest("algo", "ticket")
    assert r["engine_mode"] == "no_embeddings"
    assert r["needs_review"] is True
    assert "Reconstruir perfiles" in r["reasoning"]


def test_nivel_3_gana_la_puntuacion_mas_alta():
    a = _make_assigner()
    with patch.object(a, "_nivel_2_cache_semantica", return_value=None), \
         patch.object(a, "_perfiles_candidatos", return_value=[_perfil()]), \
         patch.object(a, "_encode_single", return_value=[0.1]), \
         patch.object(a, "_puntuar_perfiles", return_value={1: 0.4, 2: 0.9, 3: 0.6}):
        r = a._suggest("algo", "ticket", priority="medium")
    assert r["suggested_user_id"] == 2
    assert r["confidence"] == 0.9
    assert r["needs_review"] is False   # 0.9 >= umbral medium 0.58


def test_se_devuelven_como_maximo_cinco_alternativas_y_ordenadas():
    """La interfaz ofrece alternativas; más de cinco no caben en el desplegable
    y obligarían a paginar una lista de sugerencias."""
    a = _make_assigner()
    todos = {i: round(0.9 - i / 100, 4) for i in range(1, 9)}
    with patch.object(a, "_nivel_2_cache_semantica", return_value=None), \
         patch.object(a, "_perfiles_candidatos", return_value=[_perfil()]), \
         patch.object(a, "_encode_single", return_value=[0.1]), \
         patch.object(a, "_puntuar_perfiles", return_value=todos):
        r = a._suggest("algo", "ticket")
    assert len(r["top_scores"]) == 5
    assert list(r["top_scores"]) == [1, 2, 3, 4, 5]


def test_por_debajo_del_umbral_se_marca_para_revision():
    a = _make_assigner(config=_make_config(engine_mode="semantic"))
    with patch.object(a, "_nivel_2_cache_semantica", return_value=None), \
         patch.object(a, "_perfiles_candidatos", return_value=[_perfil()]), \
         patch.object(a, "_encode_single", return_value=[0.1]), \
         patch.object(a, "_puntuar_perfiles", return_value={1: 0.30}):
        r = a._suggest("algo", "ticket", priority="medium")
    assert r["needs_review"] is True
    assert r["suggested_user_id"] == 1, "se sigue sugiriendo, sólo se pide revisar"


def test_un_critico_se_revisa_aunque_la_puntuacion_sea_altisima():
    a = _make_assigner(config=_make_config(engine_mode="semantic"))
    with patch.object(a, "_nivel_2_cache_semantica", return_value=None), \
         patch.object(a, "_perfiles_candidatos", return_value=[_perfil()]), \
         patch.object(a, "_encode_single", return_value=[0.1]), \
         patch.object(a, "_puntuar_perfiles", return_value={1: 0.99}):
        r = a._suggest("se ha caido produccion", "ticket", priority="critical")
    assert r["needs_review"] is True


def test_el_modo_solo_reglas_se_ve_en_la_explicacion():
    """Quien recibe la sugerencia tiene que poder distinguir «esto lo ha
    decidido el parecido semántico» de «esto lo ha decidido el reparto»."""
    a = _make_assigner(config=_make_config(engine_mode="rules_only"))
    with patch.object(a, "_nivel_2_cache_semantica", return_value=None), \
         patch.object(a, "_perfiles_candidatos", return_value=[_perfil()]), \
         patch.object(a, "_encode_single", return_value=[0.1]), \
         patch.object(a, "_puntuar_perfiles", return_value={1: 0.5}):
        r = a._suggest("algo", "ticket")
    assert r["engine_mode"] == "rules_only"
    assert "Reglas/carga" in r["reasoning"]


# ── Nivel 4: cuándo se consulta al LLM y cuándo no ───────────────────────────

def test_nivel_4_el_llm_entra_cuando_la_puntuacion_es_baja_en_hibrido():
    a = _make_assigner(config=_make_config(engine_mode="hybrid"))
    llm = {"suggested_user_id": 5, "confidence": 0.8, "engine_mode": "llm",
           "needs_review": False, "reasoning": "el LLM dice"}
    with patch.object(a, "_nivel_2_cache_semantica", return_value=None), \
         patch.object(a, "_perfiles_candidatos", return_value=[_perfil()]), \
         patch.object(a, "_encode_single", return_value=[0.1]), \
         patch.object(a, "_puntuar_perfiles", return_value={1: 0.20}), \
         patch.object(a, "_llm_suggest", return_value=llm):
        r = a._suggest("algo", "ticket", priority="medium")
    assert r["suggested_user_id"] == 5
    assert r["sem_score"] == 0.20, "se conserva la puntuación semántica para auditar"
    assert r["top_scores"], "las alternativas del motor no se pierden"


def test_si_el_llm_no_contesta_se_devuelve_lo_del_motor():
    """Que el LLM no esté no deja al usuario sin sugerencia."""
    a = _make_assigner(config=_make_config(engine_mode="hybrid"))
    with patch.object(a, "_nivel_2_cache_semantica", return_value=None), \
         patch.object(a, "_perfiles_candidatos", return_value=[_perfil()]), \
         patch.object(a, "_encode_single", return_value=[0.1]), \
         patch.object(a, "_puntuar_perfiles", return_value={1: 0.20}), \
         patch.object(a, "_llm_suggest", return_value=None):
        r = a._suggest("algo", "ticket", priority="medium")
    assert r["suggested_user_id"] == 1
    assert r["needs_review"] is True


def test_con_prioridad_que_obliga_a_revisar_no_se_gasta_el_llm():
    """El LLM no puede levantar la obligación de revisión que impone un crítico,
    así que la llamada —que cuesta dinero y latencia— no aportaría nada."""
    a = _make_assigner(config=_make_config(engine_mode="hybrid"))
    with patch.object(a, "_nivel_2_cache_semantica", return_value=None), \
         patch.object(a, "_perfiles_candidatos", return_value=[_perfil()]), \
         patch.object(a, "_encode_single", return_value=[0.1]), \
         patch.object(a, "_puntuar_perfiles", return_value={1: 0.20}), \
         patch.object(a, "_llm_suggest") as llm:
        a._suggest("algo", "ticket", priority="critical")
    llm.assert_not_called()


def test_en_modo_semantico_no_se_llama_al_llm_aunque_la_puntuacion_sea_baja():
    """Sólo `hybrid` escala al LLM. Quien configura `semantic` está pidiendo
    explícitamente que no se llame a un proveedor externo."""
    a = _make_assigner(config=_make_config(engine_mode="semantic"))
    with patch.object(a, "_nivel_2_cache_semantica", return_value=None), \
         patch.object(a, "_perfiles_candidatos", return_value=[_perfil()]), \
         patch.object(a, "_encode_single", return_value=[0.1]), \
         patch.object(a, "_puntuar_perfiles", return_value={1: 0.05}), \
         patch.object(a, "_llm_suggest") as llm:
        r = a._suggest("algo", "ticket")
    llm.assert_not_called()
    assert r["engine_mode"] == "semantic"


def test_el_modo_llm_no_puntua_perfiles():
    """`llm` delega directamente: calcular embeddings y cargas sería trabajo
    tirado."""
    a = _make_assigner(config=_make_config(engine_mode="llm"))
    with patch.object(a, "_nivel_2_cache_semantica", return_value=None), \
         patch.object(a, "_perfiles_candidatos", return_value=[_perfil()]), \
         patch.object(a, "_puntuar_perfiles") as puntuar, \
         patch.object(a, "_encode_single") as codificar, \
         patch.object(a, "_llm_suggest", return_value={
             "suggested_user_id": 3, "confidence": 0.7,
             "needs_review": False, "reasoning": "x"}):
        r = a._suggest("algo", "ticket")
    puntuar.assert_not_called()
    codificar.assert_not_called()
    assert r["suggested_user_id"] == 3
    assert r["engine_mode"] == "llm"


def test_en_modo_llm_sin_llm_no_hay_sugerencia_pero_si_explicacion():
    a = _make_assigner(config=_make_config(engine_mode="llm"))
    with patch.object(a, "_nivel_2_cache_semantica", return_value=None), \
         patch.object(a, "_perfiles_candidatos", return_value=[_perfil()]), \
         patch.object(a, "_llm_suggest", return_value=None):
        r = a._suggest("algo", "ticket")
    assert r["suggested_user_id"] is None
    assert r["needs_review"] is True
    assert "LLM no disponible" in r["reasoning"]


# ── Los candidatos ──────────────────────────────────────────────────────────

def test_la_lista_de_candidatos_acota_la_consulta():
    """Cuando quien llama ya sabe qué equipo puede atender el ítem, se filtra en
    SQL en vez de puntuar a toda la organización y descartar después. El filtro
    de disponibilidad va también en la consulta, no después."""
    a = _make_assigner()
    a._perfiles_candidatos([4, 5, 6])
    filtro_disponibilidad = a.db.query.return_value.filter
    assert filtro_disponibilidad.called
    assert filtro_disponibilidad.return_value.filter.called


def test_sin_lista_de_candidatos_solo_se_filtra_por_disponibilidad():
    a = _make_assigner()
    a._perfiles_candidatos(None)
    filtro_disponibilidad = a.db.query.return_value.filter
    assert filtro_disponibilidad.called
    assert not filtro_disponibilidad.return_value.filter.called
