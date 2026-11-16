/**
 * Mapa de calor de cobertura: una fila por turno, una columna por día. Cada
 * celda dice disponibles / requeridas y se colorea por estado (bien, justo,
 * falta gente). `MapaDeCobertura` pinta unos datos; `PanelDeCobertura` los
 * pide con su rango y filtros.
 */
import { fmtMonth } from '../../../utils/helpers'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Grid3x3 } from 'lucide-react'
import { ausenciasApi } from '../../../services/api/ausencias'
import type { Cobertura, CeldaDeCobertura } from '../../../services/api/tipos-ausencias'
import { Button, EmptyState, Spinner } from '../../ui'
import { useOpciones } from '../../politicas/comun'
import { AvisoDeError, Muestra, diaDeLaSemana, isoDe, mesDe, useT } from './comun'

export function MapaDeCobertura({ datos, resaltar }: { datos: Cobertura; resaltar?: Set<string> }) {
  const { ta } = useT()
  const dias: string[] = []
  for (let d = new Date(`${datos.desde}T00:00:00`); isoDe(d) <= datos.hasta; d.setDate(d.getDate() + 1)) dias.push(isoDe(d))
  const celdas = new Map(datos.celdas.map(c => [`${c.fecha}|${c.turno_id}`, c]))
  const festivos = new Map(datos.festivos.map(f => [f.fecha, f.nombre]))
  if (!datos.turnos.length) return <EmptyState svgIcon={<Grid3x3 size={26} />} title={ta('sin_turnos')} description={ta('sin_turnos_texto')} />
  const texto = (c: CeldaDeCobertura, turno: string) => [
    `${turno} · ${c.fecha}`,
    ta('cobertura_celda', { disp: c.disponibles, req: c.requeridas, asig: c.asignadas }),
    c.ausentes_nombres.length ? `${ta('ausentes')}: ${c.ausentes_nombres.join(', ')}` : '',
    c.pendientes_nombres.length ? `${ta('pendientes_o_espera')}: ${c.pendientes_nombres.join(', ')}` : '',
    c.con_esta != null ? ta('con_esta', { n: c.con_esta }) : '',
  ].filter(Boolean).join('. ')
  return (
    <div className="ausadm-mapa">
      <div className="ausadm-tabla-scroll">
        <table className="ausadm-tabla ausadm-tabla--mapa">
          <caption className="u-sr-only">{ta('cobertura_caption')}</caption>
          <thead>
            <tr>
              <th scope="col">{ta('turno')}</th>
              {dias.map(d => (
                <th key={d} scope="col" className={festivos.has(d) ? 'ausadm-festivo' : diaDeLaSemana(d) > 5 ? 'ausadm-finde' : undefined}
                  title={festivos.get(d)}>
                  <span className="ausadm-dia-semana">{ta(`dia_corto_${diaDeLaSemana(d)}`)}</span>{Number(d.slice(8))}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {datos.turnos.map(t => (
              <tr key={t.id}>
                <th scope="row"><Muestra color={t.color} className="ausadm-muestra--punto" /> {t.nombre}</th>
                {dias.map(d => {
                  const c = celdas.get(`${d}|${t.id}`)
                  if (!c) return <td key={d} className="ausadm-mapa-celda ausadm-mapa-celda--vacia" aria-label={`${t.nombre} · ${d}: —`}>·</td>
                  const etiqueta = texto(c, t.nombre)
                  const mio = resaltar?.has(`${d}|${t.id}`)
                  return (
                    <td key={d} className={`ausadm-mapa-celda ausadm-mapa-celda--${c.estado}${mio ? ' ausadm-mapa-celda--mia' : ''}`}
                      title={etiqueta} aria-label={etiqueta} tabIndex={0}>
                      {c.con_esta != null && mio ? c.con_esta : c.disponibles}<span className="ausadm-mapa-req">/{c.requeridas}</span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="ausadm-leyenda" aria-label={ta('leyenda')}>
        {(['ok', 'justo', 'falta'] as const).map(e => (
          <li key={e}><span className={`ausadm-mapa-celda ausadm-mapa-celda--${e} ausadm-leyenda-muestra`} aria-hidden />{ta(`estado_${e}`)}</li>
        ))}
        <li className="ausadm-ayuda">{ta('leyenda_numeros')}</li>
      </ul>
    </div>
  )
}

/** Mes navegable con filtros de equipo y departamento. */
export function PanelDeCobertura() {
  const { ta } = useT()
  const opciones = useOpciones().data
  const [rango, setRango] = useState(() => mesDe(isoDe(new Date())))
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
        <Navegacion rango={rango} onCambiar={setRango} />
      </div>
      <Filtros equipo={equipo} departamento={departamento} equipos={opciones?.equipos ?? []}
        departamentos={opciones?.departamentos ?? []} onEquipo={setEquipo} onDepartamento={setDepartamento} />
      {q.isLoading ? <Spinner label={ta('cargando')} />
        : q.isError ? <AvisoDeError error={q.error} defecto={ta('error_cargar')} />
        : q.data && <MapaDeCobertura datos={q.data} />}
    </section>
  )
}

export function Navegacion({ rango, onCambiar }: { rango: { desde: string; hasta: string }; onCambiar: (r: { desde: string; hasta: string }) => void }) {
  const { ta } = useT()
  const etiqueta = fmtMonth(new Date(`${rango.desde}T00:00:00`))
  return (
    <div className="ausadm-fila" role="group" aria-label={ta('mes')}>
      <Button size="xs" variant="ghost" icon={<ChevronLeft size={14} />} title={ta('mes_anterior')}
        onClick={() => onCambiar(mesDe(rango.desde, -1))}><span className="u-sr-only">{ta('mes_anterior')}</span></Button>
      <span className="ausadm-mes" aria-live="polite">{etiqueta}</span>
      <Button size="xs" variant="ghost" icon={<ChevronRight size={14} />} title={ta('mes_siguiente')}
        onClick={() => onCambiar(mesDe(rango.desde, 1))}><span className="u-sr-only">{ta('mes_siguiente')}</span></Button>
    </div>
  )
}

export function Filtros({ equipo, departamento, equipos, departamentos, onEquipo, onDepartamento }: {
  equipo: string; departamento: string; equipos: string[]; departamentos: string[]
  onEquipo: (v: string) => void; onDepartamento: (v: string) => void
}) {
  const { ta } = useT()
  return (
    <div className="ausadm-fila ausadm-filtros">
      <select className="ausadm-campo" aria-label={ta('equipo')} value={equipo} onChange={e => onEquipo(e.target.value)}>
        <option value="">{ta('todos_los_equipos')}</option>
        {equipos.map(x => <option key={x} value={x}>{x}</option>)}
      </select>
      <select className="ausadm-campo" aria-label={ta('departamento')} value={departamento} onChange={e => onDepartamento(e.target.value)}>
        <option value="">{ta('todos_los_departamentos')}</option>
        {departamentos.map(x => <option key={x} value={x}>{x}</option>)}
      </select>
    </div>
  )
}

export default MapaDeCobertura
