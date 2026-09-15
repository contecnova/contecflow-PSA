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
import { Card, Button, Spinner, EmptyState } from '../ui'
import { useToast } from '../../context/ToastContext'

// TODO type: alertClustersApi payload — needs shared type
interface AlertCluster {
  cluster_id: string | number
  size: number
  ticket_ids?: Array<string | number>
  ticket_numbers?: string[]
  ci_id?: string
  category?: string
  priority?: string
  correlation_score?: number
  suggested_action?: string
  root_ci_ids?: string[]
  earliest_at?: string
  latest_at?: string
}

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
  const sizeColor = cluster.size >= 10 ? 'var(--danger)' : cluster.size >= 5 ? 'var(--warning)' : 'var(--success)'
  const score = Math.round((cluster.correlation_score ?? 0) * 100)
  const suggestedAction = cluster.suggested_action ?? 'monitor'
  const action = ACTION_META[suggestedAction] || ACTION_META.monitor
  const ticketNums = cluster.ticket_numbers || []
  const ticketIds = cluster.ticket_ids || []

  return (
    <div style={{
      background: 'var(--surface-3)',
      border: '1px solid var(--surface-4)',
      borderRadius: 10,
      padding: '14px 16px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
              #{String(cluster.cluster_id || '').slice(0, 8)}
            </span>
            <span style={chip(sizeColor)}>{cluster.size} alertas</span>
            <span style={chip(action.color)}>{action.label}</span>
            <span style={chip('var(--accent)')}>score {score}%</span>
          </div>
          <div style={{ fontSize: 'var(--text-base)', color: 'var(--text-1)', fontWeight: 600 }}>
            {cluster.category ? `${cluster.category}` : 'Cluster sin categoría'}
            {cluster.priority && <span style={{ color: 'var(--text-3)', fontWeight: 400 }}> · {PRIORITY_LABELS[cluster.priority] || cluster.priority}</span>}
          </div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 12 }}>
            {cluster.ci_id && <span>CI: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>{cluster.ci_id}</span></span>}
            {cluster.earliest_at && (
              <span>Desde {new Date(cluster.earliest_at).toLocaleString()}</span>
            )}
            {cluster.latest_at && (
              <span>Hasta {new Date(cluster.latest_at).toLocaleString()}</span>
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
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 12 }}>
          {(expanded ? ticketNums : ticketNums.slice(0, 8)).map((num, i) => (
            <span key={`${num}-${i}`} style={{
              fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)',
              color: 'var(--text-2)', background: 'var(--surface-4)',
              padding: '2px 8px', borderRadius: 4,
            }}>{num}</span>
          ))}
          {!expanded && ticketNums.length > 8 && (
            <button
              type="button"
              onClick={onToggle}
              style={{
                background: 'transparent', border: 'none', cursor: 'pointer',
                color: 'var(--accent)', fontSize: 'var(--text-xs)', fontFamily: 'inherit',
                padding: '2px 8px',
              }}
            >+{ticketNums.length - 8} más</button>
          )}
          {expanded && ticketNums.length > 8 && (
            <button
              type="button"
              onClick={onToggle}
              style={{
                background: 'transparent', border: 'none', cursor: 'pointer',
                color: 'var(--accent)', fontSize: 'var(--text-xs)', fontFamily: 'inherit',
                padding: '2px 8px',
              }}
            >mostrar menos</button>
          )}
        </div>
      )}
    </div>
  )
}

export default function AlertCorrelationPanel() {
  const toast = useToast()
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  const { data: clustersData, isLoading: clustersLoading } = useQuery<{ clusters?: AlertCluster[] }>({
    queryKey: ['sd-alert-clusters'],
    queryFn: () => alertClustersApi.list().then(r => r.data),
    refetchInterval: 60_000,
  })

  const clusters = clustersData?.clusters ?? []
  const windowHours = clustersData?.window_hours ?? 4

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['sd-alert-clusters-stats'],
    queryFn: () => alertClustersApi.stats().then(r => r.data),
    refetchInterval: 60_000,
  })

  const { mutate: mergeMutate, variables: mergeVars, isPending: isMerging } = useMutation({
    mutationFn: ({ ticket_ids }: { ticket_ids: Array<string | number>; cluster_id: string | number }) => alertClustersApi.merge({ ticket_ids, auto_rca: true }),
    onSuccess: (res) => {
      const num = res.data?.problem_number || res.data?.problem_id || ''
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
      const found = res.data?.clusters_detected ?? res.data?.clusters_found ?? 0
      const created = res.data?.problems_auto_created ?? res.data?.created_problems ?? 0
      toast.success(`Escáner: ${found} clusters · ${created} problemas auto-creados`)
      qc.invalidateQueries({ queryKey: ['sd-alert-clusters'] })
      qc.invalidateQueries({ queryKey: ['sd-alert-clusters-stats'] })
      qc.invalidateQueries({ queryKey: ['sd-problems'] })
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      toast.error(detail ? String(detail) : 'Error al ejecutar el escáner')
    },
  })

  const mergingId = isMerging ? mergeVars?.cluster_id : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card style={{ padding: '20px 22px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, gap: 12, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)' }}>
              📊 Estadísticas de correlación
            </span>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
              ventana últimas {windowHours}h
            </span>
          </div>
          <Button onClick={() => runScan()} loading={scanning} variant="secondary" size="sm">
            🔍 Escanear ahora
          </Button>
        </div>

        {statsLoading ? <Spinner /> : (
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <StatCard label="Clusters detectados" value={stats?.clusters_detected} accent="var(--warning)" />
            <StatCard label="Tickets correlados" value={stats?.tickets_in_clusters} accent="var(--accent)" />
            <StatCard label="Necesitan problema" value={stats?.tickets_needing_problem} accent="var(--danger)" />
            <StatCard label="Tickets en ventana" value={stats?.open_tickets_in_window} accent="var(--text-3)" />
          </div>
        )}
      </Card>

      <Card style={{ padding: '20px 22px' }}>
        <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', marginBottom: 14 }}>
          🧩 Clusters de alertas
        </div>

        {clustersLoading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}><Spinner /></div>
        ) : clusters.length === 0 ? (
          <EmptyState
            icon="🔎"
            title="Sin clusters detectados"
            description="No hay grupos de alertas correladas en la ventana actual. Ejecuta el escáner para revisar."
          />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
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
