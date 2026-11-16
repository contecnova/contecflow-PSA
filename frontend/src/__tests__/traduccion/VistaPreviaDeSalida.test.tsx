// Traducción en tiempo real (16-11-2026): la vista previa de lo que recibe el cliente.
// Se previsualiza, se corrige y, si el operador cambia su texto después, queda
// desfasada y no se expone (nunca se envía la traducción de otro texto).
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ConfigDeTraduccion, VistaPrevia } from '../../services/api/traduccion'

const { tPrueba } = vi.hoisted(() => ({
  tPrueba: (k: string, p?: string | Record<string, unknown>) =>
    (p && typeof p === 'object' ? `${k}:${Object.values(p).join(',')}` : k),
}))
vi.mock('../../i18n/AppLangContext', () => ({ useAppT: () => tPrueba, useAppLang: () => ({ lang: 'es', t: tPrueba }) }))

const config = vi.fn()
const vistaPrevia = vi.fn()
vi.mock('../../services/api/traduccion', () => ({
  traduccionApi: {
    config: (...a: unknown[]) => config(...a),
    vistaPrevia: (...a: unknown[]) => vistaPrevia(...a),
  },
}))

import VistaPreviaDeSalida from '../../components/traduccion/VistaPreviaDeSalida'

const CONFIG: ConfigDeTraduccion = {
  enabled: true, provider: 'ai', channels: ['ticket', 'livechat'], include_original: true, outbound_auto: false,
  my_language: 'es', languages: ['es', 'en', 'fr'], operator_languages: ['es', 'en'], portal_languages: ['es', 'en'],
}
const TRADUCIDA: VistaPrevia = {
  status: 'translated', text: 'The printer is fixed', source_language: 'es', target_language: 'en',
  target_source: 'contact', enabled: true, include_original: true, reason: null,
}

function pintar(texto: string, onChange = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const arbol = (txt: string) => (
    <QueryClientProvider client={qc}>
      <VistaPreviaDeSalida contextType="ticket" contextId="t1" texto={txt} onChange={onChange} />
    </QueryClientProvider>
  )
  const r = render(arbol(texto))
  return { ...r, onChange, cambiarTexto: (txt: string) => r.rerender(arbol(txt)) }
}

const ultimaLlamada = (fn: ReturnType<typeof vi.fn>) => fn.mock.calls[fn.mock.calls.length - 1]

