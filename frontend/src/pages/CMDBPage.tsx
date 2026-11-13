import { useState, lazy, Suspense } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, localeActivo } from '../utils/helpers'
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

const ps: CSSProperties = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is: CSSProperties = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", fontFamily:'inherit', boxSizing:'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }
const chip = (color: string): CSSProperties => ({
  fontSize: "var(--text-xs)", padding: '2px 8px', borderRadius: 20, color,
  background: `color-mix(in srgb, ${color} 14%, transparent)`,
})
// Texto solo para lectores de pantalla (la aplicación no tiene clase para ello).
const srOnly: CSSProperties = { position: 'absolute', width: 1, height: 1, padding: 0, margin: -1, overflow: 'hidden', clip: 'rect(0,0,0,0)', whiteSpace: 'nowrap', border: 0 }
const iconBtn: CSSProperties = { background:'none', border:'1px solid var(--surface-4)', borderRadius:'var(--radius-sm)', padding:'4px 8px', color:'var(--text-2)', cursor:'pointer', fontSize: "var(--text-xs)" }

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
    staleTime: 60000,
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
    mutationFn: () => {
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
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:12}}>
          <div>
            <label style={ls} htmlFor={id('name')}>{t('cmdb.ci_name')}</label>
            <input id={id('name')} style={is} value={form.name} onChange={e => set('name')(e.target.value)} />
          </div>
          <div>
            <label style={ls} htmlFor={id('type')}>{t('cmdb.ci_type')}</label>
            <select id={id('type')} style={is} value={form.ci_type} onChange={e => set('ci_type')(e.target.value)}>
              {CI_TYPES.map(c => <option key={c} value={c}>{CI_TYPE_ICONS[c]} {etiqueta('type_', c)}</option>)}
            </select>
          </div>
        </div>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(140px,1fr))',gap:12}}>
          <div>
            <label style={ls} htmlFor={id('status')}>{t('cmdb.status')}</label>
            <select id={id('status')} style={is} value={form.status} onChange={e => set('status')(e.target.value)}>
              {Object.keys(STATUS_COLOR).map(v => <option key={v} value={v}>{etiqueta('st_', v)}</option>)}
            </select>
          </div>
          <div>
            <label style={ls} htmlFor={id('env')}>{t('cmdb.environment')}</label>
            <select id={id('env')} style={is} value={form.environment} onChange={e => set('environment')(e.target.value)}>
              {Object.keys(ENV_COLOR).map(v => <option key={v} value={v}>{etiqueta('env_', v)}</option>)}
            </select>
          </div>
          <div>
            <label style={ls} htmlFor={id('crit')}>{t('cmdb.criticality')}</label>
            <select id={id('crit')} style={is} value={form.criticality} onChange={e => set('criticality')(e.target.value)}>
              {CRITICALITIES.map(v => <option key={v} value={v}>{etiqueta('crit_', v)}</option>)}
            </select>
          </div>
        </div>
        <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(140px,1fr))',gap:12}}>
          {(['hostname','ip_address','version'] as const).map(k => (
            <div key={k}>
              <label style={ls} htmlFor={id(k)}>{t(`cmdb.f_${k}`)}</label>
              <input id={id(k)} style={is} value={form[k]} onChange={e => set(k)(e.target.value)} />
            </div>
          ))}
        </div>
        <div>
          <div style={{fontSize: "var(--text-xs)",fontWeight:700,color:'var(--text-2)',textTransform:'uppercase',letterSpacing:'0.06em',marginBottom:10}}>
            {CI_TYPE_ICONS[form.ci_type]} {t('cmdb.class_fields', { type: etiqueta('type_', form.ci_type) })}
          </div>
          <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:10}}>
            {campos.map(c => (
              <div key={c.key}>
                <label style={ls} htmlFor={id(c.key)}>{etiquetaDeCampo(c)}</label>
                <input id={id(c.key)} style={is} type={c.field_type || 'text'} value={attrs[c.key] ?? ''}
                  onChange={e => setAttrs(a => ({ ...a, [c.key]: e.target.value }))} />
              </div>
            ))}
          </div>
        </div>
        <div>
          <label style={ls} htmlFor={id('descr')}>{t('cmdb.descripcion')}</label>
          <textarea id={id('descr')} style={{...is, height:70, resize:'vertical'}} value={form.description} onChange={e => set('description')(e.target.value)} />
        </div>
        <div style={{display:'flex',justifyContent:'flex-end',gap:10,marginTop:8}}>
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
    <span style={{ color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
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
          <div style={{textAlign:'center',padding:'20px',color:'var(--text-2)',fontSize: "var(--text-base)"}}>{t('cmdb.sin_relaciones_definidas')}</div>
        ) : (
          <div style={{display:'flex',flexDirection:'column',gap:4}}>
            {rels.map(r => (
              <div key={r.id} style={{display:'flex',alignItems:'center',gap:10,padding:'8px 12px',background:'var(--surface-1)',borderRadius:'var(--radius-sm)',fontSize: "var(--text-sm)"}}>
                <RelLinea r={r} ciId={item.id} />
                <button aria-label={t('cmdb.delete_relation')}
                  onClick={() => openConfirmGlobal({ message: t('cmdb.delete_relation_q'), onConfirm: () => deleteRel(r.id), danger: true })}
                  style={{marginLeft:'auto',background:'none',border:'none',color:'var(--danger)',cursor:'pointer'}}>✕</button>
              </div>
            ))}
          </div>
        )}
        <div style={{borderTop:'1px solid var(--surface-4)',paddingTop:14}}>
          <div style={{fontSize: "var(--text-sm)",fontWeight:600,color:'var(--text-2)',marginBottom:10}}>{t('cmdb.anadir_relacion')}</div>
          <div style={{display:'grid',gridTemplateColumns:'auto 1fr',gap:8,alignItems:'center'}}>
            <select aria-label={t('cmdb.relation_type')} style={{...is,width:180}} value={relType} onChange={e => setRelType(e.target.value)}>
              {REL_TYPES.map(r => <option key={r} value={r}>{etiqueta('rel_', r)}</option>)}
            </select>
            <select aria-label={t('cmdb.target_ci')} style={is} value={toId} onChange={e => setToId(e.target.value)}>
              <option value="">{t('cmdb.target_ci')}</option>
              {allItems.filter(i => i.id !== item.id).map(i => (
                <option key={i.id} value={i.id}>{CI_TYPE_ICONS[i.ci_type ?? ''] || '📌'} {i.name}</option>
              ))}
            </select>
          </div>
          <div style={{marginTop:10}}>
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
        <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-2)', fontSize: "var(--text-base)" }}>
          {t('cmdb.sin_cambios_registrados')}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 480, overflowY: 'auto' }}>
          {entries.map(e => {
            const color = ACTION_COLOR[e.action ?? ''] || 'var(--text-2)'
            return (
              <div key={e.id} style={{ padding: '10px 14px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
                  <span style={{ ...chip(color), fontWeight: 700 }}>{etiqueta('action_', e.action)}</span>
                  <span className="u-text2-xs">
                    {e.created_at ? new Date(e.created_at).toLocaleString(localeActivo()) : ''}
                    {e.user_name ? ` · ${t('cmdb.por')} ${e.user_name}` : ` · ${t('cmdb.by_discovery')}`}
                  </span>
                </div>
                <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)' }}>{e.summary}</div>
                {e.field && (
                  <div style={{ marginTop: 4, fontSize: "var(--text-xs)", color: 'var(--text-2)', wordBreak: 'break-word' }}>
                    <code style={{ background: 'var(--surface-3)', padding: '1px 5px', borderRadius: 4 }}>{e.field}</code>
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
    queryFn: () => cmdbApi.assetsByCI(ciId).then(r => r.data?.assets ?? r.data ?? []),
    staleTime: 30000,
  })
  if (isLoading) return null
  return (
    <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 12, marginBottom: 8 }}>
      <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
        {t('cmdb.linked_assets', { n: assets.length })}
      </div>
      {assets.length === 0 ? (
        <div className="u-text2-sm">{t('cmdb.ningun_activo_vinculado_a_este_ci')}</div>
      ) : (
        <div className="u-stack-6">
          {assets.map(a => (
            <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--surface-3)', borderRadius: 'var(--radius-sm)', padding: '6px 10px' }}>
              <div className="u-flex1-min0">
                <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</div>
                {a.serial_number ? <div className="u-text2-2xs">S/N {String(a.serial_number)}</div> : null}
              </div>
              {a.status ? <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)', background: 'var(--surface-4)', padding: '2px 6px', borderRadius: 3, whiteSpace: 'nowrap' }}>{String(a.status)}</span> : null}
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
    refetchInterval: 15000,
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

  const th: CSSProperties = { padding: '8px 10px', textAlign: 'left', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase' }
  const td: CSSProperties = { padding: '10px 10px', color: 'var(--text-2)' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ ...ps }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 16 }}>
          {t('cmdb.registrar_nuevo_agente_on_prem')}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto auto', gap: 12, alignItems: 'flex-end' }}>
          <div>
            <label style={ls} htmlFor="agent-name">{t('cmdb.nombre_del_agente')}</label>
            <input id="agent-name" value={agentName} onChange={e => setAgentName(e.target.value)} style={is} placeholder="agent-datacenter-01" />
          </div>
          <div>
            <label style={ls} htmlFor="agent-os">{t('cmdb.platform')}</label>
            <select id="agent-os" value={osType} onChange={e => setOsType(e.target.value)} style={{ ...is, width: 130 }}>
              <option value="linux">Linux</option>
              <option value="windows">Windows</option>
            </select>
          </div>
          <Button onClick={() => registerAgent()} loading={isPending} disabled={!agentName.trim()}>{t('cmdb.register')}</Button>
        </div>

        {newToken && (
          <div style={{ marginTop: 16, background: 'var(--info-bg)', border: '1px solid var(--info-border)', borderRadius: 'var(--radius-md)', padding: '14px 18px' }}>
            <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-1)', textTransform: 'uppercase', marginBottom: 8 }}>
              {t('cmdb.token_de_registro_usalo_una_sola_vez')}
            </div>
            <code style={{ display: 'block', fontSize: "var(--text-sm)", color: 'var(--text-1)', wordBreak: 'break-all', fontFamily: 'var(--font-mono)', background: 'var(--surface-4)', padding: '8px 12px', borderRadius: 'var(--radius-sm)' }}>
              {newToken}
            </code>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 8 }}>
              {t('cmdb.ejecuta_el_agente_con')} <code className="u-mono">CMDB_TOKEN={newToken} ./cmdb-agent</code>
            </div>
            <Button variant="ghost" size="sm" onClick={() => setNewToken(null)} style={{ marginTop: 10 }}>{t('cmdb.hide_token')}</Button>
          </div>
        )}
      </div>

      {/* `position: relative`: el texto oculto de la cabecera es absoluto y, sin
          esto, escapaba del recorte y ensanchaba la página en móvil. */}
      <div style={{ ...ps, overflowX: 'auto', position: 'relative' }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 16 }}>
          {t('cmdb.registered_agents', { n: agents.length })}
        </div>
        {isLoading ? <Spinner /> : agents.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 32, color: 'var(--text-2)', fontSize: "var(--text-base)" }}>
            {t('cmdb.no_hay_agentes_registrados_registra_el_primero')}
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-base)" }}>
            <thead>
              <tr className="u-border-b">
                <th style={th}>{t('cmdb.nombre_del_agente')}</th>
                <th style={th}>{t('cmdb.platform')}</th>
                <th style={th}>{t('cmdb.status')}</th>
                <th style={th}>{t('cmdb.last_checkin')}</th>
                <th style={th}>{t('cmdb.its_ci')}</th>
                <th style={th}><span style={srOnly}>{t('cmdb.actions')}</span></th>
              </tr>
            </thead>
            <tbody>
              {agents.map(ag => (
                <tr key={ag.id} className="u-border-b">
                  <td style={{ ...td, fontWeight: 600, color: 'var(--text-1)' }}>{ag.name}</td>
                  <td style={td}>{ag.os_type || '—'}</td>
                  <td style={td}>
                    <span style={chip(ag.is_active ? 'var(--success)' : 'var(--text-2)')}>
                      {ag.is_active ? t('cmdb.agent_active') : t('cmdb.agent_revoked_state')}
                    </span>
                  </td>
                  <td style={{ ...td, fontSize: "var(--text-sm)" }}>
                    {ag.last_checkin_at ? new Date(ag.last_checkin_at).toLocaleString(localeActivo()) : t('cmdb.never')}
                  </td>
                  <td style={td}>{nombreCI(ag.ci_id) || ag.last_hostname || '—'}</td>
                  <td style={td}>
                    {ag.is_active && (
                      <button aria-label={t('cmdb.revoke_agent')} title={t('cmdb.revoke_agent')}
                        onClick={() => openConfirmGlobal({ message: t('cmdb.revoke_agent_q', { name: ag.name }), onConfirm: () => revokeAgent(ag.id), danger: true })}
                        style={{ ...iconBtn, color: 'var(--danger)', borderColor: 'var(--danger-border)' }}>🗑</button>
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
  const btn: CSSProperties = { ...iconBtn, padding: '4px 8px' }

  return (
    <div style={{ ...ps, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <p style={{ margin: 0, color: 'var(--text-2)', fontSize: "var(--text-sm)" }}>
        {t('cmdb.classes_help')} {data?.por_defecto ? t('cmdb.classes_factory') : ''}
      </p>
      <div>
        <label style={ls} htmlFor="clase-ci">{t('cmdb.ci_type')}</label>
        <select id="clase-ci" style={{ ...is, maxWidth: 280 }} value={clase} onChange={e => { setClase(e.target.value); setFilas(null) }}>
          {CI_TYPES.map(c => <option key={c} value={c}>{CI_TYPE_ICONS[c]} {etiqueta('type_', c)}</option>)}
        </select>
      </div>
      {actuales.length === 0 && <div className="u-text2-sm">{t('cmdb.classes_empty')}</div>}
      {actuales.map((f, i) => (
        <div key={i} style={{ display: 'grid', gridTemplateColumns: 'minmax(120px,1fr) minmax(160px,1.4fr) 120px auto', gap: 8, alignItems: 'center' }}>
          <input aria-label={t('cmdb.classes_key')} style={{ ...is, fontFamily: 'var(--font-mono)' }} value={f.key}
            onChange={e => cambiar(i, { key: e.target.value })} />
          <input aria-label={t('cmdb.classes_label')} style={is} value={f.label ?? ''} placeholder={etiquetaDeCampo({ ...f, label: null })}
            onChange={e => cambiar(i, { label: e.target.value })} />
          <select aria-label={t('cmdb.classes_type')} style={is} value={f.field_type} onChange={e => cambiar(i, { field_type: e.target.value })}>
            {['text', 'number', 'date'].map(ft => <option key={ft} value={ft}>{t(`cmdb.classes_type_${ft}`)}</option>)}
          </select>
          <div style={{ display: 'flex', gap: 4 }}>
            <button type="button" style={btn} disabled={i === 0} onClick={() => mover(i, -1)} aria-label={t('cmdb.classes_up')}>↑</button>
            <button type="button" style={btn} disabled={i === actuales.length - 1} onClick={() => mover(i, 1)} aria-label={t('cmdb.classes_down')}>↓</button>
            <button type="button" style={{ ...btn, color: 'var(--danger)', borderColor: 'var(--danger-border)' }}
              onClick={() => setFilas(actuales.filter((_, j) => j !== i))} aria-label={t('cmdb.classes_remove')}>✕</button>
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
      {item.hostname && <div style={{fontFamily:'var(--font-mono)',fontSize: "var(--text-sm)"}}>{item.hostname}{a.port ? `:${a.port}` : ''}</div>}
      {item.ip_address && <div className="u-text2-mono-xs">{item.ip_address}</div>}
      {extra && <div style={{fontSize: "var(--text-xs)",color:'var(--text-2)',overflow:'hidden',textOverflow:'ellipsis',maxWidth:200}}>{String(extra)}</div>}
      {!item.hostname && !item.ip_address && !extra && '—'}
    </>
  )
}

export default function CMDBPage(): JSX.Element {
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
    queryFn: () => cmdbApi.sdList({ page_size: 500 }).then(r => r.data ?? []),
  })
  const { data: items = [], isLoading } = useQuery<CI[]>({
    queryKey: ['cmdb-items', filterType, filterStatus, searchQ],
    queryFn: () => {
      const p: Record<string, string | number> = { page_size: 500 }
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
        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div style={{ ...ps, flex: '1 1 480px', minWidth: 0 }}>
            <div style={{display:'flex',gap:12,alignItems:'flex-end',marginBottom:20,flexWrap:'wrap'}}>
              <div style={{flex:'1 1 280px'}}>
                <label style={ls} htmlFor="topo-ci">{t('cmdb.central_ci')}</label>
                <select id="topo-ci" style={is} value={topoCI?.id || ''} onChange={e => {
                  setTopoCI(todos.find(i => i.id === e.target.value) || null)
                  setDrillCI(null)
                }}>
                  <option value="">{t('cmdb.select_ci')}</option>
                  {todos.map(ci => <option key={ci.id} value={ci.id}>{CI_TYPE_ICONS[ci.ci_type ?? '']||'📌'} {ci.name}</option>)}
                </select>
              </div>
              <div>
                <label style={ls} htmlFor="topo-radius">{t('cmdb.radio_de_expansion')}</label>
                <select id="topo-radius" style={{...is,width:120}} value={topoRadius} onChange={e => setTopoRadius(Number(e.target.value))}>
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
            <div style={{
              flex: '0 1 310px', background: 'var(--surface-2)',
              border: '1px solid var(--surface-4)', borderRadius: 12,
              padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14,
              maxHeight: 660, overflowY: 'auto',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div className="u-row-center-8">
                  <span style={{ fontSize: "var(--text-xl-em)" }}>{CI_TYPE_ICONS[drillCI.ci_type ?? ''] || '📌'}</span>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: "var(--text-md)", color: 'var(--text-1)' }}>{drillCI.name}</div>
                    <div className="u-text2-xs">{drillCI.code} · {etiqueta('type_', drillCI.ci_type)}</div>
                  </div>
                </div>
                <button
                  onClick={() => setDrillCI(null)}
                  style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-lg)", padding: 0 }}
                  aria-label={t('cmdb.cerrar_panel_de_detalle')}
                >✕</button>
              </div>

              <div className="u-wrap-8">
                {drillCI.status && <span style={chip(STATUS_COLOR[drillCI.status] || 'var(--text-2)')}>{etiqueta('st_', drillCI.status)}</span>}
                {drillCI.environment && <span style={chip(ENV_COLOR[drillCI.environment] || 'var(--text-2)')}>{etiqueta('env_', drillCI.environment)}</span>}
                {drillCI.is_discovered && <span style={chip('var(--accent)')}>{t('cmdb.discovered', { provider: drillCI.discovery_provider ?? '' })}</span>}
                {drillCI.drift_detected_at && <span style={chip('var(--warning)')}>{t('cmdb.drift')}</span>}
              </div>

              {drillCI.description && (
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.5 }}>{drillCI.description}</div>
              )}

              <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 12 }}>
                <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
                  {t('cmdb.attributes')}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {([
                    ['hostname', drillCI.hostname], ['ip_address', drillCI.ip_address], ['version', drillCI.version],
                    ...Object.entries(drillCI.attributes || {}).filter(([, v]) => typeof v !== 'object'),
                  ] as [string, unknown][]).filter(([, v]) => v !== null && v !== undefined && v !== '').map(([k, value]) => {
                    const campo = deClase?.clases[drillCI.ci_type ?? '']?.find(c => c.key === k) ?? { key: k, field_type: 'text' }
                    return (
                      <div key={k} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: "var(--text-sm)" }}>
                        <span style={{ color: 'var(--text-2)', flexShrink: 0 }}>{etiquetaDeCampo(campo)}</span>
                        <span style={{ color: 'var(--text-1)', fontFamily: 'var(--font-mono)', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 160 }} title={String(value)}>{String(value)}</span>
                      </div>
                    )
                  })}
                </div>
              </div>

              {drillRels.length > 0 && (
                <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 12 }}>
                  <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
                    {t('cmdb.relationships')}
                  </div>
                  {drillRels.map(r => (
                    <div key={r.id} style={{ display: 'flex', fontSize: "var(--text-xs)", marginBottom: 4 }}>
                      <RelLinea r={r} ciId={drillCI.id} />
                    </div>
                  ))}
                </div>
              )}

              <CILinkedAssets ciId={drillCI.id} />

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, borderTop: '1px solid var(--surface-4)', paddingTop: 12 }}>
                <Button onClick={() => { setTopoCI(drillCI); setDrillCI(null) }}>{t('cmdb.ver_como_ci_central')}</Button>
                <Button variant="secondary" onClick={() => { setEditing(drillCI); setShowForm(true) }}>{t('cmdb.edit_ci')}</Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─── INVENTARIO ─────────────────────────────────────────────── */}
      {tab === 'list' && <>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(150px,1fr))',gap:12,marginBottom:20}}>
        {([
          [t('cmdb.kpi_total'), todos.length, 'var(--text-1)'],
          ...Object.keys(STATUS_COLOR).map(s => [etiqueta('st_', s), todos.filter(i => i.status === s).length, STATUS_COLOR[s]]),
        ] as [string, number, string][]).map(([label,val,color]) => (
          <div key={label} style={{...ps,padding:'14px 16px'}}>
            <div style={{fontSize: "var(--text-2xl)",fontWeight:700,color}}>{val}</div>
            <div style={{fontSize: "var(--text-xs)",color:'var(--text-2)',textTransform:'uppercase',letterSpacing:'.07em'}}>{label}</div>
          </div>
        ))}
      </div>

      <div style={{...ps,marginBottom:20}}>
        <div style={{display:'flex',flexWrap:'wrap',gap:12,alignItems:'flex-end'}}>
          <div style={{flex:'1 1 240px'}}>
            <label style={ls} htmlFor="cmdb-q">{t('cmdb.search')}</label>
            <input id="cmdb-q" value={searchQ} onChange={e => setSearchQ(e.target.value)} placeholder={t('cmdb.search_ph')} style={is} />
          </div>
          <div>
            <label style={ls} htmlFor="cmdb-type">{t('cmdb.ci_type')}</label>
            <select id="cmdb-type" value={filterType} onChange={e => setFilterType(e.target.value)} style={{...is,width:200}}>
              <option value="">{t('cmdb.todos_los_tipos')}</option>
              {CI_TYPES.map(c => <option key={c} value={c}>{CI_TYPE_ICONS[c]} {etiqueta('type_', c)} ({typeCounts[c]||0})</option>)}
            </select>
          </div>
          <div>
            <label style={ls} htmlFor="cmdb-status">{t('cmdb.status')}</label>
            <select id="cmdb-status" value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={{...is,width:160}}>
              <option value="">{t('cmdb.todos')}</option>
              {Object.keys(STATUS_COLOR).map(v => <option key={v} value={v}>{etiqueta('st_', v)}</option>)}
            </select>
          </div>
          {(filterType||filterStatus||searchQ) && (
            <Button variant="secondary" onClick={() => {setFilterType('');setFilterStatus('');setSearchQ('')}}>{t('cmdb.clear')}</Button>
          )}
        </div>
      </div>

      {isLoading ? <Spinner /> : items.length === 0 ? (
        <div style={{...ps,textAlign:'center',padding:'48px 24px'}}>
          <div style={{fontSize: "var(--text-md-em)",fontWeight:600,marginBottom:8}}>{todos.length ? t('cmdb.no_match') : t('cmdb.no_cis')}</div>
          {!todos.length && <>
            <div className="u-text2-base-mb20">{t('cmdb.registra_servidores_aplicaciones_bases_de_datos_y')}</div>
            <Button onClick={() => { setEditing(null); setShowForm(true) }}>{t('cmdb.new_ci')}</Button>
          </>}
        </div>
      ) : (
        <div style={{...ps, overflowX:'auto', position:'relative'}}>
          <table style={{width:'100%',borderCollapse:'collapse',fontSize: "var(--text-base)"}}>
            <thead>
              <tr className="u-border-b">
              {columnas.map(([key, label]) => (
                <th key={key} aria-sort={sortKey === key ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  style={{textAlign:'left',padding:0,whiteSpace:'nowrap'}}>
                  <button onClick={() => toggleSort(key)}
                    style={{background:'none',border:'none',padding:'8px 12px',cursor:'pointer',fontFamily:'inherit',fontSize: "var(--text-xs)",
                      color: sortKey === key ? 'var(--accent)' : 'var(--text-2)', textTransform:'uppercase',letterSpacing:'.06em'}}>
                    {t(`cmdb.${label}`)}{sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
                  </button>
                </th>
              ))}
              <th style={{padding:'8px 12px'}}><span style={srOnly}>{t('cmdb.actions')}</span></th>
              </tr>
            </thead>
            <tbody>
              {sortedItems.map(item => (
                  <tr key={item.id} className="u-border-b">
                    <td className="u-pad-10-12">
                      <div className="u-row-center-8">
                        <span style={{fontSize: "var(--text-lg)"}} aria-hidden>{CI_TYPE_ICONS[item.ci_type ?? '']||'📌'}</span>
                        <div className="u-min0">
                          <div className="u-600">{item.name}</div>
                          <div className="u-text2-xs">
                            {item.code}{item.is_discovered ? ` · ${t('cmdb.discovered', { provider: item.discovery_provider ?? '' })}` : ''}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td style={{padding:'10px 12px',color:'var(--text-2)',fontSize: "var(--text-sm)"}}>{etiqueta('type_', item.ci_type)}</td>
                    <td className="u-pad-10-12">
                      <span style={chip(STATUS_COLOR[item.status ?? ''] || 'var(--text-2)')}>{etiqueta('st_', item.status)}</span>
                      {item.drift_detected_at && <span style={{...chip('var(--warning)'), marginLeft: 6}}>{t('cmdb.drift')}</span>}
                    </td>
                    <td className="u-pad-10-12">
                      {item.environment ? <span style={chip(ENV_COLOR[item.environment] || 'var(--text-2)')}>{etiqueta('env_', item.environment)}</span> : '—'}
                    </td>
                    <td style={{padding:'10px 12px',fontSize: "var(--text-sm)",color:'var(--text-2)'}}><Red item={item} /></td>
                    <td style={{padding:'10px 12px',fontSize: "var(--text-sm)",color:'var(--text-2)',fontFamily:'var(--font-mono)'}}>{item.version||'—'}</td>
                    <td className="u-pad-10-12">
                      <div className="u-row-6">
                        <button onClick={() => setHistoryItem(item)} style={iconBtn} aria-label={t('cmdb.ver_historial_de_cambios')} title={t('cmdb.ver_historial_de_cambios')}>📋</button>
                        <button onClick={() => setRelItem(item)} style={iconBtn} aria-label={t('cmdb.relationships')} title={t('cmdb.relationships')}>🔗</button>
                        <button onClick={() => { setEditing(item); setShowForm(true) }} style={iconBtn} aria-label={t('cmdb.edit_ci')} title={t('cmdb.edit_ci')}>✏</button>
                        <button onClick={() => openConfirmGlobal({ message: t('cmdb.delete_ci_q', { name: item.name ?? '' }), onConfirm: () => deleteItem(item.id), danger: true })}
                          style={{...iconBtn, borderColor:'var(--danger-border)', color:'var(--danger)'}} aria-label={t('cmdb.delete_ci')} title={t('cmdb.delete_ci')}>🗑</button>
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
