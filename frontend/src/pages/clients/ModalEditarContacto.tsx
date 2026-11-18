// Edición de un contacto (persona) del cliente. La abren la pestaña Contactos
// y la tarjeta «Contacto principal» de la ficha.
import { useId, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Modal, Select, useErroresDeCampo } from '../../components/ui'
import { clientExtApi, type ClientContact } from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import { invalidarContactosDelCliente, rolesDeContacto } from './contactosCliente'
import './ClientsPageTabs.css'

type FormContacto = { full_name: string; job_title: string; email: string; phone: string; role: string; notes: string }

export function ModalEditarContacto({ cid, contacto, onClose }: { cid: string; contacto: ClientContact; onClose: () => void }) {
  const idCampo = useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const campos = useErroresDeCampo()
  const esPrincipal = !!contacto.is_primary
  const [form, setForm] = useState<FormContacto>({
    full_name: contacto.full_name || '',
    job_title: contacto.job_title || '',
    email: contacto.email || '',
    phone: contacto.phone || '',
    role: esPrincipal ? 'primary' : (contacto.role || 'other'),
    notes: contacto.notes || '',
  })
  // El rol «Principal» va con ser el principal: no se elige aquí (para eso,
  // «Marcar como principal»), salvo que el contacto ya lo tuviera.
  const roles = rolesDeContacto(t).filter(r => esPrincipal || r.id !== 'primary' || contacto.role === 'primary')

  const { mutate: guardar, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: (d: FormContacto) => {
      const { role, ...resto } = d
      return clientExtApi.updateContact(cid, contacto.id, esPrincipal ? resto : { ...resto, role }).then(r => r.data)
    },
    onSuccess: () => {
      invalidarContactosDelCliente(qc, cid)
      toast.success(t('clicontactos.contacto_actualizado'))
      onClose()
    },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('clicontactos.error_guardar'))) },
  })

  const campo = (clave: keyof FormContacto, etiqueta: string, tipo = 'text') => (
    <div>
      <label id={`${idCampo}-et-${clave}`} htmlFor={`${idCampo}-${clave}`} className="clpata-lbl">{etiqueta}</label>
      <input id={`${idCampo}-${clave}`} aria-labelledby={`${idCampo}-et-${clave}`} type={tipo} value={form[clave]}
        aria-invalid={campos.de(clave) ? true : undefined}
        onChange={e => { campos.limpiar(clave); setForm(f => ({ ...f, [clave]: e.target.value })) }}
        className="clpata-inp" />
      {campos.de(clave) && <div className="u-field-error">{campos.de(clave)}</div>}
    </div>
  )

  return (
    <Modal open title={t('clicontactos.editar_contacto_titulo', { nombre: contacto.full_name })} onClose={onClose} width={520}>
      <form onSubmit={e => { e.preventDefault(); if (form.full_name.trim()) guardar(form) }}>
        <div className="clpata-grid-1">
          {campo('full_name', `${t('clicontactos.nombre_contacto')} *`)}
          {campo('job_title', t('clicontactos.cargo_contacto'))}
          {campo('email', t('clicontactos.email_contacto'), 'email')}
          {campo('phone', t('clicontactos.telefono_contacto'))}
          <div>
            <Select label={t('clicontactos.rol')} placeholder={false} value={form.role} disabled={esPrincipal}
              hint={esPrincipal ? t('clicontactos.rol_fijo_principal') : undefined} error={campos.de('role')}
              onChange={e => { campos.limpiar('role'); setForm(f => ({ ...f, role: e.target.value })) }}
              options={roles.map(r => ({ value: r.id, label: r.label }))} />
          </div>
        </div>
        <div className="u-mb-16">
          <label id={`${idCampo}-et-notes`} htmlFor={`${idCampo}-notes`} className="clpata-lbl">{t('clicontactos.notas')}</label>
          <textarea id={`${idCampo}-notes`} aria-labelledby={`${idCampo}-et-notes`} value={form.notes}
            aria-invalid={campos.de('notes') ? true : undefined}
            onChange={e => { campos.limpiar('notes'); setForm(f => ({ ...f, notes: e.target.value })) }}
            className="clpata-inp" />
          {campos.de('notes') && <div className="u-field-error">{campos.de('notes')}</div>}
        </div>
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('clicontactos.cancelar')}</Button>
          <Button type="submit" loading={isPending} disabled={!form.full_name.trim() || isPending}>
            {isPending ? t('clicontactos.guardando') : t('clicontactos.guardar')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
