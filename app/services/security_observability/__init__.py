"""
Security Observability Service — SOC-ready event collection, detection, and analytics.

Responsibilities:
- Ingest & normalize security events from auth, ABAC, sessions, API middleware
- Fire detection rules (brute-force, impossible travel, mass export, cred stuffing, …)
- Maintain MTTD/MTTR metrics
- Update per-hour snapshot for instant dashboard rendering
- Raise LoginAnomaly records for dedicated anomaly widget

Auditoria 2026-11 (#24): eran 1053 lineas en un fichero. Se partio en
submodulos por responsabilidad, sin cambiar el codigo:

- `_comun`: Reloj UTC, logger y organizacion de la peticion, compartidos.
- `eventos`: Registro y deteccion de eventos de seguridad (fuerza bruta, MFA, exportaciones, sesiones).
- `analitica`: Analitica de seguridad: tendencias, resumenes y paneles.
"""

from app.services.security_observability._comun import (  # noqa: F401
    logger,
    _UTC,
    _utcnow,
    get_org_id,
)

from app.services.security_observability.eventos import (  # noqa: F401
    _trunc_hour,
    BRUTE_FORCE_WINDOW_MINUTES,
    BRUTE_FORCE_THRESHOLD,
    CRED_STUFFING_THRESHOLD,
    MASS_EXPORT_THRESHOLD,
    SESSION_CONCURRENT_LIMIT,
    MFA_FAIL_THRESHOLD,
    _CONTADOR_POR_SEVERIDAD,
    _CONTADOR_POR_TIPO,
    _sumar_uno,
    SecurityEventService,
)

from app.services.security_observability.analitica import (  # noqa: F401
    SecurityAnalyticsService,
)
