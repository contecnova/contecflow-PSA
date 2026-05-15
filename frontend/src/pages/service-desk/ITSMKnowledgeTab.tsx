import { useAppT } from "../../hooks/useAppT";
import { useId, useState } from 'react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import RcaWizardModal from '../../components/servicedesk/RcaWizardModal'

import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useToast } from '../../context/ToastContext'
import { sdKbApi, problemsApi } from '../../services/api'
import { Button, Spinner, EmptyState, Modal } from '../../components/ui'
import { COLOR } from '../../constants/theme'

const PRIORITY_COLOR = {
  p1_critical: COLOR.danger,
  p2_high: 'var(--orange)',
  p3_medium: COLOR.warning,
  p4_low: COLOR.text2,
}

const PRIORITY_LABEL = {
  p1_critical: 'P1 Critico',
  p2_high: 'P2 Alto',
  p3_medium: 'P3 Medio',
  p4_low: 'P4 Bajo',
}

function PBadge({ v }) {
  const color = PRIORITY_COLOR[v] || COLOR.text2
  return (
    <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color, padding: '2px 7px', borderRadius: 4, border: `1px solid ${color}30`, background: `${color}12`, whiteSpace: 'nowrap' }}>
      {PRIORITY_LABEL[v] || v}
    </span>
  )
}

function KELinkedTickets({ kedbId }) {
  const { data: tickets, isLoading } = useQuery({
    queryKey: ['sd-ke-tickets', kedbId],
    queryFn: () => sdKbApi.knownErrorTickets(kedbId).then(r => r.data).catch(() => []),
    staleTime: 30000,
  })
  if (isLoading) return <div style={{ padding: '8px 0' }}><Spinner /></div>
  if (!tickets?.length) return (
    <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', padding: '8px 0', borderTop: '1px solid var(--surface-4)', marginTop: 10 }}>
      No hay tickets vinculados a este error conocido.
    </div>
  )
  return (
    <div style={{ marginTop: 10, borderTop: '1px solid var(--surface-4)', paddingTop: 10 }}>
      <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', marginBottom: 8 }}>Tickets vinculados</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {tickets.map(tk => (
          <div key={tk.id} style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'var(--surface-4)', borderRadius: 6, padding: '6px 10px' }}>
            <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)' }}>#{tk.id}</span>
            <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)', flex: 1 }}>{tk.title}</span>
            <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>{tk.status}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function KnownErrors() {
  useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)
  const [editing, setEditing] = useState(null)
  const [expandedKE, setExpandedKE] = useState(null)

  const { data: kedb = [], isLoading } = useQuery({
    queryKey: ['sd-kedb'],
    queryFn: () => sdKbApi.knownErrors().then(r => r.data),
  })
  const { mutate: updateProblem } = useMutation({
    mutationFn: ({ id, ...data }) => problemsApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-kedb'] }); setEditing(null); toast.success('Error conocido actualizado') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const IS = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const LS = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
          Base de errores conocidos - Problemas con causa raiz y workaround documentado.
        </div>
        <Button onClick={() => { setEditing(null); setShowNew(true) }}>+ Nuevo error conocido</Button>
      </div>
      {isLoading ? <Spinner /> :
       kedb.length === 0 ? <EmptyState icon="📚" title="Sin errores conocidos" description="Crea el primer error conocido para documentar workaround y causa raíz." /> :
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {kedb.map(ke => (
          <div key={ke.id} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
              <div style={{ flex: 1 }}>
                <span style={{ fontSize: "var(--text-xs)", color: COLOR.warning, fontWeight: 700, marginRight: 10 }}>{ke.number}</span>
                <span style={{ fontSize: "var(--text-md)", fontWeight: 600, color: 'var(--text-1)' }}>{ke.title}</span>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <button
                  onClick={() => setExpandedKE(expandedKE === ke.id ? null : ke.id)}
                  style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', background: 'var(--surface-4)', padding: '2px 8px', borderRadius: 4, border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
                >
                  {ke.affected_tickets || 0} tickets {expandedKE === ke.id ? '▲' : '▼'}
                </button>
                <button onClick={() => setEditing(ke)} style={{ padding: '3px 10px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>✏ Editar</button>
              </div>
            </div>
            {ke.ci && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginBottom: 8 }}>CI afectado: {ke.ci}</div>}
            {ke.root_cause && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', marginBottom: 4 }}>CAUSA RAIZ</div>
                <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>{ke.root_cause}</div>
              </div>
            )}
            {ke.workaround ? (
              <div>
                <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: COLOR.success, marginBottom: 4 }}>WORKAROUND</div>
                <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', background: `${COLOR.success}08`, border: `1px solid ${COLOR.success}20`, borderRadius: 8, padding: '10px 14px' }}>
                  {ke.workaround}
                </div>
              </div>
            ) : ke.fix_description ? (
              <div>
                <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: COLOR.info, marginBottom: 4 }}>SOLUCIÓN DEFINITIVA</div>
                <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', background: `${COLOR.info}08`, border: `1px solid ${COLOR.info}20`, borderRadius: 8, padding: '10px 14px' }}>
                  {ke.fix_description}
                </div>
              </div>
            ) : null}
            {/* Linked tickets */}
            {expandedKE === ke.id && (
              <KELinkedTickets kedbId={ke.id} />
            )}
          </div>
        ))}
      </div>}

      {(showNew || editing) && (
        <KEDBModal
          item={editing}
          onClose={() => { setShowNew(false); setEditing(null) }}
          onSaved={(data) => {
            if (editing) {
              updateProblem({ id: editing.id, ...data })
            } else {
              problemsApi.create(data).then(() => {
                qc.invalidateQueries({ queryKey: ['sd-kedb'] })
                setShowNew(false)
                toast.success('Error conocido creado')
              }).catch(e => toast.error(e?.response?.data?.detail || 'Error'))
            }
          }}
          IS={IS} LS={LS}
        />
      )}
    </div>
  )
}

