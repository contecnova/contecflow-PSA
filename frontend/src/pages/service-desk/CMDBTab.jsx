import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { extractErr } from '../../utils/helpers'
import { useToast } from '../../context/ToastContext'
import api from '../../services/api'
import { Button, Spinner, EmptyState, Modal } from '../../components/ui'

function onKeyboardActivate(event, action) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}

function CMDBDetail({ ci, onClose }) {
  const [tab, setTab] = useState('info')
  const { data: relations = [] } = useQuery({
    queryKey: ['sd-cmdb-relations', ci.id],
    queryFn: () => api.get(`/sd/cmdb/${ci.id}/relations`).then(r => r.data),
    enabled: tab === 'relations',
  })
  const { data: impact } = useQuery({
    queryKey: ['sd-cmdb-impact', ci.id],
    queryFn: () => api.get(`/sd/cmdb/${ci.id}/impact`).then(r => r.data),
    enabled: tab === 'impact',
  })

  const STATUS_COLOR_CI = { operational: '#00e5a0', degraded: '#fb923c', maintenance: '#facc15', retired: '#6b7280' }
  const tabStyle = a => ({ padding: '5px 14px', borderRadius: 7, border: 'none', cursor: 'pointer', background: a ? 'var(--accent-glow)' : 'transparent', color: a ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, fontFamily: 'inherit', fontWeight: a ? 700 : 400 })

  return (
    <Modal open title={`CI: ${ci.name}`} onClose={onClose} width={600}>
      <div style={{ display: 'flex', gap: 4, marginBottom: 16, background: 'var(--surface-1)', borderRadius: 8, padding: 3, width: 'fit-content' }}>
        {[{ id: 'info', l: 'ℹ Info' }, { id: 'relations', l: '🔗 Relaciones' }, { id: 'impact', l: '💥 Impacto' }].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={tabStyle(tab === t.id)}>{t.l}</button>
        ))}
      </div>
      {tab === 'info' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          {[['Codigo', ci.code], ['Tipo', ci.ci_type], ['Estado', ci.status], ['Entorno', ci.environment], ['Criticidad', ci.criticality], ['Vendor', ci.vendor], ['Version', ci.version]].map(([l, v]) => v ? (
            <div key={l}><div style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{l}</div><div style={{ fontSize: 13, fontWeight: 600, marginTop: 2, color: 'var(--text-1)' }}>{v}</div></div>
          ) : null)}
          {ci.description && <div style={{ gridColumn: '1/-1', marginTop: 8, fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5 }}>{ci.description}</div>}
        </div>
      )}
      {tab === 'relations' && (
        <div>
          {relations.length === 0
            ? <EmptyState icon="🔗" title="Sin relaciones" description="Este CI aun no tiene relaciones registradas" />
            : relations.map(r => (
              <div key={r.id} style={{ display: 'flex', gap: 12, padding: '10px 14px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, marginBottom: 6, alignItems: 'center' }}>
                <span style={{ fontSize: 10, padding: '2px 7px', background: 'var(--accent-muted)', color: 'var(--accent)', borderRadius: 4 }}>{r.relation_type?.replace(/_/g, ' ')}</span>
                <div><div style={{ fontSize: 13, fontWeight: 600 }}>{r.target_name || r.source_name}</div><div style={{ fontSize: 11, color: 'var(--text-2)' }}>{r.target_code || r.source_code}</div></div>
              </div>
            ))}
        </div>
      )}
      {tab === 'impact' && (
        <div>
          {!impact ? <div style={{ textAlign: 'center', padding: 20 }}><Spinner /></div>
            : (impact.affected || []).length === 0
              ? <EmptyState icon="💥" title="Sin impacto registrado" description="No hay otros CIs afectados por este elemento" />
              : <>
                  <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 12 }}>Si <strong>{ci.name}</strong> falla, los siguientes CIs se ven afectados:</div>
                  {(impact.affected || []).map(a => (
                    <div key={a.id} style={{ padding: '10px 14px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, marginBottom: 6 }}>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{a.name} <span style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'monospace' }}>{a.code}</span></div>
                      <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>{a.ci_type} · <span style={{ color: STATUS_COLOR_CI[a.status] }}>{a.status}</span></div>
                    </div>
                  ))}
                </>}
        </div>
      )}
    </Modal>
  )
}

