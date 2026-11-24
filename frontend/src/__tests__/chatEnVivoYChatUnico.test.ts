// Chat en vivo de Soporte completo y «un solo chat» (24-11-2026,
// docs/portal/CHAT_DEL_PORTAL.md §10 y docs/GUIA_DE_DISENO.md §«Un solo chat»):
// rutas por lado (el cliente no llama nunca), reacciones agrupadas y que los
// chats del portal usen las piezas del chat interno. Escrito sin ejecutar.
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { chatEnVivoApi, type ClienteHttp } from '../components/portal/chatEnVivoApi'
import { agruparReacciones, cambiaDeDia } from '../components/chat'
import es from '../i18n/portal/es'
import en from '../i18n/portal/en'
import de from '../i18n/portal/de'
import fr from '../i18n/portal/fr'
import it_ from '../i18n/portal/it'
import pl from '../i18n/portal/pl'
import pt from '../i18n/portal/pt'
import zh from '../i18n/portal/zh'

function falso() {
  const llamadas: Array<{ metodo: string; url: string }> = []
  const anotar = (metodo: string) => (url: string) => { llamadas.push({ metodo, url }); return Promise.resolve({ data: {} }) }
  const http = { get: anotar('get'), post: anotar('post'), put: anotar('put'), delete: anotar('delete') } as unknown as ClienteHttp
  return { http, llamadas }
}

describe('chatEnVivoApi', () => {
  it('el operador va por la bandeja de canales y puede llamar', async () => {
    const { http, llamadas } = falso()
    const api = chatEnVivoApi(http, 'team')
    await api.llamar('c1', 'video')
    await api.adjunto('c1', 'a1')
    await api.editar('c1', 'm1', 'x')
    expect(llamadas.map(l => `${l.metodo} ${l.url}`)).toEqual([
      'post /sd/channels/conversations/c1/calls',
      'get /sd/channels/conversations/c1/files/a1',
      'put /sd/channels/conversations/c1/messages/m1',
    ])
  })
  it('el cliente nunca llama: ni siquiera pide la ruta', async () => {
    const { http, llamadas } = falso()
    const api = chatEnVivoApi(http, 'client')
    await expect(api.llamar('c1', 'audio')).rejects.toThrow('portal_llamada_solo_operador')
    expect(llamadas).toEqual([])
    await api.aceptar('c1', 'k1')
    await api.adjunto('c1', 'a1')
    expect(llamadas.map(l => l.url)).toEqual([
      '/sd/channels/livechat/c1/calls/k1/accept',
      '/sd/channels/livechat/c1/attachments/a1',
    ])
  })
})

describe('agruparReacciones (pieza compartida)', () => {
  it('agrupa por emoji y marca las de quien mira', () => {
    const g = agruparReacciones([
      { emoji: '👍', user_id: 'u1', client_user_id: null },
      { emoji: '👍', user_id: null, client_user_id: 'c1' },
      { emoji: '🎉', user_id: 'u2', client_user_id: null },
    ], { clientId: 'c1' })
    expect(g).toEqual([{ emoji: '👍', n: 2, mia: true }, { emoji: '🎉', n: 1, mia: false }])
  })
})

describe('un solo chat', () => {
  const raiz = path.resolve(__dirname, '..')
  const chats = [
    'components/portal/GovernedConversations.tsx',
    'components/portal/GovernedConversationsPiezas.tsx',
    'components/portal/ChatColaboracionDelPortal.tsx',
    'components/portal/MensajeDelChatEnVivo.tsx',
    'pages/portal-client/PortalAsistenteYChat.tsx',
    'components/servicedesk/BandejaDeCanales.tsx',
    'pages/chat/Mensajes.tsx',
    'pages/chat/PanelDeConversacion.tsx',
    'pages/chat/ListaDeConversaciones.tsx',
    // 24-11-2026 (burbujas): el resto de chats de la aplicación.
    'components/layout/GlobalChatPanel.tsx',
    'components/layout/NexusAssistPanel.tsx',
    'pages/portal-client/PortalAIChatWidget.tsx',
    'pages/NexusAgentPage.tsx',
    'pages/PreguntarALaEmpresaPage.tsx',
    'pages/CallPage.tsx',
  ]
  it.each(chats)('%s usa las piezas de components/chat', (rel) => {
    const texto = fs.readFileSync(path.join(raiz, rel), 'utf8')
    expect(texto).toMatch(/from '(\.\.\/)+(components\/)?chat'/)
    expect(texto).not.toMatch(/chat-portal-(burbuja|acciones|reaccion|contexto|cita)|ConversationListItem|sdm-chat__msg|chat-thread__msg/)
  })
  // Burbujas «como WhatsApp»: cada FilaDeMensaje dice si es de quien mira (`propio`) o del bot.
  it.each(chats)('%s: cada FilaDeMensaje lleva `propio` o `esBot`', (rel) => {
    const texto = fs.readFileSync(path.join(raiz, rel), 'utf8')
    for (const m of texto.matchAll(/<FilaDeMensaje\b/g)) {
      expect(texto.slice(m.index, (m.index ?? 0) + 400)).toMatch(/\bpropio\b|\besBot\b/)
    }
  })
})

describe('burbujas: separadores de día', () => {
  it('cambia de día solo al pasar a otra fecha local', () => {
    const a = new Date(2026, 10, 23, 23, 50).toISOString()
    const b = new Date(2026, 10, 23, 23, 59).toISOString()
    const c = new Date(2026, 10, 24, 0, 5).toISOString()
    expect(cambiaDeDia(null, a)).toBe(true)
    expect(cambiaDeDia(a, b)).toBe(false)
    expect(cambiaDeDia(b, c)).toBe(true)
    expect(cambiaDeDia(b, null)).toBe(false)
  })
})

describe('textos nuevos en los 8 idiomas del portal', () => {
  const claves = ['governedconversations.buscar', 'governedconversations.mensajes']
  it.each([es, en, de, fr, it_, pl, pt, zh].map((d, i) => [i, d] as const))('diccionario %i', (_i, dic) => {
    for (const c of claves) expect((dic as Record<string, string>)[c]).toBeTruthy()
  })
})
