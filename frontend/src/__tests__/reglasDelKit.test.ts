// @vitest-environment node
import { RuleTester } from 'eslint'
import tsParser from '@typescript-eslint/parser'
import { reglasDelKit } from '../../scripts/eslint/kit-sin-marcado-propio.mjs'

// Reglas `contec/sin-*` de la migración al kit (eslint.config.js, nivel error
// fuera de components/ui, con el cupo por fichero de kit-pendientes.json).
const tester = new RuleTester({
  languageOptions: { parser: tsParser, parserOptions: { ecmaFeatures: { jsx: true } } },
})
const regla = (n: keyof typeof reglasDelKit) => reglasDelKit[n] as never
const F = '/proyecto/src/pages/X.tsx'
const cupo = (n: number) => [{ raiz: '/proyecto', pendientes: { 'src/pages/X.tsx': n } }]

tester.run('sin-boton-nativo', regla('sin-boton-nativo'), {
  valid: [
    { code: 'const a = <Button onClick={f}>Guardar</Button>' },
    { code: 'const a = <IconButton ariaLabel="x"><X /></IconButton>' },
    // Dentro del cupo del fichero.
    { code: 'const a = <><button /><button /></>', filename: F, options: cupo(2) },
  ],
  invalid: [
    { code: 'const a = <button type="button">x</button>', errors: [{ messageId: 'prohibido' }] },
    // Por encima del cupo se marcan todos, con el aviso de que la lista solo encoge.
    { code: 'const a = <><button /><button /><button /></>', filename: F, options: cupo(2), errors: 3 },
    // El cupo es de otro fichero.
    { code: 'const a = <button />', filename: '/proyecto/src/pages/Y.tsx', options: cupo(5), errors: [{ messageId: 'prohibido' }] },
  ],
})

tester.run('sin-tabla-propia', regla('sin-tabla-propia'), {
  valid: [{ code: 'const a = <Tabla columnas={c} filas={f} />' }, { code: 'const a = <TablaSimple><tbody /></TablaSimple>' }],
  invalid: [{ code: 'const a = <table className="contecflow-table" />', errors: 1 }],
})

tester.run('sin-select-nativo', regla('sin-select-nativo'), {
  valid: [{ code: 'const a = <Select suelto value={v} onChange={f} />' }],
  invalid: [{ code: 'const a = <select className="ds-input"><option /></select>', errors: 1 }],
})

tester.run('sin-casilla-suelta', regla('sin-casilla-suelta'), {
  valid: [
    { code: 'const a = <input type="text" />' },
    { code: 'const a = <input />' },
    { code: 'const a = <Checkbox checked={c} label="x" />' },
  ],
  invalid: [
    { code: 'const a = <input type="checkbox" />', errors: 1 },
    { code: `const a = <input type={'radio'} />`, errors: 1 },
    { code: `const a = <input type={multi ? 'checkbox' : 'radio'} />`, errors: 1 },
  ],
})

tester.run('sin-fieldset-propio', regla('sin-fieldset-propio'), {
  valid: [
    { code: 'const a = <fieldset className="ds-grupo-opciones"><legend /></fieldset>' },
    { code: 'const a = <fieldset className={`ds-grupo-opciones ${x}`} />' },
  ],
  invalid: [
    { code: 'const a = <fieldset />', errors: 1 },
    { code: 'const a = <fieldset className="mi-grupo" />', errors: 1 },
  ],
})
