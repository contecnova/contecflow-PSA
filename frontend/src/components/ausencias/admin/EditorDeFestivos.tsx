/**
 * Festivos de la empresa por sede (rev. 180). Un festivo con sede vale solo
 * para quien trabaja en esa sede; sin sede ni ámbito, para toda la empresa.
 * Cuentan en el horario efectivo, en los días laborables de una ausencia y en
 * la cobertura. (Los festivos de los calendarios de SLA son otra cosa.)
 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarX2, Pencil, Plus, Trash2 } from 'lucide-react'
import { ausenciasApi } from '../../../services/api/ausencias'
import type { Festivo, FestivoIn, TipoDeFestivo } from '../../../services/api/tipos-ausencias'
import { Button, EmptyState, Modal, Spinner, Select, TablaSimple , useErroresDeCampo } from '../../ui'
import DateInput from '../../ui/DateInput'
import { confirmar } from '../../../context/ConfirmContext'
import { useToast } from '../../../context/ToastContext'
import { fecha } from '../comun'
import { AvisoDeError, ErrorDeCampo, hayDeCampo, errorDe, useT } from './comun'
import { useOficinas } from './EditorDeTurnos'

const TIPOS: TipoDeFestivo[] = ['public', 'regional', 'company']
/** Filtro de sede: todas, solo los de toda la empresa, o una sede. */
const TODAS = ''
const EMPRESA = '__empresa'

