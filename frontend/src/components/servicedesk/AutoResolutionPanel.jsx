/**
 * AutoResolutionPanel — AI auto-resolution dashboard for ITSM
 *
 * Backend endpoints:
 *   GET  /sd/auto-resolution/stats                   -> { total_auto_resolved, pct_of_all_tickets, feedback_total_validated, overall_success_rate, per_bucket: [{bucket, total, success, failed, success_rate}] }
 *   POST /sd/auto-resolution/run-job                 -> { processed, auto_resolved, suggested, failed, status, timestamp }
 *   POST /sd/auto-resolution/run-close-job           -> { processed, auto_closed, validated, failed, status, timestamp }
 *   POST /sd/tickets/{id}/auto-resolution/feedback   { success: bool } -> { recorded, ticket_id, success }
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { Card, Button, Spinner, Modal, EmptyState } from '../ui'
import { useToast } from '../../context/ToastContext'

const card = { padding: '20px 22px' }

const fieldLabel = {
  fontSize: 'var(--text-2xs)',
  fontWeight: 700,
  color: 'var(--text-3)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 6,
}

function StatCard({ label, value, accent, sub }) {
  return (
    <div style={{
      flex: '1 1 140px',
      background: `color-mix(in srgb, ${accent} 8%, var(--surface-3))`,
      border: `1px solid color-mix(in srgb, ${accent} 25%, var(--surface-4))`,
      borderRadius: 10,
      padding: '14px 16px',
      textAlign: 'center',
    }}>
      <div style={{ fontSize: 'var(--text-2xl-em)', fontWeight: 800, color: accent, lineHeight: 1.1 }}>
        {value ?? '—'}
      </div>
      <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', marginTop: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </div>
      {sub && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)', marginTop: 6 }}>{sub}</div>
      )}
    </div>
  )
}

function FeedbackModal({ ticketId, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [success, setSuccess] = useState(true)

  const { mutate, isPending } = useMutation({
    mutationFn: () => api.post(`/sd/tickets/${ticketId}/auto-resolution/feedback`, { success }),
    onSuccess: () => {
      toast.success('Feedback registrado en el bucket de la ticket.')
      qc.invalidateQueries({ queryKey: ['sd-auto-resolution-stats'] })
      onClose()
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al registrar feedback'),
  })

  return (
    <Modal open title={`Feedback auto-resolución — ${ticketId}`} onClose={onClose} width={460}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <div style={fieldLabel}>¿La auto-resolución fue correcta?</div>
          <div style={{ display: 'flex', gap: 10 }}>
            <button
              type="button"
              onClick={() => setSuccess(true)}
              style={{
                flex: 1, padding: '10px 14px', borderRadius: 8,
                border: `1px solid ${success ? 'var(--success)' : 'var(--surface-4)'}`,
                background: success ? 'color-mix(in srgb, var(--success) 12%, transparent)' : 'var(--surface-3)',
                color: success ? 'var(--success)' : 'var(--text-2)',
                cursor: 'pointer', fontFamily: 'inherit', fontSize: 'var(--text-base)', fontWeight: 600,
              }}
            >👍 Correcta</button>
            <button
              type="button"
              onClick={() => setSuccess(false)}
              style={{
                flex: 1, padding: '10px 14px', borderRadius: 8,
                border: `1px solid ${!success ? 'var(--danger)' : 'var(--surface-4)'}`,
                background: !success ? 'color-mix(in srgb, var(--danger) 12%, transparent)' : 'var(--surface-3)',
                color: !success ? 'var(--danger)' : 'var(--text-2)',
                cursor: 'pointer', fontFamily: 'inherit', fontSize: 'var(--text-base)', fontWeight: 600,
              }}
            >👎 Falló</button>
          </div>
        </div>
        <div style={{
          fontSize: 'var(--text-xs)', color: 'var(--text-3)',
          background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
          borderRadius: 8, padding: '8px 12px',
        }}>
          Tu feedback alimenta el bucket category/priority del ticket y ajusta el score de
          confianza para futuras auto-resoluciones similares.
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate()} loading={isPending}>Enviar feedback</Button>
        </div>
      </div>
    </Modal>
  )
}

function FeedbackLookup({ onOpen }) {
  const [id, setId] = useState('')
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
      <input
        value={id}
        onChange={e => setId(e.target.value)}
        placeholder="ID o número del ticket (TSK-... / uuid)"
        style={{
          flex: '1 1 240px',
          background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
          borderRadius: 8, padding: '8px 12px',
          color: 'var(--text-1)', fontSize: 'var(--text-sm)',
          fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box',
        }}
      />
      <Button onClick={() => id && onOpen(id.trim())} disabled={!id.trim()}>
        Dar feedback
      </Button>
    </div>
  )
}

export default function AutoResolutionPanel() {
  const toast = useToast()
  const qc = useQueryClient()
  const [feedbackTicketId, setFeedbackTicketId] = useState(null)

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['sd-auto-resolution-stats'],
    queryFn: () => api.get('/sd/auto-resolution/stats').then(r => r.data),
    refetchInterval: 30_000,
  })

  const { mutate: runJob, isPending: runningJob } = useMutation({
    mutationFn: () => api.post('/sd/auto-resolution/run-job'),
    onSuccess: (res) => {
      const r = res.data || {}
      toast.success(
        `Job: ${r.processed ?? 0} procesados · ${r.auto_resolved ?? 0} auto-resueltos · ${r.suggested ?? 0} sugeridos · ${r.failed ?? 0} fallidos`
      )
      qc.invalidateQueries({ queryKey: ['sd-auto-resolution-stats'] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al ejecutar el job'),
  })

  const { mutate: runCloseJob, isPending: runningClose } = useMutation({
    mutationFn: () => api.post('/sd/auto-resolution/run-close-job'),
    onSuccess: (res) => {
      const r = res.data || {}
      toast.success(
        `Auto-cierre: ${r.auto_closed ?? 0} cerrados · ${r.validated ?? 0} validados · ${r.failed ?? 0} fallidos`
      )
      qc.invalidateQueries({ queryKey: ['sd-auto-resolution-stats'] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al ejecutar el job de cierre'),
  })

  const successRate = stats?.overall_success_rate
  const successColor = successRate == null ? 'var(--text-3)'
    : successRate >= 85 ? 'var(--success)'
    : successRate >= 60 ? 'var(--warning)' : 'var(--danger)'

  const buckets = stats?.per_bucket ?? []
  const topBuckets = buckets.slice(0, 6)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Stats */}
      <Card style={card}>
        <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', marginBottom: 14 }}>
          📊 Estadísticas de auto-resolución
        </div>
        {statsLoading ? <Spinner /> : (
          <>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <StatCard
                label="Auto-resueltos (total)"
                value={stats?.total_auto_resolved}
                accent="var(--success)"
                sub={stats?.pct_of_all_tickets != null ? `${stats.pct_of_all_tickets}% de todos los tickets` : undefined}
              />
              <StatCard
                label="Feedback validado"
                value={stats?.feedback_total_validated}
                accent="var(--accent)"
                sub="Tickets con feedback registrado"
              />
              <StatCard
                label="Tasa de éxito global"
                value={successRate != null ? `${successRate}%` : '—'}
                accent={successColor}
                sub={successRate == null ? 'Sin datos suficientes' : (
                  successRate >= 85 ? 'Excelente' : successRate >= 60 ? 'Aceptable' : 'Necesita ajuste'
                )}
              />
              <StatCard
                label="Buckets con datos"
                value={buckets.length || 0}
                accent="var(--purple)"
              />
            </div>

            {topBuckets.length > 0 && (
              <div style={{ marginTop: 18 }}>
                <div style={fieldLabel}>Top buckets (categoría · prioridad)</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {topBuckets.map(b => {
                    const rate = b.success_rate
                    const color = rate == null ? 'var(--text-3)'
                      : rate >= 85 ? 'var(--success)'
                      : rate >= 60 ? 'var(--warning)' : 'var(--danger)'
                    const pct = rate == null ? 0 : Math.max(0, Math.min(100, rate))
                    return (
                      <div key={b.bucket} style={{
                        background: 'var(--surface-3)',
                        border: '1px solid var(--surface-4)',
                        borderRadius: 8, padding: '8px 12px',
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, fontSize: 'var(--text-sm)' }}>
                          <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>{b.bucket}</span>
                          <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
                              {b.success}/{b.total}
                            </span>
                            <span style={{
                              fontSize: 'var(--text-xs)', fontWeight: 700, color,
                              background: `color-mix(in srgb, ${color} 15%, transparent)`,
                              border: `1px solid color-mix(in srgb, ${color} 30%, transparent)`,
                              borderRadius: 6, padding: '2px 8px',
                            }}>{rate != null ? `${rate}%` : '—'}</span>
                          </span>
                        </div>
                        <div style={{ marginTop: 6, height: 4, background: 'var(--surface-4)', borderRadius: 3, overflow: 'hidden' }}>
                          <div style={{ width: `${pct}%`, height: '100%', background: color, transition: 'width .4s' }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </>
        )}
      </Card>

      {/* Manual job triggers */}
      <Card style={card}>
        <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', marginBottom: 6 }}>
          ⚡ Acciones manuales
        </div>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', marginBottom: 14 }}>
          Los jobs también se ejecutan de forma programada en background.
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <Button onClick={() => runJob()} loading={runningJob}>
            ▶ Ejecutar auto-resolución
          </Button>
          <Button onClick={() => runCloseJob()} loading={runningClose} variant="secondary">
            🔒 Ejecutar auto-cierre
          </Button>
        </div>
      </Card>

      {/* Feedback */}
      <Card style={card}>
        <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', marginBottom: 6 }}>
          💬 Feedback por ticket
        </div>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', marginBottom: 14 }}>
          Registra si la resolución automática fue correcta para un ticket — ajusta el bucket de confianza.
        </div>
        <FeedbackLookup onOpen={id => setFeedbackTicketId(id)} />
      </Card>

      {feedbackTicketId && (
        <FeedbackModal ticketId={feedbackTicketId} onClose={() => setFeedbackTicketId(null)} />
      )}
    </div>
  )
}
