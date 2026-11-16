/**
 * MeetingsAIPage — Asistente de reuniones: procesa transcripciones con IA y
 * extrae resumen, decisiones y acciones.
 *
 * 16-11-2026: título = el del menú; KPIs con KpiCard en .ds-grid-stats;
 * vacíos con EmptyState e icono lucide (antes emoji en cajas propias);
 * plataformas, metadatos y secciones con iconos lucide en lugar de emojis;
 * estados con StatusBadge; formulario del modal con Input/Select/FormField
 * del kit; fechas con fmtDate según idioma (antes ISO recortado).
 */
import { PRODUCT_NAME } from '../constants/brand'
import { useState } from 'react'
import type { ChangeEvent, ReactNode } from 'react'
import { extractErr, fmtDate } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { meetingsAIApi } from '../services/api'
import { Button, Card, EmptyState, FormField, Input, KpiCard, Modal, Section, Select, Spinner } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import {
  CalendarDays, CheckCircle2, Clock, ClipboardPaste, FileText, ListChecks, ListPlus, MessageSquare,
  Mic, MousePointerClick, Sparkles, User, Users, Video,
} from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import useMediaQuery from '../hooks/useMediaQuery'
import './MeetingsAIPage.css'

interface ProcessFormState {
  title: string
  transcript: string
  platform: string
  participants: string
  duration_minutes: string
}

/** Marcas con su nombre propio; las genéricas se traducen (`label` es clave i18n solo si empieza por `pagina_meet.`). */
const PLATFORMS: { id: string; label: string; icon: ReactNode }[] = [
  { id: 'teams',  label: 'Microsoft Teams', icon: <Video size={14} aria-hidden /> },
  { id: 'zoom',   label: 'Zoom',            icon: <Video size={14} aria-hidden /> },
  { id: 'meet',   label: 'Google Meet',     icon: <Video size={14} aria-hidden /> },
  { id: 'slack',  label: 'Slack Huddle',    icon: <MessageSquare size={14} aria-hidden /> },
  { id: 'presencial', label: 'pagina_meet.presencial',  icon: <Users size={14} aria-hidden /> },
  { id: 'otro',   label: 'pagina_meet.otro',            icon: <Mic size={14} aria-hidden /> },
]
const nombreDePlataforma = (label: string, t: (k: string) => string) => (label.startsWith('pagina_meet.') ? t(label) : label)

const DEMO_TRANSCRIPT = `Pedro: Buenas, arrancamos. El objetivo de hoy es revisar el estado del Q3 y planificar el Q4.
María: Tengo los datos de rendimiento. Estamos al 78% de las entregas planificadas. Hay dos proyectos en riesgo.
Pedro: ¿Cuáles?
María: Alpha está retrasado por los problemas de infraestructura. Carlos, ¿puedes revisar eso esta semana?
Carlos: Sí, lo tengo en el radar. Lo resolveré antes del viernes.
Pedro: Bien. Y el proyecto Beta, necesitamos actualizar el contrato con el cliente antes del 30 de este mes. Ana, ¿puedes encargarte?
Ana: Confirmado, lo gestiono yo.
Pedro: Siguiente punto: el equipo necesita formación en las nuevas herramientas de testing. Luis, ¿coordinas tú con RRHH?
Luis: Sin problema, esta semana lo organizo.
Pedro: Resumiendo: Carlos revisa infraestructura de Alpha antes del viernes, Ana actualiza el contrato de Beta antes del 30, y Luis organiza la formación. Cerramos.`

