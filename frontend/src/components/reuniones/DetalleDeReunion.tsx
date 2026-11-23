/**
 * Detalle de una reunión (19-11-2026): cabecera con estado, origen, proyecto
 * y cliente; selector de idioma (por defecto el de la interfaz; dice si está
 * traducido o por qué no); avisos (bloqueo legal, consentimiento pendiente,
 * error, transcripción purgada); resumen, decisiones, riesgos y preguntas
 * abiertas; acciones; preguntar a la IA; transcripción; participantes y
 * consentimiento; audio; línea de tiempo.
 *
 * Mientras la reunión está en curso (bot, grabación, análisis) se refresca
 * cada 5 s.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, Bot, Briefcase, Building2, CalendarDays, CheckCircle2, Clock, FileDown, FileText, HelpCircle,
  History, Languages, Lock, Pencil, RefreshCw, Send, ShieldAlert, Sparkles, Trash2,
} from 'lucide-react'
import {
  Button, Card, ClientSelect, FormField, Input, Modal, ProjectSelect, Section, Select, Spinner,
} from '../ui'
import { useAppLang } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { downloadBlob, extractErr, fmtDate, fmtDateTime } from '../../utils/helpers'
import { LANGUAGES } from '../../i18n/portalTranslations'
import { reunionesApi } from '../../services/api/reuniones'
import type { FormatoTranscripcion, ReunionDetalle } from '../../services/api/reuniones'
import { CLAVES, EstadoDeReunion, OrigenDeReunion, REFRESCO_EN_CURSO_MS, enCurso } from './comun'
import AccionesDeReunion from './AccionesDeReunion'
import TranscripcionDeReunion from './TranscripcionDeReunion'
import ParticipantesDeReunion from './ParticipantesDeReunion'
import AudioDeReunion from './AudioDeReunion'
import './Reuniones.css'

interface Props {
  id: string
  segmentoResaltado?: string | null
  onBorrada?: () => void
}

function ListaDeTextos({ titulo, icono, textos, tono }: { titulo: string; icono: ReactNode; textos: string[]; tono: 'ok' | 'riesgo' | 'pregunta' }) {
  if (textos.length === 0) return null
  return (
    <Card>
      <Section title={<span className="reu-seccion">{icono}{titulo}</span>}>
        <ul className="reu-lista">
          {textos.map((d, i) => <li key={i} className={`reu-punto-texto reu-punto-texto--${tono}`}>{d}</li>)}
        </ul>
      </Section>
    </Card>
  )
}

function ModalEditar({ reunion, onClose }: { reunion: ReunionDetalle; onClose: () => void }) {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [titulo, setTitulo] = useState(reunion.title)
  const [proyecto, setProyecto] = useState(reunion.project_id ?? '')
  const [cliente, setCliente] = useState(reunion.client_id ?? '')
  const guardar = useMutation({
    mutationFn: () => reunionesApi.editar(reunion.id, { title: titulo.trim(), project_id: proyecto || null, client_id: cliente || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CLAVES.detalle(reunion.id) })
      qc.invalidateQueries({ queryKey: CLAVES.lista })
      onClose()
    },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <Modal open title={t('reuniones.detalle.editar')} onClose={onClose}>
      <div className="reu-form reu-form--una">
        <Input label={t('reuniones.campo.titulo')} required value={titulo} onChange={e => setTitulo(e.target.value)} />
        <FormField label={t('reuniones.campo.proyecto')}><ProjectSelect value={proyecto} onChange={id => setProyecto(id)} /></FormField>
        <FormField label={t('reuniones.campo.cliente')}><ClientSelect value={cliente} onChange={id => setCliente(id)} /></FormField>
        <div className="reu-botonera">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button loading={guardar.isPending} disabled={!titulo.trim()} onClick={() => guardar.mutate()}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function PreguntarALaIA({ id }: { id: string }) {
  const { t } = useAppLang()
  const toast = useToast()
  const [pregunta, setPregunta] = useState('')
  const preguntar = useMutation({
    mutationFn: () => reunionesApi.preguntar(id, pregunta.trim()),
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <Card>
      <Section title={<span className="reu-seccion"><Sparkles size={16} aria-hidden />{t('reuniones.preguntar.titulo')}</span>}>
        <div className="reu-preguntar">
          <Input aria-label={t('reuniones.preguntar.titulo')} placeholder={t('reuniones.preguntar.placeholder')} value={pregunta}
            onChange={e => setPregunta(e.target.value)} />
          <Button icon={<Send size={14} />} loading={preguntar.isPending} disabled={!pregunta.trim()} onClick={() => preguntar.mutate()}>
            {t('reuniones.preguntar.enviar')}
          </Button>
        </div>
        {preguntar.data?.answer && <p className="reu-respuesta" aria-live="polite">{preguntar.data.answer}</p>}
      </Section>
    </Card>
  )
}

export default function DetalleDeReunion({ id, segmentoResaltado, onBorrada }: Props) {
  const { t, lang } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [idioma, setIdioma] = useState<string>(lang)
  const [editar, setEditar] = useState(false)

  const { data: r, isLoading } = useQuery({
    queryKey: [...CLAVES.detalle(id), idioma],
    queryFn: () => reunionesApi.detalle(id, idioma),
    refetchInterval: q => (enCurso(q.state.data?.status) ? REFRESCO_EN_CURSO_MS : false),
  })

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: CLAVES.detalle(id) })
    qc.invalidateQueries({ queryKey: CLAVES.lista })
  }
  const alFallar = (e: unknown) => toast.error(extractErr(e))

  const reprocesar = useMutation({ mutationFn: () => reunionesApi.reprocesar(id), onSuccess: () => { toast.success(t('reuniones.detalle.reprocesando')); refrescar() }, onError: alFallar })
  const acta = useMutation({ mutationFn: () => reunionesApi.generarActa(id), onSuccess: () => { toast.success(t('reuniones.detalle.acta_generada')); refrescar() }, onError: alFallar })
  const sacarBot = useMutation({ mutationFn: () => reunionesApi.sacarBot(id), onSuccess: refrescar, onError: alFallar })
  const eliminar = useMutation({
    mutationFn: () => reunionesApi.borrar(id),
    onSuccess: () => { toast.success(t('reuniones.detalle.borrada')); qc.invalidateQueries({ queryKey: CLAVES.lista }); onBorrada?.() },
    onError: alFallar,
  })
  const descargar = useMutation({
    mutationFn: async (f: FormatoTranscripcion) => {
      const blob = await reunionesApi.transcripcion(id, f)
      downloadBlob(blob, `reunion-${id}.${f}`)
    },
    onError: alFallar,
  })

  if (isLoading || !r) return <Spinner />

  const gestor = r.permissions.manage
  const botActivo = !!r.bot && ['programada', 'bot_unido', 'grabando'].includes(r.status)
  const traduccion = r.translation?.status ?? 'original'
  const textoTraduccion = traduccion === 'translated'
    ? t('reuniones.idioma.traducido', { de: r.original_language ?? '—' })
    : traduccion === 'original'
      ? t('reuniones.idioma.original')
      : `${t(`reuniones.idioma.${traduccion}`)}${r.translation.reason ? ` (${t(`reuniones.idioma.motivo_${r.translation.reason}`, r.translation.reason)})` : ''}`

  return (
    <div className="u-stack-16">
      <Card>
        <div className="reu-cab">
          <div className="u-flex1-min0">
            <h2 className="reu-cab__titulo">{r.title}</h2>
            <div className="reu-cab__meta">
              <EstadoDeReunion estado={r.status} />
              <OrigenDeReunion origen={r.origin} />
              <span className="reu-meta"><CalendarDays size={14} aria-hidden />{fmtDate(r.meeting_date || r.created_at)}</span>
              {r.duration_min != null && <span className="reu-meta"><Clock size={14} aria-hidden />{t('reuniones.minutos', { n: r.duration_min })}</span>}
              {r.project_name && <span className="reu-meta"><Briefcase size={14} aria-hidden />{r.project_name}</span>}
              {r.client_name && <span className="reu-meta"><Building2 size={14} aria-hidden />{r.client_name}</span>}
              {r.bot && <span className="reu-meta"><Bot size={14} aria-hidden />{t('reuniones.detalle.bot_estado', { estado: r.bot.status ?? '—' })}</span>}
            </div>
          </div>
          <div className="reu-cab__idioma">
            <Select tamano="sm" label={<span className="reu-meta"><Languages size={14} aria-hidden />{t('reuniones.idioma.ver_en')}</span>}
              value={idioma} placeholder={false} onChange={e => setIdioma(e.target.value)}
              options={LANGUAGES.map(l => ({ value: l.code, label: l.label }))} />
            <span className="u-text3-xs" data-testid="estado-traduccion">{textoTraduccion}</span>
          </div>
        </div>
        <div className="reu-cab__botones">
          {gestor && <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={() => setEditar(true)}>{t('reuniones.detalle.editar')}</Button>}
          {gestor && (
            <Button size="sm" variant="secondary" icon={<FileText size={14} />} loading={acta.isPending} onClick={() => acta.mutate()}
              disabled={r.status !== 'lista'}>
              {r.minutes_document_id ? t('reuniones.detalle.regenerar_acta') : t('reuniones.detalle.generar_acta')}
            </Button>
          )}
          {gestor && !enCurso(r.status) && (
            <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} loading={reprocesar.isPending} onClick={() => reprocesar.mutate()}>
              {t('reuniones.detalle.reprocesar')}
            </Button>
          )}
          {gestor && botActivo && (
            <Button size="sm" variant="secondary" icon={<Bot size={14} />} loading={sacarBot.isPending} onClick={() => sacarBot.mutate()}>
              {t('reuniones.detalle.sacar_bot')}
            </Button>
          )}
          {!r.transcript_purged && r.segments.length > 0 && (
            <>
              <Button size="sm" variant="ghost" icon={<FileDown size={14} />} onClick={() => descargar.mutate('txt')}>{t('reuniones.detalle.descargar_txt')}</Button>
              <Button size="sm" variant="ghost" icon={<FileDown size={14} />} onClick={() => descargar.mutate('vtt')}>{t('reuniones.detalle.descargar_vtt')}</Button>
            </>
          )}
          {gestor && (
            <Button size="sm" variant="danger" icon={<Trash2 size={14} />} disabled={r.legal_hold} loading={eliminar.isPending}
              onClick={async () => { if (await confirmar({ title: t('reuniones.detalle.borrar_titulo'), message: t('reuniones.detalle.borrar_desc', { titulo: r.title }), danger: true })) eliminar.mutate() }}
              title={r.legal_hold ? t('reuniones.detalle.bloqueo_legal') : undefined}>
              {t('reuniones.detalle.borrar')}
            </Button>
          )}
        </div>
      </Card>

      {r.legal_hold && (
        <div className="reu-aviso reu-aviso--info" role="note"><Lock size={16} aria-hidden /><span>{t('reuniones.detalle.bloqueo_legal')}</span></div>
      )}
      {r.status === 'esperando_consentimiento' && (
        <div className="reu-aviso reu-aviso--warning" role="status"><ShieldAlert size={16} aria-hidden /><span>{t('reuniones.detalle.esperando_consentimiento')}</span></div>
      )}
      {r.status === 'error' && (
        <div className="reu-aviso reu-aviso--danger" role="alert">
          <AlertTriangle size={16} aria-hidden />
          <span>{r.error_code ? t(`err_srv.${r.error_code}`, t('reuniones.detalle.error_generico')) : t('reuniones.detalle.error_generico')}</span>
        </div>
      )}
      {enCurso(r.status) && (
        <div className="reu-aviso reu-aviso--info" role="status"><Spinner size={14} /><span>{t(`reuniones.detalle.en_curso_${r.status}`)}</span></div>
      )}

      {r.summary && (
        <Card>
          <Section title={<span className="reu-seccion"><FileText size={16} aria-hidden />{t('reuniones.detalle.resumen')}</span>}>
            <p className="reu-resumen">{r.summary}</p>
          </Section>
        </Card>
      )}
      <ListaDeTextos titulo={t('reuniones.detalle.decisiones', { n: r.decisions.length })} icono={<CheckCircle2 size={16} aria-hidden />} textos={r.decisions} tono="ok" />
      <ListaDeTextos titulo={t('reuniones.detalle.riesgos', { n: r.risks.length })} icono={<AlertTriangle size={16} aria-hidden />} textos={r.risks} tono="riesgo" />
      <ListaDeTextos titulo={t('reuniones.detalle.preguntas', { n: r.open_questions.length })} icono={<HelpCircle size={16} aria-hidden />} textos={r.open_questions} tono="pregunta" />

      {(r.actions.length > 0 || r.status === 'lista') && <AccionesDeReunion key={`${r.id}-acciones`} reunion={r} />}
      {r.status === 'lista' && <PreguntarALaIA id={r.id} />}
      <TranscripcionDeReunion reunion={r} segmentoResaltado={segmentoResaltado} />
      <ParticipantesDeReunion reunion={r} />
      {r.permissions.listen && (r.audio?.chunks ?? 0) > 0 && <AudioDeReunion reunion={r} />}

      {r.events.length > 0 && (
        <Card>
          <Section title={<span className="reu-seccion"><History size={16} aria-hidden />{t('reuniones.detalle.linea_de_tiempo')}</span>}>
            <ol className="reu-eventos">
              {r.events.map((ev, i) => (
                <li key={`${ev.at}-${i}`} className="reu-evento">
                  <span className="reu-evento__cuando">{fmtDateTime(ev.at)}</span>
                  <span className="reu-evento__que">{t(`reuniones.evento.${ev.type}`, ev.type.replace(/_/g, ' '))}</span>
                  {ev.actor && <span className="u-text3-xs">{ev.actor}</span>}
                </li>
              ))}
            </ol>
          </Section>
        </Card>
      )}

      {editar && <ModalEditar reunion={r} onClose={() => setEditar(false)} />}
    </div>
  )
}
