# Propuestas de mejoras visuales y de usabilidad para la coordinación FR/CR

## 1. Mejoras visuales
- Mostrar un badge con el estado CR junto al estado FR, con tooltip explicativo.
- Colorear el panel de la FR según el estado CR si existe (borde lateral).
- Añadir iconos diferenciadores para FR y CR.
- Tooltip sobre el badge CR explicando el significado del estado.

## 2. Usabilidad
- Al hacer click en el badge CR, mostrar un modal con detalles del Change Request vinculado (descripción, impacto, fechas, etc).
- Si la FR no tiene CR, mostrar un tooltip explicando cuándo se crea y su función.
- Añadir notificación (toast) cuando el estado CR cambia y el usuario está visualizando la FR. **(Implementado: el backend emite evento WebSocket y el frontend muestra toast en tiempo real)**
- En la vista de equipo, permitir filtrar FRs por estado CR.

## 3. Integración (opcional)
- Notificación por email o sistema interno cuando una CR vinculada cambia de estado relevante.
- Opción de suscribirse a cambios de estado de FR/CR.

---

---

## 4. Internacionalización (i18n) — Estado de traducciones

**Revisión completa realizada:** Todas las claves de traducción para los flujos de Feature Request (FR), Change Request (CR) y la interfaz del portal están presentes y revisadas en los 8 idiomas soportados (es, en, fr, de, pt, it, pl, zh). No faltan claves en ningún idioma. El sistema es completamente multilingüe y coherente para usuarios internacionales.

_Última revisión: [fecha de hoy]_