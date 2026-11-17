/**
 * El cuadrante: personas × días con el turno de cada uno. Se asigna eligiendo
 * un pincel de la paleta (un turno, «Libre» o «Quitar cambio») y pulsando o
 * arrastrando sobre las celdas, o soltando un chip de la paleta sobre una
 * celda (arrastrar y soltar). Cada gesto se guarda de una vez
 * (`PUT /absences/roster`). Teclado: las celdas son botones.
 * Debajo, las rotaciones (ciclos de N días con personas y desfase).
 */
import { useEffect, useState } from 'react'
import type { DragEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, Eraser, Moon, Star, Users } from 'lucide-react'
import { ausenciasApi } from '../../../services/api/ausencias'
import type { CambioDeTurno, CeldaDeCuadrante, Cuadrante, Turno } from '../../../services/api/tipos-ausencias'
import { EmptyState, RejillaPersonaDia, Spinner, columnasDeDias, IconButton } from '../../ui'
import { useToast } from '../../../context/ToastContext'
import { useOpciones } from '../../politicas/comun'
import { AvisoDeError, Muestra, errorDe, isoDe, mesDe, useT } from './comun'
import { Filtros, Navegacion } from './MapaDeCobertura'
import EditorDeRotaciones from './EditorDeRotaciones'

type Pincel = { tipo: 'turno'; id: string } | { tipo: 'libre' } | { tipo: 'quitar' }
const TIPO_DND = 'application/x-ausencias-pincel'

function cambiosDe(pincel: Pincel, celdas: string[]): CambioDeTurno[] {
  return celdas.map(k => {
    const [user_id, fecha] = k.split('|')
    if (pincel.tipo === 'quitar') return { user_id, fecha, turno_id: null, quitar: true }
    return { user_id, fecha, turno_id: pincel.tipo === 'turno' ? pincel.id : null }
  })
}

export default function CuadranteDeTurnos() {
  const { ta } = useT()
  const opciones = useOpciones().data
  const [rango, setRango] = useState(() => mesDe(isoDe(new Date())))
  const [equipo, setEquipo] = useState('')
  const [departamento, setDepartamento] = useState('')
  const q = useQuery({
    queryKey: ['ausencias', 'cuadrante', rango.desde, rango.hasta, equipo, departamento],
    queryFn: () => ausenciasApi.cuadrante({ ...rango, equipo: equipo || undefined, departamento: departamento || undefined }),
  })
  return (
    <section aria-labelledby="ausadm-cuad-titulo" className="u-stack-10">
      <div className="ausadm-cabecera">
        <h2 id="ausadm-cuad-titulo" className="ausadm-titulo">{ta('cuadrante_titulo')}</h2>
        <Navegacion rango={rango} onCambiar={setRango} />
      </div>
      <p className="ausadm-ayuda">{ta('cuadrante_ayuda')}</p>
      <Filtros equipo={equipo} departamento={departamento} equipos={opciones?.equipos ?? []}
        departamentos={opciones?.departamentos ?? []} onEquipo={setEquipo} onDepartamento={setDepartamento} />
      {q.isLoading ? <Spinner label={ta('cargando')} />
        : q.isError ? <AvisoDeError error={q.error} defecto={ta('error_cargar')} />
        : q.data && <Rejilla datos={q.data} />}
      <EditorDeRotaciones />
    </section>
  )
}

