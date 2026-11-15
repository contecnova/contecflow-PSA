import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { tasksApi, projectsApi } from '../../services/api'
import { X, CheckSquare, Clock, Ticket, FileText, Building2, ScrollText, AlertTriangle, Receipt, FolderOpen, Sparkles } from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import SmartScheduleModal from '../SmartScheduleModal'
import { useAppLang } from '../../i18n/AppLangContext'
import { alpha } from '../../constants/theme'
import { STALE_DEFAULT_MS } from '../../constants/timings'
import { SELECTOR_LIST_SIZE } from '../../constants/pagination'
import './QuickCreateMenu.css'

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
    queryFn: () => projectsApi.list({ page_size: SELECTOR_LIST_SIZE, status: 'active' }).then(r => {
      return r.data ?? []
    }),
    staleTime: STALE_DEFAULT_MS,
  })

  const { mutate: create, isPending } = useMutation({
    // `project_id` es obligatorio en el payload: una tarea sin proyecto no
    // existe en este modelo y el backend la rechaza. El boton ya esta
    // deshabilitado sin proyecto; esto lo dice tambien en el tipo.
    mutationFn: () => tasksApi.create({ title, project_id: projectId!, status: 'todo', priority: 'medium' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['kanban-board'] })
      toast.success(t('layoutshell.tarea_creada'))
      onClose()
    },
    onError: () => toast.error(t('layoutshell.error_crear_tarea')),
  })

  return (
    <div className="qucrme-stack-1">
      <div className="qucrme-box-1">{t('quickcreatemenu.nueva_tarea')}</div>
      <input aria-label={t('quickcreatemenu.titulo_de_la_tarea')}
        ref={inputRef}
        value={title}
        onChange={e => setTitle(e.target.value)}
        placeholder={t('quickcreatemenu.titulo_de_la_tarea')}
        onKeyDown={e => { if (e.key === 'Enter' && title.trim()) create() }}
        className="qucrme-box-2"
        onFocus={e => e.target.style.borderColor = 'var(--accent)'}
        onBlur={e => e.target.style.borderColor = 'var(--surface-4)'}
      />
      {projects.length > 0 && (
        <select className="qucrme-box-5"
          value={projectId}
          onChange={e => setProjectId(e.target.value)}
          style={{ color: projectId ? 'var(--text-1)' : 'var(--text-3)' }}
        >
          <option value="">{t('quickcreatemenu.sin_proyecto')}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      )}
      <div className="u-actions-8">
        <button type="button" onClick={onClose} className="qucrme-box-3">
          {t('common.cancel')}
        </button>
        <button className="qucrme-box-6"
          onClick={() => title.trim() && create()}
          disabled={!title.trim() || isPending}
          style={{ cursor: title.trim() ? 'pointer' : 'not-allowed', opacity: title.trim() ? 1 : 0.5 }}
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
        className="qucrme-box-4" />
      <div ref={panelRef}
        role="region"
        aria-label={t('quickcreatemenu.crear_nuevo')} className="quickcre-sx1"
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
            <div className="qucrme-row-1">
              <span>{t('quickcreatemenu.crear_nuevo')}</span>
              <button type="button" onClick={onClose} aria-label={t('common.close')} className="qucrme-row-2">
                <X size={13} />
              </button>
            </div>
            <div role="menu" aria-label={t('quickcreatemenu.crear_nuevo')} className="qucrme-stack-2">
              {ACTIONS.map(({ id, icon: Icon, label, color }) => (
                <button key={id} role="menuitem" onClick={() => handleAction(id)} className="qucrme-row-3"
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <div className="qucrme-row-4 quickcre-sx2" style={{ background: alpha(color, '15'), border: `1px solid ${alpha(color, '30')}` }}>
                    <Icon size={15} color={color} />
                  </div>
                  <span className="u-text1-base-600">{label}</span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </>
  )
}
