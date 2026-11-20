// Asistente de reuniones en una llamada del chat (19-11-2026, origen `chat_call`):
// activar exige la casilla del aviso, el banner pide consentimiento cuando falta,
// y la grabación por trozos abre un MediaRecorder nuevo por trozo (cada uno con su cabecera).
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, renderHook, screen, fireEvent } from '@testing-library/react'

vi.mock('../i18n/AppLangContext', () => {
  const t = (k: string) => k
  return { useAppLang: () => ({ t, lang: 'es' }), useAppT: () => t }
})
vi.mock('../context/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))

import { BannerDelAsistente, ModalActivarAsistente } from '../components/reuniones/AsistenteEnLlamada'
import { useGrabacionPorTrozos } from '../components/reuniones/grabacionPorTrozos'
import type { AsistenteDeLlamada } from '../services/api/reuniones'

const ESTADO: AsistenteDeLlamada = {
  call_id: 'c1', active: true, meeting_id: 'm1', status: 'grabando', notice_required: true,
  notice_text: 'Esta llamada se graba para el acta', require_consent: true, my_participant_id: 'p1', my_consent: null,
}

describe('activar el asistente en la llamada', () => {
  it('no deja activar sin marcar «He avisado a los asistentes»', () => {
    const onActivar = vi.fn()
    render(<ModalActivarAsistente textoAviso={ESTADO.notice_text} onActivar={onActivar} onClose={() => undefined} />)
    expect(screen.getByText('Esta llamada se graba para el acta')).toBeTruthy()
    const boton = screen.getByRole('button', { name: /reuniones\.llamada\.activar/ }) as HTMLButtonElement
    expect(boton.disabled).toBe(true)
    fireEvent.click(boton)
    expect(onActivar).not.toHaveBeenCalled()

    fireEvent.click(screen.getByLabelText('reuniones.grabador.he_avisado'))
    expect(boton.disabled).toBe(false)
    fireEvent.click(boton)
    expect(onActivar).toHaveBeenCalledTimes(1)
  })
})

describe('banner del asistente', () => {
  it('pide consentimiento cuando se exige y aún no hay respuesta', () => {
    const onConsentir = vi.fn()
    render(<BannerDelAsistente estado={ESTADO} onConsentir={onConsentir} onParar={() => undefined} />)
    expect(screen.getByText('reuniones.llamada.banner')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'reuniones.llamada.consiento' }))
    expect(onConsentir).toHaveBeenCalledWith(true)
    fireEvent.click(screen.getByRole('button', { name: 'reuniones.llamada.no_consiento' }))
    expect(onConsentir).toHaveBeenCalledWith(false)
  })

  it('no pide consentimiento si ya respondió o si no se exige', () => {
    const { rerender } = render(<BannerDelAsistente estado={{ ...ESTADO, my_consent: true }} onConsentir={vi.fn()} onParar={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'reuniones.llamada.consiento' })).toBeNull()
    rerender(<BannerDelAsistente estado={{ ...ESTADO, require_consent: false }} onConsentir={vi.fn()} onParar={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'reuniones.llamada.consiento' })).toBeNull()
  })

  it('sin permiso para parar no enseña «Parar asistente»', () => {
    render(<BannerDelAsistente estado={{ ...ESTADO, can_stop: false }} onConsentir={vi.fn()} onParar={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /reuniones\.llamada\.parar/ })).toBeNull()
  })
})

describe('grabación por trozos completos', () => {
  const creados: FakeRecorder[] = []
  class FakeRecorder {
    static isTypeSupported = () => true
    state: 'inactive' | 'recording' = 'inactive'
    mimeType = 'audio/webm;codecs=opus'
    ondataavailable: ((e: { data: Blob }) => void) | null = null
    onstop: (() => void) | null = null
    constructor() { creados.push(this) }
    start() { this.state = 'recording' }
    stop() {
      this.state = 'inactive'
      this.ondataavailable?.({ data: new Blob(['x'], { type: 'audio/webm' }) })
      this.onstop?.()
    }
  }
  const pista = { kind: 'audio' } as MediaStreamTrack
  const stream = { getAudioTracks: () => [pista] } as unknown as MediaStream

  beforeEach(() => {
    creados.length = 0
    vi.useFakeTimers()
    ;(globalThis as { MediaRecorder?: unknown }).MediaRecorder = FakeRecorder
  })
  afterEach(() => {
    vi.useRealTimers()
    delete (globalThis as { MediaRecorder?: unknown }).MediaRecorder
  })

  it('cierra y abre un grabador nuevo en cada trozo y entrega cada uno', () => {
    const onTrozo = vi.fn()
    const { unmount } = renderHook(() => useGrabacionPorTrozos({ activo: true, obtenerStream: () => stream, onTrozo, duracionMs: 1000 }))
    expect(creados).toHaveLength(1)
    vi.advanceTimersByTime(3000)
    expect(creados).toHaveLength(4)
    expect(onTrozo).toHaveBeenCalledTimes(3)
    unmount()
    expect(onTrozo).toHaveBeenCalledTimes(4)
    expect(creados.every(r => r.state === 'inactive')).toBe(true)
  })

  it('sin activar no graba', () => {
    renderHook(() => useGrabacionPorTrozos({ activo: false, obtenerStream: () => stream, onTrozo: vi.fn() }))
    expect(creados).toHaveLength(0)
  })
})
