// Pasada de diseño 16-11-2026 (pantallas M–Z, service desk y /sd/*): los
// iconos son de lucide y nunca emojis, y las acciones no llevan "+ " en el
// texto (el botón ya lleva el icono Plus). Este test falla si vuelven emojis
// al código de estas pantallas o a los textos de operador que usan (es/en/zh).
// Los comentarios del código no cuentan: ahí se explica qué había antes.
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import es from '../i18n/langs/es.mjs'
import en from '../i18n/langs/en.mjs'
import zh from '../i18n/langs/zh.mjs'

const raiz = resolve(__dirname, '..')
const leer = (p: string) => readFileSync(resolve(raiz, p), 'utf8')
const EMOJI = /\p{Extended_Pictographic}/u

const PAGINAS = [
  'MeetingsAI', 'MFA', 'MilestoneBilling', 'MisEquipos', 'NexusAgent', 'NPS', 'OKRs', 'Oracle',
  'OrgChart', 'Organizations', 'PerformanceReviews', 'Pipeline', 'Portfolio', 'CarteraIntake',
  'Predictions', 'Profitability', 'ProjectPermissions', 'ProjectTemplates', 'Projects',
  'ProjectsDashboard', 'PublicForms', 'RACI', 'RateCards', 'ReportBuilder', 'Reports',
  'ResourceForecast', 'ResourceScheduler', 'Resources', 'PlanificacionDeRecursos', 'Revenue',
  'RiskScores', 'Risks', 'Scenarios', 'SemanticEngine', 'Settings', 'Politicas', 'Workflows',
  'Skills', 'SLACalendars', 'SprintCharts', 'SprintPlanning', 'Sprints', 'Subcontractors',
  'SupportDashboard', 'Tasks', 'TeamDashboard', 'Time', 'Timer', 'Training', 'UAT', 'UserCosts',
  'WebhookLog', 'Wiki', 'WorkDashboard', 'ServiceDesk',
].map(n => `pages/${n}Page.tsx`)

const tsxDe = (dir: string) => readdirSync(resolve(raiz, dir)).filter(f => f.endsWith('.tsx')).map(f => `${dir}/${f}`)

const FICHEROS = [
  ...PAGINAS,
  'pages/SettingsPageSections.tsx',
  ...tsxDe('pages/settings-sections'),
  ...tsxDe('pages/service-desk'),
  ...tsxDe('components/servicedesk'),
  'components/dashboard/DashKit.tsx',
]

/** El código sin comentarios (bloque y de línea; respeta "http://" en cadenas). */
function sinComentarios(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`])\/\/.*$/gm, '$1')
}

type Dic = Record<string, unknown>
const valor = (d: Dic, clave: string): unknown =>
  clave.split('.').reduce<unknown>((o, p) => (o && typeof o === 'object' ? (o as Dic)[p] : undefined), d)

describe('Pasada de diseño M–Z: sin emojis', () => {
  it.each(FICHEROS)('%s no pinta emojis', f => {
    const codigo = sinComentarios(leer(f))
    const linea = codigo.split('\n').findIndex(l => EMOJI.test(l))
    expect(linea, `${f}:${linea + 1}`).toBe(-1)
  })

  it.each(FICHEROS)('%s: sus textos no llevan emojis ni "+ " en es/en/zh', f => {
    const claves = new Set(Array.from(leer(f).matchAll(/\bt\(\s*['"]([a-z0-9_/]+\.[A-Za-z0-9_.]+)['"]/g), m => m[1]))
    const malos: string[] = []
    for (const [idioma, d] of [['es', es], ['en', en], ['zh', zh]] as Array<[string, Dic]>) {
      for (const clave of claves) {
        const v = valor(d, clave)
        if (typeof v === 'string' && (EMOJI.test(v) || v.startsWith('+ '))) malos.push(`${idioma}:${clave}=${v}`)
      }
    }
    expect(malos).toEqual([])
  })
})
