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
import './BudgetsPage.css'

const estadoVar = (e: string) => ({ '--bud-estado': colorDeEstado(e) }) as CSSProperties
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
        <div className="bud-filtros">
          <select aria-label={t('pres.ejercicio')} value={year} onChange={e => setYear(Number(e.target.value))} className="bud-campo bud-campo--year">
            {anios.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
        <CuadroDeControl year={year} onAbrir={setAbierto} />
      </>}
      {vista === 'campanas' && <CampanasDePresupuesto />}
      {vista === 'plantillas' && <PlantillasDePresupuesto />}
      {vista === 'presupuestos' && <>
      <div className="bud-filtros">
        <select aria-label={t('pres.ejercicio')} value={year} onChange={e => setYear(Number(e.target.value))} className="bud-campo bud-campo--year">
          {anios.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <select aria-label={t('pres.ambito')} value={ambito} onChange={e => setAmbito(e.target.value)} className="bud-campo bud-campo--ambito">
          <option value="">{t('pres.todos_los_ambitos')}</option>
          {AMBITOS.map(a => <option key={a} value={a}>{t(`pres.ambito_${a}`)}</option>)}
        </select>
      </div>
      {r && (
        <div className="bud-kpis">
          <KpiCard label={t('pres.kpi_plan')} value={dinero(r.total_plan)} sub={t('pres.kpi_presupuestos', { n: r.presupuestos, a: r.aprobados })} />
          <KpiCard label={t('pres.kpi_plan_hoy')} value={dinero(r.plan_hasta_hoy)} />
          <KpiCard label={t('pres.kpi_real')} value={dinero(r.total_real)} danger={r.total_real > r.plan_hasta_hoy} />
          <KpiCard label={t('pres.kpi_prevision')} value={dinero(r.prevision_cierre)} warning={r.prevision_cierre > r.total_plan} />
        </div>
      )}
      {r && r.por_mes.length > 0 && (
        <div className="bud-chart" role="img" aria-label={t('pres.plan_contra_real')}>
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
          <div className="bud-tabla">
            {!estrecho && <div className="bud-fila bud-fila--head" aria-hidden="true">
              <span>{t('pres.nombre')}</span><span>{t('pres.ambito')}</span><span>{t('pres.version')}</span><span>{t('pres.estado')}</span>
              <span className="bud-num">{t('pres.plan')}</span><span className="bud-num">{t('pres.real')}</span>
              <span className="bud-num">{t('pres.desv_hoy')}</span><span className="bud-num">{t('pres.prevision')}</span>
            </div>}
            {lista.data!.map(b => estrecho ? (
              <button key={b.id} type="button" onClick={() => setAbierto(b.id)} aria-label={`${b.name} · ${dinero(b.total_plan)} · ${t(`pres.estado_${b.estado}`)}`} className="bud-tarjeta">
                <span className="bud-tarjeta__top">
                  <strong className="bud-trunc">{b.name}</strong>
                  <span className="u-mono">{dinero(b.total_plan)}</span>
                </span>
                <span className="bud-tarjeta__meta">
                  <span>{t(`pres.ambito_${b.ambito}`)} · v{b.version}</span>
                  <span className="bud-estado" style={estadoVar(b.estado)}>{t(`pres.estado_${b.estado}`)}</span>
                  <span className="bud-tarjeta__fin">{t('pres.real')} {dinero(b.total_real)} · {t('pres.prevision')} <span className={(b.prevision_cierre ?? 0) > b.total_plan ? 'bud-warning' : undefined}>{dinero(b.prevision_cierre)}</span></span>
                </span>
              </button>
            ) : (
              <button key={b.id} type="button" onClick={() => setAbierto(b.id)} className="bud-fila bud-fila-btn">
                <span className="u-min0"><strong className="bud-trunc">{b.name}</strong>
                  <span className="u-text3-xs">{b.project_name || b.department || b.area_name || b.area || ''}{b.escenario !== 'base' ? ` · ${b.escenario}` : ''} · {b.periodo_desde.slice(0, 7)} → {b.periodo_hasta.slice(0, 7)}</span></span>
                <span className="u-text2">{t(`pres.ambito_${b.ambito}`)}</span>
                <span>v{b.version}</span>
                <span className="bud-estado" style={estadoVar(b.estado)}>{t(`pres.estado_${b.estado}`)}</span>
                <span className="bud-num">{dinero(b.total_plan)}</span>
                <span className="bud-num">{dinero(b.total_real)}</span>
                <span className={`bud-num ${(b.desviacion_hasta_hoy ?? 0) > 0 ? 'bud-danger' : 'bud-success'}`}>{dinero(b.desviacion_hasta_hoy)}</span>
                <span className={`bud-num${(b.prevision_cierre ?? 0) > b.total_plan ? ' bud-warning' : ''}`}>{dinero(b.prevision_cierre)}</span>
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
  const proyectos = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data) })
  const depts = useQuery({ queryKey: ['departments-select'], queryFn: () => settingsApi.getDepartments().then(r => r.data) })
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
  return (
    <Modal open onClose={onClose} size="lg" title={t('pres.nuevo')}>
      <div className="u-stack-12">
        <label><span className="bud-lbl">{t('pres.nombre')}</span><input aria-label={t('pres.nombre')} value={f.name} onChange={set('name')} className="bud-campo" /></label>
        <div className="bud-rejilla">
          <label><span className="bud-lbl">{t('pres.ambito')}</span>
            <select aria-label={t('pres.ambito')} value={f.ambito} onChange={set('ambito')} className="bud-campo">
              {AMBITOS.map(a => <option key={a} value={a}>{t(`pres.ambito_${a}`)}</option>)}
            </select></label>
          {f.ambito === 'proyecto' && (
            <label><span className="bud-lbl">{t('pres.proyecto')}</span>
              <select aria-label={t('pres.proyecto')} value={f.project_id} onChange={set('project_id')} className="bud-campo">
                <option value="">{t('pres.elige_proyecto')}</option>
                {(proyectos.data ?? []).map(p => <option key={p.id} value={p.id}>{p.code ? `${p.code} — ` : ''}{p.name}</option>)}
              </select></label>
          )}
          {f.ambito === 'departamento' && (
            <label><span className="bud-lbl">{t('pres.departamento')}</span>
              <select aria-label={t('pres.departamento')} value={f.department} onChange={set('department')} className="bud-campo">
                <option value="">{t('pres.elige_departamento')}</option>
                {(depts.data ?? []).map(d => <option key={d.name} value={d.name}>{d.name}</option>)}
              </select></label>
          )}
          {f.ambito === 'area' && (
            <label><span className="bud-lbl">{t('pres.area')}</span>
              <select aria-label={t('pres.area')} value={f.area_id} onChange={set('area_id')} className="bud-campo">
                <option value="">{t('pres.elige_area')}</option>
                {(areas.data ?? []).map(a => <option key={a.id} value={a.id}>{a.name}{a.departamentos.length ? ` (${a.departamentos.join(', ')})` : ''}</option>)}
              </select></label>
          )}
          {f.ambito === 'proyecto_previsto' && (
            <label><span className="bud-lbl">{t('pres.tipo_proyecto')}</span><input aria-label={t('pres.tipo_proyecto')} value={f.tipo_proyecto} onChange={set('tipo_proyecto')} className="bud-campo" /></label>
          )}
        </div>
        <div className="u-text3-xs">{t(`pres.ambito_${f.ambito}_ayuda`)}</div>
        {f.ambito === 'area' && (areas.data ?? []).length === 0 && <div role="status" className="bud-aviso">{t('pres.sin_areas')}</div>}
        <div className="bud-rejilla">
          <label><span className="bud-lbl">{t('pres.desde')}</span><input aria-label={t('pres.desde')} type="month" value={f.desde} onChange={set('desde')} className="bud-campo" /></label>
          <label><span className="bud-lbl">{t('pres.hasta')}</span><input aria-label={t('pres.hasta')} type="month" value={f.hasta} onChange={set('hasta')} className="bud-campo" /></label>
          <label><span className="bud-lbl">{t('pres.moneda')}</span>
            <select aria-label={t('pres.moneda')} value={f.currency || currency} onChange={set('currency')} className="bud-campo">
              {currencies.map(c => <option key={c} value={c}>{c}</option>)}
            </select></label>
          <label><span className="bud-lbl">{t('pres.inflacion')}</span><input aria-label={t('pres.inflacion')} type="number" step="any" value={f.inflacion} onChange={set('inflacion')} className="bud-campo" placeholder="0" /></label>
          {conTecho && <label><span className="bud-lbl">{t('pres.techo')}</span><input aria-label={t('pres.techo')} type="number" min={0} step="any" value={f.techo} onChange={set('techo')} className="bud-campo" placeholder={t('pres.techo_ayuda')} /></label>}
          <label><span className="bud-lbl">{t('pres.campana')}</span>
            <select aria-label={t('pres.campana')} value={f.campana_id} onChange={set('campana_id')} className="bud-campo">
              <option value="">—</option>
              {(campanas.data ?? []).filter(c => c.abierta).map(c => <option key={c.id} value={c.id}>{c.nombre} · {c.fecha_limite}</option>)}
            </select></label>
          <div><span className="bud-lbl">{t('pres.responsable')}</span>
            <UserSelect value={f.responsable_id} onChange={(uid: string) => setF(v => ({ ...v, responsable_id: uid }))} placeholder={t('pres.responsable_yo')} /></div>
        </div>
        <fieldset className="bud-origen">
          <legend className="bud-origen__legend">{t('pres.empezar_de')}</legend>
          <div className="bud-origen__opciones">
            {(['vacio', 'plantilla', 'copia'] as const).map(o => (
              <label key={o} className="bud-origen__opcion">
                <input type="radio" name="origen" checked={f.origen === o} aria-label={t(`pres.empezar_${o}`)} onChange={() => setF(v => ({ ...v, origen: o }))} />{t(`pres.empezar_${o}`)}
              </label>))}
          </div>
          {f.origen === 'plantilla' && (
            <select aria-label={t('pres.plantilla')} value={f.plantilla_id} onChange={set('plantilla_id')} className="bud-campo">
              <option value="">{t('pres.elige_plantilla')}</option>
              {(plantillas.data ?? []).map(pl => <option key={pl.id} value={pl.id}>{pl.nombre} · {pl.partidas.length} {t('pres.partidas')}</option>)}
            </select>
          )}
          {f.origen === 'copia' && (
            <div className="bud-rejilla">
              <select aria-label={t('pres.copiar_de')} value={f.copiar_de} onChange={set('copiar_de')} className="bud-campo">
                <option value="">{t('pres.elige_presupuesto')}</option>
                {(existentes.data ?? []).map(b => <option key={b.id} value={b.id}>{b.name} · {b.year} · v{b.version}</option>)}
              </select>
              <select aria-label={t('pres.base')} value={f.base} onChange={set('base')} className="bud-campo">
                <option value="plan">{t('pres.base_plan')}</option><option value="real">{t('pres.base_real')}</option>
              </select>
              <input aria-label={t('pres.ajuste_pct')} type="number" step="any" value={f.ajuste_pct} onChange={set('ajuste_pct')} className="bud-campo" placeholder={t('pres.ajuste_pct')} />
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
