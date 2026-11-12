import js from '@eslint/js'
import reactPlugin from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import tsParser from '@typescript-eslint/parser'
import tsPlugin from '@typescript-eslint/eslint-plugin'

// Reglas de estilo con no-restricted-syntax. Van en una constante porque el
// bloque de services/api las repite sin la de fetch (una regla solo admite una
// lista de opciones por fichero).
const RESTRICCIONES_DE_ESTILO = [
  {
    selector: "Literal[value=/^#(00d4ff|0ea5e9|7c3aed)/i]",
    message: 'Hex literales de marca obsoletos (#00d4ff/#0ea5e9/#7c3aed). Usa var(--accent), var(--purple), o COLOR.* desde constants/theme.js.',
  },
  // Auditoria 2026-11: hex fijo como valor de una propiedad de color. Los
  // que coincidian con un token se pasaron a var() con
  // scripts/codemods/colores-a-tokens.mjs; esto impide que vuelvan.
  {
    selector: "Property[key.name=/^(color|background|backgroundColor|borderColor|fill|stroke|outlineColor)$/][value.type='Literal'][value.value=/^#[0-9a-fA-F]{3,8}$/]",
    message: 'Color hex fijo en una propiedad de estilo. Usa var(--token) (index.css) o COLOR.* de constants/theme; no sigue a los temas ni al acento.',
  },
  {
    selector: "Property[key.name='fontSize'][value.type='Literal'][value.raw=/^[0-9]+$/]",
    message: 'fontSize literal numérico. Usa var(--text-xs|sm|base|md|lg|xl|2xl|3xl) — escala definida en index.css.',
  },
  // Anti-patrón "card armada inline": background var(--surface-2) seguido
  // de borderRadius dentro del mismo style={{...}}. Usa la clase .ds-card
  // o el componente <Card> en lugar de repetir background + border + radius.
  {
    selector: "Property[key.name='background'][value.value='var(--surface-2)'] ~ Property[key.name='borderRadius']",
    message: 'Card armada inline detectada (background var(--surface-2) + borderRadius). Usa className="ds-card" o el componente <Card>.',
  },
]

// Auditoria 2026-11 (#29): fetch directo se salta el cliente API (cookies,
// CSRF, refresco de sesion en 401, desenvoltorio de respuestas y errores).
// Usa services/api; para flujos (SSE) `apiStream`, para URLs `apiUrl`/`apiWsUrl`.
// Si una excepcion es legitima, justificala en una linea y desactiva la regla ahi.
const MENSAJE_FETCH = 'fetch directo: usa el cliente de services/api (apiStream para flujos). Si es una excepcion legitima, justificala en un comentario.'
const FETCH_DIRECTO = [
  { selector: "CallExpression[callee.name='fetch']", message: MENSAJE_FETCH },
  { selector: "CallExpression[callee.object.name=/^(window|globalThis|self)$/][callee.property.name='fetch']", message: MENSAJE_FETCH },
]

const DIALOGOS_NATIVOS = ['confirm', 'prompt', 'alert']
const MENSAJE_DIALOGOS = 'Dialogo nativo prohibido: usa useConfirm().confirmar/pedirTexto (context/ConfirmContext) o useToast.'

