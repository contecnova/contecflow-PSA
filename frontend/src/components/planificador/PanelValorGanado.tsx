/**
 * PanelValorGanado — EVM único (rev. 173): PV de la línea base vigente, EV por
 * el avance real de cada tarea, AC del coste real; y la curva S con el
 * histórico diario (worker) y el PV previsto hasta el fin de la línea base.
 */
import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, Camera, Gauge, TrendingUp, Wallet } from 'lucide-react'
import { planificacionApi } from '../../services/api'
import { Button, EmptyState, KpiCard, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { extractErr, fmtDate } from '../../utils/helpers'
import './planificador.css'

const indice = (v: number | null) => (v == null ? '—' : v.toFixed(2))

export default function PanelValorGanado({ projectId }: { projectId: string }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const dinero = useFormatoMoneda()
  const gestiona = useAuth().hasRole('admin', 'pm')

  const { data: curva, isLoading, isError, error } = useQuery({
    queryKey: ['curva-s', projectId],
    queryFn: () => planificacionApi.curvaS(projectId),
    enabled: !!projectId,
    retry: false,
  })
  const punto = useMutation({
    mutationFn: () => planificacionApi.guardarPuntoDeCurva(projectId),
    onSuccess: () => { toast.success(t('planificador.punto_guardado')); qc.invalidateQueries({ queryKey: ['curva-s', projectId] }) },
    onError: e => toast.error(extractErr(e, t('planificador.error_generico'))),
  })

  // Un eje de fechas común: histórico (PV, EV, AC reales) y PV previsto semanal.
  const serie = useMemo(() => {
    if (!curva) return []
    const por = new Map<string, Record<string, number | string | null>>()
    for (const p of curva.planned) por.set(p.date, { date: p.date, plan: p.pv })
    for (const h of curva.history) por.set(h.date, { ...(por.get(h.date) ?? { date: h.date }), pv: h.pv, ev: h.ev, ac: h.ac })
    return [...por.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)))
  }, [curva])

  if (isLoading) return <Spinner />
  if (isError) return <EmptyState title={t('planificador.evm_sin_acceso')} description={extractErr(error, '')} />
  if (!curva) return null
  const d = curva.today

  return (
    <div className="plan-stack">
      {d.pv_source !== 'baseline' && (
        <div className="plan-aviso">{t('planificador.evm_sin_linea_base')}</div>
      )}
      <div className="plan-kpis">
        <KpiCard icon={<Wallet size={16} />} label={t('planificador.bac')} value={dinero(d.bac)} />
        <KpiCard icon={<TrendingUp size={16} />} label={t('planificador.pv')} value={d.pv == null ? '—' : dinero(d.pv)}
          sub={d.pct_planned == null ? undefined : t('planificador.pct_planificado', { n: d.pct_planned })} />
        <KpiCard icon={<Activity size={16} />} label={t('planificador.ev')} value={dinero(d.ev)} sub={t('planificador.pct_avance', { n: d.pct_complete })} />
        <KpiCard icon={<Wallet size={16} />} label={t('planificador.ac')} value={dinero(d.ac)} />
        <KpiCard icon={<Gauge size={16} />} label={t('planificador.cpi')} value={indice(d.cpi)} danger={d.cpi != null && d.cpi < 1} />
        <KpiCard icon={<Gauge size={16} />} label={t('planificador.spi')} value={indice(d.spi)} danger={d.spi != null && d.spi < 1} />
        <KpiCard label={t('planificador.eac')} value={dinero(d.eac)} sub={t('planificador.vac', { v: dinero(d.vac) })} warning={d.vac < 0} />
        <KpiCard label={t('planificador.tcpi')} value={indice(d.tcpi)} />
      </div>
      <div className="plan-card">
        <div className="plan-row plan-row--between">
          <h3 className="plan-card__titulo">{t('planificador.curva_s')}</h3>
          {gestiona && (
            <Button size="xs" variant="subtle" icon={<Camera size={12} />} loading={punto.isPending} onClick={() => punto.mutate()}>
              {t('planificador.guardar_punto')}
            </Button>
          )}
        </div>
        {serie.length === 0 ? (
          <p className="plan-muted">{t('planificador.curva_vacia')}</p>
        ) : (
          <div className="plan-grafica">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={serie}>
                <CartesianGrid stroke="var(--surface-3)" strokeDasharray="3 3" />
                <XAxis dataKey="date" tickFormatter={v => fmtDate(String(v))} stroke="var(--text-3)" fontSize={11} />
                <YAxis stroke="var(--text-3)" fontSize={11} tickFormatter={v => dinero(Number(v), { compacto: true })} />
                <Tooltip formatter={v => dinero(Number(v))} labelFormatter={v => fmtDate(String(v))}
                  contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', color: 'var(--text-1)' }} />
                <Legend />
                <Line dataKey="plan" name={t('planificador.pv_previsto')} stroke="var(--text-3)" strokeDasharray="4 3" dot={false} connectNulls />
                <Line dataKey="pv" name={t('planificador.pv')} stroke="var(--info)" dot={false} connectNulls />
                <Line dataKey="ev" name={t('planificador.ev')} stroke="var(--success)" dot={false} connectNulls />
                <Line dataKey="ac" name={t('planificador.ac')} stroke="var(--danger)" dot={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  )
}
