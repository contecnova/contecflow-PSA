// Clientes internos (22-11-2026): rutas y capacidades (`/internal-clients` con
// `interno.gestionar`, `/mi-departamento` con `interno.portal`), menú, sección
// de Configuración única con `interno.cargos`, textos en es/en/zh, kit de diseño
// (Input/Select, sin marcado propio), tipo `internal_charge` en la bandeja y
// lógica pura (acciones de un cargo, avisos, carga útil de la ficha).
// Ver docs/CLIENTES_INTERNOS.md §9-§12.
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { rutaDeclarada, puedeAbrir } from '../permisos/navegacion'
import { CAPACIDADES } from '../permisos/capacidades'
import { SECCIONES_DE_AJUSTES } from '../pages/settings/catalogoDeAjustes'
import es from '../i18n/langs/es.mjs'
import en from '../i18n/langs/en.mjs'
import zh from '../i18n/langs/zh.mjs'
import {
  DESTINO_DE_AVISO, accionesDeCargo, datosInternos, destinoDeAviso, formInternoDe, mesActual, sinCamposInternos,
} from '../pages/internos/logica'

const src = (ruta: string) => readFileSync(resolve(__dirname, '..', ruta), 'utf8')
type Dic = Record<string, Record<string, string>>
const IDIOMAS: [string, Dic][] = [['es', es as unknown as Dic], ['en', en as unknown as Dic], ['zh', zh as unknown as Dic]]

const PANTALLAS = readdirSync(resolve(__dirname, '../pages/internos'))
  .filter(f => f.endsWith('.tsx'))
  .map(f => `pages/internos/${f}`)
  .concat(['pages/clients/CamposInternos.tsx'])

