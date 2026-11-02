/**
 * Planificación de cambios: calendario (con choques y congelaciones),
 * versiones, ventanas de congelación y el comité de cada cambio.
 */
import { useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, EmptyState, Modal, Spinner } from '../../components/ui'
import { COLOR } from '../../constants/theme'
import { sdChangePlanningApi } from '../../services/api'

type Choque = { change_id: string; number: string; cis: string[] }
type CambioCal = { id: string; number: string; title: string; status: string; change_type: string; risk: string; planned_start: string; planned_end?: string | null; conflicts: Choque[]; in_blackout: boolean }
type Congelacion = { id: string; name: string; reason?: string | null; start_at: string; end_at: string }
type Version = { id: string; name: string; version?: string | null; status: string; planned_date?: string | null; notes?: string | null; changes?: { id: string; number: string; title: string; status: string }[] }
type Voto = { user_id: string; name?: string | null; decision: string; note?: string | null }
type Cab = { status: string; quorum?: number | null; meeting?: { scheduled_at: string; agenda?: string } | null; votes: Voto[] }

const IS: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8,
  padding: '9px 13px', color: 'var(--text-1)', fontSize: 'var(--text-base)', outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const LS: CSSProperties = { fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 5,
  textTransform: 'uppercase', letterSpacing: '0.06em' }
const fecha = (iso?: string | null) => iso ? new Date(iso).toLocaleString(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'
const aLocal = (iso?: string | null) => iso ? new Date(iso).toISOString().slice(0, 16) : ''
const aIso = (local: string) => local ? new Date(local).toISOString() : null

// ── Calendario ───────────────────────────────────────────────────────────────
export function CalendarioCambios({ onOpen }: { onOpen: (id: string) => void }) {
  const t = useAppT()
  const [mes, setMes] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1) })
  const hasta = new Date(mes.getFullYear(), mes.getMonth() + 1, 1)
  const { data, isLoading } = useQuery({
    queryKey: ['sd-change-calendar', mes.toISOString()],
    queryFn: () => sdChangePlanningApi.calendar(mes.toISOString(), hasta.toISOString())
      .then(r => r.data as { changes: CambioCal[]; blackouts: Congelacion[]; releases: Version[] }),
  })
  // Un día por fila con lo que empieza ese día; congelaciones y versiones arriba.
  const dias = useMemo(() => {
    const porDia = new Map<string, CambioCal[]>()
    for (const c of data?.changes ?? []) {
      const k = new Date(c.planned_start).toDateString()
      porDia.set(k, [...(porDia.get(k) ?? []), c])
    }
    return [...porDia.entries()]
  }, [data])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <Button variant="secondary" aria-label={t('sd_cfg.chg_prev')} onClick={() => setMes(new Date(mes.getFullYear(), mes.getMonth() - 1, 1))}>‹</Button>
        <div style={{ fontWeight: 700, minWidth: 160, textAlign: 'center', textTransform: 'capitalize' }}>
          {mes.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}
        </div>
        <Button variant="secondary" aria-label={t('sd_cfg.chg_next')} onClick={() => setMes(new Date(mes.getFullYear(), mes.getMonth() + 1, 1))}>›</Button>
      </div>
      {isLoading ? <Spinner /> : <>
        {(data?.blackouts ?? []).map(b => (
          <div key={b.id} role="note" style={{ border: `1px solid ${COLOR.danger}50`, background: `${COLOR.danger}10`, borderRadius: 8, padding: '8px 12px', fontSize: 'var(--text-sm)' }}>
            <strong style={{ color: COLOR.danger }}>❄ {b.name}</strong> · {fecha(b.start_at)} → {fecha(b.end_at)}
          </div>
        ))}
        {(data?.releases ?? []).map(r => (
          <div key={r.id} style={{ border: '1px solid var(--accent)', background: 'var(--accent-muted)', borderRadius: 8, padding: '8px 12px', fontSize: 'var(--text-sm)' }}>
            <strong style={{ color: 'var(--accent)' }}>🚀 {r.name}{r.version ? ` ${r.version}` : ''}</strong> · {fecha(r.planned_date)} · {t(`sd_cfg.chg_rel_${r.status}`)}
          </div>
        ))}
        {dias.length === 0 ? <div style={{ color: 'var(--text-3)', fontSize: 'var(--text-sm)' }}>{t('sd_cfg.chg_empty_month')}</div> : dias.map(([dia, cambios]) => (
          <div key={dia}>
            <div style={{ ...LS, marginBottom: 6 }}>{new Date(dia).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}</div>
            <div className="ds-card" style={{ padding: 0, overflow: 'hidden' }}>
              {cambios.map((c, i) => (
                <button key={c.id} type="button" onClick={() => onOpen(c.id)}
                  style={{ display: 'flex', gap: 12, width: '100%', textAlign: 'left', padding: '10px 14px', border: 'none', cursor: 'pointer',
                    borderTop: i ? '1px solid var(--surface-4)' : 'none', background: 'transparent', color: 'var(--text-1)', fontFamily: 'inherit', flexWrap: 'wrap' }}>
                  <span style={{ color: 'var(--text-3)', fontSize: 'var(--text-sm)', minWidth: 110 }}>
                    {new Date(c.planned_start).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                    {c.planned_end ? `–${new Date(c.planned_end).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}` : ''}
                  </span>
                  <span style={{ fontWeight: 700, color: 'var(--accent)' }}>{c.number}</span>
                  <span style={{ flex: 1, minWidth: 160 }}>{c.title}</span>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{c.status.replace(/_/g, ' ')}</span>
                  {c.in_blackout && <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: COLOR.danger }}>❄ {t('sd_cfg.chg_in_blackout')}</span>}
                  {c.conflicts.length > 0 && (
                    <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: COLOR.warning }}>
                      ⚠ {t('sd_cfg.chg_conflict', { list: c.conflicts.map(x => `${x.number} (${x.cis.join(', ')})`).join(' · ') })}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        ))}
      </>}
    </div>
  )
}

