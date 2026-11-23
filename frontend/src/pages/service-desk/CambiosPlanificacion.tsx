/**
 * Planificación de cambios: calendario (con choques y congelaciones),
 * versiones, ventanas de congelación y el comité de cada cambio.
 *
 * 16-11-2026 (pasada de diseño): iconos lucide en lugar de «❄ 🚀 ⚠ ‹ ›»;
 * estados con <StatusBadge>; fechas con el formateador de la app (antes el
 * idioma del navegador); vacíos con <EmptyState> e icono (antes texto gris);
 * «+» de texto fuera de los botones; borrar con la variante `danger`; campos
 * con `ds-input`; el modal de edición dice «Editar …» (antes «Nueva …»).
 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CalendarDays, ChevronLeft, ChevronRight, Package, Pencil, Plus, Snowflake, Trash2 } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr, fmtDateTime, fmtMonth, formateadorDeFecha } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, EmptyState, IconButton, Modal, Pulsable, Select, Spinner, StatusBadge, Input, Textarea } from '../../components/ui'
import type { StatusBadgeKind } from '../../components/ui/StatusBadge'
import { sdChangePlanningApi } from '../../services/api'
import type { SdCambioEnCalendario, SdComiteDeCambio, SdCongelacion, SdVersionDeCambios } from '../../services/api/tipos-sd'
import { etiquetaSd } from './sdUtils'
import DateInput from '../../components/ui/DateInput'
import './CambiosPlanificacion.css'

type CambioCal = SdCambioEnCalendario
type Congelacion = SdCongelacion
type Version = SdVersionDeCambios

const FORMATO_CORTO: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }
const FORMATO_DIA: Intl.DateTimeFormatOptions = { weekday: 'long', day: 'numeric', month: 'long' }
const FORMATO_HORA: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit' }

const fecha = (iso?: string | null) => iso ? formateadorDeFecha(FORMATO_CORTO).format(new Date(iso)) : '—'
const hora = (iso: string) => formateadorDeFecha(FORMATO_HORA).format(new Date(iso))
const aLocal = (iso?: string | null) => iso ? new Date(iso).toISOString().slice(0, 16) : ''
const aIso = (local: string) => local ? new Date(local).toISOString() : null

const KIND_VERSION: Record<string, StatusBadgeKind> = { planned: 'neutral', in_progress: 'accent', released: 'success', cancelled: 'neutral' }
const KIND_VOTO: Record<string, StatusBadgeKind> = { approved: 'success', rejected: 'danger', pending: 'neutral' }

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
      <div className="cambplan-nav">
        <IconButton ariaLabel={t('sd_cfg.chg_prev')} onClick={() => setMes(new Date(mes.getFullYear(), mes.getMonth() - 1, 1))}><ChevronLeft size={16} aria-hidden /></IconButton>
        <div className="cambplan-box-1">{fmtMonth(mes)}</div>
        <IconButton ariaLabel={t('sd_cfg.chg_next')} onClick={() => setMes(new Date(mes.getFullYear(), mes.getMonth() + 1, 1))}><ChevronRight size={16} aria-hidden /></IconButton>
      </div>
      {isLoading ? <Spinner /> : <>
        {(data?.blackouts ?? []).map(b => (
          <div className="cambplan-aviso cambplan-aviso--danger" key={b.id} role="note">
            <Snowflake size={14} aria-hidden className="cambplan-aviso__icono" />
            <span><strong>{b.name}</strong> · {fecha(b.start_at)} → {fecha(b.end_at)}</span>
          </div>
        ))}
        {(data?.releases ?? []).map(r => (
          <div key={r.id} className="cambplan-aviso">
            <Package size={14} aria-hidden className="cambplan-aviso__icono cambplan-aviso__icono--accent" />
            <span><strong>{r.name}{r.version ? ` ${r.version}` : ''}</strong> · {fecha(r.planned_date)}</span>
            <StatusBadge kind={KIND_VERSION[r.status] ?? 'neutral'} caps={false}>{t(`sd_cfg.chg_rel_${r.status}`)}</StatusBadge>
          </div>
        ))}
        {dias.length === 0 ? <EmptyState icon={<CalendarDays size={28} />} title={t('sd_cfg.chg_empty_month')} /> : dias.map(([dia, cambios]) => (
          <div key={dia}>
            <div className="cambplan-ls2">{formateadorDeFecha(FORMATO_DIA).format(new Date(dia))}</div>
            <div className="ds-card cambplan-box-3">
              {cambios.map(c => (
                <Pulsable className="cambplan-row-4" key={c.id} onClick={() => onOpen(c.id)}>
                  <span className="cambplan-box-4">
                    {hora(c.planned_start)}
                    {c.planned_end ? `–${hora(c.planned_end)}` : ''}
                  </span>
                  <span className="cambplan-txt-1">{c.number}</span>
                  <span className="cambplan-box-5">{c.title}</span>
                  <StatusBadge caps={false}>{etiquetaSd('chg_st', c.status)}</StatusBadge>
                  {c.in_blackout && <StatusBadge kind="danger" caps={false}><Snowflake size={11} aria-hidden /> {t('sd_cfg.chg_in_blackout')}</StatusBadge>}
                  {c.conflicts.length > 0 && (
                    <StatusBadge kind="warning" caps={false}>
                      <AlertTriangle size={11} aria-hidden /> {t('sd_cfg.chg_conflict', { list: c.conflicts.map(x => `${x.number} (${x.cis.join(', ')})`).join(' · ') })}
                    </StatusBadge>
                  )}
                </Pulsable>
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
  const nueva = <Button icon={<Plus size={14} />} onClick={() => setEditando('nueva')}>{t('sd_cfg.chg_blackout_new')}</Button>
  return (
    <div className="u-stack-14">
      <div className="cambplan-row-1">
        <div className="u-text2-sm">{t('sd_cfg.chg_blackout_help')}</div>
        {nueva}
      </div>
      {isLoading ? <Spinner /> : filas.length === 0 ? <EmptyState icon={<Snowflake size={28} />} title={t('sd_cfg.chg_blackout_empty')} description={t('changemanagement.congelaciones_vacio_desc')} action={nueva} /> : (
        <div className="ds-card cambplan-box-3">
          {filas.map(b => (
            <div className="cambplan-row-5" key={b.id}>
              <strong className="cambplan-box-6">{b.name}</strong>
              <span className="u-text2-sm">{fecha(b.start_at)} → {fecha(b.end_at)}</span>
              <Button size="sm" variant="secondary" icon={<Pencil size={13} />} onClick={() => setEditando(b)}>{t('common.edit')}</Button>
              <Button size="sm" variant="danger" icon={<Trash2 size={13} />} onClick={() => openConfirmGlobal({ message: t('sd_cfg.chg_delete_confirm'), onConfirm: () => borrar.mutate(b.id), danger: true })}>{t('common.delete')}</Button>
            </div>
          ))}
        </div>
      )}
      {editando && (
        <Modal open title={editando === 'nueva' ? t('sd_cfg.chg_blackout_new') : t('changemanagement.editar_congelacion')} onClose={() => setEditando(null)}>
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
      <div><label className="cambplan-ls" htmlFor="blk-name">{t('sd_cfg.chg_name')} *</label><Input id="blk-name" aria-label={t('sd_cfg.chg_name')} value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></div>
      <div className="u-grid2-10">
        <div><label className="cambplan-ls" htmlFor="blk-from">{t('sd_cfg.chg_from')} *</label><DateInput id="blk-from" aria-label={t('sd_cfg.chg_from')} withTime value={f.start} onChange={e => setF({ ...f, start: e.target.value })} className="ds-input" /></div>
        <div><label className="cambplan-ls" htmlFor="blk-to">{t('sd_cfg.chg_to')} *</label><DateInput id="blk-to" aria-label={t('sd_cfg.chg_to')} withTime value={f.end} onChange={e => setF({ ...f, end: e.target.value })} className="ds-input" /></div>
      </div>
      <div><label className="cambplan-ls" htmlFor="blk-reason">{t('sd_cfg.chg_reason')}</label><Textarea id="blk-reason" aria-label={t('sd_cfg.chg_reason')} rows={2} value={f.reason} onChange={e => setF({ ...f, reason: e.target.value })} inputClassName="cambplan-textarea" /></div>
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
  const nueva = <Button icon={<Plus size={14} />} onClick={() => setEditando('nueva')}>{t('sd_cfg.chg_release_new')}</Button>
  return (
    <div className="u-stack-14">
      {filas.length > 0 && <div className="u-row-end">{nueva}</div>}
      {isLoading ? <Spinner /> : filas.length === 0 ? <EmptyState icon={<Package size={28} />} title={t('sd_cfg.chg_release_empty')} description={t('changemanagement.versiones_vacio_desc')} action={nueva} /> : filas.map(r => (
        <div key={r.id} className="ds-card cambplan-stack-1">
          <div className="cambplan-row-2">
            <strong className="cambplan-version-nombre">{r.name}{r.version ? ` · ${r.version}` : ''}</strong>
            <StatusBadge kind={KIND_VERSION[r.status] ?? 'neutral'} caps={false}>{t(`sd_cfg.chg_rel_${r.status}`)}</StatusBadge>
            <span className="u-text2-sm">{fmtDateTime(r.planned_date)}</span>
            <Button size="sm" variant="secondary" icon={<Pencil size={13} />} onClick={() => setEditando(r)}>{t('common.edit')}</Button>
            <Button size="sm" variant="danger" icon={<Trash2 size={13} />} onClick={() => openConfirmGlobal({ message: t('sd_cfg.chg_delete_confirm'), onConfirm: () => borrar.mutate(r.id), danger: true })}>{t('common.delete')}</Button>
          </div>
          <div className="u-wrap-6">
            {(r.changes ?? []).length === 0 ? <span className="u-text2-sm">{t('sd_cfg.chg_no_changes')}</span>
              : (r.changes ?? []).map(c => (
                <Pulsable key={c.id} onClick={() => onOpen(c.id)} className="cambplan-box-7">
                  {c.number} · {etiquetaSd('chg_st', c.status)}
                </Pulsable>
              ))}
          </div>
        </div>
      ))}
      {editando && (
        <Modal open title={editando === 'nueva' ? t('sd_cfg.chg_release_new') : t('changemanagement.editar_version')} onClose={() => setEditando(null)}>
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
        <div><label className="cambplan-ls" htmlFor="rel-name">{t('sd_cfg.chg_name')} *</label><Input id="rel-name" aria-label={t('sd_cfg.chg_name')} value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></div>
        <div><label className="cambplan-ls" htmlFor="rel-version">{t('sd_cfg.chg_version')}</label><Input id="rel-version" aria-label={t('sd_cfg.chg_version')} value={f.version} onChange={e => setF({ ...f, version: e.target.value })} /></div>
      </div>
      <div className="u-grid2-10">
        <div><label className="cambplan-ls" htmlFor="rel-date">{t('sd_cfg.chg_planned_date')}</label><DateInput id="rel-date" aria-label={t('sd_cfg.chg_planned_date')} withTime value={f.date} onChange={e => setF({ ...f, date: e.target.value })} className="ds-input" /></div>
        <div><label className="cambplan-ls" htmlFor="rel-status">{t('sd_cfg.chg_status')}</label>
          <Select suelto placeholder={false} id="rel-status" aria-label={t('sd_cfg.chg_status')} value={f.status} onChange={e => setF({ ...f, status: e.target.value })}>
            {ESTADOS_VERSION.map(s => <option key={s} value={s}>{t(`sd_cfg.chg_rel_${s}`)}</option>)}
          </Select></div>
      </div>
      <div><label className="cambplan-ls" htmlFor="rel-notes">{t('changemanagement.notas')}</label><Textarea id="rel-notes" aria-label={t('changemanagement.notas')} rows={3} value={f.notes} onChange={e => setF({ ...f, notes: e.target.value })} inputClassName="cambplan-textarea" /></div>
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
    queryFn: () => sdChangePlanningApi.cab(changeId).then(r => r.data),
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
  return (
    <div className="ds-card cambplan-stack-2">
      <div className="cambplan-ls3">{t('sd_cfg.chg_cab')}{cab.quorum ? ` · ${t('sd_cfg.chg_cab_quorum', { n: cab.quorum })}` : ''}</div>
      {cab.meeting && <div className="u-text2-sm">{t('sd_cfg.chg_meeting', { when: fecha(cab.meeting.scheduled_at) })}</div>}
      {cab.votes.map(v => (
        <div key={v.user_id} className="cambplan-row-3">
          <span className="cambplan-voto-nombre">{v.name ?? v.user_id}</span>
          <StatusBadge kind={KIND_VOTO[v.decision] ?? 'neutral'} caps={false}>{t(`sd_cfg.chg_vote_${v.decision}`)}</StatusBadge>
          {v.note && <span className="u-text2-sm">— {v.note}</span>}
        </div>
      ))}
      {puedeVotar && (
        <div className="cambplan-stack-3">
          <Textarea aria-label={t('sd_cfg.chg_vote_note')} placeholder={t('sd_cfg.chg_vote_note')} rows={2} value={nota} onChange={e => setNota(e.target.value)} inputClassName="cambplan-textarea" />
          <div className="u-row-8">
            <Button onClick={() => votar.mutate(true)} loading={votar.isPending}>{t('sd_cfg.chg_vote_yes')}</Button>
            <Button variant="secondary" disabled={!nota.trim()} onClick={() => votar.mutate(false)}>{t('sd_cfg.chg_vote_no')}</Button>
          </div>
        </div>
      )}
    </div>
  )
}
