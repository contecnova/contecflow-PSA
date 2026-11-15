/**
 * AlertCorrelationPanel — ML-based alert clustering/correlation for ITSM
 *
 * Backend endpoints:
 *   GET  /sd/alert-clusters                    -> { window_hours, total, clusters: [{cluster_id, size, ticket_ids, ticket_numbers, ci_id, category, priority, correlation_score, suggested_action, root_ci_ids, earliest_at, latest_at}] }
 *   GET  /sd/alert-clusters/stats              -> { window_hours, open_tickets_in_window, clusters_detected, tickets_in_clusters, tickets_needing_problem, top_clusters }
 *   POST /sd/alert-clusters/merge              { ticket_ids, auto_rca } -> { ok, problem_id, problem_number, linked_tickets }
 *   POST /sd/alert-clusters/run-scan           -> stats summary
 */
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { alertClustersApi } from '../../services/api'
import type { ClusterDeAlertas } from '../../services/api/tipos-analitica'
import { Card, Button, Spinner, EmptyState } from '../ui'
import { useToast } from '../../context/ToastContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { localeActivo } from '../../utils/helpers'
import { DELAYED_REFETCH_SHORT_MS, POLL_DEFAULT_MS } from '../../constants/timings'
import './AlertCorrelationPanel.css'

type AlertCluster = ClusterDeAlertas

const PRIORITY_LABELS: Record<string, string> = {
  p1_critical: 'P1 Crítico',
  p2_high: 'P2 Alto',
  p3_medium: 'P3 Medio',
  p4_low: 'P4 Bajo',
}

const ACTION_META: Record<string, { label: string; color: string }> = {
  create_problem: { label: 'Crear problema', color: 'var(--danger)' },
  review:         { label: 'Revisar',          color: 'var(--warning)' },
  monitor:        { label: 'Monitorizar',      color: 'var(--text-3)' },
}

const chip = (color: string): React.CSSProperties => ({
  fontSize: 'var(--text-2xs)',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  color,
  background: `color-mix(in srgb, ${color} 15%, transparent)`,
  border: `1px solid color-mix(in srgb, ${color} 30%, transparent)`,
  borderRadius: 'var(--radius-full, 999px)',
  padding: '2px 9px',
  whiteSpace: 'nowrap',
})

function StatCard({ label, value, accent }: { label: string; value?: number | string | null; accent: string }) {
  return (
    <div className="alcopa-box-6" style={{ background: `color-mix(in srgb, ${accent} 8%, var(--surface-3))`, border: `1px solid color-mix(in srgb, ${accent} 25%, var(--surface-4))`, borderRadius: 'var(--radius-md)' }}>
      <div className="alcopa-txt-5" style={{ color: accent }}>
        {value ?? '—'}
      </div>
      <div className="alcopa-box-1">
        {label}
      </div>
    </div>
  )
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
  const sizeColor = cluster.size >= 10 ? 'var(--danger)' : cluster.size >= 5 ? 'var(--warning)' : 'var(--success)'
  const score = Math.round((cluster.correlation_score ?? 0) * 100)
  const suggestedAction = cluster.suggested_action ?? 'monitor'
  const action = ACTION_META[suggestedAction] || ACTION_META.monitor
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
            <span style={chip(sizeColor)}>{cluster.size} alertas</span>
            <span style={chip(action.color)}>{action.label}</span>
            <span style={chip('var(--accent)')}>score {score}%</span>
          </div>
          <div className="u-text1-base-600">
            {cluster.category ? `${cluster.category}` : 'Cluster sin categoría'}
            {cluster.priority && <span className="alcopa-txt-2"> · {PRIORITY_LABELS[cluster.priority] || cluster.priority}</span>}
          </div>
          <div className="alcopa-row-3">
            {cluster.ci_id && <span>CI: <span className="alcopa-txt-3">{cluster.ci_id}</span></span>}
            {cluster.earliest_at && (
              <span>Desde {new Date(cluster.earliest_at).toLocaleString(localeActivo())}</span>
            )}
            {cluster.latest_at && (
              <span>Hasta {new Date(cluster.latest_at).toLocaleString(localeActivo())}</span>
            )}
          </div>
        </div>
        {cluster.suggested_action !== 'monitor' && ticketIds.length >= 2 && (
          <Button
            onClick={() => onMerge(ticketIds, cluster.cluster_id)}
            loading={merging === cluster.cluster_id}
            variant="secondary"
            size="sm"
            style={{ flexShrink: 0 }}
          >
            🔗 Crear problema
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
            >mostrar menos</button>
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
      toast.success(`Problema ${num} creado desde el cluster`)
      qc.invalidateQueries({ queryKey: ['sd-alert-clusters'] })
      qc.invalidateQueries({ queryKey: ['sd-alert-clusters-stats'] })
      qc.invalidateQueries({ queryKey: ['sd-problems'] })
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      toast.error(detail ? String(detail) : 'Error al crear problema desde cluster')
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
        toast.success('Escaneo en curso: los resultados aparecerán en unos instantes.')
        setTimeout(refrescar, DELAYED_REFETCH_SHORT_MS)
        return
      }
      // run_correlation_scan_job: `clusters_found` y `problems_created`.
      const found = res.data.clusters_found
      const created = res.data.problems_created
      toast.success(`Escáner: ${found} clusters · ${created} problemas auto-creados`)
      refrescar()
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      toast.error(detail ? String(detail) : 'Error al ejecutar el escáner')
    },
  })

  const mergingId = isMerging ? mergeVars?.cluster_id : null

  return (
    <div className="u-stack-16">
      <Card style={{ padding: '20px 22px' }}>
        <div className="alcopa-row-5">
          <div className="u-row-center-8">
            <span className="alcopa-txt-4">
              {t('alertcorrelation.estadisticas_de_correlacion')}
            </span>
            <span className="u-text3-xs">
              {t('alertcorrelation.ventana_ultimas')} {windowHours}h
            </span>
          </div>
          <Button onClick={() => runScan()} loading={scanning} variant="secondary" size="sm">
            🔍 Escanear ahora
          </Button>
        </div>

        {statsLoading ? <Spinner /> : (
          <div className="u-wrap-10">
            <StatCard label="Clusters detectados" value={stats?.clusters_detected} accent="var(--warning)" />
            <StatCard label="Tickets correlados" value={stats?.tickets_in_clusters} accent="var(--accent)" />
            <StatCard label="Necesitan problema" value={stats?.tickets_needing_problem} accent="var(--danger)" />
            <StatCard label="Tickets en ventana" value={stats?.open_tickets_in_window} accent="var(--text-3)" />
          </div>
        )}
      </Card>

      <Card style={{ padding: '20px 22px' }}>
        <div className="alcopa-box-5">
          {t('alertcorrelation.clusters_de_alertas')}
        </div>

        {clustersLoading ? (
          <div className="alcopa-row-6"><Spinner /></div>
        ) : clusters.length === 0 ? (
          <EmptyState
            icon="🔎"
            title={t('alertcorrelation.sin_clusters_detectados')}
            description="No hay grupos de alertas correladas en la ventana actual. Ejecuta el escáner para revisar."
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
