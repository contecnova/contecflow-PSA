import { useState, lazy, Suspense, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, fmtDateTime } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { cmdbApi } from '../services/api'
import { Button, Spinner, Modal, Tabs } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Database } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { useAuth } from '../context/AuthContext'
// Solo tipos: se borran al compilar y no rompen la carga diferida del grafo.
import type { RawNode, RawEdge } from '../components/cmdb/CMDBTopologyGraph'
import { POLL_LIVE_MS, STALE_DEFAULT_MS, STALE_SHORT_MS } from '../constants/timings'
import { FULL_LIST_SIZE } from '../constants/pagination'
import './CMDBPage.css'
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

// Auditoría 2026-11: esta pantalla editaba `cmdb_items`, una segunda CMDB que
// los tickets no veían. Ahora trabaja sobre `/sd/cmdb`, la misma que eligen
// tickets, problemas y cambios, y que alimenta el descubrimiento.

/** Color de la etiqueta (dato): lo consume `.cmdb-chip` vía `--cmdb-chip`. */
const chip = (color: string): CSSProperties => ({ '--cmdb-chip': color } as CSSProperties)

type CI = {
  id: string; code?: string; name?: string; ci_type?: string; status?: string
  environment?: string; description?: string; hostname?: string; ip_address?: string; version?: string
  criticality?: string; attributes?: Record<string, unknown>; is_discovered?: boolean
  discovery_provider?: string; drift_detected_at?: string
}

// Las clases de `CIType` en el servidor (app/models/service_desk/_enums.py).
const CI_TYPES = ['server','virtual_machine','application','database','network','service','container','cloud','endpoint','storage','module','integration','other']
const CI_TYPE_ICONS: Record<string, string> = {server:'🖥️',virtual_machine:'🧊',application:'📱',database:'🗄️',network:'🌐',service:'⚙️',container:'📦',cloud:'☁️',endpoint:'💻',storage:'💾',module:'🧩',integration:'🔌',other:'📌'}

// Atributos propios de cada clase; se guardan en `attributes`. Host, IP y
// versión son columnas comunes a todas y van aparte. Auditoría 2026-11:
// estaban escritos aquí; ahora los configura cada organización (pestaña
// «Clases») y los de fábrica viven en el servidor (cmdb_clases.py).
type Campo = { key: string; label?: string | null; field_type: string }
type CamposDeClase = { por_defecto: boolean; clases: Record<string, Campo[]> }

function useCamposDeClase() {
  return useQuery<CamposDeClase>({
    queryKey: ['cmdb-class-fields'],
    queryFn: () => cmdbApi.classFields().then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })
}

/** La etiqueta escrita por la organización o, si no hay, la traducida de fábrica. */
function useEtiquetaDeCampo() {
  const t = useAppT()
  return (c: Campo) => {
    if (c.label) return c.label
    const texto = t(`cmdb.f_${c.key}`)
    return texto === `cmdb.f_${c.key}` ? c.key : texto
  }
}
const STATUS_COLOR: Record<string, string> = { operational:'var(--success)', degraded:'var(--orange)', maintenance:'var(--warning)', retired:'var(--text-2)' }
const ENV_COLOR: Record<string, string> = { production:'var(--danger)', staging:'var(--warning)', test:'var(--purple)', development:'var(--accent)' }
const CRITICALITIES = ['low','medium','high','critical']
const REL_TYPES = ['depends_on','hosts','connects_to','backed_up_by','monitored_by','part_of']

/** Una clave de i18n que puede no existir: si no, el valor tal cual. */
function useEtiqueta() {
  const t = useAppT()
  return (prefijo: string, valor?: string) => {
    if (!valor) return '—'
    const clave = `cmdb.${prefijo}${valor}`
    const texto = t(clave)
    return texto === clave ? valor : texto
  }
}

