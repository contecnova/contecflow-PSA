/**
 * BiGdprPanel.jsx — GDPR Compliance panel end-to-end.
 *
 * Tabs:
 *   DSR            — Data Subject Requests (erasure/portability/rectification/restriction)
 *                    with SLA deadline indicator, execute erasure, portability download,
 *                    status filter.
 *   Consentimiento — Full consent list, toggle per-user, per-user audit history.
 *   Máscaras       — Field-level masking rules (hash/redact/partial/suppress/pseudonymize).
 *   Estadísticas   — KPI dashboard: pending DSRs, SLA overdue, consent totals, type breakdown.
 */
import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { biGdprApi } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import {
  Shield, AlertTriangle, CheckCircle, Download, Trash2,
  Clock, Users, ToggleLeft, ToggleRight,
} from 'lucide-react'

// ── Styles ────────────────────────────────────────────────────────────────────
const S = {
  card:     { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14, padding: '20px 24px' },
  innerCard:{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '14px 16px' },
  input:    { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", fontFamily: 'inherit', outline: 'none', width: '100%', boxSizing: 'border-box' },
  select:   { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", fontFamily: 'inherit', outline: 'none', width: '100%' },
  btn:      { padding: '7px 16px', borderRadius: 8, background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit' },
  btnRed:   { padding: '6px 12px', borderRadius: 8, background: 'var(--danger)', color: '#fff', border: 'none', cursor: 'pointer', fontSize: "var(--text-xs)", fontWeight: 600, fontFamily: 'inherit' },
  btnGreen: { padding: '6px 12px', borderRadius: 8, background: 'var(--success)', color: '#fff', border: 'none', cursor: 'pointer', fontSize: "var(--text-xs)", fontWeight: 600, fontFamily: 'inherit' },
  btnGhost: { padding: '6px 12px', borderRadius: 8, background: 'transparent', color: 'var(--accent)', border: '1px solid var(--accent-border)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' },
  row:      { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10 },
  badge:    (color) => ({ fontSize: "var(--text-xs)", padding: '2px 8px', borderRadius: 10, fontWeight: 600, background: `color-mix(in srgb, ${color} 13%, transparent)`, color }),
  sectionTitle: { fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 10 },
}

const TYPE_COLOR  = { erasure: 'var(--danger)', portability: 'var(--accent)', rectification: 'var(--warning)', restriction: 'var(--purple)' }
const STATUS_COLOR= { pending: 'var(--warning)', completed: 'var(--success)', rejected: 'var(--danger)' }

function fmt(iso) {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' }) }
  catch { return iso }
}

function isOverdue(dsr) {
  if (dsr.status !== 'pending') return false
  const dl = dsr.deadline ? new Date(dsr.deadline) : new Date(new Date(dsr.created_at).getTime() + 30 * 864e5)
  return Date.now() > dl.getTime()
}

// ── KPI card ──────────────────────────────────────────────────────────────────
function StatCard({ icon, label, value, color = 'var(--accent)' }) {
  return (
    <div style={{ ...S.innerCard, display: 'flex', alignItems: 'center', gap: 14, padding: '16px 20px', flex: 1, minWidth: 130 }}>
      <div style={{ width: 36, height: 36, borderRadius: 10, background: `color-mix(in srgb, ${color} 13%, transparent)`, display: 'flex', alignItems: 'center', justifyContent: 'center', color, flexShrink: 0 }}>
        {icon}
      </div>
      <div>
        <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, color: 'var(--text-1)', lineHeight: 1 }}>{value ?? '—'}</div>
        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 2 }}>{label}</div>
      </div>
    </div>
  )
}

