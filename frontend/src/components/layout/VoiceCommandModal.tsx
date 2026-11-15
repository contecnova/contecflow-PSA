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
import { type CSSProperties, useState, useRef, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { voiceApi } from '../../services/api'
import type { AccionDeVozPendiente, ComandoDeVozTranscrito } from '../../services/api/tipos-analitica'
import { useToast } from '../../context/ToastContext'
import { Mic, Square, X } from 'lucide-react'
import { useAppLang } from '../../i18n/AppLangContext'
import { useDialogo } from '../ui'
import './VoiceCommandModal.css'


function _formatPendingAction(pa: AccionDeVozPendiente | undefined | null): string | null {
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
  const [transcribeResult, setTranscribeResult] = useState<ComandoDeVozTranscrito | null>(null)
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
        // El evento de error de MediaRecorder lleva el fallo en `error` (no está en lib.dom).
        const err = (e as Event & { error?: DOMException }).error
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
    onSuccess: (data) => {
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
    onSuccess: (data) => {
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
    <div role="presentation" onClick={onClose} className="voicecom-sx1">
      <div ref={dialogRef} role="dialog" aria-modal="true" tabIndex={-1}
        onClick={e => e.stopPropagation()}
        onKeyDown={e => { if (e.key === 'Escape') onClose() }} className="voicecom-sx2">
        {/* Header */}
        <div className="u-row-between-mb16">
          <h3 className="vocomo-box-1">
            {traducir('voicecommandmodal.comando_de_voz')}
          </h3>
          <button onClick={onClose}
            className="vocomo-box-2">
            <X size={18} />
          </button>
        </div>

        {/* Error banner */}
        {error && (
          <div className="voicecom-sx3">
            ⚠ {error}
          </div>
        )}

        {/* Recording state */}
        {!audioBlob && !transcribeResult && (
          <div className="vocomo-box-3">
            <div className={`vocomo-row-4 voicecom-sx4 voice-command-modal-e1 ${recording ? 'voice-command-modal-m2' : 'voice-command-modal-m3'}`} style={{ '--voice-command-modal-border': `2px solid ${recording ? 'var(--danger)' : 'var(--accent)'}` } as CSSProperties}>
              <Mic size={42} color={recording ? 'var(--danger)' : 'var(--accent)'} />
            </div>
            <div className="vocomo-box-4">
              {recording
                ? '🔴 Grabando… Habla con claridad. Click "Detener" cuando termines.'
                : 'Ejemplos: "imputa 3 horas al proyecto Acme", "crea un ticket para el portal", "¿cuántas horas llevo esta semana?"'}
            </div>
            {!recording ? (
              <button onClick={handleStart} className="vocomo-row-1">
                <Mic size={16} /> {traducir('call.record')}
              </button>
            ) : (
              <button onClick={handleStop} className="vocomo-row-2">
                <Square size={14} /> {traducir('voicecommand.detener')}
              </button>
            )}
          </div>
        )}

        {/* Audio ready → upload */}
        {audioBlob && !transcribeResult && (
          <div className="vocomo-box-5">
            <div className="vocomo-box-6">
              {traducir('voicecommand.audio_grabado_kb', { kb: Math.round(audioBlob.size / 1024) })}
            </div>
            <audio src={URL.createObjectURL(audioBlob)} controls aria-label={traducir('voicecommand.audio_grabado_2')}
              className="vocomo-box-7" />
            <div className="vocomo-row-3">
              <button onClick={() => { setAudioBlob(null); chunksRef.current = [] }}
                disabled={isTranscribing}
                className="vocomo-box-8">
                {traducir('voicecommand.re_grabar')}
              </button>
              <button className={`vocomo-box-13 ${isTranscribing ? 'voice-command-modal-m4' : 'voice-command-modal-m5'}`} onClick={() => transcribe()} disabled={isTranscribing}>
                {isTranscribing ? '⏳ Transcribiendo…' : '→ Transcribir e interpretar'}
              </button>
            </div>
          </div>
        )}

        {/* Transcription result */}
        {transcribeResult && (
          <div>
            <div className="u-mb-14">
              <div className="vocomo-box-9">
                {traducir('voicecommand.tu_comando')}
              </div>
              <div className="vocomo-box-10">
                "{transcribeResult.whisper_transcript}"
              </div>
            </div>

            <div className="u-mb-14">
              <div className="vocomo-box-9">
                {traducir('voicecommandmodal.interpretacion')}
              </div>
              <div className="vocomo-box-11">
                <div><strong>Intent:</strong> {transcribeResult.intent || 'unknown'}</div>
                <div className="vocomo-sp-1">{transcribeResult.action}</div>
              </div>
            </div>

            {pendingAction ? (
              <>
                <div className="vocomo-box-15">
                  <strong>{traducir('voicecommandmodal.confirmacion_requerida')}</strong>
                  <div className="vocomo-sp-1">{pendingLabel}</div>
                </div>
                <div className="u-actions-8">
                  <button onClick={onClose} disabled={isConfirming}
                    className="vocomo-box-8">
                    {traducir('voicecommand.cancelar')}
                  </button>
                  <button className={`vocomo-box-14 ${isConfirming ? 'voice-command-modal-m4' : 'voice-command-modal-m5'}`} onClick={() => confirm()} disabled={isConfirming}>
                    {isConfirming ? '⏳ Ejecutando…' : '✓ Confirmar y ejecutar'}
                  </button>
                </div>
              </>
            ) : (
              <div className="u-row-end">
                <button onClick={onClose}
                  className="vocomo-box-12">
                  {traducir('common.close')}
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
