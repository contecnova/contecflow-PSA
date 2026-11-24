/**
 * OKRsPage — Objectives & Key Results
 * Vista árbol: Objectives con Key Results expandibles, progreso en tiempo real, check-ins
 *
 * 16-11-2026: filtros (periodo y año) fuera de la cabecera, en una barra
 * bajo ella; KPIs con KpiCard (antes cifra monoespaciada propia); objetivos en
 * Card sin borde de color; acciones con iconos lucide e IconButton (antes
 * símbolos y emojis); estado con StatusBadge; vacíos con EmptyState; "annual"
 * traducido; años del filtro calculados (antes fijos 2024–2026).
 */
import { type CSSProperties, useState, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { okrsApi, usersApi, projectsApi } from '../services/api'
import type { EstadoDeObjetivo, Objetivo, PeriodoDeObjetivo, ResultadoClave } from '../services/api/tipos-proyectos'
import { Button, Card, IconButton, KpiCard, Modal, Select, Spinner, EmptyState, Page, useErroresDeCampo, Input, Textarea } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import type { StatusBadgeKind } from '../components/ui/StatusBadge'
import { CheckCircle2, ChevronDown, ChevronRight, Pencil, Plus, Target, Trash2, TrendingUp, Trophy, X, ListChecks } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { extractErr } from '../utils/helpers'
import { useTono } from '../hooks/useOrgSettings'
import type { Tono } from '../utils/umbrales'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { LARGE_PAGE_SIZE } from '../constants/timings'
import { useAppT } from '../i18n/AppLangContext'
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
/** Q1…H2 se leen igual en los tres idiomas; «annual» es un valor del backend y se traduce. */
const etiquetaPeriodo = (p: string | null | undefined, t: (k: string) => string) => (p === 'annual' ? t('pagina_okr.anual') : (p ?? ''))

const KR_TYPE_CFG: Record<string, { icon: string; label: string; unit: string }> = {
  percentage: { icon:'%', label:'pagina_okr.porcentaje', unit:'%' },
  number:     { icon:'#', label:'pagina_okr.numero',     unit:'' },
  boolean:    { icon:'', label:'pagina_okr.si_no',      unit:'' },
  // Moneda: icono y unidad salen de la moneda de la empresa al pintar (fmtMoneda.simbolo).
  currency:   { icon:'', label:'pagina_okr.importe',    unit:'' },
}
const STATUS_CFG: Record<string, { kind: StatusBadgeKind; label: string }> = {
  draft:     { kind: 'neutral', label:'pagina_okr.borrador' },
  active:    { kind: 'accent',  label:'pagina_okr.activo' },
  completed: { kind: 'success', label:'pagina_okr.completado' },
  cancelled: { kind: 'danger',  label:'pagina_okr.cancelado' },
}

/** 19-11-2026: aviso y crítico con UMBRAL_OKR_* de la empresa (antes 60/30 aquí); 100 % = conseguido. */
const colorDeProgreso = (pct: number, tono: Tono | undefined) => pct >= 100 ? 'var(--success)' : tono === 'success' ? 'var(--accent)' : `var(--${tono ?? 'danger'})`

function ProgressRing({ pct, size=44, stroke=4, color='var(--accent)' }: { pct: number; size?: number; stroke?: number; color?: string }) {
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const dash = (pct / 100) * circ
  return (
    <svg width={size} height={size} className="okr-anillo" aria-hidden>
      <circle cx={size/2} cy={size/2} r={r} fill="none"
        stroke="var(--surface-4)" strokeWidth={stroke} />
      <circle cx={size/2} cy={size/2} r={r} fill="none"
        stroke={color} strokeWidth={stroke}
        strokeDasharray={`${dash} ${circ}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${size/2} ${size/2})`} />
      <text x={size/2} y={size/2+1} textAnchor="middle" dominantBaseline="central"
        className={`okr-anillo__texto${size > 40 ? ' okr-anillo__texto--grande' : ''}`} style={{ '--okr-color': color } as CSSProperties}>
        {Math.round(pct)}%
      </text>
    </svg>
  )
}

function KRRow({ kr, onDelete }: { kr: KeyResult; onDelete: (id: string | number) => void }) {
  const fmtMoneda = useFormatoMoneda()
  const tono = useTono()
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
  const unidad = kr.unit || (kr.kr_type === 'currency' ? fmtMoneda.simbolo : typeCfg.unit)

  return (
    <div className="okr-kr">
      <div className="okr-kr__fila">
        <ProgressRing pct={pct} size={36} stroke={3} color={colorDeProgreso(pct, tono('okr', pct))} />
        <div className="u-flex1-min0">
          <div className="okr-kr__titulo">{kr.title}</div>
          <div className="okr-kr__meta">
            {kr.current_value ?? 0} / {kr.target_value} {unidad}
            {kr.owner_name && <span> · {kr.owner_name}</span>}
          </div>
        </div>
        <Button size="sm" variant="secondary" icon={<TrendingUp size={13} />} onClick={() => setShowCheckin(s => !s)}>
          {t('pagina_okr.actualizar')}
        </Button>
        <IconButton variante="caja" tono="peligro" ariaLabel={t('pagina_okr.eliminar_kr_corto')} onClick={() => onDelete(kr.id)}><Trash2 size={14} /></IconButton>
      </div>
      {showCheckin && (
        <div className="okr-kr__checkin">
          <Input type="number" aria-label={t('pagina_okr.nuevo_valor_actual', { current_value: kr.current_value })} value={checkinVal}
            onChange={e => setCheckinVal(e.target.value)}
            className="okr-kr__valor"
            placeholder={t('pagina_okr.nuevo_valor_actual', { current_value: kr.current_value })} />
          <Input aria-label={t('okrs.nota_del_check_in')} value={checkinNote} onChange={e => setCheckinNote(e.target.value)}
            className="okr-kr__nota"
            placeholder={t('okrs.nota_del_check_in')} />
          <Button onClick={() => submitCheckin()} loading={isPending} size="sm">
            {t('pagina_okr.guardar')}
          </Button>
          <IconButton ariaLabel={t('pagina_okr.cancelar')} onClick={() => setShowCheckin(false)}><X size={14} /></IconButton>
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
  const tono = useTono()
  const [expanded, setExpanded] = useState(true)
  const statusCfg = STATUS_CFG[obj.status ?? ''] || STATUS_CFG.draft
  const pct = obj.progress ?? 0

  return (
    <Card>
      <div className="okr-obj">
        <IconButton ariaLabel={expanded ? t('pagina_okr.contraer') : t('pagina_okr.expandir')} aria-expanded={expanded}
          onClick={() => setExpanded(s => !s)}>
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </IconButton>
        <ProgressRing pct={pct} size={48} stroke={4} color={colorDeProgreso(pct, tono('okr', pct))} />
        <div className="u-flex1-min0">
          <div className="okr-obj__titulo">{obj.title}</div>
          <div className="okr-obj__meta">
            <StatusBadge kind={statusCfg.kind} caps={false}>{t(statusCfg.label)}</StatusBadge>
            <span>{etiquetaPeriodo(obj.period, t)} {obj.year}</span>
            {obj.owner_name && <span>· {obj.owner_name}</span>}
            <span>· {obj.key_results?.length || 0}{' '}{t('pagina_okr.krs')}</span>
          </div>
        </div>
        <div className="okr-obj__acciones">
          <Button size="sm" variant="secondary" icon={<Plus size={13} />} onClick={() => onAddKR(obj)}>
            {t('pagina_okr.kr')}
          </Button>
          <IconButton variante="caja" ariaLabel={t('pagina_okr.editar_objetivo')} onClick={() => onEdit(obj)}><Pencil size={14} /></IconButton>
          <IconButton variante="caja" tono="peligro" ariaLabel={t('pagina_okr.eliminar_objetivo')} onClick={() => onDeleteObj(obj.id)}><Trash2 size={14} /></IconButton>
        </div>
      </div>

      {expanded && (obj.key_results?.length ?? 0) > 0 && (
        <div className="okr-obj__krs">
          {(obj.key_results ?? []).map((kr) => (
            <KRRow key={kr.id} kr={kr} onDelete={onDeleteKR} />
          ))}
        </div>
      )}
      {expanded && (!obj.key_results || obj.key_results.length === 0) && (
        <div className="okr-obj__krs">
          <EmptyState icon={<ListChecks size={28} />} title={t('pagina_okr.sin_resultados_clave')} description={t('okrs.sin_key_results_pulsa_quot_kr_quot')}
            action={<Button size="sm" icon={<Plus size={13} />} onClick={() => onAddKR(obj)}>{t('okrs.add_kr')}</Button>} />
        </div>
      )}
    </Card>
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
    // 23-11-2026: sin catch que se trague el fallo; el aviso global de consultas lo cubre.
    queryFn: async () => {
      const { settingsApi } = await import('../services/settingsApi')
      const r = await settingsApi.getDepartments()
      return (Array.isArray(r.data) ? r.data : []) as DepartmentPick[]
    },
  })

  const camposB = useErroresDeCampo()
  const msgB = (k: string) => camposB.de(k) ? <div className="u-field-error">{camposB.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => camposB.limpiar(),
    mutationFn: () => {
      // Limpiamos cadenas vacías → null para que el backend no falle al castear UUIDs.
      const payload = Object.fromEntries(
        Object.entries(form).map(([k, v]) => [k, v === '' ? null : v])
      ) as Record<string, unknown>
      return isEdit && obj ? okrsApi.update(obj.id, payload) : okrsApi.create(payload)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['okrs'] }); onClose() },
    onError: (e: unknown) => { if (!camposB.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? t('pagina_okr.editar_objetivo') : t('pagina_okr.nuevo_objetivo')} size="md">
      <div className="ds-stack">
        <div className="ds-field">
          <Input label={t('okrs.titulo')} id={`${idCampo}-1`} value={form.title} onChange={e => { camposB.limpiar('title'); setForm(f => ({ ...f, title: e.target.value })) }} placeholder={t('okrs.ej_incrementar_retencion_de_clientes')} autoFocus />{msgB('title')}
        </div>
        <div className="ds-field">
          <Textarea label={t('okrs.descripcion')} id={`${idCampo}-2`} value={form.description} onChange={e => { camposB.limpiar('description'); setForm(f => ({ ...f, description: e.target.value })) }} rows={2} placeholder={t('okrs.que_problema_resuelve_y_como_se_medira')} />
          {msgB('description')}
        </div>

        {/* Asignaciones */}
        <div className="okr-grid">
          <div className="ds-field">
            <Select label={t('pagina_okr.responsable')} placeholder={false} id={`${idCampo}-3`} value={form.owner_id} onChange={e => { camposB.limpiar('owner_id'); setForm(f => ({ ...f, owner_id: e.target.value })) }}>
              <option value="">{t('okrs.sin_asignar')}</option>
              {users.map((u) => <option key={u.id} value={String(u.id)}>{u.full_name || u.username}</option>)}
            </Select>{msgB('owner_id')}
            <div className="ds-field__hint">{t('okrs.persona_que_rinde_cuentas_del_objetivo')}</div>
          </div>
          <div className="ds-field">
            <Select label={t('pagina_okr.departamento_equipo')} placeholder={false} id={`${idCampo}-4`} value={form.team_id} onChange={e => { camposB.limpiar('team_id'); setForm(f => ({ ...f, team_id: e.target.value })) }}>
              <option value="">{t('okrs.compania')}</option>
              {departments.map((d) => {
                const dep = typeof d === 'string' ? { id: d, name: d } : d
                return <option key={String(dep.id || dep.name || '')} value={String(dep.id || dep.name || '')}>{dep.name || String(dep.id || '')}</option>
              })}
            </Select>{msgB('team_id')}
            <div className="ds-field__hint">{t('okrs.vacio_okr_de_empresa')}</div>
          </div>
        </div>

        <div className="ds-field">
          <Select label={t('pagina_okr.proyecto_vinculado')} placeholder={false} id={`${idCampo}-5`} value={form.project_id} onChange={e => { camposB.limpiar('project_id'); setForm(f => ({ ...f, project_id: e.target.value })) }}>
            <option value="">{t('pagina_okr.ninguno')}</option>
            {projects.map((p) => <option key={p.id} value={String(p.id)}>{p.code ? `${p.code} · ` : ''}{p.name}</option>)}
          </Select>{msgB('project_id')}
          <div className="ds-field__hint">{t('okrs.si_lo_vinculas_los_krs_pueden_sincronizar')}</div>
        </div>

        {/* Período + estado */}
        <div className="okr-grid-3">
          <div className="ds-field">
            <Select label={t('okrs.periodo')} placeholder={false} id={`${idCampo}-6`} value={form.period} onChange={e => { camposB.limpiar('period'); setForm(f => ({ ...f, period: e.target.value as PeriodoDeObjetivo })) }}>
              {PERIOD_OPTS.map(p => <option key={p} value={p}>{etiquetaPeriodo(p, t)}</option>)}
            </Select>{msgB('period')}
          </div>
          <div className="ds-field">
            <Input label={t('okrs.year')} id={`${idCampo}-7`} type="number" value={form.year} onChange={e => { camposB.limpiar('year'); setForm(f => ({ ...f, year: parseInt(e.target.value) || f.year })) }} />{msgB('year')}
          </div>
          <div className="ds-field">
            <Select label={t('pagina_okr.estado')} placeholder={false} id={`${idCampo}-8`} value={form.status} onChange={e => { camposB.limpiar('status'); setForm(f => ({ ...f, status: e.target.value as EstadoDeObjetivo })) }}>
              {Object.entries(STATUS_CFG).map(([v, c]) => <option key={v} value={v}>{t(c.label)}</option>)}
            </Select>{msgB('status')}
          </div>
        </div>

        <div className="okr-acciones">
          <Button variant="secondary" onClick={onClose}>{t('pagina_okr.cancelar')}</Button>
          <Button onClick={() => mutate()} disabled={!form.title} loading={isPending}>
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

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => {
      const payload = Object.fromEntries(
        Object.entries(form).map(([k, v]) => [k, v === '' ? null : v])
      ) as Record<string, unknown>
      // El KR siempre vive bajo un objective: aseguramos el id por si la limpieza lo borrara
      payload.objective_id = objective.id
      return okrsApi.createKR(payload)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['okrs'] }); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  return (
    <Modal open onClose={onClose}
      title={t('okrs.nuevo_key_result')}
      subtitle={t('pagina_okr.para_el_objetivo', { title: objective.title })}
      size="md">
      <div className="ds-stack">
        <div className="ds-field">
          <Input label={t('okrs.descripcion_del_resultado')} id={`${idCampo}-1`} value={form.title} onChange={e => { campos.limpiar('title'); setForm(f => ({ ...f, title: e.target.value })) }} placeholder={t('pagina_okr.ej_aumentar_nps_a_60')} autoFocus />{msg('title')}
        </div>
        <div className="okr-grid-3">
          <div className="ds-field">
            <Select label={t('pagina_okr.tipo')} placeholder={false} id={`${idCampo}-2`} value={form.kr_type} onChange={e => { campos.limpiar('kr_type'); setForm(f => ({ ...f, kr_type: e.target.value })) }}>
              {Object.entries(KR_TYPE_CFG).map(([v, c]) => <option key={v} value={v}>{t(c.label)}</option>)}
            </Select>{msg('kr_type')}
          </div>
          <div className="ds-field">
            <Input label={t('pagina_okr.meta')} id={`${idCampo}-3`} type="number" value={form.target_value} onChange={e => { campos.limpiar('target_value'); setForm(f => ({ ...f, target_value: parseFloat(e.target.value) || 0 })) }} />{msg('target_value')}
          </div>
          <div className="ds-field">
            <Input label={t('pagina_okr.unidad')} id={`${idCampo}-4`} value={form.unit} onChange={e => { campos.limpiar('unit'); setForm(f => ({ ...f, unit: e.target.value })) }} placeholder={t('pagina_okr.puntos_nps')} />{msg('unit')}
          </div>
        </div>
        <div className="okr-grid">
          <div className="ds-field">
            <Select label={t('okrs.responsable_del_kr')} placeholder={false} id={`${idCampo}-5`} value={form.owner_id} onChange={e => { campos.limpiar('owner_id'); setForm(f => ({ ...f, owner_id: e.target.value })) }}>
              <option value="">{t('okrs.hereda_del_objetivo')}</option>
              {users.map((u) => <option key={u.id} value={String(u.id)}>{u.full_name || u.username}</option>)}
            </Select>{msg('owner_id')}
          </div>
          <div className="ds-field">
            <DateInput label={t('okrs.fecha_limite')} id={`${idCampo}-6`} value={form.due_date}
              onChange={e => { campos.limpiar('due_date'); setForm(f => ({ ...f, due_date: e.target.value })) }} />{msg('due_date')}
          </div>
        </div>
        <div className="ds-field">
          <Textarea label={t('pagina_okr.notas_opcional')} id={`${idCampo}-7`} value={form.notes} onChange={e => { campos.limpiar('notes'); setForm(f => ({ ...f, notes: e.target.value })) }} rows={2} placeholder={t('okrs.detalles_criterios_de_exito_dependencias')} />
          {msg('notes')}
        </div>
        <div className="okr-acciones">
          <Button variant="secondary" onClick={onClose}>{t('pagina_okr.cancelar')}</Button>
          <Button icon={<Plus size={14} />} onClick={() => mutate()} disabled={!form.title} loading={isPending}>
            {t('okrs.add_kr')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function OKRsPage() {
  const t = useAppT() as (key: string) => string
  const tono = useTono()
  const toast = useToast()
  const qc = useQueryClient()
  const anioActual = new Date().getFullYear()
  const anios = [anioActual - 2, anioActual - 1, anioActual, anioActual + 1]
  const [year, setYear] = useState(anioActual)
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
  const onTrack = objectives.filter((o) => tono('okr', o.progress || 0) === 'success').length
  const nuevo = () => { setEditingObj(null); setShowObjModal(true) }

  return (
    <Page
      icon={<Trophy size={18} />}
      title={t('nav.okrs')}
      subtitle={t('okrs.subtitle')}
      actions={<Button icon={<Plus size={14} />} onClick={nuevo}>{t('okrs.new_objective')}</Button>}
    >
      {/* Filtros */}
      <Card>
        <div className="okr-filtros">
          <Select label={t('okrs.periodo')} placeholder={false} value={period} onChange={e => setPeriod(e.target.value as PeriodOpt)}>
              <option value="">{t('okrs.todos_los_periodos')}</option>
              {PERIOD_OPTS.map(p => <option key={p} value={p}>{etiquetaPeriodo(p, t)}</option>)}
            </Select>
          <Select label={t('okrs.year')} placeholder={false} value={year} onChange={e => setYear(parseInt(e.target.value))}>
              {anios.map(y => <option key={y} value={y}>{y}</option>)}
            </Select>
        </div>
      </Card>

      {/* KPIs */}
      <div className="ds-grid-stats">
        <KpiCard icon={<Target size={16} />} label={t('pagina_okr.objetivos_activos')} value={totalObjs} />
        <KpiCard icon={<TrendingUp size={16} />} label={t('pagina_okr.progreso_medio')} value={`${avgProgress}%`} warning={totalObjs > 0 && avgProgress < 60} />
        <KpiCard icon={<CheckCircle2 size={16} />} label={t('pagina_okr.en_camino_60')} value={onTrack} />
      </div>

      {isLoading ? <Spinner /> : objectives.length === 0 ? (
        <Card>
          <EmptyState icon={<Trophy size={28} />} title={t('okrs.sin_objetivos')}
            description={t('pagina_okr.crea_tu_primer_okr')}
            action={<Button icon={<Plus size={14} />} onClick={nuevo}>{t('okrs.new_objective')}</Button>} />
        </Card>
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
