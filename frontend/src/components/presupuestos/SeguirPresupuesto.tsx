/**
 * Seguir un presupuesto aprobado a fondo (revisión 2026-11, P2).
 *
 * - Control: por tipo, plan, real, comprometido (pedidos y contratos/licencias
 *   de ALM), disponible y previsión al cierre, con su método de reprevisión
 *   (plan, ritmo real o a mano mes a mes).
 * - Cierre: los meses terminados se cierran (congela su real); antes, cada
 *   desviación que pase los umbrales necesita su explicación. Detalle del real
 *   de un mes hasta la imputación, el gasto o el pedido, y exportación CSV.
 * - Pedidos y traspasos: comprometer un pedido (pasa a real al facturarse) y
 *   pedir traspasos entre partidas o ampliaciones, que decide otro.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { presupuestosApi } from '../../services/api'
import type { FichaPresupuesto, MetodoPrevision, PedidoDePresupuesto as Pedido, TraspasoDePresupuesto as Traspaso } from '../../services/api'
import { Button, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, localeActivo } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { campo } from './FormularioDePartida'

type Dinero = (n?: number | null) => string
type Accion = (clave: string, f: () => Promise<FichaPresupuesto>) => Promise<void>

const caja: CSSProperties = { border: '1px solid var(--surface-4)', borderRadius: 10, padding: 12, minWidth: 0 }
const lbl: CSSProperties = { fontSize: 'var(--text-xs)', color: 'var(--text-3)', display: 'block', marginBottom: 3 }
const cifra: CSSProperties = { fontFamily: 'var(--font-mono)', fontWeight: 700, whiteSpace: 'nowrap' }
const rejilla: CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(150px, 100%), 1fr))', gap: 10, alignItems: 'end' }
const lista: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 8 }

function Cifra({ k, v, color }: { k: string; v: string; color?: string }) {
  return <span style={{ display: 'inline-flex', flexDirection: 'column', minWidth: 0 }}>
    <span style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)' }}>{k}</span>
    <span style={{ ...cifra, fontSize: 'var(--text-sm)', color }}>{v}</span>
  </span>
}

// ── Control por tipo y reprevisión ────────────────────────────────────────────

export function ControlDelPresupuesto({ p, dinero, accion, ocupado }: { p: FichaPresupuesto; dinero: Dinero; accion: Accion; ocupado: string | null }) {
  const t = useAppT()
  const s = p.seguir!
  const [manual, setManual] = useState<{ tipo: string; meses: Record<string, string> } | null>(null)
  const restantes = p.informe.meses.map(m => m.mes).filter(m => m >= (p.mes_actual ?? ''))
  const elegir = (tipo: string, metodo: MetodoPrevision) => {
    if (metodo === 'manual') {   // se abre con lo que queda por gastar repartido a partes iguales; se ajusta mes a mes
      const fila = s.por_tipo.find(x => x.tipo === tipo)
      const cada = fila && restantes.length ? Math.max(0, Math.round((fila.plan - fila.real) / restantes.length)) : 0
      setManual({ tipo, meses: Object.fromEntries(restantes.map(m => [m, String(cada)])) })
      return
    }
    setManual(null)
    accion(`prev-${tipo}`, () => presupuestosApi.prevision(p.id, tipo, metodo))
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(130px, 100%), 1fr))', gap: 10 }}>
        {([['plan', s.plan], ['real', s.real], ['comprometido', s.comprometido], ['disponible', s.disponible], ['prevision', s.prevision]] as const).map(([k, v]) => (
          <div key={k} style={caja}>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t(`pres.${k}`)}</div>
            <div style={{ ...cifra, color: (k === 'disponible' && v < 0) || (k === 'prevision' && v > s.plan) ? 'var(--danger)' : undefined }}>{dinero(v)}</div>
          </div>
        ))}
      </div>
      <div style={lista}>
        {s.por_tipo.map(x => {
          const pct = x.plan > 0 ? Math.min(100, (x.real / x.plan) * 100) : 0
          const pctC = x.plan > 0 ? Math.min(100 - pct, (x.comprometido / x.plan) * 100) : 0
          return (
            <div key={x.tipo} style={caja}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'space-between' }}>
                <strong style={{ fontSize: 'var(--text-sm)' }}>{t(`pres.tipo_${x.tipo}`, x.tipo)}</strong>
                <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('pres.metodo_prevision')}
                  <select aria-label={`${t('pres.metodo_prevision')} · ${x.tipo}`} value={manual?.tipo === x.tipo ? 'manual' : x.metodo} disabled={!p.puedo_gestionar || ocupado === `prev-${x.tipo}`}
                    onChange={e => elegir(x.tipo, e.target.value as MetodoPrevision)} style={{ ...campo, width: 'auto', padding: '4px 8px' }}>
                    {(['plan', 'ritmo', 'manual'] as const).map(m => <option key={m} value={m}>{t(`pres.metodo_${m}`)}</option>)}
                  </select></label>
              </div>
              <div role="progressbar" aria-label={`${t('pres.consumo')} · ${x.tipo}`} aria-valuenow={Math.round(x.consumo_pct ?? 0)} aria-valuemin={0} aria-valuemax={100}
                style={{ display: 'flex', margin: '8px 0', height: 8, borderRadius: 99, background: 'var(--surface-3)', overflow: 'hidden' }}>
                <div style={{ width: `${pct}%`, background: (x.consumo_pct ?? 0) >= 100 ? 'var(--danger)' : 'var(--accent)' }} />
                <div style={{ width: `${pctC}%`, background: 'var(--warning)' }} />
              </div>
              <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                <Cifra k={t('pres.plan')} v={dinero(x.plan)} />
                <Cifra k={t('pres.real')} v={dinero(x.real)} />
                <Cifra k={t('pres.comprometido')} v={dinero(x.comprometido)} />
                <Cifra k={t('pres.disponible')} v={dinero(x.disponible)} color={x.disponible < 0 ? 'var(--danger)' : undefined} />
                <Cifra k={t('pres.prevision')} v={dinero(x.prevision)} color={x.prevision > x.plan ? 'var(--danger)' : undefined} />
              </div>
              {manual?.tipo === x.tipo && (
                <div style={{ ...rejilla, marginTop: 10 }}>
                  {restantes.map(m => (
                    <label key={m}><span style={lbl}>{m}</span>
                      <input aria-label={`${x.tipo} ${m}`} type="number" min={0} step="any" value={manual.meses[m] ?? ''} style={campo}
                        onChange={e => setManual(v => v && ({ ...v, meses: { ...v.meses, [m]: e.target.value } }))} /></label>
                  ))}
                  <div style={{ display: 'flex', gap: 6 }}>
                    <Button size="sm" loading={ocupado === `prev-${x.tipo}`} onClick={() => accion(`prev-${x.tipo}`, () => presupuestosApi.prevision(p.id, x.tipo, 'manual',
                      Object.fromEntries(Object.entries(manual.meses).map(([k, v]) => [k, Number(v || 0)])))).then(() => setManual(null))}>{t('pres.guardar')}</Button>
                    <Button size="sm" variant="ghost" onClick={() => setManual(null)}>{t('pres.cancelar')}</Button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('pres.control_ayuda')}</div>
    </div>
  )
}

// ── Cierre mensual, desviaciones y detalle del real ───────────────────────────

export function CierreDelPresupuesto({ p, dinero, accion, ocupado }: { p: FichaPresupuesto; dinero: Dinero; accion: Accion; ocupado: string | null }) {
  const t = useAppT()
  const toast = useToast()
  const s = p.seguir!
  const [textos, setTextos] = useState<Record<string, string>>({})
  const meses = p.informe.meses.map(m => m.mes).filter(m => m <= (p.mes_actual ?? ''))
  const [mes, setMes] = useState(meses[meses.length - 1] ?? '')
  const [tipo, setTipo] = useState('')
  const detalle = useQuery({ queryKey: ['presupuesto', p.id, 'detalle', mes, tipo], enabled: !!mes,
    queryFn: () => presupuestosApi.detalleDelReal(p.id, mes, tipo || undefined) })
  const exportar = async () => {
    try {
      const blob = await presupuestosApi.exportarCsv(p.id)
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob); a.download = `${p.name}-v${p.version}.csv`; a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }
  const clave = (m: string, tp: string) => `${m}|${tp}`
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
      <div style={caja}>
        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, marginBottom: 8 }}>{t('pres.cierre_mensual')}</div>
        {s.meses_por_cerrar.length === 0 && s.meses_cerrados.length === 0 && <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>{t('pres.nada_que_cerrar')}</div>}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {s.meses_cerrados.map(m => (
            <span key={m} style={{ display: 'inline-flex', gap: 6, alignItems: 'center', fontSize: 'var(--text-xs)', border: '1px solid var(--success)', color: 'var(--success)', borderRadius: 99, padding: '2px 4px 2px 10px' }}>
              {m} · {t('pres.cerrado')}
              {p.puedo_decidir_traspasos && <Button size="xs" variant="ghost" loading={ocupado === `reabrir-${m}`} onClick={() => accion(`reabrir-${m}`, () => presupuestosApi.reabrirMes(p.id, m))}>{t('pres.reabrir')}</Button>}
            </span>
          ))}
          {p.puedo_gestionar && s.meses_por_cerrar.map(m => (
            <Button key={m} size="sm" variant="secondary" loading={ocupado === `cerrar-${m}`} onClick={() => accion(`cerrar-${m}`, () => presupuestosApi.cerrarMes(p.id, m))}>{t('pres.cerrar_mes', { mes: m })}</Button>
          ))}
        </div>
      </div>
      {s.desviaciones_sin_explicar.length > 0 && (
        <div style={caja}>
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, marginBottom: 4 }}>{t('pres.desviaciones_a_explicar')}</div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginBottom: 8 }}>{t('pres.desviaciones_ayuda')}</div>
          <div style={lista}>
            {s.desviaciones_sin_explicar.map(d => (
              <div key={clave(d.mes, d.tipo)} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'end' }}>
                <div style={{ flex: '1 1 200px', minWidth: 0, fontSize: 'var(--text-sm)' }}>
                  <strong>{d.mes} · {t(`pres.tipo_${d.tipo}`, d.tipo)}</strong>
                  <div style={{ fontSize: 'var(--text-xs)', color: d.desviacion > 0 ? 'var(--danger)' : 'var(--success)' }}>
                    {t('pres.plan')} {dinero(d.plan)} · {t('pres.real')} {dinero(d.real)} · {d.desviacion > 0 ? '+' : ''}{dinero(d.desviacion)}{d.desviacion_pct != null ? ` (${d.desviacion_pct.toLocaleString(localeActivo())} %)` : ''}
                  </div>
                </div>
                <input aria-label={`${t('pres.explicacion')} ${d.mes} ${d.tipo}`} placeholder={t('pres.explicacion')} value={textos[clave(d.mes, d.tipo)] ?? ''} disabled={!p.puedo_gestionar}
                  onChange={e => setTextos(v => ({ ...v, [clave(d.mes, d.tipo)]: e.target.value }))} style={{ ...campo, flex: '2 1 220px' }} />
                {p.puedo_gestionar && <Button size="sm" disabled={!(textos[clave(d.mes, d.tipo)] ?? '').trim()} loading={ocupado === `expl-${clave(d.mes, d.tipo)}`}
                  onClick={() => accion(`expl-${clave(d.mes, d.tipo)}`, () => presupuestosApi.explicar(p.id, d.mes, d.tipo, textos[clave(d.mes, d.tipo)]))}>{t('pres.guardar')}</Button>}
              </div>
            ))}
          </div>
        </div>
      )}
      <div style={caja}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'end', marginBottom: 8 }}>
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, flex: '1 1 160px' }}>{t('pres.detalle_del_real')}</div>
          <select aria-label={t('pres.mes')} value={mes} onChange={e => setMes(e.target.value)} style={{ ...campo, width: 'auto' }}>
            {meses.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <select aria-label={t('pres.tipo')} value={tipo} onChange={e => setTipo(e.target.value)} style={{ ...campo, width: 'auto' }}>
            <option value="">{t('pres.todos_los_tipos')}</option>
            {p.tipos.map(tp => <option key={tp} value={tp}>{t(`pres.tipo_${tp}`, tp)}</option>)}
          </select>
          <Button size="sm" variant="secondary" icon={<Download size={13} />} onClick={exportar}>CSV</Button>
        </div>
        {detalle.isLoading ? <Spinner /> : detalle.isError ? <div role="alert" style={{ color: 'var(--danger)' }}>{extractErr(detalle.error, GENERIC_ERROR_FALLBACK)}</div>
          : (detalle.data ?? []).length === 0 ? <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>{t('pres.sin_apuntes')}</div>
          : (
            // Dos columnas (qué y quién debajo; importe a la derecha): caben a 390 px.
            <table className="cabe" style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
              <colgroup><col /><col style={{ width: 110 }} /></colgroup>
              <tbody>{(detalle.data ?? []).map(a => (
                <tr key={`${a.origen}-${a.id}`}>
                  <td style={{ padding: '6px 4px', borderBottom: '1px solid var(--surface-2)', overflowWrap: 'anywhere', fontSize: 'var(--text-sm)' }}>
                    {a.concepto || '—'}
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{a.fecha} · {t(`pres.origen_${a.origen}`)} · {t(`pres.tipo_${a.tipo}`, a.tipo)}{a.quien ? ` · ${a.quien}` : ''}{a.horas ? ` · ${a.horas} h` : ''}</div>
                  </td>
                  <td style={{ padding: '6px 4px', borderBottom: '1px solid var(--surface-2)', textAlign: 'right', ...cifra, fontWeight: 400, fontSize: 'var(--text-sm)' }}>{dinero(a.importe)}</td>
                </tr>))}</tbody>
              <tfoot><tr><td style={{ padding: '6px 4px', fontWeight: 700, fontSize: 'var(--text-sm)' }}>{t('pres.total')}</td>
                <td style={{ padding: '6px 4px', textAlign: 'right', ...cifra, fontSize: 'var(--text-sm)' }}>{dinero((detalle.data ?? []).reduce((x, a) => x + a.importe, 0))}</td></tr></tfoot>
            </table>
          )}
      </div>
    </div>
  )
}

// ── Pedidos y traspasos ───────────────────────────────────────────────────────

export function PedidosYTraspasos({ p, dinero, onCambio }: { p: FichaPresupuesto; dinero: Dinero; onCambio: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const [ocupado, setOcupado] = useState<string | null>(null)
  const vacioP = { tipo: p.tipos[0] ?? '', descripcion: '', proveedor: '', referencia: '', importe: '', mes: p.mes_actual ?? '' }
  const [ped, setPed] = useState(vacioP)
  const vacioT = { desde: '', hacia: '', hacia_tipo: p.tipos[0] ?? '', importe: '', motivo: '' }
  const [tr, setTr] = useState(vacioT)
  const [factura, setFactura] = useState<{ id: string; fecha: string; importe: string } | null>(null)
  const [rechazo, setRechazo] = useState<Record<string, string>>({})
  const gastos = p.lineas.filter(l => l.sentido !== 'ingreso')
  const hacer = async (clave: string, f: () => Promise<unknown>, despues?: () => void) => {
    setOcupado(clave)
    try {
      const r = await f() as { avisos?: string[] } | undefined
      for (const aviso of r?.avisos ?? []) toast.warning(aviso, 8000)
      despues?.(); onCambio()
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setOcupado(null) }
  }
  const linea = (id?: string | null) => gastos.find(l => l.id === id)?.descripcion ?? '—'
  const colorPedido = (e: Pedido['estado']) => e === 'facturado' ? 'var(--success)' : e === 'anulado' ? 'var(--text-3)' : 'var(--warning)'
  const colorTraspaso = (e: Traspaso['estado']) => e === 'aprobado' ? 'var(--success)' : e === 'rechazado' ? 'var(--danger)' : 'var(--warning)'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
      <div style={caja}>
        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{t('pres.pedidos')}</div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', margin: '2px 0 10px' }}>{t('pres.pedidos_ayuda')}</div>
        {p.puedo_gestionar && (
          <div style={rejilla}>
            <label><span style={lbl}>{t('pres.tipo')}</span>
              <select aria-label={t('pres.tipo')} value={ped.tipo} onChange={e => setPed(v => ({ ...v, tipo: e.target.value }))} style={campo}>
                {p.tipos.map(tp => <option key={tp} value={tp}>{t(`pres.tipo_${tp}`, tp)}</option>)}</select></label>
            <label style={{ gridColumn: '1 / -1' }}><span style={lbl}>{t('pres.descripcion')}</span>
              <input aria-label={t('pres.descripcion')} value={ped.descripcion} onChange={e => setPed(v => ({ ...v, descripcion: e.target.value }))} style={campo} /></label>
            <label><span style={lbl}>{t('pres.proveedor')}</span>
              <input aria-label={t('pres.proveedor')} value={ped.proveedor} onChange={e => setPed(v => ({ ...v, proveedor: e.target.value }))} style={campo} /></label>
            <label><span style={lbl}>{t('pres.referencia')}</span>
              <input aria-label={t('pres.referencia')} value={ped.referencia} onChange={e => setPed(v => ({ ...v, referencia: e.target.value }))} style={campo} /></label>
            <label><span style={lbl}>{t('pres.importe')}</span>
              <input aria-label={t('pres.importe')} type="number" min={0} step="any" value={ped.importe} onChange={e => setPed(v => ({ ...v, importe: e.target.value }))} style={campo} /></label>
            <label><span style={lbl}>{t('pres.mes')}</span>
              <input aria-label={t('pres.mes')} type="month" value={ped.mes} min={p.periodo_desde.slice(0, 7)} max={p.periodo_hasta.slice(0, 7)} onChange={e => setPed(v => ({ ...v, mes: e.target.value }))} style={campo} /></label>
            <div><Button size="sm" disabled={!ped.descripcion.trim() || !(Number(ped.importe) > 0) || !ped.mes} loading={ocupado === 'pedido'}
              onClick={() => hacer('pedido', () => presupuestosApi.crearPedido(p.id, { ...ped, importe: Number(ped.importe), proveedor: ped.proveedor || null, referencia: ped.referencia || null }), () => setPed(vacioP))}>{t('pres.comprometer')}</Button></div>
          </div>
        )}
        <div style={{ ...lista, marginTop: 10 }}>
          {p.pedidos.length === 0 && <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>{t('pres.sin_pedidos')}</div>}
          {p.pedidos.map(x => (
            <div key={x.id} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', borderTop: '1px solid var(--surface-3)', paddingTop: 8 }}>
              <div style={{ flex: '1 1 200px', minWidth: 0, fontSize: 'var(--text-sm)', overflowWrap: 'anywhere' }}>
                {x.descripcion}
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{x.mes} · {t(`pres.tipo_${x.tipo}`, x.tipo)}{x.proveedor ? ` · ${x.proveedor}` : ''}{x.referencia ? ` · ${x.referencia}` : ''}
                  {' · '}<span style={{ color: colorPedido(x.estado) }}>{t(`pres.pedido_${x.estado}`)}{x.fecha_factura ? ` ${x.fecha_factura}` : ''}</span></div>
              </div>
              <span style={{ ...cifra, fontWeight: 400, fontSize: 'var(--text-sm)' }}>{dinero(x.estado === 'facturado' ? x.importe_facturado ?? x.importe : x.importe)}</span>
              {p.puedo_gestionar && x.estado === 'comprometido' && factura?.id !== x.id && <span style={{ display: 'flex', gap: 4 }}>
                <Button size="xs" variant="secondary" onClick={() => setFactura({ id: x.id, fecha: new Date().toISOString().slice(0, 10), importe: String(x.importe) })}>{t('pres.facturado')}</Button>
                <Button size="xs" variant="ghost" loading={ocupado === `anular-${x.id}`} onClick={() => hacer(`anular-${x.id}`, () => presupuestosApi.estadoDePedido(x.id, { estado: 'anulado' }))}>{t('pres.anular')}</Button>
              </span>}
              {factura?.id === x.id && (
                <div style={{ ...rejilla, flexBasis: '100%' }}>
                  <label><span style={lbl}>{t('pres.fecha_factura')}</span>
                    <input aria-label={t('pres.fecha_factura')} type="date" value={factura.fecha} onChange={e => setFactura(v => v && ({ ...v, fecha: e.target.value }))} style={campo} /></label>
                  <label><span style={lbl}>{t('pres.importe_facturado')}</span>
                    <input aria-label={t('pres.importe_facturado')} type="number" min={0} step="any" value={factura.importe} onChange={e => setFactura(v => v && ({ ...v, importe: e.target.value }))} style={campo} /></label>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <Button size="sm" disabled={!factura.fecha} loading={ocupado === `fact-${x.id}`}
                      onClick={() => hacer(`fact-${x.id}`, () => presupuestosApi.estadoDePedido(x.id, { estado: 'facturado', fecha_factura: factura.fecha, importe_facturado: Number(factura.importe || 0) }), () => setFactura(null))}>{t('pres.guardar')}</Button>
                    <Button size="sm" variant="ghost" onClick={() => setFactura(null)}>{t('pres.cancelar')}</Button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
      <div style={caja}>
        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{t('pres.traspasos')}</div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', margin: '2px 0 10px' }}>{t('pres.traspasos_ayuda')}</div>
        {p.puedo_gestionar && (
          <div style={rejilla}>
            <label><span style={lbl}>{t('pres.desde_partida')}</span>
              <select aria-label={t('pres.desde_partida')} value={tr.desde} onChange={e => setTr(v => ({ ...v, desde: e.target.value }))} style={campo}>
                <option value="">{t('pres.ampliacion')}</option>
                {gastos.map(l => <option key={l.id} value={l.id}>{l.descripcion}</option>)}</select></label>
            <label><span style={lbl}>{t('pres.hacia_partida')}</span>
              <select aria-label={t('pres.hacia_partida')} value={tr.hacia} onChange={e => setTr(v => ({ ...v, hacia: e.target.value }))} style={campo}>
                <option value="">{t('pres.partida_nueva')}</option>
                {gastos.filter(l => l.id !== tr.desde).map(l => <option key={l.id} value={l.id}>{l.descripcion}</option>)}</select></label>
            {!tr.hacia && <label><span style={lbl}>{t('pres.tipo')}</span>
              <select aria-label={t('pres.tipo_de_la_nueva')} value={tr.hacia_tipo} onChange={e => setTr(v => ({ ...v, hacia_tipo: e.target.value }))} style={campo}>
                {p.tipos.map(tp => <option key={tp} value={tp}>{t(`pres.tipo_${tp}`, tp)}</option>)}</select></label>}
            <label><span style={lbl}>{t('pres.importe')}</span>
              <input aria-label={`${t('pres.importe')} · ${t('pres.traspasos')}`} type="number" min={0} step="any" value={tr.importe} onChange={e => setTr(v => ({ ...v, importe: e.target.value }))} style={campo} /></label>
            <label style={{ gridColumn: '1 / -1' }}><span style={lbl}>{t('pres.motivo')}</span>
              <input aria-label={`${t('pres.motivo')} · ${t('pres.traspasos')}`} value={tr.motivo} onChange={e => setTr(v => ({ ...v, motivo: e.target.value }))} style={campo} /></label>
            <div><Button size="sm" disabled={!(Number(tr.importe) > 0) || !tr.motivo.trim()} loading={ocupado === 'traspaso'}
              onClick={() => hacer('traspaso', () => presupuestosApi.pedirTraspaso(p.id, {
                desde_linea_id: tr.desde || null, hacia_linea_id: tr.hacia || null, hacia_tipo: tr.hacia ? null : tr.hacia_tipo,
                importe: Number(tr.importe), motivo: tr.motivo }), () => setTr(vacioT))}>{t('pres.pedir_traspaso')}</Button></div>
          </div>
        )}
        <div style={{ ...lista, marginTop: 10 }}>
          {p.traspasos.length === 0 && <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>{t('pres.sin_traspasos')}</div>}
          {p.traspasos.map(x => (
            <div key={x.id} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', borderTop: '1px solid var(--surface-3)', paddingTop: 8 }}>
              <div style={{ flex: '1 1 200px', minWidth: 0, fontSize: 'var(--text-sm)', overflowWrap: 'anywhere' }}>
                {x.desde_linea_id ? linea(x.desde_linea_id) : t('pres.ampliacion')} → {x.hacia_linea_id ? linea(x.hacia_linea_id) : `${t('pres.partida_nueva')} (${t(`pres.tipo_${x.hacia_tipo}`, x.hacia_tipo ?? '')})`}
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{x.motivo} · <span style={{ color: colorTraspaso(x.estado) }}>{t(`pres.traspaso_${x.estado}`)}</span>{x.motivo_rechazo ? ` · ${x.motivo_rechazo}` : ''}</div>
              </div>
              <span style={{ ...cifra, fontWeight: 400, fontSize: 'var(--text-sm)' }}>{dinero(x.importe)}</span>
              {p.puedo_decidir_traspasos && x.estado === 'pendiente' && <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center' }}>
                <input aria-label={`${t('pres.motivo_rechazo')} ${x.id}`} placeholder={t('pres.motivo_rechazo')} value={rechazo[x.id] ?? ''} onChange={e => setRechazo(v => ({ ...v, [x.id]: e.target.value }))} style={{ ...campo, width: 160, padding: '4px 8px' }} />
                <Button size="xs" variant="danger" disabled={!(rechazo[x.id] ?? '').trim()} loading={ocupado === `rech-${x.id}`} onClick={() => hacer(`rech-${x.id}`, () => presupuestosApi.decidirTraspaso(x.id, false, rechazo[x.id]))}>{t('pres.rechazar')}</Button>
                <Button size="xs" loading={ocupado === `apr-${x.id}`} onClick={() => hacer(`apr-${x.id}`, () => presupuestosApi.decidirTraspaso(x.id, true))}>{t('pres.aprobar')}</Button>
              </span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Cuadro de control ─────────────────────────────────────────────────────────

const SEMAFORO = { verde: 'var(--success)', ambar: 'var(--warning)', rojo: 'var(--danger)' } as const

export function CuadroDeControl({ year, onAbrir }: { year: number; onAbrir: (id: string) => void }) {
  const t = useAppT()
  const q = useQuery({ queryKey: ['presupuestos', 'cuadro', year], queryFn: () => presupuestosApi.cuadro(year) })
  // Cada renglón en su moneda.
  const dinero = (n: number, moneda: string) => n.toLocaleString(localeActivo(), { style: 'currency', currency: moneda || 'EUR', maximumFractionDigits: 0 })
  if (q.isLoading) return <Spinner />
  if (q.isError) return <div role="alert" style={{ color: 'var(--danger)' }}>{extractErr(q.error, GENERIC_ERROR_FALLBACK)}</div>
  const filas = q.data ?? []
  const cuenta = (s: keyof typeof SEMAFORO) => filas.filter(f => f.semaforo === s).length
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 'var(--text-sm)' }}>
        {(['rojo', 'ambar', 'verde'] as const).map(s => (
          <span key={s} style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
            <span aria-hidden style={{ width: 10, height: 10, borderRadius: 99, background: SEMAFORO[s] }} />{t(`pres.semaforo_${s}`)}: <strong>{cuenta(s)}</strong>
          </span>
        ))}
      </div>
      {filas.length === 0 && <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>{t('pres.cuadro_vacio')}</div>}
      {filas.map(f => (
        <button key={f.id} type="button" onClick={() => onAbrir(f.id)} style={{ ...caja, display: 'flex', flexDirection: 'column', gap: 6, width: '100%', textAlign: 'left',
          cursor: 'pointer', background: 'transparent', color: 'var(--text-1)', fontFamily: 'inherit', borderLeft: `4px solid ${SEMAFORO[f.semaforo]}` }}>
          <span style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
            <strong style={{ flex: '1 1 180px', minWidth: 0, overflowWrap: 'anywhere' }}>{f.name}</strong>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t(`pres.ambito_${f.ambito}`)} · v{f.version} · <span style={{ color: SEMAFORO[f.semaforo] }}>{t(`pres.semaforo_${f.semaforo}`)}</span></span>
          </span>
          {f.estado === 'aprobado' ? <>
            <span role="progressbar" aria-label={t('pres.consumo')} aria-valuenow={Math.round(f.consumo_pct ?? 0)} aria-valuemin={0} aria-valuemax={100}
              style={{ display: 'flex', height: 6, borderRadius: 99, background: 'var(--surface-3)', overflow: 'hidden' }}>
              <span style={{ width: `${Math.min(100, f.plan ? (f.real / f.plan) * 100 : 0)}%`, background: SEMAFORO[f.semaforo] }} />
              <span style={{ width: `${Math.min(100, f.plan ? (f.comprometido / f.plan) * 100 : 0)}%`, background: 'var(--surface-4)' }} />
            </span>
            <span style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
              <Cifra k={t('pres.plan')} v={dinero(f.plan, f.currency)} />
              <Cifra k={t('pres.real')} v={dinero(f.real, f.currency)} />
              <Cifra k={t('pres.comprometido')} v={dinero(f.comprometido, f.currency)} />
              <Cifra k={t('pres.disponible')} v={dinero(f.disponible, f.currency)} color={f.disponible < 0 ? 'var(--danger)' : undefined} />
              <Cifra k={t('pres.prevision')} v={dinero(f.prevision, f.currency)} color={f.prevision > f.plan ? 'var(--danger)' : undefined} />
              <Cifra k={t('pres.consumo')} v={f.consumo_pct == null ? '—' : `${f.consumo_pct.toLocaleString(localeActivo())} %`} />
            </span>
            {(f.meses_por_cerrar > 0 || f.desviaciones_sin_explicar > 0 || f.traspasos_pendientes > 0) && (
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--warning)' }}>
                {[f.meses_por_cerrar && t('pres.n_meses_por_cerrar', { n: f.meses_por_cerrar }),
                  f.desviaciones_sin_explicar && t('pres.n_desviaciones', { n: f.desviaciones_sin_explicar }),
                  f.traspasos_pendientes && t('pres.n_traspasos', { n: f.traspasos_pendientes })].filter(Boolean).join(' · ')}
              </span>)}
          </> : <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t(`pres.estado_${f.estado}`)} · {t('pres.sin_seguimiento')} · {t('pres.plan')} {dinero(f.plan, f.currency)}</span>}
        </button>
      ))}
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('pres.cuadro_ayuda')}</div>
    </div>
  )
}
