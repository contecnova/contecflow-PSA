/**
 * AlertCorrelationPanel — ML-based alert clustering/correlation for ITSM
 *
 * Shows alert clusters from DBSCAN clustering, lets ops merge a cluster
 * into a Problem record and trigger a new scan.
 *
 * Backend endpoints:
 *   GET  /sd/alert-clusters
 *   GET  /sd/alert-clusters/stats
 *   POST /sd/alert-clusters/merge       { cluster_id }
 *   POST /sd/alert-clusters/run-scan
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { Button, Spinner, EmptyState } from '../ui'
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
  padding: '14px 18px',
  textAlign: 'center',
  flex: 1,
  minWidth: 90,
})

function StatCard({ label, value, accent = COLOR.accent }) {
  return (
    <div style={statBox(accent)}>
      <div style={{ fontSize: "var(--text-2xl)", fontWeight: 700, color: accent }}>{value ?? '—'}</div>
      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 4 }}>{label}</div>
    </div>
  )
}

function ClusterCard({ cluster, onMerge, merging }) {
  const sizeColor = cluster.size >= 10 ? COLOR.danger : cluster.size >= 5 ? COLOR.warning : COLOR.success
  return (
    <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '14px 18px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)' }}>Cluster #{cluster.id}</span>
            <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: sizeColor, background: `${sizeColor}15`, padding: '2px 8px', borderRadius: 4 }}>
              {cluster.size} alertas
            </span>
            {cluster.problem_id && (
              <span style={{ fontSize: "var(--text-xs)", color: COLOR.info ?? 'var(--info)', background: `${COLOR.info ?? 'var(--info)'}15`, padding: '2px 8px', borderRadius: 4 }}>
                → Problema #{cluster.problem_id}
              </span>
            )}
          </div>
          <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', fontWeight: 600 }}>{cluster.label || cluster.title || `Cluster de alertas #${cluster.id}`}</div>
          {cluster.description && (
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 4 }}>{cluster.description}</div>
          )}
        </div>
        {!cluster.problem_id && (
          <Button
            onClick={() => onMerge(cluster.id)}
            loading={merging === cluster.id}
            variant="secondary"
            style={{ flexShrink: 0, marginLeft: 12 }}
          >
            🔗 Crear problema
          </Button>
        )}
      </div>

      {/* Alert list preview */}
      {cluster.alerts?.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
          {cluster.alerts.slice(0, 8).map((a, i) => (
            <span key={i} style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', background: 'var(--surface-4)', padding: '2px 8px', borderRadius: 4 }}>
              {a.title || a.name || `Alerta #${a.id}`}
            </span>
          ))}
          {cluster.alerts.length > 8 && (
            <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>+{cluster.alerts.length - 8} más</span>
          )}
        </div>
      )}
    </div>
  )
}

export default function AlertCorrelationPanel() {
  const toast = useToast()
  const qc = useQueryClient()

  const { data: clusters = [], isLoading: clustersLoading } = useQuery({
    queryKey: ['sd-alert-clusters'],
    queryFn: () => api.get('/sd/alert-clusters').then(r => r.data),
    refetchInterval: 60000,
  })

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['sd-alert-clusters-stats'],
    queryFn: () => api.get('/sd/alert-clusters/stats').then(r => r.data),
    refetchInterval: 60000,
  })

  const { mutate: mergeMutate, variables: mergeVars, isPending: isMerging } = useMutation({
    mutationFn: (clusterId) => api.post('/sd/alert-clusters/merge', { cluster_id: clusterId }),
    onSuccess: (res) => {
      toast.success(`Problema #${res.data?.problem_id ?? '?'} creado desde el cluster`)
      qc.invalidateQueries({ queryKey: ['sd-alert-clusters'] })
      qc.invalidateQueries({ queryKey: ['sd-alert-clusters-stats'] })
      qc.invalidateQueries({ queryKey: ['sd-problems'] })
    },
    onError: () => toast.error('Error al crear problema desde cluster'),
  })

  const { mutate: runScan, isPending: scanning } = useMutation({
    mutationFn: () => api.post('/sd/alert-clusters/run-scan'),
    onSuccess: (res) => {
      toast.success(`Escáner completado: ${res.data?.clusters_found ?? 0} clusters detectados`)
      qc.invalidateQueries({ queryKey: ['sd-alert-clusters'] })
      qc.invalidateQueries({ queryKey: ['sd-alert-clusters-stats'] })
    },
    onError: () => toast.error('Error al ejecutar el escáner'),
  })

  const mergingId = isMerging ? mergeVars : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Stats */}
      <div style={card}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 16 }}>
          📊 Estadísticas de correlación
        </div>
        {statsLoading ? <Spinner /> : (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <StatCard label="Clusters activos" value={stats?.active_clusters} accent={COLOR.warning} />
            <StatCard label="Alertas correladas" value={stats?.total_correlated_alerts} accent={'var(--info)'} />
            <StatCard label="Problemas creados" value={stats?.problems_created} accent={COLOR.success} />
            <StatCard label="Último escaneo" value={stats?.last_scan_ts ? new Date(stats.last_scan_ts).toLocaleTimeString() : 'Nunca'} accent={COLOR.text2 ?? 'var(--text-2)'} />
          </div>
        )}
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Button onClick={() => runScan()} loading={scanning}>
          🔍 Ejecutar escaneo DBSCAN ahora
        </Button>
      </div>

      {/* Cluster list */}
      <div style={card}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 16 }}>
          🧩 Clusters de alertas
        </div>
        {clustersLoading ? <Spinner /> :
         clusters.length === 0 ? (
           <EmptyState icon="🔎" title="Sin clusters detectados" description="Ejecuta un escaneo para detectar grupos de alertas correladas." />
         ) : (
           <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
             {clusters.map(c => (
               <ClusterCard
                 key={c.id}
                 cluster={c}
                 onMerge={mergeMutate}
                 merging={mergingId}
               />
             ))}
           </div>
         )
        }
      </div>
    </div>
  )
}
