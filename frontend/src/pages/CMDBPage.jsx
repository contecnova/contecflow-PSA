import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { Database } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import CMDBTopologyGraph from '../components/cmdb/CMDBTopologyGraph'

const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding:'8px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const CI_TYPES = ['server','application','database','network','service','container','cloud','endpoint','storage','other']
const CI_TYPE_ICONS = {server:'🖥️',application:'📱',database:'🗄️',network:'🌐',service:'⚙️',container:'📦',cloud:'☁️',endpoint:'💻',storage:'💾',other:'📌'}

// Campos específicos por tipo de CI
const CI_TYPE_FIELDS = {
  server:      [{k:'hostname',l:'Hostname',ph:'web-01.interno.com'},{k:'ip_address',l:'IP Address',ph:'192.168.1.10'},{k:'os',l:'Sistema Operativo',ph:'Ubuntu 22.04'},{k:'cpu_cores',l:'CPU Cores',ph:'8',type:'number'},{k:'ram_gb',l:'RAM (GB)',ph:'32',type:'number'},{k:'serial_number',l:'Número de serie',ph:'SN12345'},{k:'location',l:'Ubicación física',ph:'CPD Rack A-12'}],
  application: [{k:'url',l:'URL',ph:'https://app.empresa.com'},{k:'version',l:'Versión',ph:'v2.4.1'},{k:'tech_stack',l:'Stack tecnológico',ph:'React / Python / PostgreSQL'},{k:'repo_url',l:'Repositorio',ph:'https://github.com/org/repo'},{k:'owner_team',l:'Equipo responsable',ph:'Equipo Plataforma'},{k:'sla_tier',l:'Tier SLA',ph:'Gold'}],
  database:    [{k:'db_engine',l:'Motor BD',ph:'PostgreSQL 15'},{k:'hostname',l:'Host',ph:'db-prod-01'},{k:'ip_address',l:'IP',ph:'10.0.1.5'},{k:'port',l:'Puerto',ph:'5432'},{k:'size_gb',l:'Tamaño (GB)',ph:'500',type:'number'},{k:'backup_schedule',l:'Backup',ph:'Diario 02:00h'}],
  network:     [{k:'ip_address',l:'IP/Rango',ph:'10.0.0.0/24'},{k:'hostname',l:'Hostname',ph:'fw-prod-01'},{k:'vendor',l:'Fabricante',ph:'Cisco'},{k:'model',l:'Modelo',ph:'ASA 5505'},{k:'serial_number',l:'Serie',ph:'FCH1234'},{k:'location',l:'Ubicación',ph:'CPD Rack B-01'}],
  service:     [{k:'url',l:'Endpoint/URL',ph:'https://api.empresa.com'},{k:'version',l:'Versión',ph:'v1.0'},{k:'sla_tier',l:'Tier SLA',ph:'Platinum'},{k:'owner_team',l:'Equipo',ph:'DevOps'},{k:'dependencies',l:'Dependencias',ph:'auth-service, db-primary'}],
  container:   [{k:'image',l:'Imagen Docker',ph:'nginx:1.24-alpine'},{k:'version',l:'Tag/Versión',ph:'1.24-alpine'},{k:'cluster',l:'Cluster',ph:'k8s-prod'},{k:'namespace',l:'Namespace',ph:'production'},{k:'replicas',l:'Réplicas',ph:'3',type:'number'}],
  cloud:       [{k:'cloud_provider',l:'Proveedor',ph:'AWS / Azure / GCP'},{k:'region',l:'Región',ph:'eu-west-1'},{k:'resource_id',l:'Resource ID',ph:'i-1234567890abcdef0'},{k:'instance_type',l:'Tipo instancia',ph:'t3.large'},{k:'monthly_cost',l:'Coste mensual (€)',ph:'120',type:'number'}],
  endpoint:    [{k:'hostname',l:'Hostname',ph:'laptop-user01'},{k:'ip_address',l:'IP',ph:'192.168.10.25'},{k:'os',l:'Sistema Operativo',ph:'Windows 11 Pro'},{k:'serial_number',l:'Número de serie',ph:'SN98765'},{k:'assigned_to',l:'Asignado a',ph:'usuario@empresa.com'},{k:'warranty_date',l:'Garantía hasta',ph:'2026-12-31',type:'date'}],
  storage:     [{k:'hostname',l:'Host/NAS',ph:'nas-prod-01'},{k:'ip_address',l:'IP',ph:'10.0.2.10'},{k:'capacity_tb',l:'Capacidad (TB)',ph:'20',type:'number'},{k:'used_tb',l:'Usado (TB)',ph:'8',type:'number'},{k:'protocol',l:'Protocolo',ph:'NFS / iSCSI / SMB'},{k:'vendor',l:'Fabricante',ph:'NetApp'}],
  other:       [{k:'hostname',l:'Hostname',ph:''},{k:'ip_address',l:'IP',ph:''},{k:'version',l:'Versión',ph:''},{k:'serial_number',l:'Serie',ph:''},{k:'location',l:'Ubicación',ph:''}],
}
const STATUS_CFG = {active:{label:'Activo',color:'var(--success)'},maintenance:{label:'Mantenimiento',color:'var(--warning)'},decommissioned:{label:'Retirado',color:'var(--danger)'}}
const ENV_CFG   = {production:{label:'Producción',color:'var(--danger)'},staging:{label:'Staging',color:'var(--warning)'},dev:{label:'Dev',color:'var(--accent)'}}
const REL_TYPES = ['depends_on','runs_on','connects_to','hosts','monitors','backs_up']

