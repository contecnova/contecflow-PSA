import { useState, useEffect } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner, EmptyState, Modal, useSort, SortableTH, ViewToggle } from '../components/ui'
import { BadgeWithTooltip } from '../components/ui/BadgeWithTooltip'
import { IconFR, IconCR } from '../components/ui/FRCRIcons'
import _PageHeader from '../components/layout/PageHeader'
import { fmtCurrency, extractErr} from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'

// ── Estilo base ───────────────────────────────────────────────────────────────
const panel = { background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12 }
const inp   = { background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }
const lbl   = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }

const STATUS_COLOR = { active: 'var(--success)', prospect: 'var(--accent)', inactive: 'var(--warning)', churned: 'var(--danger)' }
const STATUS_LABEL = { active: 'Activo', prospect: 'Prospecto', inactive: 'Inactivo', churned: 'Perdido' }
const SLA_COLOR    = { enterprise: 'var(--purple)', gold: 'var(--warning)', silver: 'var(--text-2)', bronze: 'var(--warning)' }

const MODULES = [
  { id: 'service_desk', label: 'Service Desk', icon: '🎫' },
  { id: 'projects',     label: 'Proyectos',    icon: '⬡' },
  { id: 'documents',    label: 'Documentos',   icon: '📄' },
  { id: 'invoices',     label: 'Facturas',     icon: '🧾' },
  { id: 'reports',      label: 'Informes',     icon: '📊' },
  { id: 'knowledge_base', label: 'Base de conocimiento', icon: '📚' },
]

function HealthBadge({ score }) {
  const color = score >= 80 ? 'var(--success)' : score >= 50 ? 'var(--warning)' : 'var(--danger)'
  const label = score >= 80 ? 'Saludable' : score >= 50 ? 'Atención' : 'Crítico'
  return (
    <span style={{ background: color + '20', border: `1px solid ${color}50`, borderRadius: 20,
      padding: '2px 10px', fontSize: 11, fontWeight: 700, color }}>
      {label} {score}
    </span>
  )
}

// ── Vista 360 del cliente ─────────────────────────────────────────────────────
function Client360({ cid }) {
  const { data, isLoading } = useQuery({
    queryKey: ['client-360', cid],
    queryFn: () => api.get(`/clients/${cid}/360`).then(r => r.data),
  })
  if (isLoading) return <div style={{ padding: 40, textAlign: 'center' }}><Spinner /></div>
  if (!data) return null
  const k = data.kpis
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>Estado general del cliente</div>
        <HealthBadge score={data.health_score} />
      </div>
      {data.alerts?.length > 0 && (
        <div style={{ background: 'var(--danger-bg)', border: '1px solid #ff475730', borderRadius: 8,
          padding: '10px 14px', marginBottom: 20 }}>
          {data.alerts.map((a, i) => (
            <div key={i} style={{ fontSize: 12, color: 'var(--danger)' }}>⚠️ {a}</div>
          ))}
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 12, marginBottom: 24 }}>
        {[
          { label: 'Proyectos activos', value: k.active_projects, icon: '⬡', color: 'var(--accent)' },
          { label: 'Tickets abiertos',  value: k.open_tickets,    icon: '🎫', color: k.open_tickets > 3 ? 'var(--danger)' : 'var(--success)' },
          { label: 'Tickets (30d)',     value: k.tickets_last_30d, icon: '📈', color: 'var(--purple)' },
          { label: 'Contratos',         value: k.linked_contracts, icon: '📄', color: 'var(--success)' },
          { label: 'Valor contratos',   value: fmtCurrency(k.contract_value_eur), icon: '💰', color: 'var(--warning)', isStr: true },
          { label: 'Licencias',         value: k.linked_licenses,  icon: '🔑', color: 'var(--accent)' },
          { label: 'Lic. por vencer',   value: k.licenses_expiring_soon, icon: '⏰', color: k.licenses_expiring_soon > 0 ? 'var(--danger)' : 'var(--text-3)' },
          { label: 'Usuarios portal',   value: k.portal_users,     icon: '👤', color: 'var(--accent)' },
        ].map(kpi => (
          <div key={kpi.label} style={{ ...panel, padding: '14px 16px' }}>
            <div style={{ fontSize: 20, marginBottom: 6 }}>{kpi.icon}</div>
            <div style={{ fontSize: kpi.isStr ? 14 : 22, fontWeight: 800, color: kpi.color, fontFamily: "'Space Mono', monospace" }}>
              {kpi.value}
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-2)', marginTop: 2 }}>{kpi.label}</div>
          </div>
        ))}
      </div>
      {data.recent_tickets?.length > 0 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Tickets recientes</div>
          {data.recent_tickets.map(t => (
            <div key={t.id} style={{ ...panel, padding: '10px 14px', marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{t.title}</div>
                <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{t.created_at?.slice(0, 10)}</div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 6, background: 'var(--surface-4)', color: 'var(--text-2)' }}>{t.priority}</span>
                <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 6, background: 'var(--accent-muted)', color: 'var(--accent)' }}>{t.status}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Facturas del cliente ──────────────────────────────────────────────────────
function InvoicesClientTab({ cid }) {
  const { data: invoices = [], isLoading } = useQuery({
    queryKey: ['client-invoices', cid],
    queryFn: () => api.get(`/clients/${cid}/invoices`).then(r => r.data),
  })

  const STATUS_COLOR = { draft: 'var(--text-2)', sent: 'var(--accent)', paid: 'var(--success)', overdue: 'var(--danger)', cancelled: 'var(--text-3)' }
  const STATUS_LABEL = { draft: 'Borrador', sent: 'Enviada', paid: 'Pagada', overdue: 'Vencida', cancelled: 'Cancelada' }

  const total = invoices.reduce((s, i) => s + (i.total_amount || 0), 0)
  const paid  = invoices.filter(i => i.status === 'paid').reduce((s, i) => s + (i.total_amount || 0), 0)
  const pending = invoices.filter(i => ['sent','overdue'].includes(i.status)).reduce((s, i) => s + (i.total_amount || 0), 0)

  if (isLoading) return <Spinner />
  return (
    <div>
      {invoices.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 20 }}>
          {[
            { label: 'Total facturado', value: fmtCurrency(total), color: 'var(--accent)' },
            { label: 'Cobrado', value: fmtCurrency(paid), color: 'var(--success)' },
            { label: 'Pendiente', value: fmtCurrency(pending), color: pending > 0 ? 'var(--warning)' : 'var(--text-3)' },
          ].map(k => (
            <div key={k.label} style={{ ...panel, padding: '14px 16px' }}>
              <div style={{ fontSize: 18, fontWeight: 800, color: k.color, fontFamily: "'Space Mono', monospace" }}>{k.value}</div>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>{k.label}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 14 }}>{invoices.length} factura(s)</div>

      {invoices.length === 0
        ? <EmptyState icon="🧾" title="Sin facturas" description="Las facturas creadas en este cliente aparecerán aquí" />
        : invoices.map(inv => (
          <div key={inv.id} style={{ ...panel, padding: '12px 18px', marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 3 }}>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: 12, fontWeight: 700 }}>{inv.number}</span>
                <span style={{ fontSize: 11, padding: '1px 7px', borderRadius: 20,
                  background: (STATUS_COLOR[inv.status] || 'var(--text-2)') + '20',
                  color: STATUS_COLOR[inv.status] || 'var(--text-2)', fontWeight: 700 }}>
                  {STATUS_LABEL[inv.status] || inv.status}
                </span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-2)' }}>
                {inv.issue_date && `Emitida: ${inv.issue_date}`}
                {inv.due_date && ` · Vence: ${inv.due_date}`}
                {inv.project_name && ` · ⬡ ${inv.project_name}`}
              </div>
            </div>
            <div style={{ fontSize: 16, fontWeight: 800, color: 'var(--text-1)', fontFamily: "'Space Mono', monospace" }}>
              {fmtCurrency(inv.total_amount || 0)}
            </div>
          </div>
        ))
      }
    </div>
  )
}


