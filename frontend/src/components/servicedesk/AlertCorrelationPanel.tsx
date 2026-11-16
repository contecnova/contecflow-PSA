/**
 * AlertCorrelationPanel — agrupación de alertas correladas (ITSM).
 *
 * Backend endpoints:
 *   GET  /sd/alert-clusters                    -> { window_hours, total, clusters: [{cluster_id, size, ticket_ids, ticket_numbers, ci_id, category, priority, correlation_score, suggested_action, root_ci_ids, earliest_at, latest_at}] }
 *   GET  /sd/alert-clusters/stats              -> { window_hours, open_tickets_in_window, clusters_detected, tickets_in_clusters, tickets_needing_problem, top_clusters }
 *   POST /sd/alert-clusters/merge              { ticket_ids, auto_rca } -> { ok, problem_id, problem_number, linked_tickets }
 *   POST /sd/alert-clusters/run-scan           -> stats summary
 *
 * 16-11-2026 (pasada de diseño): KPIs con <KpiCard> en `ds-grid-stats` (antes
 * tarjetas propias centradas y teñidas); chips con <StatusBadge>; «score» y
 * los errores traducidos; fechas con el formateador de la app; iconos lucide
 * en lugar de emojis; «clusters» → «grupos».
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Layers, Link2, Search, Ticket, Timer } from 'lucide-react'
import { alertClustersApi } from '../../services/api'
import type { ClusterDeAlertas } from '../../services/api/tipos-analitica'
import { Card, Button, Spinner, EmptyState, KpiCard, StatusBadge } from '../ui'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { useToast } from '../../context/ToastContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { fmtDateTime } from '../../utils/helpers'
import { DELAYED_REFETCH_SHORT_MS, POLL_DEFAULT_MS } from '../../constants/timings'
import './AlertCorrelationPanel.css'

type AlertCluster = ClusterDeAlertas

const ACTION_KIND: Record<string, StatusBadgeKind> = {
  create_problem: 'danger',
  review: 'warning',
  monitor: 'neutral',
}

interface ClusterCardProps {
  cluster: AlertCluster
  onMerge: (ids: Array<string | number>, clusterId: string | number) => void
  merging: string | number | null
  expanded: boolean
  onToggle: () => void
}

function ClusterCard({ cluster, onMerge, merging, expanded, onToggle }: ClusterCardProps) {
  const { t } = useAppLang()
  const sizeKind: StatusBadgeKind = cluster.size >= 10 ? 'danger' : cluster.size >= 5 ? 'warning' : 'success'
  const score = Math.round((cluster.correlation_score ?? 0) * 100)
  const suggestedAction = cluster.suggested_action ?? 'monitor'
  const ticketNums = cluster.ticket_numbers || []
  const ticketIds = cluster.ticket_ids || []

  return (
    <div className="alcopa-box-2">
      <div className="alcopa-row-1">
        <div className="u-flex1-min0">
          <div className="alcopa-row-2">
            <span className="alcopa-txt-1">
              #{String(cluster.cluster_id || '').slice(0, 8)}
            </span>
            <StatusBadge kind={sizeKind} caps={false}>{cluster.size} {t('alertcorrelation.alertas')}</StatusBadge>
            <StatusBadge kind={ACTION_KIND[suggestedAction] ?? 'neutral'} caps={false}>{etiquetaCodigo(t, 'accion_sugerida', suggestedAction)}</StatusBadge>
            <StatusBadge kind="accent" caps={false}>{t('alertcorrelation.correlacion_pct', { n: score })}</StatusBadge>
          </div>
          <div className="u-text1-base-600">
            {cluster.category ? `${cluster.category}` : t('alertcorrelation.cluster_sin_categoria')}
            {cluster.priority && <span className="alcopa-txt-2"> · {etiquetaCodigo(t, 'estado', cluster.priority)}</span>}
          </div>
          <div className="alcopa-row-3">
            {cluster.ci_id && <span>{t('alertcorrelation.ci')} <span className="alcopa-txt-3">{cluster.ci_id}</span></span>}
            {cluster.earliest_at && (
              <span>{t('alertcorrelation.desde', { fecha: fmtDateTime(cluster.earliest_at) })}</span>
            )}
            {cluster.latest_at && (
              <span>{t('alertcorrelation.hasta', { fecha: fmtDateTime(cluster.latest_at) })}</span>
            )}
          </div>
        </div>
        {cluster.suggested_action !== 'monitor' && ticketIds.length >= 2 && (
          <Button
            onClick={() => onMerge(ticketIds, cluster.cluster_id)}
            loading={merging === cluster.cluster_id}
            variant="secondary"
            size="sm" className="alertcor-sx2"
            icon={<Link2 size={13} />}
          >
            {t('alertcorrelation.crear_problema')}
          </Button>
        )}
      </div>

      {/* Ticket chips */}
      {ticketNums.length > 0 && (
        <div className="alcopa-row-4">
          {(expanded ? ticketNums : ticketNums.slice(0, 8)).map((num, i) => (
            <span key={`${num}-${i}`} className="alcopa-box-3">{num}</span>
          ))}
          {!expanded && ticketNums.length > 8 && (
            <button
              type="button"
              onClick={onToggle}
              className="alcopa-box-4"
            >+{ticketNums.length - 8} {t('alertcorrelation.mas')}</button>
          )}
          {expanded && ticketNums.length > 8 && (
            <button
              type="button"
              onClick={onToggle}
              className="alcopa-box-4"
            >{t('alertcorrelation.mostrar_menos')}</button>
          )}
        </div>
      )}
    </div>
  )
}

