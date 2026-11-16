// Portal en 8 idiomas, restos (16-11-2026): el kit (Spinner, Pagination,
// Confirm…) y el aviso global (ToastContext) salen en el idioma del portal
// dentro de él, y en el del operador fuera. Los errores del servidor con código
// (`{detail, code, params}`) se pintan en el idioma del portal.
import { describe, it, expect, afterEach } from 'vitest'
import { act, render, screen, fireEvent, cleanup } from '@testing-library/react'
import { useEffect, type ReactNode } from 'react'

import { LangContext, TextosDeInterfazDelPortal, traductorDeCodigosDelPortal } from '../pages/portal-client/portalClientContext'
import { Spinner } from '../components/ui'
import Pagination from '../components/ui/Pagination'
import Confirm from '../components/ui/Confirm'
import { ToastProvider, useToast } from '../context/ToastContext'
import { _reiniciarTextosDeInterfaz, useTextoUi } from '../components/ui/useTextoUi'
import { mensajeDeError } from '../utils/mensajeDeError'
import { reportQueryError } from '../lib/queryErrorBus'
import { PORTAL_TRANSLATIONS } from '../i18n/portalTranslations'

afterEach(() => { cleanup(); _reiniciarTextosDeInterfaz() })

function EnElPortal({ idioma, children }: { idioma: string; children: ReactNode }) {
  return (
    <LangContext.Provider value={idioma}>
      <TextosDeInterfazDelPortal>{children}</TextosDeInterfazDelPortal>
    </LangContext.Provider>
  )
}

describe('kit de interfaz dentro del portal', () => {
  it('Spinner y Pagination usan el diccionario del portal (francés)', () => {
    render(
      <EnElPortal idioma="fr">
        <Spinner />
        <Pagination page={2} totalPages={5} onChange={() => {}} total={120} pageSize={25} />
      </EnElPortal>,
    )
    expect(screen.getByRole('status', { name: PORTAL_TRANSLATIONS.fr['uikit.cargando'] })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: PORTAL_TRANSLATIONS.fr['pagination.navegacion'] })).toBeInTheDocument()
    expect(screen.getAllByLabelText(PORTAL_TRANSLATIONS.fr['pagination.siguiente']).length).toBeGreaterThan(0)
    // Variables `{{n}}` del portal rellenadas.
    expect(screen.getByLabelText('Page 3')).toBeInTheDocument()
    expect(screen.getByText('26–50 sur 120')).toBeInTheDocument()
  })

  it('Confirm usa los botones del portal (alemán)', () => {
    render(
      <EnElPortal idioma="de">
        <Confirm open title="T" description="D" onCancel={() => {}} onConfirm={() => {}} />
      </EnElPortal>,
    )
    expect(screen.getByRole('button', { name: PORTAL_TRANSLATIONS.de['common.cancel'] })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: PORTAL_TRANSLATIONS.de['common.confirm'] })).toBeInTheDocument()
  })

  it('fuera del portal, el kit sigue con el traductor de operador', () => {
    function Clave() {
      const t = useTextoUi()
      return <span>{t('uikit.cargando')}</span>
    }
    render(<Clave />)
    // Sin proveedores: el operador (es/en/zh), nunca el polaco del portal.
    expect(screen.queryByText(PORTAL_TRANSLATIONS.pl['uikit.cargando'])).toBeNull()
  })

  it('los 8 diccionarios del portal tienen las claves del kit y del aviso', () => {
    const claves = ['uikit.cargando', 'uikit.cerrar', 'pagination.siguiente', 'toast.close', 'toast.load_error',
      'toast.unexpected_error', 'common.confirm', 'common.cancel', 'fecha.elegir_fecha']
    for (const [idioma, dic] of Object.entries(PORTAL_TRANSLATIONS)) {
      for (const k of claves) expect({ idioma, k, ok: Boolean(dic[k]) }).toEqual({ idioma, k, ok: true })
    }
  })
})

describe('aviso global (ToastContext) dentro del portal', () => {
  function Disparar({ mensaje }: { mensaje: string }) {
    const toast = useToast()
    useEffect(() => { toast.error(mensaje) }, [])  // eslint-disable-line react-hooks/exhaustive-deps
    return null
  }

  it('el botón de cerrar sale en el idioma del portal (italiano)', async () => {
    render(
      <ToastProvider>
        <EnElPortal idioma="it">
          <Disparar mensaje="x" />
        </EnElPortal>
      </ToastProvider>,
    )
    expect(await screen.findByRole('button', { name: PORTAL_TRANSLATIONS.it['toast.close'] })).toBeInTheDocument()
  })

  it('un error de carga con código sale traducido al idioma del portal (portugués)', async () => {
    render(
      <ToastProvider>
        <EnElPortal idioma="pt"><span>portal</span></EnElPortal>
      </ToastProvider>,
    )
    await screen.findByText('portal')
    act(() => { reportQueryError({ response: { data: { detail: 'Ticket no encontrado', code: 'ticket_no_encontrado', params: {} } } }) })
    expect(await screen.findByText(PORTAL_TRANSLATIONS.pt['err_srv.ticket_no_encontrado'])).toBeInTheDocument()
  })

  it('sin código, el aviso de carga del portal (polaco)', async () => {
    render(
      <ToastProvider>
        <EnElPortal idioma="pl"><span>portal</span></EnElPortal>
      </ToastProvider>,
    )
    await screen.findByText('portal')
    act(() => { reportQueryError(new Error('red')) })
    expect(await screen.findByText(PORTAL_TRANSLATIONS.pl['toast.load_error'])).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: PORTAL_TRANSLATIONS.pl['toast.close'] }))
  })
})

describe('errores del servidor con código', () => {
  const error = (code: string, params: Record<string, unknown> = {}, detail = 'texto en castellano') =>
    ({ response: { data: { detail, code, params } } })

  it('el portal traduce el código con sus parámetros', () => {
    const t = traductorDeCodigosDelPortal('en')
    expect(mensajeDeError(error('contrasena_corta', { n: 12 }), t, 'fallback'))
      .toBe(PORTAL_TRANSLATIONS.en['err_srv.contrasena_corta'].replace('{{n}}', '12'))
  })

  it('código desconocido: el detail; sin respuesta: el fallback', () => {
    const t = traductorDeCodigosDelPortal('fr')
    expect(mensajeDeError(error('no_existe'), t, 'fallback')).toBe('texto en castellano')
    expect(mensajeDeError(new Error('x'), t, 'fallback')).toBe('fallback')
    // Sin traductor (operador): el detail de siempre.
    expect(mensajeDeError(error('ticket_no_encontrado'), null, 'fallback')).toBe('texto en castellano')
  })
})
