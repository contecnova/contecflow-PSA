/**
 * «Nuevo externo» desde Recursos: elige el proveedor y da de alta a la persona
 * con `POST /enterprise/subcontractors/{sub_id}/workers`. Si el servidor crea
 * el usuario (con acceso), enseña una vez `login_username` y `temp_password`.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Modal, Select } from '../ui'
import { enterpriseSubsApi, subcontractorsApi } from '../../services/api'
import type { Subcontratista, SubTrabajadorCreado } from '../../services/api/tipos-alm'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useOrgSettings } from '../../hooks/useOrgSettings'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { CamposDeExterno, CredencialesDeExterno, cargaDeExterno, externoCompleto, formularioDeExternoInicial } from './FormularioDeExterno'
import type { FormDeExterno } from './FormularioDeExterno'

export default function AltaDeExternoModal({ onClose }: { onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { currency } = useOrgSettings()
  const [subId, setSubId] = useState('')
  const [form, setForm] = useState<FormDeExterno>(() => formularioDeExternoInicial(null, currency))
  const [creds, setCreds] = useState<{ usuario: string; contrasena?: string } | null>(null)

  const { data: proveedores = [], isLoading } = useQuery<Subcontratista[]>({
    queryKey: ['subcontractors'],
    queryFn: () => subcontractorsApi.list().then(r => r.data),
  })
  const activos = proveedores.filter(p => p.is_active !== false)

  const elegirProveedor = (id: string) => {
    setSubId(id)
    // La moneda del proveedor por defecto, si no se ha tocado.
    const prov = activos.find(p => p.id === id)
    if (prov?.currency) setForm(f => ({ ...f, currency: prov.currency || f.currency }))
  }

  const { mutate: crear, isPending } = useMutation({
    mutationFn: async (): Promise<SubTrabajadorCreado> => (await enterpriseSubsApi.createWorker(subId, cargaDeExterno(form))).data,
    onSuccess: (creado) => {
      qc.invalidateQueries({ queryKey: ['resources'] })
      qc.invalidateQueries({ queryKey: ['users'] })
      qc.invalidateQueries({ queryKey: ['sub-workers', subId] })
      qc.invalidateQueries({ queryKey: ['subcontractors'] })
      if (creado?.temp_password && creado.login_username) {
        setCreds({ usuario: creado.login_username, contrasena: creado.temp_password })
      } else {
        toast.success(t('externos.alta_hecha'))
        onClose()
      }
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (creds) return <CredencialesDeExterno usuario={creds.usuario} contrasena={creds.contrasena} onClose={onClose} />

  return (
    <Modal open title={t('externos.nuevo_externo')} subtitle={t('externos.nuevo_externo_sub')} onClose={onClose} width={620}>
      <Select className="ext-proveedor" label={`${t('externos.proveedor')} *`} required value={subId} disabled={isLoading}
        onChange={e => elegirProveedor(e.target.value)} placeholder={t('externos.elegir_proveedor')}
        hint={!isLoading && activos.length === 0 ? t('externos.sin_proveedores') : undefined}
        options={activos.map(p => ({ value: p.id, label: p.company && p.company !== p.name ? `${p.name} (${p.company})` : p.name }))} />
      <CamposDeExterno form={form} onChange={c => setForm(f => ({ ...f, ...c }))} />
      <div className="u-actions-8">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => crear()} loading={isPending} disabled={!subId || !externoCompleto(form) || isPending}>
          {t('externos.dar_de_alta')}
        </Button>
      </div>
    </Modal>
  )
}
