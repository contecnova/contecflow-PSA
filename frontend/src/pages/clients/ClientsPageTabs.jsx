import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { clientExtApi, contractsApi, licensesApi, portalApi, wsApi } from '../../services/api'
import { Button, Spinner, EmptyState, Modal } from '../../components/ui'
import { BadgeWithTooltip } from '../../components/ui/BadgeWithTooltip'
import { IconFR, IconCR } from '../../components/ui/FRCRIcons'
import { fmtCurrency, extractErr } from '../../utils/helpers'
import { resolveWsBase } from '../../utils/wsUtils'
import { PortalUsersTab } from './PortalUsersTab'
import { ConversationPoliciesPanel, TeamGovernedConversationInbox } from '../../components/portal/GovernedConversations'

const panel = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const inp = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }
const lbl = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }

const MODULES = [
  { id: 'dashboard',   icon: '📊', label: 'Dashboard' },
  { id: 'deliverables',icon: '📦', label: 'Entregables' },
  { id: 'uat',         icon: '🧪', label: 'UAT' },
  { id: 'requests',    icon: '💡', label: 'Solicitudes' },
  { id: 'documents',   icon: '📄', label: 'Documentos' },
  { id: 'roadmap',     icon: '🗺️', label: 'Roadmap' },
  { id: 'wiki',        icon: '📚', label: 'Wiki' },
  { id: 'support',     icon: '🎫', label: 'Service Desk' },
  { id: 'messages',    icon: '💬', label: 'Mensajes' },
]

const SLA_COLOR = {
  enterprise: 'var(--purple)',
  gold: 'var(--warning)',
  silver: 'var(--text-2)',
  bronze: 'var(--warning)',
}

