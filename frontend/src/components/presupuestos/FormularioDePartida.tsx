/**
 * Formulario de una partida de presupuesto (revisión 2026-11).
 *
 * Cada partida es de gasto o de ingreso y se calcula de una de estas formas
 * (el servidor hace el cálculo; aquí sólo se recogen los datos):
 *  - importe (repartido por igual),
 *  - unidades × precio con recurrencia,
 *  - persona por coste cargado (estructura de costes vigente cada mes) × % de dedicación,
 *  - horas × coste/hora (persona o perfil),
 *  - vacante: salario anual + cargas del país, desde su alta.
 * Un gasto puede ser CAPEX (con vida para amortizarlo). Se puede acotar a unos meses.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { Button, UserSelect } from '../ui'
import type { FichaPresupuesto, Partida } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'

export const campo: CSSProperties = { width: '100%', boxSizing: 'border-box', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 10px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }
const etiqueta: CSSProperties = { fontSize: 'var(--text-xs)', color: 'var(--text-3)', display: 'block', marginBottom: 3 }

type Modo = 'importe' | 'conductor' | 'persona' | 'horas' | 'vacante'

export function modoDe(l: Partial<Partida>): Modo {
  if (l.unidades != null && l.precio_unitario != null) return 'conductor'
  if (l.salario_anual != null) return 'vacante'
  if (l.user_id && l.dedicacion_pct != null && l.horas == null) return 'persona'
  if (l.horas != null) return 'horas'
  return 'importe'
}

const txt = (v: unknown) => (v == null ? '' : String(v))

export default function FormularioDePartida({ p, inicial, onGuardar, onCancelar, guardando }: {
  p: FichaPresupuesto
  inicial?: Partida
  onGuardar: (cuerpo: Record<string, unknown>) => void
  onCancelar?: () => void
  guardando: boolean
}) {
  const t = useAppT()
  const [f, setF] = useState({
    sentido: inicial?.sentido ?? 'gasto', modo: inicial ? modoDe(inicial) : 'importe' as Modo,
    tipo: inicial?.tipo ?? p.tipos[0] ?? '', descripcion: inicial?.descripcion ?? '',
    importe: txt(inicial?.importe), unidades: txt(inicial?.unidades), precio_unitario: txt(inicial?.precio_unitario),
    recurrencia: inicial?.recurrencia ?? 'mensual', user_id: inicial?.user_id ?? '', perfil: inicial?.perfil ?? '',
    dedicacion_pct: txt(inicial?.dedicacion_pct ?? (inicial ? '' : 100)), horas: txt(inicial?.horas), coste_hora: txt(inicial?.coste_hora),
    salario_anual: txt(inicial?.salario_anual), pais: inicial?.pais ?? '', fecha_alta: inicial?.fecha_alta ?? '',
    naturaleza: inicial?.naturaleza ?? 'opex', vida_meses: txt(inicial?.vida_meses),
    mes_desde: inicial?.mes_desde ?? '', mes_hasta: inicial?.mes_hasta ?? '', justificacion: inicial?.justificacion ?? '',
  })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF(v => ({ ...v, [k]: e.target.value }))
  const tipos = f.sentido === 'ingreso' ? p.tipos_ingreso : p.tipos
  const modos: Modo[] = f.sentido === 'ingreso' ? ['importe', 'conductor'] : ['importe', 'conductor', 'persona', 'horas', 'vacante']
  const desde = p.periodo_desde.slice(0, 7)
  const hasta = p.periodo_hasta.slice(0, 7)

  const listo = f.descripcion.trim() && f.tipo && (
    f.modo === 'importe' ? f.importe !== '' :
    f.modo === 'conductor' ? f.unidades !== '' && f.precio_unitario !== '' :
    f.modo === 'persona' ? !!f.user_id && f.dedicacion_pct !== '' :
    f.modo === 'horas' ? f.horas !== '' && (f.coste_hora !== '' || !!f.user_id) :
    f.salario_anual !== '' && f.pais.length === 2) && (f.naturaleza !== 'capex' || f.vida_meses !== '')

  const guardar = () => {
    const n = (v: string) => (v === '' ? null : Number(v))
    // Se mandan a null los campos de los otros modos: así cambiar de modo al editar no deja restos.
    const cuerpo: Record<string, unknown> = {
      sentido: f.sentido, tipo: f.tipo, descripcion: f.descripcion, naturaleza: f.sentido === 'ingreso' ? 'opex' : f.naturaleza,
      vida_meses: f.naturaleza === 'capex' && f.sentido === 'gasto' ? n(f.vida_meses) : null,
      mes_desde: f.mes_desde || null, mes_hasta: f.mes_hasta || null, justificacion: f.justificacion || null,
      unidades: null, precio_unitario: null, recurrencia: null, user_id: null, perfil: null, dedicacion_pct: null,
      horas: null, coste_hora: null, salario_anual: null, pais: null, fecha_alta: null,
    }
    if (f.modo === 'importe') cuerpo.importe = n(f.importe)
    if (f.modo === 'conductor') Object.assign(cuerpo, { unidades: n(f.unidades), precio_unitario: n(f.precio_unitario), recurrencia: f.recurrencia })
    if (f.modo === 'persona') Object.assign(cuerpo, { user_id: f.user_id, dedicacion_pct: n(f.dedicacion_pct) })
    if (f.modo === 'horas') Object.assign(cuerpo, { horas: n(f.horas), coste_hora: n(f.coste_hora), user_id: f.user_id || null, perfil: f.perfil || null })
    if (f.modo === 'vacante') Object.assign(cuerpo, { salario_anual: n(f.salario_anual), pais: f.pais.toUpperCase(), fecha_alta: f.fecha_alta || null,
      perfil: f.perfil || null, dedicacion_pct: n(f.dedicacion_pct) })
    onGuardar(cuerpo)
  }

  // Una función que devuelve el campo, no un componente: definido aquí dentro se
  // volvería a montar en cada tecla y el cursor saltaría fuera.
  // `ancho`: toda la fila. Con `span 2` la rejilla no podía bajar a una columna
  // y a 390 px empujaba los campos fuera del recuadro.
  const entrada = ({ k, label, tipo = 'number', ayuda, ancho }: { k: keyof typeof f; label: string; tipo?: string; ayuda?: string; ancho?: boolean }) => (
    <label key={k} style={ancho ? { gridColumn: '1 / -1' } : undefined}><span style={etiqueta}>{label}</span>
      <input aria-label={label} type={tipo} min={tipo === 'number' ? 0 : undefined} step={tipo === 'number' ? 'any' : undefined}
        value={f[k] as string} onChange={set(k)} style={campo} placeholder={ayuda} /></label>
  )

  return (
    <section aria-label={inicial ? t('pres.editar_partida') : t('pres.nueva_partida')}
      style={{ border: '1px solid var(--surface-4)', borderRadius: 10, padding: 12, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(160px, 100%), 1fr))', gap: 10, alignItems: 'end' }}>
      <label><span style={etiqueta}>{t('pres.sentido')}</span>
        <select aria-label={t('pres.sentido')} value={f.sentido} style={campo}
          onChange={e => setF(v => ({ ...v, sentido: e.target.value as 'gasto' | 'ingreso', tipo: (e.target.value === 'ingreso' ? p.tipos_ingreso : p.tipos)[0] ?? '', modo: 'importe' }))}>
          <option value="gasto">{t('pres.gasto')}</option><option value="ingreso">{t('pres.ingreso')}</option>
        </select></label>
      <label><span style={etiqueta}>{t('pres.tipo')}</span>
        <select aria-label={t('pres.tipo')} value={f.tipo} onChange={set('tipo')} style={campo}>
          {tipos.map(x => <option key={x} value={x}>{t(`pres.tipo_${x}`, x)}</option>)}
        </select></label>
      {entrada({ k: 'descripcion', label: t('pres.descripcion'), tipo: 'text', ancho: true })}
      <label style={{ gridColumn: '1 / -1' }}><span style={etiqueta}>{t('pres.como_se_calcula_la_partida')}</span>
        <div role="radiogroup" aria-label={t('pres.como_se_calcula_la_partida')} style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {modos.map(m => (
            <button key={m} type="button" role="radio" aria-checked={f.modo === m} onClick={() => setF(v => ({ ...v, modo: m }))}
              style={{ padding: '5px 10px', borderRadius: 99, fontSize: 'var(--text-xs)', fontFamily: 'inherit', cursor: 'pointer',
                border: `1px solid ${f.modo === m ? 'var(--accent)' : 'var(--surface-4)'}`, background: f.modo === m ? 'var(--accent-muted)' : 'transparent',
                color: f.modo === m ? 'var(--accent)' : 'var(--text-2)' }}>{t(`pres.modo_${m}`)}</button>
          ))}
        </div>
        <span style={{ ...etiqueta, marginTop: 4 }}>{t(`pres.modo_${f.modo}_ayuda`)}</span>
      </label>
      {f.modo === 'importe' && entrada({ k: 'importe', label: t('pres.importe') })}
      {f.modo === 'conductor' && <>
        {entrada({ k: 'unidades', label: t('pres.unidades') })}
        {entrada({ k: 'precio_unitario', label: f.sentido === 'ingreso' ? t('pres.tarifa') : t('pres.precio_unitario') })}
        <label><span style={etiqueta}>{t('pres.recurrencia')}</span>
          <select aria-label={t('pres.recurrencia')} value={f.recurrencia} onChange={set('recurrencia')} style={campo}>
            {(['unica', 'mensual', 'trimestral', 'anual'] as const).map(r => <option key={r} value={r}>{t(`pres.rec_${r}`)}</option>)}
          </select></label>
      </>}
      {(f.modo === 'persona' || f.modo === 'horas') && (
        <div><span style={etiqueta}>{t('pres.persona')}</span>
          <UserSelect value={f.user_id} onChange={(uid: string) => setF(v => ({ ...v, user_id: uid }))} placeholder={f.modo === 'horas' ? t('pres.persona_opcional') : t('pres.persona')} /></div>
      )}
      {f.modo === 'persona' && entrada({ k: 'dedicacion_pct', label: t('pres.dedicacion') })}
      {f.modo === 'horas' && <>
        {entrada({ k: 'perfil', label: t('pres.perfil'), tipo: 'text', ayuda: t('pres.perfil_ayuda') })}
        {entrada({ k: 'horas', label: t('pres.horas') })}
        {entrada({ k: 'coste_hora', label: t('pres.coste_hora'), ayuda: t('pres.coste_de_la_persona') })}
      </>}
      {f.modo === 'vacante' && <>
        {entrada({ k: 'perfil', label: t('pres.perfil'), tipo: 'text', ayuda: t('pres.perfil_ayuda') })}
        {entrada({ k: 'salario_anual', label: t('pres.salario_anual') })}
        {entrada({ k: 'pais', label: t('pres.pais'), tipo: 'text', ayuda: 'ES' })}
        {entrada({ k: 'fecha_alta', label: t('pres.fecha_alta'), tipo: 'date' })}
        {entrada({ k: 'dedicacion_pct', label: t('pres.dedicacion') })}
      </>}
      {f.sentido === 'gasto' && (
        <label><span style={etiqueta}>{t('pres.naturaleza')}</span>
          <select aria-label={t('pres.naturaleza')} value={f.naturaleza} onChange={set('naturaleza')} style={campo}>
            <option value="opex">OPEX</option><option value="capex">CAPEX</option>
          </select></label>
      )}
      {f.sentido === 'gasto' && f.naturaleza === 'capex' && entrada({ k: 'vida_meses', label: t('pres.vida_meses') })}
      <label><span style={etiqueta}>{t('pres.desde_mes')}</span>
        <input aria-label={t('pres.desde_mes')} type="month" min={desde} max={hasta} value={f.mes_desde} onChange={set('mes_desde')} style={campo} /></label>
      <label><span style={etiqueta}>{t('pres.hasta_mes')}</span>
        <input aria-label={t('pres.hasta_mes')} type="month" min={desde} max={hasta} value={f.mes_hasta} onChange={set('mes_hasta')} style={campo} /></label>
      <label style={{ gridColumn: '1 / -1' }}><span style={etiqueta}>{t('pres.justificacion')}</span>
        <textarea aria-label={t('pres.justificacion')} value={f.justificacion} onChange={set('justificacion')} rows={2} style={{ ...campo, resize: 'vertical' }} placeholder={t('pres.justificacion_ayuda')} /></label>
      <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        {onCancelar && <Button variant="secondary" onClick={onCancelar}>{t('pres.cancelar')}</Button>}
        <Button loading={guardando} disabled={!listo} onClick={guardar}>{inicial ? t('pres.guardar') : t('pres.anadir')}</Button>
      </div>
    </section>
  )
}
