import { type CSSProperties, useState, useEffect, useRef } from 'react'
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
import { IconButton, Pulsable, Select, Input, useCambiosSinGuardar, confirmarDescarte } from '../ui'
import './QuickCreateMenu.css'
import { useAuth } from '../../context/AuthContext'
import { puedeAbrir } from '../../permisos/navegacion'

// Auditoría 22-11-2026 (A3 del 04): textos traducidos (`quickcreatemenu.accion_<id>`) y
// cada acción filtrada por la capacidad de su ruta (`ruta`): nadie ve «Nueva factura»
// para acabar en /403.
const ACTIONS = [
  { id: 'task',     icon: CheckSquare,  color: 'var(--accent)',  inline: true, ruta: '/tasks' },
  { id: 'hours',    icon: Clock,        color: 'var(--success)', path: '/imputar', ruta: '/imputar' },
  { id: 'ticket',   icon: Ticket,       color: 'var(--warning)', path: '/service-desk?create=1', ruta: '/service-desk' },
  { id: 'invoice',  icon: FileText,     color: 'var(--accent)',  path: '/invoices?create=1', ruta: '/invoices' },
  { id: 'client',   icon: Building2,    color: 'var(--purple)',  path: '/clients?create=1', ruta: '/clients' },
  { id: 'contract', icon: ScrollText,   color: 'var(--purple)',  path: '/contracts?create=1', ruta: '/contracts' },
  { id: 'risk',     icon: AlertTriangle,color: 'var(--danger)',  path: '/risks?create=1', ruta: '/risks' },
  { id: 'expense',  icon: Receipt,      color: 'var(--orange)',  path: '/expenses?create=1', ruta: '/expenses' },
  { id: 'project',  icon: FolderOpen,   color: 'var(--accent)',  path: '/projects?create=1', ruta: '/projects' },
  // I27: quick action — auto-planificar tareas sin fecha
  { id: 'smart_schedule', icon: Sparkles, color: 'var(--purple)', inline: true, ruta: '/tasks' },
]

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
      <Input aria-label={t('quickcreatemenu.titulo_de_la_tarea')} ref={inputRef} value={title} onChange={e => setTitle(e.target.value)} placeholder={t('quickcreatemenu.titulo_de_la_tarea')} onKeyDown={e => { if (e.key === 'Enter' && title.trim()) create() }} onFocus={e => e.target.style.borderColor = 'var(--accent)'} onBlur={e => e.target.style.borderColor = 'var(--surface-4)'} inputClassName="qucrme-box-2" />
      {projects.length > 0 && (
        <Select suelto className={`qucrme-box-5 ${projectId ? 'quick-create-menu-m1' : 'quick-create-menu-m2'}`}
          value={projectId}
          onChange={e => setProjectId(e.target.value)}
          placeholder={t('quickcreatemenu.sin_proyecto')}
        >
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>
      )}
      <div className="u-actions-8">
        <Pulsable onClick={onClose} className="qucrme-box-3">
          {t('common.cancel')}
        </Pulsable>
        <Pulsable className={`qucrme-box-6 ${title.trim() ? 'quick-create-menu-m3' : 'quick-create-menu-m4'}`}
          onClick={() => title.trim() && create()}
          disabled={!title.trim() || isPending}
        >
          {isPending ? t('quickcreatemenu.creando') : t('quickcreatemenu.crear_tarea')}
        </Pulsable>
      </div>
    </div>
  )
}

export default function QuickCreateMenu({ onClose }: { onClose: () => void }) {
  const { t } = useAppLang()
  const navigate = useNavigate()
  const { puede, canOpen } = useAuth()
  const acciones = ACTIONS.filter(a => puedeAbrir(a.ruta, puede, true) && canOpen(a.ruta))
  const [activeAction, setActiveAction] = useState<string | null>(null)
  const panelRef = useRef<HTMLDivElement | null>(null)
  // Cambios sin guardar (kit, 23-11-2026): la tarea rápida es un formulario;
  // Esc y el clic fuera preguntan si hay algo escrito (aquí o en el modal de
  // planificación que se abre dentro).
  useCambiosSinGuardar<HTMLDivElement>(true, { ref: panelRef })
  const pedirCierre = () => { void confirmarDescarte().then(ok => { if (ok) onClose() }) }

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') void confirmarDescarte().then(ok => { if (ok) onClose() })
    }
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
      <div role="presentation" onMouseDown={pedirCierre}
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
              <Pulsable onClick={pedirCierre} aria-label={t('common.close')} className="qucrme-row-2">
                <X size={13} />
              </Pulsable>
            </div>
            <div role="menu" aria-label={t('quickcreatemenu.crear_nuevo')} className="qucrme-stack-2">
              {acciones.map(({ id, icon: Icon, color }) => { const label = t(`quickcreatemenu.accion_${id}`); return (
                <IconButton key={id} ariaLabel={label} title={label} role="menuitem" onClick={() => handleAction(id)} className="qucrme-row-3"
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <div className="qucrme-row-4 quickcre-sx2 quick-create-menu-e5" style={{ '--quick-create-menu-background': alpha(color, '15'), '--quick-create-menu-border': `1px solid ${alpha(color, '30')}` } as CSSProperties}>
                    <Icon size={15} color={color} />
                  </div>
                  <span className="u-text1-base-600">{label}</span>
                </IconButton>
              ) })}
            </div>
          </>
        )}
      </div>
    </>
  )
}
