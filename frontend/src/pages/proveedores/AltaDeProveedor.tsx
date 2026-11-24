/**
 * Alta de proveedor con elección de tipo (19-11-2026, migración 189).
 *
 * - «Persona (freelance)»: un paso. Los datos de la persona son los del externo
 *   (`CamposDeExterno`: responsable interno obligatorio, acceso, tarifa,
 *   capacidad, disponibilidad) más NIF, país y formación. `POST /suppliers/freelance`
 *   crea proveedor, persona y usuario; si vuelve contraseña temporal se enseña una vez.
 * - «Empresa»: el formulario de siempre (`POST /enterprise/subcontractors`) y
 *   sus modos de relación, que se guardan con `PATCH /suppliers/{id}/classification`.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Building2, UserRound } from 'lucide-react'
import { Button, Checkbox, Input, Modal, Select, useErroresDeCampo, Textarea } from '../../components/ui'
import { CamposDeExterno, CredencialesDeExterno, cargaDeExterno, externoCompleto, formularioDeExternoInicial } from '../../components/externos/FormularioDeExterno'
import type { FormDeExterno } from '../../components/externos/FormularioDeExterno'
import { subcontractorsApi } from '../../services/api'
import { proveedoresApi } from '../../services/api/proveedores'
import type { AltaDeFreelanceIn, ModoDeRelacion, TipoDeProveedor } from '../../services/api/tipos-proveedores'
import type { Subcontratista } from '../../services/api/tipos-alm'
import { useToast } from '../../context/ToastContext'
import { useOrgSettings } from '../../hooks/useOrgSettings'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { MODOS } from './logica'
import { etiquetaDe, useT } from './comunes'

/** Extras del freelance que no están en el formulario del externo. */
export type ExtrasDeFreelance = { vat_number: string; country: string; training_enabled: boolean; outsourcing: boolean }

/** Cuerpo de `POST /suppliers/freelance` (AltaDeFreelance). */
export function cargaDeFreelance(form: FormDeExterno, extra: ExtrasDeFreelance): AltaDeFreelanceIn {
  return {
    ...(cargaDeExterno(form) as unknown as AltaDeFreelanceIn),
    internal_owner_id: form.internal_owner_id,
    vat_number: extra.vat_number.trim() || null,
    country: extra.country.trim() || null,
    training_enabled: extra.training_enabled,
    engagement_modes: extra.outsourcing ? ['staff_augmentation', 'outsourcing'] : ['staff_augmentation'],
  }
}

type FormDeEmpresa = { name: string; legal_name: string; company: string; email: string; phone: string; country: string; currency: string; vat_number: string; notes: string }

function ModosDeRelacion({ valor, onChange }: { valor: ModoDeRelacion[]; onChange: (m: ModoDeRelacion[]) => void }) {
  const t = useT()
  return (
    <div className="prv-modos" role="group" aria-label={t('proveedores.modos')}>
      <div className="uiinde-estiloetiqueta">{t('proveedores.modos')} *</div>
      {MODOS.map(m => (
        <Checkbox key={m} checked={valor.includes(m)} label={etiquetaDe(t, 'modo_', m)} ayuda={t(`proveedores.modo_${m}_d`)}
          onChange={v => onChange(v ? [...valor, m] : valor.filter(x => x !== m))} />
      ))}
    </div>
  )
}
export { ModosDeRelacion }

