/**
 * NPSPage — Customer NPS & Health trend dashboard
 *
 * ─ Leaderboard sidebar (all clients by health score)
 * ─ Right panel for selected client:
 *     NPS summary + trend line chart
 *     Health history area chart
 *     Submit NPS form
 */

import { useState, useId } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ResponsiveContainer, LineChart, Line, AreaChart, Area,
  XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine,
} from 'recharts'
import { npsApi, clientsApi } from '../services/api'
import type { FotoDeSalud, ResumenNps } from '../services/api/tipos-personas'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Star } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import useMediaQuery from '../hooks/useMediaQuery'
import type { CSSProperties } from 'react'
import { localeActivo } from '../utils/helpers'
import { POLL_DEFAULT_MS } from '../constants/timings'
import { NPS_CLIENTS_LIST_SIZE } from '../constants/pagination'
import './NPSPage.css'
import { ETIQUETA_TEXTO_1, TOOLTIP_SUPERFICIE_2_BORDE_5 } from '../constants/estilosGrafico'

interface ClientItem {
  id: string | number
  name?: string
  contact_email?: string
}

type NpsTrendPoint = ResumenNps['trend'][number]
type NpsSummary = ResumenNps
type HealthSnapshot = FotoDeSalud


const HEALTH_COLOR = (score: number) => score >= 75 ? 'var(--success)' : score >= 50 ? 'var(--orange)' : 'var(--danger)'

function HealthBadge({ score }: { score: number }) {
  const c = HEALTH_COLOR(score)
  return (
    <span className="nps-label npspage-e1" style={{ '--npspage-color': c } as CSSProperties}>{Math.round(score)}</span>
  )
}

function NpsTrendChart({ trend }: { trend?: NpsTrendPoint[] }) {
  const t = useAppT();
  if (!trend || trend.length === 0) {
    return <div className="nps-box">{t('nps.no_trend')}</div>;
  }
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={trend} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
        <XAxis dataKey="month" tick={{ fill: 'var(--text-2)', fontSize: "var(--text-2xs)" }} />
        <YAxis domain={[-100, 100]} tick={{ fill: 'var(--text-2)', fontSize: "var(--text-2xs)" }} />
        <Tooltip contentStyle={TOOLTIP_SUPERFICIE_2_BORDE_5} labelStyle={ETIQUETA_TEXTO_1} />
        <ReferenceLine y={0} stroke="var(--surface-5)" />
        <ReferenceLine y={50} stroke="var(--success)" strokeDasharray="4 2" opacity={0.5} />
        <Line type="monotone" dataKey="nps" stroke="var(--info)" strokeWidth={2} dot={{ r: 3, fill: 'var(--info)' }} name="NPS" />
      </LineChart>
    </ResponsiveContainer>
  )
}