function KEDBModal({ item, onClose, onSaved, IS, LS }) {
  const idPrefix = useId()
  const isEdit = !!item
  const [form, setForm] = useState({
    title: item?.title || '',
    description: item?.description || '',
    root_cause: item?.root_cause || '',
    workaround: item?.workaround || '',
    fix_description: item?.fix_description || '',
    priority: item?.priority || 'p3_medium',
    status: item?.status || 'known_error',
  })
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <Modal open title={isEdit ? 'Editar error conocido' : 'Nuevo error conocido (KEDB)'} onClose={onClose} size="lg">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div><label htmlFor={`${idPrefix}-title`} style={LS}>Titulo *</label><input id={`${idPrefix}-title`} value={form.title} onChange={set('title')} style={IS} placeholder="Título del error conocido" /></div>
        <div><label htmlFor={`${idPrefix}-description`} style={LS}>Descripcion</label><textarea id={`${idPrefix}-description`} value={form.description} onChange={set('description')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder="Describe el error conocido" /></div>
        <div><label htmlFor={`${idPrefix}-root-cause`} style={LS}>Causa raiz</label><textarea id={`${idPrefix}-root-cause`} value={form.root_cause} onChange={set('root_cause')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder="Causa raíz identificada" /></div>
        <div><label htmlFor={`${idPrefix}-workaround`} style={LS}>Workaround (solución temporal)</label><textarea id={`${idPrefix}-workaround`} value={form.workaround} onChange={set('workaround')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder="Solución temporal disponible" /></div>
        <div><label htmlFor={`${idPrefix}-fix-description`} style={LS}>Solución definitiva</label><textarea id={`${idPrefix}-fix-description`} value={form.fix_description} onChange={set('fix_description')} rows={2} style={{ ...IS, resize: 'vertical' }} placeholder="Solución definitiva aplicada" /></div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div><label htmlFor={`${idPrefix}-priority`} style={LS}>Prioridad</label><select id={`${idPrefix}-priority`} value={form.priority} onChange={set('priority')} style={IS}>{['p1_critical', 'p2_high', 'p3_medium', 'p4_low'].map(p => <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}</select></div>
          <div><label htmlFor={`${idPrefix}-status`} style={LS}>Estado</label><select id={`${idPrefix}-status`} value={form.status} onChange={set('status')} style={IS}>{[['open', 'Abierto'], ['investigating', 'Investigando'], ['known_error', 'Error conocido'], ['resolved', 'Resuelto']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => onSaved(form)} disabled={!form.title.trim()}>{isEdit ? 'Guardar cambios' : 'Crear error conocido'}</Button>
        </div>
      </div>
    </Modal>
  )
}

function Problems() {
  useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState(null)
  const [rcaWizardProblem, setRcaWizardProblem] = useState(null)

  const { data: problems = [], isLoading } = useQuery({
    queryKey: ['sd-problems'],
    queryFn: () => problemsApi.list().then(r => r.data),
  })
  const { mutate: createProblem, isPending: creating } = useMutation({
    mutationFn: data => problemsApi.create(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-problems'] }); setShowModal(false); toast.success('Problema creado') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: updateProblem, isPending: updating } = useMutation({
    mutationFn: ({ id, ...data }) => problemsApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-problems'] }); setEditing(null); toast.success('Problema actualizado') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteProblem } = useMutation({
    mutationFn: id => problemsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-problems'] }); toast.success('Problema eliminado') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: promoteToKE, variables: promotingId } = useMutation({
    mutationFn: id => problemsApi.promoteKnownError(id),
    onSuccess: () => {
      toast.success('Problema promovido a Error Conocido (KEDB)')
      qc.invalidateQueries({ queryKey: ['sd-problems'] })
      qc.invalidateQueries({ queryKey: ['sd-kedb'] })
    },
    onError: e => toast.error(extractErr(e, 'Error al promover')),
  })

  const IS = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const LS = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

  const statusColors = {
    open: COLOR.danger,
    investigating: COLOR.warning,
    known_error: 'var(--orange)',
    resolved: COLOR.success,
    closed: COLOR.text2,
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
          Registro de problemas - causas raiz de incidentes recurrentes.
        </div>
        <Button onClick={() => { setEditing(null); setShowModal(true) }}>+ Nuevo problema</Button>
      </div>

      {isLoading ? <Spinner /> :
       problems.length === 0
        ? <EmptyState icon="🔍" title="Sin problemas registrados" description="Crea el primer problema para investigar incidentes recurrentes." />
        : <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {problems.map(p => {
              const sc = statusColors[p.status] || COLOR.text2
              return (
                <div key={p.id} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '16px 20px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                        <span style={{ fontSize: "var(--text-xs)", color: COLOR.warning, fontWeight: 700 }}>{p.number}</span>
                        <span style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: sc, background: `${sc}15`, padding: '2px 8px', borderRadius: 4 }}>
                          {p.status?.replace(/_/g, ' ')}
                        </span>
                        <PBadge v={p.priority} />
                        {p.related_tickets?.length > 0 && (
                          <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
                            {p.related_tickets.length} ticket{p.related_tickets.length !== 1 ? 's' : ''}
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: "var(--text-md)", fontWeight: 600, color: 'var(--text-1)' }}>{p.title}</div>
                    </div>
                    <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                      <button onClick={() => setRcaWizardProblem(p)} style={{ padding: '4px 10px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--info)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>🔍 RCA</button>
                      {p.status !== 'known_error' && (
                        <button
                          onClick={() => openConfirmGlobal({ message: `¿Promover "${p.title}" a Error Conocido (KEDB)?`, onConfirm: () => promoteToKE(p.id), danger: false })}
                          disabled={promotingId === p.id}
                          style={{ padding: '4px 10px', borderRadius: 6, border: '1px solid rgba(251,146,60,0.4)', background: 'transparent', color: 'var(--orange)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}
                        >
                          📋 Promover a KE
                        </button>
                      )}
                      <button onClick={() => { setEditing(p); setShowModal(true) }} style={{ padding: '4px 10px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>✏ Editar</button>
                      <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar "${p.title}"? Esta acción no se puede deshacer.`, onConfirm: () => deleteProblem(p.id), danger: true }) }} style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid rgba(255,71,87,0.3)', background: 'transparent', color: COLOR.danger, fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>🗑</button>
                    </div>
                  </div>
                  {p.root_cause && (
                    <div style={{ marginBottom: 8 }}>
                      <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', marginRight: 8 }}>Causa raiz</span>
                      <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{p.root_cause}</span>
                    </div>
                  )}
                  {p.workaround && (
                    <div style={{ background: `${COLOR.success}08`, border: `1px solid ${COLOR.success}20`, borderRadius: 8, padding: '8px 12px' }}>
                      <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: COLOR.success, textTransform: 'uppercase', marginRight: 8 }}>Workaround</span>
                      <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)' }}>{p.workaround}</span>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
      }

      {showModal && (
        <ProblemModal
          item={editing}
          onClose={() => { setShowModal(false); setEditing(null) }}
          onSaved={data => editing
            ? updateProblem({ id: editing.id, ...data })
            : createProblem(data)
          }
          isPending={creating || updating}
          IS={IS} LS={LS}
        />
      )}
      {rcaWizardProblem && (
        <RcaWizardModal
          problem={rcaWizardProblem}
          onClose={() => setRcaWizardProblem(null)}
          onCompleted={() => qc.invalidateQueries({ queryKey: ['sd-problems'] })}
        />
      )}
    </div>
  )
}

function ProblemModal({ item, onClose, onSaved, isPending, IS, LS }) {
  const idPrefix = useId()
  const isEdit = !!item
  const [form, setForm] = useState({
    title: item?.title || '',
    description: item?.description || '',
    root_cause: item?.root_cause || '',
    workaround: item?.workaround || '',
    fix_description: item?.fix_description || '',
    priority: item?.priority || 'p3_medium',
    status: item?.status || 'open',
  })
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  return (
    <Modal open title={isEdit ? `Editar - ${item.number}` : 'Nuevo problema'} onClose={onClose} size="lg">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div><label htmlFor={`${idPrefix}-title`} style={LS}>Titulo *</label><input id={`${idPrefix}-title`} value={form.title} onChange={set('title')} style={IS} placeholder="Título del problema" /></div>
        <div><label htmlFor={`${idPrefix}-description`} style={LS}>Descripcion</label><textarea id={`${idPrefix}-description`} value={form.description} onChange={set('description')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder="Describe el problema" /></div>
        <div><label htmlFor={`${idPrefix}-root-cause`} style={LS}>Causa raiz</label><textarea id={`${idPrefix}-root-cause`} value={form.root_cause} onChange={set('root_cause')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder="Causa raíz identificada" /></div>
        <div><label htmlFor={`${idPrefix}-workaround`} style={LS}>Workaround (solucion temporal)</label><textarea id={`${idPrefix}-workaround`} value={form.workaround} onChange={set('workaround')} rows={3} style={{ ...IS, resize: 'vertical' }} placeholder="Solución temporal" /></div>
        <div><label htmlFor={`${idPrefix}-fix-description`} style={LS}>Solucion definitiva (opcional)</label><textarea id={`${idPrefix}-fix-description`} value={form.fix_description} onChange={set('fix_description')} rows={2} style={{ ...IS, resize: 'vertical' }} placeholder="Solución definitiva" /></div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div><label htmlFor={`${idPrefix}-priority`} style={LS}>Prioridad</label><select id={`${idPrefix}-priority`} value={form.priority} onChange={set('priority')} style={IS}>{[['p1_critical', 'P1 Critico'], ['p2_high', 'P2 Alto'], ['p3_medium', 'P3 Medio'], ['p4_low', 'P4 Bajo']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
          <div><label htmlFor={`${idPrefix}-status`} style={LS}>Estado</label><select id={`${idPrefix}-status`} value={form.status} onChange={set('status')} style={IS}>{[['open', 'Abierto'], ['investigating', 'Investigando'], ['known_error', 'Error conocido'], ['resolved', 'Resuelto'], ['closed', 'Cerrado']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => onSaved(form)} disabled={isPending || !form.title.trim()} loading={isPending}>{isEdit ? 'Guardar cambios' : 'Crear problema'}</Button>
        </div>
      </div>
    </Modal>
  )
}

function KB() {
  useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [showNew, setShowNew] = useState(false)
  const [editing, setEditing] = useState(null)

  const { data: articles = [], isLoading } = useQuery({
    queryKey: ['sd-kb', search],
    queryFn: () => sdKbApi.list({ search: search || undefined }).then(r => r.data),
    staleTime: 30000,
  })
  const { mutate: deleteArticle } = useMutation({
    mutationFn: id => sdKbApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-kb'] }); toast.success('Articulo eliminado') },
    onError: () => toast.error('Error al eliminar'),
  })
  const { mutate: toggleStatus } = useMutation({
    mutationFn: ({ id, status }) => sdKbApi.update(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-kb'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const IS = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }

  const STATUS_COLOR = { published: COLOR.success, draft: COLOR.warning, archived: COLOR.text2 }

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        <input placeholder="Buscar artículos" aria-label="Buscar artículos" value={search} onChange={e => setSearch(e.target.value)} style={{ ...IS, flex: 1 }} />
        <Button onClick={() => { setEditing(null); setShowNew(true) }}>+ Nuevo articulo</Button>
      </div>
      {isLoading ? <Spinner /> :
      articles.length === 0 ? <EmptyState icon="📖" title="Sin artículos" description="Crea el primer artículo de conocimiento." /> :
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px,1fr))', gap: 14 }}>
        {articles.map(a => (
          <div key={a.id} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 18 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
              <div style={{ fontSize: "var(--text-md)", fontWeight: 600, color: 'var(--text-1)', flex: 1, marginRight: 8 }}>{a.title}</div>
              <span style={{ fontSize: "var(--text-2xs)", padding: '2px 6px', borderRadius: 4, whiteSpace: 'nowrap', background: `${STATUS_COLOR[a.status] || COLOR.text2}15`, color: STATUS_COLOR[a.status] || COLOR.text2 }}>
                {a.status}
              </span>
            </div>
            {a.summary && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 10 }}>{a.summary}</div>}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 12 }}>
              <span>👍 {a.helpful_count || 0}</span>
              <span>👁 {a.view_count || 0}</span>
              {a.tags && <span>🏷 {a.tags.split(',').slice(0, 2).join(', ')}</span>}
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button onClick={() => { setEditing(a); setShowNew(true) }} style={{ flex: 1, padding: '5px 0', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>✏ Editar</button>
              <button onClick={() => toggleStatus({ id: a.id, status: a.status === 'published' ? 'draft' : 'published' })} style={{ flex: 1, padding: '5px 0', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>{a.status === 'published' ? '⏸ Despublicar' : '▶ Publicar'}</button>
              <button onClick={() => { openConfirmGlobal({ message: 'Eliminar articulo?', onConfirm: () => deleteArticle(a.id), danger: true }) }} style={{ padding: '5px 8px', borderRadius: 6, border: `1px solid ${COLOR.danger}30`, background: 'transparent', color: COLOR.danger, fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>🗑</button>
            </div>
          </div>
        ))}
      </div>}

      {showNew && <KBArticleModal article={editing} onClose={() => { setShowNew(false); setEditing(null) }} onSaved={() => { qc.invalidateQueries({ queryKey: ['sd-kb'] }); setShowNew(false); setEditing(null) }} />}
    </div>
  )
}

function KBArticleModal({ article, onClose, onSaved }) {
  const idPrefix = useId()
  const toast = useToast()
  const isEdit = !!article
  const [form, setForm] = useState({
    title: article?.title || '',
    summary: article?.summary || '',
    body: article?.body || '',
    tags: article?.tags || '',
    status: article?.status || 'draft',
    is_public: article?.is_public ?? true,
  })
  const { mutate, isPending } = useMutation({
    mutationFn: data => isEdit ? sdKbApi.update(article.id, data) : sdKbApi.create(data),
    onSuccess: () => { toast.success(isEdit ? 'Articulo actualizado' : 'Articulo creado'); onSaved() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))
  const IS = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const LS = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

  return (
    <Modal open title={isEdit ? 'Editar articulo KB' : 'Nuevo articulo KB'} onClose={onClose} size="lg">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div><label style={LS}>Titulo *</label><input value={form.title} onChange={set('title')} style={IS} /></div>
        <div><label htmlFor={`${idPrefix}-summary`} style={LS}>Resumen</label><input id={`${idPrefix}-summary`} value={form.summary} onChange={set('summary')} style={IS} placeholder="Resumen del artículo" /></div>
        <div><label htmlFor={`${idPrefix}-body`} style={LS}>Contenido *</label><textarea id={`${idPrefix}-body`} value={form.body} onChange={set('body')} rows={8} style={{ ...IS, resize: 'vertical' }} placeholder="Contenido del artículo" /></div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div><label htmlFor={`${idPrefix}-tags`} style={LS}>Etiquetas (separadas por coma)</label><input id={`${idPrefix}-tags`} value={form.tags} onChange={set('tags')} style={IS} placeholder="etiqueta1, etiqueta2" /></div>
          <div><label htmlFor={`${idPrefix}-status`} style={LS}>Estado</label><select id={`${idPrefix}-status`} value={form.status} onChange={set('status')} style={IS}><option value="draft">Borrador</option><option value="published">Publicado</option><option value="archived">Archivado</option></select></div>
        </div>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: "var(--text-base)", color: 'var(--text-1)', cursor: 'pointer' }}><input type="checkbox" checked={form.is_public} onChange={set('is_public')} />Visible en el portal cliente</label>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.title || !form.body} loading={isPending}>{isEdit ? 'Guardar cambios' : 'Crear articulo'}</Button>
        </div>
      </div>
    </Modal>
  )
}

export default function ITSMKnowledgeTab({ mode }) {
  if (mode === 'problems') return <Problems />
  if (mode === 'kedb') return <KnownErrors />
  return <KB />
}
