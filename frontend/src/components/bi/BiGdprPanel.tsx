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
import React, { useState, useMemo } from 'react'
import type { CSSProperties } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { biGdprApi } from '../../services/api'
import type { ConsentimientoBi, InformeDeBorradoRgpd, SolicitudDsr } from '../../services/api/tipos-bi'
import { useAppT } from '../../i18n/AppLangContext'
import { useConfirm } from '../../context/ConfirmContext'
import {
  Shield, AlertTriangle, CheckCircle, Download, Trash2,
  Clock, Users, ToggleLeft, ToggleRight,
} from 'lucide-react'
import { localeActivo } from '../../utils/helpers'
import useMediaQuery from '../../hooks/useMediaQuery'
import { POLL_DEFAULT_MS } from '../../constants/timings'
import './BiGdprPanel.css'

// ── Styles ────────────────────────────────────────────────────────────────────
const S = {
  card:     { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-lg)', padding: '20px 24px' } as CSSProperties,
  innerCard:{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: '14px 16px' } as CSSProperties,
  input:    { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", fontFamily: 'inherit', outline: 'none', width: '100%', boxSizing: 'border-box' } as CSSProperties,
  select:   { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", fontFamily: 'inherit', outline: 'none', width: '100%' } as CSSProperties,
  btn:      { padding: '7px 16px', borderRadius: 8, background: 'var(--accent)', color: 'var(--on-accent)', border: 'none', cursor: 'pointer', fontSize: "var(--text-sm)", fontWeight: 600, fontFamily: 'inherit' } as CSSProperties,
  btnRed:   { padding: '6px 12px', borderRadius: 8, background: 'var(--danger)', color: 'var(--on-accent-light)', border: 'none', cursor: 'pointer', fontSize: "var(--text-xs)", fontWeight: 600, fontFamily: 'inherit' } as CSSProperties,
  btnGreen: { padding: '6px 12px', borderRadius: 8, background: 'var(--success)', color: 'var(--on-accent-light)', border: 'none', cursor: 'pointer', fontSize: "var(--text-xs)", fontWeight: 600, fontFamily: 'inherit' } as CSSProperties,
  btnGhost: { padding: '6px 12px', borderRadius: 8, background: 'transparent', color: 'var(--accent)', border: '1px solid var(--accent-border)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' } as CSSProperties,
  row:      { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10 } as CSSProperties,
  badge:    (color: string): CSSProperties => ({ fontSize: "var(--text-xs)", padding: '2px 8px', borderRadius: 'var(--radius-md)', fontWeight: 600, background: `color-mix(in srgb, ${color} 13%, transparent)`, color }),
  sectionTitle: { fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 10 } as CSSProperties,
}

const TYPE_COLOR: Record<string, string>  = { erasure: 'var(--danger)', portability: 'var(--accent)', rectification: 'var(--warning)', restriction: 'var(--purple)' }
const STATUS_COLOR: Record<string, string>= { pending: 'var(--warning)', completed: 'var(--success)', rejected: 'var(--danger)' }

function fmt(iso?: string): string {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleDateString(localeActivo(), { day: '2-digit', month: 'short', year: 'numeric' }) }
  catch { return iso }
}

function isOverdue(dsr: SolicitudDsr): boolean {
  if (dsr.status !== 'pending') return false
  // El servidor fija `deadline` al crearla (COMPLIANCE_GDPR_MAX_DAYS): sin plazo en duro aquí.
  return Date.now() > new Date(dsr.deadline).getTime()
}

// ── KPI card ──────────────────────────────────────────────────────────────────
interface StatCardProps {
  icon: React.ReactNode
  label: string
  value?: number | string | null
  color?: string
}

function StatCard({ icon, label, value, color = 'var(--accent)' }: StatCardProps) {
  return (
    <div style={{ ...S.innerCard, display: 'flex', alignItems: 'center', gap: 14, padding: '16px 20px', flex: 1, minWidth: 130 }}>
      <div className="bigdpa-row-11" style={{ background: `color-mix(in srgb, ${color} 13%, transparent)`, color }}>
        {icon}
      </div>
      <div>
        <div className="bigdpa-txt-1">{value ?? '—'}</div>
        <div className="u-text3-xs-mt2">{label}</div>
      </div>
    </div>
  )
}

// ── Tab DSR ───────────────────────────────────────────────────────────────────
interface DsrForm {
  user_id: string
  request_type: string
  notes: string
}

function DsrTab() {
  const t  = useAppT()
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const qc = useQueryClient()
  const { confirmar } = useConfirm()
  const [form, setForm]         = useState<DsrForm>({ user_id: '', request_type: 'erasure', notes: '' })
  const [statusFilter, setFilter] = useState<string>('')
  const [expandedId, setExpanded] = useState<string | null>(null)
  // `erasure-execute` devuelve el informe pero no lo guarda en la solicitud: se conserva aquí.
  const [informes, setInformes] = useState<Record<string, InformeDeBorradoRgpd>>({})

  const { data: dsrs = [], isLoading } = useQuery({
    queryKey: ['bi-gdpr-dsr', statusFilter],
    queryFn:  () => biGdprApi.listDsr(statusFilter ? { status: statusFilter } : {}).then(r => r.data),
  })

  const createMut = useMutation({
    mutationFn: (p: DsrForm) => biGdprApi.createDsr(p).then(r => r.data),
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: ['bi-gdpr-dsr'] })
      qc.invalidateQueries({ queryKey: ['bi-gdpr-stats'] })
      setForm({ user_id: '', request_type: 'erasure', notes: '' })
    },
  })
  const resolveMut = useMutation({
    mutationFn: (id: string) => biGdprApi.resolveDsr(id, { resolution_notes: 'Resolved manually' }).then(r => r.data),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['bi-gdpr-dsr'] }); qc.invalidateQueries({ queryKey: ['bi-gdpr-stats'] }) },
  })
  const erasureMut = useMutation({
    mutationFn: (id: string) => biGdprApi.executeDsrErasure(id).then(r => r.data),
    onSuccess:  (data) => { setInformes(x => ({ ...x, [data.dsr_id]: data.erasure_report })); setExpanded(data.dsr_id); qc.invalidateQueries({ queryKey: ['bi-gdpr-dsr'] }); qc.invalidateQueries({ queryKey: ['bi-gdpr-stats'] }) },
  })
  const portMut = useMutation({
    mutationFn: (id: string) => biGdprApi.executeDsrPortability(id).then(r => r.data),
    onSuccess:  (data) => {
      qc.invalidateQueries({ queryKey: ['bi-gdpr-dsr'] })
      const blob = new Blob([JSON.stringify(data.export, null, 2)], { type: 'application/json' })
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href = url; a.download = `portability-${data.dsr_id}.json`; a.click()
      URL.revokeObjectURL(url)
    },
  })

  return (
    <div>
      {/* Create form */}
      <div className="bigdpa-grid-1" style={{ gridTemplateColumns: isNarrow ? 'minmax(0, 1fr)' : '1fr 160px 1fr auto' }}>
        <input aria-label="subject-id o email" placeholder="subject-id o email" value={form.user_id} onChange={e => setForm(f => ({ ...f, user_id: e.target.value }))} style={S.input} />
        <select value={form.request_type} onChange={e => setForm(f => ({ ...f, request_type: e.target.value }))} style={S.select}>
          {['erasure', 'portability', 'rectification', 'restriction'].map(rt => <option key={rt} value={rt}>{rt}</option>)}
        </select>
        <input aria-label="Notas (opcional)" placeholder="Notas (opcional)" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} style={S.input} />
        <button onClick={() => createMut.mutate({ user_id: form.user_id, request_type: form.request_type, notes: form.notes || '' })}
          disabled={createMut.isPending || !form.user_id}
          style={{ ...S.btn, opacity: (createMut.isPending || !form.user_id) ? 0.5 : 1 }}>
          {t('bi.gdpr.create_dsr', 'Nueva DSR')}
        </button>
      </div>

      {/* Status filter */}
      <div className="bigdpa-row-1">
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
        <div className="bigdpa-box-1">Cargando…</div>
      ) : (
        <div className="u-stack-6">
          {dsrs.map((dsr) => {
            const overdue  = isOverdue(dsr)
            const expanded = expandedId === dsr.id
            const informe  = dsr.erasure_report ?? informes[dsr.id]
            return (
              <div key={dsr.id} style={{ ...S.innerCard }}>
                <div className="bigdpa-row-12" style={{ flexWrap: isNarrow ? 'wrap' : undefined }}>
                  <div className="u-flex1-min0">
                    <div className="u-wrap-center-8">
                      <span className="u-text1-base-600">{dsr.subject_id}</span>
                      <span style={S.badge(TYPE_COLOR[dsr.request_type] ?? 'var(--text-3)')}>{dsr.request_type}</span>
                      <span style={S.badge(STATUS_COLOR[dsr.status] ?? 'var(--text-3)')}>{dsr.status}</span>
                      {overdue && <span style={S.badge('var(--danger)')}><AlertTriangle size={10} style={{ verticalAlign: 'middle', marginRight: 2 }} />SLA vencido</span>}
                    </div>
                    <div className="bigdpa-row-2">
                      <span>Creado: {fmt(dsr.created_at)}</span>
                      {dsr.deadline && <span>{t('bigdpr.limite')} {fmt(dsr.deadline)}</span>}
                      {dsr.resolved_at && <span>Resuelto: {fmt(dsr.resolved_at)}</span>}
                    </div>
                    {dsr.notes && <div className="u-text3-xs-mt2">{dsr.notes}</div>}
                  </div>
                  <div className="bigdpa-row-3">
                    {dsr.status === 'pending' && (
                      <>
                        {dsr.request_type === 'erasure' && (
                          <button onClick={async () => {
                              const ok = await confirmar({
                                title: 'Borrado irreversible de datos personales',
                                message: `Se borrarán de forma permanente los datos PII del usuario ${dsr.subject_id}. Esta acción no se puede deshacer.`,
                                danger: true,
                                confirmLabel: 'Borrar PII',
                                palabraConfirmacion: 'BORRAR',
                              })
                              if (ok) erasureMut.mutate(dsr.id)
                            }}
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
                    {informe ? (
                      <button onClick={() => setExpanded(expanded ? null : dsr.id)} style={{ ...S.btnGhost, padding: '4px 8px' }}>
                        {expanded ? '▲' : '▼'}
                      </button>
                    ) : null}
                  </div>
                </div>
                {expanded && informe ? (
                  <div className="bigdpa-box-2">
                    <pre className="bigdpa-sp-1">{JSON.stringify(informe, null, 2)}</pre>
                  </div>
                ) : null}
              </div>
            )
          })}
          {!dsrs.length && (
            <div className="bigdpa-box-3">
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
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const qc = useQueryClient()
  const [form, setForm]         = useState<{ user_id: string; purpose: string; channel: string }>({ user_id: '', purpose: 'analytics', channel: 'web' })
  const [histUserId, setHistUser] = useState<string | null>(null)

  const { data: consents = [], isLoading } = useQuery({
    queryKey: ['bi-gdpr-consents'],
    queryFn:  () => biGdprApi.listConsents().then(r => r.data),
  })

  const { data: historyData } = useQuery({
    queryKey: ['bi-gdpr-consent-history', histUserId],
    queryFn:  () => biGdprApi.getConsentHistory(histUserId).then(r => r.data),
    enabled:  !!histUserId,
  })

  const toggleMut = useMutation({
    // El consentimiento es por usuario y finalidad: se cambia el de la fila, no siempre `analytics`.
    mutationFn: ({ c, consented }: { c: ConsentimientoBi; consented: boolean }) => biGdprApi.recordConsent({ user_id: c.user_id, granted: consented, purpose: c.purpose, channel: c.channel }).then(r => r.data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['bi-gdpr-consents'] }),
  })

  const addMut = useMutation({
    mutationFn: (p: { user_id: string; purpose: string; channel: string }) => biGdprApi.recordConsent({ user_id: p.user_id, granted: true, purpose: p.purpose, channel: p.channel }).then(r => r.data),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['bi-gdpr-consents'] }); setForm({ user_id: '', purpose: 'analytics', channel: 'web' }) },
  })

  return (
    <div>
      {/* Add form */}
      <div style={{ ...S.innerCard, marginBottom: 16 }}>
        <div style={{ ...S.sectionTitle }}>Registrar consentimiento</div>
        <div className="bigdpa-grid-2" style={{ gridTemplateColumns: isNarrow ? 'minmax(0, 1fr)' : '1fr 130px 130px auto' }}>
          <input aria-label="user-id o email" placeholder="user-id o email" value={form.user_id} onChange={e => setForm(f => ({ ...f, user_id: e.target.value }))} style={S.input} />
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
        <div className="bigdpa-box-1">Cargando…</div>
      ) : (
        <div className="u-stack-6">
          {consents.map((c) => (
            <div key={`${c.user_id}:${c.purpose}`} style={S.row}>
              <div className="u-flex1-min0">
                <div className="u-text1-base-600">{c.user_id}</div>
                <div className="u-text3-xs-mt2">
                  {c.purpose && <span className="bigdpa-sp-2">{c.purpose}</span>}
                  {c.channel && <span className="bigdpa-sp-2">{c.channel}</span>}
                  {c.updated_at && <span>Actualizado: {fmt(c.updated_at)}</span>}
                </div>
              </div>
              <span style={S.badge(c.consented ? 'var(--success)' : 'var(--danger)')}>{c.consented ? 'concedido' : 'revocado'}</span>
              <button className="bigdpa-row-13" onClick={() => toggleMut.mutate({ c, consented: !c.consented })} disabled={toggleMut.isPending}
                title={c.consented ? 'Revocar' : 'Conceder'}
                style={{ color: c.consented ? 'var(--danger)' : 'var(--success)' }}>
                {c.consented ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
              </button>
              <button aria-label="Ver historial" onClick={() => setHistUser(histUserId === c.user_id ? null : c.user_id)}
                title="Ver historial"
                className="bigdpa-row-4">
                <Clock size={14} />
              </button>
            </div>
          ))}
          {!consents.length && (
            <div className="bigdpa-box-3">
              {t('bi.gdpr.no_consents', 'No hay registros de consentimiento')}
            </div>
          )}
        </div>
      )}

      {/* History panel */}
      {histUserId && historyData && (
        <div style={{ ...S.innerCard, marginTop: 16 }}>
          <div className="bigdpa-row-5">
            <span className="bigdpa-txt-2">
              Historial — {histUserId}
            </span>
            <button onClick={() => setHistUser(null)} style={{ ...S.btnGhost, padding: '3px 8px' }}>✕</button>
          </div>
          {!historyData.history.length ? (
            <div className="u-text3-sm">{t('bigdpr.sin_historial')}</div>
          ) : (
            <div className="bigdpa-stack-1">
              {historyData.history.map((h, idx) => (
                <div key={idx} className="bigdpa-row-6">
                  <span className="bigdpa-box-10" style={{ color: h.action === 'granted' ? 'var(--success)' : 'var(--danger)' }}>{h.action}</span>
                  <span>{h.purpose}</span>
                  <span>{h.channel}</span>
                  <span className="bigdpa-box-4">{fmt(h.timestamp)}</span>
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
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const qc = useQueryClient()
  const [form, setForm] = useState<{ entity: string; field: string; mask_type: string }>({ entity: 'user', field: 'email', mask_type: 'hash' })

  const { data: masks = [] } = useQuery({
    queryKey: ['bi-gdpr-masks'],
    queryFn:  () => biGdprApi.getFieldMasks().then(r => r.data),
  })

  const addMut = useMutation({
    mutationFn: (p: { entity: string; field: string; mask_type: string }) => biGdprApi.setFieldMask(p).then(r => r.data),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['bi-gdpr-masks'] }),
  })

  const MASK_COLOR: Record<string, string> = { hash: 'var(--accent)', redact: 'var(--danger)', partial: 'var(--warning)', suppress: 'var(--purple)', pseudonymize: 'var(--info)' }

  return (
    <div>
      <div className="bigdpa-grid-1" style={{ gridTemplateColumns: isNarrow ? 'minmax(0, 1fr)' : '1fr 1fr 160px auto' }}>
        <input aria-label="entidad (ej: user)" placeholder="entidad (ej: user)" value={form.entity} onChange={e => setForm(f => ({ ...f, entity: e.target.value }))} style={S.input} />
        <input aria-label="campo (ej: email)" placeholder="campo (ej: email)" value={form.field} onChange={e => setForm(f => ({ ...f, field: e.target.value }))} style={S.input} />
        <select value={form.mask_type} onChange={e => setForm(f => ({ ...f, mask_type: e.target.value }))} style={S.select}>
          {['hash', 'redact', 'suppress', 'pseudonymize'].map(mt => <option key={mt} value={mt}>{mt}</option>)}
        </select>
        <button onClick={() => addMut.mutate(form)} disabled={addMut.isPending || !form.field}
          style={{ ...S.btn, opacity: (addMut.isPending || !form.field) ? 0.5 : 1 }}>
          {t('bi.gdpr.add_mask', 'Añadir máscara')}
        </button>
      </div>
      <div className="u-stack-6">
        {masks.map((m, i) => (
          <div key={i} style={{ ...S.row, justifyContent: 'space-between', flexWrap: 'wrap' }}>
            <span className="bigdpa-txt-3">{m.dataset}.{m.field}</span>
            <span style={S.badge(MASK_COLOR[m.mask_type] ?? 'var(--text-3)')}>{m.mask_type}</span>
            <span className="bigdpa-box-5">{fmt(m.updated_at)}</span>
          </div>
        ))}
        {!masks.length && (
          <div className="bigdpa-box-3">
            {t('bi.gdpr.no_masks', 'No hay máscaras configuradas')}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Tab Stats ─────────────────────────────────────────────────────────────────
function StatsTab() {
  const t = useAppT()
  const { data, isLoading } = useQuery({
    queryKey: ['bi-gdpr-stats'],
    queryFn:  () => biGdprApi.getStats().then(r => r.data),
    refetchInterval: POLL_DEFAULT_MS,
  })

  const byType = useMemo(() => {
    if (!data?.by_type) return []
    return Object.entries(data.by_type).map(([type, count]) => ({ type, count }))
  }, [data])

  if (isLoading) return <div className="bigdpa-box-1">{t('bigdpr.cargando_estadisticas')}</div>

  return (
    <div>
      <div className="bigdpa-row-7">
        <StatCard icon={<Clock size={18} />}         label="DSRs pendientes" value={data?.pending}   color="var(--warning)" />
        <StatCard icon={<AlertTriangle size={18} />} label="SLA vencidos"    value={data?.overdue}   color="var(--danger)" />
        <StatCard icon={<CheckCircle size={18} />}   label="Completadas"     value={data?.completed} color="var(--success)" />
        <StatCard icon={<Users size={18} />}         label="Consentidos"     value={data?.consented} color="var(--accent)" />
        <StatCard icon={<Shield size={18} />}        label="Revocados"       value={data?.revoked}   color="var(--purple)" />
      </div>

      {byType.length > 0 && (
        <div style={{ ...S.innerCard, marginBottom: 12 }}>
          <div style={S.sectionTitle}>{t('bigdpr.dsrs_por_tipo')}</div>
          <div className="u-stack-8">
            {byType.map(({ type, count }) => (
              <div key={type} className="u-row-center-12">
                <span style={{ ...S.badge(TYPE_COLOR[type] ?? 'var(--text-3)'), minWidth: 110, display: 'inline-block' }}>{type}</span>
                <div className="bigdpa-box-6">
                  <div className="bigdpa-box-11" style={{ width: `${Math.min(100, (count / (data?.total_dsrs || 1)) * 100)}%`, background: TYPE_COLOR[type] ?? 'var(--accent)' }} />
                </div>
                <span className="bigdpa-box-7">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(data?.overdue ?? 0) > 0 && (
        <div style={{ ...S.innerCard, borderColor: 'var(--danger-border)' }}>
          <div className="bigdpa-box-8">
            <AlertTriangle size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} />
            {data?.overdue} DSR{data?.overdue !== 1 ? 's' : ''} ha{data?.overdue !== 1 ? 'n' : ''} {t('bigdpr.superado_el_plazo_gdpr_30_dias')}
          </div>
          <div className="u-text3-mono-xs">
            {(data?.overdue_ids ?? []).join(', ')}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main ───────────────────────────────────────────────────────────────────────
export default function BiGdprPanel() {
  const t   = useAppT()
  const [tab, setTab] = useState<string>('dsr')

  const TAB_NAV = [
    { id: 'dsr',     label: 'DSR' },
    { id: 'consent', label: t('bi.gdpr.consent', 'Consentimiento') },
    { id: 'masks',   label: t('bi.gdpr.masks', 'Máscaras') },
    { id: 'stats',   label: t('bi.gdpr.stats', 'Estadísticas') },
  ]

  return (
    <div style={S.card}>
      <div className="bigdpa-row-8">
        <div className="bigdpa-row-9">
          <Shield size={16} />
        </div>
        <h3 className="bigdpa-box-9">
          {t('bi.gdpr.title', 'Cumplimiento GDPR')}
        </h3>
      </div>

      <div className="bigdpa-row-10">
        {TAB_NAV.map(({ id, label }) => (
          <button className="bigdpa-box-12" key={id} onClick={() => setTab(id)} style={{ fontWeight: tab === id ? 700 : 400, color: tab === id ? 'var(--accent)' : 'var(--text-2)', borderBottom: `2px solid ${tab === id ? 'var(--accent)' : 'transparent'}` }}>
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
