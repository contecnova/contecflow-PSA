/**
 * Ficha de un presupuesto (revisión 2026-11).
 *
 * Partidas (personal por persona o perfil × horas × coste/hora, y el resto por
 * importe, repartidas por meses), seguimiento (plan contra real calculado, por
 * mes y por tipo, con la previsión al cierre), versiones (reprevisiones) y
 * aprobación. Un presupuesto aprobado no se toca: se hace una versión nueva.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Plus, Trash2 } from 'lucide-react'
import { presupuestosApi, projectsApi } from '../../services/api'
import type { FichaPresupuesto } from '../../services/api'
import { Button, Modal, Spinner, Tabs, UserSelect } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, localeActivo } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'

const campo: CSSProperties = { width: '100%', boxSizing: 'border-box', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 10px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }
const th: CSSProperties = { textAlign: 'left', padding: '6px 8px', fontSize: 'var(--text-xs)', color: 'var(--text-3)', fontWeight: 600, borderBottom: '1px solid var(--surface-3)' }
const td: CSSProperties = { padding: '6px 8px', fontSize: 'var(--text-sm)', borderBottom: '1px solid var(--surface-2)' }
const num: CSSProperties = { ...td, textAlign: 'right', fontFamily: 'var(--font-mono)' }

export function colorDeEstado(e: string) {
  return e === 'aprobado' ? 'var(--success)' : e === 'enviado' ? 'var(--warning)' : e === 'rechazado' ? 'var(--danger)' : 'var(--text-3)'
}

export default function FichaDePresupuesto({ id, onClose, onAbrir }: { id: string; onClose: () => void; onAbrir: (id: string) => void }) {
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
  const dinero = (n: number | undefined) => (n ?? 0).toLocaleString(localeActivo(), { style: 'currency', currency: p?.currency || 'EUR', maximumFractionDigits: 0 })
  const accion = async (clave: string, f: () => Promise<FichaPresupuesto>) => {
    setOcupado(clave)
    try {
      const d = await f()
      qc.setQueryData(['presupuesto', d.id], d)
      qc.invalidateQueries({ queryKey: ['presupuestos'] })
      if (d.id !== id) onAbrir(d.id)
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setOcupado(null) }
  }

  return (
    <Modal open onClose={onClose} size="xl" title={p ? `${p.name} · v${p.version}` : '…'}
      subtitle={p ? `${t(`pres.ambito_${p.ambito}`)}${p.project_name ? ` · ${p.project_name}` : p.department ? ` · ${p.department}` : p.area ? ` · ${p.area}` : ''} · ${p.periodo_desde.slice(0, 7)} → ${p.periodo_hasta.slice(0, 7)}` : undefined}>
      {q.isLoading ? <Spinner /> : q.isError ? <div role="alert" style={{ color: 'var(--danger)' }}>{extractErr(q.error, GENERIC_ERROR_FALLBACK)}</div> : p && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ color: colorDeEstado(p.estado), border: '1px solid currentColor', borderRadius: 99, padding: '1px 10px', fontSize: 'var(--text-xs)', fontWeight: 600 }}>{t(`pres.estado_${p.estado}`)}</span>
            <span style={{ fontSize: 'var(--text-sm)' }}>{t('pres.plan')}: <strong>{dinero(p.total_plan)}</strong></span>
            <span style={{ fontSize: 'var(--text-sm)' }}>{t('pres.real')}: <strong>{dinero(p.informe.total_real)}</strong></span>
            <span style={{ fontSize: 'var(--text-sm)' }}>{t('pres.prevision')}: <strong>{dinero(p.informe.prevision_cierre)}</strong></span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
              {p.puedo_editar && <Button size="sm" loading={ocupado === 'enviar'} onClick={() => accion('enviar', () => presupuestosApi.enviar(p.id))}>{t('pres.enviar')}</Button>}
              {p.estado !== 'borrador' && p.estado !== 'enviado' && <Button size="sm" variant="secondary" loading={ocupado === 'version'} onClick={() => accion('version', () => presupuestosApi.nuevaVersion(p.id))}>{t('pres.nueva_version')}</Button>}
            </span>
          </div>
          {p.motivo_rechazo && <div role="alert" style={{ fontSize: 'var(--text-sm)', color: 'var(--danger)' }}>{t('pres.rechazado_por')}: {p.motivo_rechazo}</div>}
          {p.puedo_aprobar && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 10 }}>
              <input aria-label={t('pres.motivo')} placeholder={t('pres.motivo_ayuda')} value={motivo} onChange={e => setMotivo(e.target.value)} style={{ ...campo, flex: 1 }} />
              <Button size="sm" variant="danger" disabled={!motivo.trim()} loading={ocupado === 'rechazar'} onClick={() => accion('rechazar', () => presupuestosApi.decidir(p.id, false, motivo))}>{t('pres.rechazar')}</Button>
              <Button size="sm" loading={ocupado === 'aprobar'} onClick={() => accion('aprobar', () => presupuestosApi.decidir(p.id, true))}>{t('pres.aprobar')}</Button>
            </div>
          )}
          {p.ambito === 'proyecto_previsto' && !p.project_id && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 'var(--text-sm)' }}>
              <span style={{ color: 'var(--text-2)' }}>{t('pres.previsto_sin_real')}</span>
              <select aria-label={t('pres.vincular')} value={vincular} onChange={e => setVincular(e.target.value)} style={{ ...campo, width: 260 }}>
                <option value="">{t('pres.elige_proyecto')}</option>
                {(proyectos.data ?? []).map(pr => <option key={pr.id} value={pr.id}>{pr.code ? `${pr.code} — ` : ''}{pr.name}</option>)}
              </select>
              <Button size="sm" variant="secondary" disabled={!vincular} loading={ocupado === 'vincular'} onClick={() => accion('vincular', () => presupuestosApi.vincular(p.id, vincular))}>{t('pres.vincular')}</Button>
            </div>
          )}
          <Tabs active={tab} onChange={setTab} items={[
            { id: 'partidas', label: t('pres.tab_partidas') }, { id: 'seguimiento', label: t('pres.tab_seguimiento') },
            { id: 'versiones', label: `${t('pres.tab_versiones')} · ${p.versiones.length}` },
          ]} />
          {tab === 'partidas' && <Partidas p={p} dinero={dinero} onCambio={d => qc.setQueryData(['presupuesto', d.id], d)} />}
          {tab === 'seguimiento' && <Seguimiento p={p} dinero={dinero} />}
          {tab === 'versiones' && (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead><tr><th style={th}>{t('pres.version')}</th><th style={th}>{t('pres.estado')}</th><th style={{ ...th, textAlign: 'right' }}>{t('pres.plan')}</th></tr></thead>
              <tbody>{p.versiones.map(v => (
                <tr key={v.id} onClick={() => v.id !== p.id && onAbrir(v.id)} style={{ cursor: v.id !== p.id ? 'pointer' : 'default', background: v.id === p.id ? 'var(--accent-muted)' : undefined }}>
                  <td style={td}>v{v.version}</td><td style={{ ...td, color: colorDeEstado(v.estado) }}>{t(`pres.estado_${v.estado}`)}</td><td style={num}>{dinero(v.total_plan)}</td>
                </tr>))}</tbody>
            </table>
          )}
        </div>
      )}
    </Modal>
  )
}

function Partidas({ p, dinero, onCambio }: { p: FichaPresupuesto; dinero: (n?: number) => string; onCambio: (d: FichaPresupuesto) => void }) {
  const t = useAppT()
  const toast = useToast()
  const vacia = { tipo: p.tipos[0] ?? '', descripcion: '', user_id: '', perfil: '', horas: '', coste_hora: '', importe: '' }
  const [n, setN] = useState(vacia)
  const [guardando, setGuardando] = useState(false)
  const esPersonal = n.tipo === 'personal'
  const previsto = esPersonal && n.horas && n.coste_hora ? Number(n.horas) * Number(n.coste_hora) : null
  const anadir = async () => {
    setGuardando(true)
    try {
      const cuerpo: Record<string, unknown> = { tipo: n.tipo, descripcion: n.descripcion }
      if (esPersonal && n.horas) {
        cuerpo.horas = Number(n.horas)
        if (n.user_id) cuerpo.user_id = n.user_id
        if (n.perfil) cuerpo.perfil = n.perfil
        if (n.coste_hora) cuerpo.coste_hora = Number(n.coste_hora)
      } else cuerpo.importe = Number(n.importe)
      onCambio(await presupuestosApi.crearPartida(p.id, cuerpo)); setN(vacia)
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setGuardando(false) }
  }
  const quitar = async (lid: string) => { try { onCambio(await presupuestosApi.borrarPartida(p.id, lid)) } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } }
  const set = (k: keyof typeof vacia) => (e: { target: { value: string } }) => setN(v => ({ ...v, [k]: e.target.value }))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {p.lineas.length === 0 ? <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)' }}>{t('pres.sin_partidas')}</div> : (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead><tr>
            <th style={th}>{t('pres.tipo')}</th><th style={th}>{t('pres.descripcion')}</th><th style={th}>{t('pres.persona_o_perfil')}</th>
            <th style={{ ...th, textAlign: 'right' }}>{t('pres.horas')}</th><th style={{ ...th, textAlign: 'right' }}>{t('pres.coste_hora')}</th>
            <th style={{ ...th, textAlign: 'right' }}>{t('pres.importe')}</th><th style={th}>{t('pres.meses')}</th><th style={th} aria-label={t('pres.quitar')} />
          </tr></thead>
          <tbody>{p.lineas.map(l => (
            <tr key={l.id}>
              <td style={td}>{t(`pres.tipo_${l.tipo}`, l.tipo)}</td><td style={td}>{l.descripcion}</td>
              <td style={td}>{l.user_name || l.perfil || '—'}</td>
              <td style={num}>{l.horas ?? '—'}</td><td style={num}>{l.coste_hora != null ? dinero(l.coste_hora) : '—'}</td>
              <td style={num}>{dinero(l.importe)}</td>
              <td style={{ ...td, fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{Object.keys(l.meses).length}</td>
              <td style={td}>{p.puedo_editar && <Button size="xs" variant="ghost" title={t('pres.quitar')} icon={<Trash2 size={12} />} onClick={() => quitar(l.id)}>{''}</Button>}</td>
            </tr>))}</tbody>
        </table>
      )}
      {p.puedo_editar && (
        <section aria-label={t('pres.nueva_partida')} style={{ border: '1px solid var(--surface-4)', borderRadius: 10, padding: 12, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8, alignItems: 'end' }}>
          <label><span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('pres.tipo')}</span>
            <select aria-label={t('pres.tipo')} value={n.tipo} onChange={set('tipo')} style={campo}>{p.tipos.map(x => <option key={x} value={x}>{t(`pres.tipo_${x}`, x)}</option>)}</select></label>
          <label style={{ gridColumn: 'span 2' }}><span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('pres.descripcion')}</span>
            <input aria-label={t('pres.descripcion')} value={n.descripcion} onChange={set('descripcion')} style={campo} /></label>
          {esPersonal ? (
            <>
              <div><span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('pres.persona')}</span>
                <UserSelect value={n.user_id} onChange={(uid: string) => setN(v => ({ ...v, user_id: uid }))} placeholder={t('pres.persona_opcional')} /></div>
              <label><span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('pres.perfil')}</span>
                <input aria-label={t('pres.perfil')} value={n.perfil} onChange={set('perfil')} style={campo} placeholder={t('pres.perfil_ayuda')} /></label>
              <label><span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('pres.horas')}</span>
                <input aria-label={t('pres.horas')} type="number" min={0} value={n.horas} onChange={set('horas')} style={campo} /></label>
              <label><span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('pres.coste_hora')}</span>
                <input aria-label={t('pres.coste_hora')} type="number" min={0} step="0.01" value={n.coste_hora} onChange={set('coste_hora')} style={campo} placeholder={t('pres.coste_de_la_persona')} /></label>
            </>
          ) : (
            <label><span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('pres.importe')}</span>
              <input aria-label={t('pres.importe')} type="number" min={0} step="0.01" value={n.importe} onChange={set('importe')} style={campo} /></label>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {previsto != null && <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>= {dinero(previsto)}</span>}
            <Button icon={<Plus size={13} />} loading={guardando}
              disabled={!n.descripcion.trim() || (esPersonal ? !n.horas || (!n.coste_hora && !n.user_id) : n.importe === '')} onClick={anadir}>{t('pres.anadir')}</Button>
          </div>
          <div style={{ gridColumn: '1 / -1', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('pres.reparto_ayuda')}</div>
        </section>
      )}
    </div>
  )
}

function Seguimiento({ p, dinero }: { p: FichaPresupuesto; dinero: (n?: number) => string }) {
  const t = useAppT()
  const inf = p.informe
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {inf.sin_real && <div role="status" style={{ fontSize: 'var(--text-sm)', color: 'var(--warning)' }}>{t('pres.previsto_sin_real')}</div>}
      <div style={{ height: 240 }} role="img" aria-label={t('pres.plan_contra_real')}>
        <ResponsiveContainer>
          <BarChart data={inf.meses}>
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
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 14 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead><tr><th style={th}>{t('pres.mes')}</th><th style={{ ...th, textAlign: 'right' }}>{t('pres.plan')}</th><th style={{ ...th, textAlign: 'right' }}>{t('pres.real')}</th><th style={{ ...th, textAlign: 'right' }}>{t('pres.desviacion')}</th></tr></thead>
          <tbody>{inf.meses.map(m => (
            <tr key={m.mes}>
              <td style={td}>{m.mes}{m.en_curso ? ` · ${t('pres.en_curso')}` : ''}</td><td style={num}>{dinero(m.plan)}</td><td style={num}>{dinero(m.real)}</td>
              <td style={{ ...num, color: m.desviacion > 0 ? 'var(--danger)' : m.desviacion < 0 ? 'var(--success)' : undefined }}>{m.cerrado || m.en_curso ? dinero(m.desviacion) : '—'}</td>
            </tr>))}</tbody>
        </table>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead><tr><th style={th}>{t('pres.tipo')}</th><th style={{ ...th, textAlign: 'right' }}>{t('pres.plan')}</th><th style={{ ...th, textAlign: 'right' }}>{t('pres.real')}</th><th style={{ ...th, textAlign: 'right' }}>%</th></tr></thead>
          <tbody>{inf.por_tipo.map(x => (
            <tr key={x.tipo}>
              <td style={td}>{t(`pres.tipo_${x.tipo}`, x.tipo)}</td><td style={num}>{dinero(x.plan)}</td><td style={num}>{dinero(x.real)}</td>
              <td style={{ ...num, color: (x.desviacion_pct ?? 0) > 0 ? 'var(--danger)' : undefined }}>{x.desviacion_pct == null ? '—' : `${x.desviacion_pct.toLocaleString(localeActivo())} %`}</td>
            </tr>))}</tbody>
        </table>
      </div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{t('pres.como_se_calcula')}</div>
    </div>
  )
}
