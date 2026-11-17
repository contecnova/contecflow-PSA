/**
 * Tablas de referencia (p. ej. dietas por país y ciudad): lista, cabecera y
 * edición en rejilla. Importar un CSV/XLSX solo rellena la rejilla para
 * revisarla: lo que se guarda es lo que se ve.
 */
import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Plus, Save, Table2, Trash2, Upload } from 'lucide-react'
import { politicasApi } from '../../services/api'
import type { FilaDeTabla, TablaDeReferencia } from '../../services/api/tipos-politicas'
import { Button, EmptyState, Spinner, Select, TablaSimple, Pulsable } from '../ui'
import DateInput from '../ui/DateInput'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { SelectorDeMoneda, SelectorDePais, useCatalogo, useOpciones, useTextos } from './comun'

export default function EditorDeTablas() {
  const { t } = useTextos()
  const [abierta, setAbierta] = useState<string | null>(null)
  const [nueva, setNueva] = useState(false)
  const q = useQuery({ queryKey: ['politicas', 'tablas'], queryFn: politicasApi.tablas })
  if (abierta || nueva) return <Tabla id={abierta} onVolver={() => { setAbierta(null); setNueva(false) }} onCreada={setAbierta} />
  return (
    <div className="u-stack-10">
      <div className="pol-fila-fin"><Button icon={<Plus size={14} />} onClick={() => setNueva(true)}>{t('pol.nueva_tabla')}</Button></div>
      {q.isLoading ? <Spinner label={t('pol.cargando')} /> : q.isError ? <div role="alert" className="pol-error">{extractErr(q.error, t('pol.error_cargar'))}</div>
        : !(q.data ?? []).length ? <EmptyState svgIcon={<Table2 size={26} />} title={t('pol.sin_tablas')} description={t('pol.sin_tablas_texto')} />
        : (
          <div className="pol-lista">
            {(q.data ?? []).map(x => (
              <Pulsable key={x.id} className="pol-item" onClick={() => setAbierta(x.id)}>
                <span><strong>{x.nombre}</strong> <span className="pol-ayuda">{x.descripcion}</span></span>
                <span className="pol-chip">{t(`pol.valor_${x.tipo_de_valor}`)}{x.moneda ? ` · ${x.moneda}` : ''}</span>
                <span className="pol-chip">{t('pol.n_filas', { n: x.n_filas })}</span>
                <span className="pol-chip">{x.dominio ?? t('pol.todos_los_dominios')}</span>
                {x.uso && <span className="pol-chip pol-chip--publicada">{t(`pol.uso_${x.dominio}_${x.uso}`, x.uso)}</span>}
              </Pulsable>
            ))}
          </div>
        )}
    </div>
  )
}

const FILA_VACIA: FilaDeTabla = { pais: null, ciudad: null, categoria: null, valor: 0, moneda: null, vigente_desde: null, vigente_hasta: null }

