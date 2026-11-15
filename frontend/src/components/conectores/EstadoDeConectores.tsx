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
import { POLL_DEFAULT_MS } from '../../constants/timings'
import './EstadoDeConectores.css'

const num: CSSProperties = { fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--text-1)', fontFamily: 'var(--font-mono)' }

export default function EstadoDeConectores() {
  const t = useAppT()
  const estado = useQuery({ queryKey: ['conectores', 'estado'], queryFn: conectoresApi.estado, refetchInterval: POLL_DEFAULT_MS })
  if (estado.isLoading) return <Spinner size={18} />
  if (estado.isError) return <div role="alert" className="esdeco-txt-1">{mensajeDeConector(estado.error, t('conectores.error'))}</div>
  const d = estado.data!
  return (
    <section aria-label={t('conectores.titulo')} className="u-mb-20">
      <div className="esdeco-row-1">
        <h3 className="esdeco-row-2"><PlugZap size={16} />{t('conectores.titulo')}</h3>
        <span className="esdeco-sub">{t('conectores.ventana', { horas: d.ventana_horas })}</span>
      </div>
      <div className="esdeco-grid-1">
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
    <div className="esdeco-tarjeta">
      <div className="u-row-center-8">
        <span className="esdeco-box-5" aria-hidden style={{ background: color }} />
        <strong className="u-text1">{p.producto}</strong>
        <span className="esdeco-sub">{p.configurado ? t('conectores.estado_configurado') : t('conectores.sin_configurar')}</span>
        <Button size="xs" variant="secondary" style={{ marginLeft: 'auto' }} loading={probar.isPending} disabled={!p.configurado}
          onClick={() => probar.mutate()}>{t('conectores.probar')}</Button>
      </div>
      <div className="esdeco-grid-2">
        <div><div className="esdeco-sub">{t('conectores.llamadas')}</div><div className="esdeco-num">{p.llamadas}</div></div>
        <div><div className="esdeco-sub">{t('conectores.fallos')}</div><div className="esdeco-num2" style={{ color: p.fallos ? 'var(--danger)' : num.color }}>{p.fallos}</div></div>
        <div><div className="esdeco-sub">p50</div><div className="esdeco-num">{p.p50_ms == null ? '—' : `${p.p50_ms} ms`}</div></div>
        <div><div className="esdeco-sub">p95</div><div className="esdeco-num">{p.p95_ms == null ? '—' : `${p.p95_ms} ms`}</div></div>
      </div>
      {probar.data && (
        <div className="esdeco-stack-1">
          {[{ k: 'aplicacion', r: probar.data.aplicacion }, { k: 'empresa', r: probar.data.empresa }].filter(x => x.r).map(({ k, r }) => (
            <div className="esdeco-row-3" key={k} style={{ color: r!.ok ? 'var(--success)' : 'var(--danger)' }}>
              {r!.ok ? <CheckCircle2 size={14} style={{ marginTop: 2 }} /> : <XCircle size={14} style={{ marginTop: 2 }} />}
              <span className="u-text2"><strong>{t(`conectores.prueba_${k}`)}:</strong> {r!.detail}</span>
            </div>
          ))}
        </div>
      )}
      {probar.isError && <div role="alert" className="esdeco-txt-1">{mensajeDeConector(probar.error, t('conectores.error'))}</div>}
      {p.ultimo_error && (
        <div className="esdeco-box-1">
          <strong>{t('conectores.ultimo_error')}</strong> · {fmtDate(p.ultimo_error.cuando)} · {p.ultimo_error.operacion}
          {p.ultimo_error.estado_http ? ` · HTTP ${p.ultimo_error.estado_http}` : ''}
          <div className="esdeco-sp-1">{p.ultimo_error.error}</div>
        </div>
      )}
      {p.operaciones.length > 0 && (
        <div>
          <button type="button" onClick={() => setAbierto(v => !v)} className="esdeco-box-2">
            {abierto ? t('conectores.ocultar_operaciones') : t('conectores.ver_operaciones', { n: p.operaciones.length })}
          </button>
          {abierto && (
            <table className="esdeco-box-3">
              <thead><tr className="esdeco-txt-2">
                <th className="esdeco-sp-2">{t('conectores.operacion')}</th><th className="esdeco-sp-2">{t('conectores.llamadas')}</th>
                <th className="esdeco-sp-2">{t('conectores.fallos')}</th><th className="esdeco-sp-2">p50</th><th className="esdeco-sp-2">p95</th>
              </tr></thead>
              <tbody>{p.operaciones.map(o => (
                <tr key={o.operacion} className="esdeco-box-4">
                  <td className="esdeco-sp-2">{o.operacion}</td><td className="esdeco-sp-2">{o.llamadas}</td>
                  <td className="esdeco-sp-3" style={{ color: o.fallos ? 'var(--danger)' : undefined }}>{o.fallos}</td>
                  <td className="esdeco-sp-2">{o.p50_ms ?? '—'}</td><td className="esdeco-sp-2">{o.p95_ms ?? '—'}</td>
                </tr>))}</tbody>
            </table>
          )}
        </div>
      )}
      {p.ultima_llamada && <div className="esdeco-sub">{t('conectores.ultima_llamada')}: {fmtDate(p.ultima_llamada)}</div>}
    </div>
  )
}
