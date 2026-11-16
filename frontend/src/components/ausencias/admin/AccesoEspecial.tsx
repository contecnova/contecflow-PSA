/**
 * Acceso a documentos de categoría especial (RGPD art. 9: salud). La persona y
 * RRHH siempre; un administrador u otra persona, solo si está en esta lista.
 * Conceder o retirar: solo administración (queda en auditoría).
 */
import { fmtDate } from '../../../utils/helpers'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ShieldCheck, Trash2, UserPlus } from 'lucide-react'
import { ausenciasApi } from '../../../services/api/ausencias'
import { Button, EmptyState, Spinner } from '../../ui'
import { UserSelect } from '../../ui/EntitySelect'
import { confirmar } from '../../../context/ConfirmContext'
import { useToast } from '../../../context/ToastContext'
import { AvisoDeError, errorDe, useT } from './comun'

export default function AccesoEspecial({ puedeEditar }: { puedeEditar: boolean }) {
  const { ta } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const [persona, setPersona] = useState('')
  const q = useQuery({ queryKey: ['ausencias', 'acceso-especial'], queryFn: ausenciasApi.accesos })
  const fijar = (data: unknown) => qc.setQueryData(['ausencias', 'acceso-especial'], data)
  const conceder = useMutation({
    mutationFn: () => ausenciasApi.concederAcceso(persona),
    onSuccess: r => { fijar(r); setPersona(''); toast.success(ta('acceso_concedido')) },
    onError: e => toast.error(errorDe(e, ta('error_guardar')).mensaje),
  })
  const retirar = useMutation({
    mutationFn: (userId: string) => ausenciasApi.retirarAcceso(userId),
    onSuccess: r => { fijar(r); toast.success(ta('acceso_retirado')) },
    onError: e => toast.error(errorDe(e, ta('error_guardar')).mensaje),
  })
  return (
    <section aria-labelledby="ausadm-acc-titulo">
      <h2 id="ausadm-acc-titulo" className="ausadm-titulo">{ta('acceso_titulo')}</h2>
      <p className="ausadm-ayuda ausadm-explicacion">{ta('acceso_ayuda')}</p>
      {puedeEditar && (
        <div className="ausadm-fila">
          <span className="ausadm-selector-persona"><UserSelect value={persona} onChange={(v: string) => setPersona(v)} /></span>
          <Button icon={<UserPlus size={14} />} disabled={!persona} loading={conceder.isPending} onClick={() => conceder.mutate()}>
            {ta('conceder')}</Button>
        </div>
      )}
      {q.isLoading ? <Spinner label={ta('cargando')} />
        : q.isError ? <AvisoDeError error={q.error} defecto={ta('error_cargar')} />
        : !(q.data ?? []).length ? <EmptyState svgIcon={<ShieldCheck size={26} />} title={ta('sin_accesos')} description={ta('sin_accesos_texto')} />
        : (
          <ul className="ausadm-lista">
            {(q.data ?? []).map(a => (
              <li key={a.id} className="ausadm-item ausadm-item--estatico">
                <ShieldCheck size={16} aria-hidden />
                <span className="ausadm-item-nombre">{a.nombre}
                  {a.created_at && <span className="ausadm-ayuda"> · {ta('desde_fecha', { fecha: fmtDate(a.created_at) })}</span>}</span>
                {puedeEditar && <Button size="xs" variant="ghost" icon={<Trash2 size={13} />} title={ta('retirar')}
                  onClick={async () => { if (await confirmar({ title: ta('retirar'), danger: true, message: ta('retirar_confirmar', { nombre: a.nombre }) })) retirar.mutate(a.user_id) }}>
                  <span className="u-sr-only">{ta('retirar')}</span></Button>}
              </li>
            ))}
          </ul>
        )}
    </section>
  )
}
