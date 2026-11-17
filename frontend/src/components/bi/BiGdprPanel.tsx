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
import type { CSSProperties } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { biGdprApi } from '../../services/api'
import type { ConsentimientoBi, InformeDeBorradoRgpd, SolicitudDsr } from '../../services/api/tipos-bi'
import { useAppT } from '../../i18n/AppLangContext'
import { useConfirm } from '../../context/ConfirmContext'
import {
  Shield, AlertTriangle, CheckCircle, Download, Trash2,
  Clock, Users, ToggleLeft, ToggleRight, ChevronDown, ChevronUp, X, Plus, FileText, UserCheck, EyeOff, BarChart3,
} from 'lucide-react'
import { fmtDate } from '../../utils/helpers'
import { Button, EmptyState, IconButton, KpiCard, Spinner, Tabs, Select, Segmentado, Pulsable } from '../ui'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import useMediaQuery from '../../hooks/useMediaQuery'
import { POLL_DEFAULT_MS } from '../../constants/timings'
import './BiGdprPanel.css'

// ── Styles ────────────────────────────────────────────────────────────────────
/** Color del dato de una insignia: la clase `bi-gdpr-panel-badge` lo consume. */
const varsBadge = (color: string) => ({ '--bi-gdpr-badge-color': color } as CSSProperties)


const TYPE_COLOR: Record<string, string>  = { erasure: 'var(--danger)', portability: 'var(--accent)', rectification: 'var(--warning)', restriction: 'var(--purple)' }
const STATUS_COLOR: Record<string, string>= { pending: 'var(--warning)', completed: 'var(--success)', rejected: 'var(--danger)' }

const fmt = (iso?: string | null): string => fmtDate(iso)

