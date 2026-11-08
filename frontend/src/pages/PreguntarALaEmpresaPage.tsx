/**
 * Preguntar a la empresa — analítica conversacional con contecintelligence (revisión 2026-11).
 *
 * «Pregunta a los datos» (Data Explorer) contesta sobre los datos de contecflow.
 * Esta pantalla pregunta a TODAS las fuentes que la empresa tiene conectadas en
 * contecintelligence (ERP, CRM, contecflow…), con:
 *  - el progreso en vivo (SSE reenviado por contecflow, sin credenciales en el navegador);
 *  - la respuesta con su tabla o gráfico, la consulta usada y el recibo firmado verificable;
 *  - las métricas certificadas: consultarlas y explicar por qué cambiaron entre dos periodos.
 * Lo que cada persona ve lo decide contecintelligence con su rol y su filtro de filas.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { BadgeCheck, Database, MessageSquareText, Send, ShieldAlert, Sigma } from 'lucide-react'
import { conectoresApi, mensajeDeConector } from '../services/api'
import type { Metrica, RespuestaCI } from '../services/api'
import { Button, EmptyState, Page, Spinner, Tabs } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { useAuth } from '../context/AuthContext'
import { localeActivo } from '../utils/helpers'

type Fila = Record<string, unknown>
type Grafico = { type?: string; title?: string; data?: Fila[]; xAxis?: { key: string; label: string } | null
  series?: { key: string; label: string }[]; sql?: string; text?: string; citations?: unknown[] }

const caja: CSSProperties = { border: '1px solid var(--surface-4)', borderRadius: 12, background: 'var(--surface-1)', padding: 16 }
const campo: CSSProperties = { background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }
const sub: CSSProperties = { fontSize: 'var(--text-xs)', color: 'var(--text-3)' }

function leerCookie(n: string) {
  return document.cookie.split('; ').find(c => c.startsWith(n + '='))?.split('=')[1]
}
const valorTexto = (v: unknown) => typeof v === 'number' ? v.toLocaleString(localeActivo()) : v == null ? '—' : String(v)

export default function PreguntarALaEmpresaPage() {
  const t = useAppT()
  const { user } = useAuth() as { user?: { role?: string } }
  const [params] = useSearchParams()
  const [tab, setTab] = useState('preguntar')
  const disp = useQuery({ queryKey: ['conectores', 'ci-disponible'], queryFn: conectoresApi.ciDisponible })

  if (disp.isLoading) return <Page title={t('ci.titulo')}><Spinner /></Page>
  if (!disp.data?.configurado) {
    return (
      <Page title={t('ci.titulo')} subtitle={t('ci.subtitulo')}>
        <EmptyState svgIcon={<Database size={28} />} title={t('ci.no_configurado')}
          description={user?.role === 'admin' ? t('ci.no_configurado_admin') : t('ci.no_configurado_usuario')} />
      </Page>
    )
  }
  return (
    <Page title={t('ci.titulo')} subtitle={t('ci.subtitulo')}>
      <Tabs active={tab} onChange={setTab} items={[
        { id: 'preguntar', label: t('ci.tab_preguntar'), icon: <MessageSquareText size={14} /> },
        { id: 'metricas', label: t('ci.tab_metricas'), icon: <Sigma size={14} /> },
      ]} />
      <div style={{ marginTop: 16 }}>
        {tab === 'preguntar'
          ? <Preguntar fuentePorDefecto={disp.data.fuente_por_defecto} preguntaInicial={params.get('q') || ''} />
          : <Metricas analista={disp.data.analista} />}
      </div>
    </Page>
  )
}

// ── Preguntar ────────────────────────────────────────────────────────────────

function Preguntar({ fuentePorDefecto, preguntaInicial }: { fuentePorDefecto: string | null; preguntaInicial: string }) {
  const t = useAppT()
  const fuentes = useQuery({ queryKey: ['conectores', 'ci-fuentes'], queryFn: conectoresApi.fuentes, retry: false })
  const [fuente, setFuente] = useState<string>(fuentePorDefecto || '')
  const [pregunta, setPregunta] = useState(preguntaInicial)
  const [progreso, setProgreso] = useState<string[]>([])
  const [texto, setTexto] = useState('')
  const [respuesta, setRespuesta] = useState<RespuestaCI | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pensando, setPensando] = useState(false)
  const [conversacion, setConversacion] = useState<string | null>(null)
  const cancelar = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!fuente && fuentes.data?.items?.length) setFuente(fuentes.data.items[0].id)
  }, [fuente, fuentes.data])
  useEffect(() => () => cancelar.current?.abort(), [])

  const enviar = async () => {
    const q = pregunta.trim()
    if (!q || pensando) return
    cancelar.current?.abort()
    const ctrl = new AbortController()
    cancelar.current = ctrl
    setPensando(true); setProgreso([]); setTexto(''); setRespuesta(null); setError(null)
    try {
      const resp = await fetch(`${(import.meta.env.VITE_API_URL as string | undefined) || '/api/v1'}/conectores/contecintelligence/preguntar/directo`, {
        method: 'POST', credentials: 'include', signal: ctrl.signal,
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': leerCookie('csrf_token') || '' },
        body: JSON.stringify({ question: q, source_id: fuente || undefined, conversation_id: conversacion }),
      })
      if (!resp.ok || !resp.body) {
        const err = await resp.json().catch(() => ({ detail: '' }))
        setError(err.detail || t('ci.error')); return
      }
      const lector = resp.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
      for (;;) {
        const { done, value } = await lector.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const lineas = buf.split('\n')
        buf = lineas.pop() ?? ''
        for (const l of lineas) {
          if (!l.startsWith('data: ')) continue
          let ev: Record<string, unknown>
          try { ev = JSON.parse(l.slice(6)) } catch { continue }
          const tipo = String(ev.event ?? ev.type ?? '')
          if (tipo === 'token') setTexto(x => x + String(ev.text ?? ''))
          else if (tipo === 'result') {
            const r = { text: String(ev.text ?? ''), payload: ev.payload, receipt_id: (ev.receipt_id as string) ?? null,
              receipt_signed: !!ev.receipt_signed, conversation_id: (ev.conversation_id as string) ?? null, source_id: fuente }
            setRespuesta(r); setConversacion(r.conversation_id ?? null)
          } else if (tipo === 'error') setError(String(ev.message || t('ci.error')))
          else if (tipo && tipo !== 'done') setProgreso(p => [...p, String(ev.label ?? ev.message ?? ev.node ?? tipo)])
        }
      }
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setError(t('ci.error'))
    } finally {
      setPensando(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <form style={{ ...caja, display: 'flex', flexDirection: 'column', gap: 10 }} onSubmit={e => { e.preventDefault(); enviar() }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <label style={sub} htmlFor="ci-fuente">{t('ci.fuente')}</label>
          {fuentes.isError
            ? <span role="alert" style={{ ...sub, color: 'var(--danger)' }}>{mensajeDeConector(fuentes.error, t('ci.error'))}</span>
            : (
              <select id="ci-fuente" value={fuente} onChange={e => { setFuente(e.target.value); setConversacion(null) }} style={campo}>
                {(fuentes.data?.items ?? []).map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
              </select>
            )}
          {conversacion && (
            <Button size="xs" variant="ghost" onClick={() => { setConversacion(null); setRespuesta(null); setTexto('') }}>{t('ci.nueva_conversacion')}</Button>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <textarea aria-label={t('ci.pregunta')} rows={2} value={pregunta} onChange={e => setPregunta(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar() } }}
            placeholder={t('ci.pregunta_placeholder')} style={{ ...campo, flex: 1, resize: 'vertical' }} />
          <Button type="submit" icon={<Send size={14} />} loading={pensando} disabled={!pregunta.trim()}>{t('ci.preguntar')}</Button>
        </div>
      </form>

      {(pensando || progreso.length > 0) && !respuesta && (
        <div style={caja} aria-live="polite">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>{pensando && <Spinner size={16} />}<strong style={{ fontSize: 'var(--text-sm)' }}>{t('ci.calculando')}</strong></div>
          <ol style={{ margin: '8px 0 0', paddingLeft: 18, ...sub }}>{progreso.slice(-8).map((p, i) => <li key={i}>{p}</li>)}</ol>
          {texto && <div style={{ marginTop: 8, whiteSpace: 'pre-wrap', fontSize: 'var(--text-sm)' }}>{texto}</div>}
        </div>
      )}
      {error && <div role="alert" style={{ ...caja, borderColor: 'var(--danger)', color: 'var(--danger)', display: 'flex', gap: 8 }}><ShieldAlert size={16} />{error}</div>}
      {respuesta && <Respuesta r={respuesta} />}
    </div>
  )
}

function Respuesta({ r }: { r: RespuestaCI }) {
  const t = useAppT()
  const [verSql, setVerSql] = useState(false)
  const verificar = useMutation({ mutationFn: () => conectoresApi.verificarRecibo(r.receipt_id!) })
  const g = (r.payload ?? {}) as Grafico
  const grafico = (g.type === 'hybrid' ? (g as unknown as { chart: Grafico }).chart : g) as Grafico
  return (
    <div style={{ ...caja, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 'var(--text-base)', color: 'var(--text-1)', whiteSpace: 'pre-wrap', lineHeight: 1.55 }}>{r.text || grafico?.title}</div>
      {grafico?.data && grafico.data.length > 0 && <Datos g={grafico} />}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', borderTop: '1px solid var(--surface-3)', paddingTop: 10 }}>
        {r.receipt_id && (
          <>
            <span style={sub}>{t('ci.recibo')}: <code>{r.receipt_id}</code> · {r.receipt_signed ? t('ci.recibo_firmado') : t('ci.sin_firma')}</span>
            <Button size="xs" variant="secondary" icon={<BadgeCheck size={13} />} loading={verificar.isPending} onClick={() => verificar.mutate()}>{t('ci.verificar')}</Button>
          </>
        )}
        {verificar.data && (
          <span style={{ fontSize: 'var(--text-xs)', color: verificar.data.valid ? 'var(--success)' : 'var(--danger)' }}>
            {verificar.data.valid ? t('ci.recibo_valido') : t('ci.recibo_no_valido')}{verificar.data.reason ? ` — ${verificar.data.reason}` : ''}
          </span>
        )}
        {verificar.isError && <span role="alert" style={{ fontSize: 'var(--text-xs)', color: 'var(--danger)' }}>{mensajeDeConector(verificar.error, t('ci.error'))}</span>}
        {grafico?.sql && <Button size="xs" variant="ghost" onClick={() => setVerSql(v => !v)}>{verSql ? t('ci.ocultar_consulta') : t('ci.ver_consulta')}</Button>}
      </div>
      {verSql && grafico?.sql && <pre style={{ margin: 0, border: '1px solid var(--surface-3)', padding: 10, borderRadius: 8, fontSize: 'var(--text-xs)', overflow: 'auto' }}>{grafico.sql}</pre>}
    </div>
  )
}

function Datos({ g }: { g: Grafico }) {
  const columnas = useMemo(() => Array.from(new Set((g.data ?? []).flatMap(d => Object.keys(d)))), [g.data])
  const x = g.xAxis?.key
  const series = (g.series ?? []).filter(s => columnas.includes(s.key))
  const dibujable = !!x && series.length > 0 && ['bar_chart', 'line_chart', 'timeseries_line', 'area_chart', 'combo_chart'].includes(g.type || '')
  const Grafica = g.type === 'bar_chart' ? BarChart : LineChart
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {dibujable && (
        <div style={{ height: 260 }} role="img" aria-label={g.title}>
          <ResponsiveContainer>
            <Grafica data={g.data}>
              <CartesianGrid stroke="var(--surface-3)" vertical={false} />
              <XAxis dataKey={x} tick={{ fill: 'var(--text-3)', fontSize: 'var(--text-xs)' }} />
              <YAxis tick={{ fill: 'var(--text-3)', fontSize: 'var(--text-xs)' }} />
              <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)' }} />
              {series.map((s, i) => g.type === 'bar_chart'
                ? <Bar key={s.key} dataKey={s.key} name={s.label} fill={i ? 'var(--info)' : 'var(--accent)'} radius={[4, 4, 0, 0]} />
                : <Line key={s.key} dataKey={s.key} name={s.label} stroke={i ? 'var(--info)' : 'var(--accent)'} dot={false} strokeWidth={2} />)}
            </Grafica>
          </ResponsiveContainer>
        </div>
      )}
      <div style={{ overflow: 'auto', maxHeight: 360 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
          <thead><tr>{columnas.map(c => <th key={c} style={{ textAlign: 'left', padding: '6px 8px', color: 'var(--text-3)', fontWeight: 600, borderBottom: '1px solid var(--surface-3)' }}>{c}</th>)}</tr></thead>
          <tbody>{(g.data ?? []).slice(0, 500).map((d, i) => (
            <tr key={i}>{columnas.map(c => <td key={c} style={{ padding: '5px 8px', borderBottom: '1px solid var(--surface-2)', color: 'var(--text-1)', fontFamily: typeof d[c] === 'number' ? 'var(--font-mono)' : undefined, textAlign: typeof d[c] === 'number' ? 'right' : 'left' }}>{valorTexto(d[c])}</td>)}</tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  )
}

// ── Métricas certificadas ────────────────────────────────────────────────────

function Metricas({ analista }: { analista: boolean }) {
  const t = useAppT()
  const metricas = useQuery({ queryKey: ['conectores', 'ci-metricas'], queryFn: () => conectoresApi.metricas(), retry: false })
  const [elegida, setElegida] = useState<Metrica | null>(null)
  if (metricas.isLoading) return <Spinner />
  if (metricas.isError) {
    return <div role="alert" style={{ ...caja, color: 'var(--text-2)' }}>
      {mensajeDeConector(metricas.error, t('ci.error'))}{!analista && <div style={{ ...sub, marginTop: 6 }}>{t('ci.metricas_solo_analistas')}</div>}
    </div>
  }
  const lista = metricas.data?.items ?? []
  if (!lista.length) return <EmptyState svgIcon={<Sigma size={26} />} title={t('ci.sin_metricas')} description={t('ci.sin_metricas_texto')} />
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 300px) 1fr', gap: 14, alignItems: 'start' }}>
      <ul aria-label={t('ci.tab_metricas')} style={{ ...caja, listStyle: 'none', margin: 0, padding: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
        {lista.map(m => (
          <li key={m.id || m.name}>
            <button type="button" aria-pressed={elegida?.name === m.name} onClick={() => setElegida(m)} style={{ width: '100%', textAlign: 'left', background: elegida?.name === m.name ? 'var(--accent-muted)' : 'transparent', border: 'none', borderRadius: 8, padding: '8px 10px', cursor: 'pointer', color: 'var(--text-1)' }}>
              <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>{m.label}</div>
              <div style={sub}>{m.description || m.name}</div>
            </button>
          </li>
        ))}
      </ul>
      {elegida ? <DetalleMetrica key={elegida.name} m={elegida} /> : <div style={{ ...caja, ...sub }}>{t('ci.elige_metrica')}</div>}
    </div>
  )
}

function DetalleMetrica({ m }: { m: Metrica }) {
  const t = useAppT()
  const [dim, setDim] = useState('')
  const [col, setCol] = useState('')
  const hoy = new Date()
  const iso = (d: Date) => d.toISOString().slice(0, 10)
  const inicioMes = new Date(hoy.getFullYear(), hoy.getMonth(), 1)
  const inicioAnterior = new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1)
  const [actual, setActual] = useState({ start: iso(inicioMes), end: iso(hoy) })
  const [anterior, setAnterior] = useState({ start: iso(inicioAnterior), end: iso(inicioMes) })
  const consulta = useMutation({ mutationFn: () => conectoresApi.consultar(m.source_id, { metric: m.name, dimensions: dim ? [dim] : [] }) })
  const explicar = useMutation({
    mutationFn: () => conectoresApi.explicar({ source_id: m.source_id, metric: m.name, dimensions: dim ? [dim] : undefined,
      actual: { column: col, ...actual }, anterior: { column: col, ...anterior } }),
  })
  const res = consulta.data
  const filas: Fila[] = (res?.rows ?? []).map(r => Object.fromEntries((res?.columns ?? []).map((c, i) => [c, (r as unknown[])[i]])))
  const exp = explicar.data as { antes?: number; despues?: number; delta?: number; delta_pct?: number; aviso?: string; por_dimension?: Fila[] } | undefined
  return (
    <div style={{ ...caja, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <div style={{ fontWeight: 700, color: 'var(--text-1)' }}>{m.label}</div>
        <div style={sub}>{m.description}</div>
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <label style={sub} htmlFor="ci-dim">{t('ci.desglose')}</label>
        <select id="ci-dim" value={dim} onChange={e => setDim(e.target.value)} style={campo}>
          <option value="">{t('ci.sin_desglose')}</option>
          {m.dimensions.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
        <Button size="sm" loading={consulta.isPending} onClick={() => consulta.mutate()}>{t('ci.consultar')}</Button>
      </div>
      {consulta.isError && <div role="alert" style={{ color: 'var(--danger)', fontSize: 'var(--text-sm)' }}>{mensajeDeConector(consulta.error, t('ci.error'))}</div>}
      {res && (
        <>
          <div style={sub}>{res.row_count} {t('ci.n_filas')}{res.governed ? ` · ${t('ci.es_certificada')}` : ''}</div>
          <Datos g={{ type: dim ? 'bar_chart' : 'table', title: m.label, data: filas, xAxis: dim ? { key: dim, label: dim } : null,
            series: (res.columns ?? []).filter(c => c !== dim).map(c => ({ key: c, label: c })), sql: res.executed_sql }} />
        </>
      )}

      <div style={{ borderTop: '1px solid var(--surface-3)', paddingTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <strong style={{ fontSize: 'var(--text-sm)' }}>{t('ci.explicar_cambio')}</strong>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <input aria-label={t('ci.columna_fecha')} placeholder={t('ci.columna_fecha')} value={col} onChange={e => setCol(e.target.value)} style={campo} />
          <span style={sub}>{t('ci.periodo_actual')}</span>
          <input type="date" aria-label={t('ci.periodo_actual')} value={actual.start} onChange={e => setActual(v => ({ ...v, start: e.target.value }))} style={campo} />
          <input type="date" aria-label={t('ci.periodo_actual')} value={actual.end} onChange={e => setActual(v => ({ ...v, end: e.target.value }))} style={campo} />
          <span style={sub}>{t('ci.periodo_anterior')}</span>
          <input type="date" aria-label={t('ci.periodo_anterior')} value={anterior.start} onChange={e => setAnterior(v => ({ ...v, start: e.target.value }))} style={campo} />
          <input type="date" aria-label={t('ci.periodo_anterior')} value={anterior.end} onChange={e => setAnterior(v => ({ ...v, end: e.target.value }))} style={campo} />
          <Button size="sm" variant="secondary" disabled={!col} loading={explicar.isPending} onClick={() => explicar.mutate()}>{t('ci.explicar')}</Button>
        </div>
        {explicar.isError && <div role="alert" style={{ color: 'var(--danger)', fontSize: 'var(--text-sm)' }}>{mensajeDeConector(explicar.error, t('ci.error'))}</div>}
        {exp && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ fontSize: 'var(--text-sm)' }}>
              {valorTexto(exp.antes)} → <strong>{valorTexto(exp.despues)}</strong> ({exp.delta != null && exp.delta >= 0 ? '+' : ''}{valorTexto(exp.delta)}{exp.delta_pct != null ? `, ${exp.delta_pct.toLocaleString(localeActivo(), { maximumFractionDigits: 1 })} %` : ''})
            </div>
            {exp.aviso && <div style={{ ...sub, color: 'var(--warning)' }}>{exp.aviso}</div>}
            {exp.por_dimension && exp.por_dimension.length > 0 && <Datos g={{ type: 'table', title: '', data: exp.por_dimension }} />}
          </div>
        )}
      </div>
    </div>
  )
}