// ── Congelaciones ────────────────────────────────────────────────────────────
export function Congelaciones() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [editando, setEditando] = useState<Congelacion | 'nueva' | null>(null)
  const { data: filas = [], isLoading } = useQuery<Congelacion[]>({
    queryKey: ['sd-change-blackouts'], queryFn: () => sdChangePlanningApi.blackouts().then(r => r.data as Congelacion[]),
  })
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['sd-change-blackouts'] }); qc.invalidateQueries({ queryKey: ['sd-change-calendar'] }) }
  const guardar = useMutation({
    mutationFn: ({ id, ...d }: Record<string, unknown>) => id ? sdChangePlanningApi.updateBlackout(String(id), d) : sdChangePlanningApi.createBlackout(d),
    onSuccess: () => { refrescar(); setEditando(null) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const borrar = useMutation({ mutationFn: (id: string) => sdChangePlanningApi.deleteBlackout(id), onSuccess: refrescar })
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>{t('sd_cfg.chg_blackout_help')}</div>
        <Button onClick={() => setEditando('nueva')}>+ {t('sd_cfg.chg_blackout_new')}</Button>
      </div>
      {isLoading ? <Spinner /> : filas.length === 0 ? <EmptyState icon="❄" title={t('sd_cfg.chg_blackout_empty')} description={t('sd_cfg.chg_blackout_help')} /> : (
        <div className="ds-card" style={{ padding: 0, overflow: 'hidden' }}>
          {filas.map((b, i) => (
            <div key={b.id} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '10px 14px', borderTop: i ? '1px solid var(--surface-4)' : 'none', flexWrap: 'wrap' }}>
              <strong style={{ flex: '1 1 200px' }}>{b.name}</strong>
              <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{fecha(b.start_at)} → {fecha(b.end_at)}</span>
              <Button variant="secondary" onClick={() => setEditando(b)}>{t('common.edit')}</Button>
              <Button variant="secondary" onClick={() => openConfirmGlobal({ message: t('sd_cfg.chg_delete_confirm'), onConfirm: () => borrar.mutate(b.id), danger: true })}>
                <span style={{ color: COLOR.danger }}>{t('common.delete')}</span></Button>
            </div>
          ))}
        </div>
      )}
      {editando && (
        <Modal open title={t('sd_cfg.chg_blackout_new')} onClose={() => setEditando(null)}>
          <FormCongelacion inicial={editando === 'nueva' ? null : editando} pendiente={guardar.isPending}
            onCancelar={() => setEditando(null)} onGuardar={d => guardar.mutate(d)} />
        </Modal>
      )}
    </div>
  )
}

