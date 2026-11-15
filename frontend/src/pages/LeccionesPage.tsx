/**
 * Lecciones aprendidas — la base de la mejora continua (revisión 2026-11).
 *
 * Cuatro pestañas: las lecciones (buscar y filtrar), lo cerrado que aún no
 * tiene lección (capturarla desde sus hechos), las acciones de mejora abiertas
 * y unos pocos indicadores que dicen si la base sirve (cuántas recomendaciones
 * resultaron útiles o aplicadas).
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpenCheck, ClipboardList, Inbox, Plus, Target } from 'lucide-react'
import { leccionesApi } from '../services/api'
import type { Leccion } from '../services/api'
import { Button, EmptyState, KpiCard, Page, Spinner, Tabs } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { fmtDate, extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import FormularioDeLeccion from '../components/lecciones/FormularioDeLeccion'
import FichaDeLeccion, { ColorDeEstado } from '../components/lecciones/FichaDeLeccion'
import { STALE_5_MIN_MS } from '../constants/timings'
import './LeccionesPage.css'

const campo: CSSProperties = { background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 10px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }
const fila: CSSProperties = { display: 'grid', gridTemplateColumns: '90px minmax(0, 1fr) 130px 120px 110px', gap: 12, alignItems: 'center', padding: '10px 12px', borderTop: '1px solid var(--surface-3)', fontSize: 'var(--text-sm)' }

export default function LeccionesPage() {
  const t = useAppT()
  const [tab, setTab] = useState('lecciones')
  const [abierta, setAbierta] = useState<string | null>(null)
  const [nueva, setNueva] = useState<{ tipo: string; id: string } | 'manual' | null>(null)
  const qc = useQueryClient()
  const ind = useQuery({ queryKey: ['lecciones', 'indicadores'], queryFn: leccionesApi.indicadores })
  return (
    <Page title={t('lec.modulo')} subtitle={t('lec.modulo_sub')}
      actions={<Button icon={<Plus size={14} />} onClick={() => setNueva('manual')}>{t('lec.nueva')}</Button>}>
      <Tabs active={tab} onChange={setTab} items={[
        { id: 'lecciones', label: t('lec.tab_lecciones'), icon: <BookOpenCheck size={14} /> },
        { id: 'pendientes', label: `${t('lec.tab_pendientes')}${ind.data ? ` · ${ind.data.pendientes_de_capturar}` : ''}`, icon: <Inbox size={14} /> },
        { id: 'acciones', label: `${t('lec.tab_acciones')}${ind.data ? ` · ${ind.data.acciones_abiertas}` : ''}`, icon: <ClipboardList size={14} /> },
        { id: 'indicadores', label: t('lec.tab_indicadores'), icon: <Target size={14} /> },
      ]} />
      <div className="lecc-box">
        {tab === 'lecciones' && <Lista onAbrir={setAbierta} />}
        {tab === 'pendientes' && <Pendientes onCapturar={(tipo, id) => setNueva({ tipo, id })} />}
        {tab === 'acciones' && <Acciones onAbrir={setAbierta} />}
        {tab === 'indicadores' && <Indicadores onAbrir={setAbierta} />}
      </div>
      {nueva && <FormularioDeLeccion origen={nueva === 'manual' ? null : nueva} onClose={() => setNueva(null)}
        onGuardada={(l: Leccion) => { setNueva(null); qc.invalidateQueries({ queryKey: ['lecciones'] }); setAbierta(l.id) }} />}
      {abierta && <FichaDeLeccion id={abierta} onClose={() => setAbierta(null)} />}
    </Page>
  )
}

function Lista({ onAbrir }: { onAbrir: (id: string) => void }) {
  const t = useAppT()
  const [f, setF] = useState({ q: '', estado: '', tipo: '', categoria: '' })
  const cfg = useQuery({ queryKey: ['lecciones', 'config'], queryFn: leccionesApi.config, staleTime: STALE_5_MIN_MS })
  const q = useQuery({ queryKey: ['lecciones', 'lista', f], queryFn: () => leccionesApi.listar(Object.fromEntries(Object.entries(f).filter(([, v]) => v))) })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF(v => ({ ...v, [k]: e.target.value }))
  return (
    <div>
      <div className="lecc-row">
        <input aria-label={t('lec.buscar')} placeholder={t('lec.buscar')} value={f.q} onChange={set('q')} style={{ ...campo, flex: 1, minWidth: 220 }} />
        <select aria-label={t('lec.estado')} value={f.estado} onChange={set('estado')} style={campo}>
          <option value="">{t('lec.estado_activas')}</option>
          {['borrador', 'en_revision', 'validada', 'archivada'].map(e => <option key={e} value={e}>{t(`lec.estado_${e}`)}</option>)}
        </select>
        <select aria-label={t('lec.tipo')} value={f.tipo} onChange={set('tipo')} style={campo}>
          <option value="">{t('lec.todos_los_tipos')}</option>
          <option value="evitar">{t('lec.tipo_evitar')}</option><option value="repetir">{t('lec.tipo_repetir')}</option>
        </select>
        <select aria-label={t('lec.categoria')} value={f.categoria} onChange={set('categoria')} style={campo}>
          <option value="">{t('lec.todas_las_categorias')}</option>
          {(cfg.data?.categorias ?? []).map(c => <option key={c} value={c}>{t(`lec.cat_${c}`, c)}</option>)}
        </select>
      </div>
      {q.isLoading ? <Spinner /> : q.isError ? <div role="alert" className="u-danger">{extractErr(q.error, GENERIC_ERROR_FALLBACK)}</div>
        : (q.data?.items ?? []).length === 0 ? <EmptyState svgIcon={<BookOpenCheck size={26} />} title={t('lec.vacio')} description={t('lec.vacio_texto')} />
        : (
          <div className="lecc-card">
            <div style={{ ...fila, borderTop: 'none', color: 'var(--text-3)', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase' }}>
              <span>{t('lec.codigo')}</span><span>{t('lec.titulo')}</span><span>{t('lec.categoria')}</span><span>{t('lec.estado')}</span><span>{t('lec.le_sirvio')}</span>
            </div>
            {q.data!.items.map(l => (
              <button key={l.id} type="button" onClick={() => onAbrir(l.id)} style={{ ...fila, width: '100%', background: 'transparent', border: 'none', borderTop: '1px solid var(--surface-3)', textAlign: 'left', cursor: 'pointer', color: 'var(--text-1)', fontFamily: 'inherit' }}>
                <span className="lecc-label">{l.codigo}</span>
                <span className="u-min0">
                  <span className="lecc-label-2">{l.titulo}</span>
                  <span className="u-text3-xs">{t(`lec.tipo_${l.tipo}`)}{l.origen_ref ? ` · ${l.origen_ref}` : ''}</span>
                </span>
                <span className="u-text2">{t(`lec.cat_${l.categoria}`, l.categoria)}</span>
                <span className="u-600" style={{ color: ColorDeEstado(l.estado) }}>{t(`lec.estado_${l.estado}`)}</span>
                <span className="lecc-label-3">{l.usos.util + l.usos.aplicada} / {l.usos.util + l.usos.aplicada + l.usos.no_aplica}</span>
              </button>
            ))}
          </div>
        )}
    </div>
  )
}

function Pendientes({ onCapturar }: { onCapturar: (tipo: string, id: string) => void }) {
  const t = useAppT()
  const q = useQuery({ queryKey: ['lecciones', 'pendientes'], queryFn: leccionesApi.pendientes })
  if (q.isLoading) return <Spinner />
  if (q.isError) return <div role="alert" className="u-danger">{extractErr(q.error, GENERIC_ERROR_FALLBACK)}</div>
  const items = q.data?.items ?? []
  if (!items.length) return <EmptyState svgIcon={<Inbox size={26} />} title={t('lec.sin_pendientes')} description={t('lec.sin_pendientes_texto')} />
  return (
    <div className="lecc-card">
      <div className="lecc-box-2">{t('lec.pendientes_texto')}</div>
      {items.map(p => (
        <div key={`${p.origen_tipo}-${p.origen_id}`} className="lecc-row-2">
          <span className="lecc-card-2">{t(`lec.origen_${p.origen_tipo}`)}</span>
          <span className="lecc-label">{p.ref}</span>
          <span className="lecc-label-4">{p.titulo}</span>
          <span className="u-text3-xs">{p.cerrado ? fmtDate(p.cerrado) : '—'}</span>
          <Button size="sm" onClick={() => onCapturar(p.origen_tipo, p.origen_id)}>{t('lec.capturar')}</Button>
        </div>
      ))}
    </div>
  )
}

function Acciones({ onAbrir }: { onAbrir: (id: string) => void }) {
  const t = useAppT()
  const [mias, setMias] = useState(false)
  const q = useQuery({ queryKey: ['lecciones', 'acciones', mias], queryFn: () => leccionesApi.acciones({ solo_mias: mias }) })
  return (
    <div>
      <label className="lecc-label-5">
        <input type="checkbox" aria-label={t('lec.solo_mias')} checked={mias} onChange={e => setMias(e.target.checked)} />{t('lec.solo_mias')}
      </label>
      {q.isLoading ? <Spinner /> : (q.data?.items ?? []).length === 0
        ? <EmptyState svgIcon={<ClipboardList size={26} />} title={t('lec.sin_acciones_abiertas')} description="" />
        : (
          <div className="lecc-card">
            {q.data!.items.map(a => (
              <button key={a.id} type="button" onClick={() => onAbrir(a.leccion_id)} className="lecc-btn">
                <span className="lecc-label">{a.leccion_codigo}</span>
                <span className="u-flex1">{a.descripcion}</span>
                <span className="u-text2-xs">{t(`lec.accion_${a.estado}`)}</span>
                <span className="lecc-label-6" style={{ color: a.vencida ? 'var(--danger)' : 'var(--text-3)' }}>{a.fecha_limite ? fmtDate(a.fecha_limite) : '—'}</span>
              </button>
            ))}
          </div>
        )}
    </div>
  )
}

function Indicadores({ onAbrir }: { onAbrir: (id: string) => void }) {
  const t = useAppT()
  const q = useQuery({ queryKey: ['lecciones', 'indicadores'], queryFn: leccionesApi.indicadores })
  if (q.isLoading) return <Spinner />
  const d = q.data
  if (!d) return null
  return (
    <div className="u-stack-16">
      <div className="lecc-grid">
        <KpiCard label={t('lec.kpi_validadas')} value={d.por_estado.validada ?? 0} sub={t('lec.kpi_en_revision', { n: d.por_estado.en_revision ?? 0 })} />
        <KpiCard label={t('lec.kpi_efectividad')} value={d.efectividad_pct == null ? '—' : `${d.efectividad_pct.toLocaleString()} %`} sub={t('lec.kpi_valoraciones', { n: d.valoraciones_total })} />
        <KpiCard label={t('lec.kpi_pendientes')} value={d.pendientes_de_capturar} warning={d.pendientes_de_capturar > 0} />
        <KpiCard label={t('lec.kpi_acciones')} value={d.acciones_abiertas} sub={t('lec.kpi_vencidas', { n: d.acciones_vencidas })} danger={d.acciones_vencidas > 0} />
      </div>
      <div className="lecc-grid-2">
        <section className="lecc-card-3">
          <h3 className="lecc-title">{t('lec.por_categoria')}</h3>
          {Object.entries(d.por_categoria).map(([c, n]) => {
            const max = Math.max(...Object.values(d.por_categoria), 1)
            return (
              <div key={c} className="lecc-grid-3">
                <span className="u-text2">{t(`lec.cat_${c}`, c)}</span>
                <span className="lecc-card-4"><span className="lecc-card-5" style={{ width: `${(n / max) * 100}%` }} /></span>
                <span className="lecc-label-7">{n}</span>
              </div>
            )
          })}
        </section>
        <section className="lecc-card-3">
          <h3 className="lecc-title">{t('lec.mas_utiles')}</h3>
          {d.mas_utiles.length === 0 ? <div className="u-text3-sm">{t('lec.sin_valoraciones')}</div>
            : d.mas_utiles.map(l => (
              <button key={l.id} type="button" onClick={() => onAbrir(l.id)} className="lecc-btn-2">
                <span className="lecc-label">{l.codigo}</span><span className="u-flex1">{l.titulo}</span><span className="u-mono">{l.valoraciones_utiles}</span>
              </button>
            ))}
        </section>
      </div>
    </div>
  )
}
