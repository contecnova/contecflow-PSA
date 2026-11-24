import { useState, lazy, Suspense, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { cmdbApi } from '../services/api'
import { Buscador, Button, Spinner, Tabs, KpiCard, EmptyState, IconButton, Pulsable, Select, TablaSimple } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Bot, Box, Database, Gauge, History, Link2, ListTree, Network, Package, Pencil, Plus, Radar, Search, Server, ShieldAlert, Shapes, Trash2, X, Zap } from 'lucide-react'
import { IconoCi } from '../components/cmdb/iconosCi'
import { useAppT } from '../i18n/AppLangContext'
import { useAuth } from '../context/AuthContext'
// Solo tipos: se borran al compilar y no rompen la carga diferida del grafo.
import type { RawNode, RawEdge } from '../components/cmdb/CMDBTopologyGraph'
import { FULL_LIST_SIZE } from '../constants/pagination'
import './CMDBPage.css'
import { ClasesPropiasTab, DescubrimientoTab, ImpactoTab } from '../components/cmdb/CmdbMercado'
import { type CI, CI_TYPES, ENV_COLOR, STATUS_COLOR, chip, useCamposDeClase, useEtiqueta, useEtiquetaDeCampo } from './CMDBComun'
import { CMDBItemForm } from './CMDBFormulario'
import { CILinkedAssets, ChangelogModal, RelLinea, RelationsModal, useRelaciones } from './CMDBRelaciones'
import { CMDBAgentsTab, ClasesTab, Red } from './CMDBAgentesYClases'
// CMDB de software y vulnerabilidades (19-11-2026): cuatro pestañas para quien tiene `software.ver`;
// se cargan al abrirlas (docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md).
const SoftwareTab = lazy(() => import('../components/cmdb/software/SoftwareTabs').then(m => ({ default: m.SoftwareTab })))
const DondeSeUsaTab = lazy(() => import('../components/cmdb/software/SoftwareTabs').then(m => ({ default: m.DondeSeUsaTab })))
const PorMaquinaTab = lazy(() => import('../components/cmdb/software/SoftwareTabs').then(m => ({ default: m.PorMaquinaTab })))
const VulnerabilidadesTab = lazy(() => import('../components/cmdb/software/SoftwareTabs').then(m => ({ default: m.VulnerabilidadesTab })))
// Índice de riesgo y gestión de vulnerabilidades (22-11-2026, §11 del mismo documento).
const RiesgoTab = lazy(() => import('../components/cmdb/software/riesgo/RiesgoTab').then(m => ({ default: m.RiesgoTab })))
// Auditoría 2026-08 (hallazgo 19). Este import era ESTÁTICO, y
// CMDBTopologyGraph depende de react-plotly.js → plotly.js. Medido sobre el
// build: eso ponía un import estático de `vendor-plotly` (4.633 kB, el 38 % de
// todo el JS) en el chunk `route-misc`, así que abrir CUALQUIER página de ese
// chunk descargaba plotly entero aunque no mostrase ninguna gráfica.
//
// Con `lazy` se paga sólo al abrir la pestaña de topología, que es cuando de
// verdad hace falta. Es el mismo patrón que ya usaba `charts/DynamicChart` para
// las otras cuatro gráficas de plotly.
//
// Actualización 2026-09: esos 4.633 kB son ahora **1.563 kB** (gzip 510). No se
// tocó nada de esta página: el chunk adelgazó porque plotly dejó de venir
// entero. `src/charts/PlotlyCustom.ts` registra sólo las cuatro trazas que la
// aplicación dibuja, y con ello salió del bundle `maplibre-gl`, que traía dos
// avisos **críticos** de `npm audit` por una librería de mapas que aquí no se
// usa. El `lazy` de arriba sigue mereciendo la pena; simplemente ya no esconde
// tanto.
//
// Actualización 2026-11 (#31): la vista 3D ya no usa plotly (es SVG) y plotly
// salió del proyecto; el `lazy` se mantiene igual.
const CMDBTopologyGraph = lazy(() => import('../components/cmdb/CMDBTopologyGraph'))
// Mismo caso que arriba: sólo se usa en la pestaña 3D y arrastraba
// `vendor-d3` (130 kB) al chunk de la ruta.
const Cmdb3dGraph = lazy(() => import('../components/servicedesk/Cmdb3dGraph'))

