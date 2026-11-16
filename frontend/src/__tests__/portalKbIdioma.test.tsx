// Traducción en tiempo real (16-11-2026): el portal pide la KB en el idioma de su pantalla (`?lang=`),
// para recibir la versión publicada en ese idioma si la hay.
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'

vi.mock('../i18n/AppLangContext', () => {
  const t = (k: string) => k
  return { useAppLang: () => ({ t, lang: 'es' }), useAppT: () => t }
})

import { CLIENT_API, LangContext } from '../pages/portal-client/portalClientContext'
import PortalKbArticulo from '../pages/portal-client/PortalKbArticulo'

const peticiones: InternalAxiosRequestConfig[] = []

const pintar = (idioma: string) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <LangContext.Provider value={idioma}>
      <PortalKbArticulo id="a1" onVolver={() => {}} migas="KB" />
    </LangContext.Provider>
  </QueryClientProvider>,
)

describe('KB del portal en el idioma de la pantalla', () => {
  beforeEach(() => {
    peticiones.length = 0
    CLIENT_API.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
      peticiones.push(config)
      return { data: { id: 'a1', title: 'Article en français', body: 'Contenu' }, status: 200, statusText: 'OK', headers: {}, config } as AxiosResponse
    }
  })

  it('manda lang con el idioma del portal al abrir un artículo', async () => {
    pintar('fr')
    expect(await screen.findAllByText('Article en français')).toBeTruthy()
    const detalle = peticiones.find(p => p.url === '/sd/kb/a1')
    expect(detalle?.params).toEqual({ lang: 'fr' })
  })

  it('con otro idioma pide otra vez y con ese idioma', async () => {
    pintar('de')
    await waitFor(() => expect(peticiones.some(p => p.url === '/sd/kb/a1')).toBe(true))
    expect(peticiones.find(p => p.url === '/sd/kb/a1')?.params).toEqual({ lang: 'de' })
  })
})
