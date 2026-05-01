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
import { npsApi, clientsApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Star } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

const fs = { width: '100%', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

const HEALTH_COLOR = (score) => score >= 75 ? 'var(--success)' : score >= 50 ? 'var(--orange)' : 'var(--danger)'

function HealthBadge({ score }) {
  const c = HEALTH_COLOR(score)
  return (
    <span style={{ fontWeight: 800, fontSize: "var(--text-md-em)", color: c }}>{Math.round(score)}</span>
  )
}

function NpsTrendChart({ trend }) {
  const t = useAppT();
  if (!trend || trend.length === 0) {
    return <div style={{ textAlign: 'center', padding: 24, color: 'var(--surface-5)', fontSize: "var(--text-sm)" }}>{t('nps.no_trend')}</div>;
  }
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={trend} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
        <XAxis dataKey="month" tick={{ fill: 'var(--text-2)', fontSize: "var(--text-2xs)" }} />
        <YAxis domain={[-100, 100]} tick={{ fill: 'var(--text-2)', fontSize: "var(--text-2xs)" }} />
        <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--surface-5)', borderRadius: 8 }} labelStyle={{ color: 'var(--text-1)' }} />
        <ReferenceLine y={0} stroke="var(--surface-5)" />
        <ReferenceLine y={50} stroke="var(--success)" strokeDasharray="4 2" opacity={0.5} />
        <Line type="monotone" dataKey="nps" stroke="var(--info)" strokeWidth={2} dot={{ r: 3, fill: 'var(--info)' }} name="NPS" />
      </LineChart>
    </ResponsiveContainer>
  )
}