function isOverdue(dsr: SolicitudDsr): boolean {
  if (dsr.status !== 'pending') return false
  // El servidor fija `deadline` al crearla (COMPLIANCE_GDPR_MAX_DAYS): sin plazo en duro aquí.
  return Date.now() > new Date(dsr.deadline).getTime()
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
    mutationFn: (id: string) => biGdprApi.resolveDsr(id, { resolution_notes: t('bigdpr.resuelta_manual') }).then(r => r.data),
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
      <div className={`bigdpa-grid-1 ${isNarrow ? 'bi-gdpr-panel-m3' : 'bi-gdpr-panel-m4'}`}>
        <input aria-label={t('bigdpr.subject_id_o_email')} placeholder={t('bigdpr.subject_id_o_email')} value={form.user_id} onChange={e => setForm(f => ({ ...f, user_id: e.target.value }))} className="bi-gdpr-panel-e30" />
        <Select suelto value={form.request_type} onChange={e => setForm(f => ({ ...f, request_type: e.target.value }))} className="bi-gdpr-panel-e31" placeholder={false}>
          {['erasure', 'portability', 'rectification', 'restriction'].map(rt => <option key={rt} value={rt}>{etiquetaCodigo(t, 'bigdpr.tipo', rt)}</option>)}
        </Select>
        <input aria-label={t('absences.notes_optional')} placeholder={t('absences.notes_optional')} value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} className="bi-gdpr-panel-e30" />
        <Button icon={<Plus size={14} />} onClick={() => createMut.mutate({ user_id: form.user_id, request_type: form.request_type, notes: form.notes || '' })}
          disabled={createMut.isPending || !form.user_id} loading={createMut.isPending}>
          {t('bigdpr.nueva_solicitud')}
        </Button>
      </div>

      {/* Status filter */}
      <div className="bigdpa-row-1">
        <Segmentado aria-label={t('bigdpr.filtrar_estado')} valor={statusFilter} onChange={setFilter}
          opciones={['', 'pending', 'completed'].map(s => ({ valor: s, etiqueta: s ? etiquetaCodigo(t, 'bigdpr.estado', s) : t('bigdpr.todos') }))} />
      </div>

      {isLoading ? (
        <Spinner />
      ) : (
        <div className="u-stack-6">
          {dsrs.map((dsr) => {
            const overdue  = isOverdue(dsr)
            const expanded = expandedId === dsr.id
            const informe  = dsr.erasure_report ?? informes[dsr.id]
            return (
              <div key={dsr.id} className="bi-gdpr-panel-e10">
                <div className={`bigdpa-row-12 ${isNarrow ? 'bi-gdpr-panel-m11' : ''}`}>
                  <div className="u-flex1-min0">
                    <div className="u-wrap-center-8">
                      <span className="u-text1-base-600">{dsr.subject_id}</span>
                      <span className="bi-gdpr-panel-badge" style={varsBadge(TYPE_COLOR[dsr.request_type] ?? 'var(--text-3)')}>{etiquetaCodigo(t, 'bigdpr.tipo', dsr.request_type)}</span>
                      <span className="bi-gdpr-panel-badge" style={varsBadge(STATUS_COLOR[dsr.status] ?? 'var(--text-3)')}>{etiquetaCodigo(t, 'bigdpr.estado', dsr.status)}</span>
                      {overdue && <span className="bi-gdpr-panel-badge" style={varsBadge('var(--danger)')}><AlertTriangle size={10} className="bigdprpa-sx1" />{t('governedconversations.sla_vencido')}</span>}
                    </div>
                    <div className="bigdpa-row-2">
                      <span>{t('portalsupportdesk.creado')} {fmt(dsr.created_at)}</span>
                      {dsr.deadline && <span>{t('bigdpr.limite')} {fmt(dsr.deadline)}</span>}
                      {dsr.resolved_at && <span>{t('bigdpr.resuelto')} {fmt(dsr.resolved_at)}</span>}
                    </div>
                    {dsr.notes && <div className="u-text3-xs-mt2">{dsr.notes}</div>}
                  </div>
                  <div className="bigdpa-row-3">
                    {dsr.status === 'pending' && (
                      <>
                        {dsr.request_type === 'erasure' && (
                          <Button size="sm" variant="danger" icon={<Trash2 size={14} />} onClick={async () => {
                              const ok = await confirmar({
                                title: t('bigdpr.borrado_titulo'),
                                message: t('bigdpr.borrado_msg', { usuario: dsr.subject_id }),
                                danger: true,
                                confirmLabel: t('bigdpr.borrar_pii'),
                                palabraConfirmacion: t('bigdpr.borrado_palabra'),
                              })
                              if (ok) erasureMut.mutate(dsr.id)
                            }}
                            disabled={erasureMut.isPending} loading={erasureMut.isPending}>
                            {t('bigdpr.borrar_pii')}
                          </Button>
                        )}
                        {dsr.request_type === 'portability' && (
                          <Button size="sm" variant="secondary" icon={<Download size={14} />} onClick={() => portMut.mutate(dsr.id)} disabled={portMut.isPending} loading={portMut.isPending}>
                            {t('bigdpr.exportar')}
                          </Button>
                        )}
                        <Button size="sm" variant="secondary" icon={<CheckCircle size={14} />} onClick={() => resolveMut.mutate(dsr.id)} disabled={resolveMut.isPending}>
                          {t('bigdpr.resolver')}
                        </Button>
                      </>
                    )}
                    {informe ? (
                      <IconButton onClick={() => setExpanded(expanded ? null : dsr.id)} aria-expanded={expanded}
                        ariaLabel={expanded ? t('bigdpr.ocultar_informe') : t('bigdpr.ver_informe')}>
                        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </IconButton>
                    ) : null}
                  </div>
                </div>
                {expanded && informe ? (
                  <div className="bigdpa-box-2">
                    <pre className="ds-codigo ds-codigo--bloque bigdpa-sp-1">{JSON.stringify(informe, null, 2)}</pre>
                  </div>
                ) : null}
              </div>
            )
          })}
          {!dsrs.length && (
            <EmptyState icon={<FileText size={28} />} title={t('bigdpr.sin_solicitudes')} />
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
      <div className="bi-gdpr-panel-e15">
        <div className="bi-gdpr-panel-e16">{t('bigdpr.registrar_consentimiento')}</div>
        <div className={`bigdpa-grid-2 ${isNarrow ? 'bi-gdpr-panel-m3' : 'bi-gdpr-panel-m17'}`}>
          <input aria-label={t('bigdpr.user_id_o_email')} placeholder={t('bigdpr.user_id_o_email')} value={form.user_id} onChange={e => setForm(f => ({ ...f, user_id: e.target.value }))} className="bi-gdpr-panel-e30" />
          <Select suelto value={form.purpose} onChange={e => setForm(f => ({ ...f, purpose: e.target.value }))} className="bi-gdpr-panel-e31" placeholder={false}>
            {['analytics', 'marketing', 'profiling', 'research'].map(p => <option key={p} value={p}>{etiquetaCodigo(t, 'bigdpr.finalidad', p)}</option>)}
          </Select>
          <Select suelto value={form.channel} onChange={e => setForm(f => ({ ...f, channel: e.target.value }))} className="bi-gdpr-panel-e31" placeholder={false}>
            {['web', 'email', 'api', 'mobile'].map(c => <option key={c} value={c}>{etiquetaCodigo(t, 'bigdpr.canal', c)}</option>)}
          </Select>
          <Button icon={<Plus size={14} />} onClick={() => addMut.mutate(form)} disabled={addMut.isPending || !form.user_id} loading={addMut.isPending}>
            {t('bigdpr.anadir')}
          </Button>
        </div>
      </div>

      {isLoading ? (
        <Spinner />
      ) : (
        <div className="u-stack-6">
          {consents.map((c) => (
            <div key={`${c.user_id}:${c.purpose}`} className="bi-gdpr-panel-e32">
              <div className="u-flex1-min0">
                <div className="u-text1-base-600">{c.user_id}</div>
                <div className="u-text3-xs-mt2">
                  {c.purpose && <span className="bigdpa-sp-2">{etiquetaCodigo(t, 'bigdpr.finalidad', c.purpose)}</span>}
                  {c.channel && <span className="bigdpa-sp-2">{etiquetaCodigo(t, 'bigdpr.canal', c.channel)}</span>}
                  {c.updated_at && <span>{t('bigdpr.actualizado')} {fmt(c.updated_at)}</span>}
                </div>
              </div>
              <span className="bi-gdpr-panel-badge" style={varsBadge(c.consented ? 'var(--success)' : 'var(--danger)')}>{c.consented ? t('bigdpr.concedido') : t('bigdpr.revocado')}</span>
              <Pulsable className={`bigdpa-row-13 ${c.consented ? 'bi-gdpr-panel-m18' : 'bi-gdpr-panel-m19'}`} onClick={() => toggleMut.mutate({ c, consented: !c.consented })} disabled={toggleMut.isPending}
                title={c.consented ? t('bigdpr.revocar') : t('bigdpr.conceder')} aria-label={c.consented ? t('bigdpr.revocar') : t('bigdpr.conceder')}>
                {c.consented ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
              </Pulsable>
              <Pulsable aria-label={t('bigdpr.ver_historial')} onClick={() => setHistUser(histUserId === c.user_id ? null : c.user_id)}
                title={t('bigdpr.ver_historial')}
                className="bigdpa-row-4">
                <Clock size={14} />
              </Pulsable>
            </div>
          ))}
          {!consents.length && (
            <EmptyState icon={<UserCheck size={28} />} title={t('bigdpr.sin_consentimientos')} />
          )}
        </div>
      )}

      {/* History panel */}
      {histUserId && historyData && (
        <div className="bi-gdpr-panel-e20">
          <div className="bigdpa-row-5">
            <span className="bigdpa-txt-2">
              {t('bigdpr.historial')} {histUserId}
            </span>
            <IconButton onClick={() => setHistUser(null)} ariaLabel={t('bigdpr.cerrar_historial')}><X size={14} /></IconButton>
          </div>
          {!historyData.history.length ? (
            <div className="u-text3-sm">{t('bigdpr.sin_historial')}</div>
          ) : (
            <div className="bigdpa-stack-1">
              {historyData.history.map((h, idx) => (
                <div key={idx} className="bigdpa-row-6">
                  <span className={`bigdpa-box-10 ${h.action === 'granted' ? 'bi-gdpr-panel-m19' : 'bi-gdpr-panel-m18'}`}>{etiquetaCodigo(t, 'bigdpr.accion', h.action)}</span>
                  <span>{etiquetaCodigo(t, 'bigdpr.finalidad', h.purpose)}</span>
                  <span>{etiquetaCodigo(t, 'bigdpr.canal', h.channel)}</span>
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

  const MASK_COLOR: Record<string, string> = { hash: 'var(--accent)', redact: 'var(--danger)', partial: 'var(--warning)', suppress: 'var(--purple)', pseudonymize: 'var(--text-2)' }

  return (
    <div>
      <div className={`bigdpa-grid-1 ${isNarrow ? 'bi-gdpr-panel-m3' : 'bi-gdpr-panel-m22'}`}>
        <input aria-label={t('bigdpr.entidad_ej_user')} placeholder={t('bigdpr.entidad_ej_user')} value={form.entity} onChange={e => setForm(f => ({ ...f, entity: e.target.value }))} className="bi-gdpr-panel-e30" />
        <input aria-label={t('bigdpr.campo_ej_email')} placeholder={t('bigdpr.campo_ej_email')} value={form.field} onChange={e => setForm(f => ({ ...f, field: e.target.value }))} className="bi-gdpr-panel-e30" />
        <Select suelto value={form.mask_type} onChange={e => setForm(f => ({ ...f, mask_type: e.target.value }))} className="bi-gdpr-panel-e31" placeholder={false}>
          {['hash', 'redact', 'suppress', 'pseudonymize'].map(mt => <option key={mt} value={mt}>{etiquetaCodigo(t, 'bigdpr.mascara', mt)}</option>)}
        </Select>
        <Button icon={<Plus size={14} />} onClick={() => addMut.mutate(form)} disabled={addMut.isPending || !form.field} loading={addMut.isPending}>
          {t('bigdpr.anadir_mascara')}
        </Button>
      </div>
      <div className="u-stack-6">
        {masks.map((m, i) => (
          <div key={i} className="bi-gdpr-panel-e23">
            <span className="ds-codigo bigdpa-txt-3">{m.dataset}.{m.field}</span>
            <span className="bi-gdpr-panel-badge" style={varsBadge(MASK_COLOR[m.mask_type] ?? 'var(--text-3)')}>{etiquetaCodigo(t, 'bigdpr.mascara', m.mask_type)}</span>
            <span className="bigdpa-box-5">{fmt(m.updated_at)}</span>
          </div>
        ))}
        {!masks.length && (
          <EmptyState icon={<EyeOff size={28} />} title={t('bigdpr.sin_mascaras')} />
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

  if (isLoading) return <Spinner label={t('bigdpr.cargando_estadisticas')} />

  return (
    <div>
      <div className="ds-grid-stats bigdpa-kpis">
        <KpiCard icon={<Clock size={14} />}         label={t('bigdpr.dsrs_pendientes')} value={data?.pending ?? 0} warning={(data?.pending ?? 0) > 0} />
        <KpiCard icon={<AlertTriangle size={14} />} label={t('bigdpr.sla_vencidos')}    value={data?.overdue ?? 0} danger={(data?.overdue ?? 0) > 0} />
        <KpiCard icon={<CheckCircle size={14} />}   label={t('bigdpr.completadas')}     value={data?.completed ?? 0} />
        <KpiCard icon={<Users size={14} />}         label={t('bigdpr.consentidos')}     value={data?.consented ?? 0} />
        <KpiCard icon={<Shield size={14} />}        label={t('bigdpr.revocados')}       value={data?.revoked ?? 0} />
      </div>

      {byType.length > 0 && (
        <div className="bi-gdpr-panel-e24">
          <div className="bi-gdpr-panel-e16">{t('bigdpr.dsrs_por_tipo')}</div>
          <div className="u-stack-8">
            {byType.map(({ type, count }) => (
              <div key={type} className="u-row-center-12">
                <span className="bi-gdpr-panel-badge bi-gdpr-panel-badge--tipo" style={varsBadge(TYPE_COLOR[type] ?? 'var(--text-3)')}>{etiquetaCodigo(t, 'bigdpr.tipo', type)}</span>
                <div className="bigdpa-box-6">
                  <div className="bigdpa-box-11 bi-gdpr-panel-e25" style={{ '--bi-gdpr-panel-width': `${Math.min(100, (count / (data?.total_dsrs || 1)) * 100)}%`, '--bi-gdpr-panel-background': TYPE_COLOR[type] ?? 'var(--accent)' } as CSSProperties} />
                </div>
                <span className="bigdpa-box-7">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(data?.overdue ?? 0) > 0 && (
        <div className="bi-gdpr-panel-e26">
          <div className="bigdpa-box-8">
            <AlertTriangle size={14} className="bigdprpa-sx3" />
            {t(data?.overdue === 1 ? 'bigdpr.dsr_vencida_uno' : 'bigdpr.dsr_vencidas_otros', { n: data?.overdue ?? 0 })}
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
    { id: 'dsr',     label: t('bigdpr.tab_solicitudes'), icon: <FileText size={14} /> },
    { id: 'consent', label: t('bigdpr.tab_consentimiento'), icon: <UserCheck size={14} /> },
    { id: 'masks',   label: t('bigdpr.tab_mascaras'), icon: <EyeOff size={14} /> },
    { id: 'stats',   label: t('bigdpr.tab_estadisticas'), icon: <BarChart3 size={14} /> },
  ]

  return (
    <div className="bi-gdpr-panel-e33">
      <div className="bigdpa-row-8">
        <div className="bigdpa-row-9">
          <Shield size={16} />
        </div>
        <h3 className="bigdpa-box-9">
          {t('bigdpr.titulo')}
        </h3>
      </div>

      <Tabs items={TAB_NAV} active={tab} onChange={setTab} ariaLabel={t('bigdpr.titulo')} className="bigdpa-tabs" />

      {tab === 'dsr'     && <DsrTab />}
      {tab === 'consent' && <ConsentTab />}
      {tab === 'masks'   && <MasksTab />}
      {tab === 'stats'   && <StatsTab />}
    </div>
  )
}
