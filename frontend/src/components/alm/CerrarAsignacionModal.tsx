/**
 * Cerrar una asignación (fase 1): liberar (sin más) o revocar (con motivo
 * obligatorio), y devolver un equipo con su acta de devolución (checklist,
 * estado físico y, si hace falta, a reparación).
 */
import { useEffect, useId, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Modal, GrupoDeOpciones, Select, Checkbox } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { almApi } from '../../services/api/alm'
import type { Asignacion, Condicion, FilaDeChecklist } from '../../services/api/alm'
import { EditorDeChecklist, errorAlm } from './almFases'

const CLAVES_A_REFRESCAR = ['alm-licenses', 'alm-license', 'alm-assets', 'alm-asset', 'alm-assignments', 'alm-history',
  'alm-dashboard', 'alm-acts']

export default function CerrarAsignacionModal({ asignacion, onClose }: { asignacion: Asignacion; onClose: () => void }) {
  const t = useAppT()
  const id = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const esActivo = asignacion.resource_type === 'asset' && asignacion.status === 'active'
  const [tipo, setTipo] = useState<'return' | 'released' | 'revoked'>(esActivo ? 'return' : 'released')
  const [motivo, setMotivo] = useState('')
  const [checklist, setChecklist] = useState<FilaDeChecklist[]>([])
  const [condicion, setCondicion] = useState<Condicion | ''>('')
  const [observaciones, setObservaciones] = useState('')
  const [aReparar, setAReparar] = useState(false)
  const [error, setError] = useState('')
  const cfg = useQuery({ queryKey: ['alm-config'], queryFn: almApi.config, staleTime: 5 * 60_000, enabled: esActivo })
  useEffect(() => { if (cfg.data) setChecklist(cfg.data.checklist.map(item => ({ item, ok: false, note: '' }))) }, [cfg.data])

  const { mutate, isPending } = useMutation({
    mutationFn: () => tipo === 'return'
      ? almApi.devolver(asignacion.id, { reason: motivo || undefined, checklist, condition: condicion || undefined,
        observations: observaciones || undefined, to_repair: aReparar })
      : almApi.cerrar(asignacion.id, tipo, motivo || undefined),
    onSuccess: () => {
      toast.success(t(tipo === 'return' ? 'alm.return_done' : 'alm.end_done'))
      CLAVES_A_REFRESCAR.forEach(k => qc.invalidateQueries({ queryKey: [k] }))
      onClose()
    },
    onError: e => setError(errorAlm(t, e)),
  })

  const enviar = () => {
    if (tipo === 'revoked' && !motivo.trim()) return setError(t('alm.err_motivo_obligatorio'))
    setError('')
    mutate()
  }
  const opciones = esActivo ? (['return', 'revoked'] as const) : (['released', 'revoked'] as const)
  const pendiente = asignacion.status === 'pending'

  return (
    <Modal open onClose={onClose} width={620}
      title={pendiente ? t('alm.cancel_request_title') : t('alm.end_title', { name: asignacion.holder_name ?? '' })}
      subtitle={asignacion.resource_name ?? undefined}>
      <div className="u-stack-14">
        {!pendiente && (
          <GrupoDeOpciones forma="fila" className="almf-titular__tipos" aria-label={t('alm.end_kind')}
            valor={tipo} onChange={v => setTipo(v as typeof tipo)}
            opciones={opciones.map(k => ({ valor: k, titulo: t(`alm.end_${k}`) }))} />
        )}
        <p className="alm-hint">{pendiente ? t('alm.cancel_request_hint') : t(`alm.end_${tipo}_hint`)}</p>
        <div>
          <label className="alm-label" htmlFor={`${id}-motivo`}>{t('alm.reason')}{tipo === 'revoked' ? ' *' : ''}</label>
          <textarea id={`${id}-motivo`} rows={2} className="alm-input" value={motivo} onChange={e => setMotivo(e.target.value)} />
        </div>
        {tipo === 'return' && !pendiente && (
          <div className="almf-bloque">
            <h4 className="almf-bloque__titulo">{t('alm.return_act')}</h4>
            {cfg.data?.acts_enabled && <EditorDeChecklist t={t} filas={checklist} onChange={setChecklist} />}
            <div className="almf-rejilla-2">
              <div>
                <label className="alm-label" htmlFor={`${id}-cond`}>{t('alm.assets_label_condition')}</label>
                <Select suelto placeholder={false} id={`${id}-cond`} className="alm-input" value={condicion} onChange={e => setCondicion(e.target.value as Condicion | '')}>
                  <option value="">{t('alm.condition_keep')}</option>
                  {(['new', 'good', 'fair', 'poor'] as const).map(c => <option key={c} value={c}>{t(`alm.assets_condition_${c}`)}</option>)}
                </Select>
              </div>
              <div>
                <label className="alm-label" htmlFor={`${id}-obs`}>{t('alm.observations')}</label>
                <input id={`${id}-obs`} className="alm-input" value={observaciones} onChange={e => setObservaciones(e.target.value)} />
              </div>
            </div>
            <label className="alm-check-row">
              <Checkbox checked={aReparar} onChange={(_, e) => setAReparar(e.target.checked)} />
              <span className="alm-check-label">{t('alm.return_to_repair')}</span>
            </label>
          </div>
        )}
        {error && <p className="u-field-error" role="alert">{error}</p>}
      </div>
      <div className="almf-acciones-modal">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant={tipo === 'revoked' ? 'danger' : 'primary'} onClick={enviar} loading={isPending} disabled={isPending}>
          {pendiente ? t('alm.cancel_request') : t(`alm.end_${tipo}_confirm`)}
        </Button>
      </div>
    </Modal>
  )
}