export default function EditorDeFestivos({ puedeEditar }: { puedeEditar: boolean }) {
  const { ta } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const oficinas = useOficinas().data ?? []
  const [sede, setSede] = useState(TODAS)
  const [anio, setAnio] = useState(() => String(new Date().getFullYear()))
  const [abierto, setAbierto] = useState<{ id: string | null; datos: FestivoIn } | null>(null)
  const q = useQuery({ queryKey: ['ausencias', 'festivos'], queryFn: () => ausenciasApi.festivos() })
  const borrar = useMutation({
    mutationFn: (id: string) => ausenciasApi.borrarFestivo(id),
    onSuccess: () => { toast.success(ta('borrado')); qc.invalidateQueries({ queryKey: ['ausencias'] }) },
    onError: e => toast.error(errorDe(e, ta('error_guardar')).mensaje),
  })
  const anios = useMemo(() => [...new Set((q.data ?? []).map(f => f.date.slice(0, 4)))].sort(), [q.data])
  const lista = useMemo(() => (q.data ?? [])
    .filter(f => !anio || f.date.startsWith(anio))
    .filter(f => sede === TODAS || (sede === EMPRESA ? !f.office_id : f.office_id === sede))
    .sort((a, b) => a.date.localeCompare(b.date)), [q.data, anio, sede])
  const nombreDeSede = (id: string | null) => (id ? oficinas.find(o => o.id === id)?.name ?? '—' : ta('toda_la_empresa'))
  const nuevo = (): FestivoIn => ({ name: '', date: '', type: 'public', applies_to: null, office_id: sede && sede !== EMPRESA ? sede : null })

  if (q.isLoading) return <Spinner label={ta('cargando')} />
  if (q.isError) return <AvisoDeError error={q.error} defecto={ta('error_cargar')} />
  return (
    <section aria-labelledby="ausadm-festivos-titulo" className="u-stack-10">
      <div className="ausadm-cabecera">
        <h2 id="ausadm-festivos-titulo" className="ausadm-titulo">{ta('festivos_titulo')}</h2>
        {puedeEditar && <Button icon={<Plus size={14} />} onClick={() => setAbierto({ id: null, datos: nuevo() })}>{ta('nuevo_festivo')}</Button>}
      </div>
      <p className="ausadm-ayuda">{ta('festivos_ayuda')}</p>
      <div className="ds-toolbar ausadm-filtros">
        <Select suelto className="ds-input ausadm-filtro" aria-label={ta('sede')} value={sede} onChange={e => setSede(e.target.value)} placeholder={ta('todas_las_sedes')}>
          <option value={EMPRESA}>{ta('toda_la_empresa')}</option>
          {oficinas.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
        </Select>
        <Select suelto className="ds-input ausadm-filtro" aria-label={ta('anio')} value={anio} onChange={e => setAnio(e.target.value)} placeholder={ta('todos_los_anios')}>
          {[...new Set([...anios, anio].filter(Boolean))].sort().map(y => <option key={y} value={y}>{y}</option>)}
        </Select>
      </div>
      {lista.length === 0
        ? <EmptyState svgIcon={<CalendarX2 size={26} />} title={ta('sin_festivos')} description={ta('sin_festivos_texto')}
            ctaLabel={puedeEditar ? ta('nuevo_festivo') : undefined} onCta={puedeEditar ? () => setAbierto({ id: null, datos: nuevo() }) : undefined} />
        : (
          <TablaSimple claseTabla="aus-tabla">
            <caption className="u-sr-only">{ta('festivos_titulo')}</caption>
            <thead><tr>
              <th scope="col">{ta('fecha')}</th><th scope="col">{ta('nombre')}</th><th scope="col">{ta('tipo_festivo')}</th>
              <th scope="col">{ta('sede')}</th><th scope="col">{ta('ambito')}</th>
              {puedeEditar && <th scope="col"><span className="u-sr-only">{ta('acciones')}</span></th>}
            </tr></thead>
            <tbody>
              {lista.map(f => (
                <tr key={f.id}>
                  <td>{fecha(f.date)}</td><td>{f.name}</td><td>{ta(`festivo_${f.type}`)}</td>
                  <td>{nombreDeSede(f.office_id)}</td><td>{f.applies_to || '—'}</td>
                  {puedeEditar && (
                    <td className="aus-acciones-fila">
                      <Button size="xs" variant="ghost" icon={<Pencil size={12} />} onClick={() => setAbierto({ id: f.id, datos: aEntrada(f) })}>{ta('editar')}</Button>
                      <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} loading={borrar.isPending && borrar.variables === f.id}
                        onClick={async () => { if (await confirmar({ title: ta('borrar'), danger: true, message: ta('borrar_festivo_confirmar', { nombre: f.name }) })) borrar.mutate(f.id) }}>
                        {ta('borrar')}</Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        )}
      {abierto && <FormularioDeFestivo key={abierto.id ?? 'nuevo'} id={abierto.id} inicial={abierto.datos} onCerrar={() => setAbierto(null)} />}
    </section>
  )
}

function aEntrada(f: Festivo): FestivoIn {
  return { name: f.name, date: f.date, type: f.type, applies_to: f.applies_to ?? null, office_id: f.office_id ?? null }
}

function FormularioDeFestivo({ id, inicial, onCerrar }: { id: string | null; inicial: FestivoIn; onCerrar: () => void }) {
  const { ta } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const oficinas = useOficinas().data ?? []
  const [d, setD] = useState(inicial)
  const campos = useErroresDeCampo()
  const cambiar = (c: Partial<FestivoIn>) => { Object.keys(c).forEach(k => campos.limpiar(k)); setD(x => ({ ...x, ...c })) }
  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    onError: e => { campos.recoger(e) },
    mutationFn: () => (id ? ausenciasApi.guardarFestivo(id, d) : ausenciasApi.crearFestivo(d)),
    onSuccess: () => { toast.success(ta('guardado')); qc.invalidateQueries({ queryKey: ['ausencias'] }); onCerrar() },
  })
  return (
    <Modal open onClose={onCerrar} title={id ? ta('editar_festivo') : ta('nuevo_festivo')}>
      <form className="ausadm-form" onSubmit={e => { e.preventDefault(); if (d.name && d.date) guardar.mutate() }}>
        <div className="ausadm-grid-2">
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('nombre')}</span>
            <input aria-label={ta('nombre')} className="ausadm-campo" required value={d.name} onChange={e => cambiar({ name: e.target.value })} />
            <ErrorDeCampo texto={campos.de('name')} />
          </label>
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('fecha')}</span>
            <DateInput aria-label={ta('fecha')} className="ausadm-campo" required value={d.date} onChange={e => cambiar({ date: e.target.value })} />
            <ErrorDeCampo texto={campos.de('date')} />
          </label>
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('tipo_festivo')}</span>
            <Select suelto className="ausadm-campo" value={d.type} placeholder={false} onChange={e => cambiar({ type: e.target.value })}>
              {TIPOS.map(x => <option key={x} value={x}>{ta(`festivo_${x}`)}</option>)}
            </Select>
            <ErrorDeCampo texto={campos.de('type')} />
          </label>
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('sede')}</span>
            <Select suelto className="ausadm-campo" value={d.office_id ?? ''} onChange={e => cambiar({ office_id: e.target.value || null })} placeholder={ta('toda_la_empresa')}>
              {oficinas.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
            <ErrorDeCampo texto={campos.de('office_id')} />
          </label>
        </div>
        <label className="ausadm-campo-con-etiqueta">
          <span className="ausadm-etiqueta">{ta('ambito_opcional')}</span>
          <input aria-label={ta('ambito_opcional')} className="ausadm-campo" value={d.applies_to ?? ''} aria-describedby="ausadm-festivo-ambito"
            onChange={e => cambiar({ applies_to: e.target.value || null })} />
          <span id="ausadm-festivo-ambito" className="ausadm-ayuda">{ta('festivo_ambito_ayuda')}</span>
          <ErrorDeCampo texto={campos.de('applies_to')} />
        </label>
        <AvisoDeError error={hayDeCampo(campos) ? null : guardar.error} defecto={ta('error_guardar')} />
        <div className="ausadm-acciones">
          <Button variant="secondary" onClick={onCerrar}>{ta('cancelar')}</Button>
          <Button type="submit" loading={guardar.isPending}>{ta('guardar')}</Button>
        </div>
      </form>
    </Modal>
  )
}
