// stylelint (24-11-2026): `npm run lint:css` / `make lint-css` / `setup.bat lint-css`.
// Se ejecuta a mano; no hay hooks ni CI que lo exijan.
//
// Base: stylelint-config-standard. Lo que se cambia, y por qué:
//
// Convive con scripts/kit/comprobarCss.mjs, no lo duplica. Las reglas del kit
// (mayúsculas forzadas, letra monoespaciada, colores literales, altos fijos de
// controles, `.ds-input`, botones de icono propios) son reglas del proyecto con
// CUPOS por fichero que solo pueden encoger (kit-pendientes.json, que leen
// src/__tests__/kitCssSinRestos.test.ts y scripts/kit_pendientes.mjs). stylelint
// no tiene ese trinquete: como error romperían `lint:css` en los ficheros con
// cupo, y como aviso serían ruido que ya cuenta el kit. Así que stylelint vigila
// el CSS estándar (sintaxis, duplicados, valores no válidos, notación) y el kit
// sigue siendo la única fuente de sus reglas.
export default {
  extends: ['stylelint-config-standard'],
  rules: {
    // Estilo de la casa: reglas compactas en una línea (`.x { a: 1; b: 2; }`)
    // agrupadas sin línea en blanco. Son solo espacios; exigir lo contrario
    // daba ~7.200 avisos (medido el 24-11-2026) sin detectar ningún fallo.
    'declaration-block-single-line-max-declarations': null,
    'rule-empty-line-before': null,
    'at-rule-empty-line-before': null,
    'comment-empty-line-before': null,
    'declaration-empty-line-before': null,
    'custom-property-empty-line-before': null,

    // BEM en kebab-case (`bloque__elemento--modificador`), que es la
    // convención del proyecto. El modificador admite `_` porque muchos salen de
    // valores de enum (`--in_progress`, `--auto_approve`). Excepciones: clases
    // que pone el editor (Tiptap/ProseMirror), no nosotros.
    'selector-class-pattern': [
      '^(?:[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:__[a-z0-9]+(?:-[a-z0-9]+)*)?(?:--[a-z0-9_]+(?:-[a-z0-9_]+)*)?|ProseMirror(?:-[a-z]+)*|selectedCell)$',
      { message: (s) => `La clase "${s}" no sigue BEM en kebab-case (bloque__elemento--modificador)` },
    ],
    // Las animaciones globales (`fadeIn`, `fadeUp`…) se nombran desde estilos
    // en línea de los componentes: se admite lowerCamelCase además de kebab.
    'keyframes-name-pattern': [
      '^[a-z][a-zA-Z0-9]*(?:-[a-z0-9]+)*$',
      { message: (s) => `El nombre de animación "${s}" debe ser kebab-case o lowerCamelCase` },
    ],
    // 73 avisos, casi todos el patrón de accesibilidad del proyecto: un bloque
    // común `.a:focus-visible, .b:focus-visible…` al principio de la hoja y
    // después la regla base de cada clase. La regla mira el orden, no si dos
    // reglas chocan de verdad; reordenar 73 sitios para callarla mueve la
    // cascada a ciegas, que es justo el riesgo que quiere evitar.
    'no-descending-specificity': null,
  },
}
