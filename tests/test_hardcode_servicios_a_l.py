"""Hardcode de idioma en los servicios a-l (23-11-2026): estatico y barato.

Comprueba que las claves nuevas (`textos_de_salida_servicios_a_l`) tienen es/en/zh (y los 8 idiomas
las del portal), que sus datos `{x}` coinciden en todos los idiomas, que cada clave usada por los
servicios existe y que los ficheros arreglados ya no contienen los literales retirados.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SERVICIOS = RAIZ / "app" / "services"


def _textos():
    from app.services.textos_de_salida import TEXTOS
    from app.services.textos_de_salida_servicios_a_l import TEXTOS_SERVICIOS_A_L
    return TEXTOS, TEXTOS_SERVICIOS_A_L


def test_las_claves_nuevas_estan_en_el_diccionario_general_y_en_los_tres_idiomas():
    general, nuevas = _textos()
    assert len(nuevas) > 300
    for clave, variantes in nuevas.items():
        assert clave in general, clave
        for idioma in ("es", "en", "zh"):
            assert (variantes.get(idioma) or "").strip(), (clave, idioma)


def test_las_etiquetas_del_portal_estan_en_los_ocho_idiomas():
    _, nuevas = _textos()
    ocho = ("es", "en", "zh", "fr", "de", "it", "pt", "pl")
    portal = {k: v for k, v in nuevas.items() if k.startswith(("portal_etiqueta.", "portal.acceso.", "portal.panel."))}
    assert portal
    for clave, variantes in portal.items():
        assert set(ocho) <= set(variantes), clave


def test_los_datos_de_cada_plantilla_coinciden_en_todos_los_idiomas():
    _, nuevas = _textos()
    for clave, variantes in nuevas.items():
        datos = {idioma: sorted(set(re.findall(r"\{(\w+)\}", t))) for idioma, t in variantes.items()}
        assert len({tuple(d) for d in datos.values()}) == 1, (clave, datos)


FICHEROS_ARREGLADOS = {
    # fichero: literales castellanos que ya no pueden estar en el codigo
    "absence_service.py": ['"Vacaciones"', '"Pendiente"'],
    "alert_service.py": ["Sobreasignación", "lleva bloqueada", "Deadline en"],
    "ai_chat/tool_execution/crm.py": ["Acceso denegado"],
    "ai_chat/tool_execution/projects.py": ["Proyecto no encontrado", "Solo puedes editar"],
    "ai_chat/tool_execution/software.py": ["Máquina no encontrada", "Modo desconocido"],
    "ai_chat/tool_execution/meetings.py": ["Reunión no encontrada"],
    "ai_chat/tool_execution/tickets.py": ["Usuario no encontrado"],
    "ai_chat/tool_execution/executor.py": ["Herramienta desconocida"],
    "ai_modules/voice.py": ["No encontré el proyecto", "Propuesta:"],
    "ai_modules/client_portal.py": ["El asistente no está disponible"],
    "ai_modules/meetings.py": ["Reunión procesada por IA", "TRUNCADO"],
    "cmdb_service.py": ["superaría la capacidad", "Plan generado para"],
    "cmdb_software/gestion.py": ["Plazo de remediación", "Corregida en"],
    "cab_service/correo.py": ["Tarea vencida", "Nuevo ticket asignado"],
    "client_service.py": ["licencia(s) vencen"],
    "expense_service.py": ["Gasto aprobado", "Gasto rechazado", "Retirado por quien"],
    "gastos_avanzados.py": ['"Viajes y transporte"', '"Subcontratación"'],
    "custom_fields_service.py": ['"En progreso"', "Enviar a revisión"],
    "issue_type_service.py": ['"Historia"', "Investigación técnica"],
    "horas_extra/control.py": ["Horas fuera de horario"],
    "horas_extra/ejemplos.py": ["Máximo legal", "Como mucho 4"],
    "horario/jornadas.py": ["los tramos pasan de 24 horas", "la pausa no puede"],
    "imputation_service/_comun.py": ["Imputación forzada", "forzó el cierre"],
    "externos/horas.py": ["asignación consumida"],
    "lecciones.py": ['_h("Estado"', '_h("Causa raíz"', "Borrador con IA desactivado"],
    "grc_sod.py": ["Quien crea facturas", "Quien configura el sistema"],
    "automations_service/reglas.py": ["crearía una alerta", "Recuerda enviar tu parte"],
    "collaboration/bots.py": ["Bot Nexus no disponible", "Bienvenido al equipo", '"assignee": "soporte"'],
    "client_portal_service/serializacion.py": ['"Presupuestada"', '"Acta reunión"'],
    "client_portal_service/peticiones.py": ['"Crítico"'],
    "client_portal_service/panel.py": ["no tiene ningún proyecto asignado"],
    "demanda/plantillas.py": ["Triaje Digital", "Demanda Digital", "CAB Digital", "Comité de Digitalización"],
    "demanda/biblioteca.py": ["Comité de Digitalización", "CAB de Digital"],
    "ai_planning_service.py": ["Clasificación por reglas heurísticas.", "Basado en {len"],
}


@pytest.mark.parametrize("fichero,literales", sorted(FICHEROS_ARREGLADOS.items()))
def test_los_ficheros_arreglados_no_llevan_los_literales_retirados(fichero, literales):
    codigo = (SERVICIOS / fichero).read_text(encoding="utf-8")
    # el cuerpo sin docstrings/comentarios no es necesario: los literales retirados no aparecen ni en comentarios
    for lit in literales:
        assert lit not in codigo, f"{fichero}: sigue el literal {lit!r}"


def test_las_claves_que_usan_los_servicios_existen():
    general, _ = _textos()
    usadas = set()
    patron = re.compile(r'["\']((?:ausencia|alerta|ia_tool|voz|portal_ia|reunion|planificacion|plan_sprint|sw_remediacion|gasto|'
                        r'tipo_incidencia|flujo|horas_extra|jornada|imputacion_forzada|externos|bot|automatizacion|'
                        r'plantilla_auto|leccion|sod|plantilla_correo|correo|cliente|portal)\.[a-z0-9_.]+)["\']')
    for fichero in FICHEROS_ARREGLADOS:
        for m in patron.finditer((SERVICIOS / fichero).read_text(encoding="utf-8")):
            usadas.add(m.group(1))
    # las que se arman con f"..." (`ausencia.tipo.{x}`) o por prefijo no casan aqui: se comprueban por familia
    for clave in usadas:
        assert clave in general or any(k.startswith(clave) for k in general), clave


def test_la_plantilla_de_demanda_es_opcional_y_generica():
    from app.services.demanda import biblioteca, plantillas
    assert "nueva_funcionalidad" in biblioteca.PLANTILLAS
    assert "piloto_digital" not in biblioteca.PLANTILLAS and "piloto_digital" in plantillas.CLAVES_ANTIGUAS
    for clave in plantillas.GRUPOS:
        for idioma in ("es", "en", "zh"):
            assert "Digital" not in plantillas.nombre_de_grupo(clave, idioma)
    siembra = (RAIZ / "app" / "db" / "seed_parts" / "demanda.py").read_text(encoding="utf-8")
    assert "sembrar_plantilla_piloto" not in siembra


def test_las_palabras_de_triaje_tienen_ingles_y_chino():
    from app.services import ai_planning_service as ap
    todas = {p for _, palabras in ap._PALABRAS_DE_PRIORIDAD for p in palabras}
    assert {"urgent", "slow", "question"} <= todas
    assert any("一" <= c <= "鿿" for p in todas for c in p)