describe('VistaPreviaDeSalida', () => {
  beforeEach(() => {
    config.mockReset().mockResolvedValue(CONFIG)
    vistaPrevia.mockReset().mockResolvedValue(TRADUCIDA)
  })

  it('sin traducción activada no pinta nada ni expone salida', async () => {
    config.mockResolvedValue({ ...CONFIG, enabled: false })
    const { container, onChange } = pintar('La impresora ya funciona')
    await waitFor(() => expect(config).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
    expect(ultimaLlamada(onChange)).toEqual([null, { desfasada: false }])
  })

  it('previsualiza en el idioma del cliente y expone client_text/client_language', async () => {
    const { onChange } = pintar('La impresora ya funciona')
    fireEvent.click(await screen.findByRole('button', { name: /traduccion_ui.vista_previa/ }))
    await waitFor(() => expect(vistaPrevia).toHaveBeenCalledWith({
      context_type: 'ticket', context_id: 't1', text: 'La impresora ya funciona', target_language: undefined,
    }))
    const campo = await screen.findByLabelText('traduccion_ui.lo_que_recibira')
    expect(campo).toHaveValue('The printer is fixed')
    expect(screen.getByText(/traduccion_ui.idioma_cliente:.*traduccion_ui.procedencia.contact/)).toBeInTheDocument()
    expect(screen.getByText('traduccion_ui.incluye_original')).toBeInTheDocument()
    await waitFor(() => expect(ultimaLlamada(onChange)).toEqual([
      { client_text: 'The printer is fixed', client_language: 'en' }, { desfasada: false },
    ]))
  })

  it('la traducción se puede corregir antes de enviar', async () => {
    const { onChange } = pintar('La impresora ya funciona')
    fireEvent.click(await screen.findByRole('button', { name: /traduccion_ui.vista_previa/ }))
    const campo = await screen.findByLabelText('traduccion_ui.lo_que_recibira')
    fireEvent.change(campo, { target: { value: 'Your printer works again' } })
    await waitFor(() => expect(ultimaLlamada(onChange)).toEqual([
      { client_text: 'Your printer works again', client_language: 'en' }, { desfasada: false },
    ]))
  })

  it('si el operador cambia su texto, queda desfasada: avisa y no expone la traducción', async () => {
    const { onChange, cambiarTexto } = pintar('La impresora ya funciona')
    fireEvent.click(await screen.findByRole('button', { name: /traduccion_ui.vista_previa/ }))
    await screen.findByLabelText('traduccion_ui.lo_que_recibira')
    cambiarTexto('La impresora ya funciona; reinicia el equipo')
    expect(await screen.findByText('traduccion_ui.desfasada')).toBeInTheDocument()
    await waitFor(() => expect(ultimaLlamada(onChange)).toEqual([null, { desfasada: true }]))
    // Regenerar con el texto nuevo la pone al día.
    vistaPrevia.mockResolvedValue({ ...TRADUCIDA, text: 'The printer works; restart the computer' })
    fireEvent.click(screen.getByRole('button', { name: /traduccion_ui.regenerar/ }))
    await waitFor(() => expect(vistaPrevia).toHaveBeenLastCalledWith(expect.objectContaining({ text: 'La impresora ya funciona; reinicia el equipo' })))
    await waitFor(() => expect(screen.queryByText('traduccion_ui.desfasada')).toBeNull())
    await waitFor(() => expect(ultimaLlamada(onChange)).toEqual([
      { client_text: 'The printer works; restart the computer', client_language: 'en' }, { desfasada: false },
    ]))
  })

  it('cambiar el idioma regenera la vista previa en el elegido', async () => {
    pintar('La impresora ya funciona')
    fireEvent.click(await screen.findByRole('button', { name: /traduccion_ui.vista_previa/ }))
    const selector = await screen.findByLabelText('traduccion_ui.enviar_en')
    vistaPrevia.mockResolvedValue({ ...TRADUCIDA, text: "L'imprimante fonctionne", target_language: 'fr', target_source: 'manual' })
    fireEvent.change(selector, { target: { value: 'fr' } })
    await waitFor(() => expect(vistaPrevia).toHaveBeenLastCalledWith(expect.objectContaining({ target_language: 'fr' })))
    expect(await screen.findByText(/traduccion_ui.procedencia.manual/)).toBeInTheDocument()
  })

  it('idioma del cliente desconocido: lo dice y no expone nada', async () => {
    vistaPrevia.mockResolvedValue({ ...TRADUCIDA, status: 'unavailable', text: null, target_language: null, target_source: null, reason: 'unknown_client_language' })
    const { onChange } = pintar('La impresora ya funciona')
    fireEvent.click(await screen.findByRole('button', { name: /traduccion_ui.vista_previa/ }))
    expect(await screen.findByText('traduccion_ui.idioma_desconocido')).toBeInTheDocument()
    expect(screen.queryByLabelText('traduccion_ui.lo_que_recibira')).toBeNull()
    expect(ultimaLlamada(onChange)).toEqual([null, { desfasada: false }])
  })

  it('sin traducción disponible: el motivo traducido y se enviará el original', async () => {
    vistaPrevia.mockResolvedValue({ ...TRADUCIDA, status: 'unavailable', text: null, reason: 'budget_exhausted' })
    const { onChange } = pintar('La impresora ya funciona')
    fireEvent.click(await screen.findByRole('button', { name: /traduccion_ui.vista_previa/ }))
    expect(await screen.findByText('traduccion_ui.no_disponible:traduccion.motivo.budget_exhausted')).toBeInTheDocument()
    expect(ultimaLlamada(onChange)).toEqual([null, { desfasada: false }])
  })

  it('descartar quita la vista previa y la salida', async () => {
    const { onChange } = pintar('La impresora ya funciona')
    fireEvent.click(await screen.findByRole('button', { name: /traduccion_ui.vista_previa/ }))
    await screen.findByLabelText('traduccion_ui.lo_que_recibira')
    fireEvent.click(screen.getByRole('button', { name: /traduccion_ui.descartar/ }))
    await waitFor(() => expect(screen.queryByLabelText('traduccion_ui.lo_que_recibira')).toBeNull())
    expect(ultimaLlamada(onChange)).toEqual([null, { desfasada: false }])
  })
})