function HealthChart({ data }: { data?: HealthSnapshot[] }) {
  const t = useAppT();
  if (!data || data.length === 0) {
    return <div className="nps-box">{t('nps.no_health_snapshots')}</div>;
  }
  const chartData = [...data].reverse().map(d => ({
    date: new Date(d.snapshot_at).toLocaleDateString(localeActivo(), { day: '2-digit', month: 'short' }),
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
        <Tooltip contentStyle={TOOLTIP_SUPERFICIE_2_BORDE_5} labelStyle={ETIQUETA_TEXTO_1} />
        <Area type="monotone" dataKey="health" stroke="var(--info)" fill="url(#healthGrad)" strokeWidth={2} name="Salud" dot={false} />
        <ReferenceLine y={75} stroke="var(--success)" strokeDasharray="4 2" opacity={0.5} />
        <ReferenceLine y={50} stroke="var(--orange)" strokeDasharray="4 2" opacity={0.5} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

function NPSGauge({ nps }: { nps?: number | null }) {
  const t = useAppT();
  if (nps === null || nps === undefined) return <div className="nps-box-2">{t('nps.no_data')}</div>;
  const color = nps >= 50 ? 'var(--success)' : nps >= 0 ? 'var(--orange)' : 'var(--danger)'
  return (
    <div className="nps-box-3">
      <div className="nps-box-4 npspage-e1" style={{ '--npspage-color': color } as CSSProperties}>{nps > 0 ? `+${nps}` : nps}</div>
      <div className="u-text2-xs">NPS</div>
    </div>
  )
}

export default function NPSPage() {
  const idCampo = useId()
  const t = useAppT()
  const narrow = useMediaQuery('(max-width: 900px)')
  const [clientId,    setClientId]    = useState<string | number | null>(null)
  const [npsDays,     setNpsDays]     = useState(90)
  const [scoreInput,  setScoreInput]  = useState(9)
  const [comment,     setComment]     = useState('')
  const [respondent,  setRespondent]  = useState('')
  const [submitting,  setSubmitting]  = useState(false)
  const qc = useQueryClient()

  const { data: leaderboard = [] } = useQuery({
    queryKey: ['health-leaderboard'],
    queryFn: () => npsApi.leaderboard().then(r => r.data),
    refetchInterval: POLL_DEFAULT_MS,
  })

  const { data: clientsRaw = [] } = useQuery({
    queryKey: ['clients-list-nps'],
    queryFn: () => clientsApi.list({ page_size: NPS_CLIENTS_LIST_SIZE }).then(r => r.data ?? []),
  })
  const clients = clientsRaw as ClientItem[]

  const { data: summary = null } = useQuery<NpsSummary | null>({
    queryKey: ['nps-summary', clientId, npsDays],
    queryFn: () => npsApi.summary(clientId, npsDays).then(r => r.data),
    enabled: !!clientId,
  })

  const { data: health = [] } = useQuery({
    queryKey: ['health-history', clientId],
    queryFn: () => npsApi.health(clientId, 30).then(r => r.data),
    enabled: !!clientId,
  })

  const { mutate: computeHealth, isPending: computing } = useMutation({
    mutationFn: () => npsApi.healthCompute(clientId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['health-history', clientId] })
      qc.invalidateQueries({ queryKey: ['health-leaderboard'] })
    },
  })

  const submitNPS = async () => {
    if (!clientId) return
    setSubmitting(true)
    try {
      await npsApi.respond(clientId, {
        score: Number(scoreInput), comment, respondent, source: 'manual',
      })
      setComment(''); setRespondent(''); setScoreInput(9)
      qc.invalidateQueries({ queryKey: ['nps-summary', clientId, npsDays] })
    } finally {
      setSubmitting(false)
    }
  }

  const selectedClient = clients.find((c) => c.id === clientId)
  const latestHealth = health[0]?.health_score

  return (
    <PageShell className="nps-box-15">
      <PageHeader
        icon={<Star size={18} />}
        title={t('nps.title')}
        subtitle={t('nps.subtitle')}
      showListExport={false}
      />
      <div className={`nps-grid ${narrow ? 'npspage-sx1' : 'npspage-sx2'}`}>
        {/* Leaderboard sidebar */}
        <div className="nps-card">
          <div className="nps-box-5">
            {t('nps.ranking')}
          </div>
          {/* Clients without snapshots */}
          {clients.filter(c => !leaderboard.find(l => l.client_id === c.id)).length > 0 && leaderboard.length === 0 && (
            <div className="nps-box-6">
              {clients.map(c => (
                <button key={c.id} onClick={() => setClientId(c.id)} className={`nps-btn ${clientId === c.id ? 'npspage-sx3' : 'npspage-sx4'}`}>
                  <span className="nps-label-2">{c.name}</span>
                  <span className="nps-label-3">—</span>
                </button>
              ))}
            </div>
          )}
          {leaderboard.map((l, i) => (
            <button key={l.client_id} onClick={() => setClientId(l.client_id)} className={`nps-btn-2 npspage-sx5 ${clientId === l.client_id ? 'npspage-sx6' : 'npspage-sx7'}`}>
              <span className="nps-label-4">{i + 1}</span>
              <span className="nps-label-5">{l.client_name}</span>
              <HealthBadge score={l.health_score} />
            </button>
          ))}
          {leaderboard.length === 0 && clients.length === 0 && (
            <div className="nps-box-7">{t('nps.no_clients')}</div>
          )}
        </div>
        {/* Right panel */}
        {!clientId ? (
          <div className={`nps-card-2 ${narrow ? 'npspage-sx8' : 'npspage-sx9'}`}>
            {t('nps.select_client')}
          </div>
        ) : (
          <div className="nps-stack">
            {/* Client header */}
            <div className="nps-row">
              <div className="nps-box-8">
                <div className="nps-box-9">{selectedClient?.name || clientId}</div>
                <div className="u-text2-sm-mt2">{selectedClient?.contact_email || ''}</div>
              </div>
              {latestHealth !== undefined && (
                <div className="nps-box-10">
                  <div className="nps-box-11 npspage-e1" style={{ '--npspage-color': HEALTH_COLOR(latestHealth) } as CSSProperties}>{Math.round(latestHealth)}</div>
                  <div className="u-text2-2xs">{t('nps.current_health')}</div>
                </div>
              )}
              <button
                onClick={() => computeHealth()}
                disabled={computing}
                className="nps-btn-3">
                {computing ? t('nps.calculating') : t('nps.calc_health')}
              </button>
            </div>
            {/* NPS summary */}
            <div className="nps-card-3">
              <div className="nps-row-2">
                <div className="nps-box-12">{t('nps.nps')}</div>
                <select value={npsDays} onChange={e => setNpsDays(Number(e.target.value))}
                  className="npspage-e2">
                  {[30, 60, 90, 180, 365].map(d => <option key={d} value={d}>{t('nps.last_days').replace('{d}', String(d))}</option>)}
                </select>
              </div>
              <div className={`nps-grid-2 ${narrow ? 'npspage-sx1' : 'npspage-sx10'}`}>
                <div>
                  <NPSGauge nps={summary?.nps} />
                  <div className="nps-stack-2">
                    {([
                      { label: t('nps.promoters'), key: 'promoters', color: 'var(--success)' },
                      { label: t('nps.passives'),  key: 'passives',  color: 'var(--orange)' },
                      { label: t('nps.detractors'),key: 'detractors',color: 'var(--danger)' },
                    ] as Array<{ label: string; key: 'promoters' | 'passives' | 'detractors'; color: string }>)
                      .map(({ label, key, color }) => (
                      <div key={key} className="nps-row-3">
                        <span className="u-text2">{label}</span>
                        <span className="npspage-e1" style={{ '--npspage-color': color } as CSSProperties}>{summary?.[key] ?? 0}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <NpsTrendChart trend={summary?.trend} />
              </div>
            </div>
            {/* Health trend */}
            <div className="nps-card-3">
              <div className="nps-box-13">{t('nps.health_trend')}</div>
              <HealthChart data={health} />
            </div>
            {/* Submit NPS */}
            <div className="nps-card-3">
              <div className="nps-box-14">{t('nps.register_nps')}</div>
              <div className="u-stack-12">
                <div>
                  <label className="npspage-e5">{t('nps.score_label')}</label>
                  <div className="u-wrap-6">
                    {[0,1,2,3,4,5,6,7,8,9,10].map(n => (
                      <button key={n} onClick={() => setScoreInput(n)} className={`nps-btn-4 npspage-sx11 ${scoreInput === n ? 'npspage-sx12' : 'npspage-sx13'} npspage-e3`} style={{ '--npspage-background': scoreInput === n
                          ? (n >= 9 ? 'color-mix(in srgb, var(--success) 25%, var(--surface-2))'
                             : n >= 7 ? 'color-mix(in srgb, var(--orange) 25%, var(--surface-2))'
                             : 'color-mix(in srgb, var(--danger) 25%, var(--surface-2))')
                          : 'var(--surface-4)', '--npspage-border': `1px solid ${scoreInput === n ? (n >= 9 ? 'var(--success)' : n >= 7 ? 'var(--orange)' : 'var(--danger)') : 'var(--surface-5)'}` } as CSSProperties}>{n}</button>
                    ))}
                  </div>
                </div>
                <div className="u-row-10">
                  <div className="u-flex1">
                    <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="npspage-e5">{t('nps.respondent')}</label>
                    <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={respondent} onChange={e => setRespondent(e.target.value)}
                      className="npspage-e6" placeholder={t('nps.respondent')} />
                  </div>
                </div>
                <div>
                  <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="npspage-e5">{t('nps.comment')}</label>
                  <textarea id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={comment} onChange={e => setComment(e.target.value)}
                    className="npspage-e4" rows={2} placeholder={t('nps.comment')} />
                </div>
                <button onClick={submitNPS} disabled={submitting} className="nps-btn-5">
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
