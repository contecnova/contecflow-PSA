/**
 * VoiceCommandModal — Item I25 (UI de comandos de voz).
 *
 * Flujo:
 *   1. Usuario abre modal → estado "idle"
 *   2. Click "🎙 Grabar" → MediaRecorder captura audio del micrófono
 *   3. Click "■ Detener" → POST audio a /voice/transcribe (dry-run forzado)
 *   4. Backend devuelve { whisper_transcript, intent, entities, action,
 *      pending_action? }
 *   5. Modal muestra transcript + acción interpretada
 *   6. Si pending_action existe: botones "✓ Confirmar" → POST /voice/command
 *      con confirm=true (ejecuta) / "✗ Cancelar" (cierra sin acción)
 *   7. Si NO hay pending_action (query/get_summary/unknown): solo botón Cerrar
 *
 * Permisos del navegador: getUserMedia({audio:true}) requiere HTTPS o
 * localhost. Si el user deniega → error claro.
 */
import { useState, useRef, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { voiceApi } from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { Mic, Square, X } from 'lucide-react'
import { useAppLang } from '../../i18n/AppLangContext'
import { useDialogo } from '../ui'


// TODO type: voice pending_action payload — needs shared type from voiceApi
interface PendingAction {
  type: string
  hours?: number
  project_name?: string
  title?: string
  priority?: string
  [key: string]: unknown
}

interface TranscribeResult {
  whisper_transcript?: string
  intent?: string
  entities?: Record<string, unknown>
  action?: string
  pending_action?: PendingAction
}

function _formatPendingAction(pa: PendingAction | undefined | null): string | null {
  if (!pa) return null
  switch (pa.type) {
    case 'log_hours':
      return `Imputar ${pa.hours}h en ${pa.project_name}`
    case 'create_ticket':
      return `Crear ticket "${pa.title}" (prioridad ${pa.priority || 'medium'})`
    case 'create_task':
      return `Crear tarea "${pa.title}"` + (pa.project_name ? ` en ${pa.project_name}` : '')
    default:
      return JSON.stringify(pa)
  }
}


interface VoiceCommandModalProps {
  open: boolean
  onClose: () => void
}

export default function VoiceCommandModal({ open, onClose }: VoiceCommandModalProps) {
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const [recording, setRecording] = useState<boolean>(false)
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null)
  const [transcribeResult, setTranscribeResult] = useState<TranscribeResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)

  // Declarada ANTES del efecto que la usa (auditoría 2026-08, P1-6). Estaba
  // debajo: funcionaba por hoisting, pero leer una función del cuerpo del
  // componente antes de declararla es el patrón que marca react-hooks.
  // Sólo toca refs, así que es estable entre renders.
  function _stopMediaTracks() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    mediaRecorderRef.current = null
  }

  // Cleanup al cerrar
  useEffect(() => {
    if (!open) {
      _stopMediaTracks()
      setRecording(false)
      setAudioBlob(null)
      setTranscribeResult(null)
      setError(null)
      chunksRef.current = []
    }
    return () => _stopMediaTracks()
     
  }, [open])

  // ── 1. Start recording ─────────────────────────────────────────────────────
  async function handleStart() {
    setError(null)
    setAudioBlob(null)
    setTranscribeResult(null)
    chunksRef.current = []

    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Tu navegador no soporta grabación de audio. Usa Chrome/Edge/Safari recientes.')
      return
    }

    if (typeof MediaRecorder === 'undefined') {
      setError('Tu navegador no soporta MediaRecorder para grabar audio.')
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // Preferimos un formato pequeño y ampliamente compatible; si el navegador
      // no acepta el primero, probamos alternativas antes de caer al default.
      const preferredMimeTypes = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/ogg',
        'audio/mp4',
      ]
      const mime = preferredMimeTypes.find(type => MediaRecorder.isTypeSupported(type)) || ''

      const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream)
      mediaRecorderRef.current = rec
      rec.onstart = () => setRecording(true)
      rec.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data)
      }
      rec.onerror = (e: Event) => {
        // TODO type: MediaRecorderErrorEvent — DOM types vary across libs
        const err = (e as unknown as { error?: { message?: string } })?.error
        setError(err?.message || 'No se pudo grabar audio con el micrófono.')
        setRecording(false)
        _stopMediaTracks()
      }
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mime || 'audio/webm' })
        setAudioBlob(blob)
        _stopMediaTracks()
      }
      rec.start(1000)
    } catch (err: unknown) {
      const e = err as { name?: string; message?: string } | undefined
      const msg = e?.name === 'NotAllowedError'
        ? 'Permiso de micrófono denegado. Habilítalo en la configuración del navegador.'
        : `No se pudo acceder al micrófono: ${e?.message || String(err)}`
      setError(msg)
    }
  }

  // ── 2. Stop recording — triggers MediaRecorder.onstop → setAudioBlob ──────
  function handleStop() {
    setRecording(false)
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.requestData?.()
      } catch { /* noop */ }
      mediaRecorderRef.current.stop()
    }
  }

  // ── 3. Send audio for transcription (dry-run) ─────────────────────────────
  const { mutate: transcribe, isPending: isTranscribing } = useMutation({
    mutationFn: () => {
      if (!audioBlob) throw new Error('No hay audio para transcribir')
      const fd = new FormData()
      const ext = audioBlob.type.includes('ogg') ? 'ogg' : 'webm'
      fd.append('audio', audioBlob, `voice.${ext}`)
      return voiceApi.transcribe(fd).then(r => r.data)
    },
    onSuccess: (data: TranscribeResult) => {
      setTranscribeResult(data)
    },
    // TODO type: backend error envelope — needs shared type
    onError: (e: { response?: { data?: { detail?: string } }; message?: string }) => {
      const msg = e?.response?.data?.detail || e?.message || 'Error en la transcripción'
      setError(msg)
    },
  })

  // ── 4. Confirm execution of pending_action ────────────────────────────────
  const { mutate: confirm, isPending: isConfirming } = useMutation({
    mutationFn: () =>
      voiceApi.command({
        transcript: transcribeResult?.whisper_transcript || '',
        confirm: true,
      }).then(r => r.data),
    onSuccess: (data: { action?: string }) => {
      toast.success(data?.action || 'Acción ejecutada')
      onClose()
    },
    // TODO type: backend error envelope — needs shared type
    onError: (e: { response?: { data?: { detail?: string } }; message?: string }) => {
      const msg = e?.response?.data?.detail || e?.message || 'Error ejecutando la acción'
      toast.error(msg)
    },
  })
  const dialogRef = useDialogo<HTMLDivElement>(open, onClose)

  if (!open) return null

  const pendingAction = transcribeResult?.pending_action
  const pendingLabel = _formatPendingAction(pendingAction)

  return (
    <div role="presentation" onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)',
      zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" tabIndex={-1}
        onClick={e => e.stopPropagation()}
        onKeyDown={e => { if (e.key === 'Escape') onClose() }}
        style={{
        width: 480, maxWidth: '92vw',
        background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
        borderRadius: 12, padding: '22px 26px',
        boxShadow: '0 20px 60px rgba(0,0,0,0.4)',
      }}>
        {/* Header */}
        <div className="u-row-between-mb16">
          <h3 style={{ margin: 0, fontSize: 'var(--text-md)', fontWeight: 700 }}>
            {traducir('voicecommandmodal.comando_de_voz')}
          </h3>
          <button onClick={onClose}
            style={{ background: 'transparent', border: 'none', color: 'var(--text-2)', fontSize: 20, cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </div>

        {/* Error banner */}
        {error && (
          <div style={{
            background: 'rgba(239,68,68,0.12)', border: '1px solid var(--danger)',
            color: 'var(--danger)', padding: '10px 14px', borderRadius: 8,
            fontSize: 'var(--text-sm)', marginBottom: 14,
          }}>
            ⚠ {error}
          </div>
        )}

        {/* Recording state */}
        {!audioBlob && !transcribeResult && (
          <div style={{ textAlign: 'center', padding: '20px 0' }}>
            <div style={{
              width: 96, height: 96, borderRadius: '50%', margin: '0 auto 18px',
              background: recording ? 'var(--danger-bg, rgba(239,68,68,0.12))' : 'var(--accent-muted)',
              border: `2px solid ${recording ? 'var(--danger)' : 'var(--accent)'}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              animation: recording ? 'voicePulse 1.2s ease-in-out infinite' : 'none',
            }}>
              <Mic size={42} color={recording ? 'var(--danger)' : 'var(--accent)'} />
            </div>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', marginBottom: 16 }}>
              {recording
                ? '🔴 Grabando… Habla con claridad. Click "Detener" cuando termines.'
                : 'Ejemplos: "imputa 3 horas al proyecto Acme", "crea un ticket para el portal", "¿cuántas horas llevo esta semana?"'}
            </div>
            {!recording ? (
              <button onClick={handleStart} style={{
                background: 'var(--accent)', color: 'var(--on-accent)', border: 'none',
                padding: '10px 22px', borderRadius: 8, cursor: 'pointer',
                fontWeight: 600, fontSize: 'var(--text-base)',
                display: 'inline-flex', alignItems: 'center', gap: 8,
              }}>
                <Mic size={16} /> Grabar
              </button>
            ) : (
              <button onClick={handleStop} style={{
                background: 'var(--danger)', color: 'var(--on-accent-light)', border: 'none',
                padding: '10px 22px', borderRadius: 8, cursor: 'pointer',
                fontWeight: 600, fontSize: 'var(--text-base)',
                display: 'inline-flex', alignItems: 'center', gap: 8,
              }}>
                <Square size={14} /> Detener
              </button>
            )}
          </div>
        )}

        {/* Audio ready → upload */}
        {audioBlob && !transcribeResult && (
          <div style={{ textAlign: 'center', padding: '12px 0' }}>
            <div style={{ marginBottom: 12, color: 'var(--success)', fontWeight: 600 }}>
              ✓ Audio grabado ({Math.round(audioBlob.size / 1024)} KB)
            </div>
            <audio src={URL.createObjectURL(audioBlob)} controls
              style={{ width: '100%', marginBottom: 14 }} />
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
              <button onClick={() => { setAudioBlob(null); chunksRef.current = [] }}
                disabled={isTranscribing}
                style={{
                  background: 'var(--surface-3)', color: 'var(--text-2)',
                  border: '1px solid var(--surface-4)', padding: '8px 16px',
                  borderRadius: 8, cursor: 'pointer', fontSize: 'var(--text-sm)',
                }}>
                ↻ Re-grabar
              </button>
              <button onClick={() => transcribe()} disabled={isTranscribing}
                style={{
                  background: 'var(--accent)', color: 'var(--on-accent)',
                  border: 'none', padding: '8px 18px',
                  borderRadius: 8, cursor: 'pointer', fontWeight: 600,
                  fontSize: 'var(--text-sm)', opacity: isTranscribing ? 0.6 : 1,
                }}>
                {isTranscribing ? '⏳ Transcribiendo…' : '→ Transcribir e interpretar'}
              </button>
            </div>
          </div>
        )}

        {/* Transcription result */}
        {transcribeResult && (
          <div>
            <div className="u-mb-14">
              <div style={{
                fontSize: 'var(--text-xs)', color: 'var(--text-3)',
                textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4,
              }}>
                Tu comando
              </div>
              <div style={{
                background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                padding: '10px 14px', borderRadius: 8,
                fontSize: 'var(--text-base)', color: 'var(--text-1)', fontStyle: 'italic',
              }}>
                "{transcribeResult.whisper_transcript}"
              </div>
            </div>

            <div className="u-mb-14">
              <div style={{
                fontSize: 'var(--text-xs)', color: 'var(--text-3)',
                textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4,
              }}>
                {traducir('voicecommandmodal.interpretacion')}
              </div>
              <div style={{
                background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
                padding: '10px 14px', borderRadius: 8, fontSize: 'var(--text-sm)',
              }}>
                <div><strong>Intent:</strong> {transcribeResult.intent || 'unknown'}</div>
                <div style={{ marginTop: 4 }}>{transcribeResult.action}</div>
              </div>
            </div>

            {pendingAction ? (
              <>
                <div style={{
                  background: 'var(--warning-glow, rgba(251,146,60,0.10))',
                  border: '1px solid var(--warning)',
                  padding: '10px 14px', borderRadius: 8, marginBottom: 14,
                  fontSize: 'var(--text-sm)',
                }}>
                  <strong>{traducir('voicecommandmodal.confirmacion_requerida')}</strong>
                  <div style={{ marginTop: 4 }}>{pendingLabel}</div>
                </div>
                <div className="u-actions-8">
                  <button onClick={onClose} disabled={isConfirming}
                    style={{
                      background: 'var(--surface-3)', color: 'var(--text-2)',
                      border: '1px solid var(--surface-4)', padding: '8px 16px',
                      borderRadius: 8, cursor: 'pointer', fontSize: 'var(--text-sm)',
                    }}>
                    ✗ Cancelar
                  </button>
                  <button onClick={() => confirm()} disabled={isConfirming}
                    style={{
                      background: 'var(--success)', color: 'var(--on-accent-light)', border: 'none',
                      padding: '8px 18px', borderRadius: 8, cursor: 'pointer',
                      fontWeight: 600, fontSize: 'var(--text-sm)',
                      opacity: isConfirming ? 0.6 : 1,
                    }}>
                    {isConfirming ? '⏳ Ejecutando…' : '✓ Confirmar y ejecutar'}
                  </button>
                </div>
              </>
            ) : (
              <div className="u-row-end">
                <button onClick={onClose}
                  style={{
                    background: 'var(--accent)', color: 'var(--on-accent)', border: 'none',
                    padding: '8px 18px', borderRadius: 8, cursor: 'pointer',
                    fontWeight: 600, fontSize: 'var(--text-sm)',
                  }}>
                  Cerrar
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <style>{`
        @keyframes voicePulse {
          0%, 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0.5); }
          50%      { box-shadow: 0 0 0 14px rgba(239,68,68,0); }
        }
      `}</style>
    </div>
  )
}