export default function CMDBTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [showDetail, setShowDetail] = useState(null)
  const [form, setForm] = useState({ name: '', ci_type: 'application', status: 'operational', description: '', environment: '', version: '', vendor: '', criticality: 'medium', notes: '' })

  const IS = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '7px 11px', color: 'var(--text-1)', fontSize: 12, outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }
  const LS = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 4 }

  const { data: cis = [], isLoading } = useQuery({
    queryKey: ['sd-cmdb', typeFilter],
    queryFn: () => api.get('/sd/cmdb', { params: typeFilter ? { ci_type: typeFilter } : {} }).then(r => r.data),
  })

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: d => api.post('/sd/cmdb', d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-cmdb'] })
      setShowCreate(false)
      setForm({ name: '', ci_type: 'application', status: 'operational', description: '', environment: '', version: '', vendor: '', criticality: 'medium', notes: '' })
      toast.success('CI creado')
    },
    onError: e => toast.error(extractErr(e, 'Error al crear CI')),
  })

  const { mutate: update } = useMutation({
    mutationFn: ({ id, ...d }) => api.patch(`/sd/cmdb/${id}`, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-cmdb'] }); toast.success('CI actualizado') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const CI_TYPES = ['application', 'server', 'database', 'network', 'service', 'module', 'integration', 'other']
  const CI_STATUSES = ['operational', 'degraded', 'maintenance', 'retired']
  const STATUS_COLOR_CI = { operational: '#00e5a0', degraded: '#fb923c', maintenance: '#facc15', retired: '#6b7280' }
  const CRIT_COLOR = { low: '#6b7280', medium: '#facc15', high: '#fb923c', critical: '#ff4757' }

  const filtered = cis.filter(c => !search || c.name.toLowerCase().includes(search.toLowerCase()) || c.code?.toLowerCase().includes(search.toLowerCase()))

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar por nombre o codigo" aria-label="Buscar CI" style={{ ...IS, width: 200 }} />
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)} style={{ ...IS, width: 160 }}>
          <option value="">Todos los tipos</option>
          {CI_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <div style={{ flex: 1 }} />
        <Button size="sm" onClick={() => setShowCreate(true)}>+ Nuevo CI</Button>
      </div>

      {isLoading ? <div style={{ textAlign: 'center', padding: 40 }}><Spinner /></div>
        : filtered.length === 0
          ? <EmptyState icon="🖥" title="Sin elementos CMDB" description="Crea el primer elemento de configuracion para poblar la CMDB" />
          : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(270px, 1fr))', gap: 12 }}>
              {filtered.map(ci => (
                <div key={ci.id} onClick={() => setShowDetail(ci)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => onKeyboardActivate(e, () => setShowDetail(ci))}
                  style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '14px 16px', cursor: 'pointer' }} onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-glow)'} onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 700 }}>{ci.name}</div>
                      <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'monospace' }}>{ci.code}</div>
                    </div>
                    <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 20, fontWeight: 700, background: (STATUS_COLOR_CI[ci.status] || '#6b7280') + '20', color: STATUS_COLOR_CI[ci.status] || '#6b7280' }}>
                      {ci.status}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 10, padding: '2px 6px', background: 'var(--accent-muted)', color: 'var(--accent)', borderRadius: 4 }}>{ci.ci_type}</span>
                    {ci.environment && <span style={{ fontSize: 10, padding: '2px 6px', background: 'var(--surface-4)', color: 'var(--text-2)', borderRadius: 4 }}>{ci.environment}</span>}
                    <span style={{ fontSize: 10, padding: '2px 6px', background: (CRIT_COLOR[ci.criticality] || '#6b7280') + '20', color: CRIT_COLOR[ci.criticality] || '#6b7280', borderRadius: 4 }}>{ci.criticality}</span>
                  </div>
                  {ci.vendor && <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 6 }}>🏷 {ci.vendor}{ci.version ? ` v${ci.version}` : ''}</div>}
                  <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
                    <button onClick={e => { e.stopPropagation(); update({ id: ci.id, status: ci.status === 'operational' ? 'maintenance' : 'operational' }) }} style={{ fontSize: 10, padding: '3px 8px', borderRadius: 5, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer' }}>
                      {ci.status === 'operational' ? '🔧 Modo mantenimiento' : '✅ Operativo'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

      {showCreate && (
        <Modal open title="Nuevo elemento CMDB" onClose={() => setShowCreate(false)} width={540}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
            <div style={{ gridColumn: '1/-1' }}><label style={LS}>Nombre *</label><input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={IS} /></div>
            <div><label style={LS}>Tipo *</label><select value={form.ci_type} onChange={e => setForm(f => ({ ...f, ci_type: e.target.value }))} style={IS}>{CI_TYPES.map(t => <option key={t} value={t}>{t}</option>)}</select></div>
            <div><label style={LS}>Estado</label><select value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value }))} style={IS}>{CI_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}</select></div>
            <div><label style={LS}>Entorno</label><input value={form.environment} onChange={e => setForm(f => ({ ...f, environment: e.target.value }))} style={IS} placeholder="Produccion, QA o Desarrollo" aria-label="Entorno" /></div>
            <div><label style={LS}>Criticidad</label><select value={form.criticality} onChange={e => setForm(f => ({ ...f, criticality: e.target.value }))} style={IS}>{['low', 'medium', 'high', 'critical'].map(c => <option key={c} value={c}>{c}</option>)}</select></div>
            <div><label style={LS}>Version</label><input value={form.version} onChange={e => setForm(f => ({ ...f, version: e.target.value }))} style={IS} /></div>
            <div><label style={LS}>Vendor</label><input value={form.vendor} onChange={e => setForm(f => ({ ...f, vendor: e.target.value }))} style={IS} /></div>
            <div style={{ gridColumn: '1/-1' }}><label style={LS}>Descripcion</label><textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} rows={3} style={{ ...IS, resize: 'vertical' }} /></div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowCreate(false)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12 }}>Cancelar</button>
            <Button onClick={() => create(form)} loading={creating} disabled={!form.name || creating}>Crear CI</Button>
          </div>
        </Modal>
      )}

      {showDetail && <CMDBDetail ci={showDetail} onClose={() => setShowDetail(null)} />}
    </div>
  )
}