export default [
  js.configs.recommended,
  // eslint-plugin-react flat config (ESLint v9 compatible)
  reactPlugin.configs.flat.recommended,
  reactPlugin.configs.flat['jsx-runtime'],
  {
    files: ['src/i18n/**/*.mjs'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        navigator: 'readonly',
        globalThis: 'readonly',
      },
    },
    rules: {
      'no-dupe-keys': 'off',
      'no-unused-vars': 'off',
      'no-undef': 'error',
    },
  },
  {
    files: ['src/**/*.{js,jsx,ts,tsx}'],
    plugins: {
      'react-hooks': reactHooks,
      'jsx-a11y': jsxA11y,
    },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        window: 'readonly',
        document: 'readonly',
        console: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        fetch: 'readonly',
        URL: 'readonly',
        URLSearchParams: 'readonly',
        FormData: 'readonly',
        FileReader: 'readonly',
        Blob: 'readonly',
        navigator: 'readonly',
        localStorage: 'readonly',
        sessionStorage: 'readonly',
        location: 'readonly',
        history: 'readonly',
        performance: 'readonly',
        ResizeObserver: 'readonly',
        IntersectionObserver: 'readonly',
        MutationObserver: 'readonly',
        AbortController: 'readonly',
        crypto: 'readonly',
        atob: 'readonly',
        btoa: 'readonly',
        process: 'readonly',
        __dirname: 'readonly',
        indexedDB: 'readonly',
        Event: 'readonly',
        CustomEvent: 'readonly',
        WebSocket: 'readonly',
        EventSource: 'readonly',
        Image: 'readonly',
        File: 'readonly',
        Headers: 'readonly',
        Request: 'readonly',
        Response: 'readonly',
        ReadableStream: 'readonly',
        MutationObserverInit: 'readonly',
        HTMLElement: 'readonly',
        HTMLInputElement: 'readonly',
        HTMLCanvasElement: 'readonly',
        SVGElement: 'readonly',
        Element: 'readonly',
        Node: 'readonly',
        NodeList: 'readonly',
        DOMParser: 'readonly',
        XMLSerializer: 'readonly',
        TextDecoder: 'readonly',
        TextEncoder: 'readonly',
        Promise: 'readonly',
        Symbol: 'readonly',
        Map: 'readonly',
        Set: 'readonly',
        WeakMap: 'readonly',
        WeakSet: 'readonly',
        Proxy: 'readonly',
        Reflect: 'readonly',
        globalThis: 'readonly',
        queueMicrotask: 'readonly',
        structuredClone: 'readonly',
        reportError: 'readonly',
        getComputedStyle: 'readonly',
        requestAnimationFrame: 'readonly',
        cancelAnimationFrame: 'readonly',
        caches: 'readonly',
      },
      // Auditoría 2026-08 (hallazgo P1-6). Sin este parser, ESLint intentaba
      // leer .ts/.tsx con el parser de JavaScript y se atragantaba en la primera
      // anotación de tipo: 304 de 343 ficheros fallaban con "Parsing error", así
      // que react-hooks, jsx-a11y y no-unused-vars no se aplicaban al 89% del
      // frontend. Y el informe de accesibilidad cantaba "0 findings" sobre esos
      // mismos ficheros ilegibles — un verde falso, peor que no tener el control.
      parser: tsParser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
        // Sin `project`: el análisis con tipos multiplica el tiempo de ejecución
        // y las reglas que se usan aquí (react-hooks, jsx-a11y, no-unused-vars)
        // no lo necesitan. El chequeo de tipos ya lo hace `tsc`.
      },
    },
    settings: {
      react: { version: 'detect' },
    },
    rules: {
      ...reactHooks.configs.recommended.rules,

      // Security/correctness — keep as errors
      'no-debugger': 'error',
      'react-hooks/rules-of-hooks': 'error',
      'react/jsx-key': 'error',

      // ── XSS / supply-chain security rules ──
      // Disallow javascript: URLs in href/src props (XSS vector)
      'no-script-url': 'error',
      // Disallow eval() and similar dynamic code execution
      'no-eval': 'error',
      'no-implied-eval': 'error',
      // Warn when new Function() is used (eval equivalent)
      'no-new-func': 'error',
      // Catch dangerouslySetInnerHTML usage — requires manual review
      'react/no-danger': 'warn',

      // React 19 Compiler rules — not applicable to React 18; disable
      'react-hooks/static-components': 'off',
      'react-hooks/purity': 'off',
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/refs': 'off',
      'react-hooks/preserve-manual-memoization': 'off',

      // Downgrade noisy stylistic rules inherited from recommended to warn
      'react/no-unescaped-entities': 'off',
      'react/display-name': 'off',
      'react/prop-types': 'off',
      'react-hooks/exhaustive-deps': 'error',
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' }],
      'no-undef': 'off',
      'no-console': 'off',
      'no-empty': 'off',

      // Accessibility baseline (WCAG-focused)
      'jsx-a11y/aria-props': 'warn',
      'jsx-a11y/aria-proptypes': 'warn',
      'jsx-a11y/aria-unsupported-elements': 'warn',
      'jsx-a11y/role-has-required-aria-props': 'warn',
      'jsx-a11y/role-supports-aria-props': 'warn',
      'jsx-a11y/alt-text': 'warn',
      'jsx-a11y/control-has-associated-label': 'warn',
      'jsx-a11y/label-has-associated-control': 'warn',
      'jsx-a11y/click-events-have-key-events': 'error',
      'jsx-a11y/no-static-element-interactions': 'error',

      // ── Design system enforcement ──
      // Restringir colores hex literales en código nuevo. Los tokens viven en
      // index.css (--accent, --surface-*) y en constants/theme.js (CHART_COLORS,
      // COLOR.*). Si necesitas un color para chart, usa CHART_COLORS_EXTENDED.
      'no-restricted-syntax': ['warn', ...RESTRICCIONES_DE_ESTILO, ...FETCH_DIRECTO],

      // Auditoria 2026-11 (#29): nada de dialogos nativos. Bloquean el hilo, no
      // siguen el tema ni el idioma y no se pueden probar. Usa
      // useConfirm().confirmar / pedirTexto (context/ConfirmContext) o useToast.
      'no-restricted-globals': ['error', ...DIALOGOS_NATIVOS.map(name => ({ name, message: MENSAJE_DIALOGOS }))],
      'no-restricted-properties': ['error',
        ...['window', 'globalThis', 'self'].flatMap(object =>
          DIALOGOS_NATIVOS.map(property => ({ object, property, message: MENSAJE_DIALOGOS }))),
      ],
    },
  },
  {
    // El cliente API es el unico sitio donde se permite fetch directo.
    files: ['src/services/api/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-syntax': ['warn', ...RESTRICCIONES_DE_ESTILO],
    },
  },
  {
    // Reglas específicas de TypeScript. `no-unused-vars` de ESLint base no
    // entiende TS: marca como no usados los identificadores que sólo aparecen en
    // posición de tipo (interfaces, genéricos, `import type`). La versión del
    // plugin sí, así que en .ts/.tsx se apaga la base y se usa aquélla.
    files: ['src/**/*.{ts,tsx}'],
    plugins: { '@typescript-eslint': tsPlugin },
    rules: {
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': ['error', {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_',
        caughtErrorsIgnorePattern: '^_',
        ignoreRestSiblings: true,
      }],
      // `no-redeclare` da falsos positivos con las sobrecargas y con la fusión
      // de declaraciones de TypeScript.
      'no-redeclare': 'off',
      // Los enums y namespaces de TS se declaran antes de usarse en runtime.
      'no-use-before-define': 'off',
      // Auditoria 2026-11 (#25): 0 `any` explicitos en src (medido con el parser
      // de TS). Tipa con interfaces del backend (app/schemas, serializadores) o
      // con `unknown` + estrechamiento donde la forma sea de verdad dinamica.
      '@typescript-eslint/no-explicit-any': 'error',
    },
  },
  {
    // Ficheros de declaración. Un parámetro genérico sin usar es legítimo aquí:
    // en una ampliación de módulo la firma tiene que coincidir con la original
    // (p. ej. `interface HTMLAttributes<T>` de React), aunque `T` no aparezca en
    // el cuerpo que se está sobrescribiendo.
    files: ['src/**/*.d.ts'],
    rules: {
      '@typescript-eslint/no-unused-vars': 'off',
    },
  },
  {
    files: ['src/**/__tests__/**/*.{js,jsx,ts,tsx}', 'src/**/*.test.{js,jsx,ts,tsx}'],
    languageOptions: {
      globals: {
        vi: 'readonly',
        describe: 'readonly',
        it: 'readonly',
        test: 'readonly',
        expect: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
      },
    },
    rules: {
      'no-unused-vars': 'off',
    },
  },
  {
    files: [
      'src/pages/DeliverablesPage.jsx',
      'src/pages/EVMPage.jsx',
      'src/pages/EnterprisePage.jsx',
      'src/pages/EpicsPage.jsx',
      'src/pages/InternalCommentsPage.jsx',
      'src/pages/MeetingsAIPage.jsx',
      'src/pages/NotificationsPage.jsx',
      'src/pages/OrganizationsPage.jsx',
      'src/pages/OrgChartPage.jsx',
      'src/pages/ProfitabilityPage.jsx',
      'src/pages/RACIPage.jsx',
      'src/pages/RateCardsPage.jsx',
      'src/pages/ReportsPage.jsx',
      'src/pages/ClientPortalPage.jsx',
    ],
    rules: {
      'jsx-a11y/click-events-have-key-events': 'error',
      'jsx-a11y/no-static-element-interactions': 'error',
    },
  },
  {
    ignores: ['dist/**', 'node_modules/**', 'public/**', 'src/i18n/langs/*.mjs'],
  },
]
