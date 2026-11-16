"""Licencias y hardware — fase 4: integración en toda la plataforma (16-11-2026).

- `bajas`: al desactivar a una persona se liberan sus licencias (ya o tras N
  días) y se abre la devolución de cada equipo, con ticket, hasta el acta.
- `kits`: kit de alta por rol, puesto, departamento o equipo; propuesta que el
  responsable confirma con un clic (asientos y equipos, o compra).
- `autoservicio`: «Mis equipos y licencias» de cada empleado.
- `catalogo`: pedir licencia o equipo desde el catálogo, con la aprobación de
  varios niveles del catálogo (motor común) y alta automática en ALM.
- `proyecto`: recursos técnicos de un proyecto (bolsa, licencias y equipos de
  su equipo, coste en el periodo).
- `personas`: los ganchos que llaman las altas y bajas de usuarios.

Todo lo que asigna, presta, libera o devuelve pasa por
`app.services.alm_asignaciones` (fases 1 y 3).
"""