function Rejilla({ datos }: { datos: Cuadrante }) {
  const { ta } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const [pincel, setPincel] = useState<Pincel | null>(datos.turnos[0] ? { tipo: 'turno', id: datos.turnos[0].id } : null)
  const [arrastrando, setArrastrando] = useState(false)
  const [seleccion, setSeleccion] = useState<Set<string>>(new Set())
  const turnos = new Map(datos.turnos.map(t => [t.id, t]))
  const festivos = new Map(datos.festivos.map(f => [f.fecha, f.nombre]))
  const guardar = useMutation({
    mutationFn: (cambios: CambioDeTurno[]) => ausenciasApi.cambiarCuadrante(cambios),
    onSuccess: r => { toast.success(ta('cambios_guardados', { n: r.cambios })); qc.invalidateQueries({ queryKey: ['ausencias'] }) },
    onError: e => toast.error(errorDe(e, ta('error_guardar')).mensaje),
  })
  const aplicar = (p: Pincel | null, celdas: string[]) => {
    if (!p || !celdas.length) return
    guardar.mutate(cambiosDe(p, celdas))
  }
  useEffect(() => {
    if (!arrastrando) return
    const soltar = () => {
      setArrastrando(false)
      aplicar(pincel, [...seleccion])
      setSeleccion(new Set())
    }
    window.addEventListener('mouseup', soltar)
    return () => window.removeEventListener('mouseup', soltar)
  })
  if (!datos.personas.length) return <EmptyState svgIcon={<Users size={26} />} title={ta('sin_personas')} />
  if (!datos.turnos.length) return <EmptyState svgIcon={<CalendarDays size={26} />} title={ta('sin_turnos')} description={ta('sin_turnos_texto')} />

  const nombreDePincel = (p: Pincel) => p.tipo === 'turno' ? (turnos.get(p.id)?.nombre ?? '') : ta(p.tipo === 'libre' ? 'libre' : 'quitar_cambio')
  const soltarEn = (e: DragEvent<HTMLButtonElement>, clave: string) => {
    e.preventDefault()
    try {
      const p = JSON.parse(e.dataTransfer.getData(TIPO_DND)) as Pincel
      aplicar(p, [clave])
    } catch { /* no era un chip de la paleta */ }
  }
  const textoDeCelda = (persona: string, d: string, c: CeldaDeCuadrante | undefined, t: Turno | undefined) => {
    const turno = c ? (t ? `${t.nombre} ${t.hora_inicio}–${t.hora_fin}` : ta(c.origen === 'festivo' ? 'festivo' : 'libre')) : ta('sin_cuadrante')
    const origen = c ? ta(`origen_${c.origen}`) : ''
    return `${persona}, ${d}: ${turno}${origen ? ` (${origen})` : ''}${festivos.has(d) ? ` · ${festivos.get(d)}` : ''}`
  }
  return (
    <div className="ausadm-cuadrante">
      <div className="ausadm-paleta" role="radiogroup" aria-label={ta('paleta')}>
        <span className="ausadm-etiqueta">{ta('paleta')}</span>
        {[...datos.turnos.map(t => ({ tipo: 'turno', id: t.id }) as Pincel), { tipo: 'libre' } as Pincel, { tipo: 'quitar' } as Pincel].map(p => {
          const t = p.tipo === 'turno' ? turnos.get(p.id) : undefined
          const activo = JSON.stringify(p) === JSON.stringify(pincel)
          return (
            <IconButton key={p.tipo === 'turno' ? p.id : p.tipo} role="radio" aria-checked={activo} ariaLabel={nombreDePincel(p)}
              className={`ausadm-pincel${activo ? ' ausadm-pincel--activo' : ''}`} draggable
              onDragStart={e => { e.dataTransfer.setData(TIPO_DND, JSON.stringify(p)); e.dataTransfer.effectAllowed = 'copy' }}
              onClick={() => setPincel(p)}>
              {t ? <Muestra color={t.color} className="ausadm-muestra--punto" />
                : p.tipo === 'libre' ? <Moon size={12} aria-hidden /> : <Eraser size={12} aria-hidden />}
              {nombreDePincel(p)}
              {t && <span className="ausadm-ayuda">{t.hora_inicio}–{t.hora_fin}</span>}
            </IconButton>
          )
        })}
        {guardar.isPending && <Spinner size={14} label={ta('guardando')} />}
      </div>
      <RejillaPersonaDia
        titulo={ta('cuadrante_caption')}
        cabeceraFilas={ta('persona')}
        filas={datos.personas.map(p => ({ id: p.id, nombre: p.nombre, sub: p.equipo ?? undefined }))}
        columnas={columnasDeDias(datos.desde, datos.hasta, { festivos })}
        celda={(p, col) => {
          const d = col.clave
          const clave = `${p.id}|${d}`
          const c = datos.celdas[p.id]?.[d]
          const t = c?.turno_id ? turnos.get(c.turno_id) : undefined
          const detalle = textoDeCelda(p.nombre, d, c, t)
          return {
            color: t?.color, tono: t ? undefined : c ? 'neutral' : undefined,
            tentativa: c?.origen === 'cambio', marcada: seleccion.has(clave), detalle,
            contenido: t ? t.nombre.slice(0, 1) : c ? (c.origen === 'festivo' ? <Star size={10} aria-hidden /> : <Moon size={10} aria-hidden />) : null,
            boton: {
              onMouseDown: e => { if (e.button === 0) { setArrastrando(true); setSeleccion(new Set([clave])) } },
              onMouseEnter: () => { if (arrastrando) setSeleccion(s => new Set(s).add(clave)) },
              onKeyDown: e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); aplicar(pincel, [clave]) } },
              onDragOver: e => { if (e.dataTransfer.types.includes(TIPO_DND)) e.preventDefault() },
              onDrop: e => soltarEn(e, clave),
            },
          }
        }}
        leyenda={[
          ...datos.turnos.map(t => ({ clave: t.id, etiqueta: `${t.nombre} ${t.hora_inicio}–${t.hora_fin}`, color: t.color })),
          { clave: 'libre', etiqueta: ta('libre'), tono: 'neutral' as const },
          { clave: 'cambio', etiqueta: ta('origen_cambio'), tono: 'vacio' as const, tentativa: true },
        ]}
      />
    </div>
  )
}
