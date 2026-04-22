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
    files: ['src/**/*.{js,jsx}'],
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
      'react/no-unescaped-entities': 'warn',
      'react/display-name': 'warn',
      'react/prop-types': 'off',
      'react-hooks/exhaustive-deps': 'warn',
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      'no-undef': 'warn',
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-empty': 'warn',

      // Accessibility baseline (WCAG-focused)
      'jsx-a11y/aria-props': 'warn',
      'jsx-a11y/aria-proptypes': 'warn',
      'jsx-a11y/aria-unsupported-elements': 'warn',
      'jsx-a11y/role-has-required-aria-props': 'warn',
      'jsx-a11y/role-supports-aria-props': 'warn',
      'jsx-a11y/alt-text': 'warn',
      'jsx-a11y/control-has-associated-label': 'warn',
      'jsx-a11y/label-has-associated-control': ['warn', { assert: 'either' }],
      'jsx-a11y/click-events-have-key-events': 'warn',
      'jsx-a11y/no-static-element-interactions': 'warn',
    },
  },
  {
    ignores: ['dist/**', 'node_modules/**', 'public/**'],
  },
]