function HealthChart({ data }) {
  const t = useAppT();
  if (!data || data.length === 0) {
    return <div style={{ textAlign: 'center', padding: 24, color: 'var(--surface-5)', fontSize: "var(--text-sm)" }}>{t('nps.no_health_snapshots')}</div>;
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
            <stop offset="5%" stopColor="var(--info)" stopOpacity={0.25} />
            <stop offset="95%" stopColor="var(--info)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
        <XAxis dataKey="date" tick={{ fill: 'var(--text-2)', fontSize: "var(--text-2xs)" }} />
        <YAxis domain={[0, 100]} tick={{ fill: 'var(--text-2)', fontSize: "var(--text-2xs)" }} />
        <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--surface-5)', borderRadius: 8 }} labelStyle={{ color: 'var(--text-1)' }} />
        <Area type="monotone" dataKey="health" stroke="var(--info)" fill="url(#healthGrad)" strokeWidth={2} name="Salud" dot={false} />
        <ReferenceLine y={75} stroke="var(--success)" strokeDasharray="4 2" opacity={0.5} />
        <ReferenceLine y={50} stroke="var(--orange)" strokeDasharray="4 2" opacity={0.5} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

function NPSGauge({ nps }) {
  const t = useAppT();
  if (nps === null || nps === undefined) return <div style={{ color: 'var(--surface-5)', fontSize: "var(--text-base)", textAlign: 'center', padding: 12 }}>{t('nps.no_data')}</div>;
  const color = nps >= 50 ? 'var(--success)' : nps >= 0 ? 'var(--orange)' : 'var(--danger)'
  return (
    <div style={{ textAlign: 'center', padding: '8px 0' }}>
      <div style={{ fontSize: "var(--text-42)", fontWeight: 900, color }}>{nps > 0 ? `+${nps}` : nps}</div>
      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>NPS</div>
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
    queryFn: () => npsApi.leaderboard().then(r => r.data),
    refetchInterval: 60000,
  })

  const { data: clients = [] } = useQuery({
    queryKey: ['clients-list-nps'],
    queryFn: () => clientsApi.list().then(r => Array.isArray(r.data) ? r.data : r.data?.items || []),
  })

  const { data: summary } = useQuery({
    queryKey: ['nps-summary', clientId, npsDays],
    queryFn: () => npsApi.summary(clientId, npsDays).then(r => r.data),
    enabled: !!clientId,
  })

  const { data: health = [] } = useQuery({
    queryKey: ['health-history', clientId],
    queryFn: () => npsApi.health(clientId, 30).then(r => r.data),
    enabled: !!clientId,
  })

  const { mutate: computeHealth, isLoading: computing } = useMutation({
    mutationFn: () => npsApi.healthCompute(clientId),
    onSuccess: () => qc.invalidateQueries(['health-history', clientId, 'health-leaderboard']),
  })

  const submitNPS = async () => {
    if (!clientId) return
    setSubmitting(true)
    try {
      await npsApi.respond(clientId, {
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
    <PageShell style={{ maxWidth: 1100, margin: '0 auto' }}>
      <PageHeader
        icon={<Star size={18} />}
        title={t('nps.title')}
        subtitle={t('nps.subtitle')}
      />
      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: 20, alignItems: 'start' }}>
        {/* Leaderboard sidebar */}
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase' }}>
            {t('nps.ranking')}
          </div>
          {/* Clients without snapshots */}
          {clients.filter(c => !leaderboard.find(l => l.client_id === c.id)).length > 0 && leaderboard.length === 0 && (
            <div style={{ padding: 12 }}>
              {clients.map(c => (
                <button key={c.id} onClick={() => setClientId(c.id)} style={{
                  display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                  background: clientId === c.id ? 'var(--surface-4)' : 'none',
                  border: 'none', borderRadius: 6, padding: '7px 10px', cursor: 'pointer', marginBottom: 2,
                }}>
                  <span style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', textAlign: 'left', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</span>
                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--surface-5)' }}>—</span>
                </button>
              ))}
            </div>
          )}
          {leaderboard.map((l, i) => (
            <button key={l.client_id} onClick={() => setClientId(l.client_id)} style={{
              display: 'flex', alignItems: 'center', gap: 8, width: '100%',
              background: clientId === l.client_id ? 'var(--surface-4)' : 'none',
              border: 'none', borderLeft: clientId === l.client_id ? '3px solid var(--info)' : '3px solid transparent',
              padding: '9px 14px', cursor: 'pointer', borderBottom: '1px solid var(--surface-4)',
            }}>
              <span style={{ fontSize: "var(--text-xs)", color: 'var(--surface-5)', width: 16 }}>{i + 1}</span>
              <span style={{ flex: 1, fontSize: "var(--text-base)", color: 'var(--text-1)', textAlign: 'left', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.client_name}</span>
              <HealthBadge score={l.health_score} />
            </button>
          ))}
          {leaderboard.length === 0 && clients.length === 0 && (
            <div style={{ padding: 20, textAlign: 'center', color: 'var(--surface-5)', fontSize: "var(--text-sm)" }}>{t('nps.no_clients')}</div>
          )}
        </div>
        {/* Right panel */}
        {!clientId ? (
          <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 60, textAlign: 'center', color: 'var(--surface-5)', fontSize: "var(--text-md)" }}>
            {t('nps.select_client')}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Client header */}
            <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 16 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 800, color: 'var(--text-1)' }}>{selectedClient?.name || clientId}</div>
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 2 }}>{selectedClient?.contact_email || ''}</div>
              </div>
              {latestHealth !== undefined && (
                <div style={{ textAlign: 'center', padding: '0 20px', borderLeft: '1px solid var(--surface-4)' }}>
                  <div style={{ fontSize: "var(--text-3xl)", fontWeight: 900, color: HEALTH_COLOR(latestHealth) }}>{Math.round(latestHealth)}</div>
                  <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)' }}>{t('nps.current_health')}</div>
                </div>
              )}
              <button
                onClick={() => computeHealth()}
                disabled={computing}
                style={{ background: 'var(--accent-glow)', border: 'none', borderRadius: 8, color: 'var(--info)', padding: '8px 14px', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', whiteSpace: 'nowrap' }}>
                {computing ? t('nps.calculating') : t('nps.calc_health')}
              </button>
            </div>
            {/* NPS summary */}
            <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 18 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)' }}>{t('nps.nps')}</div>
                <select value={npsDays} onChange={e => setNpsDays(Number(e.target.value))}
                  style={{ ...fs, width: 120 }}>
                  {[30, 60, 90, 180, 365].map(d => <option key={d} value={d}>{t('nps.last_days').replace('{d}', d)}</option>)}
                </select>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: 16, alignItems: 'center' }}>
                <div>
                  <NPSGauge nps={summary?.nps} />
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }}>
                    {[
                      { label: t('nps.promoters'), key: 'promoters', color: 'var(--success)' },
                      { label: t('nps.passives'),  key: 'passives',  color: 'var(--orange)' },
                      { label: t('nps.detractors'),key: 'detractors',color: 'var(--danger)' },
                    ].map(({ label, key, color }) => (
                      <div key={key} style={{ display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-xs)" }}>
                        <span style={{ color: 'var(--text-2)' }}>{label}</span>
                        <span style={{ color }}>{summary?.[key] ?? 0}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <NpsTrendChart trend={summary?.trend} />
              </div>
            </div>
            {/* Health trend */}
            <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 18 }}>
              <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 12 }}>{t('nps.health_trend')}</div>
              <HealthChart data={health} />
            </div>
            {/* Submit NPS */}
            <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 18 }}>
              <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 14 }}>{t('nps.register_nps')}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div>
                  <label style={ls}>{t('nps.score_label')}</label>
                  <div style={{ display: 'flex', gap: 6 }}>
                    {[0,1,2,3,4,5,6,7,8,9,10].map(n => (
                      <button key={n} onClick={() => setScoreInput(n)} style={{
                        width: 32, height: 32, borderRadius: 6,
                        background: scoreInput === n
                          ? (n >= 9 ? 'color-mix(in srgb, var(--success) 25%, var(--surface-2))'
                             : n >= 7 ? 'color-mix(in srgb, var(--orange) 25%, var(--surface-2))'
                             : 'color-mix(in srgb, var(--danger) 25%, var(--surface-2))')
                          : 'var(--surface-4)',
                        border: `1px solid ${scoreInput === n ? (n >= 9 ? 'var(--success)' : n >= 7 ? 'var(--orange)' : 'var(--danger)') : 'var(--surface-5)'}`,
                        color: scoreInput === n ? 'var(--text-1)' : 'var(--text-2)',
                        cursor: 'pointer', fontWeight: 700, fontSize: "var(--text-sm)", fontFamily: 'inherit',
                      }}>{n}</button>
                    ))}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 10 }}>
                  <div style={{ flex: 1 }}>
                    <label style={ls}>{t('nps.respondent')}</label>
                    <input value={respondent} onChange={e => setRespondent(e.target.value)}
                      style={fs} placeholder={t('nps.respondent')} />
                  </div>
                </div>
                <div>
                  <label style={ls}>{t('nps.comment')}</label>
                  <textarea value={comment} onChange={e => setComment(e.target.value)}
                    style={{ ...fs, resize: 'vertical' }} rows={2} placeholder={t('nps.comment')} />
                </div>
                <button onClick={submitNPS} disabled={submitting} style={{
                  alignSelf: 'flex-start', background: 'var(--accent-glow)', border: 'none', borderRadius: 8,
                  color: 'var(--info)', padding: '9px 20px', cursor: 'pointer', fontWeight: 700,
                  fontSize: "var(--text-base)", fontFamily: 'inherit',
                }}>
                  {submitting ? t('nps.sending') : t('nps.submit_nps')}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </PageShell>
  );
}