export default function CMDBPage(): JSX.Element {
  const idFila = useId()
  const t = useAppT()
  const etiqueta = useEtiqueta()
  const { data: deClase } = useCamposDeClase()
  const etiquetaDeCampo = useEtiquetaDeCampo()
  const { puede } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<CI | null>(null)
  const [relItem, setRelItem] = useState<CI | null>(null)
  const [historyItem, setHistoryItem] = useState<CI | null>(null)
  const [filterType, setFilterType] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [searchQ, setSearchQ] = useState('')
  const [sortKey, setSortKey] = useState('name')
  const [sortDir, setSortDir] = useState('asc')
  const [tab, setTab] = useState('list')  // 'list' | 'topology' | '3d' | 'agents'
  const [topoCI, setTopoCI] = useState<CI | null>(null)
  const [topoRadius, setTopoRadius] = useState(2)
  const [drillCI, setDrillCI] = useState<CI | null>(null)

  const toggleSort = (key: string) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const { data: drillRels = [] } = useRelaciones(drillCI?.id)

  // Todos los CIs, sin filtros: alimentan los contadores, los selectores de
  // relación y de topología, y el nombre del CI de cada agente.
  const { data: todos = [] } = useQuery<CI[]>({
    queryKey: ['cmdb-items', 'todos'],
    queryFn: () => cmdbApi.sdList({ page_size: FULL_LIST_SIZE }).then(r => r.data ?? []),
  })
  // Segunda auditoría 2026-11: el error se pinta en la tabla (no aviso global).
  const { data: items = [], isLoading, isError: itemsFailed, error: itemsError } = useQuery<CI[]>({
    queryKey: ['cmdb-items', filterType, filterStatus, searchQ],
    meta: { errorToast: false },
    queryFn: () => {
      const p: Record<string, string | number> = { page_size: FULL_LIST_SIZE }
      if (filterType)   p.ci_type = filterType
      if (filterStatus) p.status  = filterStatus
      if (searchQ)      p.q       = searchQ
      return cmdbApi.sdList(p).then(r => r.data ?? [])
    },
  })

  const { mutate: deleteItem } = useMutation({
    mutationFn: (id: string) => cmdbApi.sdDelete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['cmdb-items'] }),
    onError: e => toast.error(extractErr(e, t('cmdb.delete_error'))),
  })

  const typeCounts = CI_TYPES.reduce((acc: Record<string, number>, c) => ({...acc, [c]: todos.filter(i => i.ci_type === c).length}), {})

  const sortedItems = [...items].sort((a, b) => {
    const va = a[sortKey] ?? ''
    const vb = b[sortKey] ?? ''
    const cmp = typeof va === 'number' ? va - (vb as number) : String(va).localeCompare(String(vb))
    return sortDir === 'asc' ? cmp : -cmp
  })

  const { data: topoData, isFetching: topoLoading } = useQuery<{ nodes: RawNode[]; edges: RawEdge[] }>({
    queryKey: ['cmdb-topology', topoCI?.id, topoRadius],
    queryFn: () => topoCI
      ? cmdbApi.topology(topoCI.id, topoRadius).then(r => r.data)
      : Promise.resolve({ nodes: [], edges: [] }),
    enabled: tab === 'topology' && !!topoCI,
  })

  const columnas: [string, string][] = [['name','ci_name'],['ci_type','ci_type'],['status','status'],['environment','environment'],['hostname','network'],['version','f_version']]
  const newCiButton = (
    <Button icon={<Plus size={14} />} onClick={() => { setEditing(null); setShowForm(true) }}>{t('cmdb.new_ci')}</Button>
  )

  return (
    <PageShell>
      <PageHeader icon={<Database size={18} />} title={t('nav.cmdb')} subtitle={t('cmdb.subtitle')}
        actions={newCiButton} />
      <div className="ds-page">

      <Tabs
        items={[
          { id: 'list',     label: t('cmdb.tab_inventory'), icon: <ListTree size={14} /> },
          { id: 'topology', label: t('cmdb.tab_topology'), icon: <Network size={14} /> },
          { id: '3d',       label: t('cmdb.tab_3d'), icon: <Box size={14} /> },
          { id: 'impact',   label: t('sd_mercado.tab_impacto'), icon: <Zap size={14} /> },
          ...(puede('software.ver') ? [
            { id: 'software', label: t('sw.tab_software'), icon: <Package size={14} /> },
            { id: 'where', label: t('sw.tab_donde'), icon: <Search size={14} /> },
            { id: 'machine', label: t('sw.tab_maquina'), icon: <Server size={14} /> },
            { id: 'vulns', label: t('sw.tab_vulns'), icon: <ShieldAlert size={14} /> },
            { id: 'risk', label: t('swr.tab_riesgo'), icon: <Gauge size={14} /> },
          ] : []),
          // Agentes y clases son de admin en el servidor (revisión 2026-11: pm veía Agentes y recibía 403).
          ...(puede('org.administrar') ? [{ id: 'agents', label: t('cmdb.tab_agents'), icon: <Bot size={14} /> }, { id: 'classes', label: t('cmdb.tab_classes'), icon: <Shapes size={14} /> },
            { id: 'ci_classes', label: t('sd_mercado.tab_clases_propias'), icon: <Shapes size={14} /> }, { id: 'discovery', label: t('sd_mercado.tab_descubrimiento'), icon: <Radar size={14} /> }] : []),
        ]}
        active={tab}
        onChange={setTab}
        ariaLabel="CMDB"
      />

      {/* ─── TOPOLOGÍA ─────────────────────────────────────────────── */}
      {tab === 'topology' && (
        <div className="cmdb-topo">
          <div className="cmdb-panel cmdb-panel--topo">
            <div className="cmdb-topo__filters">
              <div className="cmdb-topo__ci">
                <Select label={t('cmdb.central_ci')} placeholder={false} id="topo-ci" value={topoCI?.id || ''} onChange={e => {
                  setTopoCI(todos.find(i => i.id === e.target.value) || null)
                  setDrillCI(null)
                }}>
                  <option value="">{t('cmdb.select_ci')}</option>
                  {todos.map(ci => <option key={ci.id} value={ci.id}>{ci.name}</option>)}
                </Select>
              </div>
              <Select label={t('cmdb.radio_de_expansion')} placeholder={false} id="topo-radius" value={topoRadius} onChange={e => setTopoRadius(Number(e.target.value))}>
                  {[1,2,3].map(r => <option key={r} value={r}>{t('cmdb.levels', { n: r })}</option>)}
                </Select>
              {topoCI && (
                <Button variant="secondary" onClick={() => { setTopoCI(null); setDrillCI(null) }}>{t('cmdb.clear')}</Button>
              )}
            </div>
            {topoLoading
              ? <Spinner />
              : <Suspense fallback={<Spinner />}>
                  <CMDBTopologyGraph
                    nodes={topoData?.nodes || []}
                    edges={topoData?.edges || []}
                    centerName={topoCI?.name}
                    onNodeClick={(n: CI) => setDrillCI(todos.find(i => i.id === n.id) || n)}
                  />
                </Suspense>
            }
          </div>

          {drillCI && (
            <section className="cmdb-drill" aria-label={drillCI.name ?? ''}>
              <div className="cmdb-drill__head">
                <div className="u-row-center-8">
                  <span className="cmdb-drill__icon"><IconoCi tipo={drillCI.ci_type} size={20} /></span>
                  <div className="u-min0">
                    <div className="cmdb-drill__name">{drillCI.name}</div>
                    <div className="u-text2-xs">{drillCI.code} · {etiqueta('type_', drillCI.ci_type)}</div>
                  </div>
                </div>
                <IconButton onClick={() => setDrillCI(null)} ariaLabel={t('cmdb.cerrar_panel_de_detalle')}><X size={16} /></IconButton>
              </div>

              <div className="u-wrap-8">
                {drillCI.status && <span className="cmdb-chip" style={chip(STATUS_COLOR[drillCI.status] || 'var(--text-2)')}>{etiqueta('st_', drillCI.status)}</span>}
                {drillCI.environment && <span className="cmdb-chip" style={chip(ENV_COLOR[drillCI.environment] || 'var(--text-2)')}>{etiqueta('env_', drillCI.environment)}</span>}
                {drillCI.is_discovered && <span className="cmdb-chip" style={chip('var(--accent)')}>{t('cmdb.discovered', { provider: drillCI.discovery_provider ?? '' })}</span>}
                {drillCI.drift_detected_at && <span className="cmdb-chip" style={chip('var(--warning)')}>{t('cmdb.drift')}</span>}
              </div>

              {drillCI.description && (
                <div className="cmdb-drill__desc">{drillCI.description}</div>
              )}

              <div className="cmdb-divided">
                <div className="cmdb-section-title">
                  {t('cmdb.attributes')}
                </div>
                <div className="cmdb-attrs">
                  {([
                    ['hostname', drillCI.hostname], ['ip_address', drillCI.ip_address], ['version', drillCI.version],
                    ...Object.entries(drillCI.attributes || {}).filter(([, v]) => typeof v !== 'object'),
                  ] as [string, unknown][]).filter(([, v]) => v !== null && v !== undefined && v !== '').map(([k, value]) => {
                    const campo = deClase?.clases[drillCI.ci_type ?? '']?.find(c => c.key === k) ?? { key: k, field_type: 'text' }
                    return (
                      <div key={k} className="cmdb-attr">
                        <span className="cmdb-attr__key">{etiquetaDeCampo(campo)}</span>
                        <span className="cmdb-attr__val" title={String(value)}>{String(value)}</span>
                      </div>
                    )
                  })}
                </div>
              </div>

              {drillRels.length > 0 && (
                <div className="cmdb-divided">
                  <div className="cmdb-section-title">
                    {t('cmdb.relationships')}
                  </div>
                  {drillRels.map(r => (
                    <div key={r.id} className="cmdb-drill__rel">
                      <RelLinea r={r} ciId={drillCI.id} />
                    </div>
                  ))}
                </div>
              )}

              <CILinkedAssets ciId={drillCI.id} />

              <div className="cmdb-drill__actions">
                <Button onClick={() => { setTopoCI(drillCI); setDrillCI(null) }}>{t('cmdb.ver_como_ci_central')}</Button>
                <Button variant="secondary" onClick={() => { setEditing(drillCI); setShowForm(true) }}>{t('cmdb.edit_ci')}</Button>
              </div>
            </section>
          )}
        </div>
      )}

      {/* ─── INVENTARIO ─────────────────────────────────────────────── */}
      {tab === 'list' && <>
      <div className="ds-grid-stats">
        <KpiCard label={t('cmdb.kpi_total')} value={todos.length} icon={<Database size={14} />} />
        {Object.keys(STATUS_COLOR).map(s => {
          const n = todos.filter(i => i.status === s).length
          return <KpiCard key={s} label={etiqueta('st_', s)} value={n}
            danger={STATUS_COLOR[s] === 'var(--danger)' && n > 0} warning={STATUS_COLOR[s] === 'var(--warning)' && n > 0} />
        })}
      </div>

      <div className="cmdb-panel cmdb-panel--mb">
        <div className="cmdb-filters">
          <div className="cmdb-filters__q">
            <Buscador label={t('cmdb.search')} id="cmdb-q" value={searchQ} onChange={setSearchQ} placeholder={t('cmdb.search_ph')} />
          </div>
          <Select label={t('cmdb.ci_type')} placeholder={false} id="cmdb-type" value={filterType} onChange={e => setFilterType(e.target.value)}>
              <option value="">{t('cmdb.todos_los_tipos')}</option>
              {CI_TYPES.map(c => <option key={c} value={c}>{etiqueta('type_', c)} ({typeCounts[c]||0})</option>)}
            </Select>
          <Select label={t('cmdb.status')} placeholder={false} id="cmdb-status" value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
              <option value="">{t('cmdb.todos')}</option>
              {Object.keys(STATUS_COLOR).map(v => <option key={v} value={v}>{etiqueta('st_', v)}</option>)}
            </Select>
          {(filterType||filterStatus||searchQ) && (
            <Button variant="secondary" onClick={() => {setFilterType('');setFilterStatus('');setSearchQ('')}}>{t('cmdb.clear')}</Button>
          )}
        </div>
      </div>

      {isLoading ? <Spinner /> : itemsFailed ? (
        <div role="alert" className="u-danger">{extractErr(itemsError, t('toast.load_error'))}</div>
      ) : items.length === 0 ? (
        <EmptyState icon={<Database size={28} />} title={todos.length ? t('cmdb.no_match') : t('cmdb.no_cis')}
          description={todos.length ? undefined : t('cmdb.registra_servidores_aplicaciones_bases_de_datos_y')}
          action={todos.length ? undefined : newCiButton} />
      ) : (
        <div className="cmdb-panel cmdb-panel--scroll">
          <TablaSimple claseTabla="cmdb-table">
            <thead>
              <tr className="u-border-b">
              {columnas.map(([key, label]) => (
                <th key={key} aria-sort={sortKey === key ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  className="cmdb-th-sort">
                  <Pulsable type="button" onClick={() => toggleSort(key)}
                    className={`cmdb-sort-btn${sortKey === key ? ' is-active' : ''}`}>
                    {t(`cmdb.${label}`)}{sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
                  </Pulsable>
                </th>
              ))}
              <th className="cmdb-th-pad"><span className="u-sr-only">{t('cmdb.actions')}</span></th>
              </tr>
            </thead>
            <tbody>
              {sortedItems.map(item => (
                  <tr key={item.id} className="u-border-b">
                    <td className="u-pad-10-12" aria-labelledby={`${idFila}-${item.id}-n ${idFila}-${item.id}-c`}>
                      <div className="u-row-center-8">
                        <span className="cmdb-row-icon"><IconoCi tipo={item.ci_type} size={16} /></span>
                        <div className="u-min0">
                          <div id={`${idFila}-${item.id}-n`} className="u-600">{item.name}</div>
                          <div id={`${idFila}-${item.id}-c`} className="u-text2-xs">
                            {item.code}{item.is_discovered ? ` · ${t('cmdb.discovered', { provider: item.discovery_provider ?? '' })}` : ''}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="cmdb-cell">{etiqueta('type_', item.ci_type)}</td>
                    <td className="u-pad-10-12">
                      <span className="cmdb-chip" style={chip(STATUS_COLOR[item.status ?? ''] || 'var(--text-2)')}>{etiqueta('st_', item.status)}</span>
                      {item.drift_detected_at && <span className="cmdb-chip cmdb-chip--gap" style={chip('var(--warning)')}>{t('cmdb.drift')}</span>}
                    </td>
                    <td className="u-pad-10-12">
                      {item.environment ? <span className="cmdb-chip" style={chip(ENV_COLOR[item.environment] || 'var(--text-2)')}>{etiqueta('env_', item.environment)}</span> : '—'}
                    </td>
                    <td className="cmdb-cell"><Red item={item} /></td>
                    <td className="cmdb-cell cmdb-cell--mono">{item.version||'—'}</td>
                    <td className="u-pad-10-12">
                      <div className="u-row-6">
                        <IconButton onClick={() => setHistoryItem(item)} ariaLabel={t('cmdb.ver_historial_de_cambios')}><History size={14} /></IconButton>
                        <IconButton onClick={() => setRelItem(item)} ariaLabel={t('cmdb.relationships')}><Link2 size={14} /></IconButton>
                        <IconButton variante="caja" onClick={() => { setEditing(item); setShowForm(true) }} ariaLabel={t('cmdb.edit_ci')}><Pencil size={14} /></IconButton>
                        <IconButton variante="caja" tono="peligro" onClick={() => openConfirmGlobal({ message: t('cmdb.delete_ci_q', { name: item.name ?? '' }), onConfirm: () => deleteItem(item.id), danger: true })} ariaLabel={t('cmdb.delete_ci')}><Trash2 size={14} /></IconButton>
                      </div>
                    </td>
                  </tr>
              ))}
            </tbody>
          </TablaSimple>
        </div>
      )}
      </>}

      {showForm && <CMDBItemForm item={editing} onClose={() => { setShowForm(false); setEditing(null) }} />}
      {relItem && <RelationsModal item={relItem} allItems={todos} onClose={() => setRelItem(null)} />}
      {historyItem && <ChangelogModal item={historyItem} onClose={() => setHistoryItem(null)} />}

      {tab === '3d' && (
        <Suspense fallback={<Spinner />}>
          <Cmdb3dGraph />
        </Suspense>
      )}

      {tab === 'agents' && <CMDBAgentsTab items={todos} />}

      {tab === 'classes' && <ClasesTab />}
      {tab === 'ci_classes' && <ClasesPropiasTab />}
      {tab === 'discovery' && <DescubrimientoTab />}
      {tab === 'impact' && <ImpactoTab />}
      {puede('software.ver') && ['software', 'where', 'machine', 'vulns', 'risk'].includes(tab) && (
        <Suspense fallback={<Spinner />}>
          {tab === 'software' && <SoftwareTab />}
          {tab === 'where' && <DondeSeUsaTab />}
          {tab === 'machine' && <PorMaquinaTab />}
          {tab === 'vulns' && <VulnerabilidadesTab />}
          {tab === 'risk' && <RiesgoTab />}
        </Suspense>
      )}
      </div>
    </PageShell>
  )
}
