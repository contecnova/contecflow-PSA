/**
 * Administración de ausencias (tarea #25): tipos, documentos, turnos,
 * cuadrante y rotaciones, cobertura, acceso especial y ejemplos. Las reglas
 * (cupos, cierres, antelación…) se editan en Políticas (dominio «ausencias»)
 * y los flujos de aprobación en su diseñador gráfico.
 * Se muestra a administración y RRHH; lo que el API reserva a administración
 * (acceso especial, ejemplos) solo se ofrece a administración.
 *
 * Rev. 180: «Jornadas» (horario por día de la semana y a quién se aplica),
 * «Festivos» (por sede), «Personas» (ficha laboral y saldos con sus ajustes y
 * la bolsa de horas) y «Horario» (horario efectivo persona × día). Las tres
 * primeras se editan solo con administración o RRHH.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CalendarClock, CalendarDays, CalendarRange, CalendarX2, Clock, FileText, Grid3x3, Scale, ShieldCheck, Sparkles, Umbrella, Users, Workflow } from 'lucide-react'
import { Tabs } from '../../ui'
import { useAuth } from '../../../context/AuthContext'
import { useT } from './comun'
import EditorDeTipos from './EditorDeTipos'
import EditorDeDocumentos from './EditorDeDocumentos'
import EditorDeTurnos from './EditorDeTurnos'
import CuadranteDeTurnos from './CuadranteDeTurnos'
import { PanelDeCobertura } from './MapaDeCobertura'
import AccesoEspecial from './AccesoEspecial'
import EjemplosDeAusencias from './EjemplosDeAusencias'
import EditorDeJornadas from './EditorDeJornadas'
import EditorDeFestivos from './EditorDeFestivos'
import PersonasYSaldos from './PersonasYSaldos'
import PanelDeHorario from '../HorarioEfectivo'

export default function AdminDeAusencias() {
  const { ta } = useT()
  const { hasRole } = useAuth()
  const esAdmin = hasRole('admin')
  const esRrhh = hasRole('admin', 'hr')
  const [tab, setTab] = useState('tipos')
  return (
    <div className="ausadm">
      <nav className="ausadm-enlaces" aria-label={ta('mas_configuracion')}>
        <Link to="/settings/policies?dominio=ausencias" className="ausadm-enlace-tarjeta">
          <Scale size={16} aria-hidden /><span><strong>{ta('ir_a_politicas')}</strong><span className="ausadm-ayuda">{ta('ir_a_politicas_texto')}</span></span>
        </Link>
        <Link to="/settings/approval-workflows" className="ausadm-enlace-tarjeta">
          <Workflow size={16} aria-hidden /><span><strong>{ta('ir_a_flujos')}</strong><span className="ausadm-ayuda">{ta('ir_a_flujos_texto')}</span></span>
        </Link>
      </nav>
      <Tabs active={tab} onChange={setTab} items={[
        { id: 'tipos', label: ta('tab_tipos'), icon: <Umbrella size={14} /> },
        { id: 'documentos', label: ta('tab_documentos'), icon: <FileText size={14} /> },
        { id: 'turnos', label: ta('tab_turnos'), icon: <Clock size={14} /> },
        { id: 'jornadas', label: ta('tab_jornadas'), icon: <CalendarRange size={14} /> },
        { id: 'festivos', label: ta('tab_festivos'), icon: <CalendarX2 size={14} /> },
        ...(esRrhh ? [{ id: 'personas', label: ta('tab_personas'), icon: <Users size={14} /> }] : []),
        { id: 'horario', label: ta('tab_horario'), icon: <CalendarClock size={14} /> },
        { id: 'cuadrante', label: ta('tab_cuadrante'), icon: <CalendarDays size={14} /> },
        { id: 'cobertura', label: ta('tab_cobertura'), icon: <Grid3x3 size={14} /> },
        { id: 'acceso', label: ta('tab_acceso'), icon: <ShieldCheck size={14} /> },
        { id: 'ejemplos', label: ta('tab_ejemplos'), icon: <Sparkles size={14} /> },
      ]} />
      <div className="ausadm-panel">
        {tab === 'tipos' && <EditorDeTipos />}
        {tab === 'documentos' && <EditorDeDocumentos />}
        {tab === 'turnos' && <EditorDeTurnos />}
        {tab === 'jornadas' && <EditorDeJornadas puedeEditar={esRrhh} />}
        {tab === 'festivos' && <EditorDeFestivos puedeEditar={esRrhh} />}
        {tab === 'personas' && esRrhh && <PersonasYSaldos puedeEditar={esRrhh} />}
        {tab === 'horario' && <PanelDeHorario />}
        {tab === 'cuadrante' && <CuadranteDeTurnos />}
        {tab === 'cobertura' && <PanelDeCobertura />}
        {tab === 'acceso' && <AccesoEspecial puedeEditar={esAdmin} />}
        {tab === 'ejemplos' && <EjemplosDeAusencias puedeCargar={esAdmin} onIr={setTab} />}
      </div>
    </div>
  )
}
