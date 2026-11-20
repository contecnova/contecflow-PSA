/**
 * Grabador de reuniones desde el navegador (19-11-2026).
 *
 * - Fuente: micrófono (`getUserMedia`) o audio de una pestaña
 *   (`getDisplayMedia` con vídeo, que el navegador exige; se para el vídeo y
 *   solo se graban las pistas de audio).
 * - Aviso de grabación obligatorio: sin marcar «He avisado a los asistentes»
 *   no se puede empezar (el servidor también lo exige: `reuniones_sin_aviso`).
 * - Trozos de ~30 s: en lugar de `start(timeslice)` (cuyos trozos, salvo el
 *   primero, no llevan cabecera WebM y no se pueden transcribir sueltos) se
 *   cierra y se abre un `MediaRecorder` nuevo sobre la misma pista cada 30 s
 *   de grabación (las pausas no cuentan). Cada trozo es un fichero completo.
 * - Subida en cola secuencial con `seq` y `offset_ms` acumulado y dos
 *   reintentos; «Terminar» espera a que se suban los pendientes y llama a
 *   `/finish`. Las pistas se liberan al terminar o al desmontar.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Mic, MonitorSpeaker, Pause, Play, Plus, Square, Trash2 } from 'lucide-react'
import { Button, Checkbox, IconButton, Input, Modal, Segmentado, StatusBadge } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { reunionesApi } from '../../services/api/reuniones'
import type { ParticipanteIn } from '../../services/api/reuniones'
import { CLAVES, mmss } from './comun'
import './Reuniones.css'

/** Duración de cada trozo (ms de grabación, sin contar pausas). */
export const DURACION_DE_TROZO_MS = 30_000
const REINTENTOS = 2
const TIPO_PREFERIDO = 'audio/webm;codecs=opus'

type Fuente = 'microphone' | 'tab'
type Fase = 'preparar' | 'grabando' | 'terminando'

interface Props {
  onClose: () => void
  /** La reunión ya creada y terminada (para abrir su detalle). */
  onCreada?: (id: string) => void
}

const espera = (ms: number) => new Promise(r => setTimeout(r, ms))

function tipoDeGrabacion(): string | undefined {
  try {
    return typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported?.(TIPO_PREFERIDO) ? TIPO_PREFERIDO : undefined
  } catch { return undefined }
}

