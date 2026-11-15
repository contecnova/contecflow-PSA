/**
 * OKRsPage — Objectives & Key Results
 * Vista árbol: Objectives con Key Results expandibles, progreso en tiempo real, check-ins
 */
import { useState, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { okrsApi, usersApi, projectsApi } from '../services/api'
import type { EstadoDeObjetivo, Objetivo, PeriodoDeObjetivo, ResultadoClave } from '../services/api/tipos-proyectos'
import { Button, Modal, Spinner, EmptyState, Page } from '../components/ui'
import { Trophy, Plus } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { LARGE_PAGE_SIZE } from '../constants/timings'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import DateInput from '../components/ui/DateInput'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import './OKRsPage.css'
type PeriodOpt = 'Q1' | 'Q2' | 'Q3' | 'Q4' | 'H1' | 'H2' | 'annual' | ''

type UserPick = { id: string | number; full_name?: string; username?: string }
type ProjectPick = { id: string | number; code?: string; name?: string }
type DepartmentPick = { id?: string | number; name?: string } | string

type KeyResult = ResultadoClave
type Objective = Objetivo

const PERIOD_OPTS = ['Q1','Q2','Q3','Q4','H1','H2','annual']
const KR_TYPE_CFG: Record<string, { icon: string; label: string; unit: string }> = {
  percentage: { icon:'%', label:'pagina_okr.porcentaje', unit:'%' },
  number:     { icon:'#', label:'pagina_okr.numero',     unit:'' },
  boolean:    { icon:'✓', label:'pagina_okr.si_no',      unit:'' },
  // Moneda: icono y unidad salen de la moneda de la empresa al pintar (fmtMoneda.simbolo).
  currency:   { icon:'¤', label:'pagina_okr.importe',    unit:'' },
}
const STATUS_CFG: Record<string, { color: string; label: string }> = {
  draft:     { color:'var(--text-3)',   label:'pagina_okr.borrador' },
  active:    { color:'var(--accent)',   label:'pagina_okr.activo' },
  completed: { color:'var(--success)',  label:'pagina_okr.completado' },
  cancelled: { color:'var(--danger)',   label:'pagina_okr.cancelado' },
}

function ProgressRing({ pct, size=44, stroke=4, color='var(--accent)' }: { pct: number; size?: number; stroke?: number; color?: string }) {
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const dash = (pct / 100) * circ
  return (
    <svg width={size} height={size} className="okr-svg">
      <circle cx={size/2} cy={size/2} r={r} fill="none"
        stroke="var(--surface-4)" strokeWidth={stroke} />
      <circle cx={size/2} cy={size/2} r={r} fill="none"
        stroke={color} strokeWidth={stroke}
        strokeDasharray={`${dash} ${circ}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${size/2} ${size/2})`} />
      <text x={size/2} y={size/2+1} textAnchor="middle" dominantBaseline="central"
        className={`okr-svg-2 ${size > 40 ? 'okrspage-sx1' : 'okrspage-sx2'}`} style={{ fill: color }}>
        {Math.round(pct)}%
      </text>
    </svg>
  )
}

function KRRow({ kr, _onCheckin, onDelete }: { kr: KeyResult; _onCheckin?: () => void; onDelete: (id: string | number) => void }) {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT()
  const [showCheckin, setShowCheckin] = useState(false)
  const [checkinVal, setCheckinVal] = useState<string | number>(kr.current_value ?? 0)
  const [checkinNote, setCheckinNote] = useState('')
  const toast = useToast()
  const qc = useQueryClient()
  const typeCfg = KR_TYPE_CFG[kr.kr_type ?? ''] || KR_TYPE_CFG.percentage

  const { mutate: submitCheckin, isPending } = useMutation({
    mutationFn: () => okrsApi.checkin(kr.id, { value: parseFloat(String(checkinVal)), note: checkinNote }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['okrs'] })
      setShowCheckin(false)
      toast.success(t('pagina_okr.progreso_actualizado'))
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const pct = kr.progress ?? 0
  const color = pct >= 100 ? 'var(--success)' : pct >= 60 ? 'var(--accent)' : pct >= 30 ? 'var(--warning)' : 'var(--danger)'

  return (
    <div className="okr-box">
      <div className="okr-row">
        <ProgressRing pct={pct} size={36} stroke={3} color={color} />
        <div className="okr-box-2">
          <div className="okr-box-3">{kr.title}</div>
          <div className="u-text2-xs-mt2">
            {kr.kr_type === 'currency' ? fmtMoneda.simbolo : typeCfg.icon} {kr.current_value ?? 0} / {kr.target_value} {kr.unit || (kr.kr_type === 'currency' ? fmtMoneda.simbolo : typeCfg.unit)}
            {kr.owner_name && <span className="okr-label">· {kr.owner_name}</span>}
          </div>
        </div>
        <button onClick={() => setShowCheckin(s => !s)}
          className="okr-btn">
          {t('pagina_okr.actualizar')}
        </button>
        <button onClick={() => onDelete(kr.id)}
          className="okr-btn-2">×</button>
      </div>
      {showCheckin && (
        <div className="okr-row-2">
          <div className="okr-box-4">
            <input type="number" aria-label={t('pagina_okr.nuevo_valor_actual', { current_value: kr.current_value })} value={checkinVal}
              onChange={e => setCheckinVal(e.target.value)}
              className="okr-input"
              placeholder={t('pagina_okr.nuevo_valor_actual', { current_value: kr.current_value })} />
          </div>
          <div className="okr-box-5">
            <input aria-label={t('okrs.nota_del_check_in')} value={checkinNote} onChange={e => setCheckinNote(e.target.value)}
              className="okr-input"
              placeholder={t('okrs.nota_del_check_in')} />
          </div>
          <Button onClick={() => submitCheckin()} disabled={isPending} loading={isPending} size="sm">
            {t('pagina_okr.guardar')}
          </Button>
          <Button variant="secondary" onClick={() => setShowCheckin(false)} size="sm">✕</Button>
        </div>
      )}
    </div>
  )
}

function ObjectiveCard({ obj, onEdit, onAddKR, onDeleteObj, onDeleteKR }: {
  obj: Objective
  onEdit: (obj: Objective) => void
  onAddKR: (obj: Objective) => void
  onDeleteObj: (id: string | number) => void
  onDeleteKR: (id: string | number) => void
}) {
  const t = useAppT()
  const [expanded, setExpanded] = useState(true)
  const statusCfg = STATUS_CFG[obj.status ?? ''] || STATUS_CFG.draft
  const pct = obj.progress ?? 0
  const color = pct >= 100 ? 'var(--success)' : pct >= 60 ? 'var(--accent)' : pct >= 30 ? 'var(--warning)' : 'var(--danger)'

  return (
    <div className="okr-box-6 okrspage-sx3" style={{ border:`1px solid ${alpha(color, '25')}` }}>
      <div className="okr-row-3">
        <button onClick={() => setExpanded(s => !s)}
          className="okr-btn-3">
          {expanded ? '▾' : '▸'}
        </button>
        <ProgressRing pct={pct} size={48} stroke={4} color={color} />
        <div className="okr-box-2">
          <div className="okr-box-7">{obj.title}</div>
          <div className="okr-row-4">
            <span className="okr-label-2" style={{ color: statusCfg.color }}>
              {t(statusCfg.label)}
            </span>
            <span className="u-text3-xs">
              {obj.period} {obj.year}
            </span>
            {obj.owner_name && (
              <span className="u-text2-xs">· {obj.owner_name}</span>
            )}
            <span className="u-text3-xs">
              {obj.key_results?.length || 0}{' '}{t('pagina_okr.krs')}
            </span>
          </div>
        </div>
        <div className="okr-row-5">
          <button onClick={() => onAddKR(obj)}
            className="okr-btn">
            {t('pagina_okr.kr')}
          </button>
          <button onClick={() => onEdit(obj)}
            className="okr-btn-4">✏</button>
          <button onClick={() => onDeleteObj(obj.id)}
            className="okr-btn-5">🗑</button>
        </div>
      </div>

      {expanded && (obj.key_results?.length ?? 0) > 0 && (
        <div className="okr-box-8">
          {(obj.key_results ?? []).map((kr) => (
            <KRRow key={kr.id} kr={kr} onDelete={onDeleteKR} />
          ))}
        </div>
      )}
      {expanded && (!obj.key_results || obj.key_results.length === 0) && (
        <div className="okr-box-9">
          {t('okrs.sin_key_results_pulsa_quot_kr_quot')}
        </div>
      )}
    </div>
  )
}

function ObjModal({ obj, onClose }: { obj: Objective | null; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const isEdit = !!obj?.id
  const [form, setForm] = useState({
    title: obj?.title || '', description: obj?.description || '',
    period: obj?.period || 'Q1', year: obj?.year || new Date().getFullYear(),
    status: obj?.status || 'active',
    owner_id: obj?.owner_id || '',
    project_id: obj?.project_id || '',
    team_id: obj?.team_id || '',
  })

  const { data: users = [] } = useQuery<UserPick[]>({
    queryKey: ['okr-users-pick'],
    queryFn: () => usersApi.list({ page_size: LARGE_PAGE_SIZE }).then(r => (r.data ?? []) as UserPick[]),
  })
  const { data: projects = [] } = useQuery<ProjectPick[]>({
    queryKey: ['okr-projects-pick'],
    queryFn: () => projectsApi.list({ page_size: LARGE_PAGE_SIZE }).then(r => (r.data ?? []) as ProjectPick[]),
  })
  const { data: departments = [] } = useQuery<DepartmentPick[]>({
    queryKey: ['okr-departments-pick'],
    queryFn: async () => {
      try {
        const { settingsApi } = await import('../services/settingsApi')
        const r = await settingsApi.getDepartments()
        return (Array.isArray(r.data) ? r.data : []) as DepartmentPick[]
      } catch { return [] }
    },
  })

  const { mutate, isPending } = useMutation({
    mutationFn: () => {
      // Limpiamos cadenas vacías → null para que el backend no falle al castear UUIDs.
      const payload = Object.fromEntries(
        Object.entries(form).map(([k, v]) => [k, v === '' ? null : v])
      ) as Record<string, unknown>
      return isEdit && obj ? okrsApi.update(obj.id, payload) : okrsApi.create(payload)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['okrs'] }); onClose() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? t('pagina_okr.editar_objetivo') : t('pagina_okr.nuevo_objetivo')} width={580}>
      <div className="ds-stack">
        <div className="ds-field">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="ds-field__label">{t('okrs.titulo')}</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
            className="ds-input" placeholder={t('okrs.ej_incrementar_retencion_de_clientes')} autoFocus />
        </div>
        <div className="ds-field">
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="ds-field__label">{t('okrs.descripcion')}</label>
          <textarea id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            rows={2} className="ds-input okr-input-2"
            placeholder={t('okrs.que_problema_resuelve_y_como_se_medira')} />
        </div>

        {/* Asignaciones */}
        <div className="okr-grid">
          <div className="ds-field">
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="ds-field__label">{t('pagina_okr.responsable')}</label>
            <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.owner_id} onChange={e => setForm(f => ({ ...f, owner_id: e.target.value }))}
              className="ds-input">
              <option value="">{t('okrs.sin_asignar')}</option>
              {users.map((u) => <option key={u.id} value={String(u.id)}>{u.full_name || u.username}</option>)}
            </select>
            <div className="ds-field__hint">{t('okrs.persona_que_rinde_cuentas_del_objetivo')}</div>
          </div>
          <div className="ds-field">
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="ds-field__label">{t('pagina_okr.departamento_equipo')}</label>
            <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.team_id} onChange={e => setForm(f => ({ ...f, team_id: e.target.value }))}
              className="ds-input">
              <option value="">{t('okrs.compania')}</option>
              {departments.map((d) => {
                const dep = typeof d === 'string' ? { id: d, name: d } : d
                return <option key={String(dep.id || dep.name || '')} value={String(dep.id || dep.name || '')}>{dep.name || String(dep.id || '')}</option>
              })}
            </select>
            <div className="ds-field__hint">{t('okrs.vacio_okr_de_empresa')}</div>
          </div>
        </div>

        <div className="ds-field">
          <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="ds-field__label">{t('pagina_okr.proyecto_vinculado')}</label>
          <select id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.project_id} onChange={e => setForm(f => ({ ...f, project_id: e.target.value }))}
            className="ds-input">
            <option value="">{t('pagina_okr.ninguno')}</option>
            {projects.map((p) => <option key={p.id} value={String(p.id)}>{p.code ? `${p.code} · ` : ''}{p.name}</option>)}
          </select>
          <div className="ds-field__hint">{t('okrs.si_lo_vinculas_los_krs_pueden_sincronizar')}</div>
        </div>

        {/* Período + estado */}
        <div className="okr-grid-2">
          <div className="ds-field">
            <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="ds-field__label">{t('okrs.periodo')}</label>
            <select id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.period} onChange={e => setForm(f => ({ ...f, period: e.target.value as PeriodoDeObjetivo }))} className="ds-input">
              {PERIOD_OPTS.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div className="ds-field">
            <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="ds-field__label">{t('okrs.year')}</label>
            <input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} type="number" value={form.year}
              onChange={e => setForm(f => ({ ...f, year: parseInt(e.target.value) || f.year }))}
              className="ds-input" />
          </div>
          <div className="ds-field">
            <label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} className="ds-field__label">{t('pagina_okr.estado')}</label>
            <select id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value as EstadoDeObjetivo }))} className="ds-input">
              {Object.entries(STATUS_CFG).map(([v, c]) => <option key={v} value={v}>{t(c.label)}</option>)}
            </select>
          </div>
        </div>

        <div className="okr-row-6">
          <Button variant="secondary" onClick={onClose}>{t('pagina_okr.cancelar')}</Button>
          <Button onClick={() => mutate()} disabled={isPending || !form.title} loading={isPending}>
            {isEdit ? t('pagina_okr.guardar_cambios') : t('pagina_okr.crear_objetivo')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function KRModal({ objective, onClose }: { objective: Objective; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState({
    objective_id: objective.id, title: '', kr_type: 'percentage',
    target_value: 100, current_value: 0, unit: '',
    owner_id: '', due_date: '', notes: '',
  })

  const { data: users = [] } = useQuery<UserPick[]>({
    queryKey: ['okr-users-pick'],
    queryFn: () => usersApi.list({ page_size: LARGE_PAGE_SIZE }).then(r => (r.data ?? []) as UserPick[]),
  })

  const { mutate, isPending } = useMutation({
    mutationFn: () => {
      const payload = Object.fromEntries(
        Object.entries(form).map(([k, v]) => [k, v === '' ? null : v])
      ) as Record<string, unknown>
      // El KR siempre vive bajo un objective: aseguramos el id por si la limpieza lo borrara
      payload.objective_id = objective.id
      return okrsApi.createKR(payload)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['okrs'] }); onClose() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <Modal open onClose={onClose}
      title={t('okrs.nuevo_key_result')}
      subtitle={t('pagina_okr.para_el_objetivo', { title: objective.title })}
      width={560}>
      <div className="ds-stack">
        <div className="ds-field">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="ds-field__label">{t('okrs.descripcion_del_resultado')}</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
            className="ds-input" placeholder={t('pagina_okr.ej_aumentar_nps_a_60')} autoFocus />
        </div>
        <div className="okr-grid-2">
          <div className="ds-field">
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="ds-field__label">{t('pagina_okr.tipo')}</label>
            <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.kr_type} onChange={e => setForm(f => ({ ...f, kr_type: e.target.value }))} className="ds-input">
              {Object.entries(KR_TYPE_CFG).map(([v, c]) => <option key={v} value={v}>{t(c.label)}</option>)}
            </select>
          </div>
          <div className="ds-field">
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="ds-field__label">{t('pagina_okr.meta')}</label>
            <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" value={form.target_value}
              onChange={e => setForm(f => ({ ...f, target_value: parseFloat(e.target.value) || 0 }))}
              className="ds-input" />
          </div>
          <div className="ds-field">
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="ds-field__label">{t('pagina_okr.unidad')}</label>
            <input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.unit} onChange={e => setForm(f => ({ ...f, unit: e.target.value }))}
              className="ds-input" placeholder={t('pagina_okr.puntos_nps')} />
          </div>
        </div>
        <div className="okr-grid">
          <div className="ds-field">
            <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="ds-field__label">{t('okrs.responsable_del_kr')}</label>
            <select id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.owner_id} onChange={e => setForm(f => ({ ...f, owner_id: e.target.value }))}
              className="ds-input">
              <option value="">{t('okrs.hereda_del_objetivo')}</option>
              {users.map((u) => <option key={u.id} value={String(u.id)}>{u.full_name || u.username}</option>)}
            </select>
          </div>
          <div className="ds-field">
            <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="ds-field__label">{t('okrs.fecha_limite')}</label>
            <DateInput id={`${idCampo}-6`} value={form.due_date}
              onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))}
              className="ds-input" />
          </div>
        </div>
        <div className="ds-field">
          <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="ds-field__label">{t('pagina_okr.notas_opcional')}</label>
          <textarea id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
            rows={2} className="ds-input okr-input-2"
            placeholder={t('okrs.detalles_criterios_de_exito_dependencias')} />
        </div>
        <div className="okr-row-7">
          <Button variant="secondary" onClick={onClose}>{t('pagina_okr.cancelar')}</Button>
          <Button onClick={() => mutate()} disabled={isPending || !form.title} loading={isPending}>
            <Plus size={13} /> {t('okrs.add_kr')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function OKRsPage() {
  const t = useAppT() as (key: string) => string
  const toast = useToast()
  const qc = useQueryClient()
  const [year, setYear] = useState(new Date().getFullYear())
  const [period, setPeriod] = useState<PeriodOpt>('')
  const [showObjModal, setShowObjModal] = useState(false)
  const [editingObj, setEditingObj] = useState<Objective | null>(null)
  const [addKRFor, setAddKRFor] = useState<Objective | null>(null)

  const { data: objectives = [], isLoading } = useQuery({
    queryKey: ['okrs', year, period],
    queryFn: () => okrsApi.list({ year, ...(period && { period }) }).then(r => r.data),
  })

  const { mutate: deleteObj } = useMutation({
    mutationFn: (id: string | number) => okrsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['okrs'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: deleteKR } = useMutation({
    mutationFn: (id: string | number) => okrsApi.deleteKR(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['okrs'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const totalObjs = objectives.length
  const avgProgress = totalObjs > 0
    ? Math.round(objectives.reduce((s, o) => s + (o.progress || 0), 0) / totalObjs)
    : 0
  const onTrack = objectives.filter((o) => (o.progress || 0) >= 60).length

  return (
    <Page
      icon={<Trophy size={18} />}
      title={t('okrs.title')}
      subtitle={t('okrs.subtitle')}
      actions={
        <div className="okr-row-8">
          <select value={period} onChange={e => setPeriod(e.target.value as PeriodOpt)}
            className="ds-input okr-input-3">
            <option value="">{t('okrs.todos_los_periodos')}</option>
            {PERIOD_OPTS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <select value={year} onChange={e => setYear(parseInt(e.target.value))}
            className="ds-input okr-input-4">
            {[2024, 2025, 2026].map(y => <option key={y} value={y}>{y}</option>)}
          </select>
          <Button onClick={() => { setEditingObj(null); setShowObjModal(true) }}>
            <Plus size={13} /> {t('okrs.new_objective')}
          </Button>
        </div>
      }
    >
      {/* KPI cards */}
      <div className="ds-grid-stats">
        {[
          { label: t('pagina_okr.objetivos_activos'), value: totalObjs, color: 'var(--accent)' },
          { label: t('pagina_okr.progreso_medio'),    value: `${avgProgress}%`, color: avgProgress >= 60 ? 'var(--success)' : 'var(--warning)' },
          { label: t('pagina_okr.en_camino_60'),  value: onTrack, color: 'var(--success)' },
        ].map(kpi => (
          <div key={kpi.label} className="ds-card okr-box-10">
            <div className="okr-box-11" style={{ color: kpi.color }}>{kpi.value}</div>
            <div className="ds-eyebrow">{kpi.label}</div>
          </div>
        ))}
      </div>

      {isLoading ? <Spinner /> : objectives.length === 0 ? (
        <EmptyState svgIcon={<Trophy size={36} />} title={t('okrs.sin_objetivos')}
          description={t('pagina_okr.crea_tu_primer_okr')} />
      ) : (
        <div data-export-table="okrs-list" className="u-stack-12">
          {objectives.map((obj) => (
            <ObjectiveCard key={obj.id} obj={obj}
              onEdit={(o) => { setEditingObj(o); setShowObjModal(true) }}
              onAddKR={setAddKRFor}
              onDeleteObj={(id) => { openConfirmGlobal({ message: t('pagina_okr.eliminar_objetivo_y_krs'), onConfirm: () => deleteObj(id), danger: true }) }}
              onDeleteKR={(id) => { openConfirmGlobal({ message: t('pagina_okr.eliminar_kr'), onConfirm: () => deleteKR(id), danger: true }) }}
            />
          ))}
        </div>
      )}

      {showObjModal && (
        <ObjModal obj={editingObj} onClose={() => { setShowObjModal(false); setEditingObj(null) }} />
      )}
      {addKRFor && <KRModal objective={addKRFor} onClose={() => setAddKRFor(null)} />}
    </Page>
  )
}
