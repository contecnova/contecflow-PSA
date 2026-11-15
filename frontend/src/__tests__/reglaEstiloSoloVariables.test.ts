// @vitest-environment node
import { RuleTester } from 'eslint'
import tsParser from '@typescript-eslint/parser'
import regla from '../../scripts/eslint/solo-variables-css-en-style.mjs'

// Regla `contec/solo-variables-css-en-style` (eslint.config.js, nivel warn):
// `style` solo lleva propiedades CSS personalizadas.
const tester = new RuleTester({
  languageOptions: { parser: tsParser, parserOptions: { ecmaFeatures: { jsx: true } } },
})

tester.run('solo-variables-css-en-style', regla as never, {
  valid: [
    { code: `const a = <div style={{ '--pct': \`\${n}%\` }} />` },
    { code: `const a = <div style={{ '--a': 1, '--b': x } as CSSProperties} />` },
    { code: `const a = <div style={{ ['--flujo-color' as string]: color }} />` },
    { code: 'const a = <div style={estilo} />' },
    // Lo que pasa quien llama no se puede juzgar.
    { code: `const a = <div style={{ ...style, '--a': 1 }} />` },
    { code: `const a = <div style={varCss('--x', 1)} />` },
    { code: 'const a = <div style={colorVar(c)} />' },
    { code: `const a = <div style={{ ...varCss('--h', 1) }} />` },
    { code: 'const a = <div className="x" />' },
    // Los objetos de los gráficos (contentStyle...) no son `style`.
    { code: `const a = <Tooltip contentStyle={{ background: 'var(--surface-2)' }} />` },
    // Componente de terceros permitido por defecto.
    { code: `const a = <Cell style={{ fill: color }} />` },
    { code: `const a = <Foo style={{ color: 'red' }} />`, options: [{ componentesPermitidos: ['Foo'] }] },
  ],
  invalid: [
    { code: `const a = <input style={validation.inputStyle(base, 'x')} />`, errors: [{ messageId: 'cruda' }] },
    { code: `const a = <button style={btn(active)} />`, errors: [{ messageId: 'cruda' }] },
    { code: `const a = <button style={colorVar(c)} />`, options: [{ funcionesDeVariables: [] }], errors: [{ messageId: 'cruda' }] },
    { code: `const a = <input style={obj.inputStyle(base, 'x')} />`, errors: [{ messageId: 'cruda' }] },
    { code: `const a = <div style={{ color: 'red' }} />`, errors: [{ messageId: 'cruda' }] },
    { code: `const a = <div style={{ '--a': 1, width: 10 }} />`, errors: [{ messageId: 'cruda' }] },
    { code: `const a = <div style={{ width: 10 } as CSSProperties} />`, errors: [{ messageId: 'cruda' }] },
    { code: `const a = <div style={{ ...base, color: 'red' }} />`, errors: [{ messageId: 'cruda' }] },
    { code: `const a = <div style={on ? { color: 'red' } : undefined} />`, errors: [{ messageId: 'cruda' }] },
    { code: `const a = <div style={on && { opacity: 0.5 }} />`, errors: [{ messageId: 'cruda' }] },
    { code: `const a = <Button style={{ marginLeft: 8 }} />`, errors: [{ messageId: 'cruda' }] },
    { code: `const a = <Cell style={{ fill: color }} />`, options: [{ componentesPermitidos: [] }], errors: [{ messageId: 'cruda' }] },
  ],
})
