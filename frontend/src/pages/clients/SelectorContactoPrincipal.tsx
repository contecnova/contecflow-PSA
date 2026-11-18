// Sección «Contacto principal» del alta/edición de cliente. El contacto es una
// persona (tabla de contactos), no un dato de la empresa:
//   - con contactos: se elige uno existente o «Nuevo contacto…»;
//   - sin contactos (alta): directamente los campos del nuevo contacto.
// `datosDeContactoPrincipal` traduce la elección al cuerpo del POST/PATCH.
import { Select } from '../../components/ui'
import { useAppLang } from '../../i18n/AppLangContext'

export const NUEVO_CONTACTO = '__nuevo__'

export type NuevoContacto = { contact_name: string; contact_role: string; contact_email: string; contact_phone: string }
export const NUEVO_CONTACTO_VACIO: NuevoContacto = { contact_name: '', contact_role: '', contact_email: '', contact_phone: '' }

export type ContactoElegible = { id: string; full_name: string; email?: string | null; job_title?: string | null }

/** Lo que va en el cuerpo del alta/edición del cliente según lo elegido:
 *  contacto existente → `primary_contact_id`; nuevo → `contact_*` (solo si se
 *  ha escrito algo); sin elección → nada (el principal no cambia). */
export function datosDeContactoPrincipal(
  hayContactos: boolean, valor: string, nuevo: NuevoContacto,
): { primary_contact_id: string } | Partial<NuevoContacto> {
  if (hayContactos && valor !== NUEVO_CONTACTO) return valor ? { primary_contact_id: valor } : {}
  const salida: Partial<NuevoContacto> = {}
  for (const [k, v] of Object.entries(nuevo) as [keyof NuevoContacto, string][]) {
    if (v.trim()) salida[k] = v.trim()
  }
  return salida
}

interface Props {
  idBase: string
  contactos: ContactoElegible[]
  valor: string
  onCambiar: (valor: string) => void
  nuevo: NuevoContacto
  onCambiarNuevo: (campo: keyof NuevoContacto, valor: string) => void
  /** Error por campo (de useErroresDeCampo o de la validación del formulario). */
  errorDe?: (campo: string) => string | undefined
}

export function SelectorContactoPrincipal({ idBase, contactos, valor, onCambiar, nuevo, onCambiarNuevo, errorDe }: Props) {
  const { t } = useAppLang()
  const hayContactos = contactos.length > 0
  const verNuevo = !hayContactos || valor === NUEVO_CONTACTO

  const campo = (clave: keyof NuevoContacto, etiqueta: string, tipo = 'text') => {
    const err = errorDe?.(clave)
    const id = `${idBase}-${clave}`
    return (
      <div>
        <label id={`${id}-et`} htmlFor={id} className="cli-label">{etiqueta}</label>
        <input id={id} aria-labelledby={`${id}-et`} type={tipo} value={nuevo[clave]} className="cli-input"
          aria-invalid={err ? true : undefined} aria-describedby={err ? `${id}-err` : undefined}
          onChange={e => onCambiarNuevo(clave, e.target.value)} />
        {err && <div id={`${id}-err`} className="u-field-error">{err}</div>}
      </div>
    )
  }

  return (
    <div className="cli-seccion" role="group" aria-labelledby={`${idBase}-titulo`}>
      <div id={`${idBase}-titulo`} className="cli-seccion__titulo">{t('clicontactos.seccion_contacto_principal')}</div>
      {hayContactos && (
        <Select label={t('clicontactos.contacto')} value={valor} onChange={e => onCambiar(e.target.value)}
          placeholder={t('clicontactos.sin_contacto_principal')} error={errorDe?.('primary_contact_id')}
          options={[
            ...contactos.map(c => ({ value: c.id, label: [c.full_name, c.job_title, c.email].filter(Boolean).join(' · ') })),
            { value: NUEVO_CONTACTO, label: t('clicontactos.nuevo_contacto_opcion') },
          ]} />
      )}
      {verNuevo && (
        <>
          <div className="cli-form-grid">
            {campo('contact_name', t('clicontactos.nombre_contacto'))}
            {campo('contact_role', t('clicontactos.cargo_contacto'))}
            {campo('contact_email', t('clicontactos.email_contacto'), 'email')}
            {campo('contact_phone', t('clicontactos.telefono_contacto'))}
          </div>
          <div className="u-hint">{t('clicontactos.nuevo_contacto_ayuda')}</div>
        </>
      )}
    </div>
  )
}
