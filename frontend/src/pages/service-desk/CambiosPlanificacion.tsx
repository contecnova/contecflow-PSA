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
import { COLOR, alpha } from '../../constants/theme'
import { sdChangePlanningApi } from '../../services/api'
import type { SdCambioEnCalendario, SdComiteDeCambio, SdCongelacion, SdVersionDeCambios } from '../../services/api/tipos-sd'
import { etiquetaSd } from './sdUtils'
import DateInput from '../../components/ui/DateInput'
import './CambiosPlanificacion.css'

type CambioCal = SdCambioEnCalendario
type Congelacion = SdCongelacion
type Version = SdVersionDeCambios

const IS: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8,
  padding: '9px 13px', color: 'var(--text-1)', fontSize: 'var(--text-base)', outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
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
    queryFn: () => sdChangePlanningApi.calendar(mes.toISOString(), hasta.toISOString()).then(r => r.data),
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
    <div className="u-stack-14">
      <div className="u-row-center-10">
        <Button variant="secondary" aria-label={t('sd_cfg.chg_prev')} onClick={() => setMes(new Date(mes.getFullYear(), mes.getMonth() - 1, 1))}>‹</Button>
        <div className="cambplan-box-1">
          {mes.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}
        </div>
        <Button variant="secondary" aria-label={t('sd_cfg.chg_next')} onClick={() => setMes(new Date(mes.getFullYear(), mes.getMonth() + 1, 1))}>›</Button>
      </div>
      {isLoading ? <Spinner /> : <>
        {(data?.blackouts ?? []).map(b => (
          <div className="cambplan-box-8" key={b.id} role="note" style={{ border: `1px solid ${alpha(COLOR.danger, '50')}`, background: alpha(COLOR.danger, '10'), borderRadius: 8 }}>
            <strong style={{ color: COLOR.danger }}>❄ {b.name}</strong> · {fecha(b.start_at)} → {fecha(b.end_at)}
          </div>
        ))}
        {(data?.releases ?? []).map(r => (
          <div key={r.id} className="cambplan-box-2">
            <strong className="u-accent">🚀 {r.name}{r.version ? ` ${r.version}` : ''}</strong> · {fecha(r.planned_date)} · {t(`sd_cfg.chg_rel_${r.status}`)}
          </div>
        ))}
        {dias.length === 0 ? <div className="u-text3-sm">{t('sd_cfg.chg_empty_month')}</div> : dias.map(([dia, cambios]) => (
          <div key={dia}>
            <div className="cambplan-ls2">{new Date(dia).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}</div>
            <div className="ds-card cambplan-box-3">
              {cambios.map((c, i) => (
                <button className="cambplan-row-4" key={c.id} type="button" onClick={() => onOpen(c.id)}
                  style={{ borderTop: i ? '1px solid var(--surface-4)' : 'none' }}>
                  <span className="cambplan-box-4">
                    {new Date(c.planned_start).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                    {c.planned_end ? `–${new Date(c.planned_end).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}` : ''}
                  </span>
                  <span className="cambplan-txt-1">{c.number}</span>
                  <span className="cambplan-box-5">{c.title}</span>
                  <span className="u-text3-xs">{etiquetaSd('chg_st', c.status)}</span>
                  {c.in_blackout && <span className="cambplan-txt-2" style={{ color: COLOR.danger }}>❄ {t('sd_cfg.chg_in_blackout')}</span>}
                  {c.conflicts.length > 0 && (
                    <span className="cambplan-txt-2" style={{ color: COLOR.warning }}>
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
    queryKey: ['sd-change-blackouts'], queryFn: () => sdChangePlanningApi.blackouts().then(r => r.data),
  })
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['sd-change-blackouts'] }); qc.invalidateQueries({ queryKey: ['sd-change-calendar'] }) }
  const guardar = useMutation({
    mutationFn: ({ id, ...d }: Record<string, unknown>) => id ? sdChangePlanningApi.updateBlackout(String(id), d) : sdChangePlanningApi.createBlackout(d),
    onSuccess: () => { refrescar(); setEditando(null) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const borrar = useMutation({ mutationFn: (id: string) => sdChangePlanningApi.deleteBlackout(id), onSuccess: refrescar })
  return (
    <div className="u-stack-14">
      <div className="cambplan-row-1">
        <div className="u-text3-sm">{t('sd_cfg.chg_blackout_help')}</div>
        <Button onClick={() => setEditando('nueva')}>+ {t('sd_cfg.chg_blackout_new')}</Button>
      </div>
      {isLoading ? <Spinner /> : filas.length === 0 ? <EmptyState icon="❄" title={t('sd_cfg.chg_blackout_empty')} description={t('sd_cfg.chg_blackout_help')} /> : (
        <div className="ds-card cambplan-box-3">
          {filas.map((b, i) => (
            <div className="cambplan-row-5" key={b.id} style={{ borderTop: i ? '1px solid var(--surface-4)' : 'none' }}>
              <strong className="cambplan-box-6">{b.name}</strong>
              <span className="u-text2-sm">{fecha(b.start_at)} → {fecha(b.end_at)}</span>
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
    <div className="u-stack-12">
      <div><label className="cambplan-ls" htmlFor="blk-name">{t('sd_cfg.chg_name')} *</label><input id="blk-name" aria-label={t('sd_cfg.chg_name')} value={f.name} onChange={e => setF({ ...f, name: e.target.value })} className="cambplan-is" /></div>
      <div className="u-grid2-10">
        <div><label className="cambplan-ls" htmlFor="blk-from">{t('sd_cfg.chg_from')} *</label><DateInput id="blk-from" aria-label={t('sd_cfg.chg_from')} withTime value={f.start} onChange={e => setF({ ...f, start: e.target.value })} style={IS} /></div>
        <div><label className="cambplan-ls" htmlFor="blk-to">{t('sd_cfg.chg_to')} *</label><DateInput id="blk-to" aria-label={t('sd_cfg.chg_to')} withTime value={f.end} onChange={e => setF({ ...f, end: e.target.value })} style={IS} /></div>
      </div>
      <div><label className="cambplan-ls" htmlFor="blk-reason">{t('sd_cfg.chg_reason')}</label><textarea id="blk-reason" aria-label={t('sd_cfg.chg_reason')} rows={2} value={f.reason} onChange={e => setF({ ...f, reason: e.target.value })} className="cambplan-is2" /></div>
      <div className="u-actions-10">
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
    queryKey: ['sd-releases'], queryFn: () => sdChangePlanningApi.releases().then(r => r.data),
  })
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['sd-releases'] }); qc.invalidateQueries({ queryKey: ['sd-change-calendar'] }) }
  const guardar = useMutation({
    mutationFn: ({ id, ...d }: Record<string, unknown>) => id ? sdChangePlanningApi.updateRelease(String(id), d) : sdChangePlanningApi.createRelease(d),
    onSuccess: () => { refrescar(); setEditando(null) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const borrar = useMutation({ mutationFn: (id: string) => sdChangePlanningApi.deleteRelease(id), onSuccess: refrescar })
  return (
    <div className="u-stack-14">
      <div className="u-row-end"><Button onClick={() => setEditando('nueva')}>+ {t('sd_cfg.chg_release_new')}</Button></div>
      {isLoading ? <Spinner /> : filas.length === 0 ? <EmptyState icon="🚀" title={t('sd_cfg.chg_release_empty')} description="" /> : filas.map(r => (
        <div key={r.id} className="ds-card cambplan-stack-1">
          <div className="cambplan-row-2">
            <strong className="u-flex1">{r.name}{r.version ? ` · ${r.version}` : ''}</strong>
            <span className="cambplan-txt-3" style={{ color: r.status === 'released' ? COLOR.success : 'var(--text-2)' }}>{t(`sd_cfg.chg_rel_${r.status}`)}</span>
            <span className="u-text3-sm">{fecha(r.planned_date)}</span>
            <Button variant="secondary" onClick={() => setEditando(r)}>{t('common.edit')}</Button>
            <Button variant="secondary" onClick={() => openConfirmGlobal({ message: t('sd_cfg.chg_delete_confirm'), onConfirm: () => borrar.mutate(r.id), danger: true })}>
              <span style={{ color: COLOR.danger }}>{t('common.delete')}</span></Button>
          </div>
          <div className="u-wrap-6">
            {(r.changes ?? []).length === 0 ? <span className="u-text3-sm">{t('sd_cfg.chg_no_changes')}</span>
              : (r.changes ?? []).map(c => (
                <button key={c.id} type="button" onClick={() => onOpen(c.id)} className="cambplan-box-7">
                  {c.number} · {etiquetaSd('chg_st', c.status)}
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
    <div className="u-stack-12">
      <div className="cambplan-grid-1">
        <div><label className="cambplan-ls" htmlFor="rel-name">{t('sd_cfg.chg_name')} *</label><input id="rel-name" aria-label={t('sd_cfg.chg_name')} value={f.name} onChange={e => setF({ ...f, name: e.target.value })} className="cambplan-is" /></div>
        <div><label className="cambplan-ls" htmlFor="rel-version">{t('sd_cfg.chg_version')}</label><input id="rel-version" aria-label={t('sd_cfg.chg_version')} value={f.version} onChange={e => setF({ ...f, version: e.target.value })} className="cambplan-is" /></div>
      </div>
      <div className="u-grid2-10">
        <div><label className="cambplan-ls" htmlFor="rel-date">{t('sd_cfg.chg_planned_date')}</label><DateInput id="rel-date" aria-label={t('sd_cfg.chg_planned_date')} withTime value={f.date} onChange={e => setF({ ...f, date: e.target.value })} style={IS} /></div>
        <div><label className="cambplan-ls" htmlFor="rel-status">{t('sd_cfg.chg_status')}</label>
          <select id="rel-status" aria-label={t('sd_cfg.chg_status')} value={f.status} onChange={e => setF({ ...f, status: e.target.value })} className="cambplan-is">
            {ESTADOS_VERSION.map(s => <option key={s} value={s}>{t(`sd_cfg.chg_rel_${s}`)}</option>)}
          </select></div>
      </div>
      <div><label className="cambplan-ls" htmlFor="rel-notes">{t('sd_cfg.chg_reason')}</label><textarea id="rel-notes" aria-label={t('sd_cfg.chg_reason')} rows={3} value={f.notes} onChange={e => setF({ ...f, notes: e.target.value })} className="cambplan-is2" /></div>
      <div className="u-actions-10">
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
  const { data: cab } = useQuery<SdComiteDeCambio | null>({
    queryKey: ['sd-change-cab', changeId],
    queryFn: () => sdChangePlanningApi.cab(changeId).then(r => r.data).catch(() => null),
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
    <div className="ds-card cambplan-stack-2">
      <div className="cambplan-ls3">{t('sd_cfg.chg_cab')}{cab.quorum ? ` · ${t('sd_cfg.chg_cab_quorum', { n: cab.quorum })}` : ''}</div>
      {cab.meeting && <div className="u-text2-sm">{t('sd_cfg.chg_meeting', { when: fecha(cab.meeting.scheduled_at) })}</div>}
      {cab.votes.map(v => (
        <div key={v.user_id} className="cambplan-row-3">
          <span className="u-flex1">{v.name ?? v.user_id}</span>
          <span className="cambplan-txt-4" style={{ color: color(v.decision) }}>{t(`sd_cfg.chg_vote_${v.decision}`)}</span>
          {v.note && <span className="u-text3">— {v.note}</span>}
        </div>
      ))}
      {puedeVotar && (
        <div className="cambplan-stack-3">
          <textarea aria-label={t('sd_cfg.chg_vote_note')} placeholder={t('sd_cfg.chg_vote_note')} rows={2} value={nota}
            onChange={e => setNota(e.target.value)} className="cambplan-is2" />
          <div className="u-row-8">
            <Button onClick={() => votar.mutate(true)} loading={votar.isPending}>{t('sd_cfg.chg_vote_yes')}</Button>
            <Button variant="secondary" disabled={!nota.trim()} onClick={() => votar.mutate(false)}>{t('sd_cfg.chg_vote_no')}</Button>
          </div>
        </div>
      )}
    </div>
  )
}
