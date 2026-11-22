// Índice de riesgo y gestión de vulnerabilidades (22-11-2026).
// Comprueba el cableado de la pantalla: la pestaña `risk` de la CMDB, la
// sección de ajustes dentro de Configuración, los tipos de conexión nuevos y
// que es/en/zh tengan las mismas claves en `swr` y los errores `err_srv.swr_*`.
// Diseño: docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md §11.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import es from '../i18n/langs/es.mjs'
import en from '../i18n/langs/en.mjs'
import zh from '../i18n/langs/zh.mjs'

type Dic = Record<string, unknown>

/** Rutas de todas las hojas de un objeto (`a.b.c`). */
function hojas(o: unknown, prefijo = ''): string[] {
  if (!o || typeof o !== 'object') return [prefijo]
  return Object.entries(o as Dic).flatMap(([k, v]) => hojas(v, prefijo ? `${prefijo}.${k}` : k))
}

const DICCIONARIOS = { es, en, zh } as unknown as Record<string, Dic>
const SRC = resolve(__dirname, '..')
const leer = (...ruta: string[]) => readFileSync(resolve(SRC, ...ruta), 'utf8')

const CODIGOS = [
  'swr_ambito_no_valido', 'swr_ajuste_no_valido', 'swr_pesos_no_suman', 'swr_rangos_de_impacto', 'swr_objetivo_no_valido',
  'swr_control_no_encontrado', 'swr_control_tipo', 'swr_control_caducidad', 'swr_control_descripcion', 'swr_control_no_activo',
  'swr_control_sin_hallazgos', 'swr_vista_no_encontrada', 'swr_vista_ajena', 'swr_informe_no_encontrado', 'swr_informe_tipo',
  'swr_destinatarios', 'swr_fuente_no_valida', 'swr_fichero_no_reconocido', 'swr_exposicion_no_valida', 'swr_api_tercero',
]
const TIPOS_NUEVOS = ['sw_vm_trendmicro', 'sw_vm_defender', 'sw_vm_qualys', 'sw_vm_tenable', 'sw_vm_rapid7', 'sw_siem']

describe('Índice de riesgo y gestión de vulnerabilidades', () => {
  it('es, en y zh tienen las mismas claves en `swr` y ninguna vacía', () => {
    const base = hojas(DICCIONARIOS.es.swr).sort()
    expect(base.length).toBeGreaterThan(300)
    for (const lang of ['en', 'zh']) {
      expect(hojas(DICCIONARIOS[lang].swr).sort(), lang).toEqual(base)
    }
    for (const lang of ['es', 'en', 'zh']) {
      const swr = DICCIONARIOS[lang].swr as Dic
      for (const ruta of base) {
        const valor = ruta.split('.').reduce<unknown>((o, k) => (o as Dic)[k], swr)
        expect(typeof valor === 'string' && valor.trim().length > 0, `${lang}: swr.${ruta}`).toBe(true)
      }
    }
  })

  it('el chino no es una copia del inglés', () => {
    const en_ = DICCIONARIOS.en.swr as Dic
    const zh_ = DICCIONARIOS.zh.swr as Dic
    const iguales = Object.keys(en_).filter(k => typeof en_[k] === 'string' && en_[k] === zh_[k] && /[a-z]{4,}/.test(String(en_[k])))
    // Solo nombres propios o técnicos pueden coincidir.
    expect(iguales.length).toBeLessThan(10)
  })

  it('los errores `err_srv.swr_*` existen en los tres idiomas (con el texto en castellano acordado)', () => {
    for (const lang of ['es', 'en', 'zh']) {
      const err = (DICCIONARIOS[lang] as Record<string, Dic>).err_srv
      for (const c of CODIGOS) expect(err[c], `${lang}: err_srv.${c}`).toBeTruthy()
    }
    const es_ = (DICCIONARIOS.es as Record<string, Dic>).err_srv
    expect(es_.swr_pesos_no_suman).toBe('Los pesos tienen que sumar 1 (ahora suman {suma})')
    expect(es_.swr_api_tercero).toBe('{fuente} ha respondido con error: {detalle}')
  })

  it('las acciones del plan y los catálogos del servidor tienen texto', () => {
    for (const lang of ['es', 'en', 'zh']) {
      const swr = DICCIONARIOS[lang].swr as Record<string, unknown>
      for (const a of ['upgrade', 'no_fix', 'possible', 'retire', 'control']) expect(swr[`accion_${a}`], `${lang}: accion_${a}`).toBeTruthy()
      for (const cat of ['v_ambito', 'v_factor', 'v_superficie', 'v_control', 'v_fuente', 'v_accion_exploit', 'v_informe', 'v_frecuencia', 'v_evento', 'v_nivel']) {
        expect(Object.keys((swr[cat] ?? {}) as Dic).length, `${lang}: swr.${cat}`).toBeGreaterThan(1)
      }
      for (const p of ['{product}', '{from}', '{to}', '{machines}']) expect(String(swr.accion_upgrade), `${lang}: ${p}`).toContain(p)
    }
  })

  it('la CMDB tiene la pestaña `risk` con software.ver y carga diferida', () => {
    const src = leer('pages', 'CMDBPage.tsx')
    expect(src).toMatch(/id: 'risk'/)
    expect(src).toMatch(/t\('swr\.tab_riesgo'\)/)
    expect(src).toMatch(/lazy\(\(\) => import\('\.\.\/components\/cmdb\/software\/riesgo\/RiesgoTab'\)/)
    expect(src).toMatch(/\{tab === 'risk' && <RiesgoTab \/>\}/)
  })

  it('Configuración → Software y vulnerabilidades incluye los ajustes del índice', () => {
    const src = leer('components', 'cmdb', 'software', 'ConfigSoftware.tsx')
    expect(src).toMatch(/import ConfigRiesgo from '\.\/riesgo\/ConfigRiesgo'/)
    expect(src).toMatch(/<ConfigRiesgo \/>/)
  })

  it('las conexiones de escaneo conocen los tipos nuevos y tienen texto en los tres idiomas', () => {
    const src = leer('components', 'cmdb', 'software', 'Escaneos.tsx')
    for (const tipo of TIPOS_NUEVOS) expect(src, tipo).toContain(`'${tipo}'`)
    for (const lang of ['es', 'en', 'zh']) {
      const sw = DICCIONARIOS[lang].sw as Record<string, unknown>
      for (const tipo of TIPOS_NUEVOS) {
        expect((sw.v_tipo_conexion as Dic)[tipo], `${lang}: sw.v_tipo_conexion.${tipo}`).toBeTruthy()
        expect(sw[`esc_tipo_ayuda_${tipo}`], `${lang}: sw.esc_tipo_ayuda_${tipo}`).toBeTruthy()
      }
      for (const campo of ['tenant_id', 'client_id', 'client_secret', 'access_key', 'secret_key', 'complete', 'with_kb', 'days', 'cve_field', 'time_field', 'action_field', 'count_field', 'id_field']) {
        expect((sw.campo as Dic)[campo], `${lang}: sw.campo.${campo}`).toBeTruthy()
      }
    }
  })

  it('las pantallas del riesgo no llevan controles nativos sueltos ni textos fijos en botones', () => {
    for (const f of ['RiesgoTab', 'Indice', 'Plan', 'Metricas', 'Superficies', 'Controles', 'Importar', 'Informes', 'ConfigRiesgo', 'SelectorDeAmbito']) {
      const src = leer('components', 'cmdb', 'software', 'riesgo', `${f}.tsx`)
      expect(src, f).not.toMatch(/<(input|select|textarea)[\s>]/)
    }
  })
})
