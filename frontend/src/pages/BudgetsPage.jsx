/**
 * BudgetsPage — Presupuestos multi-período por departamento
 */
import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'

const fs = { width:'100%', background:'var(--color-background-secondary)', border:'.5px solid var(--color-border-secondary)', borderRadius:8, padding:'9px 12px', color:'var(--color-text-primary)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:500, color:'var(--color-text-secondary)', textTransform:'uppercase', letterSpacing:'.07em', display:'block', marginBottom:5 }
const card = { background:'var(--color-background-primary)', border:'.5px solid var(--color-border-tertiary)', borderRadius:12 }

const fmtEur = n => n == null ? '—' : new Intl.NumberFormat('es-ES',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(n)
const MONTHS = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

export default function BudgetsPage() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [year, setYear] = useState(new Date().getFullYear())
  const [selected, setSelected] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name:'', year:new Date().getFullYear(), department:'', total_amount:0, currency:'EUR' })
  const [editEntry, setEditEntry] = useState(null)
  const [entryForm, setEntryForm] = useState({ actual:0, committed:0, notes:'' })

  const { data: budgets = [], isLoading } = useQuery({ queryKey:['budgets', year], queryFn:()=>api.get(`/budgets?year=${year}`).then(r=>r.data) })
  const { data: summary } = useQuery({ queryKey:['budget-summary', year], queryFn:()=>api.get(`/budgets/summary?year=${year}`).then(r=>r.data) })

  const { mutate: create, isPending } = useMutation({
    mutationFn: d => api.post('/budgets', d),
    onSuccess: () => { qc.invalidateQueries(['budgets']); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: updateEntry } = useMutation({
    mutationFn: ({ id, month, data }) => api.patch(`/budgets/${id}/entry`, { month, ...data }),
    onSuccess: () => { qc.invalidateQueries(['budgets']); setEditEntry(null) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: approve } = useMutation({
    mutationFn: id => api.post(`/budgets/${id}/approve`),
    onSuccess: () => qc.invalidateQueries(['budgets']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const _sel = selected ? budgets.find(b => b.id === selected) : null
  const chartData = summary?.by_month?.map(m => ({ mes: MONTHS[m.month-1], Planificado: Math.round(m.planned), Real: Math.round(m.actual) })) || []

  return (
    <div style={{ padding:32 }}>
      <PageHeader title={t('budgets.title')} subtitle="Control presupuestario multi-período por departamento" />

      {/* Year selector + summary */}
      <div style={{ display:'flex', gap:16, marginBottom:24, alignItems:'center' }}>
        <div style={{ display:'flex', gap:6 }}>
          {[year-1, year, year+1].map(y => (
            <button key={y} onClick={()=>setYear(y)}
              style={{ padding:'6px 14px', borderRadius:8, border:`.5px solid ${year===y?'var(--color-border-info)':'var(--color-border-tertiary)'}`, background:year===y?'var(--color-background-info)':'transparent', color:year===y?'var(--color-text-info)':'var(--color-text-secondary)', fontSize:12, cursor:'pointer', fontFamily:'inherit', fontWeight:year===y?500:400 }}>
              {y}
            </button>
          ))}
        </div>
        {summary && (
          <div style={{ display:'flex', gap:16, marginLeft:12 }}>
            {[['Planificado', fmtEur(summary.total_planned)], ['Real', fmtEur(summary.total_actual)], ['Desviación', `${summary.deviation_pct > 0 ? '+' : ''}${summary.deviation_pct}%`]].map(([l,v]) => (
              <div key={l} style={{ fontSize:12 }}><span style={{ color:'var(--color-text-secondary)', marginRight:6 }}>{l}:</span><strong>{v}</strong></div>
            ))}
          </div>
        )}
        <Button onClick={()=>setShowCreate(true)} style={{ marginLeft:'auto' }}>+ Nuevo presupuesto</Button>
      </div>

      {/* Monthly chart */}
      {chartData.length > 0 && (
        <div style={{ ...card, padding:'16px 20px', marginBottom:24 }}>
          <div style={{ fontSize:13, fontWeight:500, marginBottom:12 }}>Planificado vs Real — {year}</div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={chartData}>
              <XAxis dataKey="mes" tick={{fontSize:11}} />
              <YAxis tickFormatter={v=>`${Math.round(v/1000)}k€`} tick={{fontSize:10}} />
              <Tooltip formatter={v=>[fmtEur(v)]} />
              <Bar dataKey="Planificado" fill="#85B7EB" radius={[3,3,0,0]} />
              <Bar dataKey="Real" fill="#1D9E75" radius={[3,3,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Budgets list */}
      {isLoading ? <Spinner /> : budgets.length === 0 ? (
        <EmptyState icon="💼" title="Sin presupuestos" description={`No hay presupuestos para ${year}`} />
      ) : (
        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
          {budgets.map(b => (
            <div key={b.id} style={{ ...card, padding:'16px 20px' }}>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:12 }}>
                <div>
                  <div style={{ display:'flex', gap:10, alignItems:'center', marginBottom:4 }}>
                    <span style={{ fontSize:14, fontWeight:500 }}>{b.name}</span>
                    {b.department && <span style={{ fontSize:11, padding:'1px 6px', borderRadius:4, background:'var(--color-background-secondary)', color:'var(--color-text-secondary)' }}>{b.department}</span>}
                    {b.is_approved
                      ? <span style={{ fontSize:11, padding:'1px 6px', borderRadius:4, background:'var(--color-background-success)', color:'var(--color-text-success)' }}>✓ Aprobado</span>
                      : <button onClick={()=>approve(b.id)} style={{ fontSize:11, padding:'2px 8px', borderRadius:4, background:'var(--color-background-warning)', color:'var(--color-text-warning)', border:'.5px solid var(--color-border-warning)', cursor:'pointer', fontFamily:'inherit' }}>Aprobar</button>
                    }
                  </div>
                  <div style={{ fontSize:12, color:'var(--color-text-secondary)' }}>
                    Planificado: {fmtEur(b.planned_total)} · Real: {fmtEur(b.actual_total)} · Desviación: <span style={{ color: b.deviation > 0 ? 'var(--color-text-danger)' : 'var(--color-text-success)', fontWeight:500 }}>{b.deviation > 0 ? '+' : ''}{fmtEur(b.deviation)}</span>
                  </div>
                </div>
                <button onClick={()=>setSelected(selected===b.id?null:b.id)}
                  style={{ background:'transparent', border:'.5px solid var(--color-border-secondary)', borderRadius:8, padding:'5px 12px', color:'var(--color-text-secondary)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
                  {selected===b.id ? 'Ocultar' : 'Ver detalle'}
                </button>
              </div>

              {/* Monthly grid */}
              {selected === b.id && (
                <div style={{ overflowX:'auto' }}>
                  <table style={{ width:'100%', borderCollapse:'collapse', fontSize:11 }}>
                    <thead>
                      <tr style={{ background:'var(--color-background-secondary)' }}>
                        <th style={{ padding:'6px 10px', textAlign:'left', fontWeight:500, color:'var(--color-text-secondary)' }}>Mes</th>
                        {MONTHS.map(m => <th key={m} style={{ padding:'6px 8px', textAlign:'right', fontWeight:500, color:'var(--color-text-secondary)', minWidth:65 }}>{m}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {['planned','actual','committed'].map(field => (
                        <tr key={field} style={{ borderBottom:'.5px solid var(--color-border-tertiary)' }}>
                          <td style={{ padding:'6px 10px', fontWeight:500, textTransform:'capitalize', color:'var(--color-text-secondary)' }}>{field}</td>
                          {b.entries.map(e => (
                            <td key={e.month} style={{ padding:'6px 8px', textAlign:'right', cursor: field==='actual'&&!e.is_locked?'pointer':'default' }}
                              onClick={()=>{ if(field==='actual'&&!e.is_locked){ setEditEntry({budget_id:b.id,month:e.month,entry:e}); setEntryForm({actual:e.actual,committed:e.committed,notes:e.notes||''}) }}}>
                              <span style={{ color: field==='actual'&&e.actual>e.planned?'var(--color-text-danger)':'var(--color-text-primary)' }}>
                                {e[field] > 0 ? `${(e[field]/1000).toFixed(1)}k` : '—'}
                              </span>
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div style={{ fontSize:11, color:'var(--color-text-tertiary)', marginTop:6 }}>Haz click en una celda de &quot;actual&quot; para actualizar el dato real del mes.</div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <Modal open title="Nuevo presupuesto" onClose={()=>setShowCreate(false)} width={480}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div><label style={ls}>Nombre</label><input value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} style={fs} /></div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
              <div><label style={ls}>Año</label><input type="number" value={form.year} onChange={e=>setForm(f=>({...f,year:+e.target.value}))} style={fs} /></div>
              <div><label style={ls}>Departamento</label><input value={form.department} onChange={e=>setForm(f=>({...f,department:e.target.value}))} style={fs} /></div>
            </div>
            <div><label style={ls}>Importe total anual (€)</label><input type="number" value={form.total_amount} onChange={e=>setForm(f=>({...f,total_amount:+e.target.value}))} style={fs} /></div>
            <div style={{ fontSize:12, color:'var(--color-text-secondary)' }}>Se distribuirá en 12 mensualidades iguales de {fmtEur((form.total_amount||0)/12)}.</div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
              <Button variant="secondary" onClick={()=>setShowCreate(false)}>Cancelar</Button>
              <Button onClick={()=>create(form)} disabled={isPending||!form.name}>{isPending?'Creando...':'Crear presupuesto'}</Button>
            </div>
          </div>
        </Modal>
      )}

      {editEntry && (
        <Modal open title={`Actualizar ${MONTHS[editEntry.month-1]}`} onClose={()=>setEditEntry(null)} width={400}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div><label style={ls}>Gasto real (€)</label><input type="number" value={entryForm.actual} onChange={e=>setEntryForm(f=>({...f,actual:+e.target.value}))} style={fs} /></div>
            <div><label style={ls}>Comprometido (€)</label><input type="number" value={entryForm.committed} onChange={e=>setEntryForm(f=>({...f,committed:+e.target.value}))} style={fs} /></div>
            <div><label style={ls}>Notas</label><input value={entryForm.notes} onChange={e=>setEntryForm(f=>({...f,notes:e.target.value}))} style={fs} /></div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
              <Button variant="secondary" onClick={()=>setEditEntry(null)}>Cancelar</Button>
              <Button onClick={()=>updateEntry({ id:editEntry.budget_id, month:editEntry.month, data:entryForm })}>Guardar</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
