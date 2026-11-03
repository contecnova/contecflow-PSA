import { useState } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, usersApi, risksApi } from '../services/api'
import { Card, Button, Modal, Spinner, EmptyState, useSort, ViewToggle, Tabs } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AlertTriangle } from 'lucide-react'
import { fmtCurrency, extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'

type RiskLevel = 'critical' | 'high' | 'medium' | 'low' | string
type RiskStatus = 'identified' | 'analyzing' | 'mitigating' | 'monitoring' | 'closed' | 'materialized' | string
type RiskProbability = 'very_low' | 'low' | 'medium' | 'high' | 'very_high' | string
type RiskImpact = 'negligible' | 'minor' | 'moderate' | 'major' | 'critical' | string

type ProjectItem = { id: string | number; code?: string; name: string }
type UserItem = { id: string | number; full_name?: string }

type RiskItem = {
  id: string | number
  code?: string
  project_id: string | number
  project_name?: string
  title: string
  description?: string
  category?: string
  category_label?: string
  probability: RiskProbability
  probability_label?: string
  impact: RiskImpact
  impact_label?: string
  status: RiskStatus
  status_label?: string
  response_type?: string
  owner_id?: string | number
  owner_name?: string
  review_date?: string
  cost_impact_min?: number | string
  cost_impact_max?: number | string
  schedule_impact_days?: number | string
  mitigation_plan?: string
  contingency_plan?: string
  notes?: string
  risk_level?: RiskLevel
}

type RiskSummary = {
  total?: number
  open?: number
  critical_count?: number
  high_count?: number
}

type RisksResponse = {
  risks: RiskItem[]
  summary: RiskSummary
}

type RiskFormState = {
  title: string
  description: string
  category: string
  probability: RiskProbability
  impact: RiskImpact
  status: RiskStatus
  mitigation_plan: string
  contingency_plan: string
  response_type: string
  owner_id: string
  review_date: string
  cost_impact_min: number | string
  cost_impact_max: number | string
  schedule_impact_days: number | string
  notes: string
}

type SortKey = 'risk_level' | 'title' | 'status' | 'project_name'

// ── Estilos compartidos ───────────────────────────────────────────────────────
const _fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const _ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }


const PROB_OPTIONS = [
  { value: 'very_low', label: 'Muy baja' },
  { value: 'low', label: 'Baja' },
  { value: 'medium', label: 'Media' },
  { value: 'high', label: 'Alta' },
  { value: 'very_high', label: 'Muy alta' },
]
const IMPACT_OPTIONS = [
  { value: 'negligible', label: 'Despreciable' },
  { value: 'minor', label: 'Menor' },
  { value: 'moderate', label: 'Moderado' },
  { value: 'major', label: 'Mayor' },
  { value: 'critical', label: 'Crítico' },
]
const STATUS_OPTIONS = [
  { value: 'identified', label: 'Identificado' },
  { value: 'analyzing', label: 'Analizando' },
  { value: 'mitigating', label: 'Mitigando' },
  { value: 'monitoring', label: 'Monitorizando' },
  { value: 'closed', label: 'Cerrado' },
  { value: 'materialized', label: 'Materializado' },
]
const CATEGORIES = [
  { value: 'technical', label: 'Técnico' },
  { value: 'financial', label: 'Financiero' },
  { value: 'schedule', label: 'Planificación' },
  { value: 'resource', label: 'Recursos' },
  { value: 'external', label: 'Externo' },
  { value: 'quality', label: 'Calidad' },
]
const RESPONSE_TYPES = [
  { value: 'avoid', label: 'Evitar' },
  { value: 'mitigate', label: 'Mitigar' },
  { value: 'transfer', label: 'Transferir' },
  { value: 'accept', label: 'Aceptar' },
]
const LEVEL_CFG: Record<string, { color: string; bg: string; label: string }> = {
  critical: { color: 'var(--danger)', bg: 'var(--danger-bg)', label: 'Crítico' },
  high:     { color: 'var(--warning)', bg: 'var(--warning-bg)', label: 'Alto' },
  medium:   { color: 'var(--accent)', bg: 'var(--accent-muted)', label: 'Medio' },
  low:      { color: 'var(--success)', bg: 'var(--success-bg)', label: 'Bajo' },
}