// ── Timeline Gantt del cliente ─────────────────────────────────────────────────
function ClientTimelineTab({ cid, clientName }) {
  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['client-projects-linked', cid],
    queryFn: () => api.get(`/clients/${cid}/projects`).then(r => r.data),
    staleTime: 0,
  })

  const today = new Date()
  const months = []
  const startYear = today.getFullYear()
  const startMonth = today.getMonth() - 2
  for (let i = 0; i < 12; i++) {
    const d = new Date(startYear, startMonth + i, 1)
    months.push({ year: d.getFullYear(), month: d.getMonth(), label: d.toLocaleDateString('es-ES', { month: 'short', year: '2-digit' }) })
  }

  const totalDays = months.length * 30
  const refDate = new Date(startYear, startMonth, 1)

  const getDayOffset = (dateStr) => {
    if (!dateStr) return null
    const d = new Date(dateStr)
    return Math.floor((d - refDate) / (1000 * 60 * 60 * 24))
  }

  const STATUS_COLOR = {
    active: 'var(--success)', planning: 'var(--accent)', on_hold: 'var(--warning)',
    completed: 'var(--purple)', cancelled: 'var(--text-3)', paused: 'var(--warning)',
  }

  if (isLoading) return <Spinner />
  if (projects.length === 0) return (
    <EmptyState icon="📅" title="Sin proyectos" description="Vincula proyectos a este cliente para ver su timeline" />
  )

  return (
    <div>
      <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 16 }}>
        Timeline de {projects.length} proyecto(s) · {clientName}
      </div>

      <div style={{ overflowX: 'auto' }}>
        <div style={{ minWidth: 900 }}>
          {/* Cabecera de meses */}
          <div style={{ display: 'flex', marginLeft: 200, marginBottom: 8 }}>
            {months.map((m, i) => (
              <div key={i} style={{ flex: 1, textAlign: 'center', fontSize: 10, color: 'var(--text-2)',
                fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
                borderLeft: '1px solid #1e2d45', padding: '4px 2px' }}>
                {m.label}
              </div>
            ))}
          </div>

          {/* Línea de hoy */}
          <div style={{ position: 'relative' }}>
            {/* Proyectos */}
            {projects.map((p, _pi) => {
              const startOffset = getDayOffset(p.start_date)
              const endOffset   = getDayOffset(p.end_date || p.end_date_planned)
              const color       = STATUS_COLOR[p.status] || 'var(--text-2)'

              const barLeft  = startOffset !== null ? Math.max(0, (startOffset / totalDays) * 100) : null
              const barWidth = (startOffset !== null && endOffset !== null)
                ? Math.max(2, ((endOffset - startOffset) / totalDays) * 100)
                : 5

              return (
                <div key={p.id} style={{ display: 'flex', alignItems: 'center', marginBottom: 8, height: 36 }}>
                  {/* Nombre proyecto */}
                  <div style={{ width: 200, flexShrink: 0, padding: '0 12px 0 0' }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.code && <span style={{ fontFamily: "'Space Mono', monospace", fontSize: 10, color: 'var(--text-2)', marginRight: 6 }}>{p.code}</span>}
                      {p.name}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-2)', marginTop: 2 }}>
                      <span style={{ background: color + '20', color, padding: '1px 5px', borderRadius: 3, fontSize: 9, fontWeight: 700 }}>{p.status}</span>
                    </div>
                  </div>

                  {/* Barra del Gantt */}
                  <div style={{ flex: 1, height: '100%', background: 'var(--surface-1)', borderRadius: 4,
                    position: 'relative', overflow: 'hidden', border: '1px solid #1e2d45' }}>

                    {/* Separadores de mes */}
                    {months.map((_, i) => (
                      <div key={i} style={{ position: 'absolute', left: `${(i / (months.length || 1)) * 100}%`,
                        top: 0, bottom: 0, width: 1, background: 'var(--surface-4)' }} />
                    ))}

                    {/* Barra del proyecto */}
                    {barLeft !== null && (
                      <div title={`${p.name}: ${p.start_date || '?'} → ${p.end_date || p.end_date_planned || '?'}`}
                        style={{
                          position: 'absolute',
                          left: `${Math.min(barLeft, 98)}%`,
                          width: `${Math.min(barWidth, 100 - barLeft)}%`,
                          top: '20%', height: '60%',
                          background: `linear-gradient(90deg, ${color}, ${color}aa)`,
                          borderRadius: 4,
                          display: 'flex', alignItems: 'center', paddingLeft: 6,
                          overflow: 'hidden',
                        }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--surface-0)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {p.name}
                        </span>
                      </div>
                    )}

                    {/* Línea de hoy */}
                    {(() => {
                      const todayOffset = getDayOffset(today.toISOString().slice(0, 10))
                      const todayPct = (todayOffset / totalDays) * 100
                      if (todayPct >= 0 && todayPct <= 100) {
                        return <div style={{ position: 'absolute', left: `${todayPct}%`, top: 0, bottom: 0,
                          width: 2, background: 'var(--danger)', opacity: 0.7 }} />
                      }
                    })()}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Leyenda */}
          <div style={{ display: 'flex', gap: 16, marginTop: 16, flexWrap: 'wrap' }}>
            {Object.entries(STATUS_COLOR).map(([k, v]) => (
              <span key={k} style={{ fontSize: 11, color: 'var(--text-2)', display: 'flex', gap: 5, alignItems: 'center' }}>
                <span style={{ width: 10, height: 10, background: v, borderRadius: 2, display: 'inline-block' }} />
                {k}
              </span>
            ))}
            <span style={{ fontSize: 11, color: 'var(--text-2)', display: 'flex', gap: 5, alignItems: 'center' }}>
              <span style={{ width: 2, height: 10, background: 'var(--danger)', display: 'inline-block' }} />
              Hoy
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}


// ── Proyectos vinculados ───────────────────────────────────────────────────────
function ProjectsTab({ cid }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { _invalidate } = useInvalidate()
  const [showLink, setShowLink] = useState(false)

  // Proyectos vinculados: endpoint dedicado, siempre fresco
  const { data: linked = [], isLoading: loadingLinked } = useQuery({
    queryKey: ['client-projects-linked', cid],
    queryFn: () => api.get(`/clients/${cid}/projects`).then(r => r.data),
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchOnMount: 'always',
  })

  // Proyectos disponibles para vincular (sin cliente o ya de este cliente)
  const { data: available = [], isLoading: loadingAvail, refetch: refetchAvailable } = useQuery({
    queryKey: ['client-projects-available', cid],
    queryFn: () => api.get(`/clients/${cid}/projects/available`).then(r => r.data),
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchOnMount: 'always',
  })

  const { mutate: link } = useMutation({
    mutationFn: pid => api.post(`/clients/${cid}/projects/${pid}/link`).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['client-projects-linked', cid]); qc.invalidateQueries(['client-projects-available', cid]); qc.invalidateQueries(['client-detail']); qc.invalidateQueries(['clients']); },
    onError: e => toast.error(extractErr(e, 'Error al vincular')),
  })

  const { mutate: unlink } = useMutation({
    mutationFn: pid => api.delete(`/clients/${cid}/projects/${pid}/link`).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['client-projects-linked', cid]); qc.invalidateQueries(['client-projects-available', cid]); qc.invalidateQueries(['client-detail']); qc.invalidateQueries(['clients']); },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const STATUS_COLOR = { active: 'var(--success)', planning: 'var(--accent)', on_hold: 'var(--warning)', completed: 'var(--text-2)', cancelled: 'var(--danger)' }
  const STATUS_LABEL = { active: 'Activo', planning: 'Planificación', on_hold: 'En espera', completed: 'Completado', cancelled: 'Cancelado' }

  const unlinked = available.filter(p => !p.is_linked)

  return (
    <div>
      <div style={{ background: 'var(--accent-muted)', border: '1px solid #00d4ff20', borderRadius: 10, padding: '10px 16px', marginBottom: 16, fontSize: 12, color: 'var(--text-2)' }}>
        ℹ️ Un proyecto solo puede estar vinculado a un cliente. Al vincular aquí, el proyecto queda asociado exclusivamente a este cliente.
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{linked.length} proyecto(s) vinculado(s)</div>
        <Button onClick={() => { setShowLink(s => !s); refetchAvailable() }} size="sm">
          {showLink ? '✕ Cerrar' : '+ Vincular proyecto'}
        </Button>
      </div>

      {/* Panel de vinculación */}
      {showLink && (
        <div style={{ ...panel, padding: '16px 18px', marginBottom: 20, border: '1px solid #00d4ff30' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12, color: 'var(--accent)' }}>Proyectos disponibles para vincular</div>
          {loadingAvail ? <Spinner /> : unlinked.length === 0 ? (
            <div style={{ fontSize: 12, color: 'var(--text-2)', padding: '10px 0' }}>No hay proyectos disponibles sin cliente asignado.</div>
          ) : (
            unlinked.map(p => (
              <div key={p.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '10px 14px', marginBottom: 6, background: 'var(--surface-1)', borderRadius: 8, border: '1px solid #1e2d45' }}>
                <div>
                  <span style={{ fontFamily: "'Space Mono', monospace", fontSize: 11, color: 'var(--text-2)', marginRight: 8 }}>{p.code}</span>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</span>
                  <span style={{ marginLeft: 10, fontSize: 11, padding: '1px 6px', borderRadius: 4,
                    background: (STATUS_COLOR[p.status] || 'var(--text-2)') + '20', color: STATUS_COLOR[p.status] || 'var(--text-2)' }}>
                    {STATUS_LABEL[p.status] || p.status}
                  </span>
                </div>
                <button onClick={() => link(p.id)}
                  style={{ fontSize: 12, padding: '5px 14px', borderRadius: 8, border: '1px solid #00d4ff40', background: 'var(--accent-muted)', color: 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600 }}>
                  + Vincular
                </button>
              </div>
            ))
          )}
        </div>
      )}

      {/* Lista de proyectos vinculados */}
      {loadingLinked ? <Spinner /> : linked.length === 0 ? (
        <EmptyState icon="⬡" title="Sin proyectos vinculados" description="Vincula proyectos existentes o créalos desde la sección Proyectos" />
      ) : (
        linked.map(p => (
          <div key={p.id} style={{ ...panel, padding: '14px 18px', marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                  <span style={{ fontFamily: "'Space Mono', monospace", fontSize: 11, color: 'var(--text-2)' }}>{p.code}</span>
                  <span style={{ fontSize: 14, fontWeight: 700 }}>{p.name}</span>
                  <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 20,
                    background: (STATUS_COLOR[p.status] || 'var(--text-2)') + '20', color: STATUS_COLOR[p.status] || 'var(--text-2)', fontWeight: 700 }}>
                    {STATUS_LABEL[p.status] || p.status}
                  </span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
                  {p.start_date && `${p.start_date} → ${p.end_date || 'en curso'}`}
                </div>
              </div>
              <button onClick={() => { openConfirmGlobal({ message: `¿Desvincular "${p.name}" de este cliente?`, onConfirm: () => unlink(p.id), danger: true }) }}
                style={{ fontSize: 11, padding: '4px 10px', borderRadius: 6, border: '1px solid #ff475730', background: 'transparent', color: 'var(--danger)', cursor: 'pointer', fontFamily: 'inherit' }}>
                Desvincular
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  )
}


// ── Gestión de contactos ──────────────────────────────────────────────────────
function ContactsTab({ cid }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ full_name: '', email: '', phone: '', job_title: '', role: 'other', is_primary: false })

  const { data: contacts = [], isLoading } = useQuery({
    queryKey: ['client-contacts', cid],
    queryFn: () => api.get(`/clients/${cid}/contacts`).then(r => r.data),
  })
  const { mutate: add } = useMutation({
    mutationFn: d => api.post(`/clients/${cid}/contacts`, d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['client-contacts', cid]); setShowAdd(false); setForm({ full_name: '', email: '', phone: '', job_title: '', role: 'other', is_primary: false }) },

    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: remove } = useMutation({
    mutationFn: id => api.delete(`/clients/${cid}/contacts/${id}`),
    onSuccess: () => qc.invalidateQueries(['client-contacts', cid]),
    onError: e => toast.error(extractErr(e, 'Error'))
  })

  const ROLES = [
    { id: 'primary', label: 'Principal' }, { id: 'billing', label: 'Facturación' },
    { id: 'technical', label: 'Técnico' }, { id: 'executive', label: 'Ejecutivo' },
    { id: 'support', label: 'Soporte' }, { id: 'other', label: 'Otro' },
  ]
  const ROLE_COLOR = { primary: 'var(--accent)', billing: 'var(--warning)', technical: 'var(--purple)', executive: 'var(--success)', support: 'var(--warning)', other: 'var(--text-2)' }

  if (isLoading) return <Spinner />
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{contacts.length} contacto(s)</div>
        <Button onClick={() => setShowAdd(true)} size="sm">+ Añadir contacto</Button>
      </div>
      {contacts.length === 0
        ? <EmptyState icon="👤" title="Sin contactos" description="Añade los contactos de esta empresa" />
        : contacts.map(ct => (
          <div key={ct.id} style={{ ...panel, padding: '14px 18px', marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: (ROLE_COLOR[ct.role] || 'var(--text-2)') + '20',
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, fontWeight: 800,
                color: ROLE_COLOR[ct.role] || 'var(--text-2)' }}>
                {ct.full_name?.charAt(0) || '?'}
              </div>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{ct.full_name}
                  {ct.is_primary && <span style={{ marginLeft: 6, fontSize: 10, background: 'var(--accent-glow)', color: 'var(--accent)', padding: '1px 6px', borderRadius: 4 }}>Principal</span>}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{ct.job_title} {ct.email && `· ${ct.email}`}</div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 20, background: (ROLE_COLOR[ct.role]||'var(--text-2)') + '15',
                color: ROLE_COLOR[ct.role] || 'var(--text-2)', fontWeight: 700 }}>
                {ROLES.find(r => r.id === ct.role)?.label || ct.role}
              </span>
              {ct.phone && <span style={{ fontSize: 12, color: 'var(--text-2)' }}>📞 {ct.phone}</span>}
              <button onClick={() => remove(ct.id)} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: 14 }}>🗑</button>
            </div>
          </div>
        ))
      }
      {showAdd && (
        <Modal open title="Añadir contacto" onClose={() => setShowAdd(false)} width={500}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
            <div><label style={lbl}>Nombre completo *</label><input value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Email</label><input type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Teléfono</label><input value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Cargo</label><input value={form.job_title} onChange={e => setForm(f => ({ ...f, job_title: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Rol</label>
              <select value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))} style={inp}>
                {ROLES.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
              </select>
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-end' }}>
              <label style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={form.is_primary} onChange={e => setForm(f => ({ ...f, is_primary: e.target.checked }))} />
                Contacto principal
              </label>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowAdd(false)} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => add(form)} disabled={!form.full_name}>Añadir</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Gestión de licencias vinculadas ───────────────────────────────────────────
function LicensesTab({ cid }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [showLink, setShowLink] = useState(false)
  const [selectedLic, setSelectedLic] = useState('')
  const [licNote, setLicNote] = useState('')

  const { data: linked = [] } = useQuery({ queryKey: ['client-licenses', cid], queryFn: () => api.get(`/clients/${cid}/licenses`).then(r => r.data) })
  const { data: allLics = [] } = useQuery({ queryKey: ['alm-licenses'], queryFn: () => api.get('/alm/licenses').then(r => r.data) })

  const { mutate: link } = useMutation({
    mutationFn: d => api.post(`/clients/${cid}/licenses`, d),
    onSuccess: () => { qc.invalidateQueries(['client-licenses', cid]); qc.invalidateQueries(['alm-licenses']); setShowLink(false); setSelectedLic(''); setLicNote('') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: unlink } = useMutation({
    mutationFn: id => api.delete(`/clients/${cid}/licenses/${id}`),
    onSuccess: () => { qc.invalidateQueries(['client-licenses', cid]); qc.invalidateQueries(['alm-licenses']) },

    onError: e => toast.error(extractErr(e, 'Error'))
  })

  const linkedIds = linked.map(l => l.license_id)
  const available = allLics.filter(l => !linkedIds.includes(l.id))
  const STATUS_COL = { active: 'var(--success)', expired: 'var(--danger)', cancelled: 'var(--text-2)' }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{linked.length} licencia(s) vinculada(s)</div>
        <Button onClick={() => setShowLink(true)} size="sm">+ Vincular licencia</Button>
      </div>
      {linked.length === 0
        ? <EmptyState icon="🔑" title="Sin licencias vinculadas" description="Vincula licencias de software/servicios a este cliente" />
        : linked.map(l => (
          <div key={l.link_id} style={{ ...panel, padding: '14px 18px', marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700 }}>{l.name}</div>
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                {l.total_seats && `${l.total_seats} seats`}
                {l.expiry_date && ` · Vence ${l.expiry_date}`}
                {l.annual_cost && ` · ${fmtCurrency(l.annual_cost)}/año`}
              </div>
              {l.notes && <div style={{ fontSize: 11, color: 'var(--text-2)', fontStyle: 'italic', marginTop: 2 }}>{l.notes}</div>}
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 20,
                background: (STATUS_COL[l.status] || 'var(--text-2)') + '15',
                color: STATUS_COL[l.status] || 'var(--text-2)', fontWeight: 700 }}>{l.status}</span>
              <button onClick={() => unlink(l.link_id)} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer' }}>🗑</button>
            </div>
          </div>
        ))
      }
      {showLink && (
        <Modal open title="Vincular licencia" onClose={() => setShowLink(false)} width={440}>
          <div style={{ marginBottom: 14 }}>
            <label style={lbl}>Licencia</label>
            <select value={selectedLic} onChange={e => setSelectedLic(e.target.value)} style={inp}>
              <option value="">Seleccionar...</option>
              {available.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={lbl}>Notas (opcional)</label>
            <input value={licNote} onChange={e => setLicNote(e.target.value)} style={inp} placeholder="Ej: Licencia dedicada para soporte" />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowLink(false)} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => link({ license_id: selectedLic, notes: licNote })} disabled={!selectedLic}>Vincular</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Gestión de contratos vinculados ───────────────────────────────────────────
function ContractsTab({ cid }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [showLink, setShowLink] = useState(false)
  const [selectedCon, setSelectedCon] = useState('')

  const { data: linked = [] } = useQuery({ queryKey: ['client-contracts', cid], queryFn: () => api.get(`/clients/${cid}/contracts`).then(r => r.data) })
  const { data: allCons = [] } = useQuery({ queryKey: ['contracts'], queryFn: () => api.get('/contracts').then(r => r.data) })

  const { mutate: link } = useMutation({
    mutationFn: d => api.post(`/clients/${cid}/contracts`, d),
    onSuccess: () => { qc.invalidateQueries(['client-contracts', cid]); qc.invalidateQueries(['contracts']); qc.invalidateQueries(['alm-contracts']); setShowLink(false); setSelectedCon('') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: unlink } = useMutation({
    mutationFn: id => api.delete(`/clients/${cid}/contracts/${id}`),
    onSuccess: () => { qc.invalidateQueries(['client-contracts', cid]); qc.invalidateQueries(['contracts']); qc.invalidateQueries(['alm-contracts']) },

    onError: e => toast.error(extractErr(e, 'Error'))
  })

  const linkedIds = linked.map(l => l.contract_id)
  const available = allCons.filter(c => !linkedIds.includes(c.id))
  const STATUS_COL = { active: 'var(--success)', draft: 'var(--text-2)', completed: 'var(--accent)', cancelled: 'var(--danger)' }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{linked.length} contrato(s) vinculado(s)</div>
        <Button onClick={() => setShowLink(true)} size="sm">+ Vincular contrato</Button>
      </div>
      {linked.length === 0
        ? <EmptyState icon="📄" title="Sin contratos vinculados" description="Vincula contratos a este cliente" />
        : linked.map(c => (
          <div key={c.link_id} style={{ ...panel, padding: '14px 18px', marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700 }}>{c.title}</div>
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                {c.reference && `Ref: ${c.reference} · `}
                {c.total_amount && `${fmtCurrency(c.total_amount)} · `}
                {c.start_date && `${c.start_date} → ${c.end_date || '...'}`}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 20,
                background: (STATUS_COL[c.status] || 'var(--text-2)') + '15',
                color: STATUS_COL[c.status] || 'var(--text-2)', fontWeight: 700 }}>{c.status}</span>
              <button onClick={() => unlink(c.link_id)} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer' }}>🗑</button>
            </div>
          </div>
        ))
      }
      {showLink && (
        <Modal open title="Vincular contrato" onClose={() => setShowLink(false)} width={440}>
          <div style={{ marginBottom: 16 }}>
            <label style={lbl}>Contrato</label>
            <select value={selectedCon} onChange={e => setSelectedCon(e.target.value)} style={inp}>
              <option value="">Seleccionar...</option>
              {available.map(c => <option key={c.id} value={c.id}>{c.title || c.client_name} — {c.status}</option>)}
            </select>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowLink(false)} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => link({ contract_id: selectedCon })} disabled={!selectedCon}>Vincular</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Portal unificado ─────────────────────────────────────────────────────────
// Sub-tabs: Accesos | UAT/Proyectos | Solicitudes | Mensajes | Documentos | Config
function PortalConfigTab({ cid, clientDetail }) {
  const [sub, setSub] = useState('accesos')

  const SUB_TABS = [
    { id: 'accesos',      label: '🔐 Accesos' },
    { id: 'uat',          label: '🧪 UAT' },
    { id: 'solicitudes',  label: '💡 Solicitudes' },
    { id: 'mensajes',     label: '💬 Mensajes' },
    { id: 'documentos',   label: '📄 Documentos' },
    { id: 'config',       label: '⚙️ Configuración' },
  ]

  return (
    <div>
      {/* Sub-navegación del portal */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid #1a2640', paddingBottom: 10 }}>
        {SUB_TABS.map(t => (
          <button key={t.id} onClick={() => setSub(t.id)}
            style={{ padding: '5px 14px', borderRadius: 8, border: `1px solid ${sub === t.id ? 'var(--accent-glow)' : 'transparent'}`,
              background: sub === t.id ? 'var(--accent-muted)' : 'transparent',
              color: sub === t.id ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 12, fontWeight: sub === t.id ? 700 : 400, cursor: 'pointer', fontFamily: 'inherit' }}>
            {t.label}
          </button>
        ))}
      </div>

      {sub === 'accesos'     && <PortalUsersTab cid={cid} clientName={clientDetail?.name} />}
      {sub === 'uat'         && <PortalUATTab cid={cid} projects={clientDetail?.projects || []} />}
      {sub === 'solicitudes' && <PortalSolicitudesTab cid={cid} projects={clientDetail?.projects || []} />}
      {sub === 'mensajes'    && <PortalMensajesTab cid={cid} projects={clientDetail?.projects || []} />}
      {sub === 'documentos'  && <PortalDocumentosTab cid={cid} projects={clientDetail?.projects || []} />}
      {sub === 'config'      && <PortalSettingsTab cid={cid} />}
    </div>
  )
}


// ── Portal: UAT por proyecto del cliente ─────────────────────────────────────
function PortalUATTab({ _cid, projects }) {
  const [selectedProject, setSelectedProject] = useState(projects[0]?.id || '')

  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ['uat-team-client', selectedProject],
    queryFn: () => api.get('/portal/uat/team', { params: { project_id: selectedProject } }).then(r => r.data).catch(() => []),
    enabled: !!selectedProject,
  })

  const STATUS_COLOR = {
    pending: 'var(--text-2)', in_progress: 'var(--accent)', passed: 'var(--success)',
    failed: 'var(--danger)', conditional: 'var(--warning)',
  }
  const STATUS_LABEL = {
    pending: 'Pendiente', in_progress: 'En progreso', passed: 'Aprobado',
    failed: 'Rechazado', conditional: 'Con reservas',
  }

  return (
    <div>
      {projects.length === 0 ? (
        <EmptyState icon="🧪" title="Sin proyectos" description="Vincula proyectos a este cliente para gestionar UATs" />
      ) : (
        <>
          {projects.length > 1 && (
            <div style={{ marginBottom: 16 }}>
              <label style={lbl}>Proyecto</label>
              <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)} style={inp}>
                {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </select>
            </div>
          )}

          {!selectedProject ? (
            <EmptyState icon="🧪" title="Selecciona un proyecto" />
          ) : isLoading ? <Spinner /> : sessions.length === 0 ? (
            <EmptyState icon="🧪" title="Sin sesiones UAT" description="No hay sesiones UAT para este proyecto. Créalas desde la gestión del proyecto." />
          ) : (
            sessions.map(s => (
              <div key={s.id} style={{ ...panel, padding: '14px 18px', marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                  <div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 3 }}>
                      <span style={{ fontFamily: "'Space Mono', monospace", fontSize: 11, color: 'var(--text-2)' }}>{s.code}</span>
                      <span style={{ fontSize: 14, fontWeight: 700 }}>{s.title}</span>
                    </div>
                    {s.description && <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{s.description.slice(0, 120)}</div>}
                    <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
                      {s.available_from && `Disponible: ${s.available_from}`}
                      {s.deadline && ` · Límite: ${s.deadline}`}
                    </div>
                  </div>
                  <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 20, flexShrink: 0,
                    background: (STATUS_COLOR[s.status] || 'var(--text-2)') + '20',
                    color: STATUS_COLOR[s.status] || 'var(--text-2)', fontWeight: 700 }}>
                    {STATUS_LABEL[s.status] || s.status}
                  </span>
                </div>
                {s.test_environment && (
                  <div style={{ marginTop: 8, fontSize: 11 }}>
                    <a href={s.test_environment} target="_blank" rel="noopener noreferrer"
                      style={{ color: 'var(--accent)', textDecoration: 'none' }}>
                      🔗 Entorno de pruebas
                    </a>
                  </div>
                )}
                {s.issues_count > 0 && (
                  <div style={{ marginTop: 6, fontSize: 11, color: 'var(--danger)' }}>
                    ⚠️ {s.issues_count} incidencia(s) reportada(s)
                  </div>
                )}
              </div>
            ))
          )}
        </>
      )}
    </div>
  )
}


// ── Portal: Solicitudes (feature requests) del cliente ───────────────────────
function PortalSolicitudesTab({ cid }) {
  const toast = useToast()
  const qc = useQueryClient()
    // --- WebSocket para notificaciones CR ---
    useEffect(() => {
      let ws;
      let reconnectTimer;
      function connectWS() {
        api.get('/ws/ticket').then(res => {
          const ticket = res.data.ticket
          ws = new window.WebSocket(`ws://${window.location.host}/api/v1/ws/notifications?ticket=${ticket}`)
          ws.onopen = () => { /* conectado */ }
          ws.onclose = () => { reconnectTimer = setTimeout(connectWS, 5000) }
          ws.onerror = () => { ws.close() }
          ws.onmessage = (ev) => {
            try {
              const msg = JSON.parse(ev.data)
              if (msg.type === 'cr_state_changed' && msg.feature_request_id) {
                toast.info(`El estado de la Change Request vinculada a "${msg.title}" ha cambiado a: ${msg.cr_status}`)
                qc.invalidateQueries(['portal-frs-client', cid])
              }
            } catch (_e) { /* ignore parse errors */ } // eslint-disable-line no-unused-vars
          }
        })
      }
      connectWS()
      return () => { ws && ws.close(); clearTimeout(reconnectTimer) }
      // eslint-disable-next-line
    }, [cid])
  const [responding, setResponding] = useState(null)
  const [responseForm, setResponseForm] = useState({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' })
  const [crDetail, setCrDetail] = useState(null)
  const [crFilter, setCrFilter] = useState('all')

  const { data: frs = [], isLoading } = useQuery({
    queryKey: ['portal-frs-client', cid],
    queryFn: () => api.get('/portal/feature-requests/team', { params: { client_org_id: cid } }).then(r => r.data).catch(() => []),
    enabled: !!cid,
  })

  const { mutate: respond, isPending } = useMutation({
    mutationFn: ({ id, data }) => api.post(`/portal/feature-requests/${id}/respond`, data),
    onSuccess: () => { qc.invalidateQueries(['portal-frs-client', cid]); setResponding(null) },
    onError: e => toast.error(extractErr(e, 'Error al responder')),
  })

  const { mutate: updateStatus } = useMutation({
    mutationFn: ({ id, status }) => api.post(`/portal/feature-requests/${id}/respond`, { status }),
    onSuccess: () => qc.invalidateQueries(['portal-frs-client', cid]),
    onError: e => toast.error(extractErr(e, 'Error al actualizar estado')),
  })

  const STATUS_COLOR = { new: 'var(--text-2)', reviewing: 'var(--accent)', estimated: 'var(--warning)', approved: 'var(--success)', rejected: 'var(--danger)', in_development: 'var(--purple)', done: 'var(--success)' }
  const STATUS_LABEL = { new: 'Nueva', reviewing: 'En revisión', estimated: 'Presupuestada', approved: 'Aprobada', rejected: 'Rechazada', in_development: 'En desarrollo', done: 'Completada' }
  const PRIO_COLOR   = { low: 'var(--text-2)', medium: 'var(--warning)', high: 'var(--warning)', critical: 'var(--danger)' }
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

  if (isLoading) return <Spinner />
  // Filtro por estado CR
  const crStates = [
    { value: 'all', label: 'Todas' },
    { value: 'none', label: 'Sin CR' },
    { value: 'submitted', label: 'CR Enviada' },
    { value: 'under_review', label: 'CR En revisión' },
    { value: 'approved', label: 'CR Aprobada' },
    { value: 'rejected', label: 'CR Rechazada' },
    { value: 'implemented', label: 'CR Implementada' },
  ]
  const filteredFrs = frs.filter(fr => {
    if (crFilter === 'all') return true
    if (crFilter === 'none') return !fr.cr_status
    return fr.cr_status === crFilter
  })
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        <span style={{ fontSize: 13, color: 'var(--text-2)' }}>{filteredFrs.length} solicitud(es) del cliente</span>
        <select value={crFilter} onChange={e => setCrFilter(e.target.value)} style={{ ...inp, width: 160, fontSize: 12, padding: '4px 8px' }}>
          {crStates.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
        </select>
      </div>
      {filteredFrs.length === 0
        ? <EmptyState icon="💡" title="Sin solicitudes" description="No hay solicitudes que coincidan con el filtro" />
        : filteredFrs.map(fr => (
          <div key={fr.id} style={{
            ...panel,
            padding: '14px 18px',
            marginBottom: 10,
            borderLeft: fr.cr_status_color ? `6px solid ${fr.cr_status_color}` : '6px solid #7a8aaa',
            boxShadow: fr.cr_status ? '0 2px 8px #0001' : undefined,
            position: 'relative',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 3 }}>
                  <IconFR />
                  <span style={{ fontSize: 11, color: 'var(--text-2)', fontFamily: "'Space Mono', monospace" }}>{fr.code}</span>
                  <span style={{ fontSize: 14, fontWeight: 700 }}>{fr.title}</span>
                </div>
                {fr.project_name && <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 3 }}>📁 {fr.project_name}</div>}
              </div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 20, background: (PRIO_COLOR[fr.priority] || 'var(--text-2)') + '20', color: PRIO_COLOR[fr.priority] || 'var(--text-2)', fontWeight: 700 }}>{fr.priority}</span>
                <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 20, background: (STATUS_COLOR[fr.status] || 'var(--text-2)') + '20', color: STATUS_COLOR[fr.status] || 'var(--text-2)', fontWeight: 700 }}>{STATUS_LABEL[fr.status] || fr.status}</span>
                {fr.cr_status ? (
                  <BadgeWithTooltip
                    label={`CR: ${fr.cr_status_label || fr.cr_status}`}
                    color={fr.cr_status_color || '#7a8aaa'}
                    tooltip={`Estado de la Change Request vinculada. Click para ver detalles.`}
                    icon={<IconCR />}
                    onClick={() => setCrDetail(fr)}
                  />
                ) : (
                  <BadgeWithTooltip
                    label={"Sin CR"}
                    color="#7a8aaa"
                    tooltip={"No se ha generado Change Request. Se crea automáticamente al aprobar la FR por el cliente."}
                    icon={<IconCR />}
                  />
                )}
              </div>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5 }}>{fr.description?.slice(0, 200)}</div>
            {fr.pm_response && (
              <div style={{ marginTop: 8, background: 'var(--success-bg)', border: '1px solid #00e5a020', borderRadius: 8, padding: '8px 12px', fontSize: 12, color: 'var(--text-2)' }}>
                <strong style={{ color: 'var(--success)' }}>Respuesta del equipo:</strong> {fr.pm_response}
                {fr.estimated_cost && <span style={{ marginLeft: 8, color: 'var(--warning)' }}>· {fr.estimated_cost}€</span>}
                {fr.estimated_delivery_weeks && <span style={{ marginLeft: 8, color: 'var(--accent)' }}>· {fr.estimated_delivery_weeks} semanas</span>}
              </div>
            )}
            {fr.client_approved === true && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--success)' }}>✓ Cliente aprobó el {fr.client_approved_at}</div>}
            {fr.client_approved === false && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--danger)' }}>✗ Cliente rechazó</div>}
            <div style={{ display: 'flex', gap: 8, marginTop: 10, justifyContent: 'flex-end' }}>
              {['new', 'reviewing'].includes(fr.status) && (
                <Button size="sm" onClick={() => { setResponding(fr); setResponseForm({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' }) }}>
                  💬 Responder
                </Button>
              )}
              {fr.status === 'approved' && (
                <Button size="sm" variant="secondary" onClick={() => updateStatus({ id: fr.id, status: 'in_development' })}>
                  🚀 Iniciar desarrollo
                </Button>
              )}
              {fr.status === 'in_development' && (
                <Button size="sm" variant="secondary" onClick={() => updateStatus({ id: fr.id, status: 'done' })}>
                  ✓ Marcar completada
                </Button>
              )}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 6 }}>{fr.submitted_at}</div>
          </div>
        ))
      }

      {responding && (
        <Modal open title={`Responder a: ${responding.title}`} onClose={() => setResponding(null)} width={520}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div><label style={ls}>Respuesta / Análisis *</label><textarea value={responseForm.pm_response} onChange={e => setResponseForm(f => ({ ...f, pm_response: e.target.value }))} rows={3} style={{ ...fs, resize: 'vertical' }} placeholder="Describe el análisis y la solución propuesta..." /></div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              <div><label style={ls}>Horas estimadas</label><input type="number" value={responseForm.estimated_hours} onChange={e => setResponseForm(f => ({ ...f, estimated_hours: e.target.value }))} style={fs} placeholder="0" /></div>
              <div><label style={ls}>Coste estimado €</label><input type="number" value={responseForm.estimated_cost} onChange={e => setResponseForm(f => ({ ...f, estimated_cost: e.target.value }))} style={fs} placeholder="0" /></div>
              <div><label style={ls}>Semanas entrega</label><input type="number" value={responseForm.estimated_delivery_weeks} onChange={e => setResponseForm(f => ({ ...f, estimated_delivery_weeks: e.target.value }))} style={fs} placeholder="0" /></div>
            </div>
            <div><label style={ls}>Estado</label>
              <select value={responseForm.status} onChange={e => setResponseForm(f => ({ ...f, status: e.target.value }))} style={fs}>
                <option value="estimated">Presupuestada (pendiente aprobación cliente)</option>
                <option value="rejected">Rechazada (no factible)</option>
              </select>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <Button variant="secondary" onClick={() => setResponding(null)}>Cancelar</Button>
              <Button onClick={() => respond({ id: responding.id, data: responseForm })} disabled={isPending || !responseForm.pm_response}>Enviar respuesta</Button>
            </div>
          </div>
        </Modal>
      )}

      {crDetail && (
        <Modal open title={`Detalle Change Request`} onClose={() => setCrDetail(null)} width={520}>
          {crDetail.cr_status ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ fontWeight: 700, fontSize: 15, color: crDetail.cr_status_color }}>
                <IconCR /> Estado: {crDetail.cr_status_label || crDetail.cr_status}
              </div>
              <div><b>Título:</b> {crDetail.title}</div>
              <div><b>Descripción:</b> {crDetail.description}</div>
              <div><b>Impacto:</b> {crDetail.impact_label || crDetail.impact || '—'}</div>
              <div><b>Coste impacto:</b> {crDetail.cost_impact != null ? crDetail.cost_impact + ' €' : '—'}</div>
              <div><b>Impacto en plazo:</b> {crDetail.schedule_impact_days != null ? crDetail.schedule_impact_days + ' días' : '—'}</div>
              <div><b>Notas/resolución:</b> {crDetail.resolution_notes || '—'}</div>
              <div><b>Fechas:</b> {['submitted_at','approved_at','implemented_at'].map(f => crDetail[f] && (<span key={f} style={{ marginRight: 10 }}>{f.replace('_at','')}: {crDetail[f]}</span>))}</div>
            </div>
          ) : (
            <div>No hay Change Request vinculada aún. Se creará automáticamente al aprobar la FR por el cliente.</div>
          )}
        </Modal>
      )}
    </div>
  )
}


