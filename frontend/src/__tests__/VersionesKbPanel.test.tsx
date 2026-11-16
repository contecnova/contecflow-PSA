// Traducción en tiempo real (16-11-2026): versiones de un artículo de la KB en otros idiomas.
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const { api } = vi.hoisted(() => {
  const nombres = ['versionesKb', 'generarKb', 'editarKb', 'revisarKb', 'borrarKb']
  return { api: Object.fromEntries(nombres.map(n => [n, vi.fn()])) as Record<string, ReturnType<typeof vi.fn>> }
})

vi.mock('../services/api/traduccion', () => ({ traduccionApi: api }))
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../i18n/AppLangContext', () => {
  const t = (k: string) => k
  return { useAppLang: () => ({ t, lang: 'es' }), useAppT: () => t }
})

import VersionesKbPanel from '../components/traduccion/VersionesKbPanel'

const version = (language: string, extra: Record<string, unknown> = {}) => ({
  id: `v-${language}`, article_id: 'a1', language, title: `Título ${language}`, summary: null, body: `Cuerpo ${language}`,
  status: 'in_review', provider: 'ai', outdated: false, review_comment: null, reviewed_at: null, updated_at: null, ...extra,
})

const pintar = () => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <VersionesKbPanel articleId="a1" />
  </QueryClientProvider>,
)

describe('Versiones de la KB en otros idiomas', () => {
  beforeEach(() => {
    Object.values(api).forEach(f => f.mockReset())
    api.versionesKb.mockResolvedValue({
      article_id: 'a1', source_language: 'es', languages: ['es', 'en', 'fr'], enabled: true,
      items: [version('en'), version('fr', { outdated: true, status: 'published' })],
    })
    api.revisarKb.mockResolvedValue(version('en', { status: 'published' }))
  })

  it('lista las versiones con su estado y avisa de la desfasada', async () => {
    pintar()
    expect(await screen.findByText('Título en')).toBeTruthy()
    expect(screen.getByText('traduccion_admin.kb_estado.in_review')).toBeTruthy()
    expect(screen.getByText('traduccion_admin.kb_estado.published')).toBeTruthy()
    expect(screen.getByText('traduccion_admin.kb_desfasada')).toBeTruthy()
  })

  it('publica una versión sin pedir comentario', async () => {
    pintar()
    await screen.findByText('Título en')
    fireEvent.click(screen.getAllByRole('button', { name: 'traduccion_admin.kb_abrir_x' })[0])
    const dialogo = await screen.findByRole('dialog')
    fireEvent.click(within(dialogo).getByRole('button', { name: /traduccion_admin.kb_publicar/ }))
    await waitFor(() => expect(api.revisarKb).toHaveBeenCalledWith('a1', 'en', { publish: true }))
  })

  it('rechazar exige un comentario', async () => {
    pintar()
    await screen.findByText('Título en')
    fireEvent.click(screen.getAllByRole('button', { name: 'traduccion_admin.kb_abrir_x' })[0])
    const dialogo = await screen.findByRole('dialog')
    fireEvent.click(within(dialogo).getByRole('button', { name: /traduccion_admin.kb_rechazar/ }))
    const confirmar = within(dialogo).getByRole('button', { name: /traduccion_admin.kb_confirmar_rechazo/ }) as HTMLButtonElement
    expect(confirmar.disabled).toBe(true)
    fireEvent.click(confirmar)
    expect(api.revisarKb).not.toHaveBeenCalled()
    fireEvent.change(within(dialogo).getByLabelText('traduccion_admin.kb_comentario'), { target: { value: '  Falta el paso 3  ' } })
    expect(confirmar.disabled).toBe(false)
    fireEvent.click(confirmar)
    await waitFor(() => expect(api.revisarKb).toHaveBeenCalledWith('a1', 'en', { publish: false, comment: 'Falta el paso 3' }))
  })

  it('enseña el motivo de los idiomas que no se pudieron generar', async () => {
    api.generarKb.mockResolvedValue({ generated: [], failed: [{ language: 'fr', reason: 'quota_exceeded' }] })
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: /traduccion_admin.kb_generar_todos/ }))
    await waitFor(() => expect(api.generarKb).toHaveBeenCalledWith('a1', undefined))
    expect(await screen.findByText('traduccion_admin.kb_fallo')).toBeTruthy()
  })
})