function Tabla({ id, onVolver, onCreada }: { id: string | null; onVolver: () => void; onCreada: (id: string) => void }) {
  const { t } = useTextos()
  const toast = useToast()
  const qc = useQueryClient()
  const opciones = useOpciones().data
  const catalogo = useCatalogo().data
  const q = useQuery({ queryKey: ['politicas', 'tabla', id], queryFn: () => politicasApi.tabla(id as string), enabled: !!id })
  const [cab, setCab] = useState<Partial<TablaDeReferencia>>({ nombre: '', tipo_de_valor: 'importe', moneda: null, dominio: null })
  const [filas, setFilas] = useState<FilaDeTabla[]>([])
  const [errores, setErrores] = useState<{ fila: number | null; mensaje: string }[]>([])
  const fichero = useRef<HTMLInputElement>(null)
  useEffect(() => { if (q.data) { setCab(q.data); setFilas(q.data.filas ?? []) } }, [q.data])
  const refrescar = () => qc.invalidateQueries({ queryKey: ['politicas'] })
  const errDe = (e: unknown) => {
    const d = (e as { response?: { data?: { detail?: { errors?: { fila: number | null; mensaje: string }[] } } } })?.response?.data?.detail
    if (d && typeof d === 'object' && Array.isArray(d.errors)) setErrores(d.errors)
    toast.error(extractErr(e, t('pol.error_guardar')))
  }
  const guardarCab = useMutation({
    mutationFn: () => (id ? politicasApi.editarTabla(id, cab) : politicasApi.crearTabla(cab)),
    onSuccess: x => { refrescar(); toast.success(t('pol.guardada')); if (!id) onCreada(x.id) }, onError: errDe,
  })
  const guardarFilas = useMutation({
    mutationFn: () => politicasApi.guardarFilas(id as string, filas),
    onSuccess: () => { setErrores([]); refrescar(); toast.success(t('pol.filas_guardadas')) }, onError: errDe,
  })
  const importar = useMutation({
    mutationFn: (f: File) => politicasApi.importar(id as string, f),
    onSuccess: r => { setFilas(r.filas); setErrores(r.errores); toast.success(t('pol.importadas', { n: r.filas.length })) }, onError: errDe,
  })
  const borrar = useMutation({ mutationFn: () => politicasApi.borrarTabla(id as string), onSuccess: () => { refrescar(); onVolver() }, onError: errDe })
  if (id && q.isLoading) return <Spinner label={t('pol.cargando')} />
  const setFila = (i: number, f: FilaDeTabla) => setFilas(filas.map((x, j) => (j === i ? f : x)))
  const conErrores = new Set(errores.map(e => e.fila))
  const esImporte = cab.tipo_de_valor === 'importe'
  return (
    <div className="u-stack-14">
      <div className="pol-fila">
        <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={onVolver}>{t('pol.volver')}</Button>
        <span className="pol-titulo">{cab.nombre || t('pol.nueva_tabla')}</span>
        <span className="u-flex1" />
        {id && <Button variant="danger" icon={<Trash2 size={14} />}
          onClick={async () => { if (await confirmar({ title: t('pol.borrar'), danger: true, message: t('pol.borrar_tabla_confirmar') })) borrar.mutate() }}>{t('pol.borrar')}</Button>}
      </div>
      <section className="pol-tarjeta pol-grid-2" aria-label={t('pol.cabecera_de_tabla')}>
        <label><span className="pol-etiqueta">{t('pol.nombre')}</span>
          <input className="pol-campo pol-campo--ancho" required value={cab.nombre ?? ''} onChange={e => setCab({ ...cab, nombre: e.target.value })} /></label>
        <label><span className="pol-etiqueta">{t('pol.tipo_de_valor')}</span>
          <Select suelto className="pol-campo" value={cab.tipo_de_valor} onChange={e => setCab({ ...cab, tipo_de_valor: e.target.value as 'importe' | 'numero' })} placeholder={false}>
            <option value="importe">{t('pol.valor_importe')}</option><option value="numero">{t('pol.valor_numero')}</option>
          </Select></label>
        {esImporte && <label><span className="pol-etiqueta">{t('pol.moneda_por_defecto')}</span>
          <SelectorDeMoneda valor={cab.moneda} opciones={opciones} etiqueta={t('pol.moneda_por_defecto')} onChange={m => setCab({ ...cab, moneda: m })} /></label>}
        <label><span className="pol-etiqueta">{t('pol.dominio')}</span>
          <Select suelto className="pol-campo" value={cab.dominio ?? ''} onChange={e => setCab({ ...cab, dominio: e.target.value || null })} placeholder={t('pol.todos_los_dominios')}>
            {(catalogo?.dominios ?? []).map(d => <option key={d.clave} value={d.clave}>{t(`pol.dominio_${d.clave}`)}</option>)}
          </Select></label>
        {(() => {
          // Rev. 166: un uso del dominio además de las reglas (gastos: tarifa por km).
          const usos = (catalogo?.dominios ?? []).find(d => d.clave === cab.dominio)?.usos_de_tabla ?? []
          return usos.length > 0 && (
            <label><span className="pol-etiqueta">{t('pol.uso_de_tabla')}</span>
              <Select suelto className="pol-campo" aria-label={t('pol.uso_de_tabla')} value={cab.uso ?? ''} onChange={e => setCab({ ...cab, uso: e.target.value || null })} placeholder={t('pol.uso_solo_reglas')}>
                {usos.map(u => <option key={u.valor} value={u.valor}>{t(`pol.uso_${cab.dominio}_${u.valor}`, u.etiqueta)}</option>)}
              </Select></label>
          )
        })()}
        <label className="u-col-full"><span className="pol-etiqueta">{t('pol.descripcion')}</span>
          <input className="pol-campo pol-campo--ancho" value={cab.descripcion ?? ''} onChange={e => setCab({ ...cab, descripcion: e.target.value })} /></label>
        <div className="pol-fila-fin u-col-full"><Button icon={<Save size={14} />} loading={guardarCab.isPending} onClick={() => guardarCab.mutate()}>{t('pol.guardar_cabecera')}</Button></div>
      </section>
      {id && (
        <section aria-label={t('pol.filas')}>
          <div className="pol-fila">
            <h3 className="pol-titulo">{t('pol.filas')}</h3>
            <span className="pol-ayuda">{t('pol.filas_ayuda')}</span>
            <span className="u-flex1" />
            <input ref={fichero} type="file" accept=".csv,.xlsx,text/csv" className="u-sr-only" aria-label={t('pol.importar')}
              onChange={e => { const f = e.target.files?.[0]; if (f) importar.mutate(f); e.target.value = '' }} />
            <Button variant="secondary" icon={<Upload size={14} />} loading={importar.isPending} onClick={() => fichero.current?.click()}>{t('pol.importar')}</Button>
            <Button variant="secondary" icon={<Plus size={14} />} onClick={() => setFilas([...filas, { ...FILA_VACIA, moneda: cab.moneda ?? null }])}>{t('pol.anadir_fila')}</Button>
            <Button icon={<Save size={14} />} loading={guardarFilas.isPending} onClick={() => guardarFilas.mutate()}>{t('pol.guardar_filas')}</Button>
          </div>
          {errores.length > 0 && (
            <ul className="pol-errores" role="alert">{errores.map((e, i) => <li key={i}>{e.fila !== null ? t('pol.fila_n', { n: e.fila + 1 }) + ': ' : ''}{e.mensaje}</li>)}</ul>
          )}
          {filas.length === 0 ? <EmptyState title={t('pol.sin_filas')} description={t('pol.sin_filas_texto')} /> : (
            <div className="pol-rejilla-envoltura pol-mt">
              <TablaSimple claseTabla="pol-rejilla">
                <thead><tr>
                  <th scope="col">{t('pol.pais')}</th><th scope="col">{t('pol.ciudad')}</th><th scope="col">{t('pol.categoria')}</th>
                  <th scope="col">{t('pol.valor')}</th>{esImporte && <th scope="col">{t('pol.moneda')}</th>}
                  <th scope="col">{t('pol.desde')}</th><th scope="col">{t('pol.hasta')}</th><th scope="col"><span className="u-sr-only">{t('pol.acciones')}</span></th>
                </tr></thead>
                <tbody>
                  {filas.map((f, i) => (
                    <tr key={i} aria-invalid={conErrores.has(i) || undefined}>
                      <td><SelectorDePais valor={f.pais} etiqueta={t('pol.pais_fila', { n: i + 1 })} onChange={v => setFila(i, { ...f, pais: v })} /></td>
                      <td><input className="pol-campo" aria-label={t('pol.ciudad_fila', { n: i + 1 })} value={f.ciudad ?? ''} placeholder={t('pol.cualquiera')}
                        onChange={e => setFila(i, { ...f, ciudad: e.target.value || null })} /></td>
                      <td><input className="pol-campo" aria-label={t('pol.categoria_fila', { n: i + 1 })} value={f.categoria ?? ''} placeholder={t('pol.cualquiera')}
                        list="pol-categorias" onChange={e => setFila(i, { ...f, categoria: e.target.value || null })} /></td>
                      <td><input type="number" step="0.01" className="pol-campo" aria-label={t('pol.valor_fila', { n: i + 1 })} value={f.valor}
                        onChange={e => setFila(i, { ...f, valor: Number(e.target.value) })} /></td>
                      {esImporte && <td><SelectorDeMoneda valor={f.moneda ?? cab.moneda} opciones={opciones} etiqueta={t('pol.moneda_fila', { n: i + 1 })}
                        onChange={m => setFila(i, { ...f, moneda: m })} /></td>}
                      <td><DateInput className="pol-campo" aria-label={t('pol.desde_fila', { n: i + 1 })} value={f.vigente_desde ?? ''} onChange={e => setFila(i, { ...f, vigente_desde: e.target.value || null })} /></td>
                      <td><DateInput className="pol-campo" aria-label={t('pol.hasta_fila', { n: i + 1 })} value={f.vigente_hasta ?? ''} onChange={e => setFila(i, { ...f, vigente_hasta: e.target.value || null })} /></td>
                      <td><Button size="xs" variant="ghost" icon={<Trash2 size={13} />} onClick={() => setFilas(filas.filter((_, j) => j !== i))}
                        title={t('pol.quitar_fila')}><span className="u-sr-only">{t('pol.quitar_fila')}</span></Button></td>
                    </tr>
                  ))}
                </tbody>
              </TablaSimple>
              <datalist id="pol-categorias">
                {(catalogo?.dominios ?? []).flatMap(d => d.campos.filter(c => c.tipo === 'enum').flatMap(c => c.opciones))
                  .map(o => <option key={o.valor} value={o.valor}>{o.etiqueta}</option>)}
              </datalist>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
