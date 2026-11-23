/**
 * Barra de acciones masivas del listado de tareas (estado, prioridad y responsable).
 * Troceado de TasksPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { Button, Select } from '../../components/ui'
import { CheckSquare, Loader2 } from 'lucide-react'
import type { PersonaVisible } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'

interface BarraAccionesMasivasProps {
  cantidad: number
  estado: string
  onEstado: (v: string) => void
  prioridad: string
  onPrioridad: (v: string) => void
  responsable: string
  onResponsable: (v: string) => void
  usuarios: PersonaVisible[]
  onAplicar: () => void
  aplicando: boolean
  onCancelar: () => void
}

export function BarraAccionesMasivas({ cantidad, estado, onEstado, prioridad, onPrioridad, responsable, onResponsable, usuarios, onAplicar, aplicando, onCancelar }: BarraAccionesMasivasProps) {
  const t = useAppT()
  return (
    <div className="tsk-bulk" role="region" aria-label={t('tasks.acciones_masivas')}>
      <span className="tsk-bulk-count">
        <CheckSquare size={13} aria-hidden /> {cantidad} {t('tasks.selected')}
      </span>
      <div className="tsk-bulk-sep" aria-hidden="true" />
      <Select suelto placeholder={false} aria-label={t('tasks.bulk_status_ph')} value={estado} onChange={e => onEstado(e.target.value)}
        className="ds-input tsk-bulk-select">
        <option value="">{t('tasks.bulk_status_ph')}</option>
        <option value="todo">{t('tasks.status_todo')}</option>
        <option value="in_progress">{t('tasks.status_in_progress')}</option>
        <option value="in_review">{t('tasks.status_review')}</option>
        <option value="blocked">{t('tasks.status_blocked')}</option>
        <option value="done">{t('tasks.status_done')}</option>
      </Select>
      <Select suelto placeholder={false} aria-label={t('tasks.bulk_priority_ph')} value={prioridad} onChange={e => onPrioridad(e.target.value)}
        className="ds-input tsk-bulk-select">
        <option value="">{t('tasks.bulk_priority_ph')}</option>
        <option value="low">{t('tasks.priority_low')}</option>
        <option value="medium">{t('tasks.priority_medium')}</option>
        <option value="high">{t('tasks.priority_high')}</option>
        <option value="critical">{t('tasks.priority_critical')}</option>
      </Select>
      <Select suelto placeholder={false} aria-label={t('tasks.bulk_assignee_ph')} value={responsable} onChange={e => onResponsable(e.target.value)}
        className="ds-input tsk-bulk-select">
        <option value="">{t('tasks.bulk_assignee_ph')}</option>
        {usuarios.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
      </Select>
      <Button size="sm" onClick={onAplicar}
        disabled={aplicando || (!estado && !prioridad && !responsable)}>
        {aplicando
          ? <><Loader2 size={12} className="tsk-spin" aria-hidden /> {t('tasks.aplicando')}</>
          : t('tasks.bulk_apply')}
      </Button>
      <Button size="sm" variant="secondary"
        onClick={onCancelar}>
        {t('common.cancel')}
      </Button>
    </div>
  )
}
