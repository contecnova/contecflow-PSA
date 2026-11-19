// Traducción en tiempo real (16-11-2026): pantalla de administración (Ajustes → Sistema → Traducción).
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { api, ajustes, estado } = vi.hoisted(() => {
  const nombres = ['config', 'mensajes', 'texto', 'vistaPrevia', 'glosario', 'crearTermino', 'cambiarTermino', 'borrarTermino',
    'uso', 'probar', 'versionesKb', 'generarKb', 'editarKb', 'revisarKb', 'borrarKb']
  return {
    api: Object.fromEntries(nombres.map(n => [n, vi.fn()])) as Record<string, ReturnType<typeof vi.fn>>,
    ajustes: { runtimeGroup: vi.fn(), setRuntime: vi.fn() },
    estado: { rol: 'admin' },
  }
})

vi.mock('../services/api/traduccion', () => ({ traduccionApi: api }))
vi.mock('../services/api', () => ({ settingsApi: ajustes }))
vi.mock('../pages/settings-sections/SettingsAdvancedSections', () => ({
  IntegrationProviderEditor: ({ provider }: { provider: string }) => <div data-testid="credenciales">{provider}</div>,
}))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { role: estado.rol }, puede: (c: string) => puedeComo(estado.rol)(c) }) }))
vi.mock('../i18n/AppLangContext', () => {
  const t = (k: string) => k
  return { useAppLang: () => ({ t, lang: 'es' }), useAppT: () => t }
})

import TraduccionSection from '../pages/settings-sections/TraduccionSection'
import { puedeComo } from './capacidadesDelBackend'

const USO = {
  cache: { entries: 120, characters: 5400, hits: 80 }, messages_translated: 42, glossary_terms: 1, kb_versions_in_review: 2,
  today_cost_usd: 0.12, today_calls: 7, today_failures: 0, ai_spend_today_usd: 0.5, ai_daily_budget_usd: 10,
}
const CONFIG = {
  enabled: true, provider: 'ai', channels: ['ticket'], include_original: false, outbound_auto: false, my_language: 'es',
  languages: ['es', 'en', 'fr'], operator_languages: ['es', 'en'], portal_languages: ['es', 'en', 'fr'],
}
const AJUSTES = [
  { key: 'TRANSLATION_ENABLED', type: 'bool', label: 'Activada', value: true, plataforma: false },
  { key: 'TRANSLATION_PROVIDER', type: 'str', label: 'Proveedor', value: 'ai', plataforma: false },
  { key: 'TRANSLATION_CHANNELS', type: 'str', label: 'Canales', value: 'ticket', plataforma: false },
  { key: 'TRANSLATION_MAX_BATCH_CHARS', type: 'int', label: 'Lote', value: 4000, plataforma: false },
]

const pintar = () => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <TraduccionSection />
  </QueryClientProvider>,
)

describe('Administración de la traducción', () => {
  beforeEach(() => {
    estado.rol = 'admin'
    Object.values(api).forEach(f => f.mockReset())
    ajustes.runtimeGroup.mockReset().mockResolvedValue({ data: { group: 'traduccion', items: AJUSTES } })
    ajustes.setRuntime.mockReset().mockResolvedValue({ data: { ok: true } })
    api.uso.mockResolvedValue(USO)
    api.config.mockResolvedValue(CONFIG)
    api.glosario.mockResolvedValue({ items: [
      { id: 'g1', term: 'Contecflow', translations: {}, case_sensitive: true, notes: null, is_active: true, updated_at: null },
    ] })
    api.crearTermino.mockResolvedValue({ id: 'g2' })
  })

  it('pinta el uso, los ajustes, las credenciales y el glosario', async () => {
    pintar()
    expect(await screen.findByText('traduccion_admin.kpi_mensajes')).toBeTruthy()
    expect(await screen.findByText('42')).toBeTruthy()
    expect(await screen.findByText('Contecflow')).toBeTruthy()
    expect(screen.getByText('traduccion_admin.no_se_traduce')).toBeTruthy()
    expect(await screen.findByLabelText('traduccion_admin.canal.internal_chat')).toBeTruthy()
    expect(screen.getByTestId('credenciales').textContent).toBe('deepl')
    expect(ajustes.runtimeGroup).toHaveBeenCalledWith('traduccion')
  })

  it('guarda los canales elegidos como lista separada por comas', async () => {
    pintar()
    fireEvent.click(await screen.findByLabelText('traduccion_admin.canal.email'))
    fireEvent.click(screen.getByRole('button', { name: /traduccion_admin.guardar_n/ }))
    await waitFor(() => expect(ajustes.setRuntime).toHaveBeenCalledWith('traduccion', 'TRANSLATION_CHANNELS', 'ticket,email'))
    expect(ajustes.setRuntime).toHaveBeenCalledTimes(1)
  })

  it('da de alta un término con sus traducciones por idioma', async () => {
    pintar()
    await screen.findByText('Contecflow')
    fireEvent.click(screen.getByRole('button', { name: /traduccion_admin.nuevo_termino/ }))
    const dialogo = await screen.findByRole('dialog')
    fireEvent.change(within(dialogo).getByLabelText('traduccion_admin.col_termino'), { target: { value: 'Ticket' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: /traduccion_admin.anadir_idioma/ }))
    fireEvent.change(within(dialogo).getByLabelText('traduccion_admin.idioma_n'), { target: { value: 'en' } })
    fireEvent.change(within(dialogo).getByLabelText('traduccion_admin.texto_en'), { target: { value: 'Ticket' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: /traduccion_admin.guardar/ }))
    await waitFor(() => expect(api.crearTermino).toHaveBeenCalledWith({
      term: 'Ticket', translations: { en: 'Ticket' }, case_sensitive: false, notes: null, is_active: true,
    }))
  })

  it('sin rol de administrador no pide nada', () => {
    estado.rol = 'agent'
    pintar()
    expect(screen.getByText('traduccion_admin.solo_admin')).toBeTruthy()
    expect(api.uso).not.toHaveBeenCalled()
    expect(ajustes.runtimeGroup).not.toHaveBeenCalled()
  })
})
