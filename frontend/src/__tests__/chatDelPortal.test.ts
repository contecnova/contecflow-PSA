// Chat del portal completo (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md):
// enlaces seguros, rutas de la API por lado (el cliente nunca tiene ruta de
// «llamar» que no sea la que el servidor rechaza) y textos en los 8 idiomas.
import { describe, it, expect } from 'vitest'
import { partirEnlaces } from '../components/ui/TextoConEnlaces'
import { chatDelPortalApi, tamanoLegible, type ClienteHttp } from '../components/portal/chatDelPortalApi'
import { agruparReacciones, leidoPorElEquipo } from '../components/portal/ChatColaboracionDelPortal'
import es from '../i18n/portal/es'
import en from '../i18n/portal/en'
import de from '../i18n/portal/de'
import fr from '../i18n/portal/fr'
import it_ from '../i18n/portal/it'
import pl from '../i18n/portal/pl'
import pt from '../i18n/portal/pt'
import zh from '../i18n/portal/zh'

describe('TextoConEnlaces', () => {
  it('enlaza http(s) y www, y deja fuera la puntuación final', () => {
    const trozos = partirEnlaces('Mira https://ejemplo.com/a?b=1. Y www.otro.es, gracias')
    expect(trozos.filter(t => t.href).map(t => t.href)).toEqual(['https://ejemplo.com/a?b=1', 'https://www.otro.es'])
    expect(trozos.map(t => t.texto).join('')).toBe('Mira https://ejemplo.com/a?b=1. Y www.otro.es, gracias')
  })
  it('nunca enlaza javascript: ni data:', () => {
    const trozos = partirEnlaces(['java', 'script:alert(1) data:text/html,hola'].join(''))
    expect(trozos.some(t => t.href)).toBe(false)
  })
})

describe('chatDelPortalApi', () => {
  const llamadas: Array<{ metodo: string; url: string }> = []
  const http = {
    get: async (url: string) => { llamadas.push({ metodo: 'get', url }); return { data: [] } },
    post: async (url: string) => { llamadas.push({ metodo: 'post', url }); return { data: {} } },
    put: async (url: string) => { llamadas.push({ metodo: 'put', url }); return { data: {} } },
    delete: async (url: string) => { llamadas.push({ metodo: 'delete', url }); return { data: {} } },
  } as unknown as ClienteHttp

  it('el equipo usa /team y el cliente no', async () => {
    llamadas.length = 0
    await chatDelPortalApi(http, 'team').llamar('c1', 'video')
    await chatDelPortalApi(http, 'client').aceptar('c1', 'l1')
    await chatDelPortalApi(http, 'client').editar('c1', 'm1', 'x')
    expect(llamadas).toEqual([
      { metodo: 'post', url: '/portal/conversations/team/c1/calls' },
      { metodo: 'post', url: '/portal/conversations/c1/calls/l1/accept' },
      { metodo: 'put', url: '/portal/conversations/c1/messages/m1' },
    ])
  })

  it('tamaño legible', () => {
    expect(tamanoLegible(0)).toBe('0 KB')
    expect(tamanoLegible(2048)).toBe('2 KB')
    expect(tamanoLegible(3 * 1024 * 1024)).toBe('3.0 MB')
  })
})

describe('textos del chat del portal en los 8 idiomas', () => {
  const claves = [
    'governedconversations.llamada_no_se_graba', 'governedconversations.aceptar', 'governedconversations.rechazar',
    'governedconversations.colgar', 'governedconversations.escribiendo', 'governedconversations.adjuntar',
    'governedconversations.mensaje_borrado', 'err_srv.portal_llamada_solo_operador', 'uikit.elegir_emoji',
  ]
  const idiomas = { es, en, de, fr, it: it_, pl, pt, zh } as Record<string, Record<string, string>>
  for (const [idioma, dic] of Object.entries(idiomas)) {
    it(idioma, () => {
      for (const clave of claves) expect(dic[clave], `${idioma}: ${clave}`).toBeTruthy()
    })
  }
})

// Pestaña «Chat» del portal (colaboración): reacciones propias y «Leído».

describe('ChatColaboracionDelPortal', () => {
  it('agrupa reacciones y marca las del propio cliente', () => {
    const grupos = agruparReacciones({ reactions: [
      { emoji: '👍', user_id: 'u1', client_user_id: null },
      { emoji: '👍', user_id: null, client_user_id: 'c1' },
      { emoji: '🎉', user_id: 'u2', client_user_id: null },
    ] }, 'c1')
    expect(grupos).toEqual([['👍', { n: 2, mia: true }], ['🎉', { n: 1, mia: false }]])
  })
  it('leído si el equipo leyó después del envío', () => {
    expect(leidoPorElEquipo('2026-11-24T10:00:00Z', '2026-11-24T10:05:00Z')).toBe(true)
    expect(leidoPorElEquipo('2026-11-24T10:10:00Z', '2026-11-24T10:05:00Z')).toBe(false)
    expect(leidoPorElEquipo('2026-11-24T10:10:00Z', null)).toBe(false)
  })
})
