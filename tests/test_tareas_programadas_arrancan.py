"""Las tareas programadas corren una vez, y en local tambien corren.

Auditoria 2026-11: setup.sh no arrancaba Celery (48 de 52 tareas no corrian
en local) y el stack de Docker corria a la vez APScheduler en la API y el
contenedor beat (tareas compartidas repetidas). Y la de recordatorios de
evaluaciones solo existia en APScheduler.
"""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def test_lo_que_corria_en_apscheduler_tambien_esta_en_beat():
    from app.worker import celery_app
    tareas = {e["task"] for e in celery_app.conf.beat_schedule.values()}
    for t in ("app.worker.run_scheduled_reports", "app.worker.run_scheduled_rotation",
              "app.worker.run_alert_engine", "app.worker.run_perf_reminders"):
        assert t in tareas, f"{t} no esta en Celery beat: con ENABLE_APSCHEDULER=0 no correria"


def test_setup_sh_arranca_celery_y_apaga_apscheduler():
    s = (RAIZ / "setup.sh").read_text(encoding="utf-8")
    assert "celery -A app.worker.celery_app worker" in s
    assert "celery -A app.worker.celery_app beat" in s
    # 23-11-2026: el modo se decide al arrancar (`CONTECFLOW_TAREAS=auto|celery|integrado`,
    # `decidir_modo_tareas`): con Redis, Celery (APScheduler apagado y beat encendido);
    # sin Redis, el planificador integrado. Nunca los dos a la vez.
    assert "ENABLE_APSCHEDULER=$RUN_APSCHEDULER ENABLE_CELERY_BEAT=$RUN_CELERY_BEAT" in s
    rama_celery = s[s.index('if [ "$TAREAS_MODO" = "celery" ]; then'):s.index("else", s.index('if [ "$TAREAS_MODO" = "celery" ]; then'))]
    assert "RUN_APSCHEDULER=0" in rama_celery and "RUN_CELERY_BEAT=1" in rama_celery


def test_docker_compose_no_corre_los_dos_planificadores():
    s = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'ENABLE_APSCHEDULER: "0"' in s and 'ENABLE_CELERY_BEAT: "1"' in s