function ProcessModal({ onClose }: { onClose: () => void }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState<ProcessFormState>({ title: '', transcript: '', platform: 'teams', participants: '', duration_minutes: '' })
  const s = (k: keyof ProcessFormState) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const { mutate: process, isPending } = useMutation({
    // Segunda auditoría 2026-11: se mandaban `participants` como texto y `duration_minutes`;
    // el backend espera una lista y `duration_min`, y respondía 422 siempre.
    mutationFn: (d: ProcessFormState) => meetingsAIApi.process({
      title: d.title.trim(),
      transcript: d.transcript,
      platform: d.platform,
      participants: d.participants.split(',').map(p => p.trim()).filter(Boolean),
      duration_min: d.duration_minutes ? Number(d.duration_minutes) : null,
    }).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ai-meetings'] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, t('meetings_ai.error_process'))),
  })

  return (
    <Modal open title={t('meetings_ai.process_title')} onClose={onClose} size="lg">
      <div className="meet-form">
        <Input className="u-col-full" label={t('meetings_ai.title_label')} value={form.title} onChange={s('title')}
          placeholder={t('meetings_ai.title_placeholder')} />
        <Select label={t('meetings_ai.platform_label')} value={form.platform} onChange={s('platform')}
          options={PLATFORMS.map(p => ({ value: p.id, label: nombreDePlataforma(p.label, t) }))} />
        <Input label={t('meetings_ai.duration_label')} type="number" value={form.duration_minutes} onChange={s('duration_minutes')}
          placeholder={t('meetings_ai.duration_placeholder')} />
        <Input className="u-col-full" label={t('meetings_ai.participants_label')} value={form.participants} onChange={s('participants')}
          placeholder={t('meetings_ai.participants_placeholder')} />
        <div className="u-col-full meet-form__transcripcion">
          <div className="meet-form__demo">
            <Button variant="ghost" size="sm" icon={<ClipboardPaste size={13} />}
              onClick={() => setForm(f => ({ ...f, transcript: DEMO_TRANSCRIPT, title: f.title || t('meetings_ai.demo_title'), participants: t('meetings_ai.demo_participants') }))}>
              {t('meetings_ai.use_demo')}
            </Button>
          </div>
          <FormField label={t('meetings_ai.transcript_label')}>
            <textarea value={form.transcript} onChange={s('transcript')} rows={10}
              className="meet-form__textarea" placeholder={t('meetings_ai.transcript_placeholder')} />
          </FormField>
        </div>
      </div>

      <div className="meet-acciones">
        <Button variant="secondary" onClick={onClose}>{t('meetings_ai.cancel')}</Button>
        <Button icon={<Sparkles size={14} />} onClick={() => process(form)} loading={isPending}
          disabled={!form.transcript.trim() || !form.title.trim()}>
          {isPending ? t('meetings_ai.processing') : t('meetings_ai.process_btn')}
        </Button>
      </div>
    </Modal>
  )
}