// ── Tab DSR ───────────────────────────────────────────────────────────────────
function DsrTab() {
  const t  = useAppT()
  const qc = useQueryClient()
  const [form, setForm]         = useState({ user_id: '', request_type: 'erasure', notes: '' })
  const [statusFilter, setFilter] = useState('')
  const [expandedId, setExpanded] = useState(null)

  const { data, isLoading } = useQuery({
    queryKey: ['bi-gdpr-dsr', statusFilter],
    queryFn:  () => biGdprApi.listDsr(statusFilter ? { status: statusFilter } : {}).then(r => r.data),
  })

  const createMut = useMutation({
    mutationFn: (p) => biGdprApi.createDsr(p).then(r => r.data),
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: ['bi-gdpr-dsr'] })
      qc.invalidateQueries({ queryKey: ['bi-gdpr-stats'] })
      setForm({ user_id: '', request_type: 'erasure', notes: '' })
    },
  })
  const resolveMut = useMutation({
    mutationFn: (id) => biGdprApi.resolveDsr(id, { resolution_notes: 'Resolved manually' }).then(r => r.data),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['bi-gdpr-dsr'] }); qc.invalidateQueries({ queryKey: ['bi-gdpr-stats'] }) },
  })
  const erasureMut = useMutation({
    mutationFn: (id) => biGdprApi.executeDsrErasure(id).then(r => r.data),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['bi-gdpr-dsr'] }); qc.invalidateQueries({ queryKey: ['bi-gdpr-stats'] }) },
  })
  const portMut = useMutation({
    mutationFn: (id) => biGdprApi.executeDsrPortability(id).then(r => r.data),
    onSuccess:  (data) => {
      qc.invalidateQueries({ queryKey: ['bi-gdpr-dsr'] })
      const blob = new Blob([JSON.stringify(data.export, null, 2)], { type: 'application/json' })
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href = url; a.download = `portability-${data.dsr_id}.json`; a.click()
      URL.revokeObjectURL(url)
    },
  })

  const dsrs = data?.items ?? []

  return (
    <div>
      {/* Create form */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 160px 1fr auto', gap: 8, marginBottom: 16 }}>
        <input placeholder="subject-id o email" value={form.user_id} onChange={e => setForm(f => ({ ...f, user_id: e.target.value }))} style={S.input} />
        <select value={form.request_type} onChange={e => setForm(f => ({ ...f, request_type: e.target.value }))} style={S.select}>
          {['erasure', 'portability', 'rectification', 'restriction'].map(rt => <option key={rt} value={rt}>{rt}</option>)}
        </select>
        <input placeholder="Notas (opcional)" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} style={S.input} />
        <button onClick={() => createMut.mutate({ user_id: form.user_id, request_type: form.request_type, notes: form.notes || undefined })}
          disabled={createMut.isPending || !form.user_id}
          style={{ ...S.btn, opacity: (createMut.isPending || !form.user_id) ? 0.5 : 1 }}>
          {t('bi.gdpr.create_dsr', 'Nueva DSR')}
        </button>
      </div>

      {/* Status filter */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
        {['', 'pending', 'completed'].map(s => (
          <button key={s} onClick={() => setFilter(s)} style={{
            ...S.btnGhost,
            background: statusFilter === s ? 'var(--accent)' : undefined,
            color: statusFilter === s ? '#fff' : undefined,
            borderColor: statusFilter === s ? 'var(--accent)' : undefined,
          }}>
            {s || 'Todos'}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', padding: '20px 0', textAlign: 'center' }}>Cargando…</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {dsrs.map(dsr => {
            const overdue  = isOverdue(dsr)
            const expanded = expandedId === dsr.id
            return (
              <div key={dsr.id} style={{ ...S.innerCard }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)' }}>{dsr.subject_id ?? dsr.user_id}</span>
                      <span style={S.badge(TYPE_COLOR[dsr.request_type] ?? 'var(--text-3)')}>{dsr.request_type}</span>
                      <span style={S.badge(STATUS_COLOR[dsr.status] ?? 'var(--text-3)')}>{dsr.status}</span>
                      {overdue && <span style={S.badge('var(--danger)')}><AlertTriangle size={10} style={{ verticalAlign: 'middle', marginRight: 2 }} />SLA vencido</span>}
                    </div>
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 3, display: 'flex', gap: 12 }}>
                      <span>Creado: {fmt(dsr.created_at)}</span>
                      {dsr.deadline && <span>Límite: {fmt(dsr.deadline)}</span>}
                      {dsr.resolved_at && <span>Resuelto: {fmt(dsr.resolved_at)}</span>}
                    </div>
                    {dsr.notes && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 2 }}>{dsr.notes}</div>}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                    {dsr.status === 'pending' && (
                      <>
                        {dsr.request_type === 'erasure' && (
                          <button onClick={() => { if (window.confirm('¿Ejecutar borrado irreversible de datos PII?')) erasureMut.mutate(dsr.id) }}
                            disabled={erasureMut.isPending} style={{ ...S.btnRed, opacity: erasureMut.isPending ? 0.5 : 1 }}>
                            <Trash2 size={11} style={{ verticalAlign: 'middle' }} /> Borrar PII
                          </button>
                        )}
                        {dsr.request_type === 'portability' && (
                          <button onClick={() => portMut.mutate(dsr.id)} disabled={portMut.isPending}
                            style={{ ...S.btn, opacity: portMut.isPending ? 0.5 : 1 }}>
                            <Download size={11} style={{ verticalAlign: 'middle' }} /> Export
                          </button>
                        )}
                        <button onClick={() => resolveMut.mutate(dsr.id)} disabled={resolveMut.isPending}
                          style={{ ...S.btnGreen, opacity: resolveMut.isPending ? 0.5 : 1 }}>
                          <CheckCircle size={11} style={{ verticalAlign: 'middle' }} /> Resolver
                        </button>
                      </>
                    )}
                    {dsr.erasure_report && (
                      <button onClick={() => setExpanded(expanded ? null : dsr.id)} style={{ ...S.btnGhost, padding: '4px 8px' }}>
                        {expanded ? '▲' : '▼'}
                      </button>
                    )}
                  </div>
                </div>
                {expanded && dsr.erasure_report && (
                  <div style={{ marginTop: 10, background: 'var(--surface-4)', borderRadius: 8, padding: '10px 12px', fontSize: "var(--text-xs)", fontFamily: 'var(--font-mono)', color: 'var(--text-2)', overflowX: 'auto' }}>
                    <pre style={{ margin: 0 }}>{JSON.stringify(dsr.erasure_report, null, 2)}</pre>
                  </div>
                )}
              </div>
            )
          })}
          {!dsrs.length && (
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', textAlign: 'center', padding: '24px 0' }}>
              {t('bi.gdpr.no_dsr', 'No hay solicitudes')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Tab Consent ───────────────────────────────────────────────────────────────
function ConsentTab() {
  const t  = useAppT()
  const qc = useQueryClient()
  const [form, setForm]         = useState({ user_id: '', purpose: 'analytics', channel: 'web' })
  const [histUserId, setHistUser] = useState(null)

  const { data: consentsData, isLoading } = useQuery({
    queryKey: ['bi-gdpr-consents'],
    queryFn:  () => biGdprApi.listConsents().then(r => r.data),
  })

  const { data: historyData } = useQuery({
    queryKey: ['bi-gdpr-consent-history', histUserId],
    queryFn:  () => biGdprApi.getConsentHistory(histUserId).then(r => r.data),
    enabled:  !!histUserId,
  })

  const toggleMut = useMutation({
    mutationFn: ({ userId, consented }) => biGdprApi.recordConsent({ user_id: userId, granted: consented, purpose: 'analytics', channel: 'web' }).then(r => r.data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['bi-gdpr-consents'] }),
  })

  const addMut = useMutation({
    mutationFn: (p) => biGdprApi.recordConsent({ user_id: p.user_id, granted: true, purpose: p.purpose, channel: p.channel }).then(r => r.data),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['bi-gdpr-consents'] }); setForm({ user_id: '', purpose: 'analytics', channel: 'web' }) },
  })

  const consents = consentsData?.items ?? []

  return (
    <div>
      {/* Add form */}
      <div style={{ ...S.innerCard, marginBottom: 16 }}>
        <div style={{ ...S.sectionTitle }}>Registrar consentimiento</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 130px 130px auto', gap: 8 }}>
          <input placeholder="user-id o email" value={form.user_id} onChange={e => setForm(f => ({ ...f, user_id: e.target.value }))} style={S.input} />
          <select value={form.purpose} onChange={e => setForm(f => ({ ...f, purpose: e.target.value }))} style={S.select}>
            {['analytics', 'marketing', 'profiling', 'research'].map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <select value={form.channel} onChange={e => setForm(f => ({ ...f, channel: e.target.value }))} style={S.select}>
            {['web', 'email', 'api', 'mobile'].map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <button onClick={() => addMut.mutate(form)} disabled={addMut.isPending || !form.user_id}
            style={{ ...S.btn, opacity: (addMut.isPending || !form.user_id) ? 0.5 : 1 }}>
            {t('bi.gdpr.add_consent', 'Añadir')}
          </button>
        </div>
      </div>

      {isLoading ? (
        <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', padding: '20px 0', textAlign: 'center' }}>Cargando…</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {consents.map((c, i) => (
            <div key={c.user_id ?? i} style={S.row}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)' }}>{c.user_id}</div>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 2 }}>
                  {c.purpose && <span style={{ marginRight: 8 }}>{c.purpose}</span>}
                  {c.channel && <span style={{ marginRight: 8 }}>{c.channel}</span>}
                  {c.updated_at && <span>Actualizado: {fmt(c.updated_at)}</span>}
                </div>
              </div>
              <span style={S.badge(c.consented ? 'var(--success)' : 'var(--danger)')}>{c.consented ? 'concedido' : 'revocado'}</span>
              <button onClick={() => toggleMut.mutate({ userId: c.user_id, consented: !c.consented })} disabled={toggleMut.isPending}
                title={c.consented ? 'Revocar' : 'Conceder'}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: c.consented ? 'var(--danger)' : 'var(--success)', padding: 4, display: 'flex' }}>
                {c.consented ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
              </button>
              <button onClick={() => setHistUser(histUserId === c.user_id ? null : c.user_id)}
                title="Ver historial"
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', padding: 4, display: 'flex' }}>
                <Clock size={14} />
              </button>
            </div>
          ))}
          {!consents.length && (
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', textAlign: 'center', padding: '24px 0' }}>
              {t('bi.gdpr.no_consents', 'No hay registros de consentimiento')}
            </div>
          )}
        </div>
      )}

      {/* History panel */}
      {histUserId && historyData && (
        <div style={{ ...S.innerCard, marginTop: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)' }}>
              Historial — {histUserId}
            </span>
            <button onClick={() => setHistUser(null)} style={{ ...S.btnGhost, padding: '3px 8px' }}>✕</button>
          </div>
          {!(historyData.history?.length) ? (
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>Sin historial</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {historyData.history.map((h, idx) => (
                <div key={idx} style={{ display: 'flex', gap: 12, fontSize: "var(--text-xs)", color: 'var(--text-2)', padding: '4px 0', borderBottom: '1px solid var(--surface-4)' }}>
                  <span style={{ color: h.action === 'granted' ? 'var(--success)' : 'var(--danger)', fontWeight: 700, width: 60 }}>{h.action}</span>
                  <span>{h.purpose}</span>
                  <span>{h.channel}</span>
                  <span style={{ marginLeft: 'auto', color: 'var(--text-3)' }}>{fmt(h.timestamp)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Tab Masks ─────────────────────────────────────────────────────────────────
function MasksTab() {
  const t  = useAppT()
  const qc = useQueryClient()
  const [form, setForm] = useState({ entity: 'user', field: 'email', mask_type: 'hash' })

  const { data: masksData } = useQuery({
    queryKey: ['bi-gdpr-masks'],
    queryFn:  () => biGdprApi.getFieldMasks().then(r => r.data),
  })

  const addMut = useMutation({
    mutationFn: (p) => biGdprApi.setFieldMask(p).then(r => r.data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['bi-gdpr-masks'] }),
  })

  const MASK_COLOR = { hash: 'var(--accent)', redact: 'var(--danger)', partial: 'var(--warning)', suppress: 'var(--purple)', pseudonymize: 'var(--info)' }

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 160px auto', gap: 8, marginBottom: 16 }}>
        <input placeholder="entidad (ej: user)" value={form.entity} onChange={e => setForm(f => ({ ...f, entity: e.target.value }))} style={S.input} />
        <input placeholder="campo (ej: email)" value={form.field} onChange={e => setForm(f => ({ ...f, field: e.target.value }))} style={S.input} />
        <select value={form.mask_type} onChange={e => setForm(f => ({ ...f, mask_type: e.target.value }))} style={S.select}>
          {['hash', 'redact', 'partial', 'suppress', 'pseudonymize'].map(mt => <option key={mt} value={mt}>{mt}</option>)}
        </select>
        <button onClick={() => addMut.mutate(form)} disabled={addMut.isPending || !form.field}
          style={{ ...S.btn, opacity: (addMut.isPending || !form.field) ? 0.5 : 1 }}>
          {t('bi.gdpr.add_mask', 'Añadir máscara')}
        </button>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {(masksData?.items ?? []).map((m, i) => (
          <div key={i} style={{ ...S.row, justifyContent: 'space-between' }}>
            <span style={{ fontSize: "var(--text-sm)", fontFamily: 'var(--font-mono)', color: 'var(--text-1)' }}>{m.dataset ?? m.entity}.{m.field}</span>
            <span style={S.badge(MASK_COLOR[m.mask_type] ?? 'var(--text-3)')}>{m.mask_type}</span>
            <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginLeft: 'auto' }}>{fmt(m.updated_at)}</span>
          </div>
        ))}
        {!(masksData?.items?.length) && (
          <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', textAlign: 'center', padding: '24px 0' }}>
            {t('bi.gdpr.no_masks', 'No hay máscaras configuradas')}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Tab Stats ─────────────────────────────────────────────────────────────────
function StatsTab() {
  const { data, isLoading } = useQuery({
    queryKey: ['bi-gdpr-stats'],
    queryFn:  () => biGdprApi.getStats().then(r => r.data),
    refetchInterval: 60_000,
  })

  const byType = useMemo(() => {
    if (!data?.by_type) return []
    return Object.entries(data.by_type).map(([type, count]) => ({ type, count }))
  }, [data])

  if (isLoading) return <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', padding: '20px 0', textAlign: 'center' }}>Cargando estadísticas…</div>

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
        <StatCard icon={<Clock size={18} />}         label="DSRs pendientes" value={data?.pending}   color="var(--warning)" />
        <StatCard icon={<AlertTriangle size={18} />} label="SLA vencidos"    value={data?.overdue}   color="var(--danger)" />
        <StatCard icon={<CheckCircle size={18} />}   label="Completadas"     value={data?.completed} color="var(--success)" />
        <StatCard icon={<Users size={18} />}         label="Consentidos"     value={data?.consented} color="var(--accent)" />
        <StatCard icon={<Shield size={18} />}        label="Revocados"       value={data?.revoked}   color="var(--purple)" />
      </div>

      {byType.length > 0 && (
        <div style={{ ...S.innerCard, marginBottom: 12 }}>
          <div style={S.sectionTitle}>DSRs por tipo</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {byType.map(({ type, count }) => (
              <div key={type} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ ...S.badge(TYPE_COLOR[type] ?? 'var(--text-3)'), minWidth: 110, display: 'inline-block' }}>{type}</span>
                <div style={{ flex: 1, height: 8, background: 'var(--surface-4)', borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${Math.min(100, (count / (data?.total_dsrs || 1)) * 100)}%`, background: TYPE_COLOR[type] ?? 'var(--accent)', borderRadius: 4 }} />
                </div>
                <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-1)', minWidth: 24, textAlign: 'right' }}>{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {data?.overdue > 0 && (
        <div style={{ ...S.innerCard, borderColor: 'var(--danger-border)' }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--danger)', marginBottom: 6 }}>
            <AlertTriangle size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} />
            {data.overdue} DSR{data.overdue !== 1 ? 's' : ''} ha{data.overdue !== 1 ? 'n' : ''} superado el plazo GDPR (30 días)
          </div>
          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
            {(data.overdue_ids ?? []).join(', ')}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main ───────────────────────────────────────────────────────────────────────
export default function BiGdprPanel() {
  const t   = useAppT()
  const [tab, setTab] = useState('dsr')

  const TAB_NAV = [
    { id: 'dsr',     label: 'DSR' },
    { id: 'consent', label: t('bi.gdpr.consent', 'Consentimiento') },
    { id: 'masks',   label: t('bi.gdpr.masks', 'Máscaras') },
    { id: 'stats',   label: t('bi.gdpr.stats', 'Estadísticas') },
  ]

  return (
    <div style={S.card}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: 'color-mix(in srgb, var(--accent) 12%, transparent)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)' }}>
          <Shield size={16} />
        </div>
        <h3 style={{ margin: 0, fontSize: "var(--text-md-em)", fontWeight: 700, color: 'var(--text-1)' }}>
          {t('bi.gdpr.title', 'Cumplimiento GDPR')}
        </h3>
      </div>

      <div style={{ display: 'flex', gap: 2, borderBottom: '1px solid var(--surface-4)', marginBottom: 20 }}>
        {TAB_NAV.map(({ id, label }) => (
          <button key={id} onClick={() => setTab(id)} style={{
            padding: '8px 16px', fontSize: "var(--text-sm)", fontWeight: tab === id ? 700 : 400,
            color: tab === id ? 'var(--accent)' : 'var(--text-2)',
            background: 'transparent', border: 'none',
            borderBottom: `2px solid ${tab === id ? 'var(--accent)' : 'transparent'}`,
            cursor: 'pointer', fontFamily: 'inherit', marginBottom: -1,
          }}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'dsr'     && <DsrTab />}
      {tab === 'consent' && <ConsentTab />}
      {tab === 'masks'   && <MasksTab />}
      {tab === 'stats'   && <StatsTab />}
    </div>
  )
}
