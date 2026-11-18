/**
 * Formulario de recurso externo (persona de un proveedor `Subcontractor`).
 *
 * Lo comparten el alta desde Recursos («Nuevo externo») y la ficha del
 * trabajador en Subcontratistas. Un externo se trata como interno en el día a
 * día (tareas, imputación, ausencias), con seguridad de externo: responsable
 * interno obligatorio y acceso (login) opcional con fecha de fin. Contrato:
 * `POST /enterprise/subcontractors/{sub_id}/workers` y
 * `PATCH /enterprise/subcontractors/workers/{id}`.
 */
import { useId } from 'react'
import type { ChangeEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { KeyRound } from 'lucide-react'
import { Button, Input, Modal, Select, Checkbox } from '../ui'
import { esExterno, etiquetaDePersona } from '../ui/MarcaExterno'
import { usersApi } from '../../services/api'
import type { PersonaVisible } from '../../services/api/users'
import type { SubTrabajador } from '../../services/api/tipos-alm'
import { useAppT } from '../../i18n/AppLangContext'
import { useOrgSettings } from '../../hooks/useOrgSettings'
import { simboloMoneda } from '../../utils/helpers'
import { STALE_REFERENCE_DATA_MS } from '../../constants/timings'
import './FormularioDeExterno.css'

export interface FormDeExterno {
  name: string
  role: string
  email: string
  phone: string
  cost_rate: string
  sell_rate: string
  currency: string
  available_from: string
  available_until: string
  weekly_capacity_hours: string
  internal_owner_id: string
  has_access: boolean
  access_until: string
  /** El fin de acceso se escribió a mano; si no, sigue a «disponible hasta». */
  access_until_manual: boolean
  notes: string
}

const texto = (v: unknown) => (v == null ? '' : String(v))

/**
 * Estado inicial: vacío para un alta, o el del trabajador que se edita.
 * 18-11-2026: `capacidadPorDefecto` es la capacidad semanal de la empresa (los llamadores pasan la del hook);
 * el 40 solo queda como valor por omisión para llamadas sin contexto (tests).
 */
export function formularioDeExternoInicial(worker: Partial<SubTrabajador> | null | undefined, monedaPorDefecto: string, capacidadPorDefecto = 40): FormDeExterno {
  return {
    name: texto(worker?.name),
    role: texto(worker?.role),
    email: texto(worker?.email),
    phone: texto(worker?.phone),
    cost_rate: texto(worker?.cost_rate),
    sell_rate: texto(worker?.sell_rate),
    currency: worker?.currency || monedaPorDefecto,
    available_from: texto(worker?.available_from),
    available_until: texto(worker?.available_until),
    weekly_capacity_hours: texto(worker?.weekly_capacity_hours ?? capacidadPorDefecto),
    internal_owner_id: texto(worker?.internal_owner_id),
    // Un alta nueva entra con acceso: es el caso de «externo como interno».
    has_access: worker ? !!worker.has_access : true,
    access_until: texto(worker?.access_until),
    access_until_manual: !!worker?.access_until && worker.access_until !== worker.available_until,
    notes: texto(worker?.notes),
  }
}

const numero = (v: string): number | null => {
  if (v.trim() === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}
const fechaONull = (v: string) => (v.trim() ? v : null)

/** Fin de acceso efectivo: el escrito, o por defecto «disponible hasta». */
export function finDeAccesoEfectivo(form: Pick<FormDeExterno, 'has_access' | 'access_until' | 'access_until_manual' | 'available_until'>): string | null {
  if (!form.has_access) return null
  const propio = form.access_until_manual ? form.access_until : ''
  return fechaONull(propio || form.available_until)
}

/** Cuerpo que se manda al servidor (números y fechas vacías como null). */
export function cargaDeExterno(form: FormDeExterno): Record<string, unknown> {
  return {
    name: form.name.trim(),
    role: form.role.trim() || null,
    email: form.email.trim() || null,
    phone: form.phone.trim() || null,
    cost_rate: numero(form.cost_rate),
    sell_rate: numero(form.sell_rate),
    currency: form.currency || null,
    available_from: fechaONull(form.available_from),
    available_until: fechaONull(form.available_until),
    weekly_capacity_hours: numero(form.weekly_capacity_hours),
    internal_owner_id: form.internal_owner_id || null,
    has_access: form.has_access,
    access_until: finDeAccesoEfectivo(form),
    notes: form.notes.trim() || null,
  }
}

export type EstadoDeAcceso = 'sin_acceso' | 'con_acceso' | 'caduca' | 'caducado'

/** Acceso del externo a fecha `hoy` (YYYY-MM-DD): sin login, con login, con fin o ya vencido. */
export function estadoDeAcceso(w: { has_access?: boolean | null; access_until?: string | null }, hoy: string): EstadoDeAcceso {
  if (!w.has_access) return 'sin_acceso'
  if (!w.access_until) return 'con_acceso'
  return w.access_until < hoy ? 'caducado' : 'caduca'
}

/** Lo mínimo para guardar: nombre y responsable interno. */
export function externoCompleto(form: FormDeExterno): boolean {
  return !!form.name.trim() && !!form.internal_owner_id
}

/** Personas internas (no externas) del directorio, para el responsable. */
export function usePersonasInternas() {
  const { data = [], isLoading } = useQuery<PersonaVisible[]>({
    queryKey: ['users', 'directory'],
    queryFn: () => usersApi.directory().then(r => r.data),
    staleTime: STALE_REFERENCE_DATA_MS,
  })
  return { personas: data.filter(p => !esExterno(p)), isLoading }
}

export interface CamposDeExternoProps {
  form: FormDeExterno
  onChange: (cambio: Partial<FormDeExterno>) => void
  /** Error de validación del servidor de un campo (`useErroresDeCampo().de`). */
  errores?: (campo: string) => string | undefined
}

/** Rejilla de campos del externo (sin proveedor ni botones). */
export function CamposDeExterno({ form, onChange, errores }: CamposDeExternoProps) {
  const t = useAppT()
  const idBase = useId()
  const { currencies } = useOrgSettings()
  const { personas, isLoading } = usePersonasInternas()
  const campo = (k: keyof FormDeExterno) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    onChange({ [k]: e.target.value } as Partial<FormDeExterno>)
  const moneda = simboloMoneda(form.currency)
  const monedas = currencies.includes(form.currency) || !form.currency ? currencies : [form.currency, ...currencies]
  const finDeAcceso = finDeAccesoEfectivo(form) ?? ''

  return (
    <div className="ext-grid">
      <Input className="ext-full" label={t('externos.nombre')} required value={form.name} onChange={campo('name')} error={errores?.('name')} />
      <Input label={t('externos.cargo')} value={form.role} onChange={campo('role')} error={errores?.('role')} />
      <Input label={t('externos.email')} type="email" value={form.email} onChange={campo('email')} error={errores?.('email')} />
      <Input label={t('externos.coste_hora', { moneda })} type="number" min={0} step="0.5" value={form.cost_rate} onChange={campo('cost_rate')} error={errores?.('cost_rate')} />
      <Input label={t('externos.venta_hora', { moneda })} type="number" min={0} step="0.5" value={form.sell_rate} onChange={campo('sell_rate')} error={errores?.('sell_rate')} />
      <Select label={t('externos.moneda')} value={form.currency} onChange={campo('currency')} error={errores?.('currency')} placeholder={false}
        options={monedas.map(c => ({ value: c, label: c }))} />
      <Input label={t('externos.capacidad_semanal')} type="number" min={0} step="0.5" value={form.weekly_capacity_hours} onChange={campo('weekly_capacity_hours')} error={errores?.('weekly_capacity_hours')} />
      <Input label={t('externos.disponible_desde')} type="date" value={form.available_from} onChange={campo('available_from')} error={errores?.('available_from')} />
      <Input label={t('externos.disponible_hasta')} type="date" value={form.available_until} onChange={campo('available_until')} error={errores?.('available_until')} />
      <Select className="ext-full" label={`${t('externos.responsable_interno')} *`} required value={form.internal_owner_id}
        onChange={campo('internal_owner_id')} error={errores?.('internal_owner_id')} disabled={isLoading}
        placeholder={t('externos.elegir_responsable')}
        hint={t('externos.responsable_ayuda')}
        options={personas.map(p => ({ value: p.id, label: etiquetaDePersona(t, p) }))} />
      <div className="ext-full ext-acceso">
        <label className="ext-check" htmlFor={`${idBase}-acceso`}>
          <Checkbox id={`${idBase}-acceso`} checked={form.has_access}
            onChange={(_, e) => onChange({ has_access: e.target.checked })} />
          <span>{t('externos.con_acceso')}</span>
        </label>
        <div className="u-text3-xs">{form.has_access ? t('externos.con_acceso_ayuda') : t('externos.sin_acceso_ayuda')}</div>
        {form.has_access && (
          <Input label={t('externos.fin_de_acceso')} type="date" value={finDeAcceso}
            hint={form.access_until_manual ? undefined : t('externos.fin_de_acceso_ayuda')}
            onChange={e => onChange({ access_until: e.target.value, access_until_manual: true })} error={errores?.('access_until')} />
        )}
      </div>
      <div className="ext-full ui-field">
        <label htmlFor={`${idBase}-notas`} className="uiinde-estiloetiqueta">{t('externos.notas')}</label>
        <textarea id={`${idBase}-notas`} value={form.notes} onChange={campo('notes')} className="ds-input ext-notas" />
        {errores?.('notes') && <div className="u-field-error" role="alert">{errores('notes')}</div>}
      </div>
    </div>
  )
}

/** Credenciales del usuario recién creado: se enseñan una sola vez. */
export function CredencialesDeExterno({ usuario, contrasena, onClose }: { usuario: string; contrasena?: string | null; onClose: () => void }) {
  const t = useAppT()
  return (
    <Modal open title={t('externos.credenciales_titulo')} onClose={onClose} width={480}>
      <div className="ext-creds">
        <div className="ext-creds-icono" aria-hidden="true"><KeyRound size={22} /></div>
        <p className="u-text2-sm">{t('externos.credenciales_texto')}</p>
        <div className="ext-creds-caja">
          <div className="ext-creds-etiqueta">{t('externos.usuario')}</div>
          <div className="ds-codigo ext-creds-valor">{usuario}</div>
          {contrasena && <>
            <div className="ext-creds-etiqueta">{t('externos.contrasena_temporal')}</div>
            <div className="ds-codigo ext-creds-valor ext-creds-valor--aviso">{contrasena}</div>
          </>}
        </div>
        <p className="u-text3-xs">{t('externos.credenciales_aviso')}</p>
        <Button onClick={onClose}>{t('externos.entendido')}</Button>
      </div>
    </Modal>
  )
}