export default function GrabadorDeReunion({ onClose, onCreada }: Props) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()

  const [fase, setFase] = useState<Fase>('preparar')
  const [fuente, setFuente] = useState<Fuente>('microphone')
  const [titulo, setTitulo] = useState('')
  const [avisado, setAvisado] = useState(false)
  const [participantes, setParticipantes] = useState<ParticipanteIn[]>([])
  const [segundos, setSegundos] = useState(0)
  const [pausado, setPausado] = useState(false)
  const [pendientes, setPendientes] = useState(0)
  const [subidos, setSubidos] = useState(0)
  const [fallidos, setFallidos] = useState(0)
  const [empezando, setEmpezando] = useState(false)

  const reunionRef = useRef<string | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const recRef = useRef<MediaRecorder | null>(null)
  const seqRef = useRef(0)
  const colaRef = useRef<Promise<void>>(Promise.resolve())
  const acumuladoRef = useRef(0)
  const reanudadoEnRef = useRef<number | null>(null)
  const inicioDeTrozoRef = useRef(0)
  const relojRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const terminandoRef = useRef(false)

  const transcurrido = () => acumuladoRef.current + (reanudadoEnRef.current ? Date.now() - reanudadoEnRef.current : 0)

  const liberar = useCallback(() => {
    if (relojRef.current) { clearInterval(relojRef.current); relojRef.current = null }
    streamRef.current?.getTracks().forEach(p => p.stop())
    streamRef.current = null
  }, [])

  // Al desmontar: parar todo (sin subir nada más).
  useEffect(() => () => {
    terminandoRef.current = true
    const rec = recRef.current
    if (rec && rec.state !== 'inactive') { rec.onstop = null; try { rec.stop() } catch { /* ya parado */ } }
    liberar()
  }, [liberar])

  // Avisar antes de cerrar la pestaña con una grabación en curso.
  useEffect(() => {
    if (fase === 'preparar') return undefined
    const avisar = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', avisar)
    return () => window.removeEventListener('beforeunload', avisar)
  }, [fase])

  const encolar = (trozo: Blob, offsetMs: number) => {
    const id = reunionRef.current
    if (!id) return
    const seq = seqRef.current++
    setPendientes(n => n + 1)
    colaRef.current = colaRef.current.then(async () => {
      for (let intento = 0; intento <= REINTENTOS; intento++) {
        try {
          await reunionesApi.subirTrozo(id, trozo, seq, offsetMs)
          setSubidos(n => n + 1)
          break
        } catch (e) {
          if (intento === REINTENTOS) {
            setFallidos(n => n + 1)
            toast.error(extractErr(e, t('reuniones.grabador.error_subida')))
          } else {
            await espera(2000 * (intento + 1))
          }
        }
      }
      setPendientes(n => n - 1)
    })
  }

  const abrirTrozo = () => {
    const stream = streamRef.current
    if (!stream) return
    const tipo = tipoDeGrabacion()
    const rec = tipo ? new MediaRecorder(stream, { mimeType: tipo }) : new MediaRecorder(stream)
    const partes: Blob[] = []
    const offset = transcurrido()
    inicioDeTrozoRef.current = offset
    rec.ondataavailable = e => { if (e.data && e.data.size > 0) partes.push(e.data) }
    rec.onstop = () => {
      const trozo = new Blob(partes, { type: rec.mimeType || 'audio/webm' })
      if (trozo.size > 0) encolar(trozo, offset)
    }
    rec.start()
    recRef.current = rec
  }

  /** Cierra el trozo actual (se encola en su `onstop`) y abre otro si se sigue grabando. */
  const cortar = () => {
    const rec = recRef.current
    if (rec && rec.state !== 'inactive') rec.stop()
    if (!terminandoRef.current) {
      abrirTrozo()
      if (reanudadoEnRef.current === null) recRef.current?.pause()
    }
  }

  const obtenerAudio = async (): Promise<MediaStream> => {
    if (fuente === 'microphone') return navigator.mediaDevices.getUserMedia({ audio: true })
    const pantalla = await navigator.mediaDevices.getDisplayMedia({ audio: true, video: true })
    pantalla.getVideoTracks().forEach(p => { p.stop(); pantalla.removeTrack(p) })
    if (pantalla.getAudioTracks().length === 0) {
      pantalla.getTracks().forEach(p => p.stop())
      throw new Error(t('reuniones.grabador.sin_audio_pestana'))
    }
    return new MediaStream(pantalla.getAudioTracks())
  }

  const empezar = async () => {
    if (!avisado || empezando) return
    if (typeof MediaRecorder === 'undefined' || !navigator.mediaDevices) {
      toast.error(t('reuniones.grabador.no_soportado'))
      return
    }
    setEmpezando(true)
    let stream: MediaStream | null = null
    try {
      stream = await obtenerAudio()
    } catch (e) {
      setEmpezando(false)
      toast.error(e instanceof Error && e.message ? e.message : t('reuniones.grabador.sin_permiso'))
      return
    }
    try {
      const r = await reunionesApi.crear({
        title: titulo.trim() || t('reuniones.grabador.titulo_por_defecto'),
        origin: 'recording',
        source: fuente,
        notice_confirmed: true,
        participants: participantes.filter(p => p.name.trim()).map(p => ({ name: p.name.trim(), email: p.email?.trim() || null })),
      })
      reunionRef.current = r.id
    } catch (e) {
      stream.getTracks().forEach(p => p.stop())
      setEmpezando(false)
      toast.error(extractErr(e, t('reuniones.grabador.error_crear')))
      return
    }
    streamRef.current = stream
    // Si se deja de compartir la pestaña o se desconecta el micrófono, se termina.
    stream.getAudioTracks().forEach(p => p.addEventListener('ended', () => { void terminar() }))
    acumuladoRef.current = 0
    reanudadoEnRef.current = Date.now()
    abrirTrozo()
    relojRef.current = setInterval(() => {
      const ms = transcurrido()
      setSegundos(Math.floor(ms / 1000))
      if (reanudadoEnRef.current !== null && ms - inicioDeTrozoRef.current >= DURACION_DE_TROZO_MS) cortar()
    }, 1000)
    setFase('grabando')
    setEmpezando(false)
    qc.invalidateQueries({ queryKey: CLAVES.lista })
  }

  const pausar = () => {
    const rec = recRef.current
    if (!rec || reanudadoEnRef.current === null) return
    if (rec.state === 'recording') rec.pause()
    acumuladoRef.current += Date.now() - reanudadoEnRef.current
    reanudadoEnRef.current = null
    setPausado(true)
  }

  const reanudar = () => {
    const rec = recRef.current
    if (!rec || reanudadoEnRef.current !== null) return
    if (rec.state === 'paused') rec.resume()
    reanudadoEnRef.current = Date.now()
    setPausado(false)
  }

  async function terminar() {
    if (terminandoRef.current) return
    terminandoRef.current = true
    setFase('terminando')
    if (relojRef.current) { clearInterval(relojRef.current); relojRef.current = null }
    const rec = recRef.current
    if (rec && rec.state !== 'inactive') {
      await new Promise<void>(res => { rec.addEventListener('stop', () => res(), { once: true }); rec.stop() })
    }
    // El `onstop` del trozo ya lo ha encolado: esperar a que la cola se vacíe.
    await Promise.resolve()
    await colaRef.current
    liberar()
    const id = reunionRef.current
    if (!id) { onClose(); return }
    try {
      await reunionesApi.terminar(id)
      toast.success(t('reuniones.grabador.terminada'))
    } catch (e) {
      toast.error(extractErr(e, t('reuniones.grabador.error_terminar')))
    }
    qc.invalidateQueries({ queryKey: CLAVES.lista })
    qc.invalidateQueries({ queryKey: CLAVES.detalle(id) })
    onCreada?.(id)
    onClose()
  }

  const cambiarParticipante = (i: number, campo: keyof ParticipanteIn, valor: string) =>
    setParticipantes(ps => ps.map((p, j) => (j === i ? { ...p, [campo]: valor } : p)))

  const preparando = fase === 'preparar'

  return (
    <Modal open size="lg" title={t('reuniones.grabador.titulo')} subtitle={t('reuniones.grabador.subtitulo')}
      onClose={preparando ? onClose : () => undefined}>
      {preparando ? (
        <div className="reu-form">
          <Input className="u-col-full" label={t('reuniones.campo.titulo')} value={titulo}
            onChange={e => setTitulo(e.target.value)} placeholder={t('reuniones.grabador.titulo_por_defecto')} />
          <div className="u-col-full reu-campo">
            <span className="reu-campo__etiqueta">{t('reuniones.grabador.fuente')}</span>
            <Segmentado aria-label={t('reuniones.grabador.fuente')} valor={fuente} onChange={v => setFuente(v as Fuente)}
              opciones={[
                { valor: 'microphone', etiqueta: t('reuniones.grabador.microfono'), icon: <Mic size={14} /> },
                { valor: 'tab', etiqueta: t('reuniones.grabador.pestana'), icon: <MonitorSpeaker size={14} /> },
              ]} />
            <span className="u-text3-xs">{fuente === 'tab' ? t('reuniones.grabador.pestana_ayuda') : t('reuniones.grabador.microfono_ayuda')}</span>
          </div>

          <div className="u-col-full reu-participantes-alta">
            <span className="reu-campo__etiqueta">{t('reuniones.grabador.participantes_opcional')}</span>
            {participantes.map((p, i) => (
              <div key={i} className="reu-fila-participante">
                <Input aria-label={t('reuniones.campo.nombre')} placeholder={t('reuniones.campo.nombre')} value={p.name}
                  onChange={e => cambiarParticipante(i, 'name', e.target.value)} />
                <Input aria-label={t('reuniones.campo.correo')} placeholder={t('reuniones.campo.correo')} type="email" value={p.email ?? ''}
                  onChange={e => cambiarParticipante(i, 'email', e.target.value)} />
                <IconButton ariaLabel={t('reuniones.quitar')} onClick={() => setParticipantes(ps => ps.filter((_, j) => j !== i))}>
                  <Trash2 size={14} aria-hidden />
                </IconButton>
              </div>
            ))}
            <div>
              <Button variant="ghost" size="sm" icon={<Plus size={14} />} onClick={() => setParticipantes(ps => [...ps, { name: '', email: '' }])}>
                {t('reuniones.anadir_participante')}
              </Button>
            </div>
          </div>

          <div className="u-col-full reu-aviso reu-aviso--warning" role="note">
            <p className="reu-aviso__texto">{t('reuniones.grabador.aviso_texto')}</p>
            <Checkbox checked={avisado} onChange={setAvisado} label={t('reuniones.grabador.he_avisado')} data-testid="aviso-grabacion" />
          </div>

          <div className="u-col-full reu-botonera">
            <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
            <Button icon={<Mic size={14} />} onClick={() => { void empezar() }} disabled={!avisado} loading={empezando}>
              {t('reuniones.grabador.empezar')}
            </Button>
          </div>
        </div>
      ) : (
        <div className="reu-grabando">
          <div className="reu-grabando__reloj" aria-live="off">
            <span className={`reu-punto${pausado ? ' reu-punto--pausa' : ''}`} aria-hidden />
            <span className="reu-grabando__tiempo">{mmss(segundos * 1000)}</span>
            <StatusBadge kind={pausado ? 'warning' : 'danger'} caps={false}>
              {pausado ? t('reuniones.grabador.en_pausa') : t('reuniones.estado.grabando')}
            </StatusBadge>
          </div>
          <div className="reu-grabando__subida" aria-live="polite">
            {t('reuniones.grabador.trozos', { subidos, pendientes })}
            {fallidos > 0 && <span className="u-danger"> · {t('reuniones.grabador.fallidos', { n: fallidos })}</span>}
          </div>
          {fase === 'terminando' && <p className="u-text3-xs">{t('reuniones.grabador.terminando')}</p>}
          <div className="reu-botonera">
            {pausado
              ? <Button variant="secondary" icon={<Play size={14} />} onClick={reanudar} disabled={fase !== 'grabando'}>{t('reuniones.grabador.reanudar')}</Button>
              : <Button variant="secondary" icon={<Pause size={14} />} onClick={pausar} disabled={fase !== 'grabando'}>{t('reuniones.grabador.pausar')}</Button>}
            <Button variant="danger" icon={<Square size={14} />} onClick={() => { void terminar() }} loading={fase === 'terminando'}>
              {t('reuniones.grabador.terminar')}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