// ── Portal: Mensajes ──────────────────────────────────────────────────────────
function PortalMensajesTab({ cid, projects }) {
  const [selectedProject, setSelectedProject] = useState(projects[0]?.id || '')
  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['portal-messages-team', cid, selectedProject],
    queryFn: () => selectedProject
      ? api.get('/portal/messages/team', { params: { project_id: selectedProject } }).then(r => r.data).catch(() => [])
      : Promise.resolve([]),
    enabled: !!selectedProject,
  })
  if (isLoading) return <Spinner />
  return (
    <div>
      {projects.length > 1 && (
        <div style={{ marginBottom: 16 }}>
          <label style={lbl}>Proyecto</label>
          <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)} style={inp}>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </select>
        </div>
      )}
      {!selectedProject
        ? <EmptyState icon="💬" title="Sin proyectos vinculados" description="Vincula un proyecto al cliente para ver mensajes" />
        : <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 16 }}>{messages.length} hilo(s) de mensajes</div>}
      {messages.length === 0
        ? <EmptyState icon="💬" title="Sin mensajes" description="No hay mensajes entre el cliente y el equipo" />
        : messages.map(m => (
          <div key={m.id} style={{ ...panel, padding: '14px 18px', marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{m.subject || '(Sin asunto)'}</div>
                <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 3, lineHeight: 1.5 }}>{m.body?.slice(0, 150)}</div>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', whiteSpace: 'nowrap', marginLeft: 12 }}>{m.created_at?.slice(0, 10)}</div>
            </div>
            {m.replies_count > 0 && (
              <div style={{ marginTop: 6, fontSize: 11, color: 'var(--accent)' }}>💬 {m.replies_count} respuesta(s)</div>
            )}
          </div>
        ))
      }
    </div>
  )
}


