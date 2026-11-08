/**
 * Estado de los conectores con contecmind y contecintelligence (revisión 2026-11).
 *
 * Sale del registro de llamadas reales (`conector_llamadas`), no de una sonda
 * aparte: cuántas, cuántas fallaron, latencias p50/p95 por operación y el
 * último error. «Probar» comprueba por separado lo que puede fallar: que el
 * producto esté vivo y listo, que acepte la credencial de la aplicación y que
 * ESTA empresa esté dada de alta allí.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { CheckCircle2, PlugZap, XCircle } from 'lucide-react'
import { conectoresApi, mensajeDeConector } from '../../services/api'
import type { EstadoProducto } from '../../services/api'
import { Button, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { fmtDate } from '../../utils/helpers'

const tarjeta: CSSProperties = { border: '1px solid var(--surface-4)', borderRadius: 10, padding: 14, background: 'var(--surface-1)', display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }
const sub: CSSProperties = { fontSize: 'var(--text-xs)', color: 'var(--text-3)' }
const num: CSSProperties = { fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--text-1)', fontFamily: 'var(--font-mono)' }

export default function EstadoDeConectores() {
  const t = useAppT()
  const estado = useQuery({ queryKey: ['conectores', 'estado'], queryFn: conectoresApi.estado, refetchInterval: 60_000 })
  if (estado.isLoading) return <Spinner size={18} />
  if (estado.isError) return <div role="alert" style={{ color: 'var(--danger)', fontSize: 'var(--text-sm)' }}>{mensajeDeConector(estado.error, t('conectores.error'))}</div>
  const d = estado.data!
  return (
    <section aria-label={t('conectores.titulo')} style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 10 }}>
        <h3 style={{ margin: 0, fontSize: 'var(--text-base)', color: 'var(--text-1)', display: 'flex', alignItems: 'center', gap: 6 }}><PlugZap size={16} />{t('conectores.titulo')}</h3>
        <span style={sub}>{t('conectores.ventana', { horas: d.ventana_horas })}</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 12 }}>
        {d.productos.map(p => <Producto key={p.producto} p={p} />)}
      </div>
    </section>
  )
}

function Producto({ p }: { p: EstadoProducto }) {
  const t = useAppT()
  const [abierto, setAbierto] = useState(false)
  const probar = useMutation({ mutationFn: () => conectoresApi.probar(p.producto) })
  const color = !p.configurado ? 'var(--text-3)' : p.fallos > 0 ? 'var(--warning)' : 'var(--success)'
  return (
    <div style={tarjeta}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span aria-hidden style={{ width: 9, height: 9, borderRadius: 99, background: color }} />
        <strong style={{ color: 'var(--text-1)' }}>{p.producto}</strong>
        <span style={sub}>{p.configurado ? t('conectores.estado_configurado') : t('conectores.sin_configurar')}</span>
        <Button size="xs" variant="secondary" style={{ marginLeft: 'auto' }} loading={probar.isPending} disabled={!p.configurado}
          onClick={() => probar.mutate()}>{t('conectores.probar')}</Button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
        <div><div style={sub}>{t('conectores.llamadas')}</div><div style={num}>{p.llamadas}</div></div>
        <div><div style={sub}>{t('conectores.fallos')}</div><div style={{ ...num, color: p.fallos ? 'var(--danger)' : num.color }}>{p.fallos}</div></div>
        <div><div style={sub}>p50</div><div style={num}>{p.p50_ms == null ? '—' : `${p.p50_ms} ms`}</div></div>
        <div><div style={sub}>p95</div><div style={num}>{p.p95_ms == null ? '—' : `${p.p95_ms} ms`}</div></div>
      </div>
      {probar.data && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 'var(--text-sm)' }}>
          {[{ k: 'aplicacion', r: probar.data.aplicacion }, { k: 'empresa', r: probar.data.empresa }].filter(x => x.r).map(({ k, r }) => (
            <div key={k} style={{ display: 'flex', gap: 6, alignItems: 'flex-start', color: r!.ok ? 'var(--success)' : 'var(--danger)' }}>
              {r!.ok ? <CheckCircle2 size={14} style={{ marginTop: 2 }} /> : <XCircle size={14} style={{ marginTop: 2 }} />}
              <span style={{ color: 'var(--text-2)' }}><strong>{t(`conectores.prueba_${k}`)}:</strong> {r!.detail}</span>
            </div>
          ))}
        </div>
      )}
      {probar.isError && <div role="alert" style={{ fontSize: 'var(--text-sm)', color: 'var(--danger)' }}>{mensajeDeConector(probar.error, t('conectores.error'))}</div>}
      {p.ultimo_error && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)', border: '1px solid var(--surface-3)', borderRadius: 6, padding: '6px 8px' }}>
          <strong>{t('conectores.ultimo_error')}</strong> · {fmtDate(p.ultimo_error.cuando)} · {p.ultimo_error.operacion}
          {p.ultimo_error.estado_http ? ` · HTTP ${p.ultimo_error.estado_http}` : ''}
          <div style={{ marginTop: 2 }}>{p.ultimo_error.error}</div>
        </div>
      )}
      {p.operaciones.length > 0 && (
        <div>
          <button type="button" onClick={() => setAbierto(v => !v)} style={{ background: 'none', border: 'none', padding: 0, color: 'var(--accent)', cursor: 'pointer', fontSize: 'var(--text-xs)' }}>
            {abierto ? t('conectores.ocultar_operaciones') : t('conectores.ver_operaciones', { n: p.operaciones.length })}
          </button>
          {abierto && (
            <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 6, fontSize: 'var(--text-xs)' }}>
              <thead><tr style={{ color: 'var(--text-3)', textAlign: 'left' }}>
                <th style={{ padding: 4 }}>{t('conectores.operacion')}</th><th style={{ padding: 4 }}>{t('conectores.llamadas')}</th>
                <th style={{ padding: 4 }}>{t('conectores.fallos')}</th><th style={{ padding: 4 }}>p50</th><th style={{ padding: 4 }}>p95</th>
              </tr></thead>
              <tbody>{p.operaciones.map(o => (
                <tr key={o.operacion} style={{ borderTop: '1px solid var(--surface-3)', color: 'var(--text-2)' }}>
                  <td style={{ padding: 4 }}>{o.operacion}</td><td style={{ padding: 4 }}>{o.llamadas}</td>
                  <td style={{ padding: 4, color: o.fallos ? 'var(--danger)' : undefined }}>{o.fallos}</td>
                  <td style={{ padding: 4 }}>{o.p50_ms ?? '—'}</td><td style={{ padding: 4 }}>{o.p95_ms ?? '—'}</td>
                </tr>))}</tbody>
            </table>
          )}
        </div>
      )}
      {p.ultima_llamada && <div style={sub}>{t('conectores.ultima_llamada')}: {fmtDate(p.ultima_llamada)}</div>}
    </div>
  )
}
