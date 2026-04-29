/**
 * AutoResolutionPanel — AI auto-resolution dashboard for ITSM
 *
 * Shows resolution stats, lets ops trigger the daily job or the
 * auto-close job, and allows per-ticket feedback submission.
 *
 * Backend endpoints:
 *   GET  /sd/auto-resolution/stats
 *   POST /sd/auto-resolution/run-job
 *   POST /sd/auto-resolution/run-close-job
 *   POST /sd/tickets/{id}/auto-resolution/feedback
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { Button, Spinner, Modal } from '../ui'
import { useToast } from '../../context/ToastContext'
import { COLOR } from '../../constants/theme'

const card = {
  background: 'var(--surface-2)',
  border: '1px solid var(--surface-4)',
  borderRadius: 12,
  padding: '20px 24px',
}

const statBox = (accent) => ({
  background: `${accent}12`,
  border: `1px solid ${accent}30`,
  borderRadius: 10,
  padding: '16px 20px',
  textAlign: 'center',
  flex: 1,
  minWidth: 100,
})

function StatCard({ label, value, accent = COLOR.accent }) {
  return (
    <div style={statBox(accent)}>
      <div style={{ fontSize: 26, fontWeight: 700, color: accent }}>{value ?? '—'}</div>
      <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>{label}</div>
    </div>
  )
}

function FeedbackModal({ ticketId, onClose }) {
  const toast = useToast()
  const [helpful, setHelpful] = useState(true)
  const [comment, setComment] = useState('')
  const IS = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const LS = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

  const { mutate, isPending } = useMutation({
    mutationFn: () => api.post(`/sd/tickets/${ticketId}/auto-resolution/feedback`, { helpful, comment }),
    onSuccess: () => { toast.success('Feedback enviado'); onClose() },
    onError: () => toast.error('Error al enviar feedback'),
  })

  return (
    <Modal open title={`Feedback auto-resolución — Ticket #${ticketId}`} onClose={onClose} size="md">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label style={LS}>¿Fue útil la resolución automática?</label>
          <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
            <button onClick={() => setHelpful(true)} style={{ flex: 1, padding: '8px 0', borderRadius: 8, border: `1px solid ${helpful ? COLOR.success : 'var(--surface-4)'}`, background: helpful ? `${COLOR.success}15` : 'transparent', color: helpful ? COLOR.success : 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: 600 }}>
              👍 Sí, fue útil
            </button>
            <button onClick={() => setHelpful(false)} style={{ flex: 1, padding: '8px 0', borderRadius: 8, border: `1px solid ${!helpful ? COLOR.danger : 'var(--surface-4)'}`, background: !helpful ? `${COLOR.danger}15` : 'transparent', color: !helpful ? COLOR.danger : 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: 600 }}>
              👎 No, falló
            </button>
          </div>
        </div>
        <div>
          <label style={LS}>Comentario (opcional)</label>
          <textarea value={comment} onChange={e => setComment(e.target.value)} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder="Explica qué salió bien o mal…" />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate()} loading={isPending}>Enviar feedback</Button>
        </div>
      </div>
    </Modal>
  )
}

export default function AutoResolutionPanel() {
  const toast = useToast()
  const qc = useQueryClient()
  const [feedbackTicketId, setFeedbackTicketId] = useState(null)

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['sd-auto-resolution-stats'],
    queryFn: () => api.get('/sd/auto-resolution/stats').then(r => r.data),
    refetchInterval: 30000,
  })

  const { mutate: runJob, isPending: runningJob } = useMutation({
    mutationFn: () => api.post('/sd/auto-resolution/run-job'),
    onSuccess: (res) => {
      toast.success(`Job completado: ${res.data?.auto_resolved ?? 0} tickets auto-resueltos`)
      qc.invalidateQueries({ queryKey: ['sd-auto-resolution-stats'] })
    },
    onError: () => toast.error('Error al ejecutar el job'),
  })

  const { mutate: runCloseJob, isPending: runningClose } = useMutation({
    mutationFn: () => api.post('/sd/auto-resolution/run-close-job'),
    onSuccess: (res) => {
      toast.success(`Auto-cierre: ${res.data?.closed ?? 0} tickets cerrados`)
      qc.invalidateQueries({ queryKey: ['sd-auto-resolution-stats'] })
    },
    onError: () => toast.error('Error al ejecutar el job de cierre'),
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Stats */}
      <div style={card}>
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)', marginBottom: 16 }}>
          📊 Estadísticas de auto-resolución
        </div>
        {statsLoading ? (
          <Spinner />
        ) : (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <StatCard label="Auto-resueltos" value={stats?.total_auto_resolved} accent={COLOR.success} />
            <StatCard label="Auto-cerrados" value={stats?.total_auto_closed} accent={COLOR.info ?? '#63b3ed'} />
            <StatCard label="Feedback positivo" value={stats?.positive_feedback} accent={COLOR.success} />
            <StatCard label="Feedback negativo" value={stats?.negative_feedback} accent={COLOR.danger} />
            <StatCard label="Confianza media" value={stats?.avg_confidence != null ? `${Math.round(stats.avg_confidence * 100)}%` : '—'} accent={COLOR.warning} />
          </div>
        )}
      </div>

      {/* Manual job triggers */}
      <div style={card}>
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)', marginBottom: 8 }}>
          ⚡ Acciones manuales
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 16 }}>
          Los jobs también se ejecutan automáticamente de forma programada.
        </div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Button onClick={() => runJob()} loading={runningJob}>
            ▶ Ejecutar auto-resolución ahora
          </Button>
          <Button onClick={() => runCloseJob()} loading={runningClose} variant="secondary">
            🔒 Ejecutar auto-cierre ahora
          </Button>
        </div>
      </div>

      {/* Feedback lookup */}
      <div style={card}>
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)', marginBottom: 8 }}>
          💬 Enviar feedback por ticket
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 14 }}>
          Indica si la resolución automática fue correcta para un ticket específico.
        </div>
        <FeedbackLookup onOpen={id => setFeedbackTicketId(id)} />
      </div>

      {feedbackTicketId && (
        <FeedbackModal ticketId={feedbackTicketId} onClose={() => setFeedbackTicketId(null)} />
      )}
    </div>
  )
}

function FeedbackLookup({ onOpen }) {
  const [id, setId] = useState('')
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
      <input
        value={id}
        onChange={e => setId(e.target.value)}
        placeholder="ID del ticket…"
        type="number"
        min="1"
        style={{ width: 140, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit' }}
      />
      <Button onClick={() => id && onOpen(Number(id))} disabled={!id}>
        Dar feedback
      </Button>
    </div>
  )
}