// ── Portal: Documentos ────────────────────────────────────────────────────────
function PortalDocumentosTab({ cid, projects }) {
  const [selectedProject, setSelectedProject] = useState(projects[0]?.id || '')
  const { data: docs = [], isLoading } = useQuery({
    queryKey: ['portal-docs-team', cid, selectedProject],
    queryFn: () => selectedProject
      ? api.get('/portal/documents/team', { params: { project_id: selectedProject } }).then(r => r.data).catch(() => [])
      : Promise.resolve([]),
    enabled: !!selectedProject,
  })
  const CAT_ICON = { general: '📄', contract: '📝', invoice: '🧾', report: '📊', specification: '📋', other: '📎' }
  if (isLoading) return <Spinner />
  return (
    <div>
      {projects.length > 1 && (
        <div style={{ marginBottom: 16 }}>
          <label style={lbl}>Proyecto</label>
          <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)} style={inp}>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </select>
        </div>
      )}
      {!selectedProject
        ? <EmptyState icon="📄" title="Sin proyectos vinculados" description="Vincula un proyecto al cliente para ver documentos" />
        : <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 16 }}>{docs.length} documento(s) compartido(s)</div>}
      {docs.length === 0
        ? <EmptyState icon="📄" title="Sin documentos" description="No hay documentos compartidos con este cliente" />
        : docs.map(d => (
          <div key={d.id} style={{ ...panel, padding: '14px 18px', marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <span style={{ fontSize: 24 }}>{CAT_ICON[d.category] || '📄'}</span>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{d.title}</div>
                <div style={{ fontSize: 11, color: 'var(--text-2)' }}>
                  {d.file_name && `${d.file_name} · `}{d.created_at?.slice(0, 10)}
                  {d.requires_signature && <span style={{ marginLeft: 8, color: 'var(--warning)' }}>✍️ Requiere firma</span>}
                </div>
              </div>
            </div>
            {d.file_url && (
              <a href={d.file_url} target="_blank" rel="noopener noreferrer"
                style={{ fontSize: 11, padding: '4px 12px', borderRadius: 6, border: '1px solid #1e2d45', color: 'var(--accent)', textDecoration: 'none', background: 'var(--accent-muted)' }}>
                ⬇ Descargar
              </a>
            )}
          </div>
        ))
      }
    </div>
  )
}


