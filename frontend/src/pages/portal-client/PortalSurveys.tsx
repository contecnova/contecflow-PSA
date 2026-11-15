/**
 * PortalSurveys — encuestas de satisfacción del portal cliente.
 * El backoffice las crea con POST /portal/surveys; aquí se listan y responden.
 */
import { ChangeEvent, ReactNode, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Sparkles, Star, ArrowLeft, ThumbsUp, ThumbsDown,
  MessageCircle, Send, CheckCircle2, Clock,
} from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { CLIENT_API } from './portalClientContext'
import {
  PortalPageHeader, PortalCard, PortalSection, PortalEmpty,
  PortalBadge, PortalButton, PortalField, PortalTextarea, PortalBanner,
} from './PortalUI'
import { useAppLang } from '../../i18n/AppLangContext'
import { alpha } from '../../constants/theme'
import './PortalSurveys.css'

type ScoreKey = 'overall_satisfaction' | 'communication_score' | 'quality_score' | 'deadline_score'

type SurveyForm = {
  overall_satisfaction: number
  communication_score: number
  quality_score: number
  deadline_score: number
  nps_score: number
  comments: string
  would_recommend: boolean
}

type SurveyItem = {
  id: string | number
  title?: string
  status?: string
  sent_at?: string
  completed_at?: string
  overall_satisfaction?: number | null
  nps_score?: number | null
  would_recommend?: boolean
  comments?: string
}

type SurveyMetaItem = {
  icon?: ReactNode
  value?: ReactNode
  label?: ReactNode
  color?: string
}

const SCORES: Array<{ key: ScoreKey; label: string; hint: string }> = [
  { key: 'overall_satisfaction', label: 'Satisfacción general',
    hint: '¿Cómo de satisfecho estás globalmente con el equipo y el proyecto?' },
  { key: 'communication_score',  label: 'Comunicación',
    hint: '¿Cómo valoras la claridad y frecuencia de comunicación?' },
  { key: 'quality_score',        label: 'Calidad de entregas',
    hint: '¿Las entregas cumplen con tus expectativas y requisitos?' },
  { key: 'deadline_score',       label: 'Cumplimiento de plazos',
    hint: '¿Se respetan los plazos y compromisos?' },
]

const RATING_LABELS = ['Muy mala', 'Mala', 'Aceptable', 'Buena', 'Excelente']

