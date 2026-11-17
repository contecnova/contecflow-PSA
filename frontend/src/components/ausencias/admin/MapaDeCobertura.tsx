/**
 * Mapa de calor de cobertura: una fila por turno, una columna por día. Cada
 * celda dice disponibles / requeridas y se colorea por estado (bien, justo,
 * falta gente). `MapaDeCobertura` pinta unos datos; `PanelDeCobertura` los
 * pide con su rango y filtros.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Grid3x3 } from 'lucide-react'
import { ausenciasApi } from '../../../services/api/ausencias'
import type { Cobertura, CeldaDeCobertura } from '../../../services/api/tipos-ausencias'
import { EmptyState, NavegadorDeMes, RejillaPersonaDia, Spinner, columnasDeDias, Select } from '../../ui'
import { useOpciones } from '../../politicas/comun'
import { AvisoDeError, Muestra, isoDe, mesDe, useT } from './comun'

/** 16-11-2026: pinta con la rejilla única del kit (RejillaPersonaDia). */
export function MapaDeCobertura({ datos, resaltar }: { datos: Cobertura; resaltar?: Set<string> }) {
  const { ta } = useT()
  const festivos = new Map(datos.festivos.map(f => [f.fecha, f.nombre]))
  const celdas = new Map(datos.celdas.map(c => [`${c.fecha}|${c.turno_id}`, c]))
  if (!datos.turnos.length) return <EmptyState svgIcon={<Grid3x3 size={26} />} title={ta('sin_turnos')} description={ta('sin_turnos_texto')} />
  const turnos = new Map(datos.turnos.map(t => [t.id, t]))
  const texto = (c: CeldaDeCobertura, turno: string) => [
    `${turno} · ${c.fecha}`,
    ta('cobertura_celda', { disp: c.disponibles, req: c.requeridas, asig: c.asignadas }),
    c.ausentes_nombres.length ? `${ta('ausentes')}: ${c.ausentes_nombres.join(', ')}` : '',
    c.pendientes_nombres.length ? `${ta('pendientes_o_espera')}: ${c.pendientes_nombres.join(', ')}` : '',
    c.con_esta != null ? ta('con_esta', { n: c.con_esta }) : '',
  ].filter(Boolean).join('. ')
  return (
    <RejillaPersonaDia
      titulo={ta('cobertura_caption')}
      cabeceraFilas={ta('turno')}
      filas={datos.turnos.map(t => ({ id: t.id, nombre: t.nombre, sub: `${t.hora_inicio}–${t.hora_fin}`, marca: <Muestra color={t.color} className="ausadm-muestra--punto" /> }))}
      columnas={columnasDeDias(datos.desde, datos.hasta, { festivos })}
      celda={(fila, col) => {
        const c = celdas.get(`${col.clave}|${fila.id}`)
        if (!c) return { tono: 'vacio', detalle: `${fila.nombre} · ${col.clave}: —` }
        const mio = resaltar?.has(`${col.clave}|${fila.id}`)
        return {
          estado: c.estado, marcada: mio,
          contenido: `${c.con_esta != null && mio ? c.con_esta : c.disponibles}/${c.requeridas}`,
          detalle: texto(c, turnos.get(fila.id)?.nombre ?? fila.nombre),
        }
      }}
      leyenda={(['ok', 'justo', 'falta'] as const).map(e => ({ clave: e, etiqueta: ta(`estado_${e}`), tono: e === 'ok' ? 'success' : e === 'justo' ? 'warning' : 'danger' }))}
      notaLeyenda={ta('leyenda_numeros')}
    />
  )
}

/** Mes navegable con filtros de equipo y departamento. */
export function PanelDeCobertura({ mes }: {
  /** Mes que fija quien lo contiene (con su propio navegador); sin él, el panel lleva el suyo. */
  mes?: Date
} = {}) {
  const { ta } = useT()
  const opciones = useOpciones().data
  const [rangoPropio, setRango] = useState(() => mesDe(isoDe(new Date())))
  const rango = mes ? mesDe(isoDe(mes)) : rangoPropio
  const [equipo, setEquipo] = useState('')
  const [departamento, setDepartamento] = useState('')
  const q = useQuery({
    queryKey: ['ausencias', 'cobertura', rango.desde, rango.hasta, equipo, departamento],
    queryFn: () => ausenciasApi.cobertura({ ...rango, equipo: equipo || undefined, departamento: departamento || undefined }),
  })
  return (
    <section aria-labelledby="ausadm-cob-titulo">
      <div className="ausadm-cabecera">
        <h2 id="ausadm-cob-titulo" className="ausadm-titulo">{ta('cobertura_titulo')}</h2>
        {!mes && <Navegacion rango={rango} onCambiar={setRango} />}
      </div>
      <Filtros equipo={equipo} departamento={departamento} equipos={opciones?.equipos ?? []}
        departamentos={opciones?.departamentos ?? []} onEquipo={setEquipo} onDepartamento={setDepartamento} />
      {q.isLoading ? <Spinner label={ta('cargando')} />
        : q.isError ? <AvisoDeError error={q.error} defecto={ta('error_cargar')} />
        : q.data && <MapaDeCobertura datos={q.data} />}
    </section>
  )
}

/** Navegador de mes sobre un rango {desde, hasta}: el común del kit. */
export function Navegacion({ rango, onCambiar }: { rango: { desde: string; hasta: string }; onCambiar: (r: { desde: string; hasta: string }) => void }) {
  return <NavegadorDeMes mes={new Date(`${rango.desde}T00:00:00`)} onCambiar={d => onCambiar(mesDe(isoDe(d)))} />
}

export function Filtros({ equipo, departamento, equipos, departamentos, onEquipo, onDepartamento }: {
  equipo: string; departamento: string; equipos: string[]; departamentos: string[]
  onEquipo: (v: string) => void; onDepartamento: (v: string) => void
}) {
  const { ta } = useT()
  return (
    <div className="ds-toolbar ausadm-filtros">
      <Select suelto className="ds-input ausadm-filtro" aria-label={ta('equipo')} value={equipo} onChange={e => onEquipo(e.target.value)} placeholder={ta('todos_los_equipos')}>
        {equipos.map(x => <option key={x} value={x}>{x}</option>)}
      </Select>
      <Select suelto className="ds-input ausadm-filtro" aria-label={ta('departamento')} value={departamento} onChange={e => onDepartamento(e.target.value)} placeholder={ta('todos_los_departamentos')}>
        {departamentos.map(x => <option key={x} value={x}>{x}</option>)}
      </Select>
    </div>
  )
}

export default MapaDeCobertura