// ── Portal: Configuración del cliente ─────────────────────────────────────────
function PortalSettingsTab({ cid }) {
  const toast = useToast()
  const qc = useQueryClient()
  const { data: cfg, isLoading } = useQuery({
    queryKey: ['client-portal-cfg', cid],
    queryFn: () => api.get(`/clients/${cid}/portal-config`).then(r => r.data),
  })
  const [modules, setModules]     = useState([])
  const [sdWithout, setSdWithout] = useState(true)
  const [slaTier, setSlaTier]     = useState('')
  const [maxUsers, setMaxUsers]   = useState(10)
  const [defaultLang, setDefaultLang] = useState('es')
  const [allowEdit, setAllowEdit] = useState(true)
  const [allowPwd, setAllowPwd]   = useState(true)

  useEffect(() => {
    if (cfg) {
      setModules(cfg.enabled_modules || [])
      setSdWithout(cfg.sd_without_project ?? true)
      setSlaTier(cfg.sla_tier || '')
      setMaxUsers(cfg.max_portal_users || 10)
      setDefaultLang(cfg.default_language || 'es')
      setAllowEdit(cfg.allow_profile_edit ?? true)
      setAllowPwd(cfg.allow_pwd_change ?? true)
    }
  }, [cfg])

  const { mutate: save, isPending: saving } = useMutation({
    mutationFn: d => api.patch(`/clients/${cid}/portal-config`, d),
    onSuccess: () => { qc.invalidateQueries(['client-portal-cfg', cid]); toast.success('✅ Configuración guardada') },

    onError: e => toast.error(extractErr(e, 'Error'))
  })

  const toggleModule = (mod) => setModules(m => m.includes(mod) ? m.filter(x => x !== mod) : [...m, mod])

  const LANGUAGES = [
    { code: 'es', label: '🇪🇸 Español' }, { code: 'en', label: '🇬🇧 English' },
    { code: 'fr', label: '🇫🇷 Français' }, { code: 'de', label: '🇩🇪 Deutsch' },
    { code: 'pt', label: '🇵🇹 Português' }, { code: 'it', label: '🇮🇹 Italiano' },
    { code: 'pl', label: '🇵🇱 Polski' }, { code: 'zh', label: '🇨🇳 中文' },
  ]
  const SLA_COLOR = { enterprise: 'var(--purple)', gold: 'var(--warning)', silver: 'var(--text-2)', bronze: 'var(--warning)' }

  if (isLoading) return <Spinner />
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
      {/* Columna izquierda */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ ...panel, padding: '18px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 14 }}>🌐 Módulos del portal</div>
          <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 12 }}>Qué secciones puede ver el cliente en su portal.</div>
          {MODULES.map(m => (
            <label key={m.id} style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 10, cursor: 'pointer' }}>
              <input type="checkbox" checked={modules.includes(m.id)} onChange={() => toggleModule(m.id)} style={{ width: 15, height: 15, accentColor: 'var(--accent)' }} />
              <span style={{ fontSize: 15 }}>{m.icon}</span>
              <span style={{ fontSize: 13, color: modules.includes(m.id) ? 'var(--text-1)' : 'var(--text-2)', fontWeight: modules.includes(m.id) ? 600 : 400 }}>{m.label}</span>
            </label>
          ))}
        </div>

        <div style={{ ...panel, padding: '18px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 14 }}>🎫 Service Desk</div>
          <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', cursor: 'pointer' }}>
            <input type="checkbox" checked={sdWithout} onChange={e => setSdWithout(e.target.checked)} style={{ width: 15, height: 15, accentColor: 'var(--accent)', marginTop: 2 }} />
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Acceso sin proyecto vinculado</div>
              <div style={{ fontSize: 11, color: 'var(--text-2)' }}>Puede abrir tickets aunque no tenga proyectos asignados</div>
            </div>
          </label>
        </div>
      </div>

      {/* Columna derecha */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ ...panel, padding: '18px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 14 }}>🌍 Idioma y SLA</div>
          <div style={{ marginBottom: 14 }}>
            <label style={lbl}>Idioma por defecto del portal</label>
            <select value={defaultLang} onChange={e => setDefaultLang(e.target.value)} style={inp}>
              {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
            <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 4 }}>Se aplica a nuevos usuarios. Cada usuario puede cambiarlo desde su perfil.</div>
          </div>
          <div>
            <label style={lbl}>Tier SLA</label>
            <select value={slaTier} onChange={e => setSlaTier(e.target.value)} style={inp}>
              <option value="">Sin tier</option>
              <option value="bronze">🥉 Bronze — 24h respuesta</option>
              <option value="silver">🥈 Silver — 8h respuesta</option>
              <option value="gold">🥇 Gold — 4h respuesta</option>
              <option value="enterprise">💎 Enterprise — 1h respuesta 24/7</option>
            </select>
            {slaTier && <div style={{ marginTop: 6, fontSize: 11, padding: '6px 10px', borderRadius: 6, background: (SLA_COLOR[slaTier] || 'var(--text-2)') + '15', color: SLA_COLOR[slaTier] || 'var(--text-2)' }}>
              Tier activo: <strong>{slaTier.toUpperCase()}</strong>
            </div>}
          </div>
        </div>

        <div style={{ ...panel, padding: '18px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 14 }}>👤 Perfil del cliente</div>
          <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 12 }}>Define qué puede modificar el cliente desde su perfil en el portal.</div>
          {[
            { key: 'allowEdit', val: allowEdit, set: setAllowEdit, label: 'Puede editar su perfil', desc: 'Nombre visible, teléfono, cargo, idioma' },
            { key: 'allowPwd',  val: allowPwd,  set: setAllowPwd,  label: 'Puede cambiar su contraseña', desc: 'El cliente puede actualizar su contraseña de acceso' },
          ].map(opt => (
            <label key={opt.key} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', cursor: 'pointer', marginBottom: 14,
              background: opt.val ? 'var(--accent-muted)' : 'transparent', border: `1px solid ${opt.val ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
              borderRadius: 8, padding: '10px 12px' }}>
              <input type="checkbox" checked={opt.val} onChange={e => opt.set(e.target.checked)} style={{ width: 15, height: 15, accentColor: 'var(--accent)', marginTop: 2, flexShrink: 0 }} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: opt.val ? 'var(--text-1)' : 'var(--text-2)' }}>{opt.label}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{opt.desc}</div>
              </div>
            </label>
          ))}
          <div style={{ marginTop: 4 }}>
            <label style={lbl}>Máx. usuarios de portal</label>
            <input type="number" min={1} max={100} value={maxUsers} onChange={e => setMaxUsers(+e.target.value)} style={inp} />
          </div>
        </div>

        <Button onClick={() => save({ enabled_modules: modules, sd_without_project: sdWithout, sla_tier: slaTier || null, max_portal_users: maxUsers, default_language: defaultLang, allow_profile_edit: allowEdit, allow_pwd_change: allowPwd })} style={{ width: '100%' }} loading={saving}>
          💾 Guardar configuración del portal
        </Button>
      </div>
    </div>
  )
}


// ── Usuarios del portal ───────────────────────────────────────────────────────
function PortalUsersTab({ cid, clientName }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [showReset, setShowReset] = useState(null)    // { id, email }
  const [newPassword, setNewPassword] = useState('')
  const [createdCreds, setCreatedCreds] = useState(null)  // { email, password }
  const [editUser, setEditUser] = useState(null)   // usuario a editar
  const [editForm, setEditForm] = useState({})
  const [form, setForm] = useState({
    full_name: '', email: '', job_title: '', phone: '',
    project_ids: [], password: '', confirm_password: '',
    can_approve_deliverables: true, can_request_changes: true,
    can_view_budget: false, can_view_team: false,
  })

  // Usar el endpoint real de portal que gestiona el login
  const { data: users = [] } = useQuery({
    queryKey: ['portal-clients-org', cid],
    queryFn: () => api.get('/portal/clients', { params: { client_org_id: cid } }).then(r => r.data),
  })
  const { data: clientDetail } = useQuery({
    queryKey: ['client-detail-projects', cid],
    queryFn: () => api.get(`/clients/${cid}`).then(r => r.data),
  })
  const projects = clientDetail?.projects || []
  const projectLabelById = new Map(projects.map(p => [p.id, `${p.code} — ${p.name}`]))

  const { mutate: add, isPending } = useMutation({
    mutationFn: d => api.post('/portal/clients', d).then(r => r.data),
    onSuccess: (_res) => {
      qc.invalidateQueries(['portal-clients-org', cid])
      setShowAdd(false)
      setCreatedCreds({ email: form.email, password: form.password })
      setForm({ full_name: '', email: '', job_title: '', phone: '', project_ids: [], password: '', confirm_password: '', can_approve_deliverables: true, can_request_changes: true, can_view_budget: false, can_view_team: false })
    },
    onError: e => toast.error(extractErr(e, 'Error al crear usuario')),
  })

  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, active }) => api.patch(`/portal/clients/${id}`, { is_active: active }),
    onSuccess: () => qc.invalidateQueries(['portal-clients-org', cid]),
    onError: e => toast.error(extractErr(e, 'Error'))
  })

  const { mutate: resetPwd, isPending: resetting } = useMutation({
    mutationFn: ({ id, password }) => api.patch(`/portal/clients/${id}`, { password }),
    onSuccess: () => { qc.invalidateQueries(['portal-clients-org', cid]); setShowReset(null); setNewPassword('') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: updateUser, isPending: updating } = useMutation({
    mutationFn: ({ id, data }) => api.patch(`/portal/clients/${id}`, data).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries(['portal-clients-org', cid])
      setEditUser(null)
      toast.success('Usuario actualizado correctamente')
    },
    onError: e => toast.error(extractErr(e, 'Error al actualizar usuario')),
  })

  const openEdit = (u) => {
    setEditUser(u)
    setEditForm({
      full_name: u.full_name || '',
      email: u.email || '',
      job_title: u.job_title || '',
      phone: u.phone || '',
      project_ids: Array.isArray(u.project_ids) ? u.project_ids : (u.project_id ? [u.project_id] : []),
      can_approve_deliverables: u.can_approve_deliverables ?? true,
      can_request_changes: u.can_request_changes ?? true,
      can_view_budget: u.can_view_budget ?? false,
      can_view_team: u.can_view_team ?? false,
    })
  }

  const portalUrl = `${window.location.origin}/portal`

  return (
    <div>
      {/* Banner informativo del flujo */}
      <div style={{ background: 'var(--accent-muted)', border: '1px solid #00d4ff20', borderRadius: 10, padding: '14px 18px', marginBottom: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6, color: 'var(--accent)' }}>🌐 Cómo accede el cliente al portal</div>
        <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.7 }}>
          1. Crea un usuario con email y contraseña en este formulario.<br/>
          2. Comparte las credenciales con el cliente (email + contraseña).<br/>
          3. El cliente accede en: <strong style={{ color: 'var(--text-1)' }}>{portalUrl}</strong><br/>
          4. Desde el portal puede ver proyectos, abrir tickets de Service Desk, aprobar entregables y más.
        </div>
        <button onClick={() => navigator.clipboard.writeText(portalUrl)}
          style={{ marginTop: 10, background: 'transparent', border: '1px solid #00d4ff30', borderRadius: 6, padding: '4px 12px', color: 'var(--accent)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
          📋 Copiar URL del portal
        </button>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{users.length} usuario(s) de portal activos</div>
        <Button onClick={() => setShowAdd(true)} size="sm">+ Crear usuario de portal</Button>
      </div>

      {users.length === 0
        ? <EmptyState icon="🔐" title="Sin accesos al portal" description="Crea usuarios para que el cliente pueda acceder al portal" />
        : users.map(u => {
          const assignedProjects = (u.project_ids || []).map(pid => projectLabelById.get(pid)).filter(Boolean)
          return (
          <div key={u.id} style={{ ...panel, padding: '14px 18px', marginBottom: 10, opacity: u.is_active ? 1 : 0.5 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                <div style={{ width: 38, height: 38, borderRadius: 10, background: u.is_active ? 'var(--accent-muted)' : 'var(--surface-4)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 17, fontWeight: 800, color: u.is_active ? 'var(--accent)' : 'var(--text-2)' }}>
                  {u.full_name?.charAt(0)?.toUpperCase() || '?'}
                </div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{u.full_name}
                    {!u.is_active && <span style={{ marginLeft: 6, fontSize: 10, color: 'var(--danger)', background: 'var(--danger-bg)', padding: '1px 6px', borderRadius: 4 }}>Inactivo</span>}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                    📧 {u.email}{u.job_title && ` · ${u.job_title}`}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
                    {assignedProjects.length > 0 ? `📁 Proyectos: ${assignedProjects.join(' · ')}` : '🔓 Sin proyecto — acceso general al Service Desk'}
                    {u.last_login && <span style={{ marginLeft: 10 }}>· Último acceso: <strong style={{ color: 'var(--text-2)' }}>{u.last_login.slice(0, 10)}</strong></span>}
                    {!u.last_login && <span style={{ marginLeft: 10, color: 'rgba(248,113,113,0.50)' }}>· Nunca ha accedido</span>}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                {u.can_approve_deliverables && <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'var(--success-bg)', color: 'var(--success)' }}>✓ Aprueba</span>}
                {u.can_view_budget && <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'var(--warning-bg)', color: 'var(--warning)' }}>💰 Budget</span>}
                {u.can_view_team && <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'var(--purple-bg)', color: 'var(--purple)' }}>👥 Equipo</span>}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 10, paddingTop: 10, borderTop: '1px solid #1e2d45' }}>
              <button onClick={() => openEdit(u)}
                style={{ fontSize: 11, padding: '4px 12px', borderRadius: 6, border: '1px solid #1e2d45', background: 'transparent', color: 'var(--success)', cursor: 'pointer', fontFamily: 'inherit' }}>
                ✏️ Editar
              </button>
              <button onClick={() => setShowReset({ id: u.id, email: u.email })}
                style={{ fontSize: 11, padding: '4px 12px', borderRadius: 6, border: '1px solid #1e2d45', background: 'transparent', color: 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit' }}>
                🔑 Cambiar contraseña
              </button>
              <button onClick={() => toggle({ id: u.id, active: !u.is_active })}
                style={{ fontSize: 11, padding: '4px 12px', borderRadius: 6, border: '1px solid #1e2d45', background: 'transparent', color: u.is_active ? 'var(--danger)' : 'var(--success)', cursor: 'pointer', fontFamily: 'inherit' }}>
                {u.is_active ? '⏸ Suspender acceso' : '▶ Reactivar acceso'}
              </button>
              <button onClick={() => {
                const text = `Acceso al portal de ${clientName || 'Clarive'}\n\nURL: ${portalUrl}\nEmail: ${u.email}\n\nContacta con tu gestor para obtener tu contraseña.`
                navigator.clipboard.writeText(text)
                toast.info('📋 Info de acceso copiada al portapapeles')
              }} style={{ fontSize: 11, padding: '4px 12px', borderRadius: 6, border: '1px solid #1e2d45', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit' }}>
                📋 Copiar datos de acceso
              </button>
            </div>
          </div>
          )
        })
      }

      {/* Modal: credenciales creadas */}
      {createdCreds && (
        <Modal open title="✅ Usuario creado correctamente" onClose={() => setCreatedCreds(null)} width={480}>
          <div style={{ background: 'var(--success-bg)', border: '1px solid #00e5a030', borderRadius: 10, padding: '18px 20px', marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12, color: 'var(--success)' }}>Credenciales de acceso al portal</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 12, color: 'var(--text-2)' }}>URL del portal:</span>
                <strong style={{ fontSize: 13, color: 'var(--accent)' }}>{portalUrl}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 12, color: 'var(--text-2)' }}>Email:</span>
                <strong style={{ fontSize: 13 }}>{createdCreds.email}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 12, color: 'var(--text-2)' }}>Contraseña:</span>
                <strong style={{ fontSize: 13, fontFamily: 'monospace', background: 'var(--surface-4)', padding: '3px 10px', borderRadius: 6 }}>{createdCreds.password}</strong>
              </div>
            </div>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 16 }}>⚠️ Guarda estas credenciales — la contraseña no se puede recuperar, solo restablecer.</div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => {
              navigator.clipboard.writeText(`Portal: ${portalUrl}\nEmail: ${createdCreds.email}\nContraseña: ${createdCreds.password}`)
              toast.success('Copiado al portapapeles')
            }} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8, padding: '7px 16px', color: 'var(--accent)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>📋 Copiar todo</button>
            <Button onClick={() => setCreatedCreds(null)}>Entendido</Button>
          </div>
        </Modal>
      )}

      {/* Modal: cambiar contraseña */}
      {showReset && (
        <Modal open title="🔑 Cambiar contraseña" onClose={() => { setShowReset(null); setNewPassword('') }} width={420}>
          <div style={{ marginBottom: 6, fontSize: 13, color: 'var(--text-2)' }}>Usuario: <strong style={{ color: 'var(--text-1)' }}>{showReset.email}</strong></div>
          <div style={{ marginBottom: 16 }}>
            <label style={lbl}>Nueva contraseña</label>
            <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)}
              style={inp} placeholder="Mínimo 8 caracteres" />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => { setShowReset(null); setNewPassword('') }} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => resetPwd({ id: showReset.id, password: newPassword })} disabled={newPassword.length < 6 || resetting}>
              {resetting ? '⟳ Guardando...' : '✓ Cambiar contraseña'}
            </Button>
          </div>
        </Modal>
      )}

      {/* Modal: editar usuario */}
      {editUser && (
        <Modal open title={`✏️ Editar: ${editUser.full_name}`} onClose={() => setEditUser(null)} width={560}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
            <div>
              <label style={lbl}>Nombre completo *</label>
              <input value={editForm.full_name}
                onChange={e => setEditForm(f => ({ ...f, full_name: e.target.value }))}
                style={inp} />
            </div>
            <div>
              <label style={lbl}>Email *</label>
              <input type="email" value={editForm.email}
                onChange={e => setEditForm(f => ({ ...f, email: e.target.value }))}
                style={inp} />
            </div>
            <div>
              <label style={lbl}>Cargo</label>
              <input value={editForm.job_title}
                onChange={e => setEditForm(f => ({ ...f, job_title: e.target.value }))}
                style={inp} placeholder="Ej: Director IT" />
            </div>
            <div>
              <label style={lbl}>Teléfono</label>
              <input value={editForm.phone}
                onChange={e => setEditForm(f => ({ ...f, phone: e.target.value }))}
                style={inp} placeholder="+34 600 000 000" />
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={lbl}>Proyectos asociados</label>
              <select multiple value={editForm.project_ids || []}
                onChange={e => setEditForm(f => ({ ...f, project_ids: Array.from(e.target.selectedOptions).map(opt => opt.value).filter(Boolean) }))}
                style={{ ...inp, height: 38 + Math.min(projects.length, 4) * 28 }}>
                {projects.map(p => (
                  <option key={p.id} value={p.id}>{p.code} — {p.name}</option>
                ))}
              </select>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>Puedes asignar acceso a varios proyectos al mismo usuario.</div>
            </div>
          </div>

          <div style={{ ...panel, padding: '12px 16px', marginBottom: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 10, color: 'var(--text-2)',
              textTransform: 'uppercase', letterSpacing: '0.05em' }}>Permisos en el portal</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {[
                { key: 'can_approve_deliverables', label: '✓ Puede aprobar entregables', desc: 'Validar o rechazar entregables del proyecto' },
                { key: 'can_request_changes',      label: '↩ Puede solicitar cambios',   desc: 'Enviar solicitudes de cambio' },
                { key: 'can_view_budget',           label: '💰 Puede ver presupuesto',    desc: 'Ver consumo vs presupuesto' },
                { key: 'can_view_team',             label: '👥 Puede ver equipo',          desc: 'Ver miembros del equipo asignado' },
              ].map(p => (
                <label key={p.key} style={{
                  display: 'flex', gap: 8, alignItems: 'flex-start', cursor: 'pointer',
                  background: editForm[p.key] ? 'var(--accent-muted)' : 'transparent',
                  border: `1px solid ${editForm[p.key] ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
                  borderRadius: 8, padding: '8px 10px',
                }}>
                  <input type="checkbox" checked={!!editForm[p.key]}
                    onChange={e => setEditForm(f => ({ ...f, [p.key]: e.target.checked }))}
                    style={{ accentColor: 'var(--accent)', marginTop: 2, flexShrink: 0 }} />
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600,
                      color: editForm[p.key] ? 'var(--text-1)' : 'var(--text-2)' }}>{p.label}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{p.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setEditUser(null)}
              style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8,
                padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
              Cancelar
            </button>
            <Button
              loading={updating}
              disabled={!editForm.full_name || !editForm.email || updating}
              onClick={() => updateUser({ id: editUser.id, data: {
                full_name:                editForm.full_name,
                email:                    editForm.email,
                job_title:                editForm.job_title || null,
                phone:                    editForm.phone || null,
                project_ids:              editForm.project_ids || [],
                can_approve_deliverables: editForm.can_approve_deliverables,
                can_request_changes:      editForm.can_request_changes,
                can_view_budget:          editForm.can_view_budget,
                can_view_team:            editForm.can_view_team,
              }})}>
              {updating ? '⟳ Guardando...' : '💾 Guardar cambios'}
            </Button>
          </div>
        </Modal>
      )}

      {/* Modal: crear usuario */}
      {showAdd && (
        <Modal open title="Crear acceso al portal" onClose={() => setShowAdd(false)} width={560}>
          <div style={{ background: 'var(--purple-bg)', border: '1px solid #7c3aed30', borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 12, color: 'var(--text-2)' }}>
            🔐 Crea las credenciales que el cliente usará para entrar en <strong style={{ color: 'var(--text-1)' }}>{portalUrl}</strong>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
            <div><label style={lbl}>Nombre completo *</label><input value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Email * (será el usuario de login)</label><input type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} style={inp} placeholder="cliente@empresa.com" /></div>
            <div><label style={lbl}>Contraseña *</label><input type="password" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} style={inp} placeholder="Mínimo 6 caracteres" /></div>
            <div><label style={lbl}>Confirmar contraseña</label><input type="password" value={form.confirm_password} onChange={e => setForm(f => ({ ...f, confirm_password: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Cargo</label><input value={form.job_title} onChange={e => setForm(f => ({ ...f, job_title: e.target.value }))} style={inp} placeholder="Ej: Director IT" /></div>
            <div>
              <label style={lbl}>Asociar a proyectos (opcional)</label>
              <select multiple value={form.project_ids} onChange={e => {
                const options = Array.from(e.target.selectedOptions).map(opt => opt.value).filter(Boolean)
                setForm(f => ({ ...f, project_ids: options }))
              }} style={{ ...inp, height: 38 + Math.min(projects.length, 4) * 28 }}>
                {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </select>
            </div>
          </div>
          <div style={{ ...panel, padding: '12px 16px', marginBottom: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 10, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Permisos en el portal</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {[
                { key: 'can_approve_deliverables', label: '✓ Puede aprobar entregables', desc: 'Validar o rechazar entregables del proyecto' },
                { key: 'can_request_changes', label: '↩ Puede solicitar cambios', desc: 'Enviar solicitudes de cambio' },
                { key: 'can_view_budget', label: '💰 Puede ver presupuesto', desc: 'Ver consumo vs presupuesto' },
                { key: 'can_view_team', label: '👥 Puede ver equipo', desc: 'Ver miembros del equipo asignado' },
              ].map(p => (
                <label key={p.key} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', cursor: 'pointer',
                  background: form[p.key] ? 'var(--accent-muted)' : 'transparent', border: `1px solid ${form[p.key] ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
                  borderRadius: 8, padding: '8px 10px' }}>
                  <input type="checkbox" checked={form[p.key]} onChange={e => setForm(f => ({ ...f, [p.key]: e.target.checked }))}
                    style={{ accentColor: 'var(--accent)', marginTop: 2, flexShrink: 0 }} />
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: form[p.key] ? 'var(--text-1)' : 'var(--text-2)' }}>{p.label}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{p.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>
          {form.password && form.confirm_password && form.password !== form.confirm_password && (
            <div style={{ background: 'var(--danger-bg)', border: '1px solid #ff475730', borderRadius: 8, padding: '8px 12px', marginBottom: 12, fontSize: 12, color: 'var(--danger)' }}>
              ✗ Las contraseñas no coinciden
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowAdd(false)} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => add({ ...form, client_org_id: cid, project_ids: form.project_ids && form.project_ids.length > 0 ? form.project_ids : undefined })}
              disabled={!form.full_name || !form.email || !form.password || form.password !== form.confirm_password || isPending}>
              {isPending ? '⟳ Creando...' : '🔐 Crear acceso al portal'}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
export default function ClientsPage() {
  const _t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [statusF, setStatusF] = useState('')
  const [sortBy, setSortBy] = useState('name')
  const [selected, setSelected] = useState(null)
  const [activeTab, setActiveTab] = useState('360')
  const [showCreate, setShowCreate] = useState(false)
  const [newForm, setNewForm] = useState({ name: '', short_name: '', tax_id: '', contact_name: '', contact_email: '', contact_phone: '', status: 'active', industry: 'other', notes: '' })
  const [showEdit, setShowEdit] = useState(false)
  const [editClientForm, setEditClientForm] = useState({})
  const [clientView, setClientView] = useState('grid')

  const { data: clients = [], isLoading } = useQuery({
    queryKey: ['clients', search, statusF],
    queryFn: () => api.get('/clients', { params: { q: search || undefined, status: statusF || undefined } }).then(r => r.data),
  })

  const { sort: clientSort, setSort: setClientSort, sortedData: sortedClients } = useSort(clients, sortBy)

  const { data: detail } = useQuery({
    queryKey: ['client-detail', selected?.id],
    queryFn: () => api.get(`/clients/${selected.id}`).then(r => r.data),
    enabled: !!selected,
  })

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: d => api.post('/clients', d),
    onSuccess: (_res) => {
      qc.invalidateQueries(['clients'])
      setShowCreate(false)
      setNewForm({ name: '', short_name: '', tax_id: '', contact_name: '', contact_email: '', contact_phone: '', status: 'active', industry: 'other', notes: '' })
      toast.success('Cliente creado correctamente')
    },
    onError: e => toast.error(extractErr(e, 'Error al crear cliente')),
  })

  const { mutate: updateClient, isPending: updatingClient } = useMutation({
    mutationFn: ({ id, data }) => api.patch(`/clients/${id}`, data),
    onSuccess: () => {
      qc.invalidateQueries(['clients'])
      qc.invalidateQueries(['client-detail', selected?.id])
      setShowEdit(false)
      toast.success('Cliente actualizado correctamente')
    },
    onError: e => toast.error(extractErr(e, 'Error al actualizar cliente')),
  })

  const openEditClient = () => {
    if (!selected) return
    setEditClientForm({
      name:          selected.name          || '',
      short_name:    selected.short_name    || '',
      tax_id:        selected.tax_id        || '',
      industry:      selected.industry      || 'other',
      contact_name:  selected.contact_name  || '',
      contact_email: selected.contact_email || '',
      contact_phone: selected.contact_phone || '',
      status:        selected.status        || 'active',
      notes:         selected.notes         || '',
      website:       selected.website       || '',
      country:       selected.country       || '',
      city:          selected.city          || '',
    })
    setShowEdit(true)
  }

  const TABS = [
    { id: '360',      label: '🎯 Vista 360' },
    { id: 'contacts', label: '👥 Contactos' },
    { id: 'projects', label: '⬡ Proyectos' },
    { id: 'timeline', label: '📅 Timeline' },
    { id: 'contracts',label: '📄 Contratos' },
    { id: 'licenses', label: '🔑 Licencias' },
    { id: 'invoices', label: '🧾 Facturas' },
    { id: 'tickets',  label: '🎫 Tickets SD' },
    { id: 'portal',   label: '🌐 Portal' },
  ]

  const INDUSTRIES = ['technology','finance','healthcare','retail','manufacturing','education','consulting','real_estate','media','other']

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 0, height: '100%', padding: 32 }}>
      {/* Lista de clientes */}
      <div style={{ paddingRight: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div style={{ fontSize: 18, fontWeight: 800 }}>Clientes</div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <ViewToggle view={clientView} onChange={setClientView} />
            <Button data-tour="btn-new-client" onClick={() => setShowCreate(true)} size="sm">+ Nuevo</Button>
          </div>
        </div>
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Buscar cliente..." style={{ ...inp, marginBottom: 8 }} />
        <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
          <select value={statusF} onChange={e => setStatusF(e.target.value)} style={{ ...inp, flex: 1 }}>
            <option value="">Todos los estados</option>
            {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select value={sortBy} onChange={e => setSortBy(e.target.value)} style={{ ...inp, width: 'auto' }}>
            <option value="name">A-Z</option>
            <option value="projects_count">Proyectos</option>
            <option value="tickets_count">Tickets</option>
            <option value="status">Estado</option>
          </select>
        </div>
        {isLoading ? <Spinner /> : clients.length === 0
          ? <EmptyState icon="🏢" title="Sin clientes" />
          : clientView === 'grid' ? sortedClients.map(c => (
            <div key={c.id} onClick={() => { setSelected(c); setActiveTab('360') }}
              style={{ ...panel, padding: '14px 16px', marginBottom: 8, cursor: 'pointer', borderColor: selected?.id === c.id ? 'var(--accent-glow)' : 'var(--surface-4)', background: selected?.id === c.id ? 'var(--accent-muted)' : 'var(--surface-2)', transition: 'all 0.12s' }}
              onMouseEnter={e => { if (selected?.id !== c.id) { e.currentTarget.style.borderColor = 'var(--surface-5)' } }}
              onMouseLeave={e => { if (selected?.id !== c.id) { e.currentTarget.style.borderColor = 'var(--surface-4)' } }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{c.name}</div>
                <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 20, background: (STATUS_COLOR[c.status] || 'var(--text-2)') + '20', color: STATUS_COLOR[c.status] || 'var(--text-2)', fontWeight: 700, whiteSpace: 'nowrap' }}>
                  {STATUS_LABEL[c.status] || c.status}
                </span>
              </div>
              {c.contact_name && <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>👤 {c.contact_name}</div>}
              <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-3)' }}>
                <span>⬡ {c.projects_count}</span>
                <span>🎫 {c.tickets_count}</span>
                {c.invoices_count > 0 && <span>🧾 {c.invoices_count}</span>}
                <span>👤 {c.portal_users_count}</span>
              </div>
            </div>
          ))
          : (
            <div style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 10, overflow: 'hidden' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 50px 40px', gap: 8, padding: '8px 12px', borderBottom: '1px solid #1e2d45', fontSize: 10, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
                <SortableTH col="name" sort={clientSort} onSort={setClientSort}>Cliente</SortableTH>
                <SortableTH col="projects_count" sort={clientSort} onSort={setClientSort}>Proy</SortableTH>
                <span>SD</span>
              </div>
              {sortedClients.map(c => (
                <div key={c.id} onClick={() => { setSelected(c); setActiveTab('360') }}
                  style={{ display: 'grid', gridTemplateColumns: '1fr 50px 40px', gap: 8, padding: '9px 12px', borderBottom: '1px solid #1e2d4530', alignItems: 'center', cursor: 'pointer', background: selected?.id === c.id ? 'var(--accent-muted)' : 'transparent' }}
                  onMouseEnter={e => { if (selected?.id !== c.id) e.currentTarget.style.background = 'var(--surface-3)' }}
                  onMouseLeave={e => { if (selected?.id !== c.id) e.currentTarget.style.background = 'transparent' }}>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.name}</div>
                    <span style={{ fontSize: 9, padding: '1px 5px', borderRadius: 10, background: (STATUS_COLOR[c.status] || 'var(--text-2)') + '20', color: STATUS_COLOR[c.status] || 'var(--text-2)', fontWeight: 700 }}>
                      {STATUS_LABEL[c.status] || c.status}
                    </span>
                  </div>
                  <span style={{ fontSize: 12, color: 'var(--text-2)', textAlign: 'center' }}>{c.projects_count}</span>
                  <span style={{ fontSize: 12, color: 'var(--text-2)', textAlign: 'center' }}>{c.tickets_count}</span>
                </div>
              ))}
            </div>
          )
        }
      </div>

      {/* Detalle del cliente */}
      <div style={{ borderLeft: '1px solid #1e2d45', paddingLeft: 24 }}>
        {!selected ? (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-3)' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>🏢</div>
              <div style={{ fontSize: 14 }}>Selecciona un cliente para ver su perfil completo</div>
            </div>
          </div>
        ) : (
          <div>
            {/* Header del cliente */}
            <div style={{ marginBottom: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div>
                  <div style={{ fontSize: 22, fontWeight: 800 }}>{detail?.name || selected.name}</div>
                  <div style={{ fontSize: 13, color: 'var(--text-2)' }}>
                    {detail?.industry && `${detail.industry} · `}
                    {detail?.city && `${detail.city}, `}{detail?.country}
                    {detail?.account_manager_name && ` · Account: ${detail.account_manager_name}`}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <button onClick={openEditClient}
                    style={{ fontSize: 12, padding: '5px 14px', borderRadius: 8, border: '1px solid #1e2d45',
                      background: 'transparent', color: 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit',
                      fontWeight: 600, display: 'flex', alignItems: 'center', gap: 5 }}>
                    ✏️ Editar
                  </button>
                  <span style={{ fontSize: 11, padding: '4px 12px', borderRadius: 20, background: (STATUS_COLOR[detail?.status] || 'var(--text-2)') + '20', color: STATUS_COLOR[detail?.status] || 'var(--text-2)', fontWeight: 700 }}>
                    {STATUS_LABEL[detail?.status] || detail?.status}
                  </span>
                  {detail?.portal_config?.sla_tier && (
                    <span style={{ fontSize: 11, padding: '4px 12px', borderRadius: 20, background: (SLA_COLOR[detail.portal_config.sla_tier] || 'var(--text-2)') + '20', color: SLA_COLOR[detail.portal_config.sla_tier] || 'var(--text-2)', fontWeight: 700 }}>
                      ⭐ {detail.portal_config.sla_tier.toUpperCase()}
                    </span>
                  )}
                </div>
              </div>
              {/* Chips de recursos vinculados */}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {detail?.projects?.length > 0 && <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 20, background: 'var(--accent-muted)', color: 'var(--accent)' }}>⬡ {detail.projects.length} proyectos</span>}
                {detail?.contracts?.length > 0 && <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 20, background: 'var(--success-bg)', color: 'var(--success)' }}>📄 {detail.contracts.length} contratos</span>}
                {detail?.licenses?.length > 0 && <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 20, background: 'var(--purple-bg)', color: 'var(--purple)' }}>🔑 {detail.licenses.length} licencias</span>}
                {detail?.portal_users?.length > 0 && <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 20, background: 'var(--warning-bg)', color: 'var(--warning)' }}>👤 {detail.portal_users.length} usuarios portal</span>}
              </div>
            </div>

            {/* Tabs */}
            <div style={{ display: 'flex', gap: 4, marginBottom: 20, flexWrap: 'wrap', borderBottom: '1px solid #1e2d45', paddingBottom: 12 }}>
              {TABS.map(t => (
                <button key={t.id} onClick={() => setActiveTab(t.id)}
                  style={{ padding: '6px 14px', borderRadius: 8, border: `1px solid ${activeTab === t.id ? 'var(--accent-glow)' : 'transparent'}`,
                    background: activeTab === t.id ? 'var(--accent-muted)' : 'transparent', color: activeTab === t.id ? 'var(--accent)' : 'var(--text-2)',
                    fontSize: 12, fontWeight: activeTab === t.id ? 700 : 400, cursor: 'pointer', fontFamily: 'inherit' }}>
                  {t.label}
                </button>
              ))}
            </div>

            {/* Contenido de cada tab */}
            {activeTab === '360'      && <Client360 cid={selected.id} />}
            {activeTab === 'contacts' && <ContactsTab cid={selected.id} />}
            {activeTab === 'projects' && <ProjectsTab cid={selected.id} />}
            {activeTab === 'timeline'  && <ClientTimelineTab cid={selected.id} clientName={detail?.name} />}
            {activeTab === 'contracts' && <ContractsTab cid={selected.id} />}
            {activeTab === 'licenses'  && <LicensesTab cid={selected.id} />}
            {activeTab === 'invoices' && <InvoicesClientTab cid={selected.id} />}
            {activeTab === 'tickets' && (
              <div>
                {detail?.tickets?.length === 0
                  ? <EmptyState icon="🎫" title="Sin tickets" description="Este cliente no ha abierto tickets aún" />
                  : detail?.tickets?.map(t => (
                    <div key={t.id} style={{ ...panel, padding: '12px 16px', marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 600 }}>{t.title}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-2)' }}>
                          {t.linked_resource_type && `${t.linked_resource_type} · `}{t.created_at?.slice(0, 10)}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'var(--surface-4)', color: 'var(--text-2)' }}>{t.priority}</span>
                        <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'var(--accent-muted)', color: 'var(--accent)' }}>{t.status}</span>
                      </div>
                    </div>
                  ))
                }
              </div>
            )}
            {activeTab === 'portal'   && <PortalConfigTab cid={selected.id} clientDetail={detail} />}

          </div>
        )}
      </div>

      {/* Modal editar cliente */}
      {showEdit && (
        <Modal open title={`✏️ Editar: ${editClientForm.name}`} onClose={() => setShowEdit(false)} width={600}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
            <div>
              <label style={lbl}>Nombre *</label>
              <input value={editClientForm.name}
                onChange={e => setEditClientForm(f => ({ ...f, name: e.target.value }))}
                style={inp} />
            </div>
            <div>
              <label style={lbl}>Nombre corto</label>
              <input value={editClientForm.short_name}
                onChange={e => setEditClientForm(f => ({ ...f, short_name: e.target.value }))}
                style={inp} />
            </div>
            <div>
              <label style={lbl}>CIF / NIF / VAT</label>
              <input value={editClientForm.tax_id}
                onChange={e => setEditClientForm(f => ({ ...f, tax_id: e.target.value }))}
                style={inp} />
            </div>
            <div>
              <label style={lbl}>Sector</label>
              <select value={editClientForm.industry}
                onChange={e => setEditClientForm(f => ({ ...f, industry: e.target.value }))}
                style={inp}>
                {INDUSTRIES.map(i => (
                  <option key={i} value={i}>{i.charAt(0).toUpperCase() + i.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={lbl}>Contacto principal</label>
              <input value={editClientForm.contact_name}
                onChange={e => setEditClientForm(f => ({ ...f, contact_name: e.target.value }))}
                style={inp} />
            </div>
            <div>
              <label style={lbl}>Email contacto</label>
              <input type="email" value={editClientForm.contact_email}
                onChange={e => setEditClientForm(f => ({ ...f, contact_email: e.target.value }))}
                style={inp} />
            </div>
            <div>
              <label style={lbl}>Teléfono</label>
              <input value={editClientForm.contact_phone}
                onChange={e => setEditClientForm(f => ({ ...f, contact_phone: e.target.value }))}
                style={inp} />
            </div>
            <div>
              <label style={lbl}>Estado</label>
              <select value={editClientForm.status}
                onChange={e => setEditClientForm(f => ({ ...f, status: e.target.value }))}
                style={inp}>
                {Object.entries(STATUS_LABEL).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={lbl}>País</label>
              <input value={editClientForm.country}
                onChange={e => setEditClientForm(f => ({ ...f, country: e.target.value }))}
                style={inp} placeholder="España" />
            </div>
            <div>
              <label style={lbl}>Ciudad</label>
              <input value={editClientForm.city}
                onChange={e => setEditClientForm(f => ({ ...f, city: e.target.value }))}
                style={inp} placeholder="Madrid" />
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={lbl}>Website</label>
              <input value={editClientForm.website}
                onChange={e => setEditClientForm(f => ({ ...f, website: e.target.value }))}
                style={inp} placeholder="https://empresa.com" />
            </div>
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={lbl}>Notas</label>
            <textarea value={editClientForm.notes}
              onChange={e => setEditClientForm(f => ({ ...f, notes: e.target.value }))}
              style={{ ...inp, minHeight: 70, resize: 'vertical' }} />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowEdit(false)}
              style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8,
                padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
              Cancelar
            </button>
            <Button
              loading={updatingClient}
              disabled={!editClientForm.name || updatingClient}
              onClick={() => updateClient({ id: selected.id, data: editClientForm })}>
              {updatingClient ? '⟳ Guardando...' : '💾 Guardar cambios'}
            </Button>
          </div>
        </Modal>
      )}

      {/* Modal nuevo cliente */}
      {showCreate && (
        <Modal open title="Nuevo cliente" onClose={() => setShowCreate(false)} width={600}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
            <div><label style={lbl}>Nombre *</label><input value={newForm.name} onChange={e => setNewForm(f => ({ ...f, name: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Nombre corto</label><input value={newForm.short_name} onChange={e => setNewForm(f => ({ ...f, short_name: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>CIF / NIF / VAT</label><input value={newForm.tax_id} onChange={e => setNewForm(f => ({ ...f, tax_id: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Sector</label>
              <select value={newForm.industry} onChange={e => setNewForm(f => ({ ...f, industry: e.target.value }))} style={inp}>
                {INDUSTRIES.map(i => <option key={i} value={i}>{i.charAt(0).toUpperCase() + i.slice(1)}</option>)}
              </select>
            </div>
            <div><label style={lbl}>Contacto principal</label><input value={newForm.contact_name} onChange={e => setNewForm(f => ({ ...f, contact_name: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Email contacto</label><input type="email" value={newForm.contact_email} onChange={e => setNewForm(f => ({ ...f, contact_email: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Teléfono</label><input value={newForm.contact_phone} onChange={e => setNewForm(f => ({ ...f, contact_phone: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Estado</label>
              <select value={newForm.status} onChange={e => setNewForm(f => ({ ...f, status: e.target.value }))} style={inp}>
                {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
          </div>
          <div style={{ marginBottom: 16 }}><label style={lbl}>Notas</label><textarea value={newForm.notes} onChange={e => setNewForm(f => ({ ...f, notes: e.target.value }))} style={{ ...inp, minHeight: 70, resize: 'vertical' }} /></div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowCreate(false)} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => create(newForm)} disabled={!newForm.name || creating}>
              {creating ? '⟳ Creando...' : '✓ Crear cliente'}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
