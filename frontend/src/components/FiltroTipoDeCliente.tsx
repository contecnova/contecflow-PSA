/**
 * Filtro Todos / Externos / Internos por el tipo del cliente (rev. 193,
 * docs/CLIENTES_INTERNOS.md §11). Lo usan la cartera (propuestas), la
 * rentabilidad, la salud de proyectos y el panel de una cartera: el backend
 * acepta `client_kind=externo|interno` (sin cliente cuenta como externo).
 */
import { Select } from './ui'
import { useAppT } from '../i18n/AppLangContext'

export type TipoDeCliente = '' | 'externo' | 'interno'

/** Parámetros de consulta: sin tipo, ninguno. */
export const paramsDeTipo = (tipo: TipoDeCliente): Record<string, string> => (tipo ? { client_kind: tipo } : {})

export default function FiltroTipoDeCliente({ value, onChange, className }: {
  value: TipoDeCliente
  onChange: (v: TipoDeCliente) => void
  className?: string
}) {
  const t = useAppT()
  return (
    <Select suelto placeholder={false} className={className || 'ds-input'} aria-label={t('internos.filtro_tipo_cliente')}
      value={value} onChange={e => onChange(e.target.value as TipoDeCliente)}>
      <option value="">{t('internos.filtro_todos')}</option>
      <option value="externo">{t('internos.filtro_externos')}</option>
      <option value="interno">{t('internos.filtro_internos')}</option>
    </Select>
  )
}