export default function MeetingsAIPage() {
  const t = useAppT()
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const toast = useToast()
  const qc = useQueryClient()
  const [showProcess, setShowProcess] = useState(false)
  const [selected, setSelected] = useState<string | number | null>(null)

  const { data: meetings = [], isLoading } = useQuery({
    queryKey: ['ai-meetings'],
    queryFn: () => meetingsAIApi.list().then(r => r.data),
  })
  const { data: detail = null } = useQuery({
    queryKey: ['ai-meeting', selected],
    queryFn: () => meetingsAIApi.get(selected).then(r => r.data),
    enabled: !!selected,
  })
  // El detalle no trae fechas: salen de la fila del listado.
  const resumen = meetings.find(m => m.id === selected)
  const { mutate: createTasks, isPending: creating } = useMutation({
    mutationFn: (id: string | number) => meetingsAIApi.createTasks(id).then(r => r.data),
    onSuccess: (data) => { qc.invalidateQueries({ queryKey: ['ai-meeting', selected] }); toast.success(t('pagina_meet.tareas_creadas_en', { v1: data.tasks_created || 0, PRODUCT_NAME })) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const platCfg = (p?: string) => PLATFORMS.find((x) => x.id === p) || PLATFORMS[PLATFORMS.length - 1]
  const decisiones = detail?.decisions ?? []
  const acciones = detail?.actions ?? []

  return (
    <PageShell>
      <PageHeader
        icon={<Mic size={18} />}
        title={t('nav.meetings')}
        subtitle={t('meetings_ai.subtitle')}
        actions={<Button icon={<Sparkles size={14} />} onClick={() => setShowProcess(true)}>{t('meetings_ai.process_meeting')}</Button>}
        showListExport={false}
      />

      <div className="u-stack-16">
        {meetings.length > 0 && (
          <div className="ds-grid-stats">
            <KpiCard icon={<Mic size={16} />} label={t('meetings_ai.stats_meetings')} value={meetings.length} />
            <KpiCard icon={<ListChecks size={16} />} label={t('meetings_ai.stats_actions')} value={meetings.reduce((a, m) => a + (m.actions_count || 0), 0)} />
            <KpiCard icon={<CheckCircle2 size={16} />} label={t('meetings_ai.stats_created')} value={meetings.reduce((a, m) => a + (m.created_actions || 0), 0)} />
          </div>
        )}

        {isLoading ? <Spinner /> : meetings.length === 0 ? (
          <Card>
            <EmptyState icon={<Mic size={28} />} title={t('meetings_ai.empty_title')} description={t('meetings_ai.empty_desc')}
              action={<Button icon={<Sparkles size={14} />} onClick={() => setShowProcess(true)}>{t('meetings_ai.empty_btn')}</Button>} />
          </Card>
        ) : (
          <div className={`meet-layout${isNarrow ? ' meet-layout--estrecho' : ''}`}>
            {/* Lista */}
            <ul className="meet-lista">
              {meetings.map(m => {
                const plat = platCfg(m.platform)
                const activa = selected === m.id
                return (
                  <li key={m.id}>
                    <button type="button" onClick={() => setSelected(m.id)} aria-pressed={activa}
                      className={`meet-item${activa ? ' meet-item--activa' : ''}`}>
                      <div className="meet-item__cab">
                        <span className="meet-item__icono">{plat.icon}</span>
                        <div className="u-flex1-min0">
                          <div className="meet-item__titulo">{m.title}</div>
                          <div className="meet-item__fecha">{fmtDate(m.meeting_date || m.created_at)}</div>
                        </div>
                      </div>
                      <div className="meet-item__pie">
                        <StatusBadge kind={m.status === 'done' ? 'success' : 'warning'} caps={false}>
                          {m.status === 'done' ? t('meetings_ai.status_done') : t('meetings_ai.status_processing')}
                        </StatusBadge>
                        <span className="meet-item__dato">{(m.actions_count || 0)} {t('meetings_ai.actions_label')}</span>
                        {(m.created_actions || 0) > 0 && (
                          <span className="meet-item__dato meet-item__dato--ok">{m.created_actions} {t('meetings_ai.created_label')}</span>
                        )}
                      </div>
                    </button>
                  </li>
                )
              })}
            </ul>

            {/* Detalle */}
            <div className="u-min0">
              {!selected ? (
                <Card>
                  <EmptyState icon={<MousePointerClick size={28} />} title={t('meetings_ai.select_title')} description={t('meetings_ai.select_desc')} />
                </Card>
              ) : !detail ? <Spinner /> : (
                <div className="u-stack-16">
                  <Card>
                    <div className="meet-detalle__titulo">{detail.title}</div>
                    <div className="meet-detalle__meta">
                      {detail.platform && <span className="meet-meta">{platCfg(detail.platform).icon}{nombreDePlataforma(platCfg(detail.platform).label, t)}</span>}
                      {detail.duration_min != null && <span className="meet-meta"><Clock size={14} aria-hidden />{t('pagina_meet.minutos', { n: detail.duration_min })}</span>}
                      {resumen && <span className="meet-meta"><CalendarDays size={14} aria-hidden />{fmtDate(resumen.meeting_date || resumen.created_at)}</span>}
                    </div>
                  </Card>

                  {detail.summary && (
                    <Card>
                      <Section title={<span className="meet-seccion"><FileText size={16} aria-hidden />{t('meetings_ai.summary_label')}</span>}>
                        <p className="meet-resumen">{detail.summary}</p>
                      </Section>
                    </Card>
                  )}

                  {decisiones.length > 0 && (
                    <Card>
                      <Section title={<span className="meet-seccion"><CheckCircle2 size={16} aria-hidden />{t('meetings_ai.decisions_label', { count: decisiones.length })}</span>}>
                        <ul className="meet-decisiones">
                          {decisiones.map((d, i) => (
                            <li key={i} className="meet-decision">
                              <CheckCircle2 size={14} aria-hidden className="meet-decision__icono" />
                              <span>{d}</span>
                            </li>
                          ))}
                        </ul>
                      </Section>
                    </Card>
                  )}

                  {acciones.length > 0 && (
                    <Card>
                      <Section
                        title={<span className="meet-seccion"><ListChecks size={16} aria-hidden />{t('meetings_ai.actions_label_detail', { count: acciones.length })}</span>}
                        actions={acciones.some(a => !a.is_created) ? (
                          <Button icon={<ListPlus size={14} />} onClick={() => createTasks(selected)} loading={creating}>
                            {creating ? t('meetings_ai.creating_tasks') : t('meetings_ai.create_tasks_btn')}
                          </Button>
                        ) : undefined}
                      >
                        <ul className="meet-acciones-lista">
                          {acciones.map(a => (
                            <li key={a.id} className="meet-accion">
                              <div className="u-flex1-min0">
                                <div className="meet-accion__texto">{a.description}</div>
                                {(a.assignee_name || a.due_date_text) && (
                                  <div className="meet-accion__meta">
                                    {a.assignee_name && <span className="meet-meta"><User size={13} aria-hidden />{a.assignee_name}</span>}
                                    {a.due_date_text && <span className="meet-meta"><CalendarDays size={13} aria-hidden />{a.due_date_text}</span>}
                                  </div>
                                )}
                              </div>
                              <StatusBadge kind={a.is_created ? 'success' : 'neutral'} caps={false}>
                                {a.is_created ? t('meetings_ai.action_created') : t('meetings_ai.action_pending')}
                              </StatusBadge>
                            </li>
                          ))}
                        </ul>
                      </Section>
                    </Card>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {showProcess && <ProcessModal onClose={() => setShowProcess(false)} />}
    </PageShell>
  )
}
