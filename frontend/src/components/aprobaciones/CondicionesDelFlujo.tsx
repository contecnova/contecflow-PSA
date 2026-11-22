/**
 * Condiciones de un flujo de aprobación (revisión 2026-11).
 *
 * El motor elige el flujo más específico cuyas condiciones encajan
 * (`approval_engine._base.elegir_flujo`), pero ninguna pantalla las fijaba
 * salvo la categoría de documentos: «gastos de más de 1.000 € van a dirección»
 * sólo se podía escribir en la base. Aquí se ponen: importe, departamento,
 * categoría y, en gastos, «excede una política».
 */
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { approvalsApi } from '../../services/api'
import { settingsApi } from '../../services/settingsApi'
import { Button, Select, Input } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import './aprobaciones.css'


type Cond = { amount_gt?: number; amount_lte?: number; department?: string; category?: string; policy_exceeded?: boolean; [k: string]: unknown }

export default function CondicionesDelFlujo({ workflowId, entityType, actuales, onGuardado }: {
  workflowId: string; entityType: string; actuales: Cond; onGuardado: () => void
}) {
  const t = useAppT()
  const toast = useToast()
  const [c, setC] = useState({ amount_gt: '', amount_lte: '', department: '', category: '', policy_exceeded: '' })
  const [guardando, setGuardando] = useState(false)
  const depts = useQuery({ queryKey: ['departments-select'], queryFn: () => settingsApi.getDepartments().then(r => r.data) })
  useEffect(() => {
    setC({
      amount_gt: actuales.amount_gt != null ? String(actuales.amount_gt) : '',
      amount_lte: actuales.amount_lte != null ? String(actuales.amount_lte) : '',
      department: actuales.department ?? '', category: actuales.category ?? '',
      policy_exceeded: actuales.policy_exceeded == null ? '' : actuales.policy_exceeded ? 'si' : 'no',
    })
  }, [actuales])
  const guardar = async () => {
    const nuevo: Cond = { ...actuales }
    for (const k of ['amount_gt', 'amount_lte', 'department', 'category', 'policy_exceeded']) delete nuevo[k]
    if (c.amount_gt !== '') nuevo.amount_gt = Number(c.amount_gt)
    if (c.amount_lte !== '') nuevo.amount_lte = Number(c.amount_lte)
    if (c.department) nuevo.department = c.department
    if (c.category) nuevo.category = c.category
    if (c.policy_exceeded) nuevo.policy_exceeded = c.policy_exceeded === 'si'
    setGuardando(true)
    try {
      await approvalsApi.updateWorkflow(workflowId, { trigger_conditions: JSON.stringify(nuevo) })
      toast.success(t('aprob.condiciones_guardadas')); onGuardado()
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setGuardando(false) }
  }
  const set = (k: keyof typeof c) => (e: { target: { value: string } }) => setC(v => ({ ...v, [k]: e.target.value }))
  return (
    <section aria-label={t('aprob.condiciones')} className="apr-condiciones">
      <div className="apr-condiciones__titulo">{t('aprob.condiciones')}</div>
      <div className="apr-condiciones__ayuda">{t('aprob.condiciones_ayuda')}</div>
      <div className="apr-condiciones__rejilla">
        <label><span className="apr-etiqueta">{t('aprob.importe_mayor_que')}</span><Input aria-label={t('aprob.importe_mayor_que')} type="number" min={0} step="0.01" value={c.amount_gt} onChange={set('amount_gt')} inputClassName="apr-campo" /></label>
        <label><span className="apr-etiqueta">{t('aprob.importe_hasta')}</span><Input aria-label={t('aprob.importe_hasta')} type="number" min={0} step="0.01" value={c.amount_lte} onChange={set('amount_lte')} inputClassName="apr-campo" /></label>
        <label><span className="apr-etiqueta">{t('aprob.departamento')}</span>
          <Select suelto placeholder={false} aria-label={t('aprob.departamento')} value={c.department} onChange={set('department')} className="apr-campo">
            <option value="">{t('aprob.cualquiera')}</option>
            {(depts.data ?? []).map(d => <option key={d.name} value={d.name}>{d.name}</option>)}
          </Select></label>
        <label><span className="apr-etiqueta">{t('aprob.categoria')}</span><Input aria-label={t('aprob.categoria')} value={c.category} onChange={set('category')} placeholder={t('aprob.cualquiera')} inputClassName="apr-campo" /></label>
        {entityType === 'expense' && (
          <label><span className="apr-etiqueta">{t('aprob.excede_politica')}</span>
            <Select suelto placeholder={false} aria-label={t('aprob.excede_politica')} value={c.policy_exceeded} onChange={set('policy_exceeded')} className="apr-campo">
              <option value="">{t('aprob.da_igual')}</option><option value="si">{t('aprob.si')}</option><option value="no">{t('aprob.no')}</option>
            </Select></label>
        )}
        <Button size="sm" loading={guardando} onClick={guardar}>{t('aprob.guardar')}</Button>
      </div>
    </section>
  )
}
