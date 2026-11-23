/**
 * Pestañas de la CMDB de software y vulnerabilidades (19-11-2026):
 * «Software» (cuadro de mando y catálogo), «Dónde se usa», «Por máquina» y
 * «Vulnerabilidades». Las pinta CMDBPage a quien tiene `software.ver`.
 *
 * Diseño: docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md (sección 8). Datos:
 * services/api/cmdbSoftware.ts. Escribir pide `software.gestionar`; aprobar
 * excepciones y líneas base, `software.aprobar` (el servidor lo vuelve a mirar).
 */
import { lazy, Suspense, useState } from 'react'
import type { CSSProperties, FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, Boxes, CheckCircle2, Download, FileUp, GitMerge, Network, Package, Plus, RefreshCw, Search,
  Server, ShieldAlert, ShieldCheck, Upload,
} from 'lucide-react'
import { useAppT } from '../../../i18n/AppLangContext'
import { useToast } from '../../../context/ToastContext'
import { useAuth } from '../../../context/AuthContext'
import { confirmar, pedirTexto } from '../../../context/ConfirmContext'
import { fmtDate, fmtDateTime } from '../../../utils/helpers'
import { FULL_LIST_SIZE } from '../../../constants/pagination'
import { cmdbApi } from '../../../services/api'
import { cmdbSoftwareApi } from '../../../services/api/cmdbSoftware'
import type { SdCi } from '../../../services/api/tipos-sd'
import type { InstanciaSw, Severidad } from '../../../services/api/cmdbSoftware'
import type { RawEdge, RawNode } from '../CMDBTopologyGraph'
import { Buscador, Button, Checkbox, EmptyState, KpiCard, Modal, Section, Select, Spinner, StatusBadge, TablaSimple, Input } from '../../ui'
import {
  BotonFichero, CicloBadge, EXCEPCION_KIND, ListaKv, ORDEN_SEV, Opciones, PosibleBadge, SeveridadBadge, VersionTexto,
  descargar, useAvisoDeImportacion, useErr, useEtiquetaSw, useMetaSw, valorLegible,
} from './comun'
import FichaDeSoftware, { EditarProductoModal, InstanciaModal } from './FichaDeSoftware'
import { AvisoDeConfiguracion, PanelDeEscaneos } from './Escaneos'
import { TablaHallazgos, TablaInstancias } from './tablas'
import DetalleDeHallazgo from './DetalleDeHallazgo'
import '../../servicedesk/sdMercado.css'
import './software.css'

const CMDBTopologyGraph = lazy(() => import('../CMDBTopologyGraph'))

const hoy = () => new Date().toISOString().slice(0, 10)

// ── Software: cuadro de mando y catálogo ─────────────────────────────────────

