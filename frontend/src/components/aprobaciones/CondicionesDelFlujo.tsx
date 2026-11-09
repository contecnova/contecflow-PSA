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
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { approvalsApi } from '../../services/api'
import { settingsApi } from '../../services/settingsApi'
import { Button } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'

const campo: CSSProperties = { width: '100%', boxSizing: 'border-box', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 10px', color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontFamily: 'inherit' }
const etiqueta: CSSProperties = { fontSize: 'var(--text-xs)', color: 'var(--text-3)', display: 'block', marginBottom: 3 }

type Cond = { amount_gt?: number; amount_lte?: number; department?: string; category?: string; policy_exceeded?: boolean; [k: string]: unknown }

export default function CondicionesDelFlujo({ workflowId, entityType, actuales, onGuardado }: {
  workflowId: string; entityType: string; actuales: Cond; onGuardado: () => void
}) {
  const t = useAppT()
  const toast = useToast()
  const [c, setC] = useState({ amount_gt: '', amount_lte: '', department: '', category: '', policy_exceeded: '' })
  const [guardando, setGuardando] = useState(false)
  const depts = useQuery<{ id?: string; name: string }[]>({ queryKey: ['departments-select'], queryFn: () => settingsApi.getDepartments().then(r => r.data as unknown as { name: string }[]) })
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
    <section aria-label={t('aprob.condiciones')} style={{ border: '1px solid var(--surface-4)', borderRadius: 10, padding: 14, marginBottom: 18 }}>
      <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, marginBottom: 4 }}>{t('aprob.condiciones')}</div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginBottom: 10 }}>{t('aprob.condiciones_ayuda')}</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10, alignItems: 'end' }}>
        <label><span style={etiqueta}>{t('aprob.importe_mayor_que')}</span><input aria-label={t('aprob.importe_mayor_que')} type="number" min={0} step="0.01" value={c.amount_gt} onChange={set('amount_gt')} style={campo} /></label>
        <label><span style={etiqueta}>{t('aprob.importe_hasta')}</span><input aria-label={t('aprob.importe_hasta')} type="number" min={0} step="0.01" value={c.amount_lte} onChange={set('amount_lte')} style={campo} /></label>
        <label><span style={etiqueta}>{t('aprob.departamento')}</span>
          <select aria-label={t('aprob.departamento')} value={c.department} onChange={set('department')} style={campo}>
            <option value="">{t('aprob.cualquiera')}</option>
            {(depts.data ?? []).map(d => <option key={d.name} value={d.name}>{d.name}</option>)}
          </select></label>
        <label><span style={etiqueta}>{t('aprob.categoria')}</span><input aria-label={t('aprob.categoria')} value={c.category} onChange={set('category')} style={campo} placeholder={t('aprob.cualquiera')} /></label>
        {entityType === 'expense' && (
          <label><span style={etiqueta}>{t('aprob.excede_politica')}</span>
            <select aria-label={t('aprob.excede_politica')} value={c.policy_exceeded} onChange={set('policy_exceeded')} style={campo}>
              <option value="">{t('aprob.da_igual')}</option><option value="si">{t('aprob.si')}</option><option value="no">{t('aprob.no')}</option>
            </select></label>
        )}
        <Button size="sm" loading={guardando} onClick={guardar}>{t('aprob.guardar')}</Button>
      </div>
    </section>
  )
}