function CMDBItemForm({ item, onClose }: { item: CI | null; onClose: () => void }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!item?.id
  const [form, setForm] = useState<Record<string, string>>({
    name:        item?.name        || '',
    ci_type:     item?.ci_type     || 'server',
    status:      item?.status      || 'operational',
    environment: item?.environment || 'production',
    criticality: item?.criticality || 'medium',
    description: item?.description || '',
    ip_address:  item?.ip_address  || '',
    hostname:    item?.hostname    || '',
    version:     item?.version     || '',
  })
  const [attrs, setAttrs] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(item?.attributes || {}).map(([k, v]) => [k, String(v ?? '')])))
  const set = (k: string) => (v: string) => setForm(f => ({ ...f, [k]: v }))
  const { data: deClase } = useCamposDeClase()
  const etiquetaDeCampo = useEtiquetaDeCampo()
  const campos = deClase?.clases[form.ci_type] ?? []

  const { mutate, isPending } = useMutation({
    mutationFn: (): Promise<unknown> => {
      // Se envían solo los atributos de la clase elegida y con valor: cambiar
      // de clase no arrastra los de la anterior.
      const propios = Object.fromEntries(campos.map(c => [c.key, attrs[c.key]]).filter(([, v]) => v))
      const vacio = (v: string) => v.trim() || null
      const d = { ...form, description: vacio(form.description), ip_address: vacio(form.ip_address),
        hostname: vacio(form.hostname), version: vacio(form.version), attributes: propios }
      return isEdit ? cmdbApi.sdUpdate(item.id, d) : cmdbApi.sdCreate(d)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cmdb-items'] }); onClose() },
    onError: e => toast.error(extractErr(e, t('cmdb.save_error'))),
  })

  const etiqueta = useEtiqueta()
  const id = (k: string) => `ci-form-${k}`
  return (
    <Modal open onClose={onClose} title={isEdit ? t('cmdb.edit_ci') : t('cmdb.new_ci')}>
      <div className="u-stack-14">
        <div className="cmdb-grid cmdb-grid--wide">
          <div>
            <label id={`${id('name')}-et`} className="cmdb-label" htmlFor={id('name')}>{t('cmdb.ci_name')}</label>
            <input id={id('name')} aria-labelledby={`${id('name')}-et`} className="cmdb-input" value={form.name} onChange={e => set('name')(e.target.value)} />
          </div>
          <div>
            <label id={`${id('type')}-et`} className="cmdb-label" htmlFor={id('type')}>{t('cmdb.ci_type')}</label>
            <select id={id('type')} className="cmdb-input" value={form.ci_type} onChange={e => set('ci_type')(e.target.value)}>
              {CI_TYPES.map(c => <option key={c} value={c}>{CI_TYPE_ICONS[c]} {etiqueta('type_', c)}</option>)}
            </select>
          </div>
        </div>
        <div className="cmdb-grid">
          <div>
            <label id={`${id('status')}-et`} className="cmdb-label" htmlFor={id('status')}>{t('cmdb.status')}</label>
            <select id={id('status')} className="cmdb-input" value={form.status} onChange={e => set('status')(e.target.value)}>
              {Object.keys(STATUS_COLOR).map(v => <option key={v} value={v}>{etiqueta('st_', v)}</option>)}
            </select>
          </div>
          <div>
            <label id={`${id('env')}-et`} className="cmdb-label" htmlFor={id('env')}>{t('cmdb.environment')}</label>
            <select id={id('env')} className="cmdb-input" value={form.environment} onChange={e => set('environment')(e.target.value)}>
              {Object.keys(ENV_COLOR).map(v => <option key={v} value={v}>{etiqueta('env_', v)}</option>)}
            </select>
          </div>
          <div>
            <label id={`${id('crit')}-et`} className="cmdb-label" htmlFor={id('crit')}>{t('cmdb.criticality')}</label>
            <select id={id('crit')} className="cmdb-input" value={form.criticality} onChange={e => set('criticality')(e.target.value)}>
              {CRITICALITIES.map(v => <option key={v} value={v}>{etiqueta('crit_', v)}</option>)}
            </select>
          </div>
        </div>
        <div className="cmdb-grid">
          {(['hostname','ip_address','version'] as const).map(k => (
            <div key={k}>
              <label id={`${id(k)}-et`} className="cmdb-label" htmlFor={id(k)}>{t(`cmdb.f_${k}`)}</label>
              <input id={id(k)} aria-labelledby={`${id(k)}-et`} className="cmdb-input" value={form[k]} onChange={e => set(k)(e.target.value)} />
            </div>
          ))}
        </div>
        <div>
          <div className="cmdb-section-title cmdb-section-title--mb10">
            {CI_TYPE_ICONS[form.ci_type]} {t('cmdb.class_fields', { type: etiqueta('type_', form.ci_type) })}
          </div>
          <div className="cmdb-grid cmdb-grid--wide cmdb-grid--gap10">
            {campos.map(c => (
              <div key={c.key}>
                <label id={`${id(c.key)}-et`} className="cmdb-label" htmlFor={id(c.key)}>{etiquetaDeCampo(c)}</label>
                <input id={id(c.key)} aria-labelledby={`${id(c.key)}-et`} className="cmdb-input" type={c.field_type || 'text'} value={attrs[c.key] ?? ''}
                  onChange={e => setAttrs(a => ({ ...a, [c.key]: e.target.value }))} />
              </div>
            ))}
          </div>
        </div>
        <div>
          <label id={`${id('descr')}-et`} className="cmdb-label" htmlFor={id('descr')}>{t('cmdb.descripcion')}</label>
          <textarea id={id('descr')} aria-labelledby={`${id('descr')}-et`} className="cmdb-input" value={form.description} onChange={e => set('description')(e.target.value)} />
        </div>
        <div className="cmdb-form-actions">
          <Button variant="secondary" onClick={onClose}>{t('cmdb.cancel')}</Button>
          <Button onClick={() => mutate()} disabled={isPending || !form.name.trim()} loading={isPending}>
            {isEdit ? t('cmdb.save') : t('cmdb.create')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

type Rel = { id: string; relation_type: string; source: { id: string; name: string; type: string }; target: { id: string; name: string; type: string } }

/** Una relación leída desde un CI: `hosts` de A a B se lee «A aloja a B». */
function RelLinea({ r, ciId }: { r: Rel; ciId: string }) {
  const t = useAppT()
  const etiqueta = useEtiqueta()
  const sale = r.source.id === ciId
  const otro = sale ? r.target : r.source
  return (
    <span className="cmdb-rel-text">
      {sale
        ? <>{etiqueta('rel_', r.relation_type)} <strong className="u-text1">{CI_TYPE_ICONS[otro.type] || '📌'} {otro.name}</strong></>
        : <><strong className="u-text1">{CI_TYPE_ICONS[otro.type] || '📌'} {otro.name}</strong> {etiqueta('rel_', r.relation_type)} {t('cmdb.this_ci')}</>}
    </span>
  )
}

function useRelaciones(ciId?: string) {
  return useQuery<Rel[]>({
    queryKey: ['item-rels', ciId],
    queryFn: () => cmdbApi.sdRelations(ciId).then(r => r.data ?? []),
    enabled: !!ciId,
  })
}

function RelationsModal({ item, allItems, onClose }: { item: CI; allItems: CI[]; onClose: () => void }) {
  const t = useAppT()
  const etiqueta = useEtiqueta()
  const toast = useToast()
  const qc = useQueryClient()
  const [toId, setToId] = useState('')
  const [relType, setRelType] = useState('depends_on')
  const { data: rels = [], isLoading } = useRelaciones(item.id)
  const refrescar = () => qc.invalidateQueries({ queryKey: ['item-rels'] })

  const { mutate: createRel, isPending } = useMutation({
    mutationFn: () => cmdbApi.sdCreateRelation({ source_ci_id: item.id, target_ci_id: toId, relation_type: relType }),
    onSuccess: () => { refrescar(); setToId('') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteRel } = useMutation({
    mutationFn: (id: string) => cmdbApi.sdDeleteRelation(id),
    onSuccess: refrescar,
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <Modal open onClose={onClose} title={t('cmdb.relations_of', { name: item.name ?? '' })}>
      <div className="u-stack-16">
        {isLoading ? <Spinner /> : rels.length === 0 ? (
          <div className="cmdb-empty">{t('cmdb.sin_relaciones_definidas')}</div>
        ) : (
          <div className="cmdb-rel-list">
            {rels.map(r => (
              <div key={r.id} className="cmdb-rel-row">
                <RelLinea r={r} ciId={item.id} />
                <button type="button" aria-label={t('cmdb.delete_relation')} title={t('cmdb.delete_relation')}
                  onClick={() => openConfirmGlobal({ message: t('cmdb.delete_relation_q'), onConfirm: () => deleteRel(r.id), danger: true })}
                  className="cmdb-link-btn cmdb-link-btn--danger"><span aria-hidden="true">✕</span></button>
              </div>
            ))}
          </div>
        )}
        <div className="cmdb-rel-add">
          <div className="cmdb-rel-add__title">{t('cmdb.anadir_relacion')}</div>
          <div className="cmdb-rel-add__grid">
            <select aria-label={t('cmdb.relation_type')} className="cmdb-input cmdb-input--w180" value={relType} onChange={e => setRelType(e.target.value)}>
              {REL_TYPES.map(r => <option key={r} value={r}>{etiqueta('rel_', r)}</option>)}
            </select>
            <select aria-label={t('cmdb.target_ci')} className="cmdb-input" value={toId} onChange={e => setToId(e.target.value)}>
              <option value="">{t('cmdb.target_ci')}</option>
              {allItems.filter(i => i.id !== item.id).map(i => (
                <option key={i.id} value={i.id}>{CI_TYPE_ICONS[i.ci_type ?? ''] || '📌'} {i.name}</option>
              ))}
            </select>
          </div>
          <div className="cmdb-mt10">
            <Button onClick={() => createRel()} disabled={isPending || !toId} loading={isPending}>{t('cmdb.add_relation')}</Button>
          </div>
        </div>
        <div className="u-row-end">
          <Button variant="secondary" onClick={onClose}>{t('cmdb.close')}</Button>
        </div>
      </div>
    </Modal>
  )
}

type ChangelogEntry = { id: string; action?: string; created_at?: string; user_name?: string; summary?: string; field?: string; old_value?: string; new_value?: string }

function ChangelogModal({ item, onClose }: { item: CI; onClose: () => void }) {
  const t = useAppT()
  const etiqueta = useEtiqueta()
  const { data: entries = [], isLoading } = useQuery<ChangelogEntry[]>({
    queryKey: ['cmdb-changelog', item.id],
    queryFn: () => cmdbApi.sdChangelog(item.id).then(r => r.data ?? []),
  })
  const ACTION_COLOR: Record<string, string> = { created: 'var(--success)', updated: 'var(--accent)', deleted: 'var(--danger)' }

  return (
    <Modal open onClose={onClose} title={t('cmdb.history_of', { name: item.name ?? '' })} width={580}>
      {isLoading ? <Spinner /> : entries.length === 0 ? (
        <div className="cmdb-empty cmdb-empty--lg">
          {t('cmdb.sin_cambios_registrados')}
        </div>
      ) : (
        <div className="cmdb-log">
          {entries.map(e => {
            const color = ACTION_COLOR[e.action ?? ''] || 'var(--text-2)'
            return (
              <div key={e.id} className="cmdb-log__entry">
                <div className="cmdb-log__head">
                  <span className="cmdb-chip cmdb-chip--bold" style={chip(color)}>{etiqueta('action_', e.action)}</span>
                  <span className="u-text2-xs">
                    {e.created_at ? fmtDateTime(e.created_at) : ''}
                    {e.user_name ? ` · ${t('cmdb.por')} ${e.user_name}` : ` · ${t('cmdb.by_discovery')}`}
                  </span>
                </div>
                <div className="cmdb-log__summary">{e.summary}</div>
                {e.field && (
                  <div className="cmdb-log__field">
                    <code className="cmdb-code">{e.field}</code>
                    {e.old_value && <span> · <span className="u-danger">−{e.old_value}</span></span>}
                    {e.new_value && <span> → <span className="u-success">+{e.new_value}</span></span>}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </Modal>
  )
}


// ── Linked assets for a CI (drill-down panel) ────────────────────────────────
/** Activo de ALM vinculado a un CI. */
interface LinkedAsset { id: string; name?: string; serial_number?: string | null; status?: string | null }

function CILinkedAssets({ ciId }: { ciId: string }) {
  const t = useAppT()
  const { data: assets = [], isLoading } = useQuery<LinkedAsset[]>({
    queryKey: ['ci-assets', ciId],
    queryFn: () => cmdbApi.assetsByCI(ciId).then(r => r.data),
    staleTime: STALE_SHORT_MS,
  })
  if (isLoading) return null
  return (
    <div className="cmdb-assets">
      <div className="cmdb-section-title">
        {t('cmdb.linked_assets', { n: assets.length })}
      </div>
      {assets.length === 0 ? (
        <div className="u-text2-sm">{t('cmdb.ningun_activo_vinculado_a_este_ci')}</div>
      ) : (
        <div className="u-stack-6">
          {assets.map(a => (
            <div key={a.id} className="cmdb-asset">
              <div className="u-flex1-min0">
                <div className="cmdb-asset__name" title={a.name}>{a.name}</div>
                {a.serial_number ? <div className="u-text2-2xs">{t('cmdb.serial_number', { sn: String(a.serial_number) })}</div> : null}
              </div>
              {a.status ? <span className="cmdb-asset__status">{String(a.status)}</span> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── CMDB Agents on-prem tab ──────────────────────────────────────────────────
type Agente = { id: string; name: string; os_type?: string; is_active: boolean; last_checkin_at?: string; last_hostname?: string; ci_id?: string; token_prefix?: string }

function CMDBAgentsTab({ items }: { items: CI[] }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [agentName, setAgentName] = useState('')
  const [osType, setOsType] = useState('linux')
  const [newToken, setNewToken] = useState<string | null>(null)

  const { data: agents = [], isLoading } = useQuery<Agente[]>({
    queryKey: ['cmdb-agents'],
    queryFn: () => cmdbApi.agents().then(r => r.data ?? []),
    refetchInterval: POLL_LIVE_MS,
  })
  const nombreCI = (id?: string) => items.find(i => i.id === id)?.name

  const { mutate: registerAgent, isPending } = useMutation({
    mutationFn: () => cmdbApi.registerAgent({ name: agentName.trim(), os_type: osType }),
    onSuccess: (res) => {
      toast.success(t('cmdb.agent_registered'))
      setNewToken(res.data?.token ?? null)
      setAgentName('')
      qc.invalidateQueries({ queryKey: ['cmdb-agents'] })
    },
    onError: e => toast.error(extractErr(e, t('cmdb.agent_register_error'))),
  })

  const { mutate: revokeAgent } = useMutation({
    mutationFn: (id: string) => cmdbApi.deleteAgent(id),
    onSuccess: () => { toast.success(t('cmdb.agent_revoked')); qc.invalidateQueries({ queryKey: ['cmdb-agents'] }) },
    onError: e => toast.error(extractErr(e, t('cmdb.agent_revoke_error'))),
  })

  return (
    <div className="cmdb-agents">
      <div className="cmdb-panel">
        <div className="cmdb-card-title">
          {t('cmdb.registrar_nuevo_agente_on_prem')}
        </div>
        <div className="cmdb-agent-form">
          <div>
            <label id="agent-name-et" className="cmdb-label" htmlFor="agent-name">{t('cmdb.nombre_del_agente')}</label>
            <input id="agent-name" aria-labelledby="agent-name-et" value={agentName} onChange={e => setAgentName(e.target.value)} className="cmdb-input" placeholder={t('cmdb.agent_name_ph')} />
          </div>
          <div>
            <label className="cmdb-label" htmlFor="agent-os">{t('cmdb.platform')}</label>
            <select id="agent-os" value={osType} onChange={e => setOsType(e.target.value)} className="cmdb-input cmdb-input--w130">
              <option value="linux">{t('cmdb.os_linux')}</option>
              <option value="windows">{t('cmdb.os_windows')}</option>
            </select>
          </div>
          <Button onClick={() => registerAgent()} loading={isPending} disabled={!agentName.trim()}>{t('cmdb.register')}</Button>
        </div>

        {newToken && (
          <div className="cmdb-token" role="status">
            <div className="cmdb-token__title">
              {t('cmdb.token_de_registro_usalo_una_sola_vez')}
            </div>
            <code className="cmdb-token__value">
              {newToken}
            </code>
            <div className="cmdb-token__hint">
              {t('cmdb.ejecuta_el_agente_con')} <code className="u-mono">CMDB_TOKEN={newToken} ./cmdb-agent</code>
            </div>
            <div className="cmdb-mt10"><Button variant="ghost" size="sm" onClick={() => setNewToken(null)}>{t('cmdb.hide_token')}</Button></div>
          </div>
        )}
      </div>

      {/* `cmdb-panel--scroll` lleva `position: relative`: el texto oculto de la
          cabecera es absoluto y, sin eso, ensanchaba la página en móvil. */}
      <div className="cmdb-panel cmdb-panel--scroll">
        <div className="cmdb-card-title">
          {t('cmdb.registered_agents', { n: agents.length })}
        </div>
        {isLoading ? <Spinner /> : agents.length === 0 ? (
          <div className="cmdb-empty cmdb-empty--pad32">
            {t('cmdb.no_hay_agentes_registrados_registra_el_primero')}
          </div>
        ) : (
          <table className="cmdb-table">
            <thead>
              <tr className="u-border-b">
                <th className="cmdb-th">{t('cmdb.nombre_del_agente')}</th>
                <th className="cmdb-th">{t('cmdb.platform')}</th>
                <th className="cmdb-th">{t('cmdb.status')}</th>
                <th className="cmdb-th">{t('cmdb.last_checkin')}</th>
                <th className="cmdb-th">{t('cmdb.its_ci')}</th>
                <th className="cmdb-th"><span className="u-sr-only">{t('cmdb.actions')}</span></th>
              </tr>
            </thead>
            <tbody>
              {agents.map(ag => (
                <tr key={ag.id} className="u-border-b">
                  <td className="cmdb-td cmdb-td--strong">{ag.name}</td>
                  <td className="cmdb-td">{ag.os_type || '—'}</td>
                  <td className="cmdb-td">
                    <span className="cmdb-chip" style={chip(ag.is_active ? 'var(--success)' : 'var(--text-2)')}>
                      {ag.is_active ? t('cmdb.agent_active') : t('cmdb.agent_revoked_state')}
                    </span>
                  </td>
                  <td className="cmdb-td cmdb-td--sm">
                    {ag.last_checkin_at ? fmtDateTime(ag.last_checkin_at) : t('cmdb.never')}
                  </td>
                  <td className="cmdb-td">{nombreCI(ag.ci_id) || ag.last_hostname || '—'}</td>
                  <td className="cmdb-td">
                    {ag.is_active && (
                      <button type="button" aria-label={t('cmdb.revoke_agent')} title={t('cmdb.revoke_agent')}
                        onClick={() => openConfirmGlobal({ message: t('cmdb.revoke_agent_q', { name: ag.name }), onConfirm: () => revokeAgent(ag.id), danger: true })}
                        className="cmdb-icon-btn cmdb-icon-btn--danger"><span aria-hidden="true">🗑</span></button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ── Clases: los datos propios de cada clase, por organización ────────────────
function ClasesTab() {
  const t = useAppT()
  const etiqueta = useEtiqueta()
  const etiquetaDeCampo = useEtiquetaDeCampo()
  const toast = useToast()
  const qc = useQueryClient()
  const { data } = useCamposDeClase()
  const [clase, setClase] = useState('server')
  const [filas, setFilas] = useState<Campo[] | null>(null)
  const actuales = filas ?? data?.clases[clase] ?? []
  const cambiar = (i: number, cambio: Partial<Campo>) =>
    setFilas(actuales.map((f, j) => (j === i ? { ...f, ...cambio } : f)))
  const mover = (i: number, d: number) => {
    const otra = [...actuales]; const [f] = otra.splice(i, 1); otra.splice(i + d, 0, f); setFilas(otra)
  }
  const { mutate: guardar, isPending } = useMutation({
    mutationFn: () => cmdbApi.saveClassFields(clase, actuales.map(f => ({ ...f, label: f.label || null }))),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cmdb-class-fields'] }); setFilas(null); toast.success(t('cmdb.classes_saved')) },
    onError: e => toast.error(extractErr(e, t('cmdb.save_error'))),
  })

  return (
    <div className="cmdb-panel cmdb-panel--stack">
      <p className="cmdb-help">
        {t('cmdb.classes_help')} {data?.por_defecto ? t('cmdb.classes_factory') : ''}
      </p>
      <div>
        <label className="cmdb-label" htmlFor="clase-ci">{t('cmdb.ci_type')}</label>
        <select id="clase-ci" className="cmdb-input cmdb-input--max280" value={clase} onChange={e => { setClase(e.target.value); setFilas(null) }}>
          {CI_TYPES.map(c => <option key={c} value={c}>{CI_TYPE_ICONS[c]} {etiqueta('type_', c)}</option>)}
        </select>
      </div>
      {actuales.length === 0 && <div className="u-text2-sm">{t('cmdb.classes_empty')}</div>}
      {actuales.map((f, i) => (
        <div key={i} className="cmdb-class-row">
          <input aria-label={t('cmdb.classes_key')} className="cmdb-input cmdb-input--mono" value={f.key}
            onChange={e => cambiar(i, { key: e.target.value })} />
          <input aria-label={t('cmdb.classes_label')} className="cmdb-input" value={f.label ?? ''} placeholder={etiquetaDeCampo({ ...f, label: null })}
            onChange={e => cambiar(i, { label: e.target.value })} />
          <select aria-label={t('cmdb.classes_type')} className="cmdb-input" value={f.field_type} onChange={e => cambiar(i, { field_type: e.target.value })}>
            {['text', 'number', 'date'].map(ft => <option key={ft} value={ft}>{t(`cmdb.classes_type_${ft}`)}</option>)}
          </select>
          <div className="cmdb-class-row__actions">
            <button type="button" className="cmdb-icon-btn" disabled={i === 0} onClick={() => mover(i, -1)} aria-label={t('cmdb.classes_up')} title={t('cmdb.classes_up')}><span aria-hidden="true">↑</span></button>
            <button type="button" className="cmdb-icon-btn" disabled={i === actuales.length - 1} onClick={() => mover(i, 1)} aria-label={t('cmdb.classes_down')} title={t('cmdb.classes_down')}><span aria-hidden="true">↓</span></button>
            <button type="button" className="cmdb-icon-btn cmdb-icon-btn--danger"
              onClick={() => setFilas(actuales.filter((_, j) => j !== i))} aria-label={t('cmdb.classes_remove')} title={t('cmdb.classes_remove')}><span aria-hidden="true">✕</span></button>
          </div>
        </div>
      ))}
      <div className="u-wrap-10">
        <Button variant="secondary" onClick={() => setFilas([...actuales, { key: '', label: '', field_type: 'text' }])}>{t('cmdb.classes_add')}</Button>
        <Button onClick={() => guardar()} loading={isPending} disabled={filas === null || isPending}>{t('cmdb.save')}</Button>
      </div>
    </div>
  )
}

/** Lo que se enseña en la columna de red: host, IP y el atributo que más dice de la clase. */
function Red({ item }: { item: CI }) {
  const a = item.attributes || {}
  const extra = a.os || a.db_engine || a.url || a.image || a.cloud_provider || a.region
  return (
    <>
      {item.hostname && <div className="cmdb-net-host">{item.hostname}{a.port ? `:${a.port}` : ''}</div>}
      {item.ip_address && <div className="u-text2-mono-xs">{item.ip_address}</div>}
      {extra && <div className="cmdb-net-extra" title={String(extra)}>{String(extra)}</div>}
      {!item.hostname && !item.ip_address && !extra && '—'}
    </>
  )
}

export default function CMDBPage(): JSX.Element {
  const idFila = useId()
  const t = useAppT()
  const etiqueta = useEtiqueta()
  const { data: deClase } = useCamposDeClase()
  const etiquetaDeCampo = useEtiquetaDeCampo()
  const { user } = useAuth()
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

  return (
    <PageShell>
      <PageHeader icon={<Database size={18} />} title={t('cmdb.title')} subtitle={t('cmdb.subtitle')}
        actions={<Button onClick={() => { setEditing(null); setShowForm(true) }}>{t('cmdb.new_ci')}</Button>} />

      <Tabs
        items={[
          { id: 'list',     label: t('cmdb.tab_inventory') },
          { id: 'topology', label: t('cmdb.tab_topology') },
          { id: '3d',       label: t('cmdb.tab_3d') },
          // Agentes y clases son de admin en el servidor (revisión 2026-11: pm veía Agentes y recibía 403).
          ...(user?.role === 'admin' ? [{ id: 'agents', label: t('cmdb.tab_agents') }, { id: 'classes', label: t('cmdb.tab_classes') }] : []),
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
                <label className="cmdb-label" htmlFor="topo-ci">{t('cmdb.central_ci')}</label>
                <select id="topo-ci" className="cmdb-input" value={topoCI?.id || ''} onChange={e => {
                  setTopoCI(todos.find(i => i.id === e.target.value) || null)
                  setDrillCI(null)
                }}>
                  <option value="">{t('cmdb.select_ci')}</option>
                  {todos.map(ci => <option key={ci.id} value={ci.id}>{CI_TYPE_ICONS[ci.ci_type ?? '']||'📌'} {ci.name}</option>)}
                </select>
              </div>
              <div>
                <label className="cmdb-label" htmlFor="topo-radius">{t('cmdb.radio_de_expansion')}</label>
                <select id="topo-radius" className="cmdb-input cmdb-input--w120" value={topoRadius} onChange={e => setTopoRadius(Number(e.target.value))}>
                  {[1,2,3].map(r => <option key={r} value={r}>{t('cmdb.levels', { n: r })}</option>)}
                </select>
              </div>
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
                  <span className="cmdb-drill__icon" aria-hidden="true">{CI_TYPE_ICONS[drillCI.ci_type ?? ''] || '📌'}</span>
                  <div>
                    <div className="cmdb-drill__name">{drillCI.name}</div>
                    <div className="u-text2-xs">{drillCI.code} · {etiqueta('type_', drillCI.ci_type)}</div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setDrillCI(null)}
                  className="cmdb-link-btn cmdb-link-btn--close"
                  aria-label={t('cmdb.cerrar_panel_de_detalle')}
                  title={t('cmdb.cerrar_panel_de_detalle')}
                ><span aria-hidden="true">✕</span></button>
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
      <div className="cmdb-kpis">
        {([
          [t('cmdb.kpi_total'), todos.length, 'var(--text-1)'],
          ...Object.keys(STATUS_COLOR).map(s => [etiqueta('st_', s), todos.filter(i => i.status === s).length, STATUS_COLOR[s]]),
        ] as [string, number, string][]).map(([label,val,color]) => (
          <div key={label} className="cmdb-panel cmdb-panel--kpi">
            <div className="cmdb-kpi__value" style={{ '--cmdb-kpi': color } as CSSProperties}>{val}</div>
            <div className="cmdb-kpi__label">{label}</div>
          </div>
        ))}
      </div>

      <div className="cmdb-panel cmdb-panel--mb">
        <div className="cmdb-filters">
          <div className="cmdb-filters__q">
            <label id="cmdb-q-et" className="cmdb-label" htmlFor="cmdb-q">{t('cmdb.search')}</label>
            <input id="cmdb-q" aria-labelledby="cmdb-q-et" value={searchQ} onChange={e => setSearchQ(e.target.value)} placeholder={t('cmdb.search_ph')} className="cmdb-input" />
          </div>
          <div>
            <label className="cmdb-label" htmlFor="cmdb-type">{t('cmdb.ci_type')}</label>
            <select id="cmdb-type" value={filterType} onChange={e => setFilterType(e.target.value)} className="cmdb-input cmdb-input--w200">
              <option value="">{t('cmdb.todos_los_tipos')}</option>
              {CI_TYPES.map(c => <option key={c} value={c}>{CI_TYPE_ICONS[c]} {etiqueta('type_', c)} ({typeCounts[c]||0})</option>)}
            </select>
          </div>
          <div>
            <label className="cmdb-label" htmlFor="cmdb-status">{t('cmdb.status')}</label>
            <select id="cmdb-status" value={filterStatus} onChange={e => setFilterStatus(e.target.value)} className="cmdb-input cmdb-input--w160">
              <option value="">{t('cmdb.todos')}</option>
              {Object.keys(STATUS_COLOR).map(v => <option key={v} value={v}>{etiqueta('st_', v)}</option>)}
            </select>
          </div>
          {(filterType||filterStatus||searchQ) && (
            <Button variant="secondary" onClick={() => {setFilterType('');setFilterStatus('');setSearchQ('')}}>{t('cmdb.clear')}</Button>
          )}
        </div>
      </div>

      {isLoading ? <Spinner /> : itemsFailed ? (
        <div role="alert" className="u-danger">{extractErr(itemsError, t('toast.load_error'))}</div>
      ) : items.length === 0 ? (
        <div className="cmdb-panel cmdb-panel--empty">
          <div className="cmdb-empty-title">{todos.length ? t('cmdb.no_match') : t('cmdb.no_cis')}</div>
          {!todos.length && <>
            <div className="u-text2-base-mb20">{t('cmdb.registra_servidores_aplicaciones_bases_de_datos_y')}</div>
            <Button onClick={() => { setEditing(null); setShowForm(true) }}>{t('cmdb.new_ci')}</Button>
          </>}
        </div>
      ) : (
        <div className="cmdb-panel cmdb-panel--scroll">
          <table className="cmdb-table">
            <thead>
              <tr className="u-border-b">
              {columnas.map(([key, label]) => (
                <th key={key} aria-sort={sortKey === key ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  className="cmdb-th-sort">
                  <button type="button" onClick={() => toggleSort(key)}
                    className={`cmdb-sort-btn${sortKey === key ? ' is-active' : ''}`}>
                    {t(`cmdb.${label}`)}{sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
                  </button>
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
                        <span className="cmdb-row-icon" aria-hidden="true">{CI_TYPE_ICONS[item.ci_type ?? '']||'📌'}</span>
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
                        <button type="button" onClick={() => setHistoryItem(item)} className="cmdb-icon-btn" aria-label={t('cmdb.ver_historial_de_cambios')} title={t('cmdb.ver_historial_de_cambios')}><span aria-hidden="true">📋</span></button>
                        <button type="button" onClick={() => setRelItem(item)} className="cmdb-icon-btn" aria-label={t('cmdb.relationships')} title={t('cmdb.relationships')}><span aria-hidden="true">🔗</span></button>
                        <button type="button" onClick={() => { setEditing(item); setShowForm(true) }} className="cmdb-icon-btn" aria-label={t('cmdb.edit_ci')} title={t('cmdb.edit_ci')}><span aria-hidden="true">✏</span></button>
                        <button type="button" onClick={() => openConfirmGlobal({ message: t('cmdb.delete_ci_q', { name: item.name ?? '' }), onConfirm: () => deleteItem(item.id), danger: true })}
                          className="cmdb-icon-btn cmdb-icon-btn--danger" aria-label={t('cmdb.delete_ci')} title={t('cmdb.delete_ci')}><span aria-hidden="true">🗑</span></button>
                      </div>
                    </td>
                  </tr>
              ))}
            </tbody>
          </table>
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
    </PageShell>
  )
}