export default function AlertCorrelationPanel() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  const { data: clustersData, isLoading: clustersLoading } = useQuery({
    queryKey: ['sd-alert-clusters'],
    queryFn: () => alertClustersApi.list().then(r => r.data),
    refetchInterval: POLL_DEFAULT_MS,
  })

  const clusters = clustersData?.clusters ?? []
  const windowHours = clustersData?.window_hours ?? 4

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['sd-alert-clusters-stats'],
    queryFn: () => alertClustersApi.stats().then(r => r.data),
    refetchInterval: POLL_DEFAULT_MS,
  })

  const { mutate: mergeMutate, variables: mergeVars, isPending: isMerging } = useMutation({
    mutationFn: ({ ticket_ids }: { ticket_ids: Array<string | number>; cluster_id: string | number }) => alertClustersApi.merge({ ticket_ids, auto_rca: true }),
    onSuccess: (res) => {
      const num = res.data.problem_number
      toast.success(t('alertcorrelation.problema_num_creado_desde_el_cluster', { num }))
      qc.invalidateQueries({ queryKey: ['sd-alert-clusters'] })
      qc.invalidateQueries({ queryKey: ['sd-alert-clusters-stats'] })
      qc.invalidateQueries({ queryKey: ['sd-problems'] })
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      toast.error(detail ? String(detail) : t('alertcorrelation.error_crear_problema'))
    },
  })

  const { mutate: runScan, isPending: scanning } = useMutation({
    mutationFn: () => alertClustersApi.runScan(),
    onSuccess: (res) => {
      const refrescar = () => {
        qc.invalidateQueries({ queryKey: ['sd-alert-clusters'] })
        qc.invalidateQueries({ queryKey: ['sd-alert-clusters-stats'] })
        qc.invalidateQueries({ queryKey: ['sd-problems'] })
      }
      // Con cola el escaneo va al worker (202 `{status: 'queued'}`): se avisa y se
      // refresca mas tarde.
      if (!('clusters_found' in res.data)) {
        toast.success(t('alertcorrelation.escaneo_en_curso_los_resultados_apareceran_en'))
        setTimeout(refrescar, DELAYED_REFETCH_SHORT_MS)
        return
      }
      // run_correlation_scan_job: `clusters_found` y `problems_created`.
      const found = res.data.clusters_found
      const created = res.data.problems_created
      toast.success(t('alertcorrelation.escaner_found_clusters_created_problemas_auto_creados', { found, created }))
      refrescar()
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      toast.error(detail ? String(detail) : t('alertcorrelation.error_escaner'))
    },
  })

  const mergingId = isMerging ? mergeVars?.cluster_id : null

  return (
    <div className="u-stack-16">
      <Card className="alertcor-sx3">
        <div className="alcopa-row-5">
          <div className="alcopa-cabecera">
            <span className="alcopa-txt-4">
              {t('alertcorrelation.estadisticas_de_correlacion')}
            </span>
            <span className="u-text2-xs">
              {t('alertcorrelation.ventana_horas', { n: windowHours })}
            </span>
          </div>
          <Button onClick={() => runScan()} loading={scanning} variant="secondary" size="sm" icon={<Search size={13} />}>
            {t('alertcorrelation.escanear_ahora')}
          </Button>
        </div>

        {statsLoading ? <Spinner /> : (
          <div className="ds-grid-stats">
            <KpiCard icon={<Layers size={16} />} label={t('alertcorrelation.clusters_detectados')} value={stats?.clusters_detected ?? '—'} warning={(stats?.clusters_detected ?? 0) > 0} />
            <KpiCard icon={<Ticket size={16} />} label={t('alertcorrelation.tickets_correlados')} value={stats?.tickets_in_clusters ?? '—'} />
            <KpiCard icon={<AlertTriangle size={16} />} label={t('alertcorrelation.necesitan_problema')} value={stats?.tickets_needing_problem ?? '—'} danger={(stats?.tickets_needing_problem ?? 0) > 0} />
            <KpiCard icon={<Timer size={16} />} label={t('alertcorrelation.tickets_en_ventana')} value={stats?.open_tickets_in_window ?? '—'} />
          </div>
        )}
      </Card>

      <Card className="alertcor-sx3">
        <div className="alcopa-box-5">
          {t('alertcorrelation.clusters_de_alertas')}
        </div>

        {clustersLoading ? (
          <div className="alcopa-row-6"><Spinner /></div>
        ) : clusters.length === 0 ? (
          <EmptyState
            icon={<Layers size={28} />}
            title={t('alertcorrelation.sin_clusters_detectados')}
            description={t('alertcorrelation.no_hay_grupos_de_alertas_correladas_en')}
            action={<Button variant="secondary" icon={<Search size={14} />} loading={scanning} onClick={() => runScan()}>{t('alertcorrelation.escanear_ahora')}</Button>}
          />
        ) : (
          <div className="u-stack-10">
            {clusters.map(c => (
              <ClusterCard
                key={c.cluster_id}
                cluster={c}
                onMerge={(ticket_ids, cluster_id) => mergeMutate({ ticket_ids, cluster_id })}
                merging={mergingId}
                expanded={!!expanded[String(c.cluster_id)]}
                onToggle={() => setExpanded(prev => ({ ...prev, [String(c.cluster_id)]: !prev[String(c.cluster_id)] }))}
              />
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