export function SoftwareTab() {
  const t = useAppT()
  const e = useEtiquetaSw()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { puede } = useAuth()
  const gestiona = puede('software.gestionar')
  const meta = useMetaSw()
  const avisoImportacion = useAvisoDeImportacion()
  const [q, setQ] = useState('')
  const [categoria, setCategoria] = useState('')
  const [origen, setOrigen] = useState('')
  const [ciclo, setCiclo] = useState('')
  const [abierto, setAbierto] = useState<string | null>(null)
  const [nuevo, setNuevo] = useState(false)
  const [verDuplicados, setVerDuplicados] = useState(false)
  const cuadro = useQuery({ queryKey: ['sw', 'cuadro'], queryFn: cmdbSoftwareApi.cuadroDeMando })
  const productos = useQuery({
    queryKey: ['sw', 'productos', q, categoria, origen, ciclo],
    queryFn: () => cmdbSoftwareApi.productos({ q: q.trim() || undefined, category: categoria || undefined, origin: origen || undefined, lifecycle: ciclo || undefined, page_size: 500 }),
  })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['sw'] })
  const importarCsv = useMutation({ mutationFn: cmdbSoftwareApi.importarCsv, onSuccess: r => { avisoImportacion(r); refrescar() }, onError: err })
  const conciliar = useMutation({
    mutationFn: cmdbSoftwareApi.importarDesdeActivos,
    onSuccess: r => { toast.success(t('sw.conciliado', { productos: r.products_created ?? 0, instancias: (r.instances_created ?? 0) + (r.instances_linked ?? 0), licencias: r.licenses_linked ?? 0 })); refrescar() },
    onError: err,
  })
  const exportar = useMutation({ mutationFn: () => descargar(cmdbSoftwareApi.exportarInventario(), `inventario-software-${hoy()}.csv`), onError: err })
  const c = cuadro.data
  const items = productos.data?.items ?? []
  const hayFiltro = !!(q || categoria || origen || ciclo)

  return (
    <div className="u-stack-20">
      {cuadro.isLoading ? <Spinner /> : c && (
        <div className="ds-grid-stats">
          <KpiCard label={t('sw.kpi_productos')} value={c.products} icon={<Package size={14} />} sub={t('sw.kpi_aplicaciones', { n: c.applications })} />
          <KpiCard label={t('sw.kpi_instancias')} value={c.instances} icon={<Boxes size={14} />} sub={t('sw.kpi_componentes', { n: c.components })} />
          <KpiCard label={t('sw.kpi_maquinas')} value={c.machines} icon={<Server size={14} />} />
          <KpiCard label={t('sw.kpi_hallazgos')} value={c.findings_live} icon={<ShieldAlert size={14} />} danger={c.findings_live > 0}
            sub={t('sw.kpi_criticos', { n: (c.findings_by_severity.critical ?? 0) + (c.findings_by_severity.high ?? 0) })} />
          <KpiCard label={t('sw.kpi_fuera_sla')} value={c.findings_out_of_sla} danger={c.findings_out_of_sla > 0} />
          <KpiCard label={t('sw.kpi_kev')} value={c.findings_kev} danger={c.findings_kev > 0} />
          <KpiCard label={t('sw.kpi_eol_prod')} value={c.eol_in_production} warning={c.eol_in_production > 0}
            sub={t('sw.kpi_eol_detalle', { eol: c.eol.eol, soon: c.eol.soon })} />
          <KpiCard label={t('sw.kpi_deriva')} value={c.drift.drift + c.drift.violations} warning={c.drift.drift + c.drift.violations > 0} />
          <KpiCard label={t('sw.kpi_licencias')} value={c.licenses.conflicts} danger={c.licenses.conflicts > 0} sub={t('sw.kpi_avisos', { n: c.licenses.warnings })} />
          <KpiCard label={t('sw.kpi_sin_responsable')} value={c.products_without_owner} warning={c.products_without_owner > 0} />
        </div>
      )}
      {c && <div className="u-text3-xs">{t('sw.ultima_sync')}: {c.last_sync_at ? fmtDateTime(c.last_sync_at) : t('sw.nunca')}{c.last_sync_status ? ` · ${e('ejec', c.last_sync_status)}` : ''}</div>}

      <Section title={t('sw.catalogo')} subtitle={t('sw.catalogo_desc')}
        actions={<div className="u-wrap-8">
          {gestiona && <Button size="sm" icon={<Plus size={14} />} onClick={() => setNuevo(true)}>{t('sw.nuevo_software')}</Button>}
          {gestiona && <BotonFichero accept=".csv,text/csv" icon={<Upload size={14} />} loading={importarCsv.isPending} onFichero={f => importarCsv.mutate(f)}>{t('sw.importar_csv')}</BotonFichero>}
          {gestiona && <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} loading={conciliar.isPending} onClick={() => conciliar.mutate()}>{t('sw.conciliar_activos')}</Button>}
          {gestiona && <Button size="sm" variant="secondary" icon={<GitMerge size={14} />} onClick={() => setVerDuplicados(true)}>{t('sw.duplicados')}</Button>}
          <Button size="sm" variant="ghost" icon={<Download size={14} />} loading={exportar.isPending} onClick={() => exportar.mutate()}>{t('sw.exportar_inventario')}</Button>
        </div>}>
        <div className="u-stack-12">
          <div className="sdm-form">
            <Buscador label={t('sw.buscar')} value={q} placeholder={t('sw.buscar_ph')} onChange={setQ} />
            <label className="sdm-field"><span>{t('sw.categoria')}</span>
              <Select suelto placeholder={false} value={categoria} onChange={ev => setCategoria(ev.target.value)}>
                <Opciones valores={meta.data?.categories} catalogo="cat" todos={t('sw.todas')} /></Select></label>
            <label className="sdm-field"><span>{t('sw.origen')}</span>
              <Select suelto placeholder={false} value={origen} onChange={ev => setOrigen(ev.target.value)}>
                <Opciones valores={meta.data?.origins} catalogo="origen" todos={t('sw.todos')} /></Select></label>
            <label className="sdm-field"><span>{t('sw.ciclo')}</span>
              <Select suelto placeholder={false} value={ciclo} onChange={ev => setCiclo(ev.target.value)}>
                <Opciones valores={meta.data?.lifecycles} catalogo="ciclo" todos={t('sw.todos')} /></Select></label>
          </div>
          {gestiona && meta.data && <div className="u-text3-xs">{t('sw.csv_columnas')}: <span className="u-mono">{meta.data.csv_columns.join(', ')}</span></div>}
          {productos.isLoading ? <Spinner /> : items.length === 0 ? (
            <EmptyState icon={<Package size={28} />} title={hayFiltro ? t('sw.sin_coincidencias') : t('sw.sin_software')}
              description={hayFiltro ? undefined : t('sw.sin_software_desc')} />
          ) : (
            <TablaSimple etiqueta={t('sw.catalogo')}>
              <thead><tr>
                <th>{t('sw.col_nombre')}</th><th>{t('sw.categoria')}</th><th>{t('sw.origen')}</th>
                <th className="sw-num">{t('sw.col_versiones')}</th><th className="sw-num">{t('sw.col_instancias')}</th>
                <th className="sw-num">{t('sw.col_maquinas')}</th><th className="sw-num">{t('sw.col_hallazgos')}</th>
                <th>{t('sw.col_peor')}</th><th>{t('sw.ciclo')}</th>
              </tr></thead>
              <tbody>
                {items.map(p => (
                  <tr key={p.id}>
                    <td>
                      <Button variant="link" className="sw-enlace" onClick={() => setAbierto(p.id)}>{p.name}</Button>
                      <div className="u-text3-xs">{[p.vendor_name, p.owner_name].filter(Boolean).join(' · ') || '—'}</div>
                    </td>
                    <td>{e('cat', p.category)}</td>
                    <td>{e('origen', p.origin)}</td>
                    <td className="sw-num">{p.versions_count ?? 0}</td>
                    <td className="sw-num">{p.instances_count ?? 0}</td>
                    <td className="sw-num">{p.machines_count ?? 0}</td>
                    <td className="sw-num">{p.open_findings ?? 0}</td>
                    <td><SeveridadBadge s={p.worst_severity} /></td>
                    <td><StatusBadge kind={p.lifecycle_status === 'retired' ? 'neutral' : p.lifecycle_status === 'deprecated' ? 'warning' : 'success'} caps={false}>{e('ciclo', p.lifecycle_status)}</StatusBadge></td>
                  </tr>
                ))}
              </tbody>
            </TablaSimple>
          )}
          {(productos.data?.total ?? 0) > items.length && <div className="u-text3-xs">{t('sw.mostrando', { n: items.length, total: productos.data?.total ?? 0 })}</div>}
        </div>
      </Section>

      {gestiona && <PanelDeEscaneos />}

      {abierto && <FichaDeSoftware id={abierto} onClose={() => setAbierto(null)} />}
      {nuevo && <EditarProductoModal producto={null} onClose={() => setNuevo(false)} onSaved={p => { setNuevo(false); refrescar(); setAbierto(p.id) }} />}
      {verDuplicados && <DuplicadosModal onClose={() => setVerDuplicados(false)} />}
    </div>
  )
}

