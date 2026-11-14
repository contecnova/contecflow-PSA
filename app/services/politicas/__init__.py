"""Motor común de políticas, reglas y flujos (tarea #26).

API para los dominios (gastos #27, ausencias #25, compras, partes de horas…):

    from app.services import politicas
    ev = politicas.evaluar(db, "gastos", entidad)            # sin efectos
    politicas.requisitos_pendientes(db, "gastos", entidad, ev["resultado"])
    politicas.aplicar_campos(db, "gastos", entidad, ev["resultado"])
    politicas.registrar_evaluacion(db, "gastos", entidad.id, ev, usuario_id=…)
    fuentes.abrir(db, "expense", …, evaluacion=ev)          # niveles, pasos y avisos en la aprobación

Registrar un dominio: `catalogo.registrar(Dominio(...))` (ver dominios/gastos.py).
"""
from app.services.politicas.catalogo import Campo, Dominio, Opcion, dominio, dominios, registrar  # noqa: F401
from app.services.politicas.motor import (  # noqa: F401
    aplicar_campos, ejecutar_avisos, evaluar, invalidar, registrar as registrar_evaluacion, requisitos_pendientes,
)
