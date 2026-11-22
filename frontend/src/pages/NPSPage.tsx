/**
 * NPSPage — Customer NPS & Health trend dashboard
 *
 * ─ Leaderboard sidebar (all clients by health score)
 * ─ Right panel for selected client:
 *     NPS summary + trend line chart
 *     Health history area chart
 *     Submit NPS form
 *
 * 16-11-2026: a todo el ancho (tenía un ancho máximo centrado); título = el
 * del menú con su icono; tarjetas con Card/Section; vacíos con EmptyState e
 * icono lucide (antes texto gris muy pálido, con un token de fondo
 * `--surface-5` como color de texto); botones e Input del kit (antes botones
 * propios y emojis); series de los gráficos en --accent (antes --info);
 * fechas del gráfico con el formateador de la app; "Salud" traducido.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ResponsiveContainer, LineChart, Line, AreaChart, Area,
  XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine,
} from 'recharts'
import { npsApi, clientsApi } from '../services/api'
import type { FotoDeSalud, ResumenNps } from '../services/api/tipos-personas'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Activity, Calculator, LineChart as IconoLinea, MousePointerClick, Send, ThumbsUp, Users } from 'lucide-react'
import { Button, Card, EmptyState, FormField, Input, Pulsable, Section, SelectorDePeriodo, Textarea } from '../components/ui'
import { usePeriodo } from '../hooks/usePeriodo'
import { CON_HORA, codigoDeErrorDePeriodo, formatearTramo, type Granularidad } from '../utils/periodo'
import { useAppT } from '../i18n/AppLangContext'
import useMediaQuery from '../hooks/useMediaQuery'
import type { CSSProperties } from 'react'
import { formateadorDeFecha } from '../utils/helpers'
import { useTono } from '../hooks/useOrgSettings'
import { POLL_DEFAULT_MS } from '../constants/timings'
import './NPSPage.css'
import { ETIQUETA_TEXTO_1, TOOLTIP_SUPERFICIE_2_BORDE_5 } from '../constants/estilosGrafico'

interface ClientItem {
  id: string | number
  name?: string
  /** Email general de la empresa. */
  email?: string | null
  /** Email del contacto principal (persona), reflejado en el cliente. */
  contact_email?: string
}

type NpsTrendPoint = ResumenNps['trend'][number]
type NpsSummary = ResumenNps
type HealthSnapshot = FotoDeSalud


/** 19-11-2026: salud de cliente con HEALTH_THRESHOLD_GOOD/AT_RISK de la empresa (antes 75/50 aquí). */
const COLOR_DE_TONO = { success: 'var(--success)', warning: 'var(--orange)', danger: 'var(--danger)' } as const
const useColorDeSalud = () => {
  const tono = useTono()
  return (score: number) => COLOR_DE_TONO[tono('salud_cliente', score) ?? 'danger']
}

function HealthBadge({ score }: { score: number }) {
  const c = useColorDeSalud()(score)
  return (
    <span className="nps-salud" style={{ '--nps-color': c } as CSSProperties}>{Math.round(score)}</span>
  )
}

function NpsTrendChart({ trend, granularidad, error }: { trend?: NpsTrendPoint[]; granularidad: Granularidad; error?: string | null }) {
  const t = useAppT()
  if (error) return <EmptyState icon={<IconoLinea size={28} />} title={error} />
  // La serie trae todos los tramos del periodo: vacía = ningún tramo con respuestas.
  if (!trend || !trend.some(p => p.count > 0)) {
    return <EmptyState icon={<IconoLinea size={28} />} title={t('nps.no_trend')} />
  }
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={trend} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
        <XAxis dataKey="t" tick={{ fill: 'var(--text-2)', fontSize: 'var(--text-2xs)' }} tickFormatter={v => formatearTramo(String(v), granularidad)} />
        <YAxis domain={[-100, 100]} tick={{ fill: 'var(--text-2)', fontSize: 'var(--text-2xs)' }} />
        <Tooltip contentStyle={TOOLTIP_SUPERFICIE_2_BORDE_5} labelStyle={ETIQUETA_TEXTO_1} labelFormatter={v => formatearTramo(String(v), granularidad, true)} />
        <ReferenceLine y={0} stroke="var(--surface-5)" />
        <ReferenceLine y={50} stroke="var(--success)" strokeDasharray="4 2" opacity={0.5} />
        <Line type="monotone" dataKey="nps" connectNulls stroke="var(--accent)" strokeWidth={2} dot={{ r: 3, fill: 'var(--accent)' }} name="NPS" />
      </LineChart>
    </ResponsiveContainer>
  )
}