function CMDBItemForm({ item, categories, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!item?.id
  // Extraer campos específicos desde item.attributes al editar
  const existingAttrs = item?.attributes || {}
  const [form, setForm] = useState({
    name:        item?.name        || '',
    ci_type:     item?.ci_type     || 'server',
    category_id: item?.category_id || '',
    status:      item?.status      || 'active',
    environment: item?.environment || 'production',
    description: item?.description || '',
    ip_address:  item?.ip_address  || '',
    hostname:    item?.hostname    || '',
    version:     item?.version     || '',
    attributes:  existingAttrs,
    // Campos específicos por tipo — inicializados desde attributes
    ...existingAttrs,
  })
  const set = k => v => setForm(f => ({...f, [k]: v}))

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit
      ? api.patch(`/cmdb/items/${item.id}`, d).then(r => r.data)
      : api.post('/cmdb/items', d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['cmdb-items']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar activo' : 'Nuevo activo IT'}>
      <div style={{display:'flex',flexDirection:'column',gap:14}}>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
          <div>
            <label style={ls}>Nombre</label>
            <input style={is} value={form.name} onChange={e => set('name')(e.target.value)} placeholder="Ej: Servidor Web 01" />
          </div>
          <div>
            <label style={ls}>Tipo</label>
            <select style={is} value={form.ci_type} onChange={e => set('ci_type')(e.target.value)}>
              {CI_TYPES.map(t => <option key={t} value={t}>{CI_TYPE_ICONS[t]} {t}</option>)}
            </select>
          </div>
        </div>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:12}}>
          <div>
            <label style={ls}>Estado</label>
            <select style={is} value={form.status} onChange={e => set('status')(e.target.value)}>
              {Object.entries(STATUS_CFG).map(([v,c]) => <option key={v} value={v}>{c.label}</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>Entorno</label>
            <select style={is} value={form.environment} onChange={e => set('environment')(e.target.value)}>
              {Object.entries(ENV_CFG).map(([v,c]) => <option key={v} value={v}>{c.label}</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>Categoría</label>
            <select style={is} value={form.category_id} onChange={e => set('category_id')(e.target.value)}>
              <option value="">Sin categoría</option>
              {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
        </div>
        {/* Campos específicos por tipo */}
        {(CI_TYPE_FIELDS[form.ci_type] || CI_TYPE_FIELDS.other).length > 0 && (
          <div>
            <div style={{fontSize:11,fontWeight:700,color:'var(--text-3)',textTransform:'uppercase',letterSpacing:'0.06em',marginBottom:10}}>
              {CI_TYPE_ICONS[form.ci_type]} Campos específicos — {form.ci_type}
            </div>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
              {(CI_TYPE_FIELDS[form.ci_type] || CI_TYPE_FIELDS.other).map(field => (
                <div key={field.k}>
                  <label style={ls}>{field.l}</label>
                  <input
                    style={is}
                    type={field.type || 'text'}
                    value={form[field.k] || ''}
                    onChange={e => set(field.k)(e.target.value)}
                    placeholder={field.ph || ''}
                  />
                </div>
              ))}
            </div>
          </div>
        )}
        <div>
          <label style={ls}>Descripción</label>
          <textarea style={{...is, height:70, resize:'vertical'}} value={form.description} onChange={e => set('description')(e.target.value)} />
        </div>
        <div style={{display:'flex',justifyContent:'flex-end',gap:10,marginTop:8}}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.name.trim()} loading={isPending}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar cambios' : 'Crear activo'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function RelationsModal({ item, allItems, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [fromId, _setFromId] = useState(item.id)
  const [toId, setToId] = useState('')
  const [relType, setRelType] = useState('depends_on')

  const { data: rels, isLoading } = useQuery({
    queryKey: ['item-rels', item.id],
    queryFn: () => api.get(`/cmdb/items/${item.id}/relations`).then(r => r.data).catch(() => ({outgoing:[],incoming:[]})),
  })

  const { mutate: createRel, isPending } = useMutation({
    mutationFn: () => api.post('/cmdb/relations', {from_item_id: fromId, to_item_id: toId, rel_type: relType}).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['item-rels', item.id]); setToId('') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: deleteRel } = useMutation({
    mutationFn: id => api.delete(`/cmdb/relations/${id}`),
    onSuccess: () => qc.invalidateQueries(['item-rels', item.id]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <Modal open onClose={onClose} title={`Relaciones — ${item.name}`}>
      <div style={{display:'flex',flexDirection:'column',gap:16}}>
        {isLoading ? <Spinner /> : (
          <div>
            {(rels?.outgoing||[]).length > 0 && (
              <div style={{marginBottom:16}}>
                <div style={{fontSize:11,color:'var(--text-2)',fontWeight:600,textTransform:'uppercase',letterSpacing:'.06em',marginBottom:8}}>Sale de este activo</div>
                {rels.outgoing.map(r => (
                  <div key={r.id} style={{display:'flex',alignItems:'center',gap:10,padding:'8px 12px',background:'var(--surface-1)',borderRadius:6,marginBottom:4,fontSize:12}}>
                    <span style={{color:'var(--accent)'}}>{CI_TYPE_ICONS[r.to_item?.ci_type]||'📌'} {r.to_item?.name}</span>
                    <span style={{color:'var(--text-3)',margin:'0 6px'}}>←</span>
                    <span style={{color:'var(--text-2)'}}>{r.rel_type}</span>
                    <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta relación?', onConfirm: () => deleteRel(r.id), danger: true }) }} style={{marginLeft:'auto',background:'none',border:'none',color:'var(--danger)',cursor:'pointer'}}>✕</button>
                  </div>
                ))}
              </div>
            )}
            {(rels?.incoming||[]).length > 0 && (
              <div style={{marginBottom:16}}>
                <div style={{fontSize:11,color:'var(--text-2)',fontWeight:600,textTransform:'uppercase',letterSpacing:'.06em',marginBottom:8}}>Apunta a este activo</div>
                {rels.incoming.map(r => (
                  <div key={r.id} style={{display:'flex',alignItems:'center',gap:10,padding:'8px 12px',background:'var(--surface-1)',borderRadius:6,marginBottom:4,fontSize:12}}>
                    <span style={{color:'var(--warning)'}}>{CI_TYPE_ICONS[r.from_item?.ci_type]||'📌'} {r.from_item?.name}</span>
                    <span style={{color:'var(--text-3)',margin:'0 6px'}}>→</span>
                    <span style={{color:'var(--text-2)'}}>{r.rel_type}</span>
                  </div>
                ))}
              </div>
            )}
            {(rels?.outgoing||[]).length === 0 && (rels?.incoming||[]).length === 0 && (
              <div style={{textAlign:'center',padding:'20px',color:'var(--text-3)',fontSize:13}}>Sin relaciones definidas</div>
            )}
          </div>
        )}
        <div style={{borderTop:'1px solid var(--surface-4)',paddingTop:14}}>
          <div style={{fontSize:12,fontWeight:600,color:'var(--text-2)',marginBottom:10}}>AÑADIR RELACIÓN</div>
          <div style={{display:'grid',gridTemplateColumns:'1fr auto 1fr',gap:8,alignItems:'center'}}>
            <select style={is} value={toId} onChange={e => setToId(e.target.value)}>
              <option value="">Activo destino...</option>
              {allItems.filter(i => i.id !== item.id).map(i => (
                <option key={i.id} value={i.id}>{CI_TYPE_ICONS[i.ci_type]||'📌'} {i.name}</option>
              ))}
            </select>
            <select style={{...is,width:140}} value={relType} onChange={e => setRelType(e.target.value)}>
              {REL_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div style={{marginTop:10}}>
            <Button onClick={() => createRel()} disabled={isPending || !toId}>
              {isPending ? '...' : 'Añadir relación'}
            </Button>
          </div>
        </div>
        <div style={{display:'flex',justifyContent:'flex-end'}}>
          <Button variant="secondary" onClick={onClose}>Cerrar</Button>
        </div>
      </div>
    </Modal>
  )
}

function ChangelogModal({ item, onClose }) {
  const { data: entries = [], isLoading } = useQuery({
    queryKey: ['cmdb-changelog', item.id],
    queryFn: () => api.get(`/cmdb/items/${item.id}/changelog`).then(r => r.data).catch(() => []),
  })

  const ACTION_COLOR = { created: 'var(--success)', updated: 'var(--accent)', deleted: 'var(--danger)' }
  const ACTION_LABEL = { created: 'Creado', updated: 'Actualizado', deleted: 'Eliminado' }

  return (
    <Modal open onClose={onClose} title={`Historial — ${item.name}`} width={580}>
      {isLoading ? <Spinner /> : entries.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-3)', fontSize: 13 }}>
          Sin cambios registrados
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 480, overflowY: 'auto' }}>
          {entries.map(e => (
            <div key={e.id} style={{ display: 'flex', gap: 14, padding: '10px 14px',
              background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10 }}>
              {/* Línea de tiempo */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                <div style={{ width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
                  background: ACTION_COLOR[e.action] || 'var(--text-3)' }} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, padding: '1px 7px', borderRadius: 20,
                    background: `${ACTION_COLOR[e.action] || 'var(--text-3)'}20`,
                    color: ACTION_COLOR[e.action] || 'var(--text-3)' }}>
                    {ACTION_LABEL[e.action] || e.action}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{e.created_at?.slice(0, 16)}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-2)' }}>por {e.user_name}</span>
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-1)' }}>{e.summary}</div>
                {e.field && (
                  <div style={{ marginTop: 4, fontSize: 11, color: 'var(--text-2)' }}>
                    Campo: <code style={{ background: 'var(--surface-3)', padding: '1px 5px', borderRadius: 4 }}>{e.field}</code>
                    {e.old_value && <span> · <span style={{ color: 'var(--danger)' }}>−{e.old_value}</span></span>}
                    {e.new_value && <span> → <span style={{ color: 'var(--success)' }}>+{e.new_value}</span></span>}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}


export default function CMDBPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [relItem, setRelItem] = useState(null)
  const [historyItem, setHistoryItem] = useState(null)
  const [filterType, setFilterType] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [searchQ, setSearchQ] = useState('')
  const [sortKey, setSortKey] = useState('name')
  const [sortDir, setSortDir] = useState('asc')
  const [tab, setTab] = useState('list')  // 'list' | 'topology'
  const [topoCI, setTopoCI] = useState(null)  // CI selected for topology
  const [topoRadius, setTopoRadius] = useState(2)
  const [drillCI, setDrillCI] = useState(null)  // CI selected for drill-down panel

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  // ─── Drill-down: relations data for the panel ──────────────────────────────
  const { data: drillRels } = useQuery({
    queryKey: ['item-rels', drillCI?.id],
    queryFn: () => drillCI
      ? api.get(`/cmdb/items/${drillCI.id}/relations`).then(r => r.data).catch(() => ({ outgoing: [], incoming: [] }))
      : Promise.resolve({ outgoing: [], incoming: [] }),
    enabled: !!drillCI,
  })

  const { data: categories = [] } = useQuery({
    queryKey: ['cmdb-categories'],
    queryFn: () => api.get('/cmdb/categories').then(r => r.data).catch(() => []),
  })
  const { data: items = [], isLoading } = useQuery({
    queryKey: ['cmdb-items', filterType, filterStatus, searchQ],
    queryFn: () => {
      const p = new URLSearchParams()
      if (filterType)   p.set('ci_type', filterType)
      if (filterStatus) p.set('status', filterStatus)
      if (searchQ)      p.set('q', searchQ)
      return api.get(`/cmdb/items?${p}`).then(r => r.data).catch(() => [])
    },
  })

  const { data: sdTopologyItems = [] } = useQuery({
    queryKey: ['sd-cmdb-topology-items'],
    queryFn: () => api.get('/sd/cmdb').then(r => r.data).catch(() => []),
    enabled: tab === 'topology',
  })

  const { mutate: deleteItem } = useMutation({
    mutationFn: id => api.delete(`/cmdb/items/${id}`),
    onSuccess: () => qc.invalidateQueries(['cmdb-items']),
    onError: e => toast.error(extractErr(e, 'Error al eliminar')),
  })

  const typeCounts = CI_TYPES.reduce((acc, t) => ({...acc, [t]: items.filter(i => i.ci_type === t).length}), {})

  const sortedItems = [...items].sort((a, b) => {
    const va = a[sortKey] ?? ''
    const vb = b[sortKey] ?? ''
    const cmp = typeof va === 'number' ? va - vb : String(va).localeCompare(String(vb))
    return sortDir === 'asc' ? cmp : -cmp
  })

  const { data: topoData, isFetching: topoLoading } = useQuery({
    queryKey: ['cmdb-topology', topoCI?.id, topoRadius],
    queryFn: () => topoCI
      ? api.get(`/sd/cmdb/${topoCI.id}/topology?radius=${topoRadius}`).then(r => r.data).catch(() => ({ nodes: [], edges: [] }))
      : Promise.resolve({ nodes: [], edges: [] }),
    enabled: tab === 'topology' && !!topoCI,
  })

  return (
    <div style={{padding:32}}>
      <PageHeader icon={<Database size={18} />} title={t('cmdb.title')} subtitle={t('cmdb.subtitle')}
        actions={<Button onClick={() => { setEditing(null); setShowForm(true) }}>+ Nuevo activo</Button>} />

      {/* Tabs */}
      <div style={{display:'flex',gap:4,marginBottom:20,borderBottom:'1px solid var(--surface-4)',paddingBottom:0}}>
        {[['list','📋 Inventario'],['topology','🔗 Topología']].map(([id,label]) => (
          <button key={id} onClick={() => setTab(id)}
            style={{padding:'8px 18px',fontSize:13,fontWeight:tab===id?700:400,
              color:tab===id?'var(--accent)':'var(--text-2)',background:'transparent',
              border:'none',borderBottom:tab===id?'2px solid var(--accent)':'2px solid transparent',
              cursor:'pointer',fontFamily:'inherit',transition:'color .15s'}}>
            {label}
          </button>
        ))}
      </div>

      {/* ─── TOPOLOGÍA ─────────────────────────────────────────────── */}
      {tab === 'topology' && (
        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
          {/* Graph panel */}
          <div style={{ ...ps, flex: 1, minWidth: 0 }}>
            {/* Selector de CI */}
            <div style={{display:'flex',gap:12,alignItems:'flex-end',marginBottom:20,flexWrap:'wrap'}}>
              <div style={{flex:'1 1 280px'}}>
                <label style={ls}>CI central</label>
                <select style={is} value={topoCI?.id || ''} onChange={e => {
                  const ci = sdTopologyItems.find(i => i.id === e.target.value)
                  setTopoCI(ci || null)
                  setDrillCI(null)
                }}>
                  <option value="">Seleccionar CI…</option>
                  {sdTopologyItems.map(ci => <option key={ci.id} value={ci.id}>{CI_TYPE_ICONS[ci.ci_type]||'📌'} {ci.name}</option>)}
                </select>
              </div>
              <div>
                <label style={ls}>Radio de expansión</label>
                <select style={{...is,width:120}} value={topoRadius} onChange={e => setTopoRadius(Number(e.target.value))}>
                  {[1,2,3].map(r => <option key={r} value={r}>{r} {r===1?'nivel':'niveles'}</option>)}
                </select>
              </div>
              {topoCI && (
                <button onClick={() => { setTopoCI(null); setDrillCI(null) }}
                  style={{alignSelf:'flex-end',padding:'8px 14px',borderRadius:8,border:'1px solid var(--surface-4)',
                    background:'transparent',color:'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize:13}}>
                  ✕ Limpiar
                </button>
              )}
            </div>
            {topoLoading
              ? <Spinner />
              : <CMDBTopologyGraph
                  nodes={topoData?.nodes || []}
                  edges={topoData?.edges || []}
                  centerName={topoCI?.name}
                  onNodeClick={n => {
                    const ci = sdTopologyItems.find(i => i.id === n.id) || n
                    setDrillCI(ci)
                  }}
                />
            }
          </div>

          {/* Drill-down panel */}
          {drillCI && (
            <div style={{
              width: 310, flexShrink: 0, background: 'var(--surface-2)',
              border: '1px solid var(--surface-4)', borderRadius: 12,
              padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14,
              maxHeight: 660, overflowY: 'auto',
            }}>
              {/* Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 22 }}>{CI_TYPE_ICONS[drillCI.ci_type] || '📌'}</span>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-1)' }}>{drillCI.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{drillCI.ci_type}</div>
                  </div>
                </div>
                <button
                  onClick={() => setDrillCI(null)}
                  style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: 16, padding: 0 }}
                  aria-label="Cerrar panel de detalle"
                >✕</button>
              </div>

              {/* Status + environment badges */}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {drillCI.status && (
                  <span style={{
                    fontSize: 11, padding: '2px 9px', borderRadius: 20,
                    background: (STATUS_CFG[drillCI.status]?.color || 'var(--text-3)') + '20',
                    color: STATUS_CFG[drillCI.status]?.color || 'var(--text-3)',
                  }}>
                    {STATUS_CFG[drillCI.status]?.label || drillCI.status}
                  </span>
                )}
                {drillCI.environment && (
                  <span style={{
                    fontSize: 11, padding: '2px 9px', borderRadius: 20,
                    background: (ENV_CFG[drillCI.environment]?.color || 'var(--text-3)') + '20',
                    color: ENV_CFG[drillCI.environment]?.color || 'var(--text-3)',
                  }}>
                    {ENV_CFG[drillCI.environment]?.label || drillCI.environment}
                  </span>
                )}
              </div>

              {/* Description */}
              {drillCI.description && (
                <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5 }}>
                  {drillCI.description}
                </div>
              )}

              {/* Key attributes */}
              <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 12 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
                  Atributos
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {[
                    ['Hostname', drillCI.hostname],
                    ['IP', drillCI.ip_address || drillCI.attributes?.ip_address],
                    ['Versión', drillCI.version],
                    ['OS', drillCI.attributes?.os],
                    ['Stack', drillCI.attributes?.tech_stack],
                    ['URL', drillCI.attributes?.url],
                    ['Proveedor cloud', drillCI.attributes?.cloud_provider],
                    ['Región', drillCI.attributes?.region],
                    ['Imagen', drillCI.attributes?.image],
                    ['Cluster', drillCI.attributes?.cluster],
                    ['RAM (GB)', drillCI.attributes?.ram_gb],
                    ['CPU cores', drillCI.attributes?.cpu_cores],
                  ].filter(([, v]) => v).map(([label, value]) => (
                    <div key={label} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 12 }}>
                      <span style={{ color: 'var(--text-3)', flexShrink: 0 }}>{label}</span>
                      <span style={{ color: 'var(--text-1)', fontFamily: 'monospace', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 160 }} title={String(value)}>{value}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Relations */}
              {drillRels && ((drillRels.outgoing?.length > 0) || (drillRels.incoming?.length > 0)) && (
                <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 12 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
                    Relaciones
                  </div>
                  {(drillRels.outgoing || []).map(r => (
                    <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, marginBottom: 4 }}>
                      <span style={{ color: 'var(--accent)' }}>↗</span>
                      <span style={{ color: 'var(--text-2)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.rel_type} → {r.to_item?.name}
                      </span>
                    </div>
                  ))}
                  {(drillRels.incoming || []).map(r => (
                    <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, marginBottom: 4 }}>
                      <span style={{ color: 'var(--warning)' }}>↙</span>
                      <span style={{ color: 'var(--text-2)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.from_item?.name} → {r.rel_type}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Actions */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, borderTop: '1px solid var(--surface-4)', paddingTop: 12 }}>
                <Button
                  onClick={() => {
                    const ci = sdTopologyItems.find(i => i.id === drillCI.id) || drillCI
                    setTopoCI(ci)
                    setDrillCI(null)
                  }}
                >
                  🔗 Ver como CI central
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => { setEditing(drillCI); setShowForm(true) }}
                >
                  ✏ Editar activo
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─── INVENTARIO ─────────────────────────────────────────────── */}
      {tab === 'list' && <>
      {/* KPIs */}
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:12,marginBottom:20}}>
        {[
          ['Total activos', items.length, 'var(--text-1)'],
          ['Activos', items.filter(i=>i.status==='active').length, 'var(--success)'],
          ['Mantenimiento', items.filter(i=>i.status==='maintenance').length, 'var(--warning)'],
          ['Retirados', items.filter(i=>i.status==='decommissioned').length, 'var(--danger)'],
        ].map(([label,val,color]) => (
          <div key={label} style={{...ps,padding:'14px 16px'}}>
            <div style={{fontSize:24,fontWeight:700,color}}>{val}</div>
            <div style={{fontSize:11,color:'var(--text-2)',textTransform:'uppercase',letterSpacing:'.07em'}}>{label}</div>
          </div>
        ))}
      </div>

      {/* Filtros */}
      <div style={{...ps,marginBottom:20}}>
        <div style={{display:'grid',gridTemplateColumns:'1fr auto auto auto',gap:12,alignItems:'flex-end'}}>
          <div>
            <label style={ls}>Buscar</label>
            <input value={searchQ} onChange={e => setSearchQ(e.target.value)}
              placeholder="Buscar activos..." style={is} />
          </div>
          <div>
            <label style={ls}>Tipo</label>
            <select value={filterType} onChange={e => setFilterType(e.target.value)} style={{...is,width:160}}>
              <option value="">Todos los tipos</option>
              {CI_TYPES.map(t => <option key={t} value={t}>{CI_TYPE_ICONS[t]} {t} ({typeCounts[t]||0})</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>Estado</label>
            <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={{...is,width:160}}>
              <option value="">Todos</option>
              {Object.entries(STATUS_CFG).map(([v,c]) => <option key={v} value={v}>{c.label}</option>)}
            </select>
          </div>
          {(filterType||filterStatus||searchQ) && (
            <button onClick={() => {setFilterType('');setFilterStatus('');setSearchQ('')}}
              style={{alignSelf:'flex-end',padding:'8px 14px',borderRadius:8,border:'1px solid var(--surface-4)',background:'transparent',color:'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize:13}}>
              ✕ Limpiar
            </button>
          )}
        </div>
      </div>

      {isLoading ? <Spinner /> : items.length === 0 ? (
        <div style={{...ps,textAlign:'center',padding:'48px 24px'}}>
          <div style={{fontSize:48,marginBottom:16}}>🖥️</div>
          <div style={{fontSize:15,fontWeight:600,marginBottom:8}}>Sin activos IT</div>
          <div style={{fontSize:13,color:'var(--text-2)',marginBottom:20}}>Registra servidores, aplicaciones, bases de datos y otros activos de tu infraestructura.</div>
          <Button onClick={() => { setEditing(null); setShowForm(true) }}>+ Añadir primer activo</Button>
        </div>
      ) : (
        <div style={ps}>
          <table style={{width:'100%',borderCollapse:'collapse',fontSize:13}}>
            <thead>
              <tr style={{borderBottom:'1px solid var(--surface-4)'}}>
              {[['name','Activo'],['ci_type','Tipo'],['status','Estado'],['environment','Entorno'],['hostname','Hostname / IP'],['version','Versión']].map(([key, label]) => (
                <th key={key} onClick={() => toggleSort(key)}
                  style={{textAlign:'left',padding:'8px 12px',fontSize:11,cursor:'pointer',userSelect:'none',whiteSpace:'nowrap',
                    color: sortKey === key ? 'var(--accent)' : 'var(--text-2)',
                    textTransform:'uppercase',letterSpacing:'.06em'}}>
                  {label}{sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
                </th>
              ))}
              <th style={{padding:'8px 12px'}}></th>
              </tr>
            </thead>
            <tbody>
              {sortedItems.map((item, i) => {
                const sc = STATUS_CFG[item.status] || STATUS_CFG.active
                const ec = ENV_CFG[item.environment] || ENV_CFG.production
                return (
                  <tr key={item.id} style={{borderBottom:'1px solid #1a2640',background:i%2===0?'transparent':'rgba(255,255,255,0.02)'}}>
                    <td style={{padding:'10px 12px'}}>
                      <div style={{display:'flex',alignItems:'center',gap:8}}>
                        <span style={{fontSize:16}}>{CI_TYPE_ICONS[item.ci_type]||'📌'}</span>
                        <div>
                          <div style={{fontWeight:600}}>{item.name}</div>
                          {item.description && <div style={{fontSize:11,color:'var(--text-2)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',maxWidth:200}}>{item.description}</div>}
                        </div>
                      </div>
                    </td>
                    <td style={{padding:'10px 12px',color:'var(--text-2)',fontSize:12}}>{item.ci_type}</td>
                    <td style={{padding:'10px 12px'}}>
                      <span style={{fontSize:11,padding:'2px 8px',borderRadius:20,
                        background:sc.color+'20',color:sc.color}}>{sc.label}</span>
                    </td>
                    <td style={{padding:'10px 12px'}}>
                      <span style={{fontSize:11,padding:'2px 8px',borderRadius:20,
                        background:ec.color+'20',color:ec.color}}>{ec.label}</span>
                    </td>
                    <td style={{padding:'10px 12px',fontSize:12,color:'var(--text-2)'}}>
                      {/* Mostrar info relevante según el tipo de CI */}
                      {(item.ci_type === 'server' || item.ci_type === 'network' || item.ci_type === 'endpoint' || item.ci_type === 'storage') && (
                        <>
                          {item.hostname && <div style={{fontFamily:'monospace',fontSize:12}}>{item.hostname}</div>}
                          {(item.ip_address || (item.attributes||{}).ip_address) && (
                            <div style={{fontFamily:'monospace',fontSize:11,color:'var(--text-3)'}}>
                              {item.ip_address || (item.attributes||{}).ip_address}
                            </div>
                          )}
                          {(item.attributes||{}).os && <div style={{fontSize:11,color:'var(--text-3)'}}>{(item.attributes||{}).os}</div>}
                        </>
                      )}
                      {item.ci_type === 'application' && (
                        <>
                          {(item.attributes||{}).url && <div style={{fontSize:11,color:'var(--accent)',overflow:'hidden',textOverflow:'ellipsis',maxWidth:180}}>{(item.attributes||{}).url}</div>}
                          {(item.attributes||{}).tech_stack && <div style={{fontSize:11,color:'var(--text-3)'}}>{(item.attributes||{}).tech_stack}</div>}
                          {(item.attributes||{}).sla_tier && <span style={{fontSize:10,background:'var(--accent-muted)',color:'var(--accent)',padding:'1px 6px',borderRadius:4}}>{(item.attributes||{}).sla_tier}</span>}
                        </>
                      )}
                      {item.ci_type === 'database' && (
                        <>
                          {(item.attributes||{}).db_engine && <div style={{fontFamily:'monospace',fontSize:12}}>{(item.attributes||{}).db_engine}</div>}
                          {item.hostname && <div style={{fontFamily:'monospace',fontSize:11,color:'var(--text-3)'}}>{item.hostname}{(item.attributes||{}).port ? ':' + (item.attributes||{}).port : ''}</div>}
                        </>
                      )}
                      {item.ci_type === 'cloud' && (
                        <>
                          {(item.attributes||{}).cloud_provider && <div style={{fontSize:12}}>{(item.attributes||{}).cloud_provider}</div>}
                          {(item.attributes||{}).region && <div style={{fontSize:11,color:'var(--text-3)'}}>{(item.attributes||{}).region}</div>}
                          {(item.attributes||{}).instance_type && <div style={{fontSize:11,fontFamily:'monospace'}}>{(item.attributes||{}).instance_type}</div>}
                        </>
                      )}
                      {item.ci_type === 'container' && (
                        <>
                          {(item.attributes||{}).image && <div style={{fontFamily:'monospace',fontSize:11}}>{(item.attributes||{}).image}</div>}
                          {(item.attributes||{}).cluster && <div style={{fontSize:11,color:'var(--text-3)'}}>{(item.attributes||{}).cluster}{(item.attributes||{}).namespace ? ' / ' + (item.attributes||{}).namespace : ''}</div>}
                        </>
                      )}
                      {item.ci_type === 'service' && (
                        <>
                          {(item.attributes||{}).url && <div style={{fontSize:11,color:'var(--accent)'}}>{(item.attributes||{}).url}</div>}
                          {(item.attributes||{}).owner_team && <div style={{fontSize:11,color:'var(--text-3)'}}>{(item.attributes||{}).owner_team}</div>}
                        </>
                      )}
                    </td>
                    <td style={{padding:'10px 12px',fontSize:12,color:'var(--text-2)',fontFamily:'monospace'}}>{item.version||'—'}</td>
                    <td style={{padding:'10px 12px'}}>
                      <div style={{display:'flex',gap:6}}>
                        <button onClick={() => setHistoryItem(item)}
                          style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'4px 8px',color:'var(--text-2)',cursor:'pointer',fontSize:11}} title="Ver historial de cambios">📋</button>
                        <button onClick={() => setRelItem(item)}
                          style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'4px 8px',color:'var(--text-2)',cursor:'pointer',fontSize:11}}>🔗</button>
                        <button onClick={() => { setEditing(item); setShowForm(true) }}
                          style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'4px 8px',color:'var(--text-2)',cursor:'pointer',fontSize:11}}>✏</button>
                        <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar "${item.name}"?`, onConfirm: () => deleteItem(item.id), danger: true }) }}
                          style={{background:'none',border:'1px solid #ff475730',borderRadius:6,padding:'4px 8px',color:'var(--danger)',cursor:'pointer',fontSize:11}}>🗑</button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      </>}

      {showForm && <CMDBItemForm item={editing} categories={categories} onClose={() => { setShowForm(false); setEditing(null) }} />}
      {relItem && <RelationsModal item={relItem} allItems={items} onClose={() => setRelItem(null)} />}
      {historyItem && <ChangelogModal item={historyItem} onClose={() => setHistoryItem(null)} />}
    </div>
  )
}