export function PortalSurveys() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [active, setActive] = useState<SurveyItem | null>(null)
  const [form, setForm] = useState<SurveyForm>({
    overall_satisfaction: 0,
    communication_score:  0,
    quality_score:        0,
    deadline_score:       0,
    nps_score:            -1,
    comments:             '',
    would_recommend:      true,
  })
  const [error, setError] = useState('')

  const { data: surveys = [], isLoading } = useQuery<SurveyItem[]>({
    queryKey: ['portal-surveys'],
    queryFn: () => CLIENT_API.get('/portal/surveys').then(r => r.data),
  })

  const { mutate: respond, isPending } = useMutation({
    mutationFn: ({ id, payload }: { id: string | number; payload: SurveyForm }) => CLIENT_API.post(`/portal/surveys/${id}/respond`, payload).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-surveys'] })
      qc.invalidateQueries({ queryKey: ['portal-dashboard'] })
      toast.success(t('portalsurveys.gracias_por_tu_feedback'))
      setActive(null); resetForm()
    },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al enviar respuesta')),
  })

  const resetForm = () => {
    setForm({
      overall_satisfaction: 0, communication_score: 0,
      quality_score: 0, deadline_score: 0,
      nps_score: -1, comments: '', would_recommend: true,
    })
    setError('')
  }

  const submit = () => {
    if (!active) return
    setError('')
    const missing = SCORES.find(s => !form[s.key])
    if (missing) { setError(`Falta puntuar "${missing.label}"`); return }
    if (form.nps_score < 0) { setError('Indica tu probabilidad de recomendar (NPS)'); return }
    respond({ id: active.id, payload: form })
  }

  const pending = surveys.filter(s => s.status === 'pending')
  const completed = surveys.filter(s => s.status !== 'pending')

  // ── Detail / response form ─────────────────────────────────────────────────
  if (active) {
    return (
      <div>
        <PortalPageHeader
          title={active.title || 'Encuesta de satisfacción'}
          subtitle={t('portalsurveys.tu_feedback_nos_ayuda_a_mejorar_el')}
          icon={Sparkles}
          breadcrumb={[
            { label: 'Encuestas', onClick: () => { setActive(null); resetForm() } },
            { label: active.title || 'Encuesta' },
          ]}
          actions={
            <PortalButton variant="secondary" size="sm" icon={<ArrowLeft size={13} />}
              disabled={false}
              loading={false}
              onClick={() => { setActive(null); resetForm() }}>{t('chat.back')}</PortalButton>
          }
          meta={(active.sent_at ? [{ icon: <Clock size={12} />, value: `Enviada el ${active.sent_at}` }] : []) as SurveyMetaItem[]}
        />

        <PortalCard className="portalsu-sx7" accent={false} onClick={undefined}>
          <PortalSection title={t('portalsurveys.puntua_cada_aspecto')} hint="De 1 (muy mala) a 5 (excelente)" action={undefined}>
            <div className="u-stack-16">
              {SCORES.map(s => (
                <RatingRow key={s.key}
                  label={s.label} hint={s.hint}
                  value={form[s.key]}
                  onChange={(v: number) => setForm(f => ({ ...f, [s.key]: v }))}
                />
              ))}
            </div>
          </PortalSection>
        </PortalCard>

        <PortalCard className="portalsu-sx7" accent={false} onClick={undefined}>
          <PortalSection title={t('portalsurveys.recomendarias_el_servicio')} hint="NPS — del 0 (nunca) al 10 (totalmente)" action={undefined}>
            <NpsScale value={form.nps_score} onChange={(v: number) => setForm(f => ({ ...f, nps_score: v }))} />
          </PortalSection>
        </PortalCard>

        <PortalCard className="portalsu-sx7" accent={false} onClick={undefined}>
          <PortalSection title={t('portalsurveys.recomendarias_el_equipo_a_otra_empresa')} hint={undefined} action={undefined}>
            <div className="u-row-10">
              {[
                { v: true,  label: 'Sí, lo recomendaría',  Icon: ThumbsUp,   color: 'var(--success)' },
                { v: false, label: 'No, esta vez no',      Icon: ThumbsDown, color: 'var(--danger)' },
              ].map(opt => {
                const isActive = form.would_recommend === opt.v
                return (
                  <button className="portsurv-row-8 portalsu-sx8" key={String(opt.v)} onClick={() => setForm(f => ({ ...f, would_recommend: opt.v }))}
                    style={{ border: `1px solid ${isActive ? opt.color : 'var(--surface-4)'}`, background: isActive ? alpha(opt.color, '1a') : 'var(--surface-3)', color: isActive ? opt.color : 'var(--text-2)' }}>
                    <opt.Icon size={15} /> {opt.label}
                  </button>
                )
              })}
            </div>
          </PortalSection>
        </PortalCard>

        <PortalCard className="portalsu-sx7" accent={false} onClick={undefined}>
          <PortalSection title={t('tasks.tab_comments')} hint="Lo que más te gusta, lo que mejorarías... (opcional)" action={undefined}>
            <PortalField label="" hint={undefined} required={false}>
              <PortalTextarea rows={4} value={form.comments}
                onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setForm(f => ({ ...f, comments: e.target.value }))}
                placeholder={t('portalsurveys.cuentanos_tu_experiencia')} maxLength={2000} />
            </PortalField>
            <div className="portsurv-box-1">
              {form.comments.length} / 2000
            </div>
          </PortalSection>
        </PortalCard>

        {error && (
          <PortalBanner tone="warning" icon={undefined} title={error} body={undefined} action={undefined} />
        )}

        <div className="u-actions-10">
          <PortalButton variant="secondary" disabled={false} loading={false} icon={undefined} onClick={() => { setActive(null); resetForm() }}>{t('common.cancel')}</PortalButton>
          <PortalButton icon={<Send size={13} />} disabled={false} loading={isPending} onClick={submit}>
            {t('clientstabs.enviar_respuesta')}
          </PortalButton>
        </div>
      </div>
    )
  }

  // ── List view ──────────────────────────────────────────────────────────────
  return (
    <div>
      <PortalPageHeader
        title={t('portalsurveys.encuestas_de_satisfaccion')}
        subtitle={t('portalsurveys.comparte_tu_experiencia_con_el_equipo_tu')}
        icon={Sparkles}
        actions={undefined}
        meta={[
          { value: pending.length, label: 'pendientes', color: pending.length ? 'var(--warning)' : 'var(--text-3)' },
          { value: completed.length, label: 'respondidas', color: 'var(--success)' },
        ]}
        breadcrumb={undefined}
      />

      {pending.length > 0 && (
        <PortalBanner tone="info" icon={<Sparkles size={18} />}
          title={`Tienes ${pending.length} encuesta(s) pendiente(s)`}
          body="Solo te llevará un minuto. Tu opinión ayuda al equipo a mejorar el servicio."
          action={undefined}
        />
      )}

      {isLoading ? (
        <div className="portsurv-box-2">{t('common.loading')}</div>
      ) : surveys.length === 0 ? (
        <PortalEmpty icon={Sparkles}
          title={t('portalsurveys.no_tienes_encuestas')}
          description={t('portalsurveys.cuando_el_equipo_te_envie_una_encuesta')}
          action={undefined} />
      ) : (
        <>
          {pending.length > 0 && (
            <div className="portsurv-sp-1">
              <div className="portsurv-box-3">
                {t('approvals.pending')}
              </div>
              <div className="u-stack-10">
                {pending.map(s => (
                  <PortalCard key={s.id} accent onClick={() => setActive(s)}>
                    <div className="u-row-center-12">
                      <div className="portsurv-row-1"><Sparkles size={18} /></div>
                      <div className="u-flex1-min0">
                        <div className="u-sm-700">{s.title}</div>
                        <div className="u-text3-xs">
                          {t('portalsurveys.enviada_el')} {s.sent_at}
                        </div>
                      </div>
                      <PortalBadge tone="warning" icon={undefined}>{t('uat.pending')}</PortalBadge>
                    </div>
                  </PortalCard>
                ))}
              </div>
            </div>
          )}

          {completed.length > 0 && (
            <div>
              <div className="portsurv-box-3">
                {t('portalsurveys.respondidas')}
              </div>
              <div className="u-stack-10">
                {completed.map(s => (
                  <PortalCard key={s.id} accent={false} onClick={undefined}>
                    <div className="portsurv-row-2">
                      <div className="portsurv-row-11"><CheckCircle2 size={18} /></div>
                      <div className="u-flex1-min0">
                        <div className="u-sm-700">{s.title}</div>
                        <div className="u-text3-xs">
                          {t('portalsurveys.respondida_el')} {s.completed_at}
                        </div>
                        <div className="portsurv-row-3">
                          {s.overall_satisfaction != null && (
                            <Pill icon={<Star size={11} />} label={t('portalsurveys.satisfaccion')} value={`${s.overall_satisfaction}/5`} />
                          )}
                          {s.nps_score != null && (
                            <Pill icon={<MessageCircle size={11} />} label="NPS" value={`${s.nps_score}/10`} />
                          )}
                          {s.would_recommend !== undefined && (
                            <Pill
                              icon={s.would_recommend ? <ThumbsUp size={11} /> : <ThumbsDown size={11} />}
                              label={t('portalsurveys.recomendaria')}
                              value={s.would_recommend ? 'Sí' : 'No'}
                              color={s.would_recommend ? 'var(--success)' : 'var(--danger)'}
                            />
                          )}
                        </div>
                        {s.comments && (
                          <div className="portsurv-box-4">“{s.comments}”</div>
                        )}
                      </div>
                      <PortalBadge tone="success" icon={undefined}>{t('portalsurveys.respondida')}</PortalBadge>
                    </div>
                  </PortalCard>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function RatingRow({ label, hint, value, onChange }: { label: string; hint?: string; value: number; onChange: (value: number) => void }) {
  return (
    <div>
      <div className="portsurv-row-4">
        <div>
          <div className="portsurv-txt-1">{label}</div>
          {hint && <div className="u-text3-xs-mt2">{hint}</div>}
        </div>
        {value > 0 && (
          <span className="u-text3-xs">{RATING_LABELS[value - 1]}</span>
        )}
      </div>
      <div className="u-row-6">
        {[1, 2, 3, 4, 5].map(n => {
          const filled = value >= n
          return (
            <button className="portsurv-row-9 portalsu-sx8" key={n} onClick={() => onChange(n)} aria-label={`${n} de 5 estrellas`}
              style={{ border: `1px solid ${filled ? 'var(--warning, #f59e0b)' : 'var(--surface-4)'}`, background: filled ? 'var(--warning-bg, rgba(245,158,11,0.12))' : 'var(--surface-3)', color: filled ? 'var(--warning, #f59e0b)' : 'var(--text-3)' }}>
              <Star size={18} fill={filled ? 'currentColor' : 'none'} strokeWidth={1.5} />
            </button>
          )
        })}
      </div>
    </div>
  )
}

function NpsScale({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  const { t } = useAppLang()
  return (
    <div>
      <div className="portsurv-row-5">
        {Array.from({ length: 11 }, (_, n) => {
          const active = value === n
          const tone = n <= 6 ? 'danger' : n <= 8 ? 'warning' : 'success'
          const color = tone === 'danger' ? 'var(--danger)' : tone === 'warning' ? 'var(--warning)' : 'var(--success)'
          return (
            <button className="portsurv-box-5 portalsu-sx9" key={n} onClick={() => onChange(n)} aria-label={`NPS ${n}`}
              style={{ border: `1px solid ${active ? color : 'var(--surface-4)'}`, background: active ? alpha(color, '1a') : 'var(--surface-3)', color: active ? color : 'var(--text-2)' }}>{n}</button>
          )
        })}
      </div>
      <div className="portsurv-row-6">
        <span>{t('portalsurveys.0_no_lo_recomendaria')}</span>
        <span>{t('portalsurveys.10_lo_recomendaria_sin_dudar')}</span>
      </div>
    </div>
  )
}

function Pill({ icon, label, value, color }: { icon: ReactNode; label: string; value: string; color?: string }) {
  return (
    <span className="portsurv-row-7">
      <span className="portsurv-row-10" style={{ color: color || 'var(--text-3)' }}>{icon}</span>
      <span className="u-text3">{label}:</span>
      <span className="portsurv-txt-2" style={{ color: color || 'var(--text-1)' }}>{value}</span>
    </span>
  )
}

export default PortalSurveys
