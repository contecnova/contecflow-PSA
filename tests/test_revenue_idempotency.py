"""Reconocimiento de ingresos ASC 606: idempotencia y zona del periodo.

Hallazgo encontrado mientras se cerraba el P2-14 (zonas horarias), y es peor que
lo que se estaba arreglando: `run_monthly_recognition` **no era idempotente**.

`_recognize_over_time` sumaba las horas imputadas del periodo y creaba un asiento
`recognized`, sin comprobar en ningún momento si ya existía asiento para ese
contrato y ese periodo. `RevenueEntry` tiene `period_year` y `period_month`, así
que la comprobación era trivial; simplemente no estaba, ni había restricción de
unicidad en la tabla (sólo dos índices, ninguno único).

Consecuencia: cada re-ejecución del lote sobre el mismo mes reconocía **otra vez**
los mismos ingresos, hasta agotar el valor del contrato. Y había tres formas
realistas de re-ejecutarlo:

  · un reintento de Celery tras un fallo transitorio de red;
  · un disparo manual del lote para «recuperar» un mes;
  · y la que lo vuelve probable en producción: hasta el arreglo del hallazgo 12,
    `beat` corría DENTRO del contenedor del worker, así que con más de una
    réplica había varios planificadores disparando el mismo lote a la vez.

El único freno era `is_period_closed()`, que sólo protege si alguien ha cerrado
el periodo explícitamente. En una instalación que no cierra periodos, no protegía
nada.

Este módulo era además el mayor de la solución sin ningún test.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.imputation import Imputation
from app.models.project import Project, ProjectType
from app.models.revenue import ASCMethod, EntryType, RevenueContract, RevenueEntry
from app.services.revenue_service import run_monthly_recognition

PERIODO = (2026, 7)


def _sembrar_contrato_tm(db, *, horas=10.0, tarifa=100.0, valor_contrato=100_000.0):
    """Contrato T&M con horas imputadas en el periodo. Devuelve el contrato."""
    from app.models.mfa import Organization

    org = db.query(Organization).first()
    assert org is not None, "las fixtures deben dejar al menos una organización"

    proj = Project(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        code=f"REC-{uuid.uuid4().hex[:8]}",
        name="Proyecto reconocimiento",
        project_type=ProjectType.consulting,
        # `billing_rate` es el nombre REAL del campo en Project. El servicio leía
        # `hourly_rate` y `daily_rate`, que no existen — ver
        # test_la_tarifa_se_lee_del_campo_que_existe.
        billing_rate=tarifa,
        is_billable=True,
    )
    db.add(proj)
    db.flush()

    contrato = RevenueContract(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        project_id=proj.id,
        name="Contrato T&M",
        contract_value=valor_contrato,
        currency="EUR",
        method=ASCMethod.over_time,
        is_active=True,
    )
    db.add(contrato)

    year, month = PERIODO
    from app.models.user import User

    usuario = db.query(User).first()
    db.add(
        Imputation(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            project_id=proj.id,
            user_id=usuario.id if usuario else None,
            date=date(year, month, 15),
            hours=horas,
            # Aprobadas: sólo esas cuentan para el reconocimiento (ver
            # test_solo_se_reconocen_las_horas_aprobadas).
            is_approved=True,
        )
    )
    db.commit()
    return contrato


def _asientos(db, contrato):
    return (
        db.query(RevenueEntry)
        .filter(
            RevenueEntry.rev_contract_id == contrato.id,
            RevenueEntry.entry_type == EntryType.recognized,
            RevenueEntry.period_year == PERIODO[0],
            RevenueEntry.period_month == PERIODO[1],
        )
        .all()
    )


# ── El fallo: dos pasadas, dos veces los mismos ingresos ──────────────────────

def test_dos_pasadas_del_lote_no_duplican_ingresos(db):
    """El caso que reventaba: mismo mes, dos ejecuciones.

    Con 10 h × 100 €/h el reconocimiento correcto es 1.000 €, una sola vez. Antes
    del arreglo la segunda pasada creaba un segundo asiento de otros 1.000 € y el
    total quedaba en 2.000 € — ingresos inventados en las cuentas.
    """
    contrato = _sembrar_contrato_tm(db, horas=10.0, tarifa=100.0)

    run_monthly_recognition(db, *PERIODO)
    tras_una = _asientos(db, contrato)
    assert len(tras_una) == 1, "la primera pasada debe crear exactamente un asiento"
    assert tras_una[0].amount == pytest.approx(1000.0)

    run_monthly_recognition(db, *PERIODO)
    tras_dos = _asientos(db, contrato)

    assert len(tras_dos) == 1, (
        f"la segunda pasada creó {len(tras_dos)} asientos: los ingresos se están "
        f"contabilizando dos veces"
    )
    assert sum(a.amount for a in tras_dos) == pytest.approx(1000.0), (
        "el total reconocido del periodo cambió al repetir el lote"
    )


def test_el_lote_es_idempotente_aunque_se_repita_muchas_veces(db):
    """Un reintento de Celery puede disparar el lote varias veces seguidas."""
    contrato = _sembrar_contrato_tm(db, horas=4.0, tarifa=250.0)

    for _ in range(5):
        run_monthly_recognition(db, *PERIODO)

    asientos = _asientos(db, contrato)
    assert len(asientos) == 1
    assert asientos[0].amount == pytest.approx(1000.0)


def test_el_total_devuelto_no_cuenta_lo_ya_reconocido(db):
    """La segunda pasada debe informar 0, no repetir el importe.

    Si informase 1.000 € otra vez, un panel que sume las salidas del lote
    presentaría el doble de ingresos aunque la tabla estuviese bien.
    """
    _sembrar_contrato_tm(db, horas=10.0, tarifa=100.0)

    primera = run_monthly_recognition(db, *PERIODO)
    segunda = run_monthly_recognition(db, *PERIODO)

    assert primera["recognized"]["over_time"] == pytest.approx(1000.0)
    assert segunda["recognized"]["over_time"] == pytest.approx(0.0), (
        "la segunda pasada informa ingresos que no ha reconocido"
    )


def test_periodos_distintos_del_mismo_contrato_si_se_reconocen(db):
    """La guarda es por (contrato, periodo): no puede bloquear el mes siguiente."""
    contrato = _sembrar_contrato_tm(db, horas=10.0, tarifa=100.0)
    from app.models.mfa import Organization
    from app.models.user import User

    org = db.query(Organization).first()
    usuario = db.query(User).first()
    # Horas en agosto, el mes siguiente al del resto del módulo.
    db.add(
        Imputation(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            project_id=contrato.project_id,
            user_id=usuario.id if usuario else None,
            date=date(2026, 8, 10),
            hours=5.0,
            is_approved=True,
        )
    )
    db.commit()

    run_monthly_recognition(db, 2026, 7)
    run_monthly_recognition(db, 2026, 8)

    agosto = (
        db.query(RevenueEntry)
        .filter(
            RevenueEntry.rev_contract_id == contrato.id,
            RevenueEntry.entry_type == EntryType.recognized,
            RevenueEntry.period_year == 2026,
            RevenueEntry.period_month == 8,
        )
        .all()
    )
    assert len(agosto) == 1, "agosto debe reconocerse aunque julio ya esté reconocido"
    assert agosto[0].amount == pytest.approx(500.0)


# ── El defecto que dejaba la función inservible ───────────────────────────────

def test_la_tarifa_se_lee_del_campo_que_existe(db):
    """El peor de los tres defectos: reconocía SIEMPRE cero euros.

    El servicio leía la tarifa así:

        getattr(proj, "hourly_rate", None) or getattr(proj, "daily_rate", None) or 0.0

    y ninguno de esos dos campos existe en `Project` — el real es `billing_rate`.
    Como los dos `getattr` llevaban valor por defecto, no lanzaba nada: la tarifa
    valía 0.0, el importe 0.0, y el `if recognized > 0` no entraba nunca. El
    reconocimiento ASC 606 de T&M y consumo no creaba un solo asiento, sin un
    error en los registros. Verificado ejecutando el lote: 0 asientos.
    """
    cols = {c.name for c in Project.__table__.columns}
    assert "billing_rate" in cols
    assert "hourly_rate" not in cols, (
        "si alguien añade hourly_rate, revisar revenue_service: el fallo original "
        "fue leer este nombre"
    )
    assert "daily_rate" not in cols

    contrato = _sembrar_contrato_tm(db, horas=8.0, tarifa=125.0)
    run_monthly_recognition(db, *PERIODO)

    asientos = _asientos(db, contrato)
    assert len(asientos) == 1, "el lote debe reconocer, no quedarse en cero"
    assert asientos[0].amount == pytest.approx(1000.0), "8 h × 125 €/h = 1.000 €"


def test_un_proyecto_sin_tarifa_no_reconoce_pero_avisa(db, caplog):
    """Un dato que falta no puede ser silencio.

    Antes, «proyecto sin tarifa» y «no hay horas» eran indistinguibles: ambos
    devolvían 0.0 sin decir nada. Quien opera el cierre necesita saber qué
    contratos se han quedado fuera.
    """
    import logging

    contrato = _sembrar_contrato_tm(db, horas=8.0, tarifa=None)
    with caplog.at_level(logging.WARNING, logger="contecflow.revenue"):
        run_monthly_recognition(db, *PERIODO)

    assert _asientos(db, contrato) == []
    assert any("billing_rate" in r.message for r in caplog.records), (
        "el cierre no avisó de que un proyecto no tiene tarifa"
    )


def test_solo_se_reconocen_las_horas_aprobadas(db):
    """La función decía «approved imputation hours» y no filtraba `is_approved`.

    Reconocer ingresos sobre horas todavía sin aprobar es lo que un auditor de
    ASC 606 / IFRS 15 marca: el importe no es exigible hasta que las horas están
    validadas.
    """
    from app.models.mfa import Organization
    from app.models.user import User

    contrato = _sembrar_contrato_tm(db, horas=8.0, tarifa=100.0)
    org = db.query(Organization).first()
    usuario = db.query(User).first()

    # 4 h más en el mismo periodo, SIN aprobar.
    db.add(
        Imputation(
            id=str(uuid.uuid4()),
            organization_id=org.id,
            project_id=contrato.project_id,
            user_id=usuario.id if usuario else None,
            date=date(PERIODO[0], PERIODO[1], 20),
            hours=4.0,
            is_approved=False,
        )
    )
    db.commit()

    run_monthly_recognition(db, *PERIODO)
    asientos = _asientos(db, contrato)
    assert len(asientos) == 1
    assert asientos[0].amount == pytest.approx(800.0), (
        "se han reconocido las 4 h sin aprobar: el importe debería ser 8 h × 100 €"
    )


# ── La tabla debe impedirlo también a nivel de esquema ─────────────────────────

def test_la_tabla_tiene_indice_unico_para_el_lote(db):
    """La comprobación en código no basta contra dos procesos concurrentes.

    Hasta el arreglo del hallazgo 12, varios `beat` podían disparar el lote a la
    vez: dos transacciones leen «no hay asiento» y ambas insertan. Sólo un índice
    único en la base lo impide de verdad.
    """
    unicos = {i.name: i for i in RevenueEntry.__table__.indexes if i.unique}
    assert "uq_rev_entries_lote_periodo" in unicos, (
        "falta el índice único del lote mensual; únicos presentes: "
        f"{sorted(unicos)}"
    )
    idx = unicos["uq_rev_entries_lote_periodo"]
    assert [c.name for c in idx.columns] == [
        "rev_contract_id", "period_year", "period_month",
    ]


def test_el_indice_unico_es_parcial_y_no_alcanza_a_hitos_ni_reversiones(db):
    """El alcance del índice es la parte delicada, y se fija aquí.

    Un único sobre (contrato, año, mes, tipo) habría ROTO producción: el
    reconocimiento por hitos crea varios asientos `recognized` del mismo contrato
    y periodo —uno por obligación satisfecha— y una reversión comparte periodo
    con el asiento que revierte. Por eso el índice se limita a las filas del lote
    mensual: `milestone_id IS NULL AND entry_type = 'recognized'`.
    """
    idx = next(
        i for i in RevenueEntry.__table__.indexes
        if i.name == "uq_rev_entries_lote_periodo"
    )
    for dialecto in ("sqlite", "postgresql"):
        clausula = idx.dialect_options[dialecto].get("where")
        assert clausula is not None, f"el índice no es parcial en {dialecto}"
        texto = str(clausula)
        assert "milestone_id IS NULL" in texto, (
            f"en {dialecto} el índice alcanzaría a los asientos de hitos"
        )
        assert "recognized" in texto, (
            f"en {dialecto} el índice alcanzaría a las reversiones"
        )


def test_el_reconocimiento_por_hitos_puede_crear_varios_asientos_por_periodo(db):
    """Contra-test del anterior: demuestra que la exclusión es necesaria.

    Si alguien «simplifica» el índice quitándole la cláusula parcial, este test
    es el que se pone rojo, y con el motivo delante.
    """
    from app.models.revenue import EntryType as ET

    contrato = _sembrar_contrato_tm(db)
    hito = str(uuid.uuid4())
    for i in range(2):
        db.add(
            RevenueEntry(
                id=str(uuid.uuid4()),
                organization_id=contrato.organization_id,
                rev_contract_id=contrato.id,
                entry_type=ET.recognized,
                amount=100.0 * (i + 1),
                currency="EUR",
                period_year=PERIODO[0],
                period_month=PERIODO[1],
                milestone_id=hito,
                description=f"Obligación {i} satisfecha",
            )
        )
    db.commit()  # no debe violar nada: llevan milestone_id

    con_hito = (
        db.query(RevenueEntry)
        .filter(
            RevenueEntry.rev_contract_id == contrato.id,
            RevenueEntry.milestone_id == hito,
        )
        .count()
    )
    assert con_hito == 2, (
        "dos obligaciones del mismo hito y periodo deben poder convivir"
    )
