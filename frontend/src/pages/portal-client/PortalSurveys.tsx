/**
 * PortalSurveys — encuestas de satisfacción del portal cliente.
 * El backoffice las crea con POST /portal/surveys; aquí se listan y responden.
 */
import { ReactNode, useState } from 'react'
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
      toast.success('Gracias por tu feedback')
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
          subtitle="Tu feedback nos ayuda a mejorar el servicio. Solo lleva 1 minuto."
          icon={Sparkles}
          breadcrumb={[
            { label: 'Encuestas', onClick: () => { setActive(null); resetForm() } },
            { label: active.title || 'Encuesta' },
          ]}
          actions={
            <PortalButton variant="secondary" size="sm" icon={<ArrowLeft size={13} />}
              disabled={false}
              loading={false}
              onClick={() => { setActive(null); resetForm() }}>Volver</PortalButton>
          }
          meta={(active.sent_at ? [{ icon: <Clock size={12} />, value: `Enviada el ${active.sent_at}` }] : []) as SurveyMetaItem[]}
        />

        <PortalCard style={{ marginBottom: 16 }} accent={false} onClick={undefined}>
          <PortalSection title="Puntúa cada aspecto" hint="De 1 (muy mala) a 5 (excelente)" action={undefined}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
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

        <PortalCard style={{ marginBottom: 16 }} accent={false} onClick={undefined}>
          <PortalSection title="¿Recomendarías el servicio?" hint="NPS — del 0 (nunca) al 10 (totalmente)" action={undefined}>
            <NpsScale value={form.nps_score} onChange={(v: number) => setForm(f => ({ ...f, nps_score: v }))} />
          </PortalSection>
        </PortalCard>

        <PortalCard style={{ marginBottom: 16 }} accent={false} onClick={undefined}>
          <PortalSection title="¿Recomendarías el equipo a otra empresa?" hint={undefined} action={undefined}>
            <div style={{ display: 'flex', gap: 10 }}>
              {[
                { v: true,  label: 'Sí, lo recomendaría',  Icon: ThumbsUp,   color: 'var(--success)' },
                { v: false, label: 'No, esta vez no',      Icon: ThumbsDown, color: 'var(--danger)' },
              ].map(opt => {
                const isActive = form.would_recommend === opt.v
                return (
                  <button key={String(opt.v)} onClick={() => setForm(f => ({ ...f, would_recommend: opt.v }))}
                    style={{
                      flex: 1, padding: '14px 12px',
                      display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                      borderRadius: 10,
                      border: `1px solid ${isActive ? opt.color : 'var(--surface-4)'}`,
                      background: isActive ? `${opt.color}1a` : 'var(--surface-3)',
                      color: isActive ? opt.color : 'var(--text-2)',
                      fontFamily: 'inherit', cursor: 'pointer',
                      fontSize: 'var(--text-sm)', fontWeight: 700,
                    }}>
                    <opt.Icon size={15} /> {opt.label}
                  </button>
                )
              })}
            </div>
          </PortalSection>
        </PortalCard>

        <PortalCard style={{ marginBottom: 16 }} accent={false} onClick={undefined}>
          <PortalSection title="Comentarios" hint="Lo que más te gusta, lo que mejorarías... (opcional)" action={undefined}>
            <PortalField label="" hint={undefined} required={false}>
              <PortalTextarea rows={4} value={form.comments}
                onChange={e => setForm(f => ({ ...f, comments: e.target.value }))}
                placeholder="Cuéntanos tu experiencia..." maxLength={2000} />
            </PortalField>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 6, textAlign: 'right' }}>
              {form.comments.length} / 2000
            </div>
          </PortalSection>
        </PortalCard>

        {error && (
          <PortalBanner tone="warning" icon={undefined} title={error} body={undefined} action={undefined} />
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <PortalButton variant="secondary" disabled={false} loading={false} icon={undefined} onClick={() => { setActive(null); resetForm() }}>Cancelar</PortalButton>
          <PortalButton icon={<Send size={13} />} disabled={false} loading={isPending} onClick={submit}>
            Enviar respuesta
          </PortalButton>
        </div>
      </div>
    )
  }

  // ── List view ──────────────────────────────────────────────────────────────
  return (
    <div>
      <PortalPageHeader
        title="Encuestas de satisfacción"
        subtitle="Comparte tu experiencia con el equipo. Tu feedback es anónimo dentro del proyecto."
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
        <div style={{ color: 'var(--text-3)', padding: 40, textAlign: 'center' }}>Cargando...</div>
      ) : surveys.length === 0 ? (
        <PortalEmpty icon={Sparkles}
          title="No tienes encuestas"
          description="Cuando el equipo te envíe una encuesta de satisfacción, la verás aquí."
          action={undefined} />
      ) : (
        <>
          {pending.length > 0 && (
            <div style={{ marginBottom: 22 }}>
              <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>
                Pendientes
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {pending.map(s => (
                  <PortalCard key={s.id} accent onClick={() => setActive(s)}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{
                        width: 38, height: 38, borderRadius: 10, flexShrink: 0,
                        background: 'var(--accent-muted)', color: 'var(--accent)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}><Sparkles size={18} /></div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{s.title}</div>
                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
                          Enviada el {s.sent_at}
                        </div>
                      </div>
                      <PortalBadge tone="warning" icon={undefined}>Pendiente</PortalBadge>
                    </div>
                  </PortalCard>
                ))}
              </div>
            </div>
          )}

          {completed.length > 0 && (
            <div>
              <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>
                Respondidas
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {completed.map(s => (
                  <PortalCard key={s.id} accent={false} onClick={undefined}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
                      <div style={{
                        width: 38, height: 38, borderRadius: 10, flexShrink: 0,
                        background: 'var(--success-bg, rgba(16,185,129,0.12))', color: 'var(--success)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}><CheckCircle2 size={18} /></div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{s.title}</div>
                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
                          Respondida el {s.completed_at}
                        </div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                          {s.overall_satisfaction != null && (
                            <Pill icon={<Star size={11} />} label="Satisfacción" value={`${s.overall_satisfaction}/5`} />
                          )}
                          {s.nps_score != null && (
                            <Pill icon={<MessageCircle size={11} />} label="NPS" value={`${s.nps_score}/10`} />
                          )}
                          {s.would_recommend !== undefined && (
                            <Pill
                              icon={s.would_recommend ? <ThumbsUp size={11} /> : <ThumbsDown size={11} />}
                              label="Recomendaría"
                              value={s.would_recommend ? 'Sí' : 'No'}
                              color={s.would_recommend ? 'var(--success)' : 'var(--danger)'}
                            />
                          )}
                        </div>
                        {s.comments && (
                          <div style={{
                            marginTop: 10, padding: '10px 12px',
                            background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                            borderRadius: 8, fontSize: 'var(--text-sm)', color: 'var(--text-2)',
                          }}>“{s.comments}”</div>
                        )}
                      </div>
                      <PortalBadge tone="success" icon={undefined}>Respondida</PortalBadge>
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8, gap: 12, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text-1)' }}>{label}</div>
          {hint && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 2 }}>{hint}</div>}
        </div>
        {value > 0 && (
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{RATING_LABELS[value - 1]}</span>
        )}
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        {[1, 2, 3, 4, 5].map(n => {
          const filled = value >= n
          return (
            <button key={n} onClick={() => onChange(n)} aria-label={`${n} de 5 estrellas`}
              style={{
                flex: 1, minWidth: 0, padding: '12px 8px',
                borderRadius: 10,
                border: `1px solid ${filled ? 'var(--warning, #f59e0b)' : 'var(--surface-4)'}`,
                background: filled ? 'var(--warning-bg, rgba(245,158,11,0.12))' : 'var(--surface-3)',
                color: filled ? 'var(--warning, #f59e0b)' : 'var(--text-3)',
                cursor: 'pointer', fontFamily: 'inherit',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'background 0.15s, border-color 0.15s',
              }}>
              <Star size={18} fill={filled ? 'currentColor' : 'none'} strokeWidth={1.5} />
            </button>
          )
        })}
      </div>
    </div>
  )
}

function NpsScale({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return (
    <div>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {Array.from({ length: 11 }, (_, n) => {
          const active = value === n
          const tone = n <= 6 ? 'danger' : n <= 8 ? 'warning' : 'success'
          const color = tone === 'danger' ? 'var(--danger)' : tone === 'warning' ? 'var(--warning)' : 'var(--success)'
          return (
            <button key={n} onClick={() => onChange(n)} aria-label={`NPS ${n}`}
              style={{
                width: 40, height: 40, flexShrink: 0,
                borderRadius: 8,
                border: `1px solid ${active ? color : 'var(--surface-4)'}`,
                background: active ? `${color}1a` : 'var(--surface-3)',
                color: active ? color : 'var(--text-2)',
                cursor: 'pointer', fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-base)', fontWeight: 700,
              }}>{n}</button>
          )
        })}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 6 }}>
        <span>0 — No lo recomendaría</span>
        <span>10 — Lo recomendaría sin dudar</span>
      </div>
    </div>
  )
}

function Pill({ icon, label, value, color }: { icon: ReactNode; label: string; value: string; color?: string }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '3px 8px', borderRadius: 999,
      background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
      fontSize: 'var(--text-xs)', color: 'var(--text-2)',
    }}>
      <span style={{ color: color || 'var(--text-3)', display: 'inline-flex' }}>{icon}</span>
      <span style={{ color: 'var(--text-3)' }}>{label}:</span>
      <span style={{ fontWeight: 700, color: color || 'var(--text-1)', fontFamily: 'var(--font-mono)' }}>{value}</span>
    </span>
  )
}

export default PortalSurveys
