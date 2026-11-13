/**
 * Ficha de un presupuesto (revisión 2026-11, preparar a fondo).
 *
 * Partidas (gasto e ingreso, con su forma de cálculo), seguimiento (plan contra
 * real, ingresos y margen, amortización del CAPEX), estructura (presupuesto
 * padre, techo y lo que consumen los hijos, consolidado), escenarios y
 * versiones (crearlos y compararlos), y supuestos. Un presupuesto aprobado no
 * se toca: se hace una versión nueva. Aprobado, se sigue a fondo (P2): control
 * por tipo con comprometido y reprevisión, cierre mensual con desviaciones
 * explicadas y detalle del real, pedidos y traspasos (`SeguirPresupuesto.tsx`).
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Bar, CartesianGrid, Legend, Line, ComposedChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Pencil, Trash2, MessageSquareText } from 'lucide-react'
import { presupuestosApi, projectsApi } from '../../services/api'
import type { ComparacionDePresupuestos, FichaPresupuesto, Partida } from '../../services/api'
import { Button, Modal, Spinner, Tabs } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, localeActivo } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import FormularioDePartida, { campo, modoDe } from './FormularioDePartida'
import { CierreDelPresupuesto, ControlDelPresupuesto, PedidosYTraspasos } from './SeguirPresupuesto'

import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
const th: CSSProperties = { textAlign: 'left', padding: '6px 8px', fontSize: 'var(--text-xs)', color: 'var(--text-3)', fontWeight: 600, borderBottom: '1px solid var(--surface-3)', whiteSpace: 'nowrap' }
const td: CSSProperties = { padding: '6px 8px', fontSize: 'var(--text-sm)', borderBottom: '1px solid var(--surface-2)' }
const num: CSSProperties = { ...td, textAlign: 'right', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }
const caja: CSSProperties = { border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: 12 }
const tablaConScroll: CSSProperties = { overflowX: 'auto', maxWidth: '100%' }

export function colorDeEstado(e: string) {
  return e === 'aprobado' ? 'var(--success)' : e === 'enviado' ? 'var(--warning)' : e === 'rechazado' ? 'var(--danger)' : 'var(--text-3)'
}

type Dinero = (n?: number | null) => string

export default function FichaDePresupuesto({ id, onClose, onAbrir }: { id: string; onClose: () => void; onAbrir: (id: string) => void }) {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('partidas')
  const q = useQuery({ queryKey: ['presupuesto', id], queryFn: () => presupuestosApi.ficha(id) })
  const [ocupado, setOcupado] = useState<string | null>(null)
  const [motivo, setMotivo] = useState('')
  const [vincular, setVincular] = useState('')
  const proyectos = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data as unknown as { id: string; code?: string; name?: string }[]) })
  const p = q.data
  const dinero: Dinero = n => fmtMoneda(n ?? 0, { moneda: p?.currency, decimales: 0 })
  const accion = async (clave: string, f: () => Promise<FichaPresupuesto>) => {
    setOcupado(clave)
    try {
      const d = await f()
      qc.setQueryData(['presupuesto', d.id], d)
      qc.invalidateQueries({ queryKey: ['presupuestos'] })
      if (d.id !== id) onAbrir(d.id)
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setOcupado(null) }
  }
  const ambitoTexto = p ? (p.project_name || p.department || p.area_name || p.area || '') : ''

  return (
    <Modal open onClose={onClose} size="xl" title={p ? `${p.name} · v${p.version}${p.escenario !== 'base' ? ` · ${p.escenario}` : ''}` : '…'}
      subtitle={p ? `${t(`pres.ambito_${p.ambito}`)}${ambitoTexto ? ` · ${ambitoTexto}` : ''} · ${p.periodo_desde.slice(0, 7)} → ${p.periodo_hasta.slice(0, 7)}${p.responsable_name ? ` · ${t('pres.responsable')}: ${p.responsable_name}` : ''}` : undefined}>
      {q.isLoading ? <Spinner /> : q.isError ? <div role="alert" className="u-danger">{extractErr(q.error, GENERIC_ERROR_FALLBACK)}</div> : p && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ color: colorDeEstado(p.estado), border: '1px solid currentColor', borderRadius: 99, padding: '1px 10px', fontSize: 'var(--text-xs)', fontWeight: 600 }}>{t(`pres.estado_${p.estado}`)}</span>
            <span className="u-sm">{t('pres.gasto')}: <strong>{dinero(p.total_plan)}</strong></span>
            {p.total_ingreso > 0 && <>
              <span className="u-sm">{t('pres.ingreso')}: <strong>{dinero(p.total_ingreso)}</strong></span>
              <span style={{ fontSize: 'var(--text-sm)', color: p.informe.margen_plan < 0 ? 'var(--danger)' : 'var(--success)' }}>{t('pres.margen')}: <strong>{dinero(p.informe.margen_plan)}</strong></span>
            </>}
            <span className="u-sm">{t('pres.real')}: <strong>{dinero(p.informe.total_real)}</strong></span>
            <span className="u-sm">{t('pres.prevision')}: <strong>{dinero(p.informe.prevision_cierre)}</strong></span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {p.puedo_editar && <Button size="sm" loading={ocupado === 'enviar'} onClick={() => accion('enviar', () => presupuestosApi.enviar(p.id))}>{t('pres.enviar')}</Button>}
              {p.estado !== 'borrador' && p.estado !== 'enviado' && <Button size="sm" variant="secondary" loading={ocupado === 'version'} onClick={() => accion('version', () => presupuestosApi.nuevaVersion(p.id))}>{t('pres.nueva_version')}</Button>}
            </span>
          </div>
          {!p.seguir && (() => {
            // El seguimiento vive en la versión aprobada: desde un borrador, a un clic.
            const aprobada = p.versiones.find(v => v.estado === 'aprobado' && v.id !== p.id)
            return aprobada && <div role="status" style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>
              {t('pres.se_sigue_la_aprobada', { v: aprobada.version })}
              <Button size="xs" variant="secondary" onClick={() => onAbrir(aprobada.id)}>{t('pres.abrir_aprobada')}</Button>
            </div>
          })()}
          {p.aviso_techo_del_padre && <div role="alert" style={{ fontSize: 'var(--text-sm)', color: 'var(--warning)' }}>⚠ {p.aviso_techo_del_padre}</div>}
          {p.motivo_rechazo && <div role="alert" style={{ fontSize: 'var(--text-sm)', color: 'var(--danger)' }}>{t('pres.rechazado_por')}: {p.motivo_rechazo}</div>}
          {p.puedo_aprobar && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', ...caja, padding: 10 }}>
              <input aria-label={t('pres.motivo')} placeholder={t('pres.motivo_ayuda')} value={motivo} onChange={e => setMotivo(e.target.value)} style={{ ...campo, flex: '1 1 220px' }} />
              <Button size="sm" variant="danger" disabled={!motivo.trim()} loading={ocupado === 'rechazar'} onClick={() => accion('rechazar', () => presupuestosApi.decidir(p.id, false, motivo))}>{t('pres.rechazar')}</Button>
              <Button size="sm" loading={ocupado === 'aprobar'} onClick={() => accion('aprobar', () => presupuestosApi.decidir(p.id, true))}>{t('pres.aprobar')}</Button>
            </div>
          )}
          {p.ambito === 'proyecto_previsto' && !p.project_id && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', fontSize: 'var(--text-sm)' }}>
              <span className="u-text2">{t('pres.previsto_sin_real')}</span>
              <select aria-label={t('pres.vincular')} value={vincular} onChange={e => setVincular(e.target.value)} style={{ ...campo, width: 'min(260px, 100%)' }}>
                <option value="">{t('pres.elige_proyecto')}</option>
                {(proyectos.data ?? []).map(pr => <option key={pr.id} value={pr.id}>{pr.code ? `${pr.code} — ` : ''}{pr.name}</option>)}
              </select>
              <Button size="sm" variant="secondary" disabled={!vincular} loading={ocupado === 'vincular'} onClick={() => accion('vincular', () => presupuestosApi.vincular(p.id, vincular))}>{t('pres.vincular')}</Button>
            </div>
          )}
          <Tabs active={tab} onChange={setTab} items={[
            { id: 'partidas', label: `${t('pres.tab_partidas')} · ${p.lineas.length}` },
            { id: 'seguimiento', label: t('pres.tab_seguimiento') },
            ...(p.seguir ? [
              { id: 'control', label: t('pres.tab_control') },
              { id: 'cierre', label: `${t('pres.tab_cierre')}${p.seguir.desviaciones_sin_explicar.length ? ` · ${p.seguir.desviaciones_sin_explicar.length}` : ''}` },
              { id: 'pedidos', label: `${t('pres.tab_pedidos')}${p.seguir.traspasos_pendientes ? ` · ${p.seguir.traspasos_pendientes}` : ''}` },
            ] : []),
            { id: 'estructura', label: t('pres.tab_estructura') },
            { id: 'escenarios', label: `${t('pres.tab_escenarios')} · ${p.versiones.length}` },
            { id: 'supuestos', label: t('pres.tab_supuestos') },
          ]} />
          {tab === 'partidas' && <Partidas p={p} dinero={dinero} onCambio={d => qc.setQueryData(['presupuesto', d.id], d)} />}
          {tab === 'seguimiento' && <Seguimiento p={p} dinero={dinero} />}
          {tab === 'control' && p.seguir && <ControlDelPresupuesto p={p} dinero={dinero} accion={accion} ocupado={ocupado} />}
          {tab === 'cierre' && p.seguir && <CierreDelPresupuesto p={p} dinero={dinero} accion={accion} ocupado={ocupado} />}
          {tab === 'pedidos' && p.seguir && <PedidosYTraspasos p={p} dinero={dinero} onCambio={() => qc.invalidateQueries({ queryKey: ['presupuesto', p.id] })} />}
          {tab === 'estructura' && <Estructura p={p} dinero={dinero} onAbrir={onAbrir} />}
          {tab === 'escenarios' && <Escenarios p={p} dinero={dinero} onAbrir={onAbrir} accion={accion} ocupado={ocupado} />}
          {tab === 'supuestos' && <SupuestosDelPresupuesto p={p} accion={accion} ocupado={ocupado} />}
        </div>
      )}
    </Modal>
  )
}

function resumenDelCalculo(l: Partida, t: (k: string, d?: string) => string, dinero: Dinero): string {
  const m = modoDe(l)
  if (m === 'conductor') return `${l.unidades} × ${dinero(l.precio_unitario)} · ${t(`pres.rec_${l.recurrencia || 'unica'}`)}`
  if (m === 'persona') return `${l.user_name ?? ''} · ${l.dedicacion_pct} % · ${t('pres.modo_persona')}`
  if (m === 'vacante') return `${l.perfil || t('pres.modo_vacante')} · ${dinero(l.salario_anual)}/${t('pres.anio')} · ${l.pais}${l.fecha_alta ? ` · ${t('pres.alta')} ${l.fecha_alta}` : ''}`
  if (m === 'horas') return `${l.user_name || l.perfil || ''} · ${l.horas} h × ${dinero(l.coste_hora)}`
  return t('pres.modo_importe')
}

function Partidas({ p, dinero, onCambio }: { p: FichaPresupuesto; dinero: Dinero; onCambio: (d: FichaPresupuesto) => void }) {
  const t = useAppT()
  const toast = useToast()
  const [guardando, setGuardando] = useState(false)
  const [editando, setEditando] = useState<Partida | null>(null)
  const [nueva, setNueva] = useState(0)        // cambia la clave: vacía el formulario tras añadir
  const guardar = async (cuerpo: Record<string, unknown>, lid?: string) => {
    setGuardando(true)
    try {
      onCambio(lid ? await presupuestosApi.editarPartida(p.id, lid, cuerpo) : await presupuestosApi.crearPartida(p.id, cuerpo))
      if (lid) setEditando(null); else setNueva(n => n + 1)
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setGuardando(false) }
  }
  const quitar = async (lid: string) => { try { onCambio(await presupuestosApi.borrarPartida(p.id, lid)) } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } }
  const grupos: { titulo: string; lineas: Partida[] }[] = [
    { titulo: t('pres.gastos'), lineas: p.lineas.filter(l => l.sentido !== 'ingreso') },
    { titulo: t('pres.ingresos'), lineas: p.lineas.filter(l => l.sentido === 'ingreso') },
  ].filter(g => g.lineas.length)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
      {p.lineas.length === 0 && <div className="u-text3-sm">{t('pres.sin_partidas')}</div>}
      {grupos.map(g => (
        // Tres columnas (concepto con su cálculo debajo, importe, acciones): caben
        // a 390 px sin esconder el importe tras un desplazamiento lateral.
        <div key={g.titulo}>
          <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', margin: '4px 0' }}>{g.titulo}</div>
          <table className="cabe" style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
            <colgroup><col /><col style={{ width: 120 }} /><col style={{ width: p.puedo_editar ? 72 : 0 }} /></colgroup>
            <thead><tr>
              <th style={th}>{t('pres.descripcion')}</th><th style={{ ...th, textAlign: 'right' }}>{t('pres.importe')}</th><th style={th} aria-label={t('pres.acciones')} />
            </tr></thead>
            <tbody>{g.lineas.map(l => (
              <tr key={l.id}>
                <td style={{ ...td, overflowWrap: 'anywhere' }}>
                  <div>{l.descripcion}{l.justificacion && <span title={l.justificacion} aria-label={t('pres.justificacion')} style={{ marginLeft: 6, color: 'var(--text-3)' }}><MessageSquareText size={12} /></span>}
                    {l.naturaleza === 'capex' && <span title={`${t('pres.vida_meses')}: ${l.vida_meses}`} style={{ marginLeft: 6, fontSize: 'var(--text-2xs)', color: 'var(--accent)', border: '1px solid currentColor', borderRadius: 4, padding: '0 4px' }}>CAPEX</span>}</div>
                  <div className="u-text3-xs">
                    {t(`pres.tipo_${l.tipo}`, l.tipo)} · {resumenDelCalculo(l, t, dinero)} · {Object.keys(l.meses).length} {t('pres.meses').toLowerCase()}{l.mes_desde || l.mes_hasta ? ` (${l.mes_desde ?? ''}→${l.mes_hasta ?? ''})` : ''}
                  </div>
                </td>
                <td style={num}>{dinero(l.importe)}</td>
                <td style={{ ...td, whiteSpace: 'nowrap', textAlign: 'right' }}>{p.puedo_editar && <>
                  <Button size="xs" variant="ghost" title={t('pres.editar_partida')} icon={<Pencil size={12} />} onClick={() => setEditando(l)}>{''}</Button>
                  <Button size="xs" variant="ghost" title={t('pres.quitar')} icon={<Trash2 size={12} />} onClick={() => quitar(l.id)}>{''}</Button>
                </>}</td>
              </tr>))}</tbody>
          </table>
        </div>
      ))}
      {p.puedo_editar && !editando && <FormularioDePartida key={nueva} p={p} guardando={guardando} onGuardar={c => guardar(c)} />}
      {editando && <FormularioDePartida key={editando.id} p={p} inicial={editando} guardando={guardando} onGuardar={c => guardar(c, editando.id)} onCancelar={() => setEditando(null)} />}
    </div>
  )
}

function Seguimiento({ p, dinero }: { p: FichaPresupuesto; dinero: Dinero }) {
  const t = useAppT()
  const inf = p.informe
  const conIngresos = inf.ingreso_plan > 0 || inf.ingreso_real > 0
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
      {inf.sin_real && <div role="status" style={{ fontSize: 'var(--text-sm)', color: 'var(--warning)' }}>{t('pres.previsto_sin_real')}</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(120px, 100%), 1fr))', gap: 10 }}>
        {[
          [t('pres.opex'), inf.opex_plan], [t('pres.capex'), inf.capex_plan], [t('pres.amortizacion'), inf.amortizacion_total],
          ...(conIngresos ? [[t('pres.margen_plan'), inf.margen_plan], [t('pres.margen_real'), inf.margen_real]] : []),
        ].map(([k, v]) => (
          <div key={k as string} style={caja}><div className="u-text3-xs">{k}</div><div style={{ fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{dinero(v as number)}</div></div>
        ))}
      </div>
      <div style={{ height: 240 }} role="img" aria-label={t('pres.plan_contra_real')}>
        <ResponsiveContainer>
          <ComposedChart data={inf.meses}>
            <CartesianGrid stroke="var(--surface-3)" vertical={false} />
            <XAxis dataKey="mes" tick={{ fill: 'var(--text-3)', fontSize: 'var(--text-xs)' }} />
            <YAxis tick={{ fill: 'var(--text-3)', fontSize: 'var(--text-xs)' }} />
            <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)' }} formatter={(v: number) => dinero(v)} />
            <Legend />
            <Bar dataKey="plan" name={t('pres.plan')} fill="var(--surface-4)" radius={[3, 3, 0, 0]} />
            <Bar dataKey="real" name={t('pres.real')} fill="var(--accent)" radius={[3, 3, 0, 0]} />
            {conIngresos && <Line dataKey="ingreso_plan" name={t('pres.ingreso_plan')} stroke="var(--success)" strokeDasharray="4 3" dot={false} />}
            {conIngresos && <Line dataKey="ingreso_real" name={t('pres.ingreso_real')} stroke="var(--success)" dot={false} />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(320px, 100%), 1fr))', gap: 14 }}>
        <div style={tablaConScroll}>
          <table className="responsive-stack u-table">
            <thead><tr><th style={th}>{t('pres.mes')}</th><th style={{ ...th, textAlign: 'right' }}>{t('pres.plan')}</th><th style={{ ...th, textAlign: 'right' }}>{t('pres.real')}</th><th style={{ ...th, textAlign: 'right' }}>{t('pres.desviacion')}</th>
              {inf.amortizacion_total > 0 && <th style={{ ...th, textAlign: 'right' }}>{t('pres.amortizacion')}</th>}
              {conIngresos && <th style={{ ...th, textAlign: 'right' }}>{t('pres.ingreso')}</th>}</tr></thead>
            <tbody>{inf.meses.map(m => (
              <tr key={m.mes}>
                <td data-label={t('pres.mes')} style={{ ...td, whiteSpace: 'nowrap' }}>{m.mes}{m.en_curso ? ` · ${t('pres.en_curso')}` : ''}</td>
                <td data-label={t('pres.plan')} style={num}>{dinero(m.plan)}</td><td data-label={t('pres.real')} style={num}>{dinero(m.real)}</td>
                <td data-label={t('pres.desviacion')} style={{ ...num, color: m.desviacion > 0 ? 'var(--danger)' : m.desviacion < 0 ? 'var(--success)' : undefined }}>{m.cerrado || m.en_curso ? dinero(m.desviacion) : '—'}</td>
                {inf.amortizacion_total > 0 && <td data-label={t('pres.amortizacion')} style={num}>{dinero(m.amortizacion)}</td>}
                {conIngresos && <td data-label={t('pres.ingreso')} style={num}>{dinero(m.ingreso_real || m.ingreso_plan)}</td>}
              </tr>))}</tbody>
          </table>
        </div>
        <div style={tablaConScroll}>
          <table className="cabe u-table">
            <thead><tr><th style={th}>{t('pres.tipo')}</th><th style={{ ...th, textAlign: 'right' }}>{t('pres.plan')}</th><th style={{ ...th, textAlign: 'right' }}>{t('pres.real')}</th><th style={{ ...th, textAlign: 'right' }}>%</th></tr></thead>
            <tbody>{inf.por_tipo.map(x => (
              <tr key={x.tipo}>
                <td style={td}>{t(`pres.tipo_${x.tipo}`, x.tipo)}</td><td style={num}>{dinero(x.plan)}</td><td style={num}>{dinero(x.real)}</td>
                <td style={{ ...num, color: (x.desviacion_pct ?? 0) > 0 ? 'var(--danger)' : undefined }}>{x.desviacion_pct == null ? '—' : `${x.desviacion_pct.toLocaleString(localeActivo())} %`}</td>
              </tr>))}</tbody>
          </table>
        </div>
      </div>
      <div className="u-text3-xs">{t('pres.como_se_calcula')}</div>
    </div>
  )
}

function Estructura({ p, dinero, onAbrir }: { p: FichaPresupuesto; dinero: Dinero; onAbrir: (id: string) => void }) {
  const t = useAppT()
  const te = p.techo_estado
  const uso = te && te.techo > 0 ? Math.min(100, Math.round((te.consumido_por_hijos / te.techo) * 100)) : 0
  return (
    <div className="u-stack-14">
      <div style={caja}>
        <div className="u-text3-xs">{t('pres.padre')}</div>
        {p.padre_ficha_id
          ? <button type="button" onClick={() => onAbrir(p.padre_ficha_id!)} style={{ background: 'none', border: 'none', padding: 0, color: 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 'var(--text-sm)' }}>{p.padre_name} · {t(`pres.ambito_${p.padre_ambito}`)}</button>
          : <div className="u-text2-sm">{t('pres.sin_padre')}</div>}
      </div>
      {te && (
        <div style={caja}>
          <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, fontSize: 'var(--text-sm)' }}>
            <span>{t('pres.techo')}: <strong>{dinero(te.techo)}</strong></span>
            <span>{t('pres.consumido_por_hijos')}: <strong>{dinero(te.consumido_por_hijos)}</strong></span>
            <span style={{ color: te.excedido ? 'var(--danger)' : 'var(--success)' }}>{t('pres.disponible')}: <strong>{dinero(te.disponible)}</strong></span>
          </div>
          <div role="progressbar" aria-valuenow={uso} aria-valuemin={0} aria-valuemax={100} aria-label={t('pres.techo')} style={{ marginTop: 8, height: 8, borderRadius: 99, background: 'var(--surface-3)', overflow: 'hidden' }}>
            <div style={{ width: `${uso}%`, height: '100%', background: te.excedido ? 'var(--danger)' : uso > 85 ? 'var(--warning)' : 'var(--success)' }} />
          </div>
        </div>
      )}
      {p.hijos.length > 0 ? (
        // Dos columnas (nombre con ámbito y estado debajo; importe a la derecha):
        // a 390 px una tabla de cuatro escondía el importe tras un desplazamiento.
        <table className="cabe u-table">
          <thead><tr><th style={th}>{t('pres.hijos')}</th><th style={{ ...th, textAlign: 'right' }}>{t('pres.gasto')}</th></tr></thead>
          <tbody>{p.hijos.map(h => (
            <tr key={h.id} onClick={() => onAbrir(h.id)} style={{ cursor: 'pointer' }}>
              <td style={td}>{h.name} · v{h.version}
                <div className="u-text3-xs">{t(`pres.ambito_${h.ambito}`)} · <span style={{ color: colorDeEstado(h.estado) }}>{t(`pres.estado_${h.estado}`)}</span></div></td>
              <td style={num}>{dinero(h.total_plan)}</td>
            </tr>))}</tbody>
          {p.consolidado_plan != null && <tfoot><tr><td style={{ ...td, fontWeight: 700 }}>{t('pres.consolidado')}</td><td style={{ ...num, fontWeight: 700 }}>{dinero(p.consolidado_plan)}</td></tr></tfoot>}
        </table>
      ) : <div className="u-text3-sm">{t('pres.sin_hijos')}</div>}
      <div className="u-text3-xs">{t('pres.estructura_ayuda')}</div>
    </div>
  )
}

function Escenarios({ p, dinero, onAbrir, accion, ocupado }: {
  p: FichaPresupuesto; dinero: Dinero; onAbrir: (id: string) => void
  accion: (clave: string, f: () => Promise<FichaPresupuesto>) => Promise<void>; ocupado: string | null
}) {
  const t = useAppT()
  const toast = useToast()
  const [nombre, setNombre] = useState('')
  const [inflacion, setInflacion] = useState('')
  const [otro, setOtro] = useState('')
  const [cmp, setCmp] = useState<ComparacionDePresupuestos | null>(null)
  const hermanos = useQuery({ queryKey: ['presupuestos', 'lista', p.year, p.ambito], queryFn: () => presupuestosApi.listar({ year: p.year, ambito: p.ambito }) })
  const candidatos = [...p.versiones.filter(v => v.id !== p.id).map(v => ({ id: v.id, nombre: `v${v.version} · ${t(`pres.estado_${v.estado}`)}` })),
    ...(hermanos.data ?? []).filter(b => b.name === p.name && b.escenario !== p.escenario).map(b => ({ id: b.id, nombre: `${b.escenario} · v${b.version}` }))]
  const comparar = async () => {
    try { setCmp(await presupuestosApi.comparar([p.id, otro])) } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }
  const tipos = cmp ? Array.from(new Set(cmp.presupuestos.flatMap(x => Object.keys(x.por_tipo)))) : []
  return (
    <div className="u-stack-14">
      <div style={tablaConScroll}>
        <table className="cabe u-table">
          <thead><tr><th style={th}>{t('pres.version')}</th><th style={th}>{t('pres.estado')}</th><th style={{ ...th, textAlign: 'right' }}>{t('pres.gasto')}</th></tr></thead>
          <tbody>{p.versiones.map(v => (
            <tr key={v.id} onClick={() => v.id !== p.id && onAbrir(v.id)} style={{ cursor: v.id !== p.id ? 'pointer' : 'default', background: v.id === p.id ? 'var(--accent-muted)' : undefined }}>
              <td style={td}>v{v.version}</td><td style={{ ...td, color: colorDeEstado(v.estado) }}>{t(`pres.estado_${v.estado}`)}</td><td style={num}>{dinero(v.total_plan)}</td>
            </tr>))}</tbody>
        </table>
      </div>
      <div style={{ ...caja, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'end' }}>
        <label style={{ flex: '1 1 160px' }}><span className="u-text3-xs">{t('pres.escenario_nuevo')}</span>
          <input aria-label={t('pres.escenario_nuevo')} value={nombre} onChange={e => setNombre(e.target.value)} placeholder={t('pres.escenario_ejemplo')} style={campo} /></label>
        <label style={{ flex: '0 1 140px' }}><span className="u-text3-xs">{t('pres.inflacion')}</span>
          <input aria-label={t('pres.inflacion')} type="number" step="any" value={inflacion} onChange={e => setInflacion(e.target.value)} placeholder={String(p.supuestos.inflacion_pct ?? 0)} style={campo} /></label>
        <Button size="sm" disabled={!nombre.trim()} loading={ocupado === 'escenario'}
          onClick={() => accion('escenario', () => presupuestosApi.escenario(p.id, nombre.trim(), inflacion === '' ? undefined : { ...p.supuestos, inflacion_pct: Number(inflacion) }))}>{t('pres.crear_escenario')}</Button>
      </div>
      <div style={{ ...caja, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'end' }}>
        <label style={{ flex: '1 1 220px' }}><span className="u-text3-xs">{t('pres.comparar_con')}</span>
          <select aria-label={t('pres.comparar_con')} value={otro} onChange={e => setOtro(e.target.value)} style={campo}>
            <option value="">—</option>{candidatos.map(c => <option key={c.id} value={c.id}>{c.nombre}</option>)}
          </select></label>
        <Button size="sm" variant="secondary" disabled={!otro} onClick={comparar}>{t('pres.comparar')}</Button>
      </div>
      {cmp && (
        <div style={tablaConScroll}>
          <table className="cabe u-table">
            <thead><tr><th style={th}><span className="u-sr-only">{t('pres.tipo')}</span></th>{cmp.presupuestos.map(x => <th key={x.id} style={{ ...th, textAlign: 'right' }}>{x.escenario} · v{x.version}</th>)}</tr></thead>
            <tbody>
              {tipos.map(tp => <tr key={tp}><td style={td}>{t(`pres.tipo_${tp}`, tp)}</td>{cmp.presupuestos.map(x => <td key={x.id} style={num}>{dinero(x.por_tipo[tp] ?? 0)}</td>)}</tr>)}
              {(['gasto', 'ingreso', 'margen'] as const).map(k => <tr key={k}><td style={{ ...td, fontWeight: 700 }}>{t(`pres.${k}`)}</td>{cmp.presupuestos.map(x => <td key={x.id} style={{ ...num, fontWeight: 700 }}>{dinero(x[k])}</td>)}</tr>)}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function SupuestosDelPresupuesto({ p, accion, ocupado }: { p: FichaPresupuesto; accion: (clave: string, f: () => Promise<FichaPresupuesto>) => Promise<void>; ocupado: string | null }) {
  const t = useAppT()
  const [inflacion, setInflacion] = useState(String(p.supuestos.inflacion_pct ?? ''))
  const [notas, setNotas] = useState(String(p.supuestos.notas ?? ''))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 560 }}>
      <label><span className="u-text3-xs">{t('pres.inflacion')}</span>
        <input aria-label={t('pres.inflacion')} type="number" step="any" value={inflacion} disabled={!p.puedo_editar} onChange={e => setInflacion(e.target.value)} style={campo} /></label>
      <label><span className="u-text3-xs">{t('pres.supuestos_notas')}</span>
        <textarea aria-label={t('pres.supuestos_notas')} rows={4} value={notas} disabled={!p.puedo_editar} onChange={e => setNotas(e.target.value)} style={{ ...campo, resize: 'vertical' }} /></label>
      <div className="u-text3-xs">{t('pres.supuestos_ayuda')}</div>
      {p.puedo_editar && <div><Button size="sm" loading={ocupado === 'supuestos'}
        onClick={() => accion('supuestos', () => presupuestosApi.editar(p.id, { supuestos: { ...p.supuestos, inflacion_pct: inflacion === '' ? 0 : Number(inflacion), notas } }))}>{t('pres.guardar')}</Button></div>}
    </div>
  )
}
