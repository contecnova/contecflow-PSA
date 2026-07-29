import js from '@eslint/js'
import reactPlugin from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import jsxA11y from 'eslint-plugin-jsx-a11y'

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
        alert: 'readonly',
        confirm: 'readonly',
        prompt: 'readonly',
      },
      parserOptions: {
        ecmaFeatures: { jsx: true },
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
      'no-restricted-syntax': ['warn',
        {
          selector: "Literal[value=/^#(00d4ff|0ea5e9|7c3aed)/i]",
          message: 'Hex literales de marca obsoletos (#00d4ff/#0ea5e9/#7c3aed). Usa var(--accent), var(--purple), o COLOR.* desde constants/theme.js.',
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
      ],
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
