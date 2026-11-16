/**
 * PlantillasRca — plantillas de análisis de causa raíz de la empresa
 * (`/sd/rca/templates`, mejoras de mercado 16-11-2026). Las de serie se ven y
 * no se tocan; las propias se crean con sus pasos y se desactivan.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, Modal, Spinner, StatusBadge } from '../ui'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { problemasApi } from '../../services/api/serviceDeskMercado'
import './sdMercado.css'

interface PasoRca { label: string; prompt: string }

export default function PlantillasRca({ onClose }: { onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const err = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const { data = [], isLoading } = useQuery({ queryKey: ['sd-rca-templates'], queryFn: problemasApi.plantillas })
  const [nombre, setNombre] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [pasos, setPasos] = useState<PasoRca[]>([{ label: '', prompt: '' }])
  const refrescar = () => qc.invalidateQueries({ queryKey: ['sd-rca-templates'] })
  const crear = useMutation({
    mutationFn: () => problemasApi.crearPlantilla({
      name: nombre.trim(), template_type: 'custom', description: descripcion.trim() || undefined,
      steps_json: JSON.stringify(pasos.filter(p => p.label.trim()).map((p, i) => ({ step: i + 1, label: p.label.trim(), prompt: p.prompt.trim() }))),
    }),
    onSuccess: () => { setNombre(''); setDescripcion(''); setPasos([{ label: '', prompt: '' }]); refrescar(); toast.success(t('sd_mercado.guardado')) },
    onError: err,
  })
  const borrar = useMutation({ mutationFn: problemasApi.borrarPlantilla, onSuccess: refrescar, onError: err })
  const validos = pasos.filter(p => p.label.trim()).length > 0 && nombre.trim().length >= 3

  return (
    <Modal open size="lg" onClose={onClose} title={t('sd_mercado.plantillas_rca')}>
      <div className="u-stack-16">
        {isLoading ? <Spinner /> : (
          <ul className="sdm-list">
            {data.map(p => (
              <li key={p.id} className="sdm-list__item">
                <div className="u-flex1-min0">
                  <div className="u-text1-sm-600">{p.is_system ? etiquetaCodigo(t, 'sd_mercado.rca_tipo', p.template_type, p.name) : p.name}</div>
                  <div className="u-wrap-6 u-text3-xs">
                    <StatusBadge caps={false} kind={p.is_system ? 'neutral' : 'accent'}>{t(p.is_system ? 'sd_mercado.de_serie' : 'sd_mercado.propio')}</StatusBadge>
                    {!p.is_active && <StatusBadge caps={false}>{t('sd_mercado.apagado')}</StatusBadge>}
                    <span>{t('sd_mercado.n_pasos', { n: p.total_steps })}</span>
                  </div>
                </div>
                {!p.is_system && p.is_active && (
                  <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={async () => {
                    if (await confirmar({ message: t('sd_mercado.plantilla_desactivar', { n: p.name }), danger: true })) borrar.mutate(p.uuid || p.id)
                  }}>{t('sd_mercado.desactivar')}</Button>
                )}
              </li>
            ))}
          </ul>
        )}
        <div className="ds-card sdm-card">
          <div className="sdm-card__head">{t('sd_mercado.plantilla_nueva')}</div>
          <div className="sdm-form">
            <label className="sdm-field"><span>{t('sd_mercado.nombre')}</span><input className="ds-input" value={nombre} onChange={e => setNombre(e.target.value)} /></label>
            <label className="sdm-field"><span>{t('sd_mercado.descripcion')}</span><input className="ds-input" value={descripcion} onChange={e => setDescripcion(e.target.value)} /></label>
          </div>
          <div className="sdm-steps">
            {pasos.map((p, i) => (
              <div key={i} className="sdm-step">
                <input className="ds-input" aria-label={t('sd_mercado.paso_titulo')} placeholder={t('sd_mercado.paso_titulo')} value={p.label}
                  onChange={e => setPasos(pasos.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} />
                <input className="ds-input" aria-label={t('sd_mercado.paso_pregunta')} placeholder={t('sd_mercado.paso_pregunta')} value={p.prompt}
                  onChange={e => setPasos(pasos.map((x, j) => j === i ? { ...x, prompt: e.target.value } : x))} />
                <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => setPasos(pasos.filter((_, j) => j !== i))}>{t('sd_mercado.quitar')}</Button>
              </div>
            ))}
          </div>
          <div className="u-row-between">
            <Button size="sm" variant="secondary" icon={<Plus size={12} />} onClick={() => setPasos([...pasos, { label: '', prompt: '' }])}>{t('sd_mercado.anadir_paso')}</Button>
            <Button size="sm" onClick={() => crear.mutate()} loading={crear.isPending} disabled={!validos}>{t('sd_mercado.crear_plantilla')}</Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