function DuplicadosModal({ onClose }: { onClose: () => void }) {
  const t = useAppT()
  const e = useEtiquetaSw()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { data, isLoading } = useQuery({ queryKey: ['sw', 'duplicados'], queryFn: cmdbSoftwareApi.duplicados })
  const [destino, setDestino] = useState<Record<number, string>>({})
  const fusionar = useMutation({
    mutationFn: ({ origen, dest }: { origen: string; dest: string }) => cmdbSoftwareApi.fusionar(origen, dest),
    onSuccess: () => { toast.success(t('sw.fusionado')); qc.invalidateQueries({ queryKey: ['sw'] }) },
    onError: err,
  })
  return (
    <Modal open size="lg" onClose={onClose} title={t('sw.duplicados')} subtitle={t('sw.duplicados_desc')}>
      {isLoading ? <Spinner /> : (data ?? []).length === 0 ? <EmptyState icon={<CheckCircle2 size={28} />} title={t('sw.sin_duplicados')} /> : (
        <ul className="sdm-list">
          {(data ?? []).map((g, i) => {
            const dest = destino[i] ?? g.products[0]?.id
            const nombreDestino = g.products.find(p => p.id === dest)?.name ?? ''
            return (
              <li key={i} className="sdm-list__item">
                <div className="u-flex1-min0 u-stack-6">
                  <StatusBadge caps={false}>{e('motivo_dup', g.reason)}</StatusBadge>
                  <label className="sdm-field"><span>{t('sw.conservar')}</span>
                    <Select suelto placeholder={false} value={dest} onChange={ev => setDestino({ ...destino, [i]: ev.target.value })}>
                      {g.products.map(p => <option key={p.id} value={p.id}>{p.name} · {e('cat', p.category)}</option>)}
                    </Select></label>
                  <div className="u-wrap-6">
                    {g.products.filter(p => p.id !== dest).map(p => (
                      <Button key={p.id} size="xs" variant="secondary" icon={<GitMerge size={12} />} disabled={fusionar.isPending}
                        onClick={async () => { if (await confirmar({ message: t('sw.fusionar_confirmar', { origen: p.name, destino: nombreDestino }), danger: true })) fusionar.mutate({ origen: p.id, dest }) }}>
                        {t('sw.fusionar_en', { origen: p.name })}
                      </Button>
                    ))}
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </Modal>
  )
}

// ── Dónde se usa ──────────────────────────────────────────────────────────────

export function DondeSeUsaTab() {
  const t = useAppT()
  const e = useEtiquetaSw()
  const meta = useMetaSw()
  const [texto, setTexto] = useState('')
  const [entorno, setEntorno] = useState('')
  const [consulta, setConsulta] = useState('')
  const [abierto, setAbierto] = useState<string | null>(null)
  const { data, isFetching } = useQuery({
    queryKey: ['sw', 'donde', consulta, entorno],
    queryFn: () => cmdbSoftwareApi.dondeSeUsa({ q: consulta, environment: entorno || undefined }),
    enabled: consulta.trim().length >= 2,
  })
  const buscar = (ev: FormEvent) => { ev.preventDefault(); setConsulta(texto.trim()) }
  const total = Math.max(1, ...Object.values(data?.versions ?? {}))
  return (
    <div className="u-stack-20">
      <Section title={t('sw.donde_titulo')} subtitle={t('sw.donde_desc')}>
        <form className="sdm-form" onSubmit={buscar}>
          <Input label={t('sw.buscar')} value={texto} placeholder={t('sw.donde_ph')} onChange={ev => setTexto(ev.target.value)} />
          <label className="sdm-field"><span>{t('sw.entorno')}</span>
            <Select suelto placeholder={false} value={entorno} onChange={ev => setEntorno(ev.target.value)}>
              <Opciones valores={meta.data?.environments} catalogo="entorno" todos={t('sw.todos')} /></Select></label>
          <div><Button type="submit" icon={<Search size={14} />} disabled={texto.trim().length < 2} loading={isFetching}>{t('sw.buscar')}</Button></div>
        </form>
      </Section>
      {!consulta ? <EmptyState icon={<Search size={28} />} title={t('sw.donde_vacio')} description={t('sw.donde_ejemplos')} />
        : isFetching && !data ? <Spinner />
        : data && (data.summary.instances + data.summary.components === 0
          ? <EmptyState icon={<Search size={28} />} title={t('sw.donde_nada', { q: consulta })} />
          : <>
            <div className="ds-grid-stats">
              <KpiCard label={t('sw.kpi_instancias')} value={data.summary.instances} />
              <KpiCard label={t('sw.donde_software')} value={data.summary.software} />
              <KpiCard label={t('sw.kpi_maquinas')} value={data.summary.machines} />
              <KpiCard label={t('sw.donde_componentes')} value={data.summary.components} />
            </div>
            {data.products.length > 0 && (
              <div className="u-wrap-6">
                {data.products.map(p => <Button key={p.id} size="xs" variant="secondary" onClick={() => setAbierto(p.id)}>{p.name} · {e('cat', p.category)}</Button>)}
              </div>
            )}
            <div className="sdm-grid">
              <div className="ds-card sdm-card">
                <div className="sdm-card__head">{t('sw.distribucion_versiones')}</div>
                <ul className="sw-barras">
                  {Object.entries(data.versions).map(([v, n]) => (
                    <li key={v}><span className="u-mono">{v}</span>
                      <span className="sdm-bar"><span className="sdm-bar__fill" style={{ '--sdm-w': `${Math.round((n / total) * 100)}%` } as CSSProperties} /></span>
                      <span className="sw-num">{n}</span></li>
                  ))}
                </ul>
              </div>
            </div>
            {data.instances.length > 0 && (
              <Section title={t('sw.instancias')}>
                <TablaInstancias instancias={data.instances} conProducto />
              </Section>
            )}
            {data.software.length > 0 && (
              <Section title={t('sw.software_que_lo_lleva')} subtitle={t('sw.software_que_lo_lleva_desc')}>
                <ul className="sdm-list">
                  {data.software.map(s => (
                    <li key={s.version_id} className="sdm-list__item">
                      <div className="u-flex1-min0 u-stack-6">
                        <div className="u-wrap-8">
                          <Button variant="link" className="sw-enlace" onClick={() => setAbierto(s.product_id)}>{s.product_name}</Button>
                          <span className="u-mono u-text3-xs">{s.version}</span>
                          <StatusBadge caps={false}>{e('origen', s.origin)}</StatusBadge>
                        </div>
                        <div className="u-wrap-6">
                          {s.components.map(c => (
                            <span key={c.component_id} className="u-wrap-6">
                              <StatusBadge kind={c.direct ? 'accent' : 'neutral'} caps={false}>{c.name} {c.version ?? t('sw.version_desconocida')} · {t(c.direct ? 'sw.directo' : 'sw.transitivo')}</StatusBadge>
                              <CicloBadge c={c.lifecycle} fecha={c.eol_date} />
                            </span>
                          ))}
                        </div>
                        <div className="u-text3-xs">
                          {s.machines.length === 0 ? t('sw.sin_maquinas') : s.machines.map(m => `${m.name}${m.ip_address ? ` (${m.ip_address})` : ''}${m.environment ? ` · ${e('entorno', m.environment)}` : ''}`).join(' · ')}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              </Section>
            )}
          </>)}
      {abierto && <FichaDeSoftware id={abierto} onClose={() => setAbierto(null)} />}
    </div>
  )
}

// ── Por máquina ───────────────────────────────────────────────────────────────

type CiDeLista = Pick<SdCi, 'id' | 'code' | 'name' | 'ci_type' | 'hostname' | 'ip_address'>

export function PorMaquinaTab() {
  const t = useAppT()
  const e = useEtiquetaSw()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { puede } = useAuth()
  const [ciId, setCiId] = useState('')
  const [filtro, setFiltro] = useState('')
  const [alta, setAlta] = useState(false)
  const [editando, setEditando] = useState<InstanciaSw | null>(null)
  const [verGrafo, setVerGrafo] = useState(false)
  const { data: cis = [] } = useQuery<CiDeLista[]>({
    queryKey: ['cmdb-items', 'todos'],
    queryFn: () => cmdbApi.sdList({ page_size: FULL_LIST_SIZE }).then(r => r.data ?? []),
  })
  const maquina = useQuery({ queryKey: ['sw', 'maquina', ciId], queryFn: () => cmdbSoftwareApi.maquina(ciId), enabled: !!ciId })
  const grafo = useQuery({ queryKey: ['sw', 'grafo-ci', ciId], queryFn: () => cmdbSoftwareApi.grafo({ ci_id: ciId }), enabled: !!ciId && verGrafo })
  const aprobar = useMutation({
    mutationFn: cmdbSoftwareApi.aprobarConfiguracion,
    onSuccess: () => { toast.success(t('sw.linea_base_aprobada')); qc.invalidateQueries({ queryKey: ['sw'] }) },
    onError: err,
  })
  const visibles = filtro.trim()
    ? cis.filter(c => `${c.code ?? ''} ${c.name ?? ''} ${c.hostname ?? ''} ${c.ip_address ?? ''}`.toLowerCase().includes(filtro.trim().toLowerCase()))
    : cis
  const m = maquina.data
  return (
    <div className="u-stack-20">
      <Section title={t('sw.maquina_titulo')} subtitle={t('sw.maquina_desc')}>
        <div className="sdm-form">
          <Buscador label={t('sw.filtrar_ci')} value={filtro} onChange={setFiltro} placeholder={t('sw.filtrar_ci_ph')} />
          <label className="sdm-field"><span>{t('sw.maquina')}</span>
            <Select suelto placeholder={false} value={ciId} onChange={ev => { setCiId(ev.target.value); setVerGrafo(false) }}>
              <option value="">{t('sw.elige_ci')}</option>
              {visibles.map(c => <option key={c.id} value={c.id}>{c.code ? `${c.code} · ` : ''}{c.name}{c.ip_address ? ` (${c.ip_address})` : ''}</option>)}
            </Select></label>
        </div>
      </Section>
      {!ciId ? <EmptyState icon={<Server size={28} />} title={t('sw.elige_ci')} />
        : maquina.isLoading ? <Spinner />
        : m && <>
          <Section title={m.ci.name} subtitle={[m.ci.code, m.ci.hostname, m.ci.ip_address, m.ci.environment].filter(Boolean).join(' · ')}
            actions={<div className="u-wrap-8">
              {puede('software.gestionar') && <Button size="sm" icon={<Plus size={14} />} onClick={() => setAlta(true)}>{t('sw.instancia_nueva')}</Button>}
              <Button size="sm" variant="secondary" icon={<Network size={14} />} onClick={() => setVerGrafo(!verGrafo)}>{t(verGrafo ? 'sw.ocultar_grafo' : 'sw.ver_grafo')}</Button>
            </div>}>
            <div className="ds-grid-stats">
              <KpiCard label={t('sw.software_instalado')} value={m.instances.length} />
              {ORDEN_SEV.slice(0, 4).map(s => <KpiCard key={s} label={e('sev', s)} value={m.findings_by_severity[s] ?? 0} danger={(s === 'critical' || s === 'high') && (m.findings_by_severity[s] ?? 0) > 0} />)}
              <KpiCard label={t('sw.tickets_abiertos')} value={m.open_tickets} />
            </div>
          </Section>
          {verGrafo && (
            <Section title={t('sw.grafo')}>
              {grafo.isLoading ? <Spinner /> : (
                <Suspense fallback={<Spinner />}>
                  <CMDBTopologyGraph nodes={(grafo.data?.nodes ?? []) as unknown as RawNode[]} edges={(grafo.data?.edges ?? []) as unknown as RawEdge[]} centerName={m.ci.name} />
                </Suspense>
              )}
            </Section>
          )}
          <Section title={t('sw.software_instalado')}>
            {m.instances.length === 0 ? <EmptyState icon={<Package size={28} />} title={t('sw.sin_instancias')} /> : (
              <ul className="sdm-list">
                {m.instances.map(i => (
                  <li key={i.id} className="sdm-list__item">
                    <div className="u-flex1-min0 u-stack-6">
                      <div className="u-wrap-8">
                        <span className="u-text1-sm-600">{i.product_name ?? i.name}</span>
                        <span className="u-text3-xs"><VersionTexto v={i.version} /></span>
                        <StatusBadge caps={false}>{e('entorno', i.environment)}</StatusBadge>
                        <StatusBadge caps={false} kind={i.status === 'running' ? 'success' : 'neutral'}>{e('est_inst', i.status)}</StatusBadge>
                        <CicloBadge c={i.lifecycle} fecha={i.eol_date} />
                        {i.drift_detected_at && <StatusBadge kind="warning" caps={false}>{t('sw.deriva_desde', { fecha: fmtDate(i.drift_detected_at) })}</StatusBadge>}
                        {(i.open_findings ?? 0) > 0 && <><StatusBadge kind="danger" caps={false}>{t('sw.n_hallazgos', { n: i.open_findings ?? 0 })}</StatusBadge><SeveridadBadge s={i.worst_severity} /></>}
                      </div>
                      <div className="u-text3-xs">
                        {[i.install_path, i.config_path, (i.ports ?? []).length ? `${t('sw.puertos')}: ${i.ports.join(', ')}` : null, e('expo', i.exposure)].filter(Boolean).join(' · ')}
                        {i.baseline_approved_at && ` · ${t('sw.linea_base_del', { fecha: fmtDate(i.baseline_approved_at) })}`}
                      </div>
                      {i.config && Object.keys(i.config).length > 0 && (
                        <details className="sw-detalles"><summary>{t('sw.configuracion_n', { n: Object.keys(i.config).length })}</summary>
                          <ListaKv filas={Object.entries(i.config).map(([k, v]) => [<span key={k} className="u-mono">{k}</span>, <span key={`${k}-v`} className="u-mono">{valorLegible(v)}</span>])} />
                        </details>
                      )}
                      {(i.baseline_violations ?? []).length > 0 && (
                        <div className="sw-incumplimientos">
                          <div className="u-row-center-6"><AlertTriangle size={14} /> {t('sw.incumplimientos', { n: i.baseline_violations?.length ?? 0 })}</div>
                          <ul>{(i.baseline_violations ?? []).map((v, k) => (
                            <li key={k}><span className="u-mono">{v.key}</span> {e('op', v.op)} <span className="u-mono">{valorLegible(v.expected)}</span> · {t('sw.actual')}: <span className="u-mono">{valorLegible(v.actual)}</span> <SeveridadBadge s={v.severity} /></li>
                          ))}</ul>
                        </div>
                      )}
                    </div>
                    <div className="u-actions-8">
                      {puede('software.gestionar') && <Button size="xs" variant="ghost" onClick={() => setEditando(i)}>{t('sw.editar')}</Button>}
                      {puede('software.aprobar') && i.config && <Button size="xs" variant="secondary" icon={<ShieldCheck size={12} />} loading={aprobar.isPending}
                        onClick={async () => { if (await confirmar({ message: t('sw.aprobar_config_confirmar') })) aprobar.mutate(i.id) }}>{t('sw.aprobar_config')}</Button>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Section>
          <div className="sdm-grid">
            <div className="ds-card sdm-card">
              <div className="sdm-card__head">{t('sw.activos')}</div>
              {m.assets.length === 0 ? <div className="u-text3-xs">{t('sw.sin_activos')}</div> : (
                <ul className="sdm-list">{m.assets.map(a => (
                  <li key={a.id} className="sdm-list__item"><div className="u-flex1-min0">
                    <div className="u-text1-sm-600">{a.name}</div>
                    <div className="u-text3-xs">{[a.asset_tag, a.serial_number, a.os].filter(Boolean).join(' · ')}</div>
                    <div className="u-text3-xs">{t('sw.garantia')}: {fmtDate(a.warranty_expiry)} · {t('sw.fin_vida')}: {fmtDate(a.eol_date)}</div>
                  </div></li>
                ))}</ul>
              )}
            </div>
            <div className="ds-card sdm-card">
              <div className="sdm-card__head">{t('sw.licencias')}</div>
              {m.licenses.length === 0 ? <div className="u-text3-xs">{t('sw.sin_licencias')}</div> : (
                <ul className="sdm-list">{m.licenses.map(l => (
                  <li key={l.id} className="sdm-list__item"><div className="u-flex1-min0">
                    <div className="u-text1-sm-600">{l.name}</div>
                    <div className="u-text3-xs">{t('sw.caduca')}: {fmtDate(l.expiry_date)}</div>
                  </div></li>
                ))}</ul>
              )}
            </div>
            <div className="ds-card sdm-card">
              <div className="sdm-card__head">{t('sw.historial_software')}</div>
              {m.software_history.length === 0 ? <div className="u-text3-xs">{t('sw.sin_historial')}</div> : (
                <ul className="sdm-list">{m.software_history.map((h, k) => (
                  <li key={k} className="sdm-list__item"><div className="u-flex1-min0">
                    <div className="u-text2-sm">{h.summary ?? h.field}</div>
                    {(h.old_value || h.new_value) && <div className="u-text3-xs u-mono">{h.old_value ?? '—'} → {h.new_value ?? '—'}</div>}
                    <div className="u-text3-xs">{fmtDateTime(h.created_at)}</div>
                  </div></li>
                ))}</ul>
              )}
            </div>
          </div>
        </>}
      {alta && ciId && <InstanciaModal inicial={null} ciId={ciId} onClose={() => setAlta(false)} onSaved={() => { setAlta(false); qc.invalidateQueries({ queryKey: ['sw'] }) }} />}
      {editando && <InstanciaModal inicial={editando} productId={editando.product_id} onClose={() => setEditando(null)} onSaved={() => { setEditando(null); qc.invalidateQueries({ queryKey: ['sw'] }) }} />}
    </div>
  )
}

// ── Vulnerabilidades ──────────────────────────────────────────────────────────

const ESTADOS_ABIERTOS = 'open,triaged,in_progress'

export function VulnerabilidadesTab() {
  const t = useAppT()
  const e = useEtiquetaSw()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { puede } = useAuth()
  const gestiona = puede('software.gestionar')
  const meta = useMetaSw()
  const avisoImportacion = useAvisoDeImportacion()
  const [estado, setEstado] = useState(ESTADOS_ABIERTOS)
  const [severidad, setSeveridad] = useState('')
  const [kev, setKev] = useState(false)
  const [fueraSla, setFueraSla] = useState(false)
  const [posible, setPosible] = useState('')
  const [sinFuentes, setSinFuentes] = useState(false)
  const [q, setQ] = useState('')
  const [abierto, setAbierto] = useState<string | null>(null)
  const cuadro = useQuery({ queryKey: ['sw', 'cuadro'], queryFn: cmdbSoftwareApi.cuadroDeMando })
  const hallazgos = useQuery({
    queryKey: ['sw', 'hallazgos', estado, severidad, kev, fueraSla, posible, q],
    queryFn: () => cmdbSoftwareApi.hallazgos({ status: estado || undefined, severity: severidad || undefined, kev: kev || undefined, out_of_sla: fueraSla || undefined,
      possible: posible === '' ? undefined : posible === 'true', q: q.trim() || undefined, page_size: 500 }),
  })
  const ejecuciones = useQuery({ queryKey: ['sw', 'ejecuciones'], queryFn: cmdbSoftwareApi.ejecuciones })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['sw'] })
  const importar = useMutation({ mutationFn: cmdbSoftwareApi.importarAvisos, onSuccess: r => { avisoImportacion(r.vulnerabilities ?? r); refrescar() }, onError: err })
  const sincronizar = useMutation({
    mutationFn: () => cmdbSoftwareApi.sincronizar(),
    onSuccess: r => {
      const fallos = r.sources.filter(s => s.status === 'error').map(s => e('fuente', s.source))
      toast.success(t('sw.sincronizado', { nuevos: r.findings_new, resueltos: r.findings_resolved }))
      if (fallos.length) toast.error(t('sw.fuentes_con_error', { fuentes: fallos.join(', ') }))
      refrescar()
    },
    // Sin fuentes activas no se avisa con un error suelto: sale el aviso contextual.
    onError: (x: unknown) => {
      if ((x as { response?: { data?: { code?: string } } })?.response?.data?.code === 'sw_fuente_desactivada') setSinFuentes(true)
      else err(x)
    },
  })
  const reevaluar = useMutation({ mutationFn: cmdbSoftwareApi.reevaluar, onSuccess: () => { toast.success(t('sw.reevaluado')); refrescar() }, onError: err })
  const exportar = useMutation({ mutationFn: () => descargar(cmdbSoftwareApi.exportarHallazgos(), `hallazgos-${hoy()}.csv`), onError: err })
  const c = cuadro.data
  const items = hallazgos.data?.items ?? []

  return (
    <div className="u-stack-20">
      {c && (
        <div className="ds-grid-stats">
          <KpiCard label={t('sw.kpi_hallazgos')} value={c.findings_live} icon={<ShieldAlert size={14} />} danger={c.findings_live > 0} />
          {(['critical', 'high', 'medium', 'low'] as Severidad[]).map(s => (
            <KpiCard key={s} label={e('sev', s)} value={c.findings_by_severity[s] ?? 0} danger={s === 'critical' && (c.findings_by_severity[s] ?? 0) > 0}
              warning={s === 'high' && (c.findings_by_severity[s] ?? 0) > 0} onClick={() => setSeveridad(severidad === s ? '' : s)} ariaLabel={t('sw.filtrar_por', { valor: e('sev', s) })} />
          ))}
          <KpiCard label={t('sw.kpi_fuera_sla')} value={c.findings_out_of_sla} danger={c.findings_out_of_sla > 0} onClick={() => setFueraSla(!fueraSla)} ariaLabel={t('sw.kpi_fuera_sla')} />
          <KpiCard label={t('sw.kpi_kev')} value={c.findings_kev} danger={c.findings_kev > 0} onClick={() => setKev(!kev)} ariaLabel={t('sw.kpi_kev')} />
          <KpiCard label={t('sw.kpi_posibles')} value={c.findings_possible ?? 0} onClick={() => setPosible(posible === 'true' ? '' : 'true')} ariaLabel={t('sw.kpi_posibles')} sub={t('sw.kpi_posibles_sub')} />
          <KpiCard label={t('sw.excepciones_pendientes')} value={c.exceptions.pending ?? 0} warning={(c.exceptions.pending ?? 0) > 0} sub={t('sw.excepciones_vigentes', { n: c.exceptions.approved ?? 0 })} />
        </div>
      )}

      {(sinFuentes || (c && c.sources_active && c.sources_active.length === 0)) && <AvisoDeConfiguracion>{t('sw.sin_fuentes_activas')}</AvisoDeConfiguracion>}

      <Section title={t('sw.hallazgos')} subtitle={t('sw.hallazgos_desc')}
        actions={<div className="u-wrap-8">
          {gestiona && <BotonFichero accept=".json,.csv,.xml,application/json,text/csv" icon={<FileUp size={14} />} loading={importar.isPending} onFichero={f => importar.mutate(f)}>{t('sw.importar_avisos')}</BotonFichero>}
          {gestiona && <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} loading={sincronizar.isPending} onClick={() => sincronizar.mutate()}>{t('sw.sincronizar')}</Button>}
          {gestiona && <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} loading={reevaluar.isPending} onClick={() => reevaluar.mutate()}>{t('sw.reevaluar')}</Button>}
          <Button size="sm" variant="ghost" icon={<Download size={14} />} loading={exportar.isPending} onClick={() => exportar.mutate()}>{t('sw.exportar_hallazgos')}</Button>
        </div>}>
        <div className="u-stack-12">
          {gestiona && <div className="u-text3-xs">{t('sw.importar_avisos_ayuda')}</div>}
          <div className="sdm-form">
            <Input label={t('sw.buscar')} value={q} placeholder={t('sw.hallazgos_ph')} onChange={ev => setQ(ev.target.value)} />
            <label className="sdm-field"><span>{t('sw.estado')}</span>
              <Select suelto placeholder={false} value={estado} onChange={ev => setEstado(ev.target.value)}>
                <option value={ESTADOS_ABIERTOS}>{t('sw.abiertos')}</option>
                <option value="">{t('sw.todos')}</option>
                {(meta.data?.finding_statuses ?? []).map(s => <option key={s} value={s}>{e('estado', s)}</option>)}
              </Select></label>
            <label className="sdm-field"><span>{t('sw.severidad')}</span>
              <Select suelto placeholder={false} value={severidad} onChange={ev => setSeveridad(ev.target.value)}>
                <Opciones valores={meta.data?.severities} catalogo="sev" todos={t('sw.todas')} /></Select></label>
            <label className="sdm-field"><span>{t('sw.posible_filtro')}</span>
              <Select suelto placeholder={false} value={posible} onChange={ev => setPosible(ev.target.value)}>
                <option value="">{t('sw.todos')}</option>
                <option value="true">{t('sw.posible_solo')}</option>
                <option value="false">{t('sw.posible_confirmados')}</option>
              </Select></label>
            <div className="u-wrap-10 sw-casillas">
              <Checkbox checked={kev} onChange={setKev} label={t('sw.solo_kev')} />
              <Checkbox checked={fueraSla} onChange={setFueraSla} label={t('sw.solo_fuera_sla')} />
            </div>
          </div>
          {hallazgos.isLoading ? <Spinner /> : items.length === 0 ? <EmptyState icon={<ShieldCheck size={28} />} title={t('sw.sin_hallazgos')} /> : (
            <TablaHallazgos hallazgos={items} onAbrir={h => setAbierto(h.id)} />
          )}
          {(hallazgos.data?.total ?? 0) > items.length && <div className="u-text3-xs">{t('sw.mostrando', { n: items.length, total: hallazgos.data?.total ?? 0 })}</div>}
        </div>
      </Section>

      <Excepciones />
      <Analisis />

      <Section title={t('sw.ejecuciones')} subtitle={t('sw.ejecuciones_desc')}>
        {ejecuciones.isLoading ? <Spinner size={16} /> : (ejecuciones.data ?? []).length === 0 ? <div className="u-text3-xs">{t('sw.sin_ejecuciones')}</div> : (
          <TablaSimple etiqueta={t('sw.ejecuciones')} densidad="compacta">
            <thead><tr><th>{t('sw.fuente')}</th><th>{t('sw.estado')}</th><th>{t('sw.inicio')}</th><th className="sw-num">{t('sw.consultas')}</th>
              <th className="sw-num">{t('sw.avisos')}</th><th className="sw-num">{t('sw.nuevos')}</th><th className="sw-num">{t('sw.resueltos')}</th><th>{t('sw.error')}</th></tr></thead>
            <tbody>{(ejecuciones.data ?? []).slice(0, 20).map(r => (
              <tr key={r.id}>
                <td>{e('fuente', r.source)}</td>
                <td><StatusBadge kind={r.status === 'ok' ? 'success' : r.status === 'error' ? 'danger' : 'info'} caps={false}>{e('ejec', r.status)}</StatusBadge></td>
                <td>{fmtDateTime(r.started_at)}</td>
                <td className="sw-num">{r.queries}</td><td className="sw-num">{r.vulnerabilities}</td>
                <td className="sw-num">{r.findings_new}</td><td className="sw-num">{r.findings_resolved}</td>
                <td className="u-text3-xs sdm-wrap">{r.error ?? ''}</td>
              </tr>
            ))}</tbody>
          </TablaSimple>
        )}
      </Section>

      {abierto && <DetalleDeHallazgo id={abierto} onClose={() => setAbierto(null)} />}
    </div>
  )
}

function Excepciones() {
  const t = useAppT()
  const e = useEtiquetaSw()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { puede } = useAuth()
  const aprueba = puede('software.aprobar')
  const [estado, setEstado] = useState('pending')
  const [abierto, setAbierto] = useState<string | null>(null)
  const { data, isLoading } = useQuery({ queryKey: ['sw', 'excepciones', estado], queryFn: () => cmdbSoftwareApi.excepciones(estado || undefined) })
  const hecho = () => { toast.success(t('sw.guardado')); qc.invalidateQueries({ queryKey: ['sw'] }) }
  const aprobar = useMutation({ mutationFn: ({ id, nota }: { id: string; nota?: string }) => cmdbSoftwareApi.aprobarExcepcion(id, nota), onSuccess: hecho, onError: err })
  const rechazar = useMutation({ mutationFn: ({ id, nota }: { id: string; nota?: string }) => cmdbSoftwareApi.rechazarExcepcion(id, nota), onSuccess: hecho, onError: err })
  const revocar = useMutation({ mutationFn: cmdbSoftwareApi.revocarExcepcion, onSuccess: hecho, onError: err })
  const nota = (titulo: string) => pedirTexto({ title: titulo, message: t('sw.nota_decision') })
  return (
    <Section title={t('sw.excepciones')} subtitle={t('sw.excepciones_desc')}
      actions={<Select suelto placeholder={false} className="sdm-select-accion" aria-label={t('sw.estado')} value={estado} onChange={ev => setEstado(ev.target.value)}>
        <option value="">{t('sw.todas')}</option>
        {['pending', 'approved', 'rejected', 'expired', 'revoked'].map(s => <option key={s} value={s}>{e('exc', s)}</option>)}
      </Select>}>
      {isLoading ? <Spinner size={16} /> : (data ?? []).length === 0 ? <div className="u-text3-xs">{t('sw.sin_excepciones')}</div> : (
        <ul className="sdm-list">
          {(data ?? []).map(x => (
            <li key={x.id} className="sdm-list__item">
              <div className="u-flex1-min0 u-stack-6">
                <div className="u-wrap-8">
                  <StatusBadge kind={EXCEPCION_KIND[x.status] ?? 'neutral'} caps={false}>{e('exc', x.status)}</StatusBadge>
                  {x.finding && <Button variant="link" className="sw-enlace u-mono" onClick={() => setAbierto(x.finding_id)}>{x.finding.vuln_id}</Button>}
                  {x.finding && <span className="u-text3-xs">{x.finding.product_name} {x.finding.affected_version ?? ''} · {x.finding.ci_name ?? ''}</span>}
                  {x.finding && <SeveridadBadge s={x.finding.severity} />}
                  {x.finding && <PosibleBadge posible={x.finding.possible} />}
                </div>
                <div className="u-text2-sm sdm-pre">{x.reason}</div>
                {x.compensating_controls && <div className="u-text3-xs sdm-pre">{t('sw.controles')}: {x.compensating_controls}</div>}
                <div className="u-text3-xs">{t('sw.caduca')}: {fmtDate(x.expires_at)}{x.decided_at ? ` · ${t('sw.decidida')}: ${fmtDate(x.decided_at)}` : ''}{x.decision_note ? ` · ${x.decision_note}` : ''}</div>
              </div>
              {aprueba && (
                <div className="u-actions-8">
                  {x.status === 'pending' && <>
                    <Button size="xs" variant="secondary" onClick={async () => { const n = await nota(t('sw.aprobar')); if (n !== null) aprobar.mutate({ id: x.id, nota: n || undefined }) }}>{t('sw.aprobar')}</Button>
                    <Button size="xs" variant="ghost" onClick={async () => { const n = await nota(t('sw.rechazar')); if (n !== null) rechazar.mutate({ id: x.id, nota: n || undefined }) }}>{t('sw.rechazar')}</Button>
                  </>}
                  {x.status === 'approved' && <Button size="xs" variant="ghost"
                    onClick={async () => { if (await confirmar({ message: t('sw.revocar_confirmar'), danger: true })) revocar.mutate(x.id) }}>{t('sw.revocar')}</Button>}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {abierto && <DetalleDeHallazgo id={abierto} onClose={() => setAbierto(null)} />}
    </Section>
  )
}

/** Análisis: fin de vida, deriva de configuración y licencias. */
function Analisis() {
  const t = useAppT()
  const e = useEtiquetaSw()
  const [vista, setVista] = useState<'eol' | 'deriva' | 'licencias'>('eol')
  const [soloProd, setSoloProd] = useState(false)
  const eol = useQuery({ queryKey: ['sw', 'eol', soloProd], queryFn: () => cmdbSoftwareApi.finDeVida({ prod_only: soloProd || undefined }), enabled: vista === 'eol' })
  const deriva = useQuery({ queryKey: ['sw', 'deriva'], queryFn: cmdbSoftwareApi.deriva, enabled: vista === 'deriva' })
  const licencias = useQuery({ queryKey: ['sw', 'licencias'], queryFn: cmdbSoftwareApi.licencias, enabled: vista === 'licencias' })
  return (
    <Section title={t('sw.analisis')} subtitle={t('sw.analisis_desc')}
      actions={<div className="u-wrap-6">
        {(['eol', 'deriva', 'licencias'] as const).map(v => (
          <Button key={v} size="xs" variant={vista === v ? 'primary' : 'secondary'} onClick={() => setVista(v)}>{t(`sw.analisis_${v}`)}</Button>
        ))}
      </div>}>
      {vista === 'eol' && (eol.isLoading ? <Spinner size={16} /> : eol.data && (
        <div className="u-stack-12">
          <div className="u-wrap-8">
            <StatusBadge kind="danger" caps={false}>{e('vida', 'eol')}: {eol.data.summary.eol}</StatusBadge>
            <StatusBadge kind="orange" caps={false}>{e('vida', 'unsupported')}: {eol.data.summary.unsupported}</StatusBadge>
            <StatusBadge kind="warning" caps={false}>{e('vida', 'soon')}: {eol.data.summary.soon}</StatusBadge>
            <Checkbox checked={soloProd} onChange={setSoloProd} label={t('sw.solo_produccion')} />
          </div>
          {eol.data.instances.length > 0 && <TablaInstancias instancias={eol.data.instances} conProducto />}
          {eol.data.components.length > 0 && (
            <TablaSimple etiqueta={t('sw.componentes')} densidad="compacta">
              <thead><tr><th>{t('sw.componente')}</th><th>{t('sw.version')}</th><th>{t('sw.dentro_de_col')}</th><th>{t('sw.ciclo_vida')}</th><th>{t('sw.fin_vida')}</th></tr></thead>
              <tbody>{eol.data.components.map(c => (
                <tr key={c.component_id}><td>{c.name}</td><td><VersionTexto v={c.version} /></td>
                  <td>{c.parent_product_name} <span className="u-mono u-text3-xs">{c.parent_version ?? ''}</span></td>
                  <td><CicloBadge c={c.lifecycle} /></td><td>{fmtDate(c.eol_date ?? c.support_end)}</td></tr>
              ))}</tbody>
            </TablaSimple>
          )}
          {eol.data.instances.length + eol.data.components.length === 0 && <div className="u-text3-xs">{t('sw.sin_eol')}</div>}
        </div>
      ))}
      {vista === 'deriva' && (deriva.isLoading ? <Spinner size={16} /> : deriva.data && (
        <div className="u-stack-12">
          {deriva.data.drift.length + deriva.data.violations.length === 0 && <div className="u-text3-xs">{t('sw.sin_deriva')}</div>}
          {deriva.data.drift.length > 0 && (
            <ul className="sdm-list">{deriva.data.drift.map(i => (
              <li key={i.id} className="sdm-list__item"><div className="u-flex1-min0">
                <div className="u-wrap-8"><span className="u-text1-sm-600">{i.product_name ?? i.name}</span><span className="u-text3-xs">{i.ci_name ?? ''}</span>
                  <StatusBadge kind="warning" caps={false}>{t('sw.deriva_desde', { fecha: fmtDate(i.drift_detected_at) })}</StatusBadge></div>
                <div className="u-text3-xs">{t('sw.claves_cambiadas')}: <span className="u-mono">{i.changed_keys.join(', ') || '—'}</span></div>
              </div></li>
            ))}</ul>
          )}
          {deriva.data.violations.length > 0 && (
            <ul className="sdm-list">{deriva.data.violations.map(v => (
              <li key={`${v.instance_id}-${v.baseline_id}`} className="sdm-list__item"><div className="u-flex1-min0 u-stack-6">
                <div className="u-wrap-8"><span className="u-text1-sm-600">{v.product_name ?? v.instance_name}</span><span className="u-text3-xs">{v.ci_name ?? ''} · {e('entorno', v.environment)}</span>
                  <StatusBadge caps={false} kind={v.baseline_approved ? 'success' : 'neutral'}>{v.baseline_name}</StatusBadge></div>
                <ul className="sw-incumplimientos">{v.violations.map((x, k) => (
                  <li key={k}><span className="u-mono">{x.key}</span> {e('op', x.op)} <span className="u-mono">{valorLegible(x.expected)}</span> · {t('sw.actual')}: <span className="u-mono">{valorLegible(x.actual)}</span> <SeveridadBadge s={x.severity} /></li>
                ))}</ul>
              </div></li>
            ))}</ul>
          )}
        </div>
      ))}
      {vista === 'licencias' && (licencias.isLoading ? <Spinner size={16} /> : licencias.data && (
        <div className="u-stack-12">
          <div className="u-wrap-8">
            {Object.entries(licencias.data.by_family).map(([f, n]) => <StatusBadge key={f} caps={false}>{e('familia', f)}: {n}</StatusBadge>)}
          </div>
          {licencias.data.issues.length === 0 ? <div className="u-text3-xs">{t('sw.sin_problemas_licencia')}</div> : (
            <TablaSimple etiqueta={t('sw.analisis_licencias')} densidad="compacta">
              <thead><tr><th>{t('sw.componente')}</th><th>{t('sw.licencia')}</th><th>{t('sw.nivel')}</th><th>{t('sw.motivo')}</th><th>{t('sw.dentro_de_col')}</th></tr></thead>
              <tbody>{licencias.data.issues.map(x => (
                <tr key={x.component_id}>
                  <td>{x.name} <span className="u-text3-xs"><VersionTexto v={x.version} /></span></td>
                  <td className="u-mono">{x.license ?? '—'}<div className="u-text3-xs">{e('familia', x.family)}</div></td>
                  <td><StatusBadge kind={x.level === 'conflict' ? 'danger' : 'warning'} caps={false}>{e('nivel_lic', x.level)}</StatusBadge></td>
                  <td>{e('motivo_lic', x.reason)}</td>
                  <td>{x.parent_product_name} <span className="u-mono u-text3-xs">{x.parent_version ?? ''}</span>{x.parent_distribution && <div className="u-text3-xs">{e('dist', x.parent_distribution)}</div>}</td>
                </tr>
              ))}</tbody>
            </TablaSimple>
          )}
        </div>
      ))}
    </Section>
  )
}