function RiskMatrix({ risks }: { risks: RiskItem[] }) {
  const probs = ['very_low', 'low', 'medium', 'high', 'very_high']
  const impacts = ['negligible', 'minor', 'moderate', 'major', 'critical']
  const t = useAppT() as (key: string) => string
  const probLabels: Record<string, string> = {
    very_low: t('risks.options.prob_very_low_short'),
    low: t('risks.options.prob_low_short'),
    medium: t('risks.options.prob_medium_short'),
    high: t('risks.options.prob_high_short'),
    very_high: t('risks.options.prob_very_high_short'),
  }
  const impactLabels = {
    negligible: t('risks.options.impact_negligible_short'),
    minor: t('risks.options.impact_minor_short'),
    moderate: t('risks.options.impact_moderate_short'),
    major: t('risks.options.impact_major_short'),
    critical: t('risks.options.impact_critical_short'),
  }

  const getColor = (p: string, i: string) => {
    const ps = probs.indexOf(p)
    const is = impacts.indexOf(i)
    const score = (ps + 1) * (is + 1)
    if (score >= 15) return 'var(--danger)'
    if (score >= 8) return 'var(--warning)'
    if (score >= 4) return 'var(--accent)'
    return 'var(--success)'
  }

  const cellRisks = (p: string, i: string) => risks.filter((r) => r.probability === p && r.impact === i)

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'separate', borderSpacing: 4 }}>
        <thead>
          <tr>
            <th style={{ padding: '6px 10px', fontSize: "var(--text-xs)", color: 'var(--text-2)', textAlign: 'right' }}>{t('risks.matrix.axis')}</th>
            {probs.map(p => <th key={p} style={{ padding: '6px 10px', fontSize: "var(--text-xs)", color: 'var(--text-2)', textAlign: 'center', width: 90 }}>{probLabels[p]}</th>)}
          </tr>
        </thead>
        <tbody>
          {[...impacts].reverse().map(imp => (
            <tr key={imp}>
              <td style={{ padding: '4px 10px', fontSize: "var(--text-xs)", color: 'var(--text-2)', textAlign: 'right', whiteSpace: 'nowrap' }}>{impactLabels[imp as keyof typeof impactLabels]}</td>
              {probs.map(prob => {
                const color = getColor(prob, imp)
                const cr = cellRisks(prob, imp)
                return (
                  <td key={prob} style={{ padding: 4 }}>
                    <div style={{ width: 82, height: 52, borderRadius: 6, background: alpha(color, '20'), border: `1px solid ${alpha(color, '40')}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
                      {cr.length > 0 && (
                        <>
                          <div style={{ fontSize: "var(--text-lg)", fontWeight: 800, color, fontFamily: 'var(--font-mono)' }}>{cr.length}</div>
                          <div style={{ fontSize: "var(--text-3xs)", color: color, maxWidth: 70, textAlign: 'center', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {cr[0].code}
                            {cr.length > 1 ? ` +${cr.length - 1}` : ''}
                          </div>
                        </>
                      )}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RiskFormModal({ risk, projectId, onClose }: { risk?: RiskItem | null; projectId: string | number; onClose: () => void }) {
  const t = useAppT() as (key: string) => string
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!risk?.id
  const { data: users = [] } = useQuery<UserItem[]>({ queryKey: ['users'], queryFn: () => usersApi.list({}).then(r => r.data as UserItem[]) })
  const [form, setForm] = useState<RiskFormState>({
    title: risk?.title || '',
    description: risk?.description || '',
    category: risk?.category || 'technical',
    probability: risk?.probability || 'medium',
    impact: risk?.impact || 'moderate',
    status: risk?.status || 'identified',
    mitigation_plan: risk?.mitigation_plan || '',
    contingency_plan: risk?.contingency_plan || '',
    response_type: risk?.response_type || 'mitigate',
    owner_id: risk?.owner_id != null ? String(risk.owner_id) : '',
    review_date: risk?.review_date || '',
    cost_impact_min: risk?.cost_impact_min || '',
    cost_impact_max: risk?.cost_impact_max || '',
    schedule_impact_days: risk?.schedule_impact_days || '',
    notes: risk?.notes || '',
  })
  const set = <K extends keyof RiskFormState>(k: K) => (e: { target: { value: string } }) => setForm(f => ({ ...f, [k]: e.target.value as RiskFormState[K] }))
  const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

  const { mutate, isPending } = useMutation({
    mutationFn: (data: RiskFormState) => isEdit && risk
      ? risksApi.update(projectId, risk.id, data)
      : risksApi.create(projectId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['risks', projectId] }); onClose() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <Modal open title={isEdit ? t('risks.edit_title') : t('risks.new_title')} onClose={onClose} width={660}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>{t('risks.form.title')}</label>
          <input value={form.title} onChange={set('title')} style={fs} placeholder={t('risks.form.title_ph')} />
        </div>
        <div>
          <label style={ls}>{t('risks.form.category')}</label>
          <select value={form.category} onChange={set('category')} style={fs}>
            {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>{t('risks.form.status')}</label>
          <select value={form.status} onChange={set('status')} style={fs}>
            {STATUS_OPTIONS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>{t('risks.form.prob')}</label>
          <select value={form.probability} onChange={set('probability')} style={fs}>
            {PROB_OPTIONS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>{t('risks.form.impact')}</label>
          <select value={form.impact} onChange={set('impact')} style={fs}>
            {IMPACT_OPTIONS.map(i => <option key={i.value} value={i.value}>{i.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>{t('risks.form.response_type')}</label>
          <select value={form.response_type} onChange={set('response_type')} style={fs}>
            {RESPONSE_TYPES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>{t('risks.form.owner')}</label>
          <select value={form.owner_id} onChange={set('owner_id')} style={fs}>
            <option value="">{t('risks.form.unassigned')}</option>
            {users.map(u => <option key={u.id} value={String(u.id)}>{u.full_name}</option>)}
          </select>
        </div>
        <div>
          <label style={ls}>{t('risks.form.cost_min')}</label>
          <input type="number" value={form.cost_impact_min} onChange={set('cost_impact_min')} style={fs} placeholder={t('risks.form.cost_min_ph')} />
        </div>
        <div>
          <label style={ls}>{t('risks.form.cost_max')}</label>
          <input type="number" value={form.cost_impact_max} onChange={set('cost_impact_max')} style={fs} placeholder={t('risks.form.cost_max_ph')} />
        </div>
        <div>
          <label style={ls}>{t('risks.form.days_impact')}</label>
          <input type="number" value={form.schedule_impact_days} onChange={set('schedule_impact_days')} style={fs} placeholder={t('risks.form.days_impact_ph')} />
        </div>
        <div>
          <label style={ls}>{t('risks.form.review_date')}</label>
          <input type="date" value={form.review_date} onChange={set('review_date')} style={fs} />
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>{t('risks.form.description')}</label>
          <textarea value={form.description} onChange={set('description')} rows={2} style={{ ...fs, resize: 'vertical' }} />
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>{t('risks.form.mitigation_plan')}</label>
          <textarea value={form.mitigation_plan} onChange={set('mitigation_plan')} rows={2} style={{ ...fs, resize: 'vertical' }} placeholder={t('risks.form.mitigation_plan_ph')} />
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>{t('risks.form.contingency_plan')}</label>
          <textarea value={form.contingency_plan} onChange={set('contingency_plan')} rows={2} style={{ ...fs, resize: 'vertical' }} placeholder={t('risks.form.contingency_plan_ph')} />
        </div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>{t('risks.form.cancel')}</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.title} loading={isPending}>
            {isPending ? t('risks.form.saving') : isEdit ? t('risks.form.save') : t('risks.form.create')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function RisksPage() {
  const t = useAppT() as (key: string) => string
  const toast = useToast()
  const [selectedProject, setSelectedProject] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<RiskItem | null>(null)
  const [tab, setTab] = useState<'register' | 'matrix'>('register')
  const [riskLevelFilter, setRiskLevelFilter] = useState('')
  const [riskSortBy, setRiskSortBy] = useState<SortKey>('risk_level')
  const [view, setView] = useState<'list' | 'cards'>('list')
  const qc = useQueryClient()

  const { data: projects = [] } = useQuery<ProjectItem[]>({ queryKey: ['projects', { status: 'active' }], queryFn: () => projectsApi.list({ status: 'active' }).then(r => (r.data ?? []) as ProjectItem[]) })

  const { data: risksData, isLoading } = useQuery<RisksResponse>({
    queryKey: ['risks', selectedProject],
    queryFn: () => selectedProject
      ? risksApi.list(selectedProject, {}).then(r => r.data as RisksResponse)
      : risksApi.portfolioAll().then(r => {
          const items = (r.data?.items ?? r.data ?? []) as RiskItem[]
          return { risks: items, summary: { total: items.length } }
        }),
  })

  const { mutate: deleteRisk } = useMutation({
    mutationFn: ({ projectId, riskId }: { projectId: string | number; riskId: string | number }) => risksApi.delete(projectId, riskId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['risks', selectedProject] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const risks: RiskItem[] = risksData?.risks || []
  const summary: RiskSummary = risksData?.summary || {}
  const filteredRisks: RiskItem[] = riskLevelFilter ? risks.filter(r => r.risk_level === riskLevelFilter) : risks
  const { sortedData: sortedRisks } = useSort(filteredRisks, riskSortBy)

  return (
    <PageShell>
      <PageHeader
        icon={<AlertTriangle size={18} />}
        title={t('risks.title')}
        subtitle={t('risks.subtitle')}
        actions={
          <div style={{ display: 'flex', gap: 10 }}>
            <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
              style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', cursor: 'pointer', minWidth: 200 }}>
              <option value="">{t('risks.all_projects')}</option>
              {projects.map(p => <option key={p.id} value={String(p.id)}>{p.code} — {p.name}</option>)}
            </select>
            {selectedProject && <Button onClick={() => setShowCreate(true)} icon="＋">{t('risks.new_risk')}</Button>}
          </div>
        }
      />

      {/* Summary */}
      <div style={{ display: 'flex', gap: 14, marginBottom: 24, flexWrap: 'wrap' }}>
        {[
          { label: t('risks.summary.total'), value: summary.total || risks.length, color: 'var(--text-2)' },
          { label: t('risks.summary.open'), value: summary.open || risks.filter(r => !['closed','materialized'].includes(r.status)).length, color: 'var(--warning)' },
          { label: t('risks.summary.critical'), value: summary.critical_count || risks.filter(r => r.risk_level === 'critical').length, color: 'var(--danger)' },
          { label: t('risks.summary.high'), value: summary.high_count || risks.filter(r => r.risk_level === 'high').length, color: 'var(--warning)' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '14px 18px', flex: 1 }}>
            <div style={{ fontSize: "var(--text-2xl)", fontWeight: 800, fontFamily: 'var(--font-mono)', color }}>{value}</div>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
          </div>
        ))}
      </div>

      <Tabs
        items={[
          { id: 'register', label: t('risks.tabs.register') },
          { id: 'matrix',   label: t('risks.tabs.matrix') },
        ]}
        active={tab}
        onChange={(id: string) => setTab(id as 'register' | 'matrix')}
        variant="pill"
        size="sm"
        ariaLabel={t('risks.title')}
        style={{ marginBottom: 20, borderBottom: 'none' }}
      />

      {isLoading ? <Spinner /> : risks.length === 0 ? (
        <EmptyState icon="🛡️" title={t('risks.empty.title')} description={selectedProject ? t('risks.empty.no_risks_project') : t('risks.empty.no_risks_portfolio')} />
      ) : tab === 'matrix' ? (
        <Card style={{ padding: 20 }}>
          <h3 style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 16, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{t('risks.matrix.title')}</h3>
          <RiskMatrix risks={risks} />
        </Card>
      ) : (
        <div>
          <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
            <select value={riskLevelFilter} onChange={e => setRiskLevelFilter(e.target.value)}
              style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 14px', color: riskLevelFilter ? 'var(--danger)' : 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
              <option value="">{t('risks.filters.all_levels')}</option>
              <option value="critical">🚨 {t('risks.options.level_critical')}</option>
              <option value="high">🔴 {t('risks.options.level_high')}</option>
              <option value="medium">🟡 {t('risks.options.level_medium')}</option>
              <option value="low">🟢 {t('risks.options.level_low')}</option>
            </select>
            <select value={riskSortBy} onChange={e => setRiskSortBy(e.target.value as SortKey)}
              style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
              <option value="risk_level">{t('risks.sort.level')}</option>
              <option value="title">{t('risks.sort.title')}</option>
              <option value="status">{t('risks.sort.status')}</option>
              <option value="project_name">{t('risks.sort.project')}</option>
            </select>
            <div style={{ marginLeft: 'auto' }}>
              <ViewToggle view={view} onChange={(v: string) => setView(v as 'list' | 'cards')} />
            </div>
          </div>
          {view === 'list' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {sortedRisks.map((r: RiskItem) => {
            const lvl = (r.risk_level && LEVEL_CFG[r.risk_level]) || LEVEL_CFG.low
            return (
              <div key={r.id} style={{ padding: '16px 20px', background: 'var(--surface-2)', border: `1px solid ${alpha(lvl.color, '30')}`, borderRadius: 12 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
                  <div style={{ width: 10, height: 10, borderRadius: '50%', background: lvl.color, marginTop: 4, flexShrink: 0 }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                      <div>
                        <span style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>{r.title}</span>
                        <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginLeft: 8, fontFamily: 'var(--font-mono)' }}>{r.code}</span>
                        {r.project_name && <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginLeft: 8 }}>· {r.project_name}</span>}
                      </div>
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: lvl.bg, color: lvl.color, border: `1px solid ${alpha(lvl.color, '40')}` }}>{lvl.label}</span>
                        <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{r.status_label}</span>
                        <button onClick={() => setEditing(r)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏️</button>
                        <button onClick={() => { openConfirmGlobal({ message: t('risks.delete_confirm'), onConfirm: () => deleteRisk({ projectId: r.project_id, riskId: r.id }), danger: true }) }} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 16, fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: r.mitigation_plan ? 8 : 0 }}>
                      <span>Prob: <span style={{ color: 'var(--text-1)' }}>{r.probability_label}</span></span>
                      <span>Impacto: <span style={{ color: 'var(--text-1)' }}>{r.impact_label}</span></span>
                      {r.category_label && <span>Tipo: <span style={{ color: 'var(--text-1)' }}>{r.category_label}</span></span>}
                      {r.owner_name && <span>Responsable: <span style={{ color: 'var(--text-1)' }}>{r.owner_name}</span></span>}
                      {r.cost_impact_max && <span>Impacto €: <span style={{ color: 'var(--warning)' }}>hasta {fmtCurrency(Number(r.cost_impact_max))}</span></span>}
                      {r.schedule_impact_days && <span>Plazo: <span style={{ color: 'var(--warning)' }}>+{r.schedule_impact_days}d</span></span>}
                    </div>
                    {r.mitigation_plan && (
                      <div style={{ marginTop: 8, fontSize: "var(--text-sm)", color: 'var(--text-2)', background: 'var(--surface-3)', borderRadius: 6, padding: '6px 10px' }}>
                        🛡️ <span style={{ color: 'var(--text-1)' }}>{r.mitigation_plan}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
          </div>
          ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
            {sortedRisks.map((r: RiskItem) => {
              const lvl = (r.risk_level && LEVEL_CFG[r.risk_level]) || LEVEL_CFG.low
              return (
                <div key={r.id} style={{ padding: '14px 16px', background: 'var(--surface-2)', border: `1px solid ${alpha(lvl.color, '30')}`, borderRadius: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ width: 10, height: 10, borderRadius: '50%', background: lvl.color, flexShrink: 0 }} />
                      <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, padding: '2px 7px', borderRadius: 20, background: lvl.bg, color: lvl.color }}>{lvl.label}</span>
                    </div>
                    <div style={{ display: 'flex', gap: 4 }}>
                      <button onClick={() => setEditing(r)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 5, padding: '2px 7px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏️</button>
                      <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar este riesgo?', onConfirm: () => deleteRisk({ projectId: r.project_id, riskId: r.id }), danger: true }) }} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 5, padding: '2px 7px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                    </div>
                  </div>
                  <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 4 }}>{r.title}</div>
                  {r.project_name && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 6 }}>📁 {r.project_name}</div>}
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
                    <span style={{ fontSize: "var(--text-xs)", padding: '2px 7px', borderRadius: 4, background: 'var(--surface-3)', color: 'var(--text-2)' }}>P: {r.probability_label}</span>
                    <span style={{ fontSize: "var(--text-xs)", padding: '2px 7px', borderRadius: 4, background: 'var(--surface-3)', color: 'var(--text-2)' }}>I: {r.impact_label}</span>
                    {r.owner_name && <span style={{ fontSize: "var(--text-xs)", padding: '2px 7px', borderRadius: 4, background: 'var(--surface-3)', color: 'var(--text-2)' }}>👤 {r.owner_name}</span>}
                  </div>
                  {r.mitigation_plan && (
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', lineHeight: 1.4, borderTop: '1px solid var(--surface-4)', paddingTop: 6, marginTop: 4 }}>
                      🛡️ {r.mitigation_plan.length > 80 ? r.mitigation_plan.slice(0, 80) + '…' : r.mitigation_plan}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          )}
        </div>
      )}

      {showCreate && <RiskFormModal projectId={selectedProject} onClose={() => setShowCreate(false)} />}
      {editing && <RiskFormModal risk={editing} projectId={editing.project_id} onClose={() => setEditing(null)} />}
    </PageShell>
  )
}