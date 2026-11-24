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

// 23-11-2026: botón de solo icono hecho a mano → IconButton (variante="caja" en tarjetas y filas).
const LUCIDE = "import { Pencil, Trash2, ChevronUp, ChevronDown } from 'lucide-react'\n"
tester.run('sin-boton-de-icono-propio', regla('sin-boton-de-icono-propio'), {
  valid: [
    { code: LUCIDE + 'const a = <IconButton variante="caja" ariaLabel="Editar"><Pencil size={16} /></IconButton>' },
    // Icono con texto: es un Button normal.
    { code: LUCIDE + 'const a = <Button icon={<Pencil />}>Editar</Button>' },
    { code: LUCIDE + 'const a = <Pulsable className="x"><Pencil /> Editar</Pulsable>' },
    // Un icono que no es de lucide no cuenta.
    { code: 'const a = <Pulsable><MiIcono /></Pulsable>' },
    // Excepción justificada en la línea (el aviso cae en la línea de la etiqueta de
    // apertura, donde va el comentario). El RuleTester registra la regla como
    // `rule-to-test/<nombre>`, no como `contec/<nombre>`: con el prefijo de la app la
    // directiva apunta a una regla que aquí no existe y ESLint da «Definition for rule
    // not found» (fallo del caso, no de la regla). En la app vale `contec/…`; lo
    // comprueba `eslint src` con los Pulsable exceptuados (CallPage, GanttChart…).
    { code: LUCIDE + 'const a = <Pulsable /* eslint-disable-line rule-to-test/sin-boton-de-icono-propio -- excepción: chip */><Trash2 /></Pulsable>' },
  ],
  invalid: [
    { code: LUCIDE + 'const a = <Pulsable aria-label="Editar" className="x-icon-btn"><Pencil size={14} /></Pulsable>', errors: [{ messageId: 'prohibido' }] },
    { code: LUCIDE + 'const a = <button type="button">\n  <Trash2 />\n</button>', errors: 1 },
    { code: LUCIDE + 'const a = <Pulsable>{abierto ? <ChevronUp /> : <ChevronDown />}</Pulsable>', errors: 1 },
    { code: LUCIDE + 'const a = <Button size="sm" variant="ghost" aria-label="Borrar"><Trash2 /></Button>', errors: 1 },
    // Button sin texto, solo con `icon`.
    { code: 'const a = <Button size="xs" variant="ghost" icon={<X />} title="Borrar" />', errors: 1 },
  ],
})
