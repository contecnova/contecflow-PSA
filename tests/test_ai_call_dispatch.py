"""El despacho de una llamada a un modelo: `call_ai`.

Auditoría 2026-08 (P3-18 + hueco de observabilidad encontrado de paso).
`call_ai` era complejidad 24 en siete fases mezcladas —gobernanza de entrada,
elección de proveedor, llamada con respaldo, registro de uso, aviso de coste y
gobernanza de salida— y **no tenía cobertura directa**: los tests que existen
sólo la sustituyen por un doble.

Eso importa porque es la función por la que pasa **todo** el tráfico de IA de la
aplicación, incluida la aplicación de políticas de gobernanza. Su propio
docstring dice que antes los guardrails sólo se aplicaban en `ai_chat.py` y el
54 % del tráfico las esquivaba: la corrección de entonces vive aquí y no estaba
verificada.

## El hueco encontrado

`_try_fallback_providers` devolvía sólo el resultado, no el proveedor que lo
había servido, y `call_ai` ponía `p = None` antes de llamarlo. Una llamada
atendida por el respaldo se registraba en `AIUsageLog` con `provider_id = None`.

Y el proveedor **sí** actualizaba sus propios contadores dentro del respaldo, así
que los agregados por proveedor y el registro de uso discrepaban justo para ese
tráfico: coste contado en el proveedor, filas del log sin poder agruparse por él.
Con un primario caído —que es cuando el respaldo actúa— eso puede ser una parte
grande del gasto sin atribuir.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.ai_providers import AIProvider, AIUsageLog
from app.services import ai_provider_service as svc


def _proveedor(db, *, nombre, estado="active", org="1", modelo="claude-opus-4-5",
               es_predeterminado=False):
    p = AIProvider(
        id=str(uuid.uuid4()),
        name=nombre,
        provider="anthropic",
        default_model=modelo,
        status=estado,
        is_active=True,
        is_default=es_predeterminado,
        organization_id=org,
        total_requests=0,
        total_tokens_in=0,
        total_tokens_out=0,
        total_cost_usd=0.0,
    )
    db.add(p)
    db.commit()
    return p


def _respuesta(texto="hola", entrada=1000, salida=2000, modelo="claude-opus-4-5"):
    return {"text": texto, "tokens_in": entrada, "tokens_out": salida, "model": modelo}


# Los tests de despacho pasan `skip_guardrails=True` para que un fallo de
# políticas no se lea como un fallo de despacho; los de gobernanza las activan
# explícitamente pasando `user_id`.


# ── Elección de proveedor ─────────────────────────────────────────────────────

def test_sin_ningun_proveedor_devuelve_un_mensaje_accionable(db):
    """Y no una excepción: la pantalla tiene que poder mostrar qué hacer."""
    texto = svc.call_ai(db, [{"role": "user", "content": "hola"}], skip_guardrails=True)
    assert "No hay ningún proveedor de IA configurado" in texto
    assert "IA & Conectores" in texto


def test_un_provider_id_explicito_se_usa(db, monkeypatch):
    p = _proveedor(db, nombre="Explícito")
    llamados = []
    monkeypatch.setattr(svc, "call_provider",
                        lambda prov, *a, **k: llamados.append(prov.name) or _respuesta())

    texto = svc.call_ai(db, [{"role": "user", "content": "x"}],
                        provider_id=p.id, skip_guardrails=True)
    assert texto == "hola"
    assert llamados == ["Explícito"]


def test_un_provider_id_de_otra_organizacion_no_se_usa(db, monkeypatch):
    """El filtro por organización cuando no es superadmin. Sin él, un
    identificador adivinado serviría para usar el proveedor —y la clave de
    API— de otro cliente."""
    ajeno = _proveedor(db, nombre="De otro cliente", org="ORG_AJENA")
    monkeypatch.setattr(svc, "call_provider",
                        lambda *a, **k: pytest.fail("no debía llamarse"))

    texto = svc.call_ai(db, [{"role": "user", "content": "x"}],
                        provider_id=ajeno.id, is_superadmin=False,
                        organization_id="1", skip_guardrails=True)
    assert "No hay ningún proveedor" in texto


# ── Contadores y coste ────────────────────────────────────────────────────────

def test_el_proveedor_suma_peticiones_tokens_y_coste(db, monkeypatch):
    """1.000 tokens de entrada a 15 $/M y 2.000 de salida a 75 $/M:
    0,015 + 0,15 = 0,165 $."""
    p = _proveedor(db, nombre="Contable")
    monkeypatch.setattr(svc, "call_provider", lambda *a, **k: _respuesta())

    svc.call_ai(db, [{"role": "user", "content": "x"}],
                provider_id=p.id, skip_guardrails=True)
    db.refresh(p)

    assert p.total_requests == 1
    assert p.total_tokens_in == 1000
    assert p.total_tokens_out == 2000
    assert p.total_cost_usd == pytest.approx(0.165)
    assert p.last_used_at is not None


def test_un_modelo_fuera_del_catalogo_no_calcula_coste(db, monkeypatch):
    """Sin precio conocido no se inventa: los tokens sí se cuentan y el coste
    queda a cero, que es honesto. Inventarlo falsearía el gasto."""
    p = _proveedor(db, nombre="Modelo raro", modelo="modelo-que-no-existe")
    monkeypatch.setattr(svc, "call_provider",
                        lambda *a, **k: _respuesta(modelo="modelo-que-no-existe"))

    svc.call_ai(db, [{"role": "user", "content": "x"}],
                provider_id=p.id, skip_guardrails=True)
    db.refresh(p)
    assert p.total_tokens_in == 1000
    assert p.total_cost_usd == 0.0


# ── Registro de uso ───────────────────────────────────────────────────────────

def test_cada_llamada_deja_una_fila_de_uso(db, monkeypatch):
    p = _proveedor(db, nombre="Registrado")
    monkeypatch.setattr(svc, "call_provider", lambda *a, **k: _respuesta())

    svc.call_ai(db, [{"role": "user", "content": "x"}], provider_id=p.id,
                module="informes", user_id="admin-test-id", skip_guardrails=True)

    log = db.query(AIUsageLog).filter(AIUsageLog.module == "informes").one()
    assert log.provider_id == p.id
    assert log.user_id == "admin-test-id"
    assert log.tokens_in == 1000
    assert log.tokens_out == 2000
    assert log.success is True
    assert log.error_msg is None
    assert log.latency_ms >= 0


def test_una_llamada_fallida_se_registra_como_fallida(db, monkeypatch):
    p = _proveedor(db, nombre="Roto")
    monkeypatch.setattr(svc, "call_provider",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429 sin cuota")))

    texto = svc.call_ai(db, [{"role": "user", "content": "x"}], provider_id=p.id,
                        module="fallo", skip_guardrails=True)

    assert texto.startswith("⚠️ AI provider error")
    assert "429 sin cuota" in texto

    log = db.query(AIUsageLog).filter(AIUsageLog.module == "fallo").one()
    assert log.success is False
    assert "429" in log.error_msg


def test_el_proveedor_que_falla_queda_marcado_en_error(db, monkeypatch):
    """Para que el respaldo no vuelva a elegirlo: `_try_fallback_providers`
    excluye los que están en estado de error."""
    p = _proveedor(db, nombre="Se cae")
    monkeypatch.setattr(svc, "call_provider",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("caído")))

    svc.call_ai(db, [{"role": "user", "content": "x"}], provider_id=p.id,
                skip_guardrails=True)
    db.refresh(p)
    assert p.status == "error"
    assert "caído" in p.last_error
    assert p.last_error_at is not None


# ── El respaldo, y el hueco que se cerró ──────────────────────────────────────

def test_si_el_primario_falla_responde_el_respaldo(db, monkeypatch):
    primario = _proveedor(db, nombre="Primario")
    _proveedor(db, nombre="Respaldo")

    def segun_proveedor(prov, *a, **k):
        if prov.name == "Primario":
            raise RuntimeError("primario caído")
        return _respuesta(texto="respondió el respaldo")

    monkeypatch.setattr(svc, "call_provider", segun_proveedor)

    texto = svc.call_ai(db, [{"role": "user", "content": "x"}],
                        provider_id=primario.id, module="respaldo",
                        skip_guardrails=True)
    assert texto == "respondió el respaldo"

    log = db.query(AIUsageLog).filter(AIUsageLog.module == "respaldo").one()
    assert log.success is True, "una llamada atendida por el respaldo es un éxito"


def test_el_registro_atribuye_la_llamada_al_proveedor_que_de_verdad_respondio(db, monkeypatch):
    """El hueco de observabilidad, cerrado.

    Antes `_try_fallback_providers` devolvía sólo el resultado y `call_ai`
    registraba `provider_id = None`. El coste quedaba contado en el proveedor
    pero la fila del log no se podía agrupar por él: los agregados por proveedor
    y el registro de uso discrepaban justo para el tráfico de respaldo.
    """
    primario = _proveedor(db, nombre="Primario")
    respaldo = _proveedor(db, nombre="Respaldo")

    def segun_proveedor(prov, *a, **k):
        if prov.name == "Primario":
            raise RuntimeError("primario caído")
        return _respuesta()

    monkeypatch.setattr(svc, "call_provider", segun_proveedor)

    svc.call_ai(db, [{"role": "user", "content": "x"}], provider_id=primario.id,
                module="atribucion", skip_guardrails=True)

    log = db.query(AIUsageLog).filter(AIUsageLog.module == "atribucion").one()
    assert log.provider_id == respaldo.id, (
        "la llamada debe quedar atribuida al proveedor que respondió, no a nadie"
    )
    assert log.provider_id is not None


def test_si_fallan_todos_se_conserva_el_error_del_primario(db, monkeypatch):
    """El del primario es el informativo: es el que se eligió a propósito."""
    primario = _proveedor(db, nombre="Primario")
    monkeypatch.setattr(svc, "call_provider",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("error del primario")))

    texto = svc.call_ai(db, [{"role": "user", "content": "x"}],
                        provider_id=primario.id, skip_guardrails=True)
    assert "error del primario" in texto


def test_el_respaldo_no_reintenta_los_que_estan_en_error(db, monkeypatch):
    _proveedor(db, nombre="Ya roto", estado="error")
    _proveedor(db, nombre="Bueno")
    intentados = []

    def registrar(prov, *a, **k):
        intentados.append(prov.name)
        return _respuesta()

    monkeypatch.setattr(svc, "call_provider", registrar)
    svc.call_ai(db, [{"role": "user", "content": "x"}], skip_guardrails=True)
    assert "Ya roto" not in intentados


# ── Gobernanza: la razón de que esta función exista tal como es ───────────────

def test_un_prompt_bloqueado_no_llega_al_modelo(db, monkeypatch):
    """La política corta ANTES de la llamada. Si sólo se revisara la salida, el
    contenido prohibido ya habría salido de la organización."""
    p = _proveedor(db, nombre="No debe llamarse")
    monkeypatch.setattr(svc, "call_provider",
                        lambda *a, **k: pytest.fail("el modelo no debía llamarse"))

    import app.services.ai_governance as gov
    monkeypatch.setattr(
        gov, "check_prompt",
        lambda *a, **k: type("R", (), {"allowed": False, "blocked_by": "datos_personales",
                                       "redacted_text": None})(),
    )

    texto = svc.call_ai(db, [{"role": "user", "content": "un DNI"}],
                        provider_id=p.id, user_id="admin-test-id")
    assert "bloqueado por política de gobernanza" in texto
    assert "datos_personales" in texto


def test_un_prompt_redactado_es_el_que_se_manda_al_modelo(db, monkeypatch):
    """La redacción se escribe en `messages` a propósito: lo que sale hacia el
    proveedor tiene que ser el texto ya redactado, no el original."""
    p = _proveedor(db, nombre="Recibe redactado")
    enviados = []
    monkeypatch.setattr(
        svc, "call_provider",
        lambda prov, msgs, *a, **k: enviados.append(msgs[-1]["content"]) or _respuesta(),
    )

    import app.services.ai_governance as gov
    monkeypatch.setattr(
        gov, "check_prompt",
        lambda *a, **k: type("R", (), {"allowed": True, "blocked_by": None,
                                       "redacted_text": "mi [REDACTADO]"})(),
    )

    svc.call_ai(db, [{"role": "user", "content": "mi 12345678Z"}],
                provider_id=p.id, user_id="admin-test-id")
    assert enviados == ["mi [REDACTADO]"]


def test_una_respuesta_bloqueada_no_se_devuelve(db, monkeypatch):
    p = _proveedor(db, nombre="Salida bloqueada")
    monkeypatch.setattr(svc, "call_provider",
                        lambda *a, **k: _respuesta(texto="algo prohibido"))

    import app.services.ai_governance as gov
    monkeypatch.setattr(gov, "check_prompt",
                        lambda *a, **k: type("R", (), {"allowed": True, "blocked_by": None,
                                                       "redacted_text": None})())
    monkeypatch.setattr(gov, "check_output",
                        lambda *a, **k: type("R", (), {"allowed": False,
                                                       "redacted_text": None})())

    texto = svc.call_ai(db, [{"role": "user", "content": "x"}],
                        provider_id=p.id, user_id="admin-test-id")
    assert texto == "[Respuesta bloqueada por política de gobernanza]"


def test_skip_guardrails_no_evalua_politicas(db, monkeypatch):
    """Existe para las llamadas internas que no son de cara al usuario
    —embeddings, sondas de salud—. Que funcione importa, pero más importa que
    NADIE lo use por defecto: el valor por defecto es False."""
    import inspect

    firma = inspect.signature(svc.call_ai)
    assert firma.parameters["skip_guardrails"].default is False

    p = _proveedor(db, nombre="Interno")
    monkeypatch.setattr(svc, "call_provider", lambda *a, **k: _respuesta())

    import app.services.ai_governance as gov
    monkeypatch.setattr(gov, "check_prompt",
                        lambda *a, **k: pytest.fail("no debía evaluarse"))

    texto = svc.call_ai(db, [{"role": "user", "content": "x"}], provider_id=p.id,
                        user_id="admin-test-id", skip_guardrails=True)
    assert texto == "hola"


def test_un_fallo_del_motor_de_politicas_no_deja_la_aplicacion_sin_ia(db, monkeypatch):
    """Se sigue y queda en el log. Es una decisión discutible y por eso está
    fijada: la alternativa —cortar toda la IA si el motor de políticas falla—
    convierte una avería de un componente auxiliar en una caída funcional."""
    p = _proveedor(db, nombre="Políticas caídas")
    monkeypatch.setattr(svc, "call_provider", lambda *a, **k: _respuesta())

    import app.services.ai_governance as gov
    monkeypatch.setattr(gov, "check_prompt",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("motor caído")))

    texto = svc.call_ai(db, [{"role": "user", "content": "x"}],
                        provider_id=p.id, user_id="admin-test-id")
    assert texto == "hola"


def test_las_politicas_de_salida_no_se_evaluan_sobre_un_error(db, monkeypatch):
    """No hay respuesta que revisar, y el texto devuelto es el error del
    proveedor: pasarlo por las políticas lo redactaría sin sentido."""
    p = _proveedor(db, nombre="Falla")
    monkeypatch.setattr(svc, "call_provider",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    import app.services.ai_governance as gov
    monkeypatch.setattr(gov, "check_prompt",
                        lambda *a, **k: type("R", (), {"allowed": True, "blocked_by": None,
                                                       "redacted_text": None})())
    monkeypatch.setattr(gov, "check_output",
                        lambda *a, **k: pytest.fail("no debía evaluarse sobre un error"))

    texto = svc.call_ai(db, [{"role": "user", "content": "x"}],
                        provider_id=p.id, user_id="admin-test-id")
    assert texto.startswith("⚠️ AI provider error")