export default function AltaDeProveedor({ onClose, onCreado }: { onClose: () => void; onCreado?: (s: Subcontratista) => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const { currency, currencies, weekly_capacity_hours: capacidad } = useOrgSettings()
  const [tipo, setTipo] = useState<TipoDeProveedor | null>(null)
  const [persona, setPersona] = useState<FormDeExterno>(() => formularioDeExternoInicial(null, currency, capacidad))
  const [extra, setExtra] = useState<ExtrasDeFreelance>({ vat_number: '', country: '', training_enabled: false, outsourcing: false })
  const [empresa, setEmpresa] = useState<FormDeEmpresa>({ name: '', legal_name: '', company: '', email: '', phone: '', country: '', currency, vat_number: '', notes: '' })
  const [modos, setModos] = useState<ModoDeRelacion[]>(['staff_augmentation'])
  const [credenciales, setCredenciales] = useState<{ usuario: string; contrasena?: string | null } | null>(null)
  const [creado, setCreado] = useState<Subcontratista | null>(null)
  const campos = useErroresDeCampo()

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['subcontractors'] })
    qc.invalidateQueries({ queryKey: ['sub-dashboard'] })
    qc.invalidateQueries({ queryKey: ['suppliers'] })
    qc.invalidateQueries({ queryKey: ['users'] })
  }
  const alFallar = (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }

  const altaFreelance = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => proveedoresApi.altaFreelance(cargaDeFreelance(persona, extra)).then(r => r.data),
    onSuccess: res => {
      refrescar()
      toast.success(t('proveedores.freelance_creado'))
      // Con contraseña temporal se enseña antes de abrir la ficha (abrirla desmonta este diálogo).
      if (res.login_username && res.temp_password) { setCreado(res.supplier); setCredenciales({ usuario: res.login_username, contrasena: res.temp_password }) }
      else { onCreado?.(res.supplier); onClose() }
    },
    onError: alFallar,
  })

  const altaEmpresa = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: async (): Promise<Subcontratista> => {
      const { legal_name, ...resto } = empresa
      const creado = (await subcontractorsApi.create({ ...resto, country: resto.country || null })).data
      const clasificado = await proveedoresApi.clasificar(creado.id, { kind: 'company', engagement_modes: modos, legal_name: legal_name.trim() || null })
      return { ...creado, ...clasificado.data }
    },
    onSuccess: s => { refrescar(); toast.success(t('subcontractors.subcontratista_creado')); onCreado?.(s); onClose() },
    onError: alFallar,
  })

  if (credenciales) {
    return <CredencialesDeExterno usuario={credenciales.usuario} contrasena={credenciales.contrasena}
      onClose={() => { onClose(); if (creado) onCreado?.(creado) }} />
  }

  const campoEmpresa = (k: keyof FormDeEmpresa) => (e: { target: { value: string } }) => { campos.limpiar(k); setEmpresa(f => ({ ...f, [k]: e.target.value })) }

  return (
    <Modal open title={t('proveedores.nuevo_proveedor')} subtitle={tipo ? etiquetaDe(t, 'tipo_', tipo) : t('proveedores.elige_tipo')} onClose={onClose} width={620}>
      {!tipo && (
        <div className="prv-eleccion">
          <Button variant="secondary" icon={<UserRound size={16} />} onClick={() => setTipo('freelance')}>{t('proveedores.alta_freelance')}</Button>
          <Button variant="secondary" icon={<Building2 size={16} />} onClick={() => setTipo('company')}>{t('proveedores.alta_empresa')}</Button>
          <p className="u-text2-sm">{t('proveedores.tipo_freelance_d')}</p>
          <p className="u-text2-sm">{t('proveedores.tipo_company_d')}</p>
        </div>
      )}

      {tipo === 'freelance' && (
        <div className="u-stack-8">
          <CamposDeExterno form={persona} errores={campos.de} onChange={c => { Object.keys(c).forEach(k => campos.limpiar(k)); setPersona(f => ({ ...f, ...c })) }} />
          <div className="prv-rejilla">
            <Input label={t('subcontractors.nif_vat')} value={extra.vat_number} onChange={e => setExtra(x => ({ ...x, vat_number: e.target.value }))} error={campos.de('vat_number')} />
            <Input label={t('proveedores.pais')} value={extra.country} onChange={e => setExtra(x => ({ ...x, country: e.target.value }))} error={campos.de('country')} />
          </div>
          <Checkbox checked={extra.outsourcing} onChange={v => setExtra(x => ({ ...x, outsourcing: v }))}
            label={t('proveedores.freelance_outsourcing')} ayuda={t('proveedores.freelance_outsourcing_d')} />
          <Checkbox checked={extra.training_enabled} onChange={v => setExtra(x => ({ ...x, training_enabled: v }))}
            label={t('proveedores.formacion')} ayuda={t('proveedores.formacion_d')} />
          <div className="u-actions-8">
            <Button variant="ghost" onClick={() => setTipo(null)}>{t('proveedores.cambiar_tipo')}</Button>
            <Button onClick={() => altaFreelance.mutate()} loading={altaFreelance.isPending} disabled={!externoCompleto(persona) || altaFreelance.isPending}>
              {t('proveedores.crear_freelance')}
            </Button>
          </div>
        </div>
      )}

      {tipo === 'company' && (
        <div className="u-stack-8">
          <div className="prv-rejilla">
            <Input label={t('subcontractors.nombre_razon_social')} required value={empresa.name} onChange={campoEmpresa('name')} error={campos.de('name')} />
            <Input label={t('proveedores.razon_social')} value={empresa.legal_name} onChange={campoEmpresa('legal_name')} error={campos.de('legal_name')} />
            <Input label={t('subcontractors.email')} type="email" value={empresa.email} onChange={campoEmpresa('email')} error={campos.de('email')} />
            <Input label={t('subcontractors.telefono')} value={empresa.phone} onChange={campoEmpresa('phone')} error={campos.de('phone')} />
            <Input label={t('subcontractors.nif_vat')} value={empresa.vat_number} onChange={campoEmpresa('vat_number')} error={campos.de('vat_number')} />
            <Input label={t('proveedores.pais')} value={empresa.country} onChange={campoEmpresa('country')} error={campos.de('country')} />
            <Select label={t('subcontractors.moneda')} value={empresa.currency} onChange={campoEmpresa('currency')} placeholder={false}
              options={currencies.map(c => ({ value: c, label: c }))} error={campos.de('currency')} />
          </div>
          <ModosDeRelacion valor={modos} onChange={setModos} />
          <Textarea label={t('subcontractors.notes')} id="prv-alta-notas" value={empresa.notes} onChange={campoEmpresa('notes')} />
          <div className="u-actions-8">
            <Button variant="ghost" onClick={() => setTipo(null)}>{t('proveedores.cambiar_tipo')}</Button>
            <Button onClick={() => altaEmpresa.mutate()} loading={altaEmpresa.isPending} disabled={!empresa.name.trim() || modos.length === 0 || altaEmpresa.isPending}>
              {t('subcontractors.crear_subcontratista')}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
