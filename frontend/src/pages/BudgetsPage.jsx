/**
 * BudgetsPage — Presupuestos multi-período por departamento
 */
import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { budgetsApi } from '../services/api'
import { settingsApi } from '../services/settingsApi'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { PieChart } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { useAppT } from '../i18n/AppLangContext'
import { z } from 'zod'
import { useFormValidation } from '../hooks/useFormValidation'

const fs = { width:'100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize: "var(--text-xs)", fontWeight:500, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'.07em', display:'block', marginBottom:5 }
const card = { background:'var(--surface-1)', border:'.5px solid var(--surface-4)', borderRadius:12 }

const fmtEur = n => n == null ? '—' : new Intl.NumberFormat('es-ES',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(n)
const MONTHS = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

const budgetSchema = z.object({
  name: z.string().trim().min(1, 'El nombre es obligatorio'),
  year: z.coerce.number().int().min(2000, 'El año no es válido').max(2100, 'El año no es válido'),
  department: z.string().optional(),
  total_amount: z.coerce.number().min(0, 'El importe total no puede ser negativo'),
  currency: z.string().trim().min(1),
})

const budgetEntrySchema = z.object({
  actual: z.coerce.number().min(0, 'El gasto real no puede ser negativo'),
  committed: z.coerce.number().min(0, 'El importe comprometido no puede ser negativo'),
  notes: z.string().optional(),
})

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
  const createValidation = useFormValidation(budgetSchema)
  const entryValidation = useFormValidation(budgetEntrySchema)

  const { data: budgets = [], isLoading } = useQuery({ queryKey:['budgets', year], queryFn:()=>budgetsApi.list(year).then(r=>r.data) })
  const { data: summary } = useQuery({ queryKey:['budget-summary', year], queryFn:()=>budgetsApi.summary(year).then(r=>r.data) })
  const { data: departments = [] } = useQuery({ queryKey:['departments-select'], queryFn:()=>settingsApi.getDepartments().then(r=>r.data) })

  const { mutate: create, isPending } = useMutation({
    mutationFn: d => budgetsApi.create(d),
    onSuccess: () => { qc.invalidateQueries(['budgets']); setShowCreate(false); createValidation.setErrors({}) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: updateEntry } = useMutation({
    mutationFn: ({ id, month, data }) => budgetsApi.updateEntry(id, month, data),
    onSuccess: () => { qc.invalidateQueries(['budgets']); setEditEntry(null); entryValidation.setErrors({}) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: approve } = useMutation({
    mutationFn: id => budgetsApi.approve(id),
    onSuccess: () => qc.invalidateQueries(['budgets']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const _sel = selected ? budgets.find(b => b.id === selected) : null
  const chartData = summary?.by_month?.map(m => ({ mes: MONTHS[m.month-1], Planificado: Math.round(m.planned), Real: Math.round(m.actual) })) || []

  const setCreateField = (key) => (e) => {
    const value = key === 'year' || key === 'total_amount' ? +e.target.value : e.target.value
    setForm(current => ({ ...current, [key]: value }))
    createValidation.clearFieldError(key)
  }

  const setEntryField = (key) => (e) => {
    const value = key === 'actual' || key === 'committed' ? +e.target.value : e.target.value
    setEntryForm(current => ({ ...current, [key]: value }))
    entryValidation.clearFieldError(key)
  }

  const submitCreate = () => {
    const result = createValidation.validateForm(form)
    if (!result.success) {
      return
    }
    create(result.data)
  }

  const submitEntry = () => {
    const result = entryValidation.validateForm(entryForm)
    if (!result.success) {
      return
    }
    updateEntry({ id:editEntry.budget_id, month:editEntry.month, data:result.data })
  }

  return (
    <PageShell>
      <PageHeader icon={<PieChart size={18} />} title={t('budgets.title')} subtitle={t('budgets.subtitle')} />

      {/* Year selector + summary */}
      <div style={{ display:'flex', gap:16, marginBottom:24, alignItems:'center' }}>
        <div style={{ display:'flex', gap:6 }}>
          {[year-1, year, year+1].map(y => (
            <button key={y} onClick={()=>setYear(y)}
              style={{ padding:'6px 14px', borderRadius:8, border:`.5px solid ${year===y?'rgba(0,212,255,0.25)':'var(--surface-4)'}`, background:year===y?'var(--accent-muted)':'transparent', color:year===y?'var(--accent)':'var(--text-2)', fontSize: "var(--text-sm)", cursor:'pointer', fontFamily:'inherit', fontWeight:year===y?500:400 }}>
              {y}
            </button>
          ))}
        </div>
        {summary && (
          <div style={{ display:'flex', gap:16, marginLeft:12 }}>
            {[['planned', fmtEur(summary.total_planned)], ['actual', fmtEur(summary.total_actual)], ['deviation', `${summary.deviation_pct > 0 ? '+' : ''}${summary.deviation_pct}%`]].map(([k,v]) => (
              <div key={k} style={{ fontSize: "var(--text-sm)" }}><span style={{ color:'var(--text-2)', marginRight:6 }}>{t(`budgets.${k}`)}:</span><strong>{v}</strong></div>
            ))}
          </div>
        )}
        <Button onClick={()=>setShowCreate(true)} style={{ marginLeft:'auto' }}>{t('budgets.new_budget')}</Button>
      </div>

      {/* Monthly chart */}
      {chartData.length > 0 && (
        <div style={{ ...card, padding:'16px 20px', marginBottom:24 }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight:500, marginBottom:12 }}>{t('budgets.chart_title', {year})}</div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={chartData}>
              <XAxis dataKey="mes" tick={{fontSize: "var(--text-xs)"}} />
              <YAxis tickFormatter={v=>`${Math.round(v/1000)}k€`} tick={{fontSize: "var(--text-2xs)"}} />
              <Tooltip formatter={v=>[fmtEur(v)]} />
              <Bar dataKey="Planificado" fill="#85B7EB" radius={[3,3,0,0]} />
              <Bar dataKey="Real" fill="#34d399" radius={[3,3,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Budgets list */}
      {isLoading ? <Spinner /> : budgets.length === 0 ? (
        <EmptyState icon="💼" title={t('budgets.empty_title')} description={t('budgets.empty_desc', {year})} />
      ) : (
        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
          {budgets.map(b => (
            <div key={b.id} style={{ ...card, padding:'16px 20px' }}>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:12 }}>
                <div>
                  <div style={{ display:'flex', gap:10, alignItems:'center', marginBottom:4 }}>
                    <span style={{ fontSize: "var(--text-md)", fontWeight:500 }}>{b.name}</span>
                    {b.department && <span style={{ fontSize: "var(--text-xs)", padding:'1px 6px', borderRadius:4, background:'var(--surface-2)', color:'var(--text-2)' }}>{b.department}</span>}
                    {b.is_approved
                      ? <span style={{ fontSize: "var(--text-xs)", padding:'1px 6px', borderRadius:4, background:'var(--success-bg)', color:'var(--success)' }}>✓ {t('budgets.approved')}</span>
                      : <button onClick={()=>approve(b.id)} style={{ fontSize: "var(--text-xs)", padding:'2px 8px', borderRadius:4, background:'var(--warning-bg)', color:'var(--warning)', border:'.5px solid rgba(251,191,36,0.25)', cursor:'pointer', fontFamily:'inherit' }}>{t('budgets.approve')}</button>
                    }
                  </div>
                  <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)' }}>
                    {t('budgets.planned')}: {fmtEur(b.planned_total)} · {t('budgets.actual')}: {fmtEur(b.actual_total)} · {t('budgets.deviation')}: <span style={{ color: b.deviation > 0 ? 'var(--danger)' : 'var(--success)', fontWeight:500 }}>{b.deviation > 0 ? '+' : ''}{fmtEur(b.deviation)}</span>
                  </div>
                </div>
                <button onClick={()=>setSelected(selected===b.id?null:b.id)}
                  style={{ background:'transparent', border:'.5px solid var(--surface-4)', borderRadius:8, padding:'5px 12px', color:'var(--text-2)', cursor:'pointer', fontSize: "var(--text-sm)", fontFamily:'inherit' }}>
                  {selected===b.id ? t('budgets.hide_detail') : t('budgets.show_detail')}
                </button>
              </div>

              {/* Monthly grid */}
              {selected === b.id && (
                <div style={{ overflowX:'auto' }}>
                  <table style={{ width:'100%', borderCollapse:'collapse', fontSize: "var(--text-xs)" }}>
                    <thead>
                      <tr style={{ background:'var(--surface-2)' }}>
                        <th style={{ padding:'6px 10px', textAlign:'left', fontWeight:500, color:'var(--text-2)' }}>Mes</th>
                        {MONTHS.map(m => <th key={m} style={{ padding:'6px 8px', textAlign:'right', fontWeight:500, color:'var(--text-2)', minWidth:65 }}>{m}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {['planned','actual','committed'].map(field => (
                        <tr key={field} style={{ borderBottom:'.5px solid var(--surface-4)' }}>
                          <td style={{ padding:'6px 10px', fontWeight:500, textTransform:'capitalize', color:'var(--text-2)' }}>{field}</td>
                          {b.entries.map(e => {
                            const val = Number(e[field]) || 0
                            const planned = Number(e.planned) || 0
                            const actual = Number(e.actual) || 0
                            return (
                              <td key={e.month} style={{ padding:'6px 8px', textAlign:'right', cursor: field==='actual'&&!e.is_locked?'pointer':'default' }}
                                onClick={()=>{ if(field==='actual'&&!e.is_locked){ setEditEntry({budget_id:b.id,month:e.month,entry:e}); setEntryForm({actual:e.actual,committed:e.committed,notes:e.notes||''}) }}}>
                                <span style={{ color: field==='actual'&&actual>planned?'var(--danger)':'var(--text-1)' }}>
                                  {val > 0 ? `${(val/1000).toFixed(1)}k` : '—'}
                                </span>
                              </td>
                            )
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div style={{ fontSize: "var(--text-xs)", color:'var(--text-3)', marginTop:6 }}>{t('budgets.edit_actual_hint')}</div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <Modal open title={t('budgets.new_budget')} onClose={()=>setShowCreate(false)} width={480}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div>
              <label style={ls}>{t('budgets.name')}</label>
              <input value={form.name} onChange={setCreateField('name')} style={createValidation.inputStyle(fs, 'name')} />
              {createValidation.errors.name && <div style={{ color:'var(--danger)', fontSize: "var(--text-xs)", marginTop:4 }}>{createValidation.errors.name}</div>}
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
              <div>
                <label style={ls}>{t('budgets.year')}</label>
                <input type="number" value={form.year} onChange={setCreateField('year')} style={createValidation.inputStyle(fs, 'year')} />
                {createValidation.errors.year && <div style={{ color:'var(--danger)', fontSize: "var(--text-xs)", marginTop:4 }}>{createValidation.errors.year}</div>}
              </div>
              <div><label style={ls}>{t('budgets.department')}</label><select value={form.department} onChange={setCreateField('department')} style={fs}><option value="">— Sin departamento —</option>{departments.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}</select></div>
            </div>
            <div>
              <label style={ls}>{t('budgets.total_amount')}</label>
              <input type="number" value={form.total_amount} onChange={setCreateField('total_amount')} style={createValidation.inputStyle(fs, 'total_amount')} />
              {createValidation.errors.total_amount && <div style={{ color:'var(--danger)', fontSize: "var(--text-xs)", marginTop:4 }}>{createValidation.errors.total_amount}</div>}
            </div>
            <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)' }}>{t('budgets.monthly_distribution', {amount: fmtEur((form.total_amount||0)/12)})}</div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
              <Button variant="secondary" onClick={()=>setShowCreate(false)}>{t('budgets.cancel')}</Button>
              <Button onClick={submitCreate} disabled={isPending}>{isPending?t('budgets.creating'):t('budgets.create')}</Button>
            </div>
          </div>
        </Modal>
      )}

      {editEntry && (
        <Modal open title={t('budgets.update_month', {month: MONTHS[editEntry.month-1]})} onClose={()=>setEditEntry(null)} width={400}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div>
              <label style={ls}>{t('budgets.actual_amount')}</label>
              <input type="number" value={entryForm.actual} onChange={setEntryField('actual')} style={entryValidation.inputStyle(fs, 'actual')} />
              {entryValidation.errors.actual && <div style={{ color:'var(--danger)', fontSize: "var(--text-xs)", marginTop:4 }}>{entryValidation.errors.actual}</div>}
            </div>
            <div>
              <label style={ls}>{t('budgets.committed_amount')}</label>
              <input type="number" value={entryForm.committed} onChange={setEntryField('committed')} style={entryValidation.inputStyle(fs, 'committed')} />
              {entryValidation.errors.committed && <div style={{ color:'var(--danger)', fontSize: "var(--text-xs)", marginTop:4 }}>{entryValidation.errors.committed}</div>}
            </div>
            <div><label style={ls}>{t('budgets.notes')}</label><input value={entryForm.notes} onChange={setEntryField('notes')} style={fs} /></div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
              <Button variant="secondary" onClick={()=>setEditEntry(null)}>{t('budgets.cancel')}</Button>
              <Button onClick={submitEntry}>{t('budgets.save')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </PageShell>
  )
}