function FormCongelacion({ inicial, pendiente, onCancelar, onGuardar }: { inicial: Congelacion | null; pendiente: boolean; onCancelar: () => void; onGuardar: (d: Record<string, unknown>) => void }) {
  const t = useAppT()
  const [f, setF] = useState({ name: inicial?.name ?? '', reason: inicial?.reason ?? '', start: aLocal(inicial?.start_at), end: aLocal(inicial?.end_at) })
  const valido = f.name.trim() && f.start && f.end && f.end > f.start
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div><label style={LS} htmlFor="blk-name">{t('sd_cfg.chg_name')} *</label><input id="blk-name" aria-label={t('sd_cfg.chg_name')} value={f.name} onChange={e => setF({ ...f, name: e.target.value })} style={IS} /></div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div><label style={LS} htmlFor="blk-from">{t('sd_cfg.chg_from')} *</label><input id="blk-from" aria-label={t('sd_cfg.chg_from')} type="datetime-local" value={f.start} onChange={e => setF({ ...f, start: e.target.value })} style={IS} /></div>
        <div><label style={LS} htmlFor="blk-to">{t('sd_cfg.chg_to')} *</label><input id="blk-to" aria-label={t('sd_cfg.chg_to')} type="datetime-local" value={f.end} onChange={e => setF({ ...f, end: e.target.value })} style={IS} /></div>
      </div>
      <div><label style={LS} htmlFor="blk-reason">{t('sd_cfg.chg_reason')}</label><textarea id="blk-reason" aria-label={t('sd_cfg.chg_reason')} rows={2} value={f.reason} onChange={e => setF({ ...f, reason: e.target.value })} style={{ ...IS, resize: 'vertical' }} /></div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <Button variant="secondary" onClick={onCancelar}>{t('common.cancel')}</Button>
        <Button disabled={!valido || pendiente} loading={pendiente}
          onClick={() => onGuardar({ id: inicial?.id, name: f.name.trim(), reason: f.reason || null, start_at: aIso(f.start), end_at: aIso(f.end) })}>{t('common.save')}</Button>
      </div>
    </div>
  )
}

// ── Versiones ────────────────────────────────────────────────────────────────
const ESTADOS_VERSION = ['planned', 'in_progress', 'released', 'cancelled']

export function Versiones({ onOpen }: { onOpen: (id: string) => void }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [editando, setEditando] = useState<Version | 'nueva' | null>(null)
  const { data: filas = [], isLoading } = useQuery<Version[]>({
    queryKey: ['sd-releases'], queryFn: () => sdChangePlanningApi.releases().then(r => r.data as Version[]),
  })
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['sd-releases'] }); qc.invalidateQueries({ queryKey: ['sd-change-calendar'] }) }
  const guardar = useMutation({
    mutationFn: ({ id, ...d }: Record<string, unknown>) => id ? sdChangePlanningApi.updateRelease(String(id), d) : sdChangePlanningApi.createRelease(d),
    onSuccess: () => { refrescar(); setEditando(null) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const borrar = useMutation({ mutationFn: (id: string) => sdChangePlanningApi.deleteRelease(id), onSuccess: refrescar })
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}><Button onClick={() => setEditando('nueva')}>+ {t('sd_cfg.chg_release_new')}</Button></div>
      {isLoading ? <Spinner /> : filas.length === 0 ? <EmptyState icon="🚀" title={t('sd_cfg.chg_release_empty')} description="" /> : filas.map(r => (
        <div key={r.id} className="ds-card" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <strong style={{ flex: 1 }}>{r.name}{r.version ? ` · ${r.version}` : ''}</strong>
            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: r.status === 'released' ? COLOR.success : 'var(--text-2)' }}>{t(`sd_cfg.chg_rel_${r.status}`)}</span>
            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>{fecha(r.planned_date)}</span>
            <Button variant="secondary" onClick={() => setEditando(r)}>{t('common.edit')}</Button>
            <Button variant="secondary" onClick={() => openConfirmGlobal({ message: t('sd_cfg.chg_delete_confirm'), onConfirm: () => borrar.mutate(r.id), danger: true })}>
              <span style={{ color: COLOR.danger }}>{t('common.delete')}</span></Button>
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {(r.changes ?? []).length === 0 ? <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>{t('sd_cfg.chg_no_changes')}</span>
              : (r.changes ?? []).map(c => (
                <button key={c.id} type="button" onClick={() => onOpen(c.id)} style={{ border: '1px solid var(--surface-4)', borderRadius: 999, padding: '3px 10px', background: 'transparent', cursor: 'pointer', fontFamily: 'inherit', fontSize: 'var(--text-xs)', color: 'var(--text-1)' }}>
                  {c.number} · {c.status.replace(/_/g, ' ')}
                </button>
              ))}
          </div>
        </div>
      ))}
      {editando && (
        <Modal open title={t('sd_cfg.chg_release_new')} onClose={() => setEditando(null)}>
          <FormVersion inicial={editando === 'nueva' ? null : editando} pendiente={guardar.isPending}
            onCancelar={() => setEditando(null)} onGuardar={d => guardar.mutate(d)} />
        </Modal>
      )}
    </div>
  )
}

