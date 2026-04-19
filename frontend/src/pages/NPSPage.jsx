/**
 * NPSPage — Customer NPS & Health trend dashboard
 *
 * ─ Leaderboard sidebar (all clients by health score)
 * ─ Right panel for selected client:
 *     NPS summary + trend line chart
 *     Health history area chart
 *     Submit NPS form
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ResponsiveContainer, LineChart, Line, AreaChart, Area,
  XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine,
} from 'recharts'
import api from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const fs = { width: '100%', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

const HEALTH_COLOR = (score) => score >= 75 ? '#68d391' : score >= 50 ? '#f6ad55' : '#fc8181'

function HealthBadge({ score }) {
  const c = HEALTH_COLOR(score)
  return (
    <span style={{ fontWeight: 800, fontSize: 15, color: c }}>{Math.round(score)}</span>
  )
}

function NpsTrendChart({ trend }) {
  if (!trend || trend.length === 0) {
    return <div style={{ textAlign: 'center', padding: 24, color: '#4a5568', fontSize: 12 }}>Sin datos de tendencia</div>
  }
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={trend} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
        <XAxis dataKey="month" tick={{ fill: '#718096', fontSize: 10 }} />
        <YAxis domain={[-100, 100]} tick={{ fill: '#718096', fontSize: 10 }} />
        <Tooltip contentStyle={{ background: '#1a202c', border: '1px solid #4a5568', borderRadius: 8 }} labelStyle={{ color: '#e2e8f0' }} />
        <ReferenceLine y={0} stroke="#4a5568" />
        <ReferenceLine y={50} stroke="#68d391" strokeDasharray="4 2" opacity={0.5} />
        <Line type="monotone" dataKey="nps" stroke="#90cdf4" strokeWidth={2} dot={{ r: 3, fill: '#90cdf4' }} name="NPS" />
      </LineChart>
    </ResponsiveContainer>
  )
}

function HealthChart({ data }) {
  if (!data || data.length === 0) {
    return <div style={{ textAlign: 'center', padding: 24, color: '#4a5568', fontSize: 12 }}>Sin snapshots de salud</div>
  }
  const chartData = [...data].reverse().map(d => ({
    date: new Date(d.snapshot_at).toLocaleDateString('es-ES', { day: '2-digit', month: 'short' }),
    health: d.health_score,
  }))
  return (
    <ResponsiveContainer width="100%" height={160}>
      <AreaChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
        <defs>
          <linearGradient id="healthGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#90cdf4" stopOpacity={0.25} />
            <stop offset="95%" stopColor="#90cdf4" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
        <XAxis dataKey="date" tick={{ fill: '#718096', fontSize: 10 }} />
        <YAxis domain={[0, 100]} tick={{ fill: '#718096', fontSize: 10 }} />
        <Tooltip contentStyle={{ background: '#1a202c', border: '1px solid #4a5568', borderRadius: 8 }} labelStyle={{ color: '#e2e8f0' }} />
        <Area type="monotone" dataKey="health" stroke="#90cdf4" fill="url(#healthGrad)" strokeWidth={2} name="Salud" dot={false} />
        <ReferenceLine y={75} stroke="#68d391" strokeDasharray="4 2" opacity={0.5} />
        <ReferenceLine y={50} stroke="#f6ad55" strokeDasharray="4 2" opacity={0.5} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

function NPSGauge({ nps }) {
  if (nps === null || nps === undefined) return <div style={{ color: '#4a5568', fontSize: 13, textAlign: 'center', padding: 12 }}>Sin datos</div>
  const color = nps >= 50 ? '#68d391' : nps >= 0 ? '#f6ad55' : '#fc8181'
  return (
    <div style={{ textAlign: 'center', padding: '8px 0' }}>
      <div style={{ fontSize: 42, fontWeight: 900, color }}>{nps > 0 ? `+${nps}` : nps}</div>
      <div style={{ fontSize: 11, color: '#718096' }}>NPS</div>
    </div>
  )
}

export default function NPSPage() {
  const t = useAppT()
  const [clientId,    setClientId]    = useState(null)
  const [npsDays,     setNpsDays]     = useState(90)
  const [scoreInput,  setScoreInput]  = useState(9)
  const [comment,     setComment]     = useState('')
  const [respondent,  setRespondent]  = useState('')
  const [submitting,  setSubmitting]  = useState(false)
  const qc = useQueryClient()

  const { data: leaderboard = [] } = useQuery({
    queryKey: ['health-leaderboard'],
    queryFn: () => api.get('/nps/leaderboard').then(r => r.data),
    refetchInterval: 60000,
  })

  const { data: clients = [] } = useQuery({
    queryKey: ['clients-list-nps'],
    queryFn: () => api.get('/clients').then(r => Array.isArray(r.data) ? r.data : r.data?.items || []),
  })

  const { data: summary } = useQuery({
    queryKey: ['nps-summary', clientId, npsDays],
    queryFn: () => api.get(`/nps/${clientId}/summary?days=${npsDays}`).then(r => r.data),
    enabled: !!clientId,
  })

  const { data: health = [] } = useQuery({
    queryKey: ['health-history', clientId],
    queryFn: () => api.get(`/nps/${clientId}/health?limit=30`).then(r => r.data),
    enabled: !!clientId,
  })

  const { mutate: computeHealth, isLoading: computing } = useMutation({
    mutationFn: () => api.post(`/nps/${clientId}/health-compute`),
    onSuccess: () => qc.invalidateQueries(['health-history', clientId, 'health-leaderboard']),
  })

  const submitNPS = async () => {
    if (!clientId) return
    setSubmitting(true)
    try {
      await api.post(`/nps/${clientId}/responses`, {
        score: Number(scoreInput), comment, respondent, source: 'manual',
      })
      setComment(''); setRespondent(''); setScoreInput(9)
      qc.invalidateQueries(['nps-summary', clientId, npsDays])
    } finally {
      setSubmitting(false)
    }
  }

  const selectedClient = clients.find(c => c.id === clientId)
  const latestHealth = health[0]?.health_score

  return (
    <div style={{ padding: 32, maxWidth: 1100, margin: '0 auto' }}>
      <PageHeader
        title={t('nps.title')}
        subtitle={t('nps.subtitle')}
      />

      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: 20, alignItems: 'start' }}>
        {/* Leaderboard sidebar */}
        <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid #2d3748', fontSize: 12, fontWeight: 700, color: '#718096', textTransform: 'uppercase' }}>
            Ranking salud
          </div>

          {/* Clients without snapshots */}
          {clients.filter(c => !leaderboard.find(l => l.client_id === c.id)).length > 0 && leaderboard.length === 0 && (
            <div style={{ padding: 12 }}>
              {clients.map(c => (
                <button key={c.id} onClick={() => setClientId(c.id)} style={{
                  display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                  background: clientId === c.id ? '#2d3748' : 'none',
                  border: 'none', borderRadius: 6, padding: '7px 10px', cursor: 'pointer', marginBottom: 2,
                }}>
                  <span style={{ fontSize: 13, color: '#e2e8f0', textAlign: 'left', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</span>
                  <span style={{ fontSize: 11, color: '#4a5568' }}>—</span>
                </button>
              ))}
            </div>
          )}

          {leaderboard.map((l, i) => (
            <button key={l.client_id} onClick={() => setClientId(l.client_id)} style={{
              display: 'flex', alignItems: 'center', gap: 8, width: '100%',
              background: clientId === l.client_id ? '#2d3748' : 'none',
              border: 'none', borderLeft: clientId === l.client_id ? '3px solid #63b3ed' : '3px solid transparent',
              padding: '9px 14px', cursor: 'pointer', borderBottom: '1px solid #1e2d45',
            }}>
              <span style={{ fontSize: 11, color: '#4a5568', width: 16 }}>{i + 1}</span>
              <span style={{ flex: 1, fontSize: 13, color: '#e2e8f0', textAlign: 'left', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.client_name}</span>
              <HealthBadge score={l.health_score} />
            </button>
          ))}

          {leaderboard.length === 0 && clients.length === 0 && (
            <div style={{ padding: 20, textAlign: 'center', color: '#4a5568', fontSize: 12 }}>Sin clientes</div>
          )}
        </div>

        {/* Right panel */}
        {!clientId ? (
          <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: 60, textAlign: 'center', color: '#4a5568', fontSize: 14 }}>
            Selecciona un cliente para ver su NPS y salud
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Client header */}
            <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 16 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 18, fontWeight: 800, color: '#e2e8f0' }}>{selectedClient?.name || clientId}</div>
                <div style={{ fontSize: 12, color: '#718096', marginTop: 2 }}>{selectedClient?.contact_email || ''}</div>
              </div>
              {latestHealth !== undefined && (
                <div style={{ textAlign: 'center', padding: '0 20px', borderLeft: '1px solid #2d3748' }}>
                  <div style={{ fontSize: 28, fontWeight: 900, color: HEALTH_COLOR(latestHealth) }}>{Math.round(latestHealth)}</div>
                  <div style={{ fontSize: 10, color: '#718096' }}>Salud actual</div>
                </div>
              )}
              <button
                onClick={() => computeHealth()}
                disabled={computing}
                style={{ background: '#2b4a7a', border: 'none', borderRadius: 8, color: '#90cdf4', padding: '8px 14px', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', whiteSpace: 'nowrap' }}>
                {computing ? 'Calculando…' : '⚙ Calcular salud'}
              </button>
            </div>

            {/* NPS summary */}
            <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: 18 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#e2e8f0' }}>NPS</div>
                <select value={npsDays} onChange={e => setNpsDays(Number(e.target.value))}
                  style={{ ...fs, width: 120 }}>
                  {[30, 60, 90, 180, 365].map(d => <option key={d} value={d}>Últimos {d}d</option>)}
                </select>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: 16, alignItems: 'center' }}>
                <div>
                  <NPSGauge nps={summary?.nps} />
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }}>
                    {[
                      { label: 'Promotores', key: 'promoters', color: '#68d391' },
                      { label: 'Pasivos',    key: 'passives',  color: '#f6ad55' },
                      { label: 'Detractores',key: 'detractors',color: '#fc8181' },
                    ].map(({ label, key, color }) => (
                      <div key={key} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                        <span style={{ color: '#718096' }}>{label}</span>
                        <span style={{ color }}>{summary?.[key] ?? 0}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <NpsTrendChart trend={summary?.trend} />
              </div>
            </div>

            {/* Health trend */}
            <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: 18 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#e2e8f0', marginBottom: 12 }}>Evolución de salud</div>
              <HealthChart data={health} />
            </div>

            {/* Submit NPS */}
            <div style={{ background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: 18 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#e2e8f0', marginBottom: 14 }}>Registrar nueva encuesta NPS</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div>
                  <label style={ls}>Puntuación (0–10)</label>
                  <div style={{ display: 'flex', gap: 6 }}>
                    {[0,1,2,3,4,5,6,7,8,9,10].map(n => (
                      <button key={n} onClick={() => setScoreInput(n)} style={{
                        width: 32, height: 32, borderRadius: 6,
                        background: scoreInput === n
                          ? (n >= 9 ? '#276227' : n >= 7 ? '#7b4a00' : '#6b1a1a')
                          : '#2d3748',
                        border: `1px solid ${scoreInput === n ? (n >= 9 ? '#68d391' : n >= 7 ? '#f6ad55' : '#fc8181') : '#4a5568'}`,
                        color: scoreInput === n ? '#e2e8f0' : '#718096',
                        cursor: 'pointer', fontWeight: 700, fontSize: 12, fontFamily: 'inherit',
                      }}>{n}</button>
                    ))}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 10 }}>
                  <div style={{ flex: 1 }}>
                    <label style={ls}>Respondente</label>
                    <input value={respondent} onChange={e => setRespondent(e.target.value)}
                      style={fs} placeholder={t(modulo.clave)} />
                  </div>
                </div>
                <div>
                  <label style={ls}>Comentario (opcional)</label>
                  <textarea value={comment} onChange={e => setComment(e.target.value)}
                    style={{ ...fs, resize: 'vertical' }} rows={2} placeholder={t(modulo.clave)} />
                </div>
                <button onClick={submitNPS} disabled={submitting} style={{
                  alignSelf: 'flex-start', background: '#2b4a7a', border: 'none', borderRadius: 8,
                  color: '#90cdf4', padding: '9px 20px', cursor: 'pointer', fontWeight: 700,
                  fontSize: 13, fontFamily: 'inherit',
                }}>
                  {submitting ? 'Enviando…' : '📨 Registrar respuesta NPS'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
