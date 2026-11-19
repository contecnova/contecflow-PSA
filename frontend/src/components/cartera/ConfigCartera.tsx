/**
 * Sección «Entrada a la cartera» de Configuración (`/settings/cartera`, 19-11-2026).
 *
 * Antes era la pestaña «Configuración» de /portfolio/intake. Criterios de
 * puntuación (peso, inverso, activo) y fases stage-gate (orden, puntuación
 * mínima, flujo de aprobación, activa).
 *
 * Escrituras: POST/PATCH /portfolio-intake/criteria y /gates, `require_admin_or_pm`;
 * la sección pide `cartera.gestionar` (admin, pm). Cada guardado queda en la
 * auditoría (`portfolio_criterion` / `portfolio_gate`, cartera_service).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { Button, Checkbox, Select, TablaSimple } from '../ui'
import { approvalsApi, carteraApi, type Criterio, type Fase } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useConfirm } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import '../planificador/planificador.css'
import '../../pages/CarteraIntakePage.css'

export default function ConfigCartera() {
  const t = useAppT()
  const toast = useToast()
  const { pedirTexto } = useConfirm()
  const qc = useQueryClient()
  const { data: criterios = [] } = useQuery({ queryKey: ['cartera-criterios'], queryFn: carteraApi.criterios })
  const { data: fases = [] } = useQuery({ queryKey: ['cartera-fases'], queryFn: carteraApi.fases })
  const { data: flujos = [] } = useQuery({
    queryKey: ['approval-workflows', 'portfolio_gate'],
    queryFn: () => approvalsApi.listWorkflows({ entity_type: 'portfolio_gate' }).then(r => r.data),
  })
  const onError = (e: unknown) => toast.error(extractErr(e, t('cartera.error')))
  const guardarCriterio = useMutation({
    mutationFn: ({ id, b }: { id?: string; b: Partial<Criterio> }) => id ? carteraApi.editarCriterio(id, b) : carteraApi.crearCriterio(b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['cartera-criterios'] }), onError,
  })
  const guardarFase = useMutation({
    mutationFn: ({ id, b }: { id?: string; b: Partial<Fase> }) => id ? carteraApi.editarFase(id, b) : carteraApi.crearFase(b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['cartera-fases'] }), onError,
  })
  const nuevo = async (clave: string) => (await pedirTexto({ message: t(clave), required: true }))?.trim()
  return (
    <div className="u-stack-16">
      <div className="ds-card plan-stack">
        <div className="plan-row plan-row--between">
          <h3 className="plan-card__titulo">{t('cartera.criterios')}</h3>
          <Button size="xs" icon={<Plus size={12} />} onClick={async () => { const n = await nuevo('cartera.nombre_criterio'); if (n) guardarCriterio.mutate({ b: { name: n, weight: 1 } }) }}>{t('cartera.anadir_criterio')}</Button>
        </div>
        <TablaSimple claseTabla="plan-tabla">
          <thead><tr><th>{t('cartera.col_nombre')}</th><th className="plan-num">{t('cartera.col_peso')}</th><th>{t('cartera.inverso')}</th><th>{t('cartera.activo')}</th></tr></thead>
          <tbody>
            {criterios.map(c => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td className="plan-num"><input type="number" min={0} step={0.5} className="ds-input cit-num" aria-label={t('cartera.col_peso')} defaultValue={c.weight}
                  onBlur={e => Number(e.target.value) !== c.weight && guardarCriterio.mutate({ id: c.id, b: { weight: Number(e.target.value) } })} /></td>
                <td><Checkbox aria-label={t('cartera.inverso')} checked={c.inverse} onChange={(_, e) => guardarCriterio.mutate({ id: c.id, b: { inverse: e.target.checked } })} /></td>
                <td><Checkbox aria-label={t('cartera.activo')} checked={c.is_active} onChange={(_, e) => guardarCriterio.mutate({ id: c.id, b: { is_active: e.target.checked } })} /></td>
              </tr>
            ))}
          </tbody>
        </TablaSimple>
      </div>
      <div className="ds-card plan-stack">
        <div className="plan-row plan-row--between">
          <h3 className="plan-card__titulo">{t('cartera.fases')}</h3>
          <Button size="xs" icon={<Plus size={12} />} onClick={async () => { const n = await nuevo('cartera.nombre_fase'); if (n) guardarFase.mutate({ b: { name: n, sort_order: fases.length + 1 } }) }}>{t('cartera.anadir_fase')}</Button>
        </div>
        <p className="plan-muted">{t('cartera.fases_ayuda')}</p>
        <TablaSimple claseTabla="plan-tabla">
          <thead><tr><th>{t('cartera.col_orden')}</th><th>{t('cartera.col_nombre')}</th><th className="plan-num">{t('cartera.col_minimo')}</th><th>{t('cartera.col_flujo')}</th><th>{t('cartera.activo')}</th></tr></thead>
          <tbody>
            {fases.map(g => (
              <tr key={g.id}>
                <td className="plan-num">{g.sort_order}</td>
                <td>{g.name}</td>
                <td className="plan-num"><input type="number" min={0} max={100} className="ds-input cit-num" aria-label={t('cartera.col_minimo')} defaultValue={g.min_score ?? ''}
                  onBlur={e => guardarFase.mutate({ id: g.id, b: { min_score: e.target.value === '' ? null : Number(e.target.value) } })} /></td>
                <td>
                  <Select suelto placeholder={false} className="ds-input cit-flujo" aria-label={t('cartera.col_flujo')} value={g.workflow_id ?? ''}
                    onChange={e => guardarFase.mutate({ id: g.id, b: { workflow_id: e.target.value || null } })}>
                    <option value="">{t('cartera.flujo_por_defecto')}</option>
                    {flujos.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </Select>
                </td>
                <td><Checkbox aria-label={t('cartera.activo')} checked={g.is_active} onChange={(_, e) => guardarFase.mutate({ id: g.id, b: { is_active: e.target.checked } })} /></td>
              </tr>
            ))}
          </tbody>
        </TablaSimple>
      </div>
    </div>
  )
}
