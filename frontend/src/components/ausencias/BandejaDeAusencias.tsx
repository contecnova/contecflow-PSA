/**
 * Bandeja de quien aprueba (tarea #25): las ausencias en las que le toca el
 * paso actual (motor de aprobaciones) o, sin flujo, las de quien depende de él;
 * con la explicación de las políticas, el impacto en la cobertura de cada día y
 * turno, las plazas del cupo y el saldo. Aprobar o rechazar es un voto en ESA
 * solicitud (varios niveles, en paralelo, delegación).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Inbox, X } from 'lucide-react'
import { ausenciasApi } from '../../services/api/ausencias'
import type { ElementoDeBandeja } from '../../services/api/tipos-ausencias'
import { Button, EmptyState, Spinner, TablaSimple, Pulsable } from '../ui'
import { AvisoDeError } from './admin/comun'
import { TipoChip, cantidad, fecha, useTa, useTurnos } from './comun'

export default function BandejaDeAusencias({ onAbrir }: { onAbrir: (id: string) => void }) {
  const { ta } = useTa()
  const q = useQuery({ queryKey: ['ausencias', 'bandeja'], queryFn: ausenciasApi.bandeja })
  if (q.isLoading) return <Spinner label={ta('cargando')} />
  if (q.isError) return <AvisoDeError error={q.error} defecto={ta('error_cargar')} />
  if (!q.data?.length) return <EmptyState svgIcon={<Inbox size={26} />} title={ta('bandeja_vacia')} description={ta('bandeja_vacia_texto')} />
  return <ul className="aus-bandeja">{q.data.map(x => <Elemento key={x.ausencia.id} x={x} onAbrir={onAbrir} />)}</ul>
}

function Elemento({ x, onAbrir }: { x: ElementoDeBandeja; onAbrir: (id: string) => void }) {
  const { ta } = useTa()
  const qc = useQueryClient()
  const turnos = useTurnos().data ?? []
  const [nota, setNota] = useState('')
  const decidir = useMutation({
    mutationFn: (aprobada: boolean) => ausenciasApi.decidir(x.ausencia.id, aprobada, nota),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ausencias'] }),
  })
  const a = x.ausencia
  const reglas = (x.explicacion?.explicacion.politicas ?? []).filter(p => p.aplica)
    .flatMap(p => p.reglas.filter(r => r.cumple).map(r => `${p.politica}: ${r.regla}`))
  const faltan = x.impacto.filter(c => (c.con_esta ?? c.disponibles) < c.requeridas)
  return (
    <li className="aus-tarjeta">
      <header className="aus-fila">
        <Pulsable className="aus-enlace" onClick={() => onAbrir(a.id)}>{a.user_name}</Pulsable>
        <TipoChip a={a} />
        <span>{fecha(a.start_date)} → {fecha(a.end_date)} · {cantidad(a, ta)}</span>
        {x.paso && <span className="aus-chip">{ta('paso')}: {x.paso}</span>}
        {x.sin_flujo && <span className="aus-chip">{ta('sin_flujo')}</span>}
      </header>
      {a.reason && <p className="aus-ayuda">{a.reason}</p>}
      <dl className="aus-datos">
        {x.saldo_restante !== null && (<><dt>{ta('saldo_tras')}</dt><dd className={x.saldo_restante < 0 ? 'aus-negativo' : ''}>{x.saldo_restante}</dd></>)}
        <dt>{ta('companeros_ausentes')}</dt><dd>{x.companeros_ausentes}</dd>
        {x.cobertura_restante !== null && (<><dt>{ta('cobertura_que_queda')}</dt>
          <dd className={x.cobertura_restante < 0 ? 'aus-negativo' : ''}>{x.cobertura_restante}</dd></>)}
      </dl>
      {reglas.length > 0 && (
        <details className="aus-explicacion">
          <summary>{ta('por_que', { n: reglas.length })}</summary>
          <ul className="aus-lista-simple">{reglas.map(r => <li key={r}>{r}</li>)}</ul>
        </details>
      )}
      {x.impacto.length > 0 && (
        <TablaSimple claseTabla="aus-tabla aus-tabla--compacta">
          <caption>{ta('impacto_en_cobertura')}</caption>
          <thead><tr><th scope="col">{ta('dia')}</th><th scope="col">{ta('turno')}</th><th scope="col">{ta('con_esta')}</th><th scope="col">{ta('requeridas')}</th></tr></thead>
          <tbody>
            {x.impacto.map(c => (
              <tr key={`${c.fecha}-${c.turno_id}`} className={(c.con_esta ?? c.disponibles) < c.requeridas ? 'aus-fila-llena' : ''}>
                <td>{fecha(c.fecha)}</td><td>{turnos.find(t => t.id === c.turno_id)?.nombre ?? '—'}</td>
                <td>{c.con_esta ?? c.disponibles}</td><td>{c.requeridas}</td>
              </tr>
            ))}
          </tbody>
        </TablaSimple>
      )}
      {faltan.length > 0 && <p className="aus-aviso" role="status">{ta('dejaria_sin_cobertura', { n: faltan.length })}</p>}
      <div className="aus-fila">
        <input className="aus-campo aus-campo--ancho" aria-label={ta('nota')} placeholder={ta('nota_opcional')} value={nota}
          onChange={e => setNota(e.target.value)} />
        <Button size="sm" icon={<Check size={13} />} loading={decidir.isPending && decidir.variables === true} onClick={() => decidir.mutate(true)}>{ta('aprobar')}</Button>
        <Button size="sm" variant="danger" icon={<X size={13} />} loading={decidir.isPending && decidir.variables === false} onClick={() => decidir.mutate(false)}>{ta('rechazar')}</Button>
      </div>
      {decidir.isError && <AvisoDeError error={decidir.error} defecto={ta('error_guardar')} />}
    </li>
  )
}
