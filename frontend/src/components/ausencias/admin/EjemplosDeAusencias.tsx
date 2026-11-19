/**
 * «Cargar ejemplo»: tres turnos al día, como mucho dos personas de vacaciones
 * por día y turno, plaza por orden de llegada al pedir, lista de espera,
 * aprobación del responsable y luego de RRHH, e informar al jefe de equipo.
 * Nada se aplica solo: la política queda en borrador y el flujo desactivado;
 * aquí se dice qué falta para ponerlo en marcha.
 *
 * 18-11-2026: los pasos que llevan a Políticas y Flujos solo enlazan para
 * administración (quien los publica); el resto ve el texto sin enlace. El
 * cuadrante ya no está en Configuración sino en el módulo de Ausencias
 * (`/absences?tab=cuadrante`), así que ese paso lleva allí.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { CheckCircle2, Sparkles } from 'lucide-react'
import { ausenciasApi } from '../../../services/api/ausencias'
import { Button, Pulsable } from '../../ui'
import { useAuth } from '../../../context/AuthContext'
import { AvisoDeError, useT } from './comun'

export default function EjemplosDeAusencias({ puedeCargar, onIr }: { puedeCargar: boolean; onIr: (tab: string) => void }) {
  const { ta } = useT()
  const esAdmin = useAuth().puede('org.administrar')
  const qc = useQueryClient()
  const cargar = useMutation({
    mutationFn: ausenciasApi.cargarEjemplos,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ausencias'] }),
  })
  const r = cargar.data
  return (
    <section aria-labelledby="ausadm-ej-titulo">
      <h2 id="ausadm-ej-titulo" className="ausadm-titulo">{ta('ejemplos_titulo')}</h2>
      <p className="ausadm-explicacion">{ta('ejemplos_texto')}</p>
      <ul className="ausadm-puntos">
        {['ej_turnos', 'ej_cupo', 'ej_espera', 'ej_flujo', 'ej_informar'].map(k => <li key={k}>{ta(k)}</li>)}
      </ul>
      <p className="ausadm-ayuda">{ta('ejemplos_nunca_solo')}</p>
      {puedeCargar
        ? <Button icon={<Sparkles size={14} />} loading={cargar.isPending} onClick={() => cargar.mutate()}>{ta('cargar_ejemplo')}</Button>
        : <p className="ausadm-ayuda">{ta('solo_admin')}</p>}
      <AvisoDeError error={cargar.error} defecto={ta('error_guardar')} />
      {r && (
        <div className="ausadm-tarjeta" role="status">
          <p><CheckCircle2 size={14} aria-hidden /> {ta('ejemplo_cargado')}</p>
          <ul className="ausadm-puntos">
            <li>{r.turnos.length ? ta('turnos_creados', { lista: r.turnos.join(', ') }) : ta('turnos_ya_estaban')}</li>
            <li>{r.politica ? ta('politica_creada') : ta('politica_ya_estaba')}</li>
            <li>{r.flujo ? ta('flujo_creado') : ta('flujo_ya_estaba')}</li>
          </ul>
          <h3 className="ausadm-subtitulo">{ta('pasos_siguientes')}</h3>
          <ol className="ausadm-puntos">
            {r.pasos_siguientes.map(p => (
              <li key={p}>
                {p === 'publicar_politica' && (esAdmin
                  ? <Link to="/settings/policies?dominio=ausencias">{ta('paso_publicar_politica')}</Link>
                  : ta('paso_publicar_politica'))}
                {p === 'activar_flujo' && (esAdmin
                  ? <Link to="/settings/approval-workflows">{ta('paso_activar_flujo')}</Link>
                  : ta('paso_activar_flujo'))}
                {p === 'elegir_flujo_en_vacaciones' && <Pulsable className="ausadm-enlace" onClick={() => onIr('tipos')}>{ta('paso_elegir_flujo')}</Pulsable>}
                {p === 'asignar_cuadrante' && <Link to="/absences?tab=cuadrante">{ta('paso_asignar_cuadrante')}</Link>}
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  )
}