function HealthChart({ data }: { data?: HealthSnapshot[] }) {
  const t = useAppT()
  if (!data || data.length === 0) {
    return <EmptyState icon={<Activity size={28} />} title={t('nps.no_health_snapshots')} />
  }
  const fmt = formateadorDeFecha({ day: '2-digit', month: 'short' })
  const chartData = [...data].reverse().map(d => ({
    date: fmt.format(new Date(d.snapshot_at)),
    health: d.health_score,
  }))
  return (
    <ResponsiveContainer width="100%" height={160}>
      <AreaChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
        <defs>
          <linearGradient id="healthGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="var(--accent)" stopOpacity={0.25} />
            <stop offset="95%" stopColor="var(--accent)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
        <XAxis dataKey="date" tick={{ fill: 'var(--text-2)', fontSize: 'var(--text-2xs)' }} />
        <YAxis domain={[0, 100]} tick={{ fill: 'var(--text-2)', fontSize: 'var(--text-2xs)' }} />
        <Tooltip contentStyle={TOOLTIP_SUPERFICIE_2_BORDE_5} labelStyle={ETIQUETA_TEXTO_1} />
        <Area type="monotone" dataKey="health" stroke="var(--accent)" fill="url(#healthGrad)" strokeWidth={2} name={t('nps.salud')} dot={false} />
        <ReferenceLine y={75} stroke="var(--success)" strokeDasharray="4 2" opacity={0.5} />
        <ReferenceLine y={50} stroke="var(--orange)" strokeDasharray="4 2" opacity={0.5} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

function NPSGauge({ nps }: { nps?: number | null }) {
  const t = useAppT()
  const tono = useTono()
  if (nps === null || nps === undefined) return <div className="nps-gauge nps-gauge--vacio">{t('nps.no_data')}</div>
  // 19-11-2026: UMBRAL_NPS_* de la empresa (antes 50/0 aquí).
  const color = COLOR_DE_TONO[tono('nps', nps) ?? 'danger']
  return (
    <div className="nps-gauge">
      <div className="nps-gauge__valor" style={{ '--nps-color': color } as CSSProperties}>{nps > 0 ? `+${nps}` : nps}</div>
      <div className="nps-gauge__etiqueta">NPS</div>
    </div>
  )
}

export default function NPSPage() {
  const t = useAppT()
  const colorDeSalud = useColorDeSalud()
  const narrow = useMediaQuery('(max-width: 900px)')
  const [clientId,    setClientId]    = useState<string | number | null>(null)
  // Periodo libre (16-11-2026): antes 30/60/90/180/365 días propios y tendencia mensual fija.
  const periodo = usePeriodo({ defecto: '90d', granularidades: CON_HORA })
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
    queryFn: () => clientsApi.list().then(r => r.data ?? []),
  })
  const clients = clientsRaw as ClientItem[]

  const { data: summary = null, error: errorResumen } = useQuery<NpsSummary | null>({
    queryKey: ['nps-summary', clientId, periodo.params],
    queryFn: () => npsApi.summary(clientId, { ...periodo.params }).then(r => r.data),
    enabled: !!clientId,
  })
  const errorDePeriodo = codigoDeErrorDePeriodo(errorResumen)

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
      qc.invalidateQueries({ queryKey: ['nps-summary', clientId] })
    } finally {
      setSubmitting(false)
    }
  }

  const selectedClient = clients.find((c) => c.id === clientId)
  const latestHealth = health[0]?.health_score
  const tramo = (n: number) => (n >= 9 ? 'promotor' : n >= 7 ? 'pasivo' : 'detractor')

  return (
    <PageShell>
      <PageHeader
        icon={<ThumbsUp size={18} />}
        title={t('nav.nps')}
        subtitle={t('nps.subtitle')}
        showListExport={false}
      />
      <div className={`nps-layout${narrow ? ' nps-layout--estrecho' : ''}`}>
        {/* Ranking */}
        <Card>
          <Section title={t('nps.ranking')}>
            {leaderboard.length === 0 && clients.length === 0 ? (
              <EmptyState icon={<Users size={28} />} title={t('nps.no_clients')} />
            ) : (
              <ul className="nps-ranking">
                {/* Clientes sin instantáneas de salud */}
                {leaderboard.length === 0 && clients.map(c => (
                  <li key={c.id}>
                    <Pulsable onClick={() => setClientId(c.id)} aria-pressed={clientId === c.id}
                      className={`nps-fila${clientId === c.id ? ' nps-fila--activa' : ''}`}>
                      <span className="nps-fila__nombre">{c.name}</span>
                      <span className="nps-fila__vacio">—</span>
                    </Pulsable>
                  </li>
                ))}
                {leaderboard.map((l, i) => (
                  <li key={l.client_id}>
                    <Pulsable onClick={() => setClientId(l.client_id)} aria-pressed={clientId === l.client_id}
                      className={`nps-fila${clientId === l.client_id ? ' nps-fila--activa' : ''}`}>
                      <span className="nps-fila__pos">{i + 1}</span>
                      <span className="nps-fila__nombre">{l.client_name}</span>
                      <HealthBadge score={l.health_score} />
                    </Pulsable>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </Card>

        {/* Panel del cliente */}
        {!clientId ? (
          <Card>
            <EmptyState icon={<MousePointerClick size={28} />} title={t('nps.select_client')} />
          </Card>
        ) : (
          <div className="u-stack-16 u-min0">
            {/* Cabecera del cliente */}
            <Card>
              <div className="nps-cliente">
                <div className="u-flex1-min0">
                  <div className="nps-cliente__nombre">{selectedClient?.name || clientId}</div>
                  {selectedClient?.email
                    ? <div className="nps-cliente__email" title={t('clicontactos.email_empresa')}>{selectedClient.email}</div>
                    : selectedClient?.contact_email && <div className="nps-cliente__email">{t('clicontactos.email_del_contacto_principal', { email: selectedClient.contact_email })}</div>}
                </div>
                {latestHealth !== undefined && (
                  <div className="nps-cliente__salud">
                    <div className="nps-cliente__salud-valor" style={{ '--nps-color': colorDeSalud(latestHealth) } as CSSProperties}>{Math.round(latestHealth)}</div>
                    <div className="nps-cliente__salud-etiqueta">{t('nps.current_health')}</div>
                  </div>
                )}
                <Button variant="secondary" icon={<Calculator size={14} />} onClick={() => computeHealth()} loading={computing}>
                  {computing ? t('nps.calculating') : t('nps.calc_health')}
                </Button>
              </div>
            </Card>

            {/* Resumen NPS */}
            <Card>
              <Section title={t('nps.nps')}
                actions={<SelectorDePeriodo {...periodo.selector} />}>
                <div className={`nps-resumen${narrow ? ' nps-resumen--estrecho' : ''}`}>
                  <div>
                    <NPSGauge nps={summary?.nps} />
                    <dl className="nps-reparto">
                      {([
                        { label: t('nps.promoters'), key: 'promoters', color: 'var(--success)' },
                        { label: t('nps.passives'),  key: 'passives',  color: 'var(--orange)' },
                        { label: t('nps.detractors'), key: 'detractors', color: 'var(--danger)' },
                      ] as Array<{ label: string; key: 'promoters' | 'passives' | 'detractors'; color: string }>)
                        .map(({ label, key, color }) => (
                          <div key={key} className="nps-reparto__fila">
                            <dt>{label}</dt>
                            <dd style={{ '--nps-color': color } as CSSProperties}>{summary?.[key] ?? 0}</dd>
                          </div>
                        ))}
                    </dl>
                  </div>
                  <NpsTrendChart trend={summary?.trend} granularidad={periodo.granularidad}
                    error={errorDePeriodo ? t(`periodo_err.${errorDePeriodo.motivo}`, errorDePeriodo.params) : null} />
                </div>
              </Section>
            </Card>

            {/* Tendencia de salud */}
            <Card>
              <Section title={t('nps.health_trend')}>
                <HealthChart data={health} />
              </Section>
            </Card>

            {/* Registrar NPS */}
            <Card>
              <Section title={t('nps.register_nps')}>
                <div className="u-stack-12">
                  <div>
                    <div className="nps-etiqueta" id="nps-puntuacion">{t('nps.score_label')}</div>
                    <div className="nps-puntos" role="group" aria-labelledby="nps-puntuacion">
                      {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(n => (
                        <Pulsable key={n} aria-pressed={scoreInput === n} onClick={() => setScoreInput(n)}
                          className={`nps-punto${scoreInput === n ? ` nps-punto--activo nps-punto--${tramo(n)}` : ''}`}>{n}</Pulsable>
                      ))}
                    </div>
                  </div>
                  <Input label={t('nps.respondent')} value={respondent} onChange={e => setRespondent(e.target.value)} placeholder={t('nps.respondent')} />
                  <FormField label={t('nps.comment')}>
                    <Textarea value={comment} onChange={e => setComment(e.target.value)} rows={2} placeholder={t('nps.comment')} inputClassName="nps-textarea" />
                  </FormField>
                  <div>
                    <Button icon={<Send size={14} />} onClick={submitNPS} loading={submitting}>
                      {submitting ? t('nps.sending') : t('nps.submit_nps')}
                    </Button>
                  </div>
                </div>
              </Section>
            </Card>
          </div>
        )}
      </div>
    </PageShell>
  )
}