export function ProjectsTab({ cid }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [showLink, setShowLink] = useState(false)

  const { data: linked = [], isLoading: loadingLinked } = useQuery({
    queryKey: ['client-projects-linked', cid],
    queryFn: () => clientExtApi.projects(cid).then(r => r.data),
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchOnMount: 'always',
  })

  const { data: available = [], isLoading: loadingAvail, refetch: refetchAvailable } = useQuery({
    queryKey: ['client-projects-available', cid],
    queryFn: () => clientExtApi.availableProjects(cid).then(r => r.data),
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchOnMount: 'always',
  })

  const { mutate: link } = useMutation({
    mutationFn: pid => clientExtApi.linkProject(cid, pid).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['client-projects-linked', cid]); qc.invalidateQueries(['client-projects-available', cid]); qc.invalidateQueries(['client-detail']); qc.invalidateQueries(['clients']) },
    onError: e => toast.error(extractErr(e, 'Error al vincular')),
  })

  const { mutate: unlink } = useMutation({
    mutationFn: pid => clientExtApi.unlinkProject(cid, pid).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['client-projects-linked', cid]); qc.invalidateQueries(['client-projects-available', cid]); qc.invalidateQueries(['client-detail']); qc.invalidateQueries(['clients']) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const statusColor = { active: 'var(--success)', planning: 'var(--accent)', on_hold: 'var(--warning)', completed: 'var(--text-2)', cancelled: 'var(--danger)' }
  const statusLabel = { active: 'Activo', planning: 'Planificación', on_hold: 'En espera', completed: 'Completado', cancelled: 'Cancelado' }

  const unlinked = available.filter(p => !p.is_linked)

  return (
    <div>
      <div style={{ background: 'var(--accent-muted)', border: '1px solid #00d4ff20', borderRadius: 10, padding: '10px 16px', marginBottom: 16, fontSize: 12, color: 'var(--text-2)' }}>
        ℹ️ Un proyecto solo puede estar vinculado a un cliente. Al vincular aquí, el proyecto queda asociado exclusivamente a este cliente.
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{linked.length} proyecto(s) vinculado(s)</div>
        <Button onClick={() => { setShowLink(s => !s); refetchAvailable() }} size="sm">
          {showLink ? '✕ Cerrar' : '+ Vincular proyecto'}
        </Button>
      </div>

      {showLink && (
        <div style={{ ...panel, padding: '16px 18px', marginBottom: 20, border: '1px solid #00d4ff30' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12, color: 'var(--accent)' }}>Proyectos disponibles para vincular</div>
          {loadingAvail ? <Spinner /> : unlinked.length === 0 ? (
            <div style={{ fontSize: 12, color: 'var(--text-2)', padding: '10px 0' }}>No hay proyectos disponibles sin cliente asignado.</div>
          ) : (
            unlinked.map(p => (
              <div key={p.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', marginBottom: 6, background: 'var(--surface-1)', borderRadius: 8, border: '1px solid var(--surface-4)' }}>
                <div>
                  <span style={{ fontFamily: "'Space Mono', monospace", fontSize: 11, color: 'var(--text-2)', marginRight: 8 }}>{p.code}</span>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</span>
                  <span style={{ marginLeft: 10, fontSize: 11, padding: '1px 6px', borderRadius: 4, background: (statusColor[p.status] || 'var(--text-2)') + '20', color: statusColor[p.status] || 'var(--text-2)' }}>
                    {statusLabel[p.status] || p.status}
                  </span>
                </div>
                <button onClick={() => link(p.id)} style={{ fontSize: 12, padding: '5px 14px', borderRadius: 8, border: '1px solid #00d4ff40', background: 'var(--accent-muted)', color: 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600 }}>
                  + Vincular
                </button>
              </div>
            ))
          )}
        </div>
      )}

      {loadingLinked ? <Spinner /> : linked.length === 0 ? (
        <EmptyState icon="⬡" title="Sin proyectos vinculados" description="Vincula el primer proyecto a este cliente" />
      ) : (
        linked.map(p => (
          <div key={p.id} style={{ ...panel, padding: '14px 18px', marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                  <span style={{ fontFamily: "'Space Mono', monospace", fontSize: 11, color: 'var(--text-2)' }}>{p.code}</span>
                  <span style={{ fontSize: 14, fontWeight: 700 }}>{p.name}</span>
                  <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 20, background: (statusColor[p.status] || 'var(--text-2)') + '20', color: statusColor[p.status] || 'var(--text-2)', fontWeight: 700 }}>
                    {statusLabel[p.status] || p.status}
                  </span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
                  {p.start_date && `${p.start_date} → ${p.end_date || 'en curso'}`}
                </div>
              </div>
              <button onClick={() => { openConfirmGlobal({ message: `¿Desvincular "${p.name}" de este cliente?`, onConfirm: () => unlink(p.id), danger: true }) }} style={{ fontSize: 11, padding: '4px 10px', borderRadius: 6, border: '1px solid #ff475730', background: 'transparent', color: 'var(--danger)', cursor: 'pointer', fontFamily: 'inherit' }}>
                Desvincular
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  )
}

export function ContactsTab({ cid }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ full_name: '', email: '', phone: '', job_title: '', role: 'other', is_primary: false })

  const { data: contacts = [], isLoading } = useQuery({
    queryKey: ['client-contacts', cid],
    queryFn: () => clientExtApi.contacts(cid).then(r => r.data),
  })
  const { mutate: add } = useMutation({
    mutationFn: d => clientExtApi.createContact(cid, d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['client-contacts', cid]); setShowAdd(false); setForm({ full_name: '', email: '', phone: '', job_title: '', role: 'other', is_primary: false }) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: remove } = useMutation({
    mutationFn: id => clientExtApi.deleteContact(cid, id),
    onSuccess: () => qc.invalidateQueries(['client-contacts', cid]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const roles = [
    { id: 'primary', label: 'Principal' }, { id: 'billing', label: 'Facturación' },
    { id: 'technical', label: 'Técnico' }, { id: 'executive', label: 'Ejecutivo' },
    { id: 'support', label: 'Soporte' }, { id: 'other', label: 'Otro' },
  ]
  const roleColor = { primary: 'var(--accent)', billing: 'var(--warning)', technical: 'var(--purple)', executive: 'var(--success)', support: 'var(--warning)', other: 'var(--text-2)' }

  if (isLoading) return <Spinner />
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{contacts.length} contacto(s)</div>
        <Button onClick={() => setShowAdd(true)} size="sm">+ Añadir contacto</Button>
      </div>
      {contacts.length === 0 ? (
        <EmptyState icon="👤" title="Sin contactos" description="Anade un contacto principal para este cliente" />
      ) : contacts.map(ct => (
        <div key={ct.id} style={{ ...panel, padding: '14px 18px', marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: (roleColor[ct.role] || 'var(--text-2)') + '20', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, fontWeight: 800, color: roleColor[ct.role] || 'var(--text-2)' }}>
              {ct.full_name?.charAt(0) || '?'}
            </div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700 }}>{ct.full_name}
                {ct.is_primary && <span style={{ marginLeft: 6, fontSize: 10, background: 'var(--accent-glow)', color: 'var(--accent)', padding: '1px 6px', borderRadius: 4 }}>Principal</span>}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{ct.job_title} {ct.email && `· ${ct.email}`}</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 20, background: (roleColor[ct.role] || 'var(--text-2)') + '15', color: roleColor[ct.role] || 'var(--text-2)', fontWeight: 700 }}>
              {roles.find(r => r.id === ct.role)?.label || ct.role}
            </span>
            {ct.phone && <span style={{ fontSize: 12, color: 'var(--text-2)' }}>📞 {ct.phone}</span>}
            <button onClick={() => remove(ct.id)} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: 14 }}>🗑</button>
          </div>
        </div>
      ))}
      {showAdd && (
        <Modal open title="Nuevo contacto" onClose={() => setShowAdd(false)} width={500}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
            <div><label style={lbl}>Nombre completo *</label><input value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Email</label><input type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Teléfono</label><input value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Cargo</label><input value={form.job_title} onChange={e => setForm(f => ({ ...f, job_title: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Rol</label>
              <select value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))} style={inp}>
                {roles.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
              </select>
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-end' }}>
              <label style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={form.is_primary} onChange={e => setForm(f => ({ ...f, is_primary: e.target.checked }))} />
                Contacto principal
              </label>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowAdd(false)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => add(form)} disabled={!form.full_name}>Añadir</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

export function LicensesTab({ cid }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [showLink, setShowLink] = useState(false)
  const [selectedLic, setSelectedLic] = useState('')
  const [licNote, setLicNote] = useState('')

  const { data: linked = [] } = useQuery({ queryKey: ['client-licenses', cid], queryFn: () => clientExtApi.licenses(cid).then(r => r.data) })
  const { data: allLics = [] } = useQuery({ queryKey: ['alm-licenses'], queryFn: () => licensesApi.list().then(r => r.data) })

  const { mutate: link } = useMutation({
    mutationFn: d => clientExtApi.linkLicense(cid, d),
    onSuccess: () => { qc.invalidateQueries(['client-licenses', cid]); qc.invalidateQueries(['alm-licenses']); setShowLink(false); setSelectedLic(''); setLicNote('') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: unlink } = useMutation({
    mutationFn: id => clientExtApi.unlinkLicense(cid, id),
    onSuccess: () => { qc.invalidateQueries(['client-licenses', cid]); qc.invalidateQueries(['alm-licenses']) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const linkedIds = linked.map(l => l.license_id)
  const available = allLics.filter(l => !linkedIds.includes(l.id))
  const statusCol = { active: 'var(--success)', expired: 'var(--danger)', cancelled: 'var(--text-2)' }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{linked.length} licencia(s) vinculada(s)</div>
        <Button onClick={() => setShowLink(true)} size="sm">+ Vincular licencia</Button>
      </div>
      {linked.length === 0 ? (
        <EmptyState icon="🔑" title="Sin licencias vinculadas" description="Vincula una licencia para este cliente" />
      ) : linked.map(l => (
        <div key={l.link_id} style={{ ...panel, padding: '14px 18px', marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700 }}>{l.name}</div>
            <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
              {l.total_seats && `${l.total_seats} seats`}
              {l.expiry_date && ` · Vence ${l.expiry_date}`}
              {l.annual_cost && ` · ${fmtCurrency(l.annual_cost)}/año`}
            </div>
            {l.notes && <div style={{ fontSize: 11, color: 'var(--text-2)', fontStyle: 'italic', marginTop: 2 }}>{l.notes}</div>}
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 20, background: (statusCol[l.status] || 'var(--text-2)') + '15', color: statusCol[l.status] || 'var(--text-2)', fontWeight: 700 }}>{l.status}</span>
            <button onClick={() => unlink(l.link_id)} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer' }}>🗑</button>
          </div>
        </div>
      ))}
      {showLink && (
        <Modal open title="Vincular licencia" onClose={() => setShowLink(false)} width={440}>
          <div style={{ marginBottom: 14 }}>
            <label style={lbl}>Licencia</label>
            <select value={selectedLic} onChange={e => setSelectedLic(e.target.value)} style={inp}>
              <option value="">Seleccionar...</option>
              {available.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={lbl}>Notas (opcional)</label>
            <input value={licNote} onChange={e => setLicNote(e.target.value)} style={inp} placeholder="Notas de la licencia" aria-label="Notas de la licencia" />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowLink(false)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => link({ license_id: selectedLic, notes: licNote })} disabled={!selectedLic}>Vincular</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

export function ContractsTab({ cid }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [showLink, setShowLink] = useState(false)
  const [selectedCon, setSelectedCon] = useState('')

  const { data: linked = [] } = useQuery({ queryKey: ['client-contracts', cid], queryFn: () => clientExtApi.contracts(cid).then(r => r.data) })
  const { data: allCons = [] } = useQuery({ queryKey: ['contracts'], queryFn: () => contractsApi.list().then(r => r.data) })

  const { mutate: link } = useMutation({
    mutationFn: d => clientExtApi.linkContract(cid, d),
    onSuccess: () => { qc.invalidateQueries(['client-contracts', cid]); qc.invalidateQueries(['contracts']); qc.invalidateQueries(['alm-contracts']); setShowLink(false); setSelectedCon('') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: unlink } = useMutation({
    mutationFn: id => clientExtApi.unlinkContract(cid, id),
    onSuccess: () => { qc.invalidateQueries(['client-contracts', cid]); qc.invalidateQueries(['contracts']); qc.invalidateQueries(['alm-contracts']) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const linkedIds = linked.map(l => l.contract_id)
  const available = allCons.filter(c => !linkedIds.includes(c.id))
  const statusCol = { active: 'var(--success)', draft: 'var(--text-2)', completed: 'var(--accent)', cancelled: 'var(--danger)' }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{linked.length} contrato(s) vinculado(s)</div>
        <Button onClick={() => setShowLink(true)} size="sm">+ Vincular contrato</Button>
      </div>
      {linked.length === 0 ? (
        <EmptyState icon="📄" title="Sin contratos vinculados" description="Asocia un contrato activo a este cliente" />
      ) : linked.map(c => (
        <div key={c.link_id} style={{ ...panel, padding: '14px 18px', marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700 }}>{c.title}</div>
            <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
              {c.reference && `Ref: ${c.reference} · `}
              {c.total_amount && `${fmtCurrency(c.total_amount)} · `}
              {c.start_date && `${c.start_date} → ${c.end_date || '...'}`}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 20, background: (statusCol[c.status] || 'var(--text-2)') + '15', color: statusCol[c.status] || 'var(--text-2)', fontWeight: 700 }}>{c.status}</span>
            <button onClick={() => unlink(c.link_id)} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer' }}>🗑</button>
          </div>
        </div>
      ))}
      {showLink && (
        <Modal open title="Vincular contrato" onClose={() => setShowLink(false)} width={440}>
          <div style={{ marginBottom: 16 }}>
            <label style={lbl}>Contrato</label>
            <select value={selectedCon} onChange={e => setSelectedCon(e.target.value)} style={inp}>
              <option value="">Seleccionar...</option>
              {available.map(c => <option key={c.id} value={c.id}>{c.title || c.client_name} — {c.status}</option>)}
            </select>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowLink(false)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => link({ contract_id: selectedCon })} disabled={!selectedCon}>Vincular</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

export function PortalConfigTab({ cid, clientDetail }) {
  const [sub, setSub] = useState('accesos')

  const subTabs = [
    { id: 'accesos', label: 'Accesos' },
    { id: 'uat', label: 'UAT' },
    { id: 'solicitudes', label: 'Solicitudes' },
    { id: 'mensajes', label: 'Mensajes' },
    { id: 'documentos', label: 'Documentos' },
    { id: 'config', label: 'Configuración' },
  ]

  return (
    <div>
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid #1a2640', paddingBottom: 10 }}>
        {subTabs.map(t => (
          <button key={t.id} onClick={() => setSub(t.id)}
            style={{ padding: '5px 14px', borderRadius: 8, border: `1px solid ${sub === t.id ? 'var(--accent-glow)' : 'transparent'}`,
              background: sub === t.id ? 'var(--accent-muted)' : 'transparent',
              color: sub === t.id ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 12, fontWeight: sub === t.id ? 700 : 400, cursor: 'pointer', fontFamily: 'inherit' }}>
            {t.label}
          </button>
        ))}
      </div>

      {sub === 'accesos' && <PortalUsersTab cid={cid} clientName={clientDetail?.name} />}
      {sub === 'uat' && <PortalUATTab cid={cid} projects={clientDetail?.projects || []} />}
      {sub === 'solicitudes' && <PortalSolicitudesTab cid={cid} projects={clientDetail?.projects || []} />}
      {sub === 'mensajes' && <PortalMensajesTab cid={cid} projects={clientDetail?.projects || []} />}
      {sub === 'documentos' && <PortalDocumentosTab cid={cid} projects={clientDetail?.projects || []} />}
      {sub === 'config' && <PortalSettingsTab cid={cid} />}
    </div>
  )
}

export function PortalUATTab({ _cid, projects }) {
  const [selectedProject, setSelectedProject] = useState(projects[0]?.id || '')

  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ['uat-team-client', selectedProject],
    queryFn: () => portalApi.uat({ project_id: selectedProject }).then(r => r.data).catch(() => []),
    enabled: !!selectedProject,
  })

  const statusColor = {
    pending: 'var(--text-2)', in_progress: 'var(--accent)', passed: 'var(--success)',
    failed: 'var(--danger)', conditional: 'var(--warning)',
  }
  const statusLabel = {
    pending: 'Pendiente', in_progress: 'En progreso', passed: 'Aprobado',
    failed: 'Rechazado', conditional: 'Con reservas',
  }

  return (
    <div>
      {projects.length === 0 ? (
        <EmptyState icon="🧪" title="Sin proyectos para UAT" description="Asocia un proyecto para mostrar sesiones UAT" />
      ) : (
        <>
          {projects.length > 1 && (
            <div style={{ marginBottom: 16 }}>
              <label style={lbl}>Proyecto</label>
              <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)} style={inp}>
                {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </select>
            </div>
          )}

          {!selectedProject ? (
            <EmptyState icon="🧪" title="Selecciona un proyecto" description="Elige un proyecto para ver las sesiones UAT" />
          ) : isLoading ? <Spinner /> : sessions.length === 0 ? (
            <EmptyState icon="🧪" title="Sin sesiones UAT" description="Todavia no hay sesiones UAT disponibles para este proyecto" />
          ) : (
            sessions.map(s => (
              <div key={s.id} style={{ ...panel, padding: '14px 18px', marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                  <div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 3 }}>
                      <span style={{ fontFamily: "'Space Mono', monospace", fontSize: 11, color: 'var(--text-2)' }}>{s.code}</span>
                      <span style={{ fontSize: 14, fontWeight: 700 }}>{s.title}</span>
                    </div>
                    {s.description && <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{s.description.slice(0, 120)}</div>}
                    <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
                      {s.available_from && `Disponible: ${s.available_from}`}
                      {s.deadline && ` · Límite: ${s.deadline}`}
                    </div>
                  </div>
                  <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 20, flexShrink: 0, background: (statusColor[s.status] || 'var(--text-2)') + '20', color: statusColor[s.status] || 'var(--text-2)', fontWeight: 700 }}>
                    {statusLabel[s.status] || s.status}
                  </span>
                </div>
                {s.test_environment && (
                  <div style={{ marginTop: 8, fontSize: 11 }}>
                    <a href={s.test_environment} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', textDecoration: 'none' }}>
                      🔗 Entorno de pruebas
                    </a>
                  </div>
                )}
                {s.issues_count > 0 && (
                  <div style={{ marginTop: 6, fontSize: 11, color: 'var(--danger)' }}>
                    ⚠️ {s.issues_count} incidencia(s) reportada(s)
                  </div>
                )}
              </div>
            ))
          )}
        </>
      )}
    </div>
  )
}

export function PortalSolicitudesTab({ cid }) {
  const toast = useToast()
  const qc = useQueryClient()
  const { user, loading } = useAuth()

  useEffect(() => {
    if (loading || !user) return undefined

    let ws
    let reconnectTimer
    function connectWS() {
      wsApi.ticket().then(res => {
        const ticket = res.data.ticket
        ws = new window.WebSocket(`${resolveWsBase()}/api/v1/ws/notifications?ticket=${ticket}`)
        ws.onclose = () => { reconnectTimer = setTimeout(connectWS, 5000) }
        ws.onerror = () => { ws.close() }
        ws.onmessage = (ev) => {
          try {
            const msg = JSON.parse(ev.data)
            if (msg.type === 'cr_state_changed' && msg.feature_request_id) {
              toast.info(`El estado de la Change Request vinculada a "${msg.title}" ha cambiado a: ${msg.cr_status}`)
              qc.invalidateQueries(['portal-frs-client', cid])
            }
          } catch {
            // ignore parse errors
          }
        }
      })
    }
    connectWS()
    return () => { if (ws) ws.close(); clearTimeout(reconnectTimer) }
  }, [cid, loading, qc, toast, user])

  const [responding, setResponding] = useState(null)
  const [responseForm, setResponseForm] = useState({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' })
  const [crDetail, setCrDetail] = useState(null)
  const [crFilter, setCrFilter] = useState('all')

  const { data: frs = [], isLoading } = useQuery({
    queryKey: ['portal-frs-client', cid],
    queryFn: () => portalApi.featureRequests({ client_org_id: cid }).then(r => r.data).catch(() => []),
    enabled: !!cid,
  })

  const { mutate: respond, isPending } = useMutation({
    mutationFn: ({ id, data }) => portalApi.respondFeatureRequest(id, data),
    onSuccess: () => { qc.invalidateQueries(['portal-frs-client', cid]); setResponding(null) },
    onError: e => toast.error(extractErr(e, 'Error al responder')),
  })

  const { mutate: updateStatus } = useMutation({
    mutationFn: ({ id, status }) => portalApi.respondFeatureRequest(id, { status }),
    onSuccess: () => qc.invalidateQueries(['portal-frs-client', cid]),
    onError: e => toast.error(extractErr(e, 'Error al actualizar estado')),
  })

  const statusColor = { new: 'var(--text-2)', reviewing: 'var(--accent)', estimated: 'var(--warning)', approved: 'var(--success)', rejected: 'var(--danger)', in_development: 'var(--purple)', done: 'var(--success)' }
  const statusLabel = { new: 'Nueva', reviewing: 'En revisión', estimated: 'Presupuestada', approved: 'Aprobada', rejected: 'Rechazada', in_development: 'En desarrollo', done: 'Completada' }
  const prioColor = { low: 'var(--text-2)', medium: 'var(--warning)', high: 'var(--warning)', critical: 'var(--danger)' }
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

  if (isLoading) return <Spinner />

  const crStates = [
    { value: 'all', label: 'Todas' },
    { value: 'none', label: 'Sin CR' },
    { value: 'submitted', label: 'CR Enviada' },
    { value: 'under_review', label: 'CR En revisión' },
    { value: 'approved', label: 'CR Aprobada' },
    { value: 'rejected', label: 'CR Rechazada' },
    { value: 'implemented', label: 'CR Implementada' },
  ]
  const filteredFrs = frs.filter(fr => {
    if (crFilter === 'all') return true
    if (crFilter === 'none') return !fr.cr_status
    return fr.cr_status === crFilter
  })

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        <span style={{ fontSize: 13, color: 'var(--text-2)' }}>{filteredFrs.length} solicitud(es) del cliente</span>
        <select value={crFilter} onChange={e => setCrFilter(e.target.value)} style={{ ...inp, width: 160, fontSize: 12, padding: '4px 8px' }}>
          {crStates.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
        </select>
      </div>
      {filteredFrs.length === 0 ? (
        <EmptyState icon="💡" title="Sin solicitudes" description="No hay solicitudes funcionales del cliente" />
      ) : filteredFrs.map(fr => (
        <div key={fr.id} style={{ ...panel, padding: '14px 18px', marginBottom: 10, borderLeft: fr.cr_status_color ? `6px solid ${fr.cr_status_color}` : '6px solid #7a8aaa', boxShadow: fr.cr_status ? '0 2px 8px #0001' : undefined, position: 'relative' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 3 }}>
                <IconFR />
                <span style={{ fontSize: 11, color: 'var(--text-2)', fontFamily: "'Space Mono', monospace" }}>{fr.code}</span>
                <span style={{ fontSize: 14, fontWeight: 700 }}>{fr.title}</span>
              </div>
              {fr.project_name && <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 3 }}>📁 {fr.project_name}</div>}
            </div>
            <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
              <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 20, background: (prioColor[fr.priority] || 'var(--text-2)') + '20', color: prioColor[fr.priority] || 'var(--text-2)', fontWeight: 700 }}>{fr.priority}</span>
              <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 20, background: (statusColor[fr.status] || 'var(--text-2)') + '20', color: statusColor[fr.status] || 'var(--text-2)', fontWeight: 700 }}>{statusLabel[fr.status] || fr.status}</span>
              {fr.cr_status ? (
                <BadgeWithTooltip
                  label={`CR: ${fr.cr_status_label || fr.cr_status}`}
                  color={fr.cr_status_color || '#7a8aaa'}
                  tooltip={'Estado de la Change Request vinculada. Click para ver detalles.'}
                  icon={<IconCR />}
                  onClick={() => setCrDetail(fr)}
                />
              ) : (
                <BadgeWithTooltip
                  label={'Sin CR'}
                  color="#7a8aaa"
                  tooltip={'No se ha generado Change Request. Se crea automáticamente al aprobar la FR por el cliente.'}
                  icon={<IconCR />}
                />
              )}
            </div>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5 }}>{fr.description?.slice(0, 200)}</div>
          {fr.pm_response && (
            <div style={{ marginTop: 8, background: 'var(--success-bg)', border: '1px solid #00e5a020', borderRadius: 8, padding: '8px 12px', fontSize: 12, color: 'var(--text-2)' }}>
              <strong style={{ color: 'var(--success)' }}>Respuesta del equipo:</strong> {fr.pm_response}
              {fr.estimated_cost && <span style={{ marginLeft: 8, color: 'var(--warning)' }}>· {fr.estimated_cost}€</span>}
              {fr.estimated_delivery_weeks && <span style={{ marginLeft: 8, color: 'var(--accent)' }}>· {fr.estimated_delivery_weeks} semanas</span>}
            </div>
          )}
          {fr.client_approved === true && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--success)' }}>✓ Cliente aprobó el {fr.client_approved_at}</div>}
          {fr.client_approved === false && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--danger)' }}>✗ Cliente rechazó</div>}
          <div style={{ display: 'flex', gap: 8, marginTop: 10, justifyContent: 'flex-end' }}>
            {['new', 'reviewing'].includes(fr.status) && (
              <Button size="sm" onClick={() => { setResponding(fr); setResponseForm({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' }) }}>
                💬 Responder
              </Button>
            )}
            {fr.status === 'approved' && (
              <Button size="sm" variant="secondary" onClick={() => updateStatus({ id: fr.id, status: 'in_development' })}>
                🚀 Iniciar desarrollo
              </Button>
            )}
            {fr.status === 'in_development' && (
              <Button size="sm" variant="secondary" onClick={() => updateStatus({ id: fr.id, status: 'done' })}>
                ✓ Marcar completada
              </Button>
            )}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 6 }}>{fr.submitted_at}</div>
        </div>
      ))}

      {responding && (
        <Modal open title={`Responder a: ${responding.title}`} onClose={() => setResponding(null)} width={520}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div><label style={ls}>Respuesta / Análisis *</label><textarea value={responseForm.pm_response} onChange={e => setResponseForm(f => ({ ...f, pm_response: e.target.value }))} rows={3} style={{ ...fs, resize: 'vertical' }} placeholder="Respuesta del equipo" aria-label="Respuesta del equipo" /></div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              <div><label style={ls}>Horas estimadas</label><input type="number" value={responseForm.estimated_hours} onChange={e => setResponseForm(f => ({ ...f, estimated_hours: e.target.value }))} style={fs} placeholder="Horas" aria-label="Horas estimadas" /></div>
              <div><label style={ls}>Coste estimado €</label><input type="number" value={responseForm.estimated_cost} onChange={e => setResponseForm(f => ({ ...f, estimated_cost: e.target.value }))} style={fs} placeholder="Coste" aria-label="Coste estimado" /></div>
              <div><label style={ls}>Semanas entrega</label><input type="number" value={responseForm.estimated_delivery_weeks} onChange={e => setResponseForm(f => ({ ...f, estimated_delivery_weeks: e.target.value }))} style={fs} placeholder="Semanas" aria-label="Semanas de entrega" /></div>
            </div>
            <div><label style={ls}>Estado</label>
              <select value={responseForm.status} onChange={e => setResponseForm(f => ({ ...f, status: e.target.value }))} style={fs}>
                <option value="estimated">Presupuestada (pendiente aprobación cliente)</option>
                <option value="rejected">Rechazada (no factible)</option>
              </select>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <Button variant="secondary" onClick={() => setResponding(null)}>Cancelar</Button>
              <Button onClick={() => respond({ id: responding.id, data: responseForm })} disabled={isPending || !responseForm.pm_response}>Enviar respuesta</Button>
            </div>
          </div>
        </Modal>
      )}

      {crDetail && (
        <Modal open title="Detalle Change Request" onClose={() => setCrDetail(null)} width={520}>
          {crDetail.cr_status ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ fontWeight: 700, fontSize: 15, color: crDetail.cr_status_color }}>
                <IconCR /> Estado: {crDetail.cr_status_label || crDetail.cr_status}
              </div>
              <div><b>Título:</b> {crDetail.title}</div>
              <div><b>Descripción:</b> {crDetail.description}</div>
              <div><b>Impacto:</b> {crDetail.impact_label || crDetail.impact || '—'}</div>
              <div><b>Coste impacto:</b> {crDetail.cost_impact != null ? crDetail.cost_impact + ' €' : '—'}</div>
              <div><b>Impacto en plazo:</b> {crDetail.schedule_impact_days != null ? crDetail.schedule_impact_days + ' días' : '—'}</div>
              <div><b>Notas/resolución:</b> {crDetail.resolution_notes || '—'}</div>
              <div><b>Fechas:</b> {['submitted_at', 'approved_at', 'implemented_at'].map(f => crDetail[f] && (<span key={f} style={{ marginRight: 10 }}>{f.replace('_at', '')}: {crDetail[f]}</span>))}</div>
            </div>
          ) : (
            <div>No hay Change Request vinculada aún. Se creará automáticamente al aprobar la FR por el cliente.</div>
          )}
        </Modal>
      )}
    </div>
  )
}

export function PortalMensajesTab({ cid, projects }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <TeamGovernedConversationInbox
        title="Conversaciones del cliente"
        emptyTitle="Sin conversaciones"
        emptyDescription="Todavía no hay conversaciones del portal para este cliente."
        projectOptions={projects.map((project) => ({ id: project.id, name: project.name || project.code || project.id, code: project.code || '' }))}
        initialProjectId={projects[0]?.id || ''}
        clientOrgId={cid}
      />
      <ConversationPoliciesPanel />
    </div>
  )
}

export function PortalDocumentosTab({ cid, projects }) {
  const [selectedProject, setSelectedProject] = useState(projects[0]?.id || '')
  const { data: docs = [], isLoading } = useQuery({
    queryKey: ['portal-docs-team', cid, selectedProject],
    queryFn: () => selectedProject
      ? portalApi.documents({ project_id: selectedProject }).then(r => r.data).catch(() => [])
      : Promise.resolve([]),
    enabled: !!selectedProject,
  })
  const catIcon = { general: '📄', contract: '📝', invoice: '🧾', report: '📊', specification: '📋', other: '📎' }
  if (isLoading) return <Spinner />
  return (
    <div>
      {projects.length > 1 && (
        <div style={{ marginBottom: 16 }}>
          <label style={lbl}>Proyecto</label>
          <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)} style={inp}>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </select>
        </div>
      )}
      {!selectedProject
        ? <EmptyState icon="📄" title="Selecciona un proyecto" description="Elige un proyecto para ver documentos" />
        : <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 16 }}>{docs.length} documento(s) compartido(s)</div>}
      {docs.length === 0
        ? <EmptyState icon="📄" title="Sin documentos" description="No hay documentos compartidos en el portal para este proyecto" />
        : docs.map(d => (
          <div key={d.id} style={{ ...panel, padding: '14px 18px', marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <span style={{ fontSize: 24 }}>{catIcon[d.category] || '📄'}</span>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{d.title}</div>
                <div style={{ fontSize: 11, color: 'var(--text-2)' }}>
                  {d.file_name && `${d.file_name} · `}{d.created_at?.slice(0, 10)}
                  {d.requires_signature && <span style={{ marginLeft: 8, color: 'var(--warning)' }}>✍️ Requiere firma</span>}
                </div>
              </div>
            </div>
            {d.file_url && (
              <a href={d.file_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 11, padding: '4px 12px', borderRadius: 6, border: '1px solid var(--surface-4)', color: 'var(--accent)', textDecoration: 'none', background: 'var(--accent-muted)' }}>
                ⬇ Descargar
              </a>
            )}
          </div>
        ))}
    </div>
  )
}

