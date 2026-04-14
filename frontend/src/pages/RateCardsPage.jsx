import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { rateCardsApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { Button, Modal, EmptyState } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'

const inp = { background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '7px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }
const lbl = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }
const panel = { background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12 }

// ── Formulario de entrada ─────────────────────────────────────────────────────
function EntryForm({ tableId, entry, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const isEdit = !!entry?.id
  const [form, setForm] = useState({
    label:          entry?.label          || '',
    billing_rate:   entry?.billing_rate   || '',
    cost_rate:      entry?.cost_rate      || '',
    escalation_pct: entry?.escalation_pct || 0,
    valid_from:     entry?.valid_from     || '',
    valid_to:       entry?.valid_to       || '',
    notes:          entry?.notes          || '',
  })

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit
      ? rateCardsApi.updateEntry(tableId, entry.id, d)
      : rateCardsApi.addEntry(tableId, d),
    onSuccess: () => {
      qc.invalidateQueries(['rate-card', tableId])
      toast.success(isEdit ? 'Entrada actualizada' : 'Entrada añadida')
      onClose()
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const save = () => {
    if (!form.label) return
    mutate({
      ...form,
      billing_rate:   form.billing_rate   ? +form.billing_rate   : null,
      cost_rate:      form.cost_rate      ? +form.cost_rate      : null,
      escalation_pct: +form.escalation_pct,
    })
  }

  return (
    <Modal open title={isEdit ? '✏️ Editar tarifa' : '+ Nueva tarifa'} onClose={onClose} width={500}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={lbl}>Rol / Perfil *</label>
          <input value={form.label} onChange={e => setForm(f=>({...f,label:e.target.value}))} style={inp} placeholder="Ej: Senior Developer, PM, UX Designer" />
        </div>
        <div>
          <label style={lbl}>Tarifa facturación (€/h)</label>
          <input type="number" value={form.billing_rate} onChange={e => setForm(f=>({...f,billing_rate:e.target.value}))} style={inp} placeholder="120" />
        </div>
        <div>
          <label style={lbl}>Coste interno (€/h)</label>
          <input type="number" value={form.cost_rate} onChange={e => setForm(f=>({...f,cost_rate:e.target.value}))} style={inp} placeholder="65" />
        </div>
        <div>
          <label style={lbl}>Escalado anual (%)</label>
          <input type="number" value={form.escalation_pct} onChange={e => setForm(f=>({...f,escalation_pct:e.target.value}))} style={inp} placeholder="3" min="0" max="20" step="0.5" />
        </div>
        <div>
          <label style={lbl}>Válido desde</label>
          <input type="date" value={form.valid_from} onChange={e => setForm(f=>({...f,valid_from:e.target.value}))} style={inp} />
        </div>
        <div>
          <label style={lbl}>Válido hasta</label>
          <input type="date" value={form.valid_to} onChange={e => setForm(f=>({...f,valid_to:e.target.value}))} style={inp} />
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={lbl}>Notas</label>
          <input value={form.notes} onChange={e => setForm(f=>({...f,notes:e.target.value}))} style={inp} placeholder="Notas internas" />
        </div>
      </div>

      {form.billing_rate && form.cost_rate && (
        <div style={{ background: 'var(--success-bg)', border: '1px solid #00e5a020', borderRadius: 8, padding: '8px 12px', marginBottom: 14, fontSize: 12, color: 'var(--success)' }}>
          💰 Margen: <strong>{Math.round((1 - form.cost_rate / form.billing_rate) * 100)}%</strong>
          {form.escalation_pct > 0 && ` · Tarifa en 1 año: ${Math.round(form.billing_rate * (1 + form.escalation_pct/100))}€/h`}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={onClose} style={{ background:'transparent', border:'1px solid #1e2d45', borderRadius:8, padding:'7px 16px', color:'var(--text-2)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>Cancelar</button>
        <Button onClick={save} loading={isPending} disabled={!form.label || isPending}>
          {isEdit ? '💾 Guardar' : '+ Añadir'}
        </Button>
      </div>
    </Modal>
  )
}

// ── Detalle de tabla ──────────────────────────────────────────────────────────
function RateTableDetail({ tableId, onBack }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [showEntry, setShowEntry]   = useState(false)
  const [editEntry, setEditEntry]   = useState(null)
  const [showDupe, setShowDupe]     = useState(false)
  const [dupeEsc, setDupeEsc]       = useState(3)

  const { data: table, isLoading } = useQuery({
    queryKey: ['rate-card', tableId],
    queryFn: () => rateCardsApi.get(tableId).then(r => r.data),
  })

  const { mutate: deleteEntry } = useMutation({
    mutationFn: eid => rateCardsApi.deleteEntry(tableId, eid),
    onSuccess: () => { qc.invalidateQueries(['rate-card', tableId]); toast.success('Entrada eliminada') },

    onError: e => toast.error(extractErr(e, 'Error'))
  })

  const { mutate: duplicate, isPending: duping } = useMutation({
    mutationFn: () => rateCardsApi.duplicate(tableId, { escalation_pct: dupeEsc }),
    onSuccess: () => { qc.invalidateQueries(['rate-cards']); toast.success('Tabla duplicada con escalado'); setShowDupe(false); onBack() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  if (isLoading) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-2)' }}>Cargando...</div>
  if (!table) return null

  const entries = table.entries || []
  const avgMargin = entries.filter(e => e.billing_rate && e.cost_rate).length > 0
    ? Math.round(entries.filter(e => e.billing_rate && e.cost_rate)
        .reduce((s, e) => s + (1 - e.cost_rate / e.billing_rate), 0)
        / entries.filter(e => e.billing_rate && e.cost_rate).length * 100)
    : null

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 20 }}>
        <button onClick={onBack} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8, padding: '6px 12px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
          ← Volver
        </button>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 18, fontWeight: 800 }}>{table.name}</div>
          {table.description && <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{table.description}</div>}
        </div>
        {avgMargin !== null && (
          <div style={{ fontSize: 13, color: 'var(--success)', fontWeight: 700, background: 'var(--success-bg)', padding: '4px 12px', borderRadius: 8 }}>
            Margen medio: {avgMargin}%
          </div>
        )}
        <button onClick={() => setShowDupe(true)} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8, padding: '6px 14px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
          📋 Duplicar con escalado
        </button>
        <Button onClick={() => setShowEntry(true)}>+ Nueva tarifa</Button>
      </div>

      {entries.length === 0 ? (
        <EmptyState icon="💰" title="Sin tarifas definidas" description="Añade tarifas por rol para esta tabla" />
      ) : (
        <div style={{ ...panel, overflow: 'hidden' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #1e2d45' }}>
                {['Rol / Perfil', 'Facturación', 'Coste', 'Margen', 'Escalado', 'Vigencia', ''].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '10px 16px', fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => {
                const margin = e.billing_rate && e.cost_rate
                  ? Math.round((1 - e.cost_rate / e.billing_rate) * 100) : null
                return (
                  <tr key={e.id} style={{ borderBottom: '1px solid #0d1626', background: i % 2 === 0 ? 'transparent' : 'rgba(8,14,26,0.03)' }}>
                    <td style={{ padding: '10px 16px', fontSize: 13, fontWeight: 600, color: 'var(--text-1)' }}>{e.label}</td>
                    <td style={{ padding: '10px 16px', fontSize: 13, fontWeight: 700, color: 'var(--accent)', fontFamily: "'Space Mono', monospace" }}>
                      {e.billing_rate ? `${e.billing_rate}€/h` : '—'}
                    </td>
                    <td style={{ padding: '10px 16px', fontSize: 13, color: 'var(--text-2)', fontFamily: "'Space Mono', monospace" }}>
                      {e.cost_rate ? `${e.cost_rate}€/h` : '—'}
                    </td>
                    <td style={{ padding: '10px 16px' }}>
                      {margin !== null && (
                        <span style={{ fontSize: 12, fontWeight: 700, color: margin > 50 ? 'var(--success)' : margin > 30 ? 'var(--warning)' : 'var(--danger)' }}>
                          {margin}%
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '10px 16px', fontSize: 11, color: 'var(--text-2)' }}>
                      {e.escalation_pct > 0 ? `+${e.escalation_pct}%/año` : '—'}
                    </td>
                    <td style={{ padding: '10px 16px', fontSize: 11, color: 'var(--text-2)' }}>
                      {e.valid_from || e.valid_to ? `${e.valid_from || '?'} → ${e.valid_to || '∞'}` : '—'}
                    </td>
                    <td style={{ padding: '10px 16px' }}>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button onClick={() => setEditEntry(e)} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '3px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>✏️</button>
                        <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar tarifa "${e.label}"?`, onConfirm: () => deleteEntry(e.id), danger: true }) }} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '3px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {(showEntry || editEntry) && (
        <EntryForm tableId={tableId} entry={editEntry} onClose={() => { setShowEntry(false); setEditEntry(null) }} />
      )}

      {showDupe && (
        <Modal open title="📋 Duplicar tabla con escalado" onClose={() => setShowDupe(false)} width={420}>
          <div style={{ marginBottom: 16 }}>
            <label style={lbl}>Escalado anual (%)</label>
            <input type="number" value={dupeEsc} onChange={e => setDupeEsc(+e.target.value)} style={inp} min="0" max="20" step="0.5" />
            <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 6 }}>
              Se creará una copia de &quot;{table.name}&quot; con todas las tarifas incrementadas en este porcentaje.
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowDupe(false)} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => duplicate()} loading={duping}>Duplicar +{dupeEsc}%</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
export default function RateCardsPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selected, setSelected]   = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm]           = useState({ name: '', description: '', applies_to: 'role', is_default: false })

  const { data: tables = [], isLoading } = useQuery({
    queryKey: ['rate-cards'],
    queryFn: () => rateCardsApi.list().then(r => r.data),
  })

  const { mutate: create, isPending } = useMutation({
    mutationFn: rateCardsApi.create,
    onSuccess: (res) => {
      qc.invalidateQueries(['rate-cards'])
      setShowCreate(false)
      setForm({ name: '', description: '', applies_to: 'role', is_default: false })
      setSelected(res.data.id)
      toast.success('Tabla de tarifas creada')
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: del } = useMutation({
    mutationFn: rateCardsApi.delete,
    onSuccess: () => { qc.invalidateQueries(['rate-cards']); toast.success('Tabla eliminada') },

    onError: e => toast.error(extractErr(e, 'Error'))
  })

  if (selected) return <RateTableDetail tableId={selected} onBack={() => setSelected(null)} />

  return (
    <div style={{ padding: 32 }}>
      <PageHeader title={t('rate_cards.title')} subtitle="Tablas de tarifas por rol, departamento o cliente" />

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 20 }}>
        <Button onClick={() => setShowCreate(true)}>+ Nueva tabla de tarifas</Button>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-2)' }}>Cargando...</div>
      ) : tables.length === 0 ? (
        <EmptyState icon="💰" title="Sin tablas de tarifas" description="Crea tablas de tarifas por rol para calcular márgenes y facturar correctamente" />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
          {tables.map(t => (
            <div key={t.id} style={{
              background: 'var(--surface-2)', border: `1px solid ${t.is_default ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
              borderRadius: 12, padding: '18px 20px', cursor: 'pointer',
              transition: 'border-color 0.15s',
            }}
              onClick={() => setSelected(t.id)}
              onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-glow)'}
              onMouseLeave={e => e.currentTarget.style.borderColor = t.is_default ? 'var(--accent-glow)' : 'var(--surface-4)'}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-1)' }}>{t.name}</div>
                <div style={{ display: 'flex', gap: 4 }}>
                  {t.is_default && (
                    <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'var(--accent-muted)', color: 'var(--accent)', fontWeight: 700 }}>DEFAULT</span>
                  )}
                  <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'var(--surface-4)', color: 'var(--text-2)' }}>
                    {t.applies_to}
                  </span>
                </div>
              </div>
              {t.description && <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 10 }}>{t.description}</div>}
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                💶 {t.entry_count || 0} tarifa{t.entry_count !== 1 ? 's' : ''} definida{t.entry_count !== 1 ? 's' : ''}
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 10 }}>
                <button onClick={e => { e.stopPropagation(); openConfirmGlobal({message:`¿Eliminar tabla "${t.name}"?`,onConfirm:()=>del(t.id),danger:true}) }}
                  style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '3px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>
                  🗑
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <Modal open title="Nueva tabla de tarifas" onClose={() => setShowCreate(false)} width={480}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
            <div>
              <label style={lbl}>Nombre *</label>
              <input value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} style={inp} placeholder="Ej: Tarifas 2025 — Consultoría" />
            </div>
            <div>
              <label style={lbl}>Descripción</label>
              <input value={form.description} onChange={e => setForm(f=>({...f,description:e.target.value}))} style={inp} placeholder="Uso interno" />
            </div>
            <div>
              <label style={lbl}>Aplicar a</label>
              <select value={form.applies_to} onChange={e => setForm(f=>({...f,applies_to:e.target.value}))} style={inp}>
                <option value="role">Por Rol / Perfil</option>
                <option value="department">Por Departamento</option>
                <option value="client">Por Cliente</option>
              </select>
            </div>
            <label style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer', fontSize: 12, color: 'var(--text-1)' }}>
              <input type="checkbox" checked={form.is_default} onChange={e => setForm(f=>({...f,is_default:e.target.checked}))} style={{ accentColor: 'var(--accent)' }} />
              Tabla por defecto (se usa cuando no hay otra específica)
            </label>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowCreate(false)} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => create(form)} loading={isPending} disabled={!form.name || isPending}>Crear tabla</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
