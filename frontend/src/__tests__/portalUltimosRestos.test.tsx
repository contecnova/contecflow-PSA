// Portal en 8 idiomas, últimos restos (16-11-2026, tercera pasada):
// - marca «Traducido automáticamente» con «Ver original» en el portal;
// - las personalizaciones de textos del administrador llegan también al kit.
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import {
  CLIENT_API, ClientAuthContext, LangContext, PersonalizacionesDelPortal, PortalCustomContext,
  TextosDeInterfazDelPortal, type SesionDeCliente,
} from '../pages/portal-client/portalClientContext'
import TraduccionAutomatica, { MarcaDeTraduccion, textoDe } from '../pages/portal-client/TraduccionAutomatica'
import { Spinner } from '../components/ui'
import { _reiniciarTextosDeInterfaz } from '../components/ui/useTextoUi'
import { PORTAL_TRANSLATIONS } from '../i18n/portalTranslations'

afterEach(() => { cleanup(); _reiniciarTextosDeInterfaz(); vi.restoreAllMocks() })

const aviso = {
  id: 'a1',
  title: '[fr] Maintenance samedi',
  body: '[fr] Le portail sera indisponible.',
  translated_from: 'es',
  language: 'fr',
  original: { title: 'Mantenimiento el sábado', body: 'El portal no estará disponible.' },
}

function EnFrances({ children }: { children: ReactNode }) {
  return <LangContext.Provider value="fr">{children}</LangContext.Provider>
}

describe('marca de traducción automática del portal', () => {
  it('enseña la traducción con la marca y permite ver el original', () => {
    render(
      <EnFrances>
        <TraduccionAutomatica item={aviso}>
          {texto => <h2>{texto('title', aviso.title)}</h2>}
        </TraduccionAutomatica>
      </EnFrances>,
    )
    expect(screen.getByRole('heading', { name: '[fr] Maintenance samedi' })).toBeInTheDocument()
    const fr = PORTAL_TRANSLATIONS.fr
    const boton = screen.getByRole('button', { name: fr['traduccion_portal.ver_original'] })
    expect(boton).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(boton)
    expect(screen.getByRole('heading', { name: 'Mantenimiento el sábado' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: fr['traduccion_portal.ver_traduccion'] })).toHaveAttribute('aria-pressed', 'true')
  })

  it('lo que no llegó traducido sale tal cual, sin marca', () => {
    render(
      <EnFrances>
        <TraduccionAutomatica item={{ id: 'a2' } as { id: string }}>
          {texto => <p>{texto('title', 'Aviso')}</p>}
        </TraduccionAutomatica>
      </EnFrances>,
    )
    expect(screen.getByText('Aviso')).toBeInTheDocument()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('la marca sola, sin original que enseñar, no tiene botón', () => {
    render(
      <EnFrances>
        <MarcaDeTraduccion origen="de" verOriginal={false} onAlternar={() => {}} puedeVerOriginal={false} />
      </EnFrances>,
    )
    expect(screen.queryByRole('button')).toBeNull()
    expect(document.querySelector('.trad-marca')).not.toBeNull()
  })

  it('textoDe: el original solo si se pide y existe', () => {
    expect(textoDe(aviso, 'title', aviso.title, true)).toBe('Mantenimiento el sábado')
    expect(textoDe(aviso, 'title', aviso.title, false)).toBe('[fr] Maintenance samedi')
    expect(textoDe(aviso, 'otro', 'x', true)).toBe('x')
  })

  it('los 8 diccionarios del portal tienen los textos de la marca', () => {
    const claves = ['traduccion_portal.marca_auto', 'traduccion_portal.marca_original',
      'traduccion_portal.ver_original', 'traduccion_portal.ver_traduccion']
    for (const [idioma, dic] of Object.entries(PORTAL_TRANSLATIONS)) {
      for (const k of claves) expect({ idioma, k, ok: Boolean(dic[k]) }).toEqual({ idioma, k, ok: true })
      expect(dic['traduccion_portal.marca_auto']).toContain('{{idioma}}')
    }
  })
})

describe('personalizaciones del administrador en el kit del portal', () => {
  it('el proveedor de textos del kit usa las personalizaciones que tiene por encima', () => {
    render(
      <LangContext.Provider value="es">
        <PortalCustomContext.Provider value={{ es: { 'uikit.cargando': 'Un momento, por favor' } }}>
          <TextosDeInterfazDelPortal>
            <Spinner />
          </TextosDeInterfazDelPortal>
        </PortalCustomContext.Provider>
      </LangContext.Provider>,
    )
    expect(screen.getByRole('status', { name: 'Un momento, por favor' })).toBeInTheDocument()
  })

  it('PersonalizacionesDelPortal carga las de la marca y llegan al kit', async () => {
    vi.spyOn(CLIENT_API, 'get').mockResolvedValue({ data: { translations: { de: { 'uikit.cargando': 'Bitte warten' } } } })
    const sesion = { client: { id: 'c1' }, isReady: true, login: async () => null, logout: async () => {} } as unknown as SesionDeCliente
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <LangContext.Provider value="de">
          <ClientAuthContext.Provider value={sesion}>
            <PersonalizacionesDelPortal>
              <TextosDeInterfazDelPortal>
                <Spinner />
              </TextosDeInterfazDelPortal>
            </PersonalizacionesDelPortal>
          </ClientAuthContext.Provider>
        </LangContext.Provider>
      </QueryClientProvider>,
    )
    await waitFor(() => expect(screen.getByRole('status', { name: 'Bitte warten' })).toBeInTheDocument())
    expect(CLIENT_API.get).toHaveBeenCalledWith('/portal/branding')
  })
})