export function PortalSettingsTab({ cid }) {
  const toast = useToast()
  const qc = useQueryClient()
  const { data: cfg, isLoading } = useQuery({
    queryKey: ['client-portal-cfg', cid],
    queryFn: () => clientExtApi.portalConfig(cid).then(r => r.data),
  })
  const [modules, setModules] = useState([])
  const [sdWithout, setSdWithout] = useState(true)
  const [slaTier, setSlaTier] = useState('')
  const [maxUsers, setMaxUsers] = useState(10)
  const [defaultLang, setDefaultLang] = useState('es')
  const [allowEdit, setAllowEdit] = useState(true)
  const [allowPwd, setAllowPwd] = useState(true)

  useEffect(() => {
    if (cfg) {
      setModules(cfg.enabled_modules || [])
      setSdWithout(cfg.sd_without_project ?? true)
      setSlaTier(cfg.sla_tier || '')
      setMaxUsers(cfg.max_portal_users || 10)
      setDefaultLang(cfg.default_language || 'es')
      setAllowEdit(cfg.allow_profile_edit ?? true)
      setAllowPwd(cfg.allow_pwd_change ?? true)
    }
  }, [cfg])

  const { mutate: save, isPending: saving } = useMutation({
    mutationFn: d => clientExtApi.updatePortalConfig(cid, d),
    onSuccess: () => { qc.invalidateQueries(['client-portal-cfg', cid]); toast.success('✅ Configuración guardada') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const toggleModule = (mod) => setModules(m => m.includes(mod) ? m.filter(x => x !== mod) : [...m, mod])

  const languages = [
    { code: 'es', label: 'Español' }, { code: 'en', label: 'English' },
    { code: 'fr', label: 'Français' }, { code: 'de', label: 'Deutsch' },
    { code: 'pt', label: 'Português' }, { code: 'it', label: 'Italiano' },
    { code: 'pl', label: 'Polski' }, { code: 'zh', label: '中文' },
  ]

  if (isLoading) return <Spinner />
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ ...panel, padding: '18px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 14 }}>🌐 Módulos del portal</div>
          <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 12 }}>Qué secciones puede ver el cliente en su portal.</div>
          {MODULES.map(m => (
            <label key={m.id} style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 10, cursor: 'pointer' }}>
              <input type="checkbox" checked={modules.includes(m.id)} onChange={() => toggleModule(m.id)} style={{ width: 15, height: 15, accentColor: 'var(--accent)' }} />
              <span style={{ fontSize: 15 }}>{m.icon}</span>
              <span style={{ fontSize: 13, color: modules.includes(m.id) ? 'var(--text-1)' : 'var(--text-2)', fontWeight: modules.includes(m.id) ? 600 : 400 }}>{m.label}</span>
            </label>
          ))}
        </div>

        <div style={{ ...panel, padding: '18px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 14 }}>🎫 Service Desk</div>
          <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', cursor: 'pointer' }}>
            <input type="checkbox" checked={sdWithout} onChange={e => setSdWithout(e.target.checked)} style={{ width: 15, height: 15, accentColor: 'var(--accent)', marginTop: 2 }} />
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Acceso sin proyecto vinculado</div>
              <div style={{ fontSize: 11, color: 'var(--text-2)' }}>Puede abrir tickets aunque no tenga proyectos asignados</div>
            </div>
          </label>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ ...panel, padding: '18px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 14 }}>🌍 Idioma y SLA</div>
          <div style={{ marginBottom: 14 }}>
            <label style={lbl}>Idioma por defecto del portal</label>
            <select value={defaultLang} onChange={e => setDefaultLang(e.target.value)} style={inp}>
              {languages.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
            <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 4 }}>Se aplica a nuevos usuarios. Cada usuario puede cambiarlo desde su perfil.</div>
          </div>
          <div>
            <label style={lbl}>Tier SLA</label>
            <select value={slaTier} onChange={e => setSlaTier(e.target.value)} style={inp}>
              <option value="">Sin tier</option>
              <option value="bronze">🥉 Bronze — 24h respuesta</option>
              <option value="silver">🥈 Silver — 8h respuesta</option>
              <option value="gold">🥇 Gold — 4h respuesta</option>
              <option value="enterprise">💎 Enterprise — 1h respuesta 24/7</option>
            </select>
            {slaTier && <div style={{ marginTop: 6, fontSize: 11, padding: '6px 10px', borderRadius: 6, background: (SLA_COLOR[slaTier] || 'var(--text-2)') + '15', color: SLA_COLOR[slaTier] || 'var(--text-2)' }}>
              Tier activo: <strong>{slaTier.toUpperCase()}</strong>
            </div>}
          </div>
        </div>

        <div style={{ ...panel, padding: '18px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 14 }}>👤 Perfil del cliente</div>
          <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 12 }}>Define qué puede modificar el cliente desde su perfil en el portal.</div>
          {[
            { key: 'allowEdit', val: allowEdit, set: setAllowEdit, label: 'Puede editar su perfil', desc: 'Nombre visible, teléfono, cargo, idioma' },
            { key: 'allowPwd', val: allowPwd, set: setAllowPwd, label: 'Puede cambiar su contraseña', desc: 'El cliente puede actualizar su contraseña de acceso' },
          ].map(opt => (
            <label key={opt.key} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', cursor: 'pointer', marginBottom: 14, background: opt.val ? 'var(--accent-muted)' : 'transparent', border: `1px solid ${opt.val ? 'var(--accent-glow)' : 'var(--surface-4)'}`, borderRadius: 8, padding: '10px 12px' }}>
              <input type="checkbox" checked={opt.val} onChange={e => opt.set(e.target.checked)} style={{ width: 15, height: 15, accentColor: 'var(--accent)', marginTop: 2, flexShrink: 0 }} />
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: opt.val ? 'var(--text-1)' : 'var(--text-2)' }}>{opt.label}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{opt.desc}</div>
              </div>
            </label>
          ))}
          <div style={{ marginTop: 4 }}>
            <label style={lbl}>Máx. usuarios de portal</label>
            <input type="number" min={1} max={100} value={maxUsers} onChange={e => setMaxUsers(+e.target.value)} style={inp} />
          </div>
        </div>

        <Button onClick={() => save({ enabled_modules: modules, sd_without_project: sdWithout, sla_tier: slaTier || null, max_portal_users: maxUsers, default_language: defaultLang, allow_profile_edit: allowEdit, allow_pwd_change: allowPwd })} style={{ width: '100%' }} loading={saving}>
          💾 Guardar configuración del portal
        </Button>
      </div>
    </div>
  )
}
