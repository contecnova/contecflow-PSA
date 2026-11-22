/**
 * Selector de ámbito del riesgo (22-11-2026): tipo (empresa, cliente, servicio,
 * máquina, aplicación) y, salvo la empresa, la entidad. Las opciones salen de
 * `/risk/compare?scope_type=…` (lo que el índice ya conoce); los clientes
 * internos (unidades) se marcan.
 */
import { useQuery } from '@tanstack/react-query'
import { useAppT } from '../../../../i18n/AppLangContext'
import { cmdbRiesgoApi } from '../../../../services/api/cmdbRiesgo'
import type { Ambito, TipoDeAmbito } from '../../../../services/api/cmdbRiesgo'
import { Select } from '../../../ui'
import { useEtiquetaSwr, useMetaRiesgo } from './comunRiesgo'

const TIPOS: TipoDeAmbito[] = ['org', 'client', 'service', 'machine', 'application']
/** Tope de entidades por tipo en el desplegable. */
export const LIMITE_DE_OPCIONES = 500

export default function SelectorDeAmbito({ valor, onChange, className }: { valor: Ambito; onChange: (a: Ambito) => void; className?: string }) {
  const t = useAppT()
  const e = useEtiquetaSwr()
  const meta = useMetaRiesgo()
  const tipos = meta.data?.scope_types?.length ? meta.data.scope_types : TIPOS
  const tipo = valor.scope_type
  const opciones = useQuery({
    queryKey: ['swr', 'opciones-ambito', tipo],
    queryFn: () => cmdbRiesgoApi.comparar({ scope_type: tipo as Exclude<TipoDeAmbito, 'org'>, limit: LIMITE_DE_OPCIONES }),
    enabled: tipo !== 'org',
  })
  const lista = [...(opciones.data ?? [])].sort((a, b) => a.name.localeCompare(b.name))
  return (
    <div className={className ?? 'swr-ambito'}>
      <Select label={t('swr.ambito')} placeholder={false} value={tipo} onChange={ev => onChange({ scope_type: ev.target.value as TipoDeAmbito, scope_id: null })}>
        {tipos.map(x => <option key={x} value={x}>{e('ambito', x)}</option>)}
      </Select>
      {tipo !== 'org' && (
        <Select label={e('ambito', tipo)} placeholder={t('swr.elige_entidad')} value={valor.scope_id ?? ''} disabled={opciones.isLoading}
          onChange={ev => onChange({ scope_type: tipo, scope_id: ev.target.value || null })}>
          {lista.map(o => <option key={o.scope_id} value={o.scope_id}>{o.name}{o.is_internal ? ` · ${t('swr.unidad')}` : ''}</option>)}
        </Select>
      )}
    </div>
  )
}