describe('rutas, capacidades y menú', () => {
  it('las tres capacidades están declaradas', () => {
    for (const c of ['interno.portal', 'interno.gestionar', 'interno.cargos']) expect(CAPACIDADES).toContain(c)
  })

  it('/internal-clients se abre solo con interno.gestionar', () => {
    expect(rutaDeclarada('/internal-clients')?.capacidad).toBe('interno.gestionar')
    expect(puedeAbrir('/internal-clients', c => c === 'interno.gestionar')).toBe(true)
    expect(puedeAbrir('/internal-clients', c => c === 'interno.portal')).toBe(false)
    expect(puedeAbrir('/internal-clients', c => c === 'finanzas.ver')).toBe(false)
  })

  it('/mi-departamento se abre solo con interno.portal', () => {
    expect(rutaDeclarada('/mi-departamento')?.capacidad).toBe('interno.portal')
    expect(puedeAbrir('/mi-departamento', c => c === 'interno.portal')).toBe(true)
    expect(puedeAbrir('/mi-departamento', c => c === 'interno.gestionar')).toBe(false)
  })

  it('las dos pantallas están en App y en el menú', () => {
    const app = src('App.tsx')
    expect(app).toMatch(/path="\/internal-clients"/)
    expect(app).toMatch(/path="\/mi-departamento"/)
    const layout = src('components/layout/Layout.tsx')
    expect(layout).toMatch(/to: '\/internal-clients'/)
    expect(layout).toMatch(/to: '\/mi-departamento'/)
  })

  it('las pantallas preguntan por capacidades, nunca por roles', () => {
    for (const f of PANTALLAS) {
      const s = src(f)
      expect(s, f).not.toMatch(/hasRole\(|\.role\s*===\s*'(admin|pm)'/)
    }
    expect(src('pages/internos/PestanaCargos.tsx')).toMatch(/usePermiso\('interno\.cargos'\)/)
  })
})

describe('configuración única', () => {
  it('sección clientes-internos en Finanzas con interno.cargos', () => {
    const s = SECCIONES_DE_AJUSTES.find(x => x.id === 'clientes-internos')
    expect(s?.grupo).toBe('finanzas')
    expect(s?.capacidad).toBe('interno.cargos')
  })

  it('el módulo no lleva botón «Configurar»', () => {
    for (const f of PANTALLAS) expect(src(f), f).not.toMatch(/ajustes\.configurar/)
  })

  it('los avisos enlazan a donde se arregla', () => {
    for (const a of ['interno_sin_responsable', 'interno_sin_presupuesto', 'interno_sin_tarifa', 'interno_sin_cuenta_erp', 'interno_sin_estructura']) {
      expect(DESTINO_DE_AVISO[a]).toMatch(/^\//)
    }
    expect(destinoDeAviso('interno_sin_tarifa')).toBe('/settings/rates')
    expect(destinoDeAviso('desconocido')).toBe('/clients')
  })
})

describe('textos en es, en y zh', () => {
  it('mismas claves de internos en los tres idiomas y sin vacíos', () => {
    const claves = Object.keys(IDIOMAS[0][1].internos).sort()
    expect(claves.length).toBeGreaterThan(100)
    for (const [lang, d] of IDIOMAS) {
      expect(Object.keys(d.internos).sort(), lang).toEqual(claves)
      for (const k of claves) expect(d.internos[k], `${lang}.internos.${k}`).toBeTruthy()
    }
  })

  it('cada clave internos.* usada en las pantallas existe', () => {
    const usadas = new Set<string>()
    for (const f of [...PANTALLAS, 'pages/ClientsPage.tsx']) {
      for (const m of src(f).matchAll(/'internos\.([a-z_]+)'/g)) usadas.add(m[1])
    }
    for (const [lang, d] of IDIOMAS) for (const k of usadas) expect(d.internos[k], `${lang}.internos.${k}`).toBeTruthy()
  })

  it('menú, bandeja y ajustes traducidos', () => {
    for (const [lang, d] of IDIOMAS) {
      expect(d.nav.internal_clients, lang).toBeTruthy()
      expect(d.nav.mi_departamento, lang).toBeTruthy()
      expect(d.approvals.entity_internal_charge, lang).toBeTruthy()
      expect(d.ajustes.s_clientes_internos, lang).toBeTruthy()
      expect(d.ajustes.s_clientes_internos_d, lang).toBeTruthy()
    }
  })
})

describe('kit de diseño', () => {
  it('sin <input>/<select> a mano: Input y Select del kit', () => {
    for (const f of PANTALLAS) {
      const s = src(f)
      expect(s, f).not.toMatch(/<input[\s>]/)
      expect(s, f).not.toMatch(/<select[\s>]/)
      expect(s, f).not.toMatch(/style=\{\{/)
    }
    expect(src('pages/clients/CamposInternos.tsx')).toMatch(/import \{ Input, Select \} from '\.\.\/\.\.\/components\/ui'/)
  })
})

describe('bandeja de aprobaciones y ficha del cliente', () => {
  it('la bandeja conoce el tipo internal_charge', () => {
    expect(src('pages/ApprovalsPage.tsx')).toMatch(/internal_charge:/)
  })

  it('la lista de clientes filtra por kind y el formulario lleva los campos internos', () => {
    const s = src('pages/ClientsPage.tsx')
    expect(s).toMatch(/kind: kindF \|\| undefined/)
    expect(s).toMatch(/<CamposInternos/)
  })
})

describe('lógica pura', () => {
  it('acciones de un cargo según estado, interno.cargos y can_approve', () => {
    expect(accionesDeCargo('borrador', true, false)).toEqual(['issue', 'cancel'])
    expect(accionesDeCargo('borrador', false, false)).toEqual([])
    expect(accionesDeCargo('por_aprobar', false, true)).toEqual(['approve', 'reject'])
    expect(accionesDeCargo('por_aprobar', true, false)).toEqual(['cancel'])
    expect(accionesDeCargo('emitido', true, true)).toEqual(['cancel'])
    expect(accionesDeCargo('exportado', true, true)).toEqual([])
    expect(accionesDeCargo('anulado', true, true)).toEqual([])
  })

  it('carga útil de la ficha: externo solo kind; interno con nulos y margen solo en intercompañía', () => {
    expect(datosInternos({ kind: 'externo', finance_mode: 'chargeback' })).toEqual({ kind: 'externo' })
    const d = datosInternos({
      kind: 'interno', internal_type: 'departamento', department_id: 'd1', area_id: '', cost_center_id: '', group_organization_id: '',
      business_owner_id: 'u1', finance_mode: 'chargeback', cost_method: 'horas_coste', internal_rate_table_id: 'r1', transfer_markup_pct: '5', erp_account: ' 629000 ',
    })
    expect(d).toMatchObject({ kind: 'interno', department_id: 'd1', area_id: null, transfer_markup_pct: null, internal_rate_table_id: null, erp_account: '629000' })
    expect(datosInternos({ kind: 'interno', finance_mode: 'intercompania', transfer_markup_pct: '7,5' }).transfer_markup_pct).toBe(7.5)
  })

  it('formInternoDe y sinCamposInternos', () => {
    expect(formInternoDe({ kind: 'interno', transfer_markup_pct: 3 }).transfer_markup_pct).toBe('3')
    expect(formInternoDe({}).kind).toBe('externo')
    expect(sinCamposInternos({ name: 'X', kind: 'interno', erp_account: '1' })).toEqual({ name: 'X' })
  })

  it('mes actual YYYY-MM', () => {
    expect(mesActual(new Date(2026, 10, 22))).toBe('2026-11')
    expect(mesActual(new Date(2026, 0, 3))).toBe('2026-01')
  })
})

describe('clientes internos: filtro externos/internos, precio del catálogo y cuenta de TI', () => {
  const dicc = { es, en, zh } as unknown as Record<string, Record<string, Record<string, string>>>

  it('el filtro por tipo de cliente está en cartera, rentabilidad, salud de proyectos y panel de cartera', () => {
    const filtro = src('components/FiltroTipoDeCliente.tsx')
    expect(filtro).toMatch(/client_kind/)
    expect(filtro).toMatch(/from '\.\/ui'/)
    for (const pagina of ['pages/CarteraIntakePage.tsx', 'pages/ProfitabilityPage.tsx', 'pages/ProjectsDashboardPage.tsx', 'pages/PortfolioPage.tsx']) {
      expect(src(pagina)).toMatch(/FiltroTipoDeCliente/)
    }
    expect(src('services/api/planificacion.ts')).toMatch(/client_kind: clientKind/)
  })

  it('el formulario del catálogo pide el precio interno con el Input del kit', () => {
    const form = src('pages/service-desk/ConfigTab.tsx')
    expect(form).toMatch(/<Input[^>]*label=\{t\('sd_cfg\.svc_internal_price'\)\}/)
    expect(form).toMatch(/internal_price: form\.internal_price\.trim\(\) === '' \? null/)
  })

  it('la cuenta de TI se edita en Configuración → Clientes internos y no hay valor fijo', () => {
    const cfg = src('pages/internos/ConfigClientesInternos.tsx')
    expect(cfg).toMatch(/INTERNAL_IT_ERP_ACCOUNT/)
    expect(cfg).toMatch(/settingsApi\.setRuntime/)
    expect(DESTINO_DE_AVISO.interno_sin_cuenta_ti).toBe('/settings/clientes-internos')
  })

  it('textos nuevos en es/en/zh', () => {
    for (const l of ['es', 'en', 'zh']) {
      const d = dicc[l]
      for (const k of ['filtro_tipo_cliente', 'cuenta_ti', 'cuenta_ti_d', 'cuenta_ti_vacia', 'aviso_interno_sin_cuenta_ti']) {
        expect(d.internos[k], `${l}.internos.${k}`).toBeTruthy()
      }
      expect(d.sd_cfg.svc_internal_price, `${l}.sd_cfg.svc_internal_price`).toBeTruthy()
      expect(d.ajuste_clave.INTERNAL_IT_ERP_ACCOUNT, `${l}.ajuste_clave.INTERNAL_IT_ERP_ACCOUNT`).toBeTruthy()
    }
  })
})
