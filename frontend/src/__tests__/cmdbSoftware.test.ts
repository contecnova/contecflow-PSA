// CMDB de software, composición y vulnerabilidades (19-11-2026).
// Comprueba el cableado de la pantalla: capacidades, la sección de
// Configuración y que es/en/zh tengan las mismas claves en `sw`.
// Diseño: docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it, vi } from 'vitest'

// La API no se llama en estas pruebas: se simula para no tocar la red al importar.
vi.mock('../services/api/cmdbSoftware', () => ({
  cmdbSoftwareApi: new Proxy({}, { get: () => vi.fn().mockResolvedValue({}) }),
}))

import es from '../i18n/langs/es.mjs'
import en from '../i18n/langs/en.mjs'
import zh from '../i18n/langs/zh.mjs'
import { CAPACIDADES } from '../permisos/capacidades'
import { SECCIONES_DE_AJUSTES } from '../pages/settings/catalogoDeAjustes'

type Dic = Record<string, unknown>

/** Rutas de todas las hojas de un objeto (`a.b.c`). */
function hojas(o: unknown, prefijo = ''): string[] {
  if (!o || typeof o !== 'object') return [prefijo]
  return Object.entries(o as Dic).flatMap(([k, v]) => hojas(v, prefijo ? `${prefijo}.${k}` : k))
}

const DICCIONARIOS = { es, en, zh } as unknown as Record<string, Dic>

describe('CMDB de software y vulnerabilidades', () => {
  it('las cuatro capacidades existen', () => {
    for (const c of ['software.ver', 'software.gestionar', 'software.aprobar', 'software.config']) {
      expect(CAPACIDADES as readonly string[]).toContain(c)
    }
  })

  it('la sección «cmdb-software» está en Configuración y pide software.config', () => {
    const s = SECCIONES_DE_AJUSTES.find(x => x.id === 'cmdb-software')
    expect(s).toBeTruthy()
    expect(s?.capacidad).toBe('software.config')
    expect(s?.grupo).toBe('servicedesk')
  })

  it('es, en y zh tienen las mismas claves en `sw` y ninguna vacía', () => {
    const base = hojas(DICCIONARIOS.es.sw).sort()
    expect(base.length).toBeGreaterThan(300)
    for (const lang of ['en', 'zh']) {
      expect(hojas(DICCIONARIOS[lang].sw).sort(), lang).toEqual(base)
    }
    for (const lang of ['es', 'en', 'zh']) {
      const sw = DICCIONARIOS[lang].sw as Dic
      for (const ruta of base) {
        const valor = ruta.split('.').reduce<unknown>((o, k) => (o as Dic)[k], sw)
        expect(typeof valor === 'string' && valor.trim().length > 0, `${lang}: sw.${ruta}`).toBe(true)
      }
    }
  })

  it('el chino no es una copia del inglés', () => {
    const en_ = DICCIONARIOS.en.sw as Dic
    const zh_ = DICCIONARIOS.zh.sw as Dic
    const iguales = Object.keys(en_).filter(k => typeof en_[k] === 'string' && en_[k] === zh_[k] && /[a-z]{4,}/.test(String(en_[k])))
    // Solo nombres propios o técnicos (TLS, CVSS, nginx…) pueden coincidir.
    expect(iguales.length).toBeLessThan(10)
  })

  // 19-11-2026: ningún módulo lleva botón «Configurar»; en su lugar, avisos contextuales.
  it('la CMDB no tiene botón «Configurar»', () => {
    const src = readFileSync(resolve(__dirname, '..', 'pages', 'CMDBPage.tsx'), 'utf8')
    expect(src).not.toMatch(/Configurar|sw\.configurar|ajustes\.configurar|useNavigate/)
  })

  it('claves de escaneo, «posible afectado» y avisos contextuales en los tres idiomas', () => {
    for (const lang of ['es', 'en', 'zh']) {
      const d = DICCIONARIOS[lang] as Record<string, Dic>
      const sw = d.sw as Record<string, unknown>
      for (const k of ['esc_titulo', 'esc_conexiones', 'esc_escanear', 'esc_aviso_credenciales', 'esc_sin_conexiones_aviso',
        'posible', 'posible_ayuda', 'kpi_posibles', 'version_desconocida', 'sin_fuentes_activas', 'ir_a_configuracion',
        'pide_a_la_direccion', 'importar_varios_ayuda', 'importado_ignorados', 'importado_sin_version']) {
        expect(sw[k], `${lang}: sw.${k}`).toBeTruthy()
      }
      for (const tipo of ['sw_ssh', 'sw_winrm', 'sw_api']) {
        expect((sw.v_tipo_conexion as Dic)[tipo], `${lang}: ${tipo}`).toBeTruthy()
        expect(((d.sd_mercado as Dic).proveedor as Dic)[tipo], `${lang}: sd_mercado.proveedor.${tipo}`).toBeTruthy()
      }
      for (const campo of ['hosts', 'known_hosts', 'accept_unknown_host_keys', 'transport', 'list_path', 'max_pages']) {
        expect((sw.campo as Dic)[campo], `${lang}: sw.campo.${campo}`).toBeTruthy()
      }
      for (const codigo of ['sw_conexion_no_encontrada', 'sw_tipo_de_conexion_no_valido', 'sw_conexion_incompleta', 'sw_dependencia_no_instalada', 'sw_escaneo_fallido']) {
        expect(d.err_srv[codigo], `${lang}: ${codigo}`).toBeTruthy()
      }
    }
  })

  it('textos de la sección, de la bandeja de aprobaciones y de los errores del servidor en los tres idiomas', () => {
    for (const lang of ['es', 'en', 'zh']) {
      const d = DICCIONARIOS[lang] as Record<string, Dic>
      expect(d.ajustes.s_cmdb_software, lang).toBeTruthy()
      expect(d.ajustes.s_cmdb_software_d, lang).toBeTruthy()
      expect(d.approvals.entity_vuln_exception, lang).toBeTruthy()
      for (const codigo of ['sw_producto_no_encontrado', 'sw_estado_no_valido', 'sw_excepcion_caducidad', 'sw_sin_configuracion']) {
        expect(d.err_srv[codigo], `${lang}: ${codigo}`).toBeTruthy()
      }
      expect(d.grc.informe_control_sw_vuln_feed, lang).toBeTruthy()
      expect(d.grc.retencion_tipo_sw_findings, lang).toBeTruthy()
    }
  })
})
