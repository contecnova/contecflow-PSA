/**
 * Presupuestos (revisión 2026-11): de proyecto (existente o previsto), de
 * departamento o de área, con partidas, real calculado, versiones y aprobación.
 * El detalle está en `components/presupuestos/FichaDePresupuesto.tsx`; campañas
 * y plantillas, en `components/presupuestos/CampanasYPlantillas.tsx`; el cuadro
 * de control (semáforo de cada presupuesto), en `SeguirPresupuesto.tsx`.
 */
import { useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { PieChart, Plus } from 'lucide-react'
import { presupuestosApi, projectsApi } from '../services/api'
import type { AmbitoDePresupuesto } from '../services/api'
import { settingsApi } from '../services/settingsApi'
import { Button, EmptyState, KpiCard, Modal, Spinner, Tabs, UserSelect } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { useAppT } from '../i18n/AppLangContext'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { useOrgSettings } from '../hooks/useOrgSettings'
import useMediaQuery from '../hooks/useMediaQuery'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import FichaDePresupuesto, { colorDeEstado } from '../components/presupuestos/FichaDePresupuesto'
import { CampanasDePresupuesto, PlantillasDePresupuesto } from '../components/presupuestos/CampanasYPlantillas'
import { CuadroDeControl } from '../components/presupuestos/SeguirPresupuesto'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
const campo: CSSProperties = { width: '100%', boxSizing: 'border-box', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }
const fila: CSSProperties = { display: 'grid', gridTemplateColumns: 'minmax(220px, 2fr) 150px 70px 110px repeat(4, 120px)', gap: 10, alignItems: 'center', padding: '10px 12px', fontSize: 'var(--text-sm)' }
const AMBITOS: AmbitoDePresupuesto[] = ['proyecto', 'proyecto_previsto', 'departamento', 'area']

export default function BudgetsPage() {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT()
  const qc = useQueryClient()
  const anioActual = new Date().getFullYear()
  const [year, setYear] = useState<number>(anioActual)
  const [ambito, setAmbito] = useState('')
  const [abierto, setAbierto] = useState<string | null>(null)
  const [nuevo, setNuevo] = useState(false)
  const [vista, setVista] = useState('presupuestos')
  // En estrecho, una fila compacta: ocho columnas escondían el plan y el real tras un desplazamiento.
  const estrecho = useMediaQuery('(max-width: 760px)')
  const lista = useQuery({ queryKey: ['presupuestos', 'lista', year, ambito], queryFn: () => presupuestosApi.listar({ year, ambito: ambito || undefined }) })
  const resumen = useQuery({ queryKey: ['presupuestos', 'resumen', year], queryFn: () => presupuestosApi.resumen(year) })
  const todos = useQuery({ queryKey: ['presupuestos', 'años'], queryFn: () => presupuestosApi.listar({}) })
  // Los años que ofrece el selector salen de los datos (y el actual), no de una lista escrita.
  const anios = useMemo(() => Array.from(new Set([anioActual, ...(todos.data ?? []).map(b => b.year)])).sort(), [todos.data, anioActual])
  const moneda = lista.data?.[0]?.currency
  const dinero = (n?: number) => fmtMoneda(n ?? 0, { moneda, decimales: 0 })
  const r = resumen.data
  return (
    <PageShell>
      <PageHeader icon={<PieChart size={18} />} title={t('pres.titulo')} subtitle={t('pres.subtitulo')}
        actions={<Button icon={<Plus size={14} />} onClick={() => setNuevo(true)}>{t('pres.nuevo')}</Button>} />
      <Tabs active={vista} onChange={setVista} items={[
        { id: 'presupuestos', label: t('pres.tab_presupuestos') }, { id: 'cuadro', label: t('pres.tab_cuadro') },
        { id: 'campanas', label: t('pres.tab_campanas') },
        { id: 'plantillas', label: t('pres.tab_plantillas') },
      ]} />
      {vista === 'cuadro' && <>
        <div style={{ margin: '14px 0' }}>
          <select aria-label={t('pres.ejercicio')} value={year} onChange={e => setYear(Number(e.target.value))} style={{ ...campo, width: 120 }}>
            {anios.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
        <CuadroDeControl year={year} onAbrir={setAbierto} />
      </>}
      {vista === 'campanas' && <CampanasDePresupuesto />}
      {vista === 'plantillas' && <PlantillasDePresupuesto />}
      {vista === 'presupuestos' && <>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '14px 0' }}>
        <select aria-label={t('pres.ejercicio')} value={year} onChange={e => setYear(Number(e.target.value))} style={{ ...campo, width: 120 }}>
          {anios.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <select aria-label={t('pres.ambito')} value={ambito} onChange={e => setAmbito(e.target.value)} style={{ ...campo, width: 220 }}>
          <option value="">{t('pres.todos_los_ambitos')}</option>
          {AMBITOS.map(a => <option key={a} value={a}>{t(`pres.ambito_${a}`)}</option>)}
        </select>
      </div>
      {r && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12, marginBottom: 14 }}>
          <KpiCard label={t('pres.kpi_plan')} value={dinero(r.total_plan)} sub={t('pres.kpi_presupuestos', { n: r.presupuestos, a: r.aprobados })} />
          <KpiCard label={t('pres.kpi_plan_hoy')} value={dinero(r.plan_hasta_hoy)} />
          <KpiCard label={t('pres.kpi_real')} value={dinero(r.total_real)} danger={r.total_real > r.plan_hasta_hoy} />
          <KpiCard label={t('pres.kpi_prevision')} value={dinero(r.prevision_cierre)} warning={r.prevision_cierre > r.total_plan} />
        </div>
      )}
      {r && r.por_mes.length > 0 && (
        <div style={{ height: 220, marginBottom: 16 }} role="img" aria-label={t('pres.plan_contra_real')}>
          <ResponsiveContainer>
            <BarChart data={r.por_mes}>
              <CartesianGrid stroke="var(--surface-3)" vertical={false} />
              <XAxis dataKey="mes" tick={{ fill: 'var(--text-3)', fontSize: 'var(--text-xs)' }} />
              <YAxis tick={{ fill: 'var(--text-3)', fontSize: 'var(--text-xs)' }} />
              <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)' }} formatter={(v: number) => dinero(v)} />
              <Legend />
              <Bar dataKey="plan" name={t('pres.plan')} fill="var(--surface-4)" radius={[3, 3, 0, 0]} />
              <Bar dataKey="real" name={t('pres.real')} fill="var(--accent)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {lista.isLoading ? <Spinner /> : lista.isError ? <div role="alert" className="u-danger">{extractErr(lista.error, GENERIC_ERROR_FALLBACK)}</div>
        : (lista.data ?? []).length === 0 ? <EmptyState svgIcon={<PieChart size={26} />} title={t('pres.vacio')} description={t('pres.vacio_texto')} />
        : (
          <div style={{ border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', overflowX: 'auto' }}>
            {!estrecho && <div style={{ ...fila, color: 'var(--text-3)', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase' }}>
              <span>{t('pres.nombre')}</span><span>{t('pres.ambito')}</span><span>{t('pres.version')}</span><span>{t('pres.estado')}</span>
              <span style={{ textAlign: 'right' }}>{t('pres.plan')}</span><span style={{ textAlign: 'right' }}>{t('pres.real')}</span>
              <span style={{ textAlign: 'right' }}>{t('pres.desv_hoy')}</span><span style={{ textAlign: 'right' }}>{t('pres.prevision')}</span>
            </div>}
            {lista.data!.map(b => estrecho ? (
              <button key={b.id} type="button" onClick={() => setAbierto(b.id)} aria-label={`${b.name} · ${dinero(b.total_plan)} · ${t(`pres.estado_${b.estado}`)}`} style={{ display: 'flex', flexDirection: 'column', gap: 4, width: '100%', padding: '10px 12px', background: 'transparent', border: 'none', borderTop: '1px solid var(--surface-3)', textAlign: 'left', cursor: 'pointer', color: 'var(--text-1)', fontFamily: 'inherit', fontSize: 'var(--text-sm)' }}>
                <span style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                  <strong style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.name}</strong>
                  <span className="u-mono">{dinero(b.total_plan)}</span>
                </span>
                <span style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
                  <span>{t(`pres.ambito_${b.ambito}`)} · v{b.version}</span>
                  <span style={{ color: colorDeEstado(b.estado), fontWeight: 600 }}>{t(`pres.estado_${b.estado}`)}</span>
                  <span style={{ marginLeft: 'auto' }}>{t('pres.real')} {dinero(b.total_real)} · {t('pres.prevision')} <span style={{ color: (b.prevision_cierre ?? 0) > b.total_plan ? 'var(--warning)' : undefined }}>{dinero(b.prevision_cierre)}</span></span>
                </span>
              </button>
            ) : (
              <button key={b.id} type="button" onClick={() => setAbierto(b.id)} style={{ ...fila, width: '100%', background: 'transparent', border: 'none', borderTop: '1px solid var(--surface-3)', textAlign: 'left', cursor: 'pointer', color: 'var(--text-1)', fontFamily: 'inherit' }}>
                <span className="u-min0"><strong style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.name}</strong>
                  <span className="u-text3-xs">{b.project_name || b.department || b.area_name || b.area || ''}{b.escenario !== 'base' ? ` · ${b.escenario}` : ''} · {b.periodo_desde.slice(0, 7)} → {b.periodo_hasta.slice(0, 7)}</span></span>
                <span className="u-text2">{t(`pres.ambito_${b.ambito}`)}</span>
                <span>v{b.version}</span>
                <span style={{ color: colorDeEstado(b.estado), fontWeight: 600 }}>{t(`pres.estado_${b.estado}`)}</span>
                <span style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{dinero(b.total_plan)}</span>
                <span style={{ textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{dinero(b.total_real)}</span>
                <span style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: (b.desviacion_hasta_hoy ?? 0) > 0 ? 'var(--danger)' : 'var(--success)' }}>{dinero(b.desviacion_hasta_hoy)}</span>
                <span style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: (b.prevision_cierre ?? 0) > b.total_plan ? 'var(--warning)' : undefined }}>{dinero(b.prevision_cierre)}</span>
              </button>
            ))}
          </div>
        )}
      </>}
      {nuevo && <NuevoPresupuesto onClose={() => setNuevo(false)} onCreado={id => { setNuevo(false); qc.invalidateQueries({ queryKey: ['presupuestos'] }); setAbierto(id) }} />}
      {abierto && <FichaDePresupuesto id={abierto} onClose={() => setAbierto(null)} onAbrir={setAbierto} />}
    </PageShell>
  )
}

