/**
 * Editar la clasificación de un proveedor (19-11-2026): tipo, modos, responsable
 * interno, datos de ficha y GRC (acceso a datos, sistemas, formación) y el
 * enlace con el mismo proveedor en ALM. `PATCH /suppliers/{id}/classification`.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Checkbox, Input, Modal, Select, useErroresDeCampo } from '../../components/ui'
import { usePersonasInternas } from '../../components/externos/FormularioDeExterno'
import { etiquetaDePersona } from '../../components/ui/MarcaExterno'
import { vendorsApi } from '../../services/api'
import { proveedoresApi } from '../../services/api/proveedores'
import type { ClasificacionIn, ModoDeRelacion, TipoDeProveedor } from '../../services/api/tipos-proveedores'
import type { Subcontratista } from '../../services/api/tipos-alm'
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { STALE_REFERENCE_DATA_MS } from '../../constants/timings'
import { TIPOS, texto } from './logica'
import { etiquetaDe, useT } from './comunes'
import { ModosDeRelacion } from './AltaDeProveedor'

export default function ClasificacionModal({ sub, onClose }: { sub: Subcontratista; onClose: () => void }) {
  const t = useT()
  const tApp = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const campos = useErroresDeCampo()
  const { personas } = usePersonasInternas()
  const { data: vendors = [] } = useQuery({
    queryKey: ['alm-vendors'],
    queryFn: () => vendorsApi.list().then(r => r.data),
    staleTime: STALE_REFERENCE_DATA_MS,
    retry: false,
  })
  const [f, setF] = useState({
    kind: (sub.kind || 'company') as TipoDeProveedor,
    engagement_modes: (sub.engagement_modes || []) as ModoDeRelacion[],
    internal_owner_id: texto(sub.internal_owner_id),
    alm_vendor_id: texto(sub.alm_vendor_id),
    legal_name: texto(sub.legal_name),
    website: texto(sub.website),
    address: texto(sub.address),
    training_enabled: !!sub.training_enabled,
    data_access: !!sub.data_access,
    data_categories: texto(sub.data_categories),
    systems_access: texto(sub.systems_access),
  })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => { campos.limpiar(k); setF(x => ({ ...x, [k]: e.target.value })) }

  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => {
      const d: ClasificacionIn = {
        ...f,
        internal_owner_id: f.internal_owner_id || null,
        alm_vendor_id: f.alm_vendor_id || null,
        legal_name: f.legal_name.trim() || null,
        website: f.website.trim() || null,
        address: f.address.trim() || null,
        data_categories: f.data_categories.trim() || null,
        systems_access: f.systems_access.trim() || null,
      }
      return proveedoresApi.clasificar(sub.id, d)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subcontractors'] })
      qc.invalidateQueries({ queryKey: ['suppliers'] })
      toast.success(t('proveedores.clasificacion_guardada'))
      onClose()
    },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  return (
    <Modal open title={t('proveedores.editar_clasificacion')} subtitle={sub.name} onClose={onClose} width={620}>
      <div className="u-stack-8">
        <div className="prv-rejilla">
          <Select label={t('proveedores.tipo')} value={f.kind} placeholder={false} onChange={set('kind')} error={campos.de('kind')}
            options={TIPOS.map(k => ({ value: k, label: etiquetaDe(t, 'tipo_', k) }))} />
          <Select label={t('externos.responsable_interno')} value={f.internal_owner_id} onChange={set('internal_owner_id')} error={campos.de('internal_owner_id')}
            placeholder={t('externos.elegir_responsable')}
            options={personas.map(p => ({ value: p.id, label: etiquetaDePersona(tApp, p) }))} />
          <Input label={t('proveedores.razon_social')} value={f.legal_name} onChange={set('legal_name')} error={campos.de('legal_name')} />
          <Input label={t('proveedores.web')} value={f.website} onChange={set('website')} error={campos.de('website')} />
          <Input className="prv-completo" label={t('proveedores.direccion')} value={f.address} onChange={set('address')} error={campos.de('address')} />
          <Select className="prv-completo" label={t('proveedores.proveedor_alm')} value={f.alm_vendor_id} onChange={set('alm_vendor_id')} error={campos.de('alm_vendor_id')}
            placeholder={t('proveedores.sin_enlace_alm')} hint={t('proveedores.proveedor_alm_d')}
            options={vendors.map(v => ({ value: v.id, label: v.name }))} />
        </div>
        {f.kind === 'company' && (
          <ModosDeRelacion valor={f.engagement_modes} onChange={m => setF(x => ({ ...x, engagement_modes: m }))} />
        )}
        <Checkbox checked={f.training_enabled} onChange={v => setF(x => ({ ...x, training_enabled: v }))} label={t('proveedores.formacion')} ayuda={t('proveedores.formacion_d')} />
        <Checkbox checked={f.data_access} onChange={v => setF(x => ({ ...x, data_access: v }))} label={t('proveedores.acceso_a_datos')} ayuda={t('proveedores.acceso_a_datos_d')} />
        {f.data_access && (
          <Input label={t('proveedores.categorias_de_datos')} value={f.data_categories} onChange={set('data_categories')} error={campos.de('data_categories')} />
        )}
        <Input label={t('proveedores.sistemas')} value={f.systems_access} onChange={set('systems_access')} error={campos.de('systems_access')} />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => guardar.mutate()} loading={guardar.isPending}
            disabled={guardar.isPending || (f.kind === 'company' && f.engagement_modes.length === 0)}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}
