import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { cmdbApi } from '../services/api'
import { Button, Spinner, Modal, Tabs } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Database } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import CMDBTopologyGraph from '../components/cmdb/CMDBTopologyGraph'
import Cmdb3dGraph from '../components/servicedesk/Cmdb3dGraph'

const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

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
      ? cmdbApi.updateItem(item.id, d).then(r => r.data)
      : cmdbApi.createItem(d).then(r => r.data),
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
            <div style={{fontSize: "var(--text-xs)",fontWeight:700,color:'var(--text-3)',textTransform:'uppercase',letterSpacing:'0.06em',marginBottom:10}}>
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
    queryFn: () => cmdbApi.relations(item.id).then(r => r.data).catch(() => ({outgoing:[],incoming:[]})),
  })

  const { mutate: createRel, isPending } = useMutation({
    mutationFn: () => cmdbApi.createRelation({from_item_id: fromId, to_item_id: toId, rel_type: relType}).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['item-rels', item.id]); setToId('') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: deleteRel } = useMutation({
    mutationFn: id => cmdbApi.deleteRelation(id),
    onSuccess: () => qc.invalidateQueries(['item-rels', item.id]),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <Modal open onClose={onClose} title={`Relaciones — ${item.name}`}>
      <div style={{display:'flex',flexDirection:'column',gap:16}}>
        {isLoading ? <Spinner /> : (
          <div>
            {(rels?.outgoing||[]).length > 0 && (
              <div style={{marginBottom:16}}>
                <div style={{fontSize: "var(--text-xs)",color:'var(--text-2)',fontWeight:600,textTransform:'uppercase',letterSpacing:'.06em',marginBottom:8}}>Sale de este activo</div>
                {rels.outgoing.map(r => (
                  <div key={r.id} style={{display:'flex',alignItems:'center',gap:10,padding:'8px 12px',background:'var(--surface-1)',borderRadius:6,marginBottom:4,fontSize: "var(--text-sm)"}}>
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
                <div style={{fontSize: "var(--text-xs)",color:'var(--text-2)',fontWeight:600,textTransform:'uppercase',letterSpacing:'.06em',marginBottom:8}}>Apunta a este activo</div>
                {rels.incoming.map(r => (
                  <div key={r.id} style={{display:'flex',alignItems:'center',gap:10,padding:'8px 12px',background:'var(--surface-1)',borderRadius:6,marginBottom:4,fontSize: "var(--text-sm)"}}>
                    <span style={{color:'var(--warning)'}}>{CI_TYPE_ICONS[r.from_item?.ci_type]||'📌'} {r.from_item?.name}</span>
                    <span style={{color:'var(--text-3)',margin:'0 6px'}}>→</span>
                    <span style={{color:'var(--text-2)'}}>{r.rel_type}</span>
                  </div>
                ))}
              </div>
            )}
            {(rels?.outgoing||[]).length === 0 && (rels?.incoming||[]).length === 0 && (
              <div style={{textAlign:'center',padding:'20px',color:'var(--text-3)',fontSize: "var(--text-base)"}}>Sin relaciones definidas</div>
            )}
          </div>
        )}
        <div style={{borderTop:'1px solid var(--surface-4)',paddingTop:14}}>
          <div style={{fontSize: "var(--text-sm)",fontWeight:600,color:'var(--text-2)',marginBottom:10}}>AÑADIR RELACIÓN</div>
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
    queryFn: () => cmdbApi.changelog(item.id).then(r => r.data).catch(() => []),
  })

  const ACTION_COLOR = { created: 'var(--success)', updated: 'var(--accent)', deleted: 'var(--danger)' }
  const ACTION_LABEL = { created: 'Creado', updated: 'Actualizado', deleted: 'Eliminado' }

  return (
    <Modal open onClose={onClose} title={`Historial — ${item.name}`} width={580}>
      {isLoading ? <Spinner /> : entries.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-3)', fontSize: "var(--text-base)" }}>
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
                  <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, padding: '1px 7px', borderRadius: 20,
                    background: `${ACTION_COLOR[e.action] || 'var(--text-3)'}20`,
                    color: ACTION_COLOR[e.action] || 'var(--text-3)' }}>
                    {ACTION_LABEL[e.action] || e.action}
                  </span>
                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{e.created_at?.slice(0, 16)}</span>
                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>por {e.user_name}</span>
                </div>
                <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)' }}>{e.summary}</div>
                {e.field && (
                  <div style={{ marginTop: 4, fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
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


// ── Linked assets for a CI (drill-down panel) ────────────────────────────────
function CILinkedAssets({ ciId }) {
  const { data: assets, isLoading } = useQuery({
    queryKey: ['ci-assets', ciId],
    queryFn: () => cmdbApi.assetsByCI(ciId).then(r => r.data?.assets || []).catch(() => []),
    staleTime: 30000,
  })
  if (isLoading) return null
  if (!assets?.length) return (
    <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 12, marginBottom: 8 }}>
      <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 6 }}>Activos vinculados</div>
      <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>Ningún activo vinculado a este CI.</div>
    </div>
  )
  return (
    <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 12, marginBottom: 8 }}>
      <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
        Activos vinculados ({assets.length})
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {assets.map(a => (
          <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--surface-4)', borderRadius: 6, padding: '6px 10px' }}>
            <span style={{ fontSize: "var(--text-base)" }}>{CI_TYPE_ICONS[a.asset_type] || '📦'}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</div>
              {a.serial_number && <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>S/N: {a.serial_number}</div>}
            </div>
            <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', background: 'var(--surface-3)', padding: '2px 6px', borderRadius: 3, whiteSpace: 'nowrap' }}>{a.status || 'activo'}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── CMDB Agents on-prem tab ──────────────────────────────────────────────────
function CMDBAgentsTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const [agentName, setAgentName] = useState('')
  const [platform, setPlatform] = useState('linux')
  const [newToken, setNewToken] = useState(null)

  const { data: agentsData, isLoading } = useQuery({
    queryKey: ['cmdb-agents'],
    queryFn: () => api.get('/sd/cmdb/agents').then(r => r.data).catch(() => []),
    refetchInterval: 15000,
  })
  const agents = Array.isArray(agentsData)
    ? agentsData
    : (agentsData?.agents || agentsData?.items || [])

  const { mutate: registerAgent, isPending } = useMutation({
    mutationFn: () => api.post('/sd/cmdb/agents/register', { name: agentName.trim(), platform }),
    onSuccess: (res) => {
      toast.success('Agente registrado')
      setNewToken(res.data?.token ?? res.data?.registration_token ?? null)
      setAgentName('')
      qc.invalidateQueries({ queryKey: ['cmdb-agents'] })
    },
    onError: () => toast.error('Error al registrar agente'),
  })

  const { mutate: deleteAgent } = useMutation({
    mutationFn: (id) => api.delete(`/sd/cmdb/agents/${id}`),
    onSuccess: () => { toast.success('Agente eliminado'); qc.invalidateQueries({ queryKey: ['cmdb-agents'] }) },
    onError: () => toast.error('Error al eliminar agente'),
  })

  const inputStyle = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const labelStyle = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '.07em', display: 'block', marginBottom: 5 }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Registration form */}
      <div style={{ ...ps }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 16 }}>
          🤖 Registrar nuevo agente on-prem
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 12, alignItems: 'flex-end' }}>
          <div>
            <label style={labelStyle}>Nombre del agente</label>
            <input value={agentName} onChange={e => setAgentName(e.target.value)} style={inputStyle} placeholder="agent-datacenter-01" />
          </div>
          <div>
            <label style={labelStyle}>Plataforma</label>
            <select value={platform} onChange={e => setPlatform(e.target.value)} style={{ ...inputStyle, width: 120 }}>
              <option value="linux">🐧 Linux</option>
              <option value="windows">🪟 Windows</option>
              <option value="macos">🍎 macOS</option>
            </select>
          </div>
          <Button onClick={() => registerAgent()} loading={isPending} disabled={!agentName.trim()}>
            Registrar
          </Button>
        </div>

        {/* Show token after registration */}
        {newToken && (
          <div style={{ marginTop: 16, background: 'rgba(99,179,237,0.08)', border: '1px solid rgba(99,179,237,0.3)', borderRadius: 10, padding: '14px 18px' }}>
            <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--info)', textTransform: 'uppercase', marginBottom: 8 }}>
              🔑 Token de registro (úsalo una sola vez)
            </div>
            <code style={{ display: 'block', fontSize: "var(--text-sm)", color: 'var(--text-1)', wordBreak: 'break-all', fontFamily: 'var(--font-mono)', background: 'var(--surface-4)', padding: '8px 12px', borderRadius: 6 }}>
              {newToken}
            </code>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 8 }}>
              Ejecuta el agente con: <code style={{ fontFamily: 'var(--font-mono)' }}>CMDB_TOKEN={newToken} ./cmdb-agent</code>
            </div>
            <button onClick={() => setNewToken(null)} style={{ marginTop: 10, background: 'none', border: 'none', color: 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
              Ocultar token
            </button>
          </div>
        )}
      </div>

      {/* Registered agents list */}
      <div style={{ ...ps }}>
        <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 16 }}>
          📋 Agentes registrados ({agents.length})
        </div>
        {isLoading ? <Spinner /> :
         agents.length === 0 ? (
           <div style={{ textAlign: 'center', padding: 32, color: 'var(--text-3)', fontSize: "var(--text-base)" }}>
             No hay agentes registrados. Registra el primero arriba.
           </div>
         ) : (
           <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-base)" }}>
             <thead>
               <tr style={{ borderBottom: '1px solid var(--surface-4)' }}>
                 {['Nombre', 'Plataforma', 'Estado', 'Último ping', 'CIs descubiertos', ''].map(h => (
                   <th key={h} style={{ padding: '8px 10px', textAlign: 'left', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase' }}>{h}</th>
                 ))}
               </tr>
             </thead>
             <tbody>
               {agents.map(ag => (
                 <tr key={ag.id} style={{ borderBottom: '1px solid var(--surface-4)' }}>
                   <td style={{ padding: '10px 10px', fontWeight: 600, color: 'var(--text-1)' }}>{ag.name}</td>
                   <td style={{ padding: '10px 10px', color: 'var(--text-2)' }}>
                     {ag.platform === 'linux' ? '🐧' : ag.platform === 'windows' ? '🪟' : '🍎'} {ag.platform}
                   </td>
                   <td style={{ padding: '10px 10px' }}>
                     <span style={{ fontSize: "var(--text-xs)", fontWeight: 600, padding: '2px 8px', borderRadius: 4, background: ag.status === 'active' ? 'rgba(72,187,120,0.15)' : 'rgba(160,174,192,0.15)', color: ag.status === 'active' ? '#48bb78' : 'var(--text-2)' }}>
                       {ag.status || 'pendiente'}
                     </span>
                   </td>
                   <td style={{ padding: '10px 10px', color: 'var(--text-3)', fontSize: "var(--text-sm)" }}>
                     {ag.last_ping ? new Date(ag.last_ping).toLocaleString() : '—'}
                   </td>
                   <td style={{ padding: '10px 10px', color: 'var(--text-2)', textAlign: 'center' }}>
                     {ag.discovered_count ?? '—'}
                   </td>
                   <td style={{ padding: '10px 10px' }}>
                     <button onClick={() => openConfirmGlobal({ message: `¿Eliminar agente "${ag.name}"?`, onConfirm: () => deleteAgent(ag.id), danger: true })} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>🗑</button>
                   </td>
                 </tr>
               ))}
             </tbody>
           </table>
         )
        }
      </div>
    </div>
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
      ? cmdbApi.relations(drillCI.id).then(r => r.data).catch(() => ({ outgoing: [], incoming: [] }))
      : Promise.resolve({ outgoing: [], incoming: [] }),
    enabled: !!drillCI,
  })

  const { data: categories = [] } = useQuery({
    queryKey: ['cmdb-categories'],
    queryFn: () => cmdbApi.categories().then(r => r.data?.items ?? r.data ?? []).catch(() => []),
  })
  const { data: items = [], isLoading } = useQuery({
    queryKey: ['cmdb-items', filterType, filterStatus, searchQ],
    queryFn: () => {
      const p = {}
      if (filterType)   p.ci_type = filterType
      if (filterStatus) p.status  = filterStatus
      if (searchQ)      p.q       = searchQ
      return cmdbApi.items(p).then(r => r.data?.items ?? r.data ?? []).catch(() => [])
    },
  })

  const { data: sdTopologyItems = [] } = useQuery({
    queryKey: ['sd-cmdb-topology-items'],
    queryFn: () => cmdbApi.topologyItems().then(r => r.data).catch(() => []),
    enabled: tab === 'topology',
  })

  const { mutate: deleteItem } = useMutation({
    mutationFn: id => cmdbApi.deleteItem(id),
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
      ? cmdbApi.topology(topoCI.id, topoRadius).then(r => r.data).catch(() => ({ nodes: [], edges: [] }))
      : Promise.resolve({ nodes: [], edges: [] }),
    enabled: tab === 'topology' && !!topoCI,
  })

  return (
    <PageShell>
      <PageHeader icon={<Database size={18} />} title={t('cmdb.title')} subtitle={t('cmdb.subtitle')}
        actions={<Button onClick={() => { setEditing(null); setShowForm(true) }}>+ Nuevo activo</Button>} />

      <Tabs
        items={[
          { id: 'list',     label: '📋 Inventario' },
          { id: 'topology', label: '🔗 Topología' },
          { id: '3d',       label: '🌐 3D / Blast Radius' },
          { id: 'agents',   label: '🤖 Agentes on-prem' },
        ]}
        active={tab}
        onChange={setTab}
        ariaLabel="CMDB"
      />

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
                    background:'transparent',color:'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize: "var(--text-base)"}}>
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
                  <span style={{ fontSize: "var(--text-xl-em)" }}>{CI_TYPE_ICONS[drillCI.ci_type] || '📌'}</span>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: "var(--text-md)", color: 'var(--text-1)' }}>{drillCI.name}</div>
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{drillCI.ci_type}</div>
                  </div>
                </div>
                <button
                  onClick={() => setDrillCI(null)}
                  style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: "var(--text-lg)", padding: 0 }}
                  aria-label="Cerrar panel de detalle"
                >✕</button>
              </div>

              {/* Status + environment badges */}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {drillCI.status && (
                  <span style={{
                    fontSize: "var(--text-xs)", padding: '2px 9px', borderRadius: 20,
                    background: (STATUS_CFG[drillCI.status]?.color || 'var(--text-3)') + '20',
                    color: STATUS_CFG[drillCI.status]?.color || 'var(--text-3)',
                  }}>
                    {STATUS_CFG[drillCI.status]?.label || drillCI.status}
                  </span>
                )}
                {drillCI.environment && (
                  <span style={{
                    fontSize: "var(--text-xs)", padding: '2px 9px', borderRadius: 20,
                    background: (ENV_CFG[drillCI.environment]?.color || 'var(--text-3)') + '20',
                    color: ENV_CFG[drillCI.environment]?.color || 'var(--text-3)',
                  }}>
                    {ENV_CFG[drillCI.environment]?.label || drillCI.environment}
                  </span>
                )}
              </div>

              {/* Description */}
              {drillCI.description && (
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.5 }}>
                  {drillCI.description}
                </div>
              )}

              {/* Key attributes */}
              <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 12 }}>
                <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
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
                    <div key={label} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: "var(--text-sm)" }}>
                      <span style={{ color: 'var(--text-3)', flexShrink: 0 }}>{label}</span>
                      <span style={{ color: 'var(--text-1)', fontFamily: 'var(--font-mono)', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 160 }} title={String(value)}>{value}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Relations */}
              {drillRels && ((drillRels.outgoing?.length > 0) || (drillRels.incoming?.length > 0)) && (
                <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 12 }}>
                  <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
                    Relaciones
                  </div>
                  {(drillRels.outgoing || []).map(r => (
                    <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: "var(--text-xs)", marginBottom: 4 }}>
                      <span style={{ color: 'var(--accent)' }}>↗</span>
                      <span style={{ color: 'var(--text-2)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.rel_type} → {r.to_item?.name}
                      </span>
                    </div>
                  ))}
                  {(drillRels.incoming || []).map(r => (
                    <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: "var(--text-xs)", marginBottom: 4 }}>
                      <span style={{ color: 'var(--warning)' }}>↙</span>
                      <span style={{ color: 'var(--text-2)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.from_item?.name} → {r.rel_type}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Linked Assets */}
              <CILinkedAssets ciId={drillCI.id} />

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
            <div style={{fontSize: "var(--text-2xl)",fontWeight:700,color}}>{val}</div>
            <div style={{fontSize: "var(--text-xs)",color:'var(--text-2)',textTransform:'uppercase',letterSpacing:'.07em'}}>{label}</div>
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
              style={{alignSelf:'flex-end',padding:'8px 14px',borderRadius:8,border:'1px solid var(--surface-4)',background:'transparent',color:'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize: "var(--text-base)"}}>
              ✕ Limpiar
            </button>
          )}
        </div>
      </div>

      {isLoading ? <Spinner /> : items.length === 0 ? (
        <div style={{...ps,textAlign:'center',padding:'48px 24px'}}>
          <div style={{fontSize: "var(--text-6xl)",marginBottom:16}}>🖥️</div>
          <div style={{fontSize: "var(--text-md-em)",fontWeight:600,marginBottom:8}}>Sin activos IT</div>
          <div style={{fontSize: "var(--text-base)",color:'var(--text-2)',marginBottom:20}}>Registra servidores, aplicaciones, bases de datos y otros activos de tu infraestructura.</div>
          <Button onClick={() => { setEditing(null); setShowForm(true) }}>+ Añadir primer activo</Button>
        </div>
      ) : (
        <div style={ps}>
          <table style={{width:'100%',borderCollapse:'collapse',fontSize: "var(--text-base)"}}>
            <thead>
              <tr style={{borderBottom:'1px solid var(--surface-4)'}}>
              {[['name','Activo'],['ci_type','Tipo'],['status','Estado'],['environment','Entorno'],['hostname','Hostname / IP'],['version','Versión']].map(([key, label]) => (
                <th key={key} onClick={() => toggleSort(key)}
                  style={{textAlign:'left',padding:'8px 12px',fontSize: "var(--text-xs)",cursor:'pointer',userSelect:'none',whiteSpace:'nowrap',
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
                  <tr key={item.id} style={{borderBottom:'1px solid var(--surface-4)',background:i%2===0?'transparent':'rgba(255,255,255,0.02)'}}>
                    <td style={{padding:'10px 12px'}}>
                      <div style={{display:'flex',alignItems:'center',gap:8}}>
                        <span style={{fontSize: "var(--text-lg)"}}>{CI_TYPE_ICONS[item.ci_type]||'📌'}</span>
                        <div>
                          <div style={{fontWeight:600}}>{item.name}</div>
                          {item.description && <div style={{fontSize: "var(--text-xs)",color:'var(--text-2)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',maxWidth:200}}>{item.description}</div>}
                        </div>
                      </div>
                    </td>
                    <td style={{padding:'10px 12px',color:'var(--text-2)',fontSize: "var(--text-sm)"}}>{item.ci_type}</td>
                    <td style={{padding:'10px 12px'}}>
                      <span style={{fontSize: "var(--text-xs)",padding:'2px 8px',borderRadius:20,
                        background:sc.color+'20',color:sc.color}}>{sc.label}</span>
                    </td>
                    <td style={{padding:'10px 12px'}}>
                      <span style={{fontSize: "var(--text-xs)",padding:'2px 8px',borderRadius:20,
                        background:ec.color+'20',color:ec.color}}>{ec.label}</span>
                    </td>
                    <td style={{padding:'10px 12px',fontSize: "var(--text-sm)",color:'var(--text-2)'}}>
                      {/* Mostrar info relevante según el tipo de CI */}
                      {(item.ci_type === 'server' || item.ci_type === 'network' || item.ci_type === 'endpoint' || item.ci_type === 'storage') && (
                        <>
                          {item.hostname && <div style={{fontFamily:'var(--font-mono)',fontSize: "var(--text-sm)"}}>{item.hostname}</div>}
                          {(item.ip_address || (item.attributes||{}).ip_address) && (
                            <div style={{fontFamily:'var(--font-mono)',fontSize: "var(--text-xs)",color:'var(--text-3)'}}>
                              {item.ip_address || (item.attributes||{}).ip_address}
                            </div>
                          )}
                          {(item.attributes||{}).os && <div style={{fontSize: "var(--text-xs)",color:'var(--text-3)'}}>{(item.attributes||{}).os}</div>}
                        </>
                      )}
                      {item.ci_type === 'application' && (
                        <>
                          {(item.attributes||{}).url && <div style={{fontSize: "var(--text-xs)",color:'var(--accent)',overflow:'hidden',textOverflow:'ellipsis',maxWidth:180}}>{(item.attributes||{}).url}</div>}
                          {(item.attributes||{}).tech_stack && <div style={{fontSize: "var(--text-xs)",color:'var(--text-3)'}}>{(item.attributes||{}).tech_stack}</div>}
                          {(item.attributes||{}).sla_tier && <span style={{fontSize: "var(--text-2xs)",background:'var(--accent-muted)',color:'var(--accent)',padding:'1px 6px',borderRadius:4}}>{(item.attributes||{}).sla_tier}</span>}
                        </>
                      )}
                      {item.ci_type === 'database' && (
                        <>
                          {(item.attributes||{}).db_engine && <div style={{fontFamily:'var(--font-mono)',fontSize: "var(--text-sm)"}}>{(item.attributes||{}).db_engine}</div>}
                          {item.hostname && <div style={{fontFamily:'var(--font-mono)',fontSize: "var(--text-xs)",color:'var(--text-3)'}}>{item.hostname}{(item.attributes||{}).port ? ':' + (item.attributes||{}).port : ''}</div>}
                        </>
                      )}
                      {item.ci_type === 'cloud' && (
                        <>
                          {(item.attributes||{}).cloud_provider && <div style={{fontSize: "var(--text-sm)"}}>{(item.attributes||{}).cloud_provider}</div>}
                          {(item.attributes||{}).region && <div style={{fontSize: "var(--text-xs)",color:'var(--text-3)'}}>{(item.attributes||{}).region}</div>}
                          {(item.attributes||{}).instance_type && <div style={{fontSize: "var(--text-xs)",fontFamily:'var(--font-mono)'}}>{(item.attributes||{}).instance_type}</div>}
                        </>
                      )}
                      {item.ci_type === 'container' && (
                        <>
                          {(item.attributes||{}).image && <div style={{fontFamily:'var(--font-mono)',fontSize: "var(--text-xs)"}}>{(item.attributes||{}).image}</div>}
                          {(item.attributes||{}).cluster && <div style={{fontSize: "var(--text-xs)",color:'var(--text-3)'}}>{(item.attributes||{}).cluster}{(item.attributes||{}).namespace ? ' / ' + (item.attributes||{}).namespace : ''}</div>}
                        </>
                      )}
                      {item.ci_type === 'service' && (
                        <>
                          {(item.attributes||{}).url && <div style={{fontSize: "var(--text-xs)",color:'var(--accent)'}}>{(item.attributes||{}).url}</div>}
                          {(item.attributes||{}).owner_team && <div style={{fontSize: "var(--text-xs)",color:'var(--text-3)'}}>{(item.attributes||{}).owner_team}</div>}
                        </>
                      )}
                    </td>
                    <td style={{padding:'10px 12px',fontSize: "var(--text-sm)",color:'var(--text-2)',fontFamily:'var(--font-mono)'}}>{item.version||'—'}</td>
                    <td style={{padding:'10px 12px'}}>
                      <div style={{display:'flex',gap:6}}>
                        <button onClick={() => setHistoryItem(item)}
                          style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'4px 8px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-xs)"}} title="Ver historial de cambios">📋</button>
                        <button onClick={() => setRelItem(item)}
                          style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'4px 8px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-xs)"}}>🔗</button>
                        <button onClick={() => { setEditing(item); setShowForm(true) }}
                          style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'4px 8px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-xs)"}}>✏</button>
                        <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar "${item.name}"?`, onConfirm: () => deleteItem(item.id), danger: true }) }}
                          style={{background:'none',border:'1px solid var(--danger-border)',borderRadius:6,padding:'4px 8px',color:'var(--danger)',cursor:'pointer',fontSize: "var(--text-xs)"}}>🗑</button>
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

      {/* ── CMDB 3D Graph + Blast Radius ── */}
      {tab === '3d' && <Cmdb3dGraph />}

      {/* ─── AGENTES ON-PREM ─────────────────────────────────────────────── */}
      {tab === 'agents' && <CMDBAgentsTab />}
    </PageShell>
  )
}
