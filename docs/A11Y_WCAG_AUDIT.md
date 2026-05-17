# Auditoria A11y WCAG (P3)

## Objetivo
Establecer una auditoria integral de accesibilidad con dos capas:
- automatizada (repetible)
- manual (foco, contraste, semantica)

## Capa automatizada

### 1) Lint A11y frontend
Desde `frontend/`:

```bash
npm run lint:a11y:report
npm run lint:a11y:strict:core
```

Salida:
- `frontend/reports/a11y-eslint.json`
- `frontend/reports/a11y-summary.json`

### 2) E2E A11y baseline (Playwright + pytest)
Desde raiz del repo:

```bash
venv/bin/python -m pytest -q tests_e2e/test_e2e_accessibility_wcag.py
```

Cobertura baseline del test:
- landmark `main`
- nombres accesibles en controles interactivos
- `alt` en imagenes
- etiquetado basico de campos de formulario
- navegacion por teclado (Tab)

## Capa manual (checklist)

Validar en rutas criticas (`/tasks`, `/projects`, `/reports`, `/org-chart`, `/service-desk`, `/portal`) lo siguiente:

1. Foco visible y consistente
- El foco siempre es visible al tabular.
- No hay trampas de foco en modales.
- El orden de foco coincide con el orden visual.

2. Contraste (WCAG 2.1 AA)
- Texto normal >= 4.5:1
- Texto grande >= 3:1
- Iconos/controles informativos >= 3:1

3. Semantica y landmarks
- Un `main` por pagina.
- Jerarquia de headings coherente (`h1 -> h2 -> h3`).
- Botones y enlaces usan elementos semanticos correctos.

4. Formularios y errores
- Todo campo tiene `label` o `aria-label`/`aria-labelledby`.
- Errores asociados por `aria-describedby`.
- Mensajes de error entendibles para lector de pantalla.

5. Estados dinamicos
- Notificaciones/toasts relevantes anuncian cambios (regiones `aria-live`).
- Spinners/cargas comunican estado y no bloquean teclado.

## Criterio de salida de sprint
- `lint:a11y:strict:core` sin warnings/errors.
- Test `tests_e2e/test_e2e_accessibility_wcag.py` en verde en entorno local estable.
- Checklist manual completado en rutas criticas con hallazgos registrados y priorizados.