function FormVersion({ inicial, pendiente, onCancelar, onGuardar }: { inicial: Version | null; pendiente: boolean; onCancelar: () => void; onGuardar: (d: Record<string, unknown>) => void }) {
  const t = useAppT()
  const [f, setF] = useState({ name: inicial?.name ?? '', version: inicial?.version ?? '', status: inicial?.status ?? 'planned',
    date: aLocal(inicial?.planned_date), notes: inicial?.notes ?? '' })
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10 }}>
        <div><label style={LS} htmlFor="rel-name">{t('sd_cfg.chg_name')} *</label><input id="rel-name" aria-label={t('sd_cfg.chg_name')} value={f.name} onChange={e => setF({ ...f, name: e.target.value })} style={IS} /></div>
        <div><label style={LS} htmlFor="rel-version">{t('sd_cfg.chg_version')}</label><input id="rel-version" aria-label={t('sd_cfg.chg_version')} value={f.version} onChange={e => setF({ ...f, version: e.target.value })} style={IS} /></div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div><label style={LS} htmlFor="rel-date">{t('sd_cfg.chg_planned_date')}</label><input id="rel-date" aria-label={t('sd_cfg.chg_planned_date')} type="datetime-local" value={f.date} onChange={e => setF({ ...f, date: e.target.value })} style={IS} /></div>
        <div><label style={LS} htmlFor="rel-status">{t('sd_cfg.chg_status')}</label>
          <select id="rel-status" aria-label={t('sd_cfg.chg_status')} value={f.status} onChange={e => setF({ ...f, status: e.target.value })} style={IS}>
            {ESTADOS_VERSION.map(s => <option key={s} value={s}>{t(`sd_cfg.chg_rel_${s}`)}</option>)}
          </select></div>
      </div>
      <div><label style={LS} htmlFor="rel-notes">{t('sd_cfg.chg_reason')}</label><textarea id="rel-notes" aria-label={t('sd_cfg.chg_reason')} rows={3} value={f.notes} onChange={e => setF({ ...f, notes: e.target.value })} style={{ ...IS, resize: 'vertical' }} /></div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <Button variant="secondary" onClick={onCancelar}>{t('common.cancel')}</Button>
        <Button disabled={!f.name.trim() || pendiente} loading={pendiente}
          onClick={() => onGuardar({ id: inicial?.id, name: f.name.trim(), version: f.version || null, status: f.status, planned_date: aIso(f.date), notes: f.notes || null })}>{t('common.save')}</Button>
      </div>
    </div>
  )
}

// ── Comité del cambio ────────────────────────────────────────────────────────
export function PanelCab({ changeId }: { changeId: string | number }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { user } = useAuth()
  const [nota, setNota] = useState('')
  const { data: cab } = useQuery<Cab | null>({
    queryKey: ['sd-change-cab', changeId],
    queryFn: () => sdChangePlanningApi.cab(changeId).then(r => r.data as Cab).catch(() => null),
  })
  const votar = useMutation({
    mutationFn: (approve: boolean) => sdChangePlanningApi.vote(changeId, { approve, note: nota }),
    onSuccess: () => {
      setNota('')
      qc.invalidateQueries({ queryKey: ['sd-change-cab', changeId] })
      qc.invalidateQueries({ queryKey: ['sd-change-detail', changeId] })
      qc.invalidateQueries({ queryKey: ['sd-changes'] })
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  if (!cab) return null
  const mio = cab.votes.find(v => v.user_id === user?.id)
  const puedeVotar = mio?.decision === 'pending' && (cab.status === 'requester' || cab.status === 'cab')
  const color = (d: string) => d === 'approved' ? COLOR.success : d === 'rejected' ? COLOR.danger : 'var(--text-3)'
  return (
    <div className="ds-card" style={{ padding: 14, marginBottom: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ ...LS, marginBottom: 0 }}>{t('sd_cfg.chg_cab')}{cab.quorum ? ` · ${t('sd_cfg.chg_cab_quorum', { n: cab.quorum })}` : ''}</div>
      {cab.meeting && <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{t('sd_cfg.chg_meeting', { when: fecha(cab.meeting.scheduled_at) })}</div>}
      {cab.votes.map(v => (
        <div key={v.user_id} style={{ display: 'flex', gap: 10, fontSize: 'var(--text-sm)' }}>
          <span style={{ flex: 1 }}>{v.name ?? v.user_id}</span>
          <span style={{ fontWeight: 600, color: color(v.decision) }}>{t(`sd_cfg.chg_vote_${v.decision}`)}</span>
          {v.note && <span style={{ color: 'var(--text-3)' }}>— {v.note}</span>}
        </div>
      ))}
      {puedeVotar && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 6 }}>
          <textarea aria-label={t('sd_cfg.chg_vote_note')} placeholder={t('sd_cfg.chg_vote_note')} rows={2} value={nota}
            onChange={e => setNota(e.target.value)} style={{ ...IS, resize: 'vertical' }} />
          <div style={{ display: 'flex', gap: 8 }}>
            <Button onClick={() => votar.mutate(true)} loading={votar.isPending}>{t('sd_cfg.chg_vote_yes')}</Button>
            <Button variant="secondary" disabled={!nota.trim()} onClick={() => votar.mutate(false)}>{t('sd_cfg.chg_vote_no')}</Button>
          </div>
        </div>
      )}
    </div>
  )
}
