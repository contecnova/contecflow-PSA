/**
 * Pestaña de informes programados.
 * Troceado de ReportsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useState, useId } from 'react'
import {
  type LucideIcon,
  CalendarDays,
  Trash2,
  Plus,
  X,
  Mail,
  Paperclip,
  FileText,
  Pause,
  PlayCircle,
  Send,
  CalendarClock,
  CalendarRange,
  Info,
} from 'lucide-react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { scheduledReportsApi, apiUrl } from '../../services/api'
import { Button, Spinner, EmptyState, Select, IconButton, Checkbox, Input } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import { fmtDateTime, extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useAppT } from '../../i18n/AppLangContext'
import { POLL_FREQUENT_MS } from '../../constants/timings'
import { type ScheduledReportCreate } from './compartido'

// ── ScheduledReportsTab ────────────────────────────────────────────────────────
export function ScheduledReportsTab() {
  const idCampo = useId()
  const traducir = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showCreate, setShowCreate] = useState(false)
  const [_editing, _setEditing] = useState(null)
  const [form, setForm] = useState({
    name: '', metric: 'hours_by_month', recipients: '',
    frequency: 'weekly', include_pdf: true,
  })

  const { data: scheduled = [], isLoading } = useQuery({
    queryKey: ['scheduled-reps'],
    queryFn: () => scheduledReportsApi.list().then(r => r.data),
    refetchInterval: POLL_FREQUENT_MS,
  })

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: (d: ScheduledReportCreate) => scheduledReportsApi.create(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scheduled-reps'] })
      setShowCreate(false)
      setForm({ name: '', metric: 'hours_by_month', recipients: '', frequency: 'weekly', include_pdf: true })
      toast.success(traducir('reportes_ui.programado_creado'))
    },
    onError: e => toast.error(extractErr(e, traducir('reportes_ui.error_crear'))),
  })

  const { mutate: remove } = useMutation({
    mutationFn: (id: string) => scheduledReportsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['scheduled-reps'] }); toast.success(traducir('reportes_ui.informe_eliminado')) },

    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const { mutate: runNow, isPending: running } = useMutation({
    mutationFn: (id: string) => scheduledReportsApi.run(id).then(r => r.data),
    onSuccess: data => {
      qc.invalidateQueries({ queryKey: ['scheduled-reps'] })
      const to = data.recipients.join(', ') || '—'
      toast.success(data.status === 'queued' ? traducir('reportes_ui.envio_en_curso', { to }) : traducir('reportes_ui.informe_enviado', { to }))
    },
    onError: e => toast.error(extractErr(e, traducir('reportes_ui.error_ejecutar'))),
  })

  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, val }: { id: string; val: boolean }) => scheduledReportsApi.toggle(id, { is_active: val }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scheduled-reps'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const FREQ_LABELS: Record<string, string> = { daily: traducir('reportes_ui.frec_daily'), weekly: traducir('reportes_ui.frec_weekly'), monthly: traducir('reportes_ui.frec_monthly') }
  const FREQ_ICONS: Record<string, LucideIcon> = { daily: CalendarClock, weekly: CalendarDays, monthly: CalendarRange }

  const METRICS = [
    { id: 'hours_by_month',        label: traducir('reportes_ui.m_horas_mes') },
    { id: 'margin_by_project',     label: traducir('reportes_ui.m_margen_proyecto') },
    { id: 'ticket_volume_trend',   label: traducir('reportes_ui.m_volumen_tickets') },
    { id: 'sprint_velocity',       label: traducir('reportes_ui.m_velocidad_sprint') },
    { id: 'productivity_by_person',label: traducir('reportes_ui.m_productividad_persona') },
    { id: 'pipeline_by_stage',     label: traducir('reportes_ui.m_pipeline_etapa') },
    { id: 'tasks_overdue',         label: traducir('reportes_ui.m_tareas_vencidas') },
    { id: 'cost_vs_budget',        label: traducir('reportes_ui.m_coste_presupuesto') },
  ]


  const submitForm = () => {
    const data = {
      name:       form.name,
      metric:     form.metric,
      frequency:  form.frequency,
      include_pdf: form.include_pdf,
      recipients: form.recipients.split(',').map(r => r.trim()).filter(Boolean),
    }
    create(data)
  }

  return (
    <div>
      <div className="u-row-between-mb16">
        <div>
          <div className="rep-text-md-strong">{traducir('reportes_ui.informes_programados')}</div>
          <div className="u-text2-sm">
            {traducir('reports.envio_automatico_por_email_los_informes_se')}
          </div>
        </div>
        <Button variant={showCreate ? 'secondary' : 'primary'} icon={showCreate ? <X size={14} /> : <Plus size={14} />} onClick={() => setShowCreate(s => !s)}>
          {showCreate ? traducir('reportes_ui.cancelar_x') : traducir('reportes_ui.nuevo_informe')}
        </Button>
      </div>

      {/* Aviso de correo */}
      <div className="rep-row-warning">
        <Info size={14} className="rep-box-6" aria-hidden />
        <span>{traducir('reportes_ui.aviso_correo')}</span>
      </div>

      {/* Formulario nuevo */}
      {showCreate && (
        <div className="rep-ps rep-box-7">
          <div className="rep-text-accent-md-strong">
            {traducir('reports.nuevo_informe_programado')}
          </div>
          <div className="rep-grid-4">
            <Input label={traducir('reportes_ui.nombre_req')} id={`${idCampo}-1`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder={traducir('reports.report_name')} />
            <Select label={traducir('reports.metrica_2')} placeholder={false} id={`${idCampo}-2`} value={form.metric} onChange={e => setForm(f => ({ ...f, metric: e.target.value }))}>
                {METRICS.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
              </Select>
            <Select label={traducir('reportes_ui.frecuencia')} placeholder={false} id={`${idCampo}-3`} value={form.frequency} onChange={e => setForm(f => ({ ...f, frequency: e.target.value }))}>
                {Object.entries(FREQ_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </Select>
            <Input label={traducir('reports.destinatarios_emails_separados_por_coma')} id={`${idCampo}-4`} value={form.recipients} onChange={e => setForm(f => ({ ...f, recipients: e.target.value }))} placeholder={traducir('reportes_ui.emails_ejemplo')} />
          </div>
          <Checkbox className="rep-label-sm" checked={!!form.include_pdf}
            onChange={v => setForm(f => ({ ...f, include_pdf: v }))}
            label={traducir('reports.adjuntar_pdf_del_informe_al_email')} />
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => setShowCreate(false)}>
              {traducir('common.cancel')}
            </Button>
            <Button icon={<CalendarClock size={14} />} onClick={submitForm} loading={creating}
              disabled={!form.name || !form.recipients}>
              {traducir('reportes_ui.programar')}
            </Button>
          </div>
        </div>
      )}

      {/* Lista */}
      {isLoading ? (
        <div className="rep-state-muted-2"><Spinner /></div>
      ) : scheduled.length === 0 ? (
        <EmptyState icon={<CalendarClock size={28} />} title={traducir('reports.sin_informes_programados')}
          description={traducir('reports.crea_informes_para_recibir_datos_automaticamente_por')}
          ctaLabel={traducir('reportes_ui.nuevo_informe')} onCta={() => setShowCreate(true)} />
      ) : (
        scheduled.map(rep => {
          const IconoFrecuencia = FREQ_ICONS[rep.frequency] || CalendarDays
          return (
          <div className={`rep-ps${rep.is_active ? '' : ' rep-ps--pausado'}`} key={rep.id}>
            <div className="rep-row-14">
              <div className="u-flex1-min0">
                <div className="rep-row-15">
                  <IconoFrecuencia size={16} className="rep-icono-frecuencia" aria-hidden />
                  <span className="u-md-700">{rep.name}</span>
                  {!rep.is_active && (
                    <StatusBadge kind="warning" caps={false}>{traducir('reportes_ui.pausado')}</StatusBadge>
                  )}
                  {rep.include_pdf && (
                    <StatusBadge kind="neutral" caps={false}><Paperclip size={11} aria-hidden />PDF</StatusBadge>
                  )}
                </div>
                <div className="rep-text-muted-sm-2">
                  {FREQ_LABELS[rep.frequency]} ·{' '}
                  {METRICS.find(m => m.id === rep.metric)?.label || rep.metric}
                </div>
                <div className="rep-destinatarios">
                  <Mail size={12} aria-hidden /> {(rep.recipients || []).join(', ')}
                </div>
                {(rep.last_run_at || rep.next_run_at) && (
                  <div className="rep-text-muted-2xs-2">
                    {rep.last_run_at && traducir('reportes_ui.ultimo_envio', { fecha: fmtDateTime(rep.last_run_at) })}
                    {rep.last_run_at && rep.next_run_at && ' · '}
                    {rep.next_run_at && traducir('reportes_ui.proximo', { fecha: fmtDateTime(rep.next_run_at) })}
                  </div>
                )}
              </div>
              <div className="rep-row-16">
                <Button size="xs" variant="secondary" icon={rep.is_active ? <Pause size={12} /> : <PlayCircle size={12} />} onClick={() => toggle({ id: rep.id, val: !rep.is_active })}>
                  {rep.is_active ? traducir('reportes_ui.pausar') : traducir('reportes_ui.activar')}
                </Button>
                <Button size="xs" variant="secondary" icon={<Send size={12} />} onClick={() => runNow(rep.id)} disabled={!rep.is_active} loading={running}>
                  {traducir('reportes_ui.enviar_ahora')}
                </Button>
                {/* Enlace y no el cliente: el navegador abre el PDF en otra pestaña con la cookie de sesión. */}
                <a className="rep-enlace-pdf" href={apiUrl(`/billing-reports/scheduled-reports/${rep.id}/preview-pdf`)} target="_blank"
                  rel="noopener noreferrer">
                  <FileText size={12} aria-hidden /> PDF
                </a>
                <IconButton variante="caja" tono="peligro" ariaLabel={traducir('common.delete')} title={traducir('common.delete')} onClick={() => { openConfirmGlobal({ message: traducir('reportes_ui.eliminar_confirm', { nombre: rep.name }), onConfirm: () => remove(rep.id), danger: true }) }}>
                  <Trash2 size={14} aria-hidden />
                </IconButton>
              </div>
            </div>
          </div>
          )
        })
      )}
    </div>
  )
}
