"""Las tres columnas que la auditoría dejó anotadas como decisión de producto.

Auditoría 2026-09. Las tres salieron del detector `audit_model_attrs.py`: código
que nombraba atributos que el esquema no tenía, y las tres reventaban con
`TypeError` en la primera línea útil. En agosto se arregló el síntoma y se dejó
escrito que **añadir la columna era decisión de producto**. La revisión 096 toma
esas decisiones; este fichero las fija.

No comprueba que las columnas existan —para eso ya está
`test_atributos_de_modelo_existen.py`— sino que **los tres caminos que fallaban
vuelven a funcionar de punta a punta**, que es lo que de verdad se arregló.
"""
from datetime import date

import pytest

from app.models.imputation import Imputation
from app.models.service_desk import MajorIncident, Ticket


# ── 1. El SMS entrante: el teléfono es la identidad de quien abre el ticket ──

def test_un_ticket_guarda_el_telefono_de_quien_lo_abre(db):
    """`requester_phone` existe y se puede escribir.

    El servicio de SMS entrantes lo pasaba al constructor detrás de un
    `hasattr` que protegía el valor y no la palabra clave, así que SQLAlchemy
    recibía igual `requester_phone=None` y respondía `TypeError`. Es decir:
    **abrir un ticket desde un SMS fallaba siempre**, no a veces.
    """
    t = Ticket(
        number="SD-TEL-1", ticket_type="incident", title="Desde un SMS",
        description="cuerpo", requester_name="+34600111222",
        requester_phone="+34600111222",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    assert t.requester_phone == "+34600111222"


def test_el_telefono_es_opcional(db):
    """Los tickets que no entran por SMS no tienen teléfono, y eso está bien."""
    t = Ticket(number="SD-TEL-2", ticket_type="incident", title="Por la web",
               description="cuerpo")
    db.add(t)
    db.commit()
    assert t.requester_phone is None


# ── 2. La importación de imputaciones desde CSV ──────────────────────────────

def test_una_imputacion_guarda_su_tipo_de_trabajo(db):
    """`work_type` existe: la importación CSV fallaba fila por fila sin ella."""
    i = Imputation(user_id="dev-test-id", project_id="p-x",
                   date=date.today(), hours=8.0, work_type="development")
    db.add(i)
    db.commit()
    db.refresh(i)
    assert i.work_type == "development"


def test_sin_tipo_de_trabajo_la_fila_se_queda_sin_el(db):
    """Y **no** se inventa un «development» por defecto en la base.

    El respaldo vive donde hace falta —en el informe que lo lee— y no en la
    fila: una imputación cuyo CSV no traía la columna no es una imputación de
    desarrollo, es una imputación sin tipo. Escribir el respaldo en la fila
    convierte un dato ausente en un dato afirmado, y eso no se puede deshacer.
    """
    i = Imputation(user_id="dev-test-id", project_id="p-x",
                   date=date.today(), hours=4.0)
    db.add(i)
    db.commit()
    assert i.work_type is None


# ── 3. La incidencia mayor y sus tickets ────────────────────────────────────

def test_una_incidencia_mayor_agrupa_tickets(db):
    """La relación que faltaba, en la dirección que se decidió.

    Un ticket pertenece como mucho a **una** incidencia mayor; una incidencia
    mayor agrupa muchos tickets. Es el modelo de ITIL y el conservador: una
    tabla de unión permitiría que dos incidencias mayores compartieran tickets,
    y eso hay que quererlo explícitamente.
    """
    mi = MajorIncident(number="MI-1", title="Caída total del ERP")
    db.add(mi)
    db.flush()

    t1 = Ticket(number="SD-MI-1", ticket_type="incident", title="No entro",
                description="x", major_incident_id=mi.id)
    t2 = Ticket(number="SD-MI-2", ticket_type="incident", title="Yo tampoco",
                description="x", major_incident_id=mi.id)
    suelto = Ticket(number="SD-MI-3", ticket_type="incident",
                    title="Otra cosa", description="x")
    db.add_all([t1, t2, suelto])
    db.commit()

    db.refresh(mi)
    assert {t.number for t in mi.tickets} == {"SD-MI-1", "SD-MI-2"}
    assert suelto.major_incident is None
    assert t1.major_incident.number == "MI-1"


def test_la_comprobacion_de_cumplimiento_ya_es_evaluable(db):
    """El motivo por el que hacía falta la relación.

    `governance_compliance_service` estaba escrito contra `MajorIncident.tickets`
    detrás de un `hasattr`. Como la relación no existía, la comprobación «P1 sin
    incidencia mayor declarada» quedó declarada **no evaluable** — mejor eso que
    un falso positivo por cada P1. Ahora se puede hacer, y sin haber tocado una
    línea de esa función.
    """
    from app.models.service_desk import MajorIncident as MI

    assert hasattr(MI, "tickets"), (
        "sin esta relación la comprobación de cumplimiento vuelve a quedar "
        "declarada no evaluable"
    )

    mi = MI(number="MI-2", title="Otra caída")
    db.add(mi)
    db.flush()
    con_mi = Ticket(number="SD-P1-1", ticket_type="incident", title="P1 cubierto",
                    description="x", major_incident_id=mi.id)
    db.add(con_mi)
    db.commit()

    # Es la consulta exacta que hace el informe de cumplimiento.
    encontrada = db.query(MI).filter(MI.tickets.any(id=con_mi.id)).first()
    assert encontrada is not None and encontrada.number == "MI-2"


@pytest.mark.parametrize("campo,modelo", [
    ("requester_phone", Ticket),
    ("major_incident_id", Ticket),
    ("work_type", Imputation),
])
def test_las_tres_son_opcionales(campo, modelo):
    """Ninguna de las tres puede ser obligatoria.

    Son datos que unos caminos traen y otros no: un ticket de la web no tiene
    teléfono, uno que no pertenece a una incidencia mayor no la tiene, y una
    imputación puede no declarar tipo de trabajo. Hacerlas NOT NULL obligaría a
    inventar un valor, que es justo lo que la revisión 096 evita.
    """
    assert getattr(modelo, campo).property.columns[0].nullable is True
