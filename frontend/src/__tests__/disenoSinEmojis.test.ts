// @vitest-environment node
//
// Pasada de diseño 16-11-2026: los iconos de la interfaz son lucide, nunca
// emojis. Este test falla si vuelve un emoji al código de las pantallas de la
// pasada (rutas "/" y A–L, /chat, el editor IA y el kit común) o a los textos
// de operador que esas pantallas leen de los diccionarios es/en/zh.
//
// Se ignoran los comentarios. Excepción explícita: el selector de reacciones
// del chat, donde el emoji ES el contenido que el usuario inserta.
import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC = path.resolve(__dirname, '..')
const PICTOGRAMA = /\p{Extended_Pictographic}/u

/** Ficheros y carpetas (recursivas) de la pasada. */
const ALCANCE = [
  'components/ui',
  'components/layout/PageHeader.tsx', 'components/layout/PageShell.tsx', 'components/layout/GlobalChatPanel.tsx',
  'components/AIInlineEditor.tsx', 'components/GanttChart.tsx',
  'components/alm', 'components/aprobaciones', 'components/presupuestos', 'components/gastos',
  'components/invoices', 'components/lecciones', 'components/ausencias', 'components/cmdb', 'components/bi',
  'pages/alm', 'pages/bpm', 'pages/clients',
  // Troceado de ChatPage, ApprovalsPage y DocumentsPage (23-11-2026, auditoría M12).
  'pages/chat', 'pages/aprobaciones', 'pages/documentos',
  ...[
    'AbsencesPage', 'AgentDashboardPage', 'AIHubPage', 'AlertsPage', 'ALMPage', 'ALMAltasBajasPage',
    'ApprovalsPage', 'AprobacionPorCorreoPage', 'PreguntarALaEmpresaPage', 'AutomationsPage', 'BPMPage',
    'BudgetsPage', 'CalendarPage', 'CapacityPage', 'ChangelogPage', 'ChangesPage', 'ChatPage', 'ClientsPage',
    'CMDBPage', 'ContractsPage', 'ContractsAIPage', 'CumulativeFlowPage', 'CustomFieldsPage',
    'DataExplorerPage', 'DataGovernancePage', 'DataPlatformPage', 'DeliverablesPage', 'DependenciesPage',
    'DeveloperPortalPage', 'DocumentsPage', 'EnterprisePage', 'EpicGanttPage', 'EpicsPage', 'ESignPage',
    'EVMPage', 'BIPage', 'BIProjectDetailPage', 'ExpensesPage', 'ExportsPage', 'FinanceDashboardPage',
    'GanttPage', 'GitPage', 'GovernancePage', 'GrcPage', 'ImportPage', 'ImputarPage', 'InboxPage',
    'IntakeFormPage', 'InvoicesPage', 'IssueTypesPage', 'JiraIntegrationPage', 'LeccionesPage',
  ].map(n => `pages/${n}.tsx`),
]

/** Líneas con emoji permitidas: el emoji es contenido, no un icono. */
const PERMITIDAS: Array<[string, RegExp]> = [
  ['pages/chat/Mensajes.tsx', /\['👍'/],
  // 24-11-2026: el selector de emojis del chat (interno y portal) ofrece emojis: son su contenido.
  ['components/ui/SelectorDeEmoji.tsx', /^\s*(export const REACCIONES_RAPIDAS = \[|'\S)/],
]

function* ficheros(rel: string): Generator<string> {
  const p = path.join(SRC, rel)
  if (!fs.existsSync(p)) return
  if (fs.statSync(p).isDirectory()) {
    for (const e of fs.readdirSync(p)) {
      if (e === '__tests__') continue
      yield* ficheros(path.join(rel, e))
    }
  } else if (/\.tsx?$/.test(rel) && !/\.test\./.test(rel)) {
    yield rel.split(path.sep).join('/')
  }
}

/** El código sin comentarios (aproximado: bloques y `//` tras espacio o inicio). */
function sinComentarios(codigo: string): string[] {
  return codigo
    .replace(/\/\*[\s\S]*?\*\//g, m => m.replace(/[^\n]/g, ''))
    .split('\n')
    .map(l => l.replace(/(^|\s)\/\/.*$/, ''))
}

const TODOS = [...new Set(ALCANCE.flatMap(r => [...ficheros(r)]))]

describe('pasada de diseño: sin emojis', { timeout: 60_000 }, () => {
  it('el alcance existe (si se renombra una página, actualiza la lista)', () => {
    expect(TODOS.length).toBeGreaterThan(80)
  })

  it('no hay emojis en el código de las pantallas ni del kit común', () => {
    const encontrados: string[] = []
    for (const rel of TODOS) {
      sinComentarios(fs.readFileSync(path.join(SRC, rel), 'utf8')).forEach((l, i) => {
        if (!PICTOGRAMA.test(l)) return
        if (PERMITIDAS.some(([f, re]) => f === rel && re.test(l))) return
        encontrados.push(`${rel}:${i + 1}: ${l.trim().slice(0, 100)}`)
      })
    }
    expect(encontrados).toEqual([])
  })

  it('los textos de operador que usan esas pantallas no llevan emojis (es/en/zh)', async () => {
    // Claves literales t('ns.clave') / traducir('ns.clave') de los ficheros del alcance.
    const claves = new Set<string>()
    const RE_CLAVE = /\b(?:t|tr|ta|traducir|translate)\(\s*['"`]([a-z0-9_]+(?:\.[A-Za-z0-9_]+)+)['"`]/g
    for (const rel of TODOS) {
      for (const m of fs.readFileSync(path.join(SRC, rel), 'utf8').matchAll(RE_CLAVE)) claves.add(m[1])
    }
    expect(claves.size).toBeGreaterThan(500)

    const malos: string[] = []
    for (const idioma of ['es', 'en', 'zh']) {
      const url = pathToFileURL(path.join(SRC, 'i18n', 'langs', `${idioma}.mjs`)).href
      const dic = (await import(/* @vite-ignore */ url)).default as Record<string, unknown>
      for (const clave of claves) {
        let v: unknown = dic
        for (const parte of clave.split('.')) v = v && typeof v === 'object' ? (v as Record<string, unknown>)[parte] : undefined
        if (typeof v === 'string' && PICTOGRAMA.test(v)) malos.push(`${idioma}:${clave} = ${v}`)
      }
    }
    expect(malos).toEqual([])
  })
})
