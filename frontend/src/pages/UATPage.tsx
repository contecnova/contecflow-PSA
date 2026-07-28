/**
 * UATPage — Gestión de casos UAT (User Acceptance Testing)
 * Define criterios de aceptación por proyecto/tarea y registra su ejecución.
 * Permite exportar el plan para enviar al cliente.
 */
import { useId, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { uatApi, projectsApi, tasksApi } from '../services/api'
import { Spinner, EmptyState, Button, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { useToast } from '../context/ToastContext'
import { extractErr } from '../utils/helpers'
import { ClipboardCheck } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import type { CSSProperties, ChangeEvent } from 'react'

type UATStatus = 'pending' | 'passed' | 'failed' | 'blocked' | 'skipped'
type UATPriority = 'critical' | 'high' | 'medium' | 'low'

type UATCase = {
  id: string | number
  title: string
  description?: string
  expected_result?: string
  actual_result?: string
  status: UATStatus
  priority: UATPriority
  task_id?: string | number | ''
  task_title?: string
  notes?: string
}

type UATStats = {
  total: number
  pending: number
  passed: number
  failed: number
  blocked: number
}

type UATListResponse = {
  cases: UATCase[]
  stats: UATStats
}

type UATFormData = {
  title: string
  description: string
  expected_result: string
  actual_result: string
  status: UATStatus
  priority: UATPriority
  task_id: string
  notes: string
}

type ProjectItem = {
  id: string | number
  name: string
}

type TaskItem = {
  id: string | number
  title?: string
}

type ExportReport = {
  text: string
  cases_count: number
}

const STATUS_META: Record<UATStatus, { label: string; color: string; bg: string; icon: string }> = {
  pending:  { label: 'Pendiente', color: 'var(--text-2)',  bg: 'var(--surface-3)',     icon: '⏳' },
  passed:   { label: 'Pasado',    color: 'var(--success)', bg: 'rgba(74,222,128,0.12)', icon: '✅' },
  failed:   { label: 'Fallido',   color: 'var(--danger)',  bg: 'rgba(248,113,113,0.12)', icon: '❌' },
  blocked:  { label: 'Bloqueado', color: 'var(--warning)', bg: 'rgba(251,191,36,0.12)', icon: '🔒' },
  skipped:  { label: 'Omitido',   color: 'var(--text-3)',  bg: 'rgba(122,138,170,0.1)', icon: '⏭' },
}

const PRIORITY_META: Record<UATPriority, { label: string; color: string }> = {
  critical: { label: 'Crítica',  color: 'var(--danger)' },
  high:     { label: 'Alta',     color: 'var(--warning)' },
  medium:   { label: 'Media',    color: 'var(--accent)' },
  low:      { label: 'Baja',     color: 'var(--text-2)' },
}

const fs: CSSProperties = {
  background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8,
  padding: '9px 12px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none',
  fontFamily: 'inherit', width: '100%',
}
const ls: CSSProperties = {
  fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase',
  letterSpacing: '0.07em', display: 'block', marginBottom: 5,
}

function CaseFormModal({ open, onClose, onSave, initial, tasks = [] }: { open: boolean; onClose: () => void; onSave: (data: UATFormData) => void; initial?: UATCase | null; tasks?: TaskItem[] }) {
  const idPrefix = useId()
  const [form, setForm] = useState<UATFormData>({
    title: initial?.title || '',
    description: initial?.description || '',
    expected_result: initial?.expected_result || '',
    actual_result: initial?.actual_result || '',
    status: initial?.status || 'pending',
    priority: initial?.priority || 'medium',
    task_id: initial?.task_id != null ? String(initial.task_id) : '',
    notes: initial?.notes || '',
  })
  const s = <K extends keyof UATFormData>(k: K) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setForm(f => ({ ...f, [k]: e.target.value as UATFormData[K] }))
  const isEdit = !!initial?.id

  return (
    <Modal open={open} onClose={onClose} title={isEdit ? 'Editar caso UAT' : 'Nuevo caso UAT'} width={640}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label htmlFor={`${idPrefix}-title`} style={ls}>Título *</label>
          <input id={`${idPrefix}-title`} value={form.title} onChange={s('title')} style={fs} placeholder="Título del caso UAT" />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
          <div>
            <label htmlFor={`${idPrefix}-status`} style={ls}>Estado</label>
            <select id={`${idPrefix}-status`} value={form.status} onChange={s('status')} style={fs}>
              {Object.entries(STATUS_META).map(([v, m]) => (
                <option key={v} value={v}>{m.icon} {m.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor={`${idPrefix}-priority`} style={ls}>Prioridad</label>
            <select id={`${idPrefix}-priority`} value={form.priority} onChange={s('priority')} style={fs}>
              {Object.entries(PRIORITY_META).map(([v, m]) => (
                <option key={v} value={v}>{m.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor={`${idPrefix}-task-id`} style={ls}>Tarea vinculada</label>
            <select id={`${idPrefix}-task-id`} value={form.task_id} onChange={s('task_id')} style={fs}>
              <option value="">— Sin tarea —</option>
              {tasks.map(t => (
                <option key={t.id} value={String(t.id)}>{t.title}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label htmlFor={`${idPrefix}-description`} style={ls}>Pasos para ejecutar el test</label>
          <textarea id={`${idPrefix}-description`} value={form.description} onChange={s('description')} rows={3}
            style={{ ...fs, resize: 'vertical' }}
            placeholder="Pasos para ejecutar el test" />
        </div>

        <div>
          <label htmlFor={`${idPrefix}-expected-result`} style={ls}>Resultado esperado *</label>
          <textarea id={`${idPrefix}-expected-result`} value={form.expected_result} onChange={s('expected_result')} rows={2}
            style={{ ...fs, resize: 'vertical' }}
            placeholder="Resultado esperado" />
        </div>

        <div>
          <label htmlFor={`${idPrefix}-actual-result`} style={ls}>Resultado obtenido (rellenar al ejecutar)</label>
          <textarea id={`${idPrefix}-actual-result`} value={form.actual_result} onChange={s('actual_result')} rows={2}
            style={{ ...fs, resize: 'vertical' }}
            placeholder="Resultado obtenido" />
        </div>

        <div>
          <label htmlFor={`${idPrefix}-notes`} style={ls}>Notas internas</label>
          <textarea id={`${idPrefix}-notes`} value={form.notes} onChange={s('notes')} rows={2}
            style={{ ...fs, resize: 'vertical' }}
            placeholder="Notas internas" />
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, paddingTop: 4 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => onSave(form)} disabled={!form.title || !form.expected_result}>
            {isEdit ? 'Guardar cambios' : 'Crear caso UAT'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function ExportModal({ open, onClose, report }: { open: boolean; onClose: () => void; report: ExportReport }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(report?.text || '').then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }
  return (
    <Modal open={open} onClose={onClose} title="Exportar plan UAT" width={700}>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <Button variant="secondary" onClick={handleCopy}>
          {copied ? '✓ Copiado' : '📋 Copiar texto'}
        </Button>
      </div>
      <pre style={{
        background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 10,
        padding: '16px 18px', fontSize: "var(--text-sm)", color: 'var(--text-1)', whiteSpace: 'pre-wrap',
        maxHeight: 480, overflowY: 'auto', fontFamily: 'var(--font-mono)', lineHeight: 1.6,
      }}>
        {report?.text || ''}
      </pre>
      <div style={{ marginTop: 12, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
        {report?.cases_count} casos UAT · Copia este texto para enviar al cliente o pégalo en un documento.
      </div>
    </Modal>
  )
}

export default function UATPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editCase, setEditCase] = useState<UATCase | null>(null)
  const [exportReport, setExportReport] = useState<ExportReport | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<UATCase | null>(null)

  const { data: projects = [] } = useQuery<ProjectItem[]>({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list({}).then(r => r.data ?? []),
  })

  const { data: tasksData = [] } = useQuery<TaskItem[]>({
    queryKey: ['tasks', selectedProject],
    queryFn: () => tasksApi.list({ project_id: selectedProject }).then(r => r.data),
    enabled: !!selectedProject,
    select: (d: unknown) => {
      if (Array.isArray(d)) return d as TaskItem[]
      if (d && typeof d === 'object') {
        const maybe = d as { items?: TaskItem[]; tasks?: TaskItem[] }
        return maybe.items || maybe.tasks || []
      }
      return []
    },
  })

  const { data: uatData, isLoading } = useQuery<UATListResponse>({
    queryKey: ['uat-cases', selectedProject, statusFilter],
    queryFn: () => uatApi.list(selectedProject, { status: statusFilter || undefined }).then(r => r.data),
    enabled: !!selectedProject,
  })

  const cases = uatData?.cases || []
  const stats = uatData?.stats || { total: 0, pending: 0, passed: 0, failed: 0, blocked: 0 }

  const { mutate: createCase } = useMutation({
    mutationFn: (data: UATFormData) => uatApi.create(selectedProject, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['uat-cases'] }); setShowCreate(false); toast.success('Caso UAT creado') },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al crear caso')),
  })

  const { mutate: updateCase } = useMutation({
    mutationFn: ({ id, data }: { id: string | number; data: UATFormData | UATCase }) => uatApi.update(selectedProject, id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['uat-cases'] }); setEditCase(null); toast.success('Caso actualizado') },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al actualizar')),
  })

  const { mutate: deleteCase } = useMutation({
    mutationFn: (id: string | number) => uatApi.remove(selectedProject, id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['uat-cases'] }); toast.success('Caso eliminado') },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al eliminar')),
  })

  const handleExport = async () => {
    try {
      const r = await uatApi.export(selectedProject)
      setExportReport(r.data)
    } catch (e) {
      toast.error(extractErr(e, 'Error al exportar'))
    }
  }

  const quickStatus = (caseItem: UATCase, newStatus: UATStatus) => {
    updateCase({ id: caseItem.id, data: { ...caseItem, status: newStatus } })
  }

  return (
    <PageShell>
      <PageHeader
        title={t('uat.title')}
        subtitle={t('uat.subtitle')}
        icon={<ClipboardCheck size={18} />}
        actions={
          selectedProject ? (
            <div style={{ display: 'flex', gap: 8 }}>
              <Button variant="secondary" onClick={handleExport}>📤 Exportar para cliente</Button>
              <Button onClick={() => setShowCreate(true)}>＋ Nuevo caso</Button>
            </div>
          ) : null
        }
        showListExport={Boolean(selectedProject && cases.length)}
        exportTargetSelector='[data-export-table="uat-list"]'
        exportFilePrefix='uat'
      />

      {/* Selector de proyecto */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap', alignItems: 'center' }}>
        <select
          value={selectedProject}
          onChange={e => { setSelectedProject(e.target.value); setStatusFilter('') }}
          style={{ ...fs, width: 280 }}
        >
          <option value="">— Selecciona un proyecto —</option>
          {projects.map(p => <option key={p.id} value={String(p.id)}>{p.name}</option>)}
        </select>

        {selectedProject && (
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ ...fs, width: 180 }}>
            <option value="">Todos los estados</option>
            {Object.entries(STATUS_META).map(([v, m]) => (
              <option key={v} value={v}>{m.icon} {m.label}</option>
            ))}
          </select>
        )}
      </div>

      {/* KPI row */}
      {selectedProject && stats.total > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10, marginBottom: 20 }}>
          {[
            { label: 'Total', value: stats.total, color: 'var(--accent)' },
            { label: 'Pendientes', value: stats.pending, color: 'var(--text-2)' },
            { label: 'Pasados', value: stats.passed, color: 'var(--success)' },
            { label: 'Fallidos', value: stats.failed, color: 'var(--danger)' },
            { label: 'Bloqueados', value: stats.blocked, color: 'var(--warning)' },
          ].map(k => (
            <div key={k.label} style={{
              background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10,
              padding: '12px 16px', textAlign: 'center',
            }}>
              <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, color: k.color, fontFamily: 'var(--font-mono)' }}>
                {k.value}
              </div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 3 }}>{k.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Cases list */}
      {!selectedProject ? (
        <EmptyState
          icon={<ClipboardCheck size={40} />}
          title="Selecciona un proyecto"
          description="Selecciona un proyecto para ver y gestionar casos UAT."
        />
      ) : isLoading ? (
        <Spinner />
      ) : cases.length === 0 ? (
        <EmptyState
          icon={<ClipboardCheck size={40} />}
          title="Sin casos UAT"
          description="Crea el primer caso UAT para este proyecto."
          action={<Button onClick={() => setShowCreate(true)} style={{ marginTop: 12 }}>＋ Crear primer caso UAT</Button>}
        />
      ) : (
        <div data-export-table="uat-list" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {cases.map(c => {
            const st = STATUS_META[c.status] || STATUS_META.pending
            const pr = PRIORITY_META[c.priority] || PRIORITY_META.medium
            return (
              <div key={c.id} style={{
                background: 'var(--surface-2)', border: `1px solid ${c.status === 'failed' ? 'rgba(248,113,113,0.3)' : c.status === 'passed' ? 'rgba(74,222,128,0.2)' : 'var(--surface-4)'}`,
                borderRadius: 10, padding: '14px 18px',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{ fontSize: "var(--text-lg)" }}>{st.icon}</span>
                      <span style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)' }}>{c.title}</span>
                      <span style={{
                        fontSize: "var(--text-2xs)", fontWeight: 700, color: pr.color, background: pr.color + '20',
                        borderRadius: 20, padding: '1px 7px', border: `1px solid ${pr.color}30`,
                      }}>{pr.label}</span>
                      {c.task_title && (
                        <span style={{ fontSize: "var(--text-xs)", color: 'var(--accent)', background: 'var(--accent-muted)', borderRadius: 20, padding: '1px 8px' }}>
                          📋 {c.task_title}
                        </span>
                      )}
                    </div>
                    {c.expected_result && (
                      <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 4, paddingLeft: 24 }}>
                        <span style={{ color: 'var(--text-3)' }}>Esperado: </span>{c.expected_result}
                      </div>
                    )}
                    {c.actual_result && (
                      <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 2, paddingLeft: 24 }}>
                        <span style={{ color: 'var(--text-3)' }}>Resultado: </span>{c.actual_result}
                      </div>
                    )}
                  </div>

                  <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexShrink: 0 }}>
                    {/* Quick status buttons */}
                    {c.status !== 'passed' && (
                      <button onClick={() => quickStatus(c, 'passed')}
                        style={{ padding: '3px 8px', borderRadius: 6, border: '1px solid rgba(74,222,128,0.3)', background: 'transparent', color: 'var(--success)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                        ✅ Pasar
                      </button>
                    )}
                    {c.status !== 'failed' && (
                      <button onClick={() => quickStatus(c, 'failed')}
                        style={{ padding: '3px 8px', borderRadius: 6, border: '1px solid rgba(248,113,113,0.3)', background: 'transparent', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                        ❌ Fallar
                      </button>
                    )}
                    <button onClick={() => setEditCase(c)}
                      style={{ padding: '3px 8px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏</button>
                    <button onClick={() => setDeleteTarget(c)}
                      style={{ padding: '3px 8px', borderRadius: 6, border: '1px solid rgba(248,113,113,0.3)', background: 'transparent', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Modals */}
      {showCreate && (
        <CaseFormModal
          open
          onClose={() => setShowCreate(false)}
          onSave={createCase}
          tasks={tasksData}
        />
      )}
      {editCase && (
        <CaseFormModal
          open
          onClose={() => setEditCase(null)}
          onSave={data => updateCase({ id: editCase.id, data })}
          initial={editCase}
          tasks={tasksData}
        />
      )}
      {exportReport && (
        <ExportModal open onClose={() => setExportReport(null)} report={exportReport} />
      )}
      {/* Delete confirmation modal (no browser confirm()) */}
      {deleteTarget && (
        <Modal open onClose={() => setDeleteTarget(null)} title="Eliminar caso UAT" width={420}>
          <p style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginBottom: 20 }}>
            ¿Eliminar el caso <strong style={{ color: 'var(--text-1)' }}>&quot;{deleteTarget.title}&quot;</strong>? Esta acción no se puede deshacer.
          </p>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            <Button variant="secondary" onClick={() => setDeleteTarget(null)}>Cancelar</Button>
            <Button
              variant="danger"
              onClick={() => { deleteCase(deleteTarget.id); setDeleteTarget(null) }}
            >Eliminar</Button>
          </div>
        </Modal>
      )}
    </PageShell>
  )
}
