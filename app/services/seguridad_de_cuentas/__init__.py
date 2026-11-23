"""Políticas de cuenta y seguridad de acceso (23-11-2026).

Documentado en docs/seguridad/politicas_de_cuenta.md. Módulos:

- `politica`: la política de la empresa (lectura, recomendados, validación, escritura).
- `contrasenas`: validación (comunes, personales, historial), cambio, caducidad, temporales.
- `bloqueo`: bloqueo persistente por intentos, aviso y desbloqueo.
- `mfa`: obligatorio por empresa/rol/capacidad, métodos, gracia, dispositivos, restablecer.
- `sesiones`: al abrir (acceso, concurrentes, IP nueva) y en cada petición (sid, inactividad, tope).
- `acceso`: IP/CIDR permitidas, horario, país.
- `guardas`: lo que corre en cada petición y las marcas de `UserPublic.account_security`.
- `alertas`: avisos al administrador y al usuario.
- `separacion`: segundo administrador para cambios de seguridad.
- `recertificacion`: campañas de revisión de accesos.
- `cumplimiento`, `rgpd`, `diario`: informe, copia del interesado y trabajo diario.
"""
