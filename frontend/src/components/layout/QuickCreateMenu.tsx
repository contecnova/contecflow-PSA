import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { tasksApi, projectsApi } from '../../services/api'
import { X, CheckSquare, Clock, Ticket, FileText, Building2, ScrollText, AlertTriangle, Receipt, FolderOpen, Sparkles } from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import SmartScheduleModal from '../SmartScheduleModal'
import { useAppLang } from '../../i18n/AppLangContext'

const ACTIONS = [
  { id: 'task',     icon: CheckSquare,  label: 'Nueva tarea',     color: 'var(--accent)',  inline: true },
  { id: 'hours',    icon: Clock,        label: 'Imputar horas',   color: 'var(--success)', path: '/imputar' },
  { id: 'ticket',   icon: Ticket,       label: 'Nuevo ticket',    color: 'var(--warning)', path: '/service-desk?create=1' },
  { id: 'invoice',  icon: FileText,     label: 'Nueva factura',   color: 'var(--accent)',  path: '/invoices?create=1' },
  { id: 'client',   icon: Building2,    label: 'Nuevo cliente',   color: 'var(--purple)',  path: '/clients?create=1' },
  { id: 'contract', icon: ScrollText,   label: 'Nuevo contrato',  color: 'var(--purple)',  path: '/contracts?create=1' },
  { id: 'risk',     icon: AlertTriangle,label: 'Nuevo riesgo',    color: 'var(--danger)',  path: '/risks?create=1' },
  { id: 'expense',  icon: Receipt,      label: 'Reportar gasto',  color: 'var(--orange)',  path: '/expenses?create=1' },
  { id: 'project',  icon: FolderOpen,   label: 'Nuevo proyecto',  color: 'var(--accent)',  path: '/projects?create=1' },
  // I27: quick action — auto-planificar tareas sin fecha
  { id: 'smart_schedule', icon: Sparkles, label: 'Auto-planificar tareas IA', color: 'var(--purple)', inline: true },
]

// TODO type: project payload — needs shared type from projectsApi
interface ProjectOption {
  id: string | number
  name: string
}

function CreateTaskForm({ onClose }: { onClose: () => void }) {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [title, setTitle] = useState<string>('')
  const [projectId, setProjectId] = useState<string>('')
  const inputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  const { data: projects = [] } = useQuery<ProjectOption[]>({
    queryKey: ['projects-quick'],
    queryFn: () => projectsApi.list({ page_size: 200, status: 'active' }).then(r => {
      return r.data ?? []
    }),
    staleTime: 60_000,
  })

  const { mutate: create, isPending } = useMutation({
    // `project_id` es obligatorio en el payload: una tarea sin proyecto no
    // existe en este modelo y el backend la rechaza. El boton ya esta
    // deshabilitado sin proyecto; esto lo dice tambien en el tipo.
    mutationFn: () => tasksApi.create({ title, project_id: projectId!, status: 'todo', priority: 'medium' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['kanban-board'] })
      toast.success('Tarea creada')
      onClose()
    },
    onError: () => toast.error('Error al crear tarea'),
  })

  return (
    <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 2 }}>{t('quickcreatemenu.nueva_tarea')}</div>
      <input
        ref={inputRef}
        value={title}
        onChange={e => setTitle(e.target.value)}
        placeholder={t('quickcreatemenu.titulo_de_la_tarea')}
        onKeyDown={e => { if (e.key === 'Enter' && title.trim()) create() }}
        style={{
          width: '100%', boxSizing: 'border-box',
          background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
          borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)',
          fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit',
        }}
        onFocus={e => e.target.style.borderColor = 'var(--accent)'}
        onBlur={e => e.target.style.borderColor = 'var(--surface-4)'}
      />
      {projects.length > 0 && (
        <select
          value={projectId}
          onChange={e => setProjectId(e.target.value)}
          style={{
            width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
            borderRadius: 8, padding: '8px 12px', color: projectId ? 'var(--text-1)' : 'var(--text-3)',
            fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', cursor: 'pointer',
          }}
        >
          <option value="">{t('quickcreatemenu.sin_proyecto')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      )}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={onClose} style={{
          padding: '8px 16px', borderRadius: 8,
          background: 'transparent', border: '1px solid var(--surface-4)',
          color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit',
        }}>
          Cancelar
        </button>
        <button
          onClick={() => title.trim() && create()}
          disabled={!title.trim() || isPending}
          style={{
            padding: '8px 18px', borderRadius: 8,
            background: 'var(--accent)', border: 'none',
            color: '#fff', cursor: title.trim() ? 'pointer' : 'not-allowed',
            fontSize: "var(--text-sm)", fontWeight: 700, fontFamily: 'inherit',
            opacity: title.trim() ? 1 : 0.5,
          }}
        >
          {isPending ? 'Creando…' : 'Crear tarea'}
        </button>
      </div>
    </div>
  )
}

export default function QuickCreateMenu({ onClose }: { onClose: () => void }) {
  const { t } = useAppLang()
  const navigate = useNavigate()
  const [activeAction, setActiveAction] = useState<string | null>(null)
  const panelRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  function handleAction(id: string) {
    const action = ACTIONS.find(a => a.id === id)
    if (!action) return
    if (action.inline) { setActiveAction(id); return }
    if (action.path) { navigate(action.path); onClose() }
  }

  return (
    <>
      <div role="presentation" onMouseDown={onClose}
        style={{ position: 'fixed', inset: 0, zIndex: 500 }} />
      <div ref={panelRef}
        role="region"
        aria-label={t('quickcreatemenu.crear_nuevo')}
        style={{
          position: 'fixed', top: 52, right: 16, zIndex: 501,
          width: 280, background: 'var(--surface-1)',
          border: '1px solid var(--surface-4)', borderRadius: 12,
          boxShadow: '0 12px 40px rgba(0,0,0,0.4)',
          overflow: 'hidden',
        }}
      >
        {activeAction === 'task' ? (
          <CreateTaskForm onClose={onClose} />
        ) : activeAction === 'smart_schedule' ? (
          /* I27: quick action delega al modal compartido. Sin projectId →
             el backend planifica todas las tareas sin fecha visibles. */
          <SmartScheduleModal
            open={true}
            onClose={onClose}
            projectId={null}
            projectName={undefined}
          />
        ) : (
          <>
            <div style={{
              padding: '12px 16px 8px',
              fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)',
              textTransform: 'uppercase', letterSpacing: '.07em',
              borderBottom: '1px solid var(--surface-4)',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            }}>
              <span>{t('quickcreatemenu.crear_nuevo')}</span>
              <button onClick={onClose} aria-label="Cerrar" style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', display: 'flex', padding: 2 }}>
                <X size={13} />
              </button>
            </div>
            <div role="menu" aria-label={t('quickcreatemenu.crear_nuevo')} style={{ padding: '6px 8px 8px', display: 'flex', flexDirection: 'column', gap: 2 }}>
              {ACTIONS.map(({ id, icon: Icon, label, color }) => (
                <button key={id} role="menuitem" onClick={() => handleAction(id)} style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '10px 12px', borderRadius: 8,
                  background: 'transparent', border: 'none',
                  cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit',
                  width: '100%',
                }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <div style={{
                    width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                    background: `${color}15`, border: `1px solid ${color}30`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Icon size={15} color={color} />
                  </div>
                  <span style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)' }}>{label}</span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </>
  )
}
