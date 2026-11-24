/**
 * Casos dudosos de la asignación por IA (23-11-2026).
 *
 * Las sugerencias que aún no tienen veredicto, ordenadas por lo que más enseña
 * al motor que un experto las revise (el `ActiveLearningPrioritizer` del
 * sistema de origen: incertidumbre 40, novedad 30, urgencia 20, carga 10).
 * Confirmar la persona o corregirla alimenta la caché de experto y la
 * precisión; corregir además reasigna el ticket o la tarea.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ListOrdered, UserCog } from 'lucide-react'
import { semanticApi, tasksApi, ticketsApi } from '../../services/api'
import type { CasoDudoso } from '../../services/api/tipos-analitica'
import { Button, EmptyState, Spinner, UserSelect } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'

export default function ColaDeRevision() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [corrigiendo, setCorrigiendo] = useState<string | null>(null)
  const [persona, setPersona] = useState('')
  const cola = useQuery({ queryKey: ['semantic', 'review-queue'], queryFn: () => semanticApi.reviewQueue(50).then(r => r.data) })
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['semantic'] }); qc.invalidateQueries({ queryKey: ['sem-stats'] }) }
  const decidir = useMutation({
    mutationFn: async ({ c, uid }: { c: CasoDudoso; uid: string }) => {
      const confirmar = uid === c.suggested_user_id
      await semanticApi.feedback({ item_type: c.item_type, item_id: c.item_id, correct_user_id: uid,
        original_engine_mode: c.engine_mode, confirmed: confirmar })
      if (!confirmar) {
        if (c.item_type === 'task') await tasksApi.update(c.item_id, { assignee_id: uid })
        else await ticketsApi.update(c.item_id, { assigned_to_user_id: uid })
      }
    },
    onSuccess: () => { setCorrigiendo(null); setPersona(''); toast.success(t('bucle_ia.corregida')); refrescar() },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  if (cola.isLoading) return <Spinner />
  const casos = cola.data ?? []
  if (!casos.length) return <EmptyState icon={<ListOrdered size={28} />} title={t('bucle_ia.cola_vacia')} description={t('bucle_ia.cola_ayuda')} />
  return (
    <div className="u-stack-12">
      <p className="u-text2-xs">{t('bucle_ia.cola_ayuda')}</p>
      <div className="sem-card sem-card--clip">
        <div className="u-scroll-x">
          <div className="sem-table" role="table" aria-label={t('bucle_ia.cola')}>
            <div className="sem-row sem-row--head" role="row">
              <span role="columnheader">{t('bucle_ia.col_elemento')}</span>
              <span role="columnheader">{t('bucle_ia.col_sugerida')}</span>
              <span role="columnheader">{t('bucle_ia.col_confianza')}</span>
              <span role="columnheader">{t('bucle_ia.col_valor')}</span>
              <span role="columnheader">{t('bucle_ia.col_prioridad')}</span>
              <span role="columnheader">{t('semanticengine.accion')}</span>
            </div>
            {casos.map(c => (
              <div key={c.assignment_id} className="sem-row" role="row">
                <div className="u-min0" role="cell">
                  <div className="u-600">{c.item_title}</div>
                  <div className="u-text3-xs">{t(c.item_type === 'task' ? 'bucle_ia.tipo_tarea' : 'bucle_ia.tipo_ticket')}{c.needs_review ? ` · ${t('bucle_ia.necesita_revision')}` : ''}</div>
                </div>
                <span role="cell">{c.suggested_user_name || '—'}</span>
                <span role="cell">{Math.round((c.confidence || 0) * 100)} %</span>
                <span role="cell" title={Object.entries(c.priority_breakdown || {}).map(([k, v]) => `${k}: ${v}`).join(' · ')}>{c.priority_score}</span>
                <span role="cell">{c.priority}</span>
                <span role="cell" className="u-row-8">
                  {corrigiendo === c.assignment_id ? (
                    <>
                      <UserSelect value={persona} onChange={(uid: string) => setPersona(uid)} placeholder={t('bucle_ia.persona_correcta')} />
                      <Button size="sm" disabled={!persona} loading={decidir.isPending} onClick={() => decidir.mutate({ c, uid: persona })}>{t('bucle_ia.guardar')}</Button>
                      <Button size="sm" variant="ghost" onClick={() => setCorrigiendo(null)}>{t('common.cancel')}</Button>
                    </>
                  ) : (
                    <>
                      {c.suggested_user_id && (
                        <Button size="sm" variant="secondary" icon={<Check size={13} />} loading={decidir.isPending && decidir.variables?.c.assignment_id === c.assignment_id}
                          onClick={() => decidir.mutate({ c, uid: c.suggested_user_id as string })}>{t('bucle_ia.confirmar')}</Button>
                      )}
                      <Button size="sm" variant="ghost" icon={<UserCog size={13} />} onClick={() => { setCorrigiendo(c.assignment_id); setPersona('') }}>{t('bucle_ia.corregir')}</Button>
                    </>
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