function NuevoPresupuesto({ onClose, onCreado }: { onClose: () => void; onCreado: (id: string) => void }) {
  const t = useAppT()
  const toast = useToast()
  const { user } = useAuth() as { user?: { department?: string } }
  const { currency, currencies } = useOrgSettings()
  const anio = new Date().getFullYear()
  const [f, setF] = useState({ name: '', ambito: 'proyecto', project_id: '', department: user?.department || '', area_id: '', tipo_proyecto: '',
    desde: `${anio}-01`, hasta: `${anio}-12`, currency: '', techo: '', campana_id: '', responsable_id: '', inflacion: '',
    origen: 'vacio', plantilla_id: '', copiar_de: '', base: 'plan', ajuste_pct: '' })
  const [guardando, setGuardando] = useState(false)
  const proyectos = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data as unknown as { id: string; code?: string; name?: string }[]) })
  const depts = useQuery<{ name: string }[]>({ queryKey: ['departments-select'], queryFn: () => settingsApi.getDepartments().then(r => r.data as unknown as { name: string }[]) })
  const areas = useQuery({ queryKey: ['areas'], queryFn: () => presupuestosApi.areas() })
  const campanas = useQuery({ queryKey: ['presupuestos', 'campanas'], queryFn: () => presupuestosApi.campanas() })
  const plantillas = useQuery({ queryKey: ['presupuestos', 'plantillas'], queryFn: () => presupuestosApi.plantillas() })
  const existentes = useQuery({ queryKey: ['presupuestos', 'años'], queryFn: () => presupuestosApi.listar({}) })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF(v => ({ ...v, [k]: e.target.value }))
  const conTecho = f.ambito === 'area' || f.ambito === 'departamento'
  const crear = async () => {
    setGuardando(true)
    try {
      const d = await presupuestosApi.crear({
        name: f.name, ambito: f.ambito, currency: f.currency || currency,
        periodo_desde: `${f.desde}-01`, periodo_hasta: `${f.hasta}-01`,
        ...(f.ambito === 'proyecto' ? { project_id: f.project_id } : {}),
        ...(f.ambito === 'departamento' ? { department: f.department } : {}),
        ...(f.ambito === 'area' ? { area_id: f.area_id } : {}),
        ...(f.ambito === 'proyecto_previsto' ? { tipo_proyecto: f.tipo_proyecto || undefined } : {}),
        ...(conTecho && f.techo !== '' ? { techo: Number(f.techo) } : {}),
        ...(f.campana_id ? { campana_id: f.campana_id } : {}),
        ...(f.responsable_id ? { responsable_id: f.responsable_id } : {}),
        ...(f.inflacion !== '' ? { supuestos: { inflacion_pct: Number(f.inflacion) } } : {}),
        ...(f.origen === 'plantilla' && f.plantilla_id ? { plantilla_id: f.plantilla_id } : {}),
        ...(f.origen === 'copia' && f.copiar_de ? { copiar_de: f.copiar_de, base: f.base, ajuste_pct: f.ajuste_pct === '' ? 0 : Number(f.ajuste_pct) } : {}),
      })
      onCreado(d.id)
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setGuardando(false) }
  }
  const lbl: CSSProperties = { fontSize: 'var(--text-xs)', color: 'var(--text-3)', display: 'block', marginBottom: 3 }
  const rejilla: CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(160px, 100%), 1fr))', gap: 10 }
  return (
    <Modal open onClose={onClose} size="lg" title={t('pres.nuevo')}>
      <div className="u-stack-12">
        <label><span style={lbl}>{t('pres.nombre')}</span><input aria-label={t('pres.nombre')} value={f.name} onChange={set('name')} style={campo} /></label>
        <div style={rejilla}>
          <label><span style={lbl}>{t('pres.ambito')}</span>
            <select aria-label={t('pres.ambito')} value={f.ambito} onChange={set('ambito')} style={campo}>
              {AMBITOS.map(a => <option key={a} value={a}>{t(`pres.ambito_${a}`)}</option>)}
            </select></label>
          {f.ambito === 'proyecto' && (
            <label><span style={lbl}>{t('pres.proyecto')}</span>
              <select aria-label={t('pres.proyecto')} value={f.project_id} onChange={set('project_id')} style={campo}>
                <option value="">{t('pres.elige_proyecto')}</option>
                {(proyectos.data ?? []).map(p => <option key={p.id} value={p.id}>{p.code ? `${p.code} — ` : ''}{p.name}</option>)}
              </select></label>
          )}
          {f.ambito === 'departamento' && (
            <label><span style={lbl}>{t('pres.departamento')}</span>
              <select aria-label={t('pres.departamento')} value={f.department} onChange={set('department')} style={campo}>
                <option value="">{t('pres.elige_departamento')}</option>
                {(depts.data ?? []).map(d => <option key={d.name} value={d.name}>{d.name}</option>)}
              </select></label>
          )}
          {f.ambito === 'area' && (
            <label><span style={lbl}>{t('pres.area')}</span>
              <select aria-label={t('pres.area')} value={f.area_id} onChange={set('area_id')} style={campo}>
                <option value="">{t('pres.elige_area')}</option>
                {(areas.data ?? []).map(a => <option key={a.id} value={a.id}>{a.name}{a.departamentos.length ? ` (${a.departamentos.join(', ')})` : ''}</option>)}
              </select></label>
          )}
          {f.ambito === 'proyecto_previsto' && (
            <label><span style={lbl}>{t('pres.tipo_proyecto')}</span><input aria-label={t('pres.tipo_proyecto')} value={f.tipo_proyecto} onChange={set('tipo_proyecto')} style={campo} /></label>
          )}
        </div>
        <div className="u-text3-xs">{t(`pres.ambito_${f.ambito}_ayuda`)}</div>
        {f.ambito === 'area' && (areas.data ?? []).length === 0 && <div role="status" style={{ fontSize: 'var(--text-xs)', color: 'var(--warning)' }}>{t('pres.sin_areas')}</div>}
        <div style={rejilla}>
          <label><span style={lbl}>{t('pres.desde')}</span><input aria-label={t('pres.desde')} type="month" value={f.desde} onChange={set('desde')} style={campo} /></label>
          <label><span style={lbl}>{t('pres.hasta')}</span><input aria-label={t('pres.hasta')} type="month" value={f.hasta} onChange={set('hasta')} style={campo} /></label>
          <label><span style={lbl}>{t('pres.moneda')}</span>
            <select aria-label={t('pres.moneda')} value={f.currency || currency} onChange={set('currency')} style={campo}>
              {currencies.map(c => <option key={c} value={c}>{c}</option>)}
            </select></label>
          <label><span style={lbl}>{t('pres.inflacion')}</span><input aria-label={t('pres.inflacion')} type="number" step="any" value={f.inflacion} onChange={set('inflacion')} style={campo} placeholder="0" /></label>
          {conTecho && <label><span style={lbl}>{t('pres.techo')}</span><input aria-label={t('pres.techo')} type="number" min={0} step="any" value={f.techo} onChange={set('techo')} style={campo} placeholder={t('pres.techo_ayuda')} /></label>}
          <label><span style={lbl}>{t('pres.campana')}</span>
            <select aria-label={t('pres.campana')} value={f.campana_id} onChange={set('campana_id')} style={campo}>
              <option value="">—</option>
              {(campanas.data ?? []).filter(c => c.abierta).map(c => <option key={c.id} value={c.id}>{c.nombre} · {c.fecha_limite}</option>)}
            </select></label>
          <div><span style={lbl}>{t('pres.responsable')}</span>
            <UserSelect value={f.responsable_id} onChange={(uid: string) => setF(v => ({ ...v, responsable_id: uid }))} placeholder={t('pres.responsable_yo')} /></div>
        </div>
        <fieldset style={{ border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <legend style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', padding: '0 4px' }}>{t('pres.empezar_de')}</legend>
          <div role="radiogroup" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 'var(--text-sm)' }}>
            {(['vacio', 'plantilla', 'copia'] as const).map(o => (
              <label key={o} style={{ display: 'flex', gap: 4, alignItems: 'center', cursor: 'pointer' }}>
                <input type="radio" name="origen" checked={f.origen === o} aria-label={t(`pres.empezar_${o}`)} onChange={() => setF(v => ({ ...v, origen: o }))} />{t(`pres.empezar_${o}`)}
              </label>))}
          </div>
          {f.origen === 'plantilla' && (
            <select aria-label={t('pres.plantilla')} value={f.plantilla_id} onChange={set('plantilla_id')} style={campo}>
              <option value="">{t('pres.elige_plantilla')}</option>
              {(plantillas.data ?? []).map(pl => <option key={pl.id} value={pl.id}>{pl.nombre} · {pl.partidas.length} {t('pres.partidas')}</option>)}
            </select>
          )}
          {f.origen === 'copia' && (
            <div style={rejilla}>
              <select aria-label={t('pres.copiar_de')} value={f.copiar_de} onChange={set('copiar_de')} style={campo}>
                <option value="">{t('pres.elige_presupuesto')}</option>
                {(existentes.data ?? []).map(b => <option key={b.id} value={b.id}>{b.name} · {b.year} · v{b.version}</option>)}
              </select>
              <select aria-label={t('pres.base')} value={f.base} onChange={set('base')} style={campo}>
                <option value="plan">{t('pres.base_plan')}</option><option value="real">{t('pres.base_real')}</option>
              </select>
              <input aria-label={t('pres.ajuste_pct')} type="number" step="any" value={f.ajuste_pct} onChange={set('ajuste_pct')} style={campo} placeholder={t('pres.ajuste_pct')} />
            </div>
          )}
        </fieldset>
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('pres.cancelar')}</Button>
          <Button loading={guardando} disabled={!f.name.trim() || !f.desde || !f.hasta || (f.ambito === 'area' && !f.area_id)} onClick={crear}>{t('pres.crear')}</Button>
        </div>
      </div>
    </Modal>
  )
}
