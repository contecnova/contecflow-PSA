/**
 * Editor de una versión de política: definición y ámbito, reglas (condición,
 * resultados y bandas), simulador e historial de versiones. Solo un borrador
 * se edita; una publicada se ve y se copia como versión nueva.
 *
 * Rev. 180: el ámbito admite grupos y una sección «Excepciones» con personas y
 * grupos que quedan fuera aunque cumplan el resto del ámbito.
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowLeft, ArrowUp, CheckCircle, Copy, History, Play, Plus, Power, Save, Trash2 } from 'lucide-react'
import { politicasApi, usersApi } from '../../services/api'
import type { AmbitoDePolitica, DocumentoDePolitica, ErrorDeValidacion, Politica, Regla } from '../../services/api/tipos-politicas'
import { Button, EmptyState, Spinner, Tabs, Pulsable, Checkbox, Input } from '../ui'
import DateInput from '../ui/DateInput'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { CODIGOS_DE_PAIS } from '../../constants/paises'
import ConstructorDeCondiciones, { grupoVacio } from './ConstructorDeCondiciones'
import EditorDeResultados from './EditorDeResultados'
import EditorDeExceso from './EditorDeExceso'
import Simulador from './Simulador'
import { ListaDeValores, SelectorDeEntidad, useCatalogo, useOpciones, useTextos } from './comun'
import { Textarea } from '../ui'

const AMBITO_VACIO: AmbitoDePolitica = {
  departamentos: [], equipos: [], roles: [], ubicaciones: [], personas: [], grupos: [], excepto_personas: [], excepto_grupos: [],
}

export function documentoNuevo(dominio: string): DocumentoDePolitica {
  return { dominio, nombre: '', descripcion: '', prioridad: 100, activa: true, vigente_desde: null, vigente_hasta: null,
    ambito: AMBITO_VACIO, nota_de_version: '', reglas: [] }
}

function reglaNueva(n: number): Regla {
  return { nombre: '', activa: true, detener: false, condicion: grupoVacio(), resultados: [{ tipo: 'warn', mensaje: '' }], exceso: null, orden: n }
}

function aDocumento(p: Politica): DocumentoDePolitica {
  const { dominio, nombre, descripcion, prioridad, activa, vigente_desde, vigente_hasta, ambito, nota_de_version, reglas } = p
  return { dominio, nombre, descripcion, prioridad, activa, vigente_desde, vigente_hasta, ambito: { ...AMBITO_VACIO, ...ambito }, nota_de_version, reglas }
}

export default function EditorDePolitica({ id, nuevoDominio, onVolver, onAbrir }: {
  id: string | null; nuevoDominio: string | null; onVolver: () => void; onAbrir: (id: string) => void
}) {
  const { t } = useTextos()
  const toast = useToast()
  const qc = useQueryClient()
  const catalogo = useCatalogo()
  const detalle = useQuery({ queryKey: ['politicas', 'detalle', id], queryFn: () => politicasApi.detalle(id as string), enabled: !!id })
  const [doc, setDoc] = useState<DocumentoDePolitica | null>(nuevoDominio ? documentoNuevo(nuevoDominio) : null)
  const [errores, setErrores] = useState<ErrorDeValidacion[]>([])
  const [tab, setTab] = useState('definicion')
  useEffect(() => { if (detalle.data) setDoc(aDocumento(detalle.data)) }, [detalle.data])

  const politica = detalle.data
  const editable = !id || politica?.estado === 'borrador'
  const dominio = useMemo(() => catalogo.data?.dominios.find(d => d.clave === doc?.dominio), [catalogo.data, doc?.dominio])
  const refrescar = () => qc.invalidateQueries({ queryKey: ['politicas'] })
  const alFallar = (e: unknown) => {
    const det = (e as { response?: { data?: { detail?: { errors?: ErrorDeValidacion[] } } } })?.response?.data?.detail
    if (det && typeof det === 'object' && Array.isArray(det.errors)) setErrores(det.errors)
    toast.error(extractErr(e, t('pol.error_guardar')))
  }
  const guardar = useMutation({
    mutationFn: () => (id ? politicasApi.guardar(id, doc as DocumentoDePolitica) : politicasApi.crear(doc as DocumentoDePolitica)),
    onSuccess: p => { setErrores([]); toast.success(t('pol.guardada')); refrescar(); if (!id) onAbrir(p.id) },
    onError: alFallar,
  })
  const validar = useMutation({
    mutationFn: () => politicasApi.validar(doc as DocumentoDePolitica),
    onSuccess: r => { setErrores(r.errores); if (r.valida) toast.success(t('pol.valida')) },
    onError: alFallar,
  })
  const publicar = useMutation({ mutationFn: () => politicasApi.publicar(id as string), onSuccess: () => { toast.success(t('pol.publicada_ok')); refrescar() }, onError: alFallar })
  const nuevaVersion = useMutation({ mutationFn: () => politicasApi.nuevaVersion(id as string), onSuccess: p => { refrescar(); onAbrir(p.id) }, onError: alFallar })
  const activar = useMutation({ mutationFn: (a: boolean) => politicasApi.activar(id as string, a), onSuccess: () => refrescar(), onError: alFallar })
  const borrar = useMutation({ mutationFn: () => politicasApi.borrar(id as string), onSuccess: () => { refrescar(); onVolver() }, onError: alFallar })

  if ((id && detalle.isLoading) || catalogo.isLoading || !doc) return <Spinner label={t('pol.cargando')} />
  if (detalle.isError || catalogo.isError) return <div role="alert" className="pol-error">{extractErr(detalle.error ?? catalogo.error, t('pol.error_cargar'))}</div>
  if (!dominio) return <EmptyState title={t('pol.dominio_desconocido')} />

  const set = <K extends keyof DocumentoDePolitica>(k: K, v: DocumentoDePolitica[K]) => setDoc({ ...doc, [k]: v })
  const setRegla = (i: number, r: Regla) => set('reglas', doc.reglas.map((x, j) => (j === i ? r : x)))
  const mover = (i: number, d: -1 | 1) => {
    const r = [...doc.reglas]
    ;[r[i], r[i + d]] = [r[i + d], r[i]]
    set('reglas', r)
  }
  const errorDe = (prefijo: string) => errores.filter(e => e.ruta === prefijo || e.ruta.startsWith(`${prefijo}.`) || e.ruta.startsWith(`${prefijo}[`))

  return (
    <div className="u-stack-14">
      <div className="pol-fila">
        <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={onVolver}>{t('pol.volver')}</Button>
        <span className="pol-titulo">{doc.nombre || t('pol.politica_nueva')}</span>
        {politica && <span className={`pol-chip pol-chip--${politica.estado}`}>{t(`pol.estado_${politica.estado}`)} · v{politica.version}</span>}
        {politica && !politica.activa && <span className="pol-chip">{t('pol.desactivada')}</span>}
        <span className="u-flex1" />
        {editable && <Button variant="secondary" icon={<CheckCircle size={14} />} onClick={() => validar.mutate()} loading={validar.isPending}>{t('pol.validar')}</Button>}
        {editable && <Button icon={<Save size={14} />} onClick={() => guardar.mutate()} loading={guardar.isPending}>{t('pol.guardar_borrador')}</Button>}
        {politica?.estado === 'borrador' && (
          <Button icon={<CheckCircle size={14} />} loading={publicar.isPending}
            onClick={async () => { if (await confirmar({ title: t('pol.publicar'), message: t('pol.publicar_confirmar') })) publicar.mutate() }}>{t('pol.publicar')}</Button>
        )}
        {politica && politica.estado !== 'borrador' && <Button variant="secondary" icon={<Copy size={14} />} onClick={() => nuevaVersion.mutate()} loading={nuevaVersion.isPending}>{t('pol.nueva_version')}</Button>}
        {politica?.estado === 'publicada' && (
          <Button variant="secondary" icon={<Power size={14} />} onClick={() => activar.mutate(!politica.activa)}>{politica.activa ? t('pol.desactivar') : t('pol.activar')}</Button>
        )}
        {politica && politica.estado !== 'retirada' && (
          <Button variant="danger" icon={<Trash2 size={14} />}
            onClick={async () => { if (await confirmar({ title: t('pol.borrar'), danger: true, message: politica.estado === 'borrador' ? t('pol.borrar_borrador') : t('pol.retirar_publicada') })) borrar.mutate() }}>
            {politica.estado === 'borrador' ? t('pol.borrar') : t('pol.retirar')}
          </Button>
        )}
      </div>
      {errores.length > 0 && (
        <div className="pol-errores" role="alert">
          <strong>{t('pol.hay_errores', { n: errores.length })}</strong>
          <ul>{errores.map((e, i) => <li key={i}>{e.mensaje} <span className="pol-ayuda">({e.ruta})</span></li>)}</ul>
        </div>
      )}
      <Tabs active={tab} onChange={setTab} items={[
        { id: 'definicion', label: t('pol.tab_definicion') },
        { id: 'reglas', label: `${t('pol.tab_reglas')} · ${doc.reglas.length}` },
        { id: 'simulador', label: t('pol.tab_simulador'), icon: <Play size={14} /> },
        ...(id ? [{ id: 'historial', label: t('pol.tab_historial'), icon: <History size={14} /> }] : []),
      ]} />
      <fieldset disabled={!editable} className="ds-grupo-opciones pol-sin-borde">
        {tab === 'definicion' && <Definicion doc={doc} set={set} errorDe={errorDe} />}
        {tab === 'reglas' && (
          <div>
            {doc.reglas.length === 0 && <EmptyState title={t('pol.sin_reglas')} description={t('pol.sin_reglas_texto')} />}
            {doc.reglas.map((r, i) => (
              <section key={i} className={`pol-tarjeta${r.activa ? '' : ' pol-tarjeta--inactiva'}`} aria-label={t('pol.regla_n', { n: i + 1 })}>
                <div className="pol-fila">
                  <Input label={t('pol.regla_n', { n: i + 1 })} aria-label={t('pol.nombre_de_la_regla')} placeholder={t('pol.nombre_de_la_regla')} value={r.nombre} onChange={e => setRegla(i, { ...r, nombre: e.target.value })} />
                  <Checkbox className="pol-chip" label={t('pol.activa')} checked={r.activa} onChange={m => setRegla(i, { ...r, activa: m })} />
                  <span title={t('pol.detener_ayuda')}><Checkbox className="pol-chip" label={t('pol.detener')} checked={r.detener} onChange={m => setRegla(i, { ...r, detener: m })} /></span>
                  <Button size="xs" variant="ghost" icon={<ArrowUp size={13} />} disabled={i === 0} onClick={() => mover(i, -1)} title={t('pol.subir')}><span className="u-sr-only">{t('pol.subir')}</span></Button>
                  <Button size="xs" variant="ghost" icon={<ArrowDown size={13} />} disabled={i === doc.reglas.length - 1} onClick={() => mover(i, 1)} title={t('pol.bajar')}><span className="u-sr-only">{t('pol.bajar')}</span></Button>
                  <Button size="xs" variant="ghost" icon={<Trash2 size={13} />} onClick={() => set('reglas', doc.reglas.filter((_, j) => j !== i))} title={t('pol.quitar_regla')}><span className="u-sr-only">{t('pol.quitar_regla')}</span></Button>
                </div>
                {errorDe(`reglas[${i}]`).map((e, k) => <p key={k} className="pol-error">{e.mensaje}</p>)}
                <h4 className="pol-subtitulo">{t('pol.si_se_cumple')}</h4>
                <ConstructorDeCondiciones dominio={dominio} valor={r.condicion} onChange={c => setRegla(i, { ...r, condicion: c })} />
                <h4 className="pol-subtitulo">{t('pol.entonces')}</h4>
                <EditorDeResultados dominio={dominio} valor={r.resultados} onChange={x => setRegla(i, { ...r, resultados: x })} />
                <h4 className="pol-subtitulo">{t('pol.bandas_de_exceso')}</h4>
                <p className="pol-ayuda">{t('pol.bandas_ayuda')}</p>
                <EditorDeExceso dominio={dominio} valor={r.exceso} onChange={x => setRegla(i, { ...r, exceso: x })} />
              </section>
            ))}
            <div className="pol-fila pol-mt">
              <Button icon={<Plus size={14} />} onClick={() => set('reglas', [...doc.reglas, reglaNueva(doc.reglas.length + 1)])}>{t('pol.anadir_regla')}</Button>
            </div>
          </div>
        )}
      </fieldset>
      {tab === 'simulador' && <Simulador documento={{ ...doc, ...(politica ? { id: politica.id, familia_id: politica.familia_id } : {}) }} />}
      {tab === 'historial' && id && <Historial id={id} onAbrir={onAbrir} />}
    </div>
  )
}

function Definicion({ doc, set, errorDe }: {
  doc: DocumentoDePolitica; set: <K extends keyof DocumentoDePolitica>(k: K, v: DocumentoDePolitica[K]) => void
  errorDe: (p: string) => ErrorDeValidacion[]
}) {
  const { t, pais } = useTextos()
  const opciones = useOpciones().data
  const amb = doc.ambito
  const setAmb = (k: keyof AmbitoDePolitica, v: string[]) => set('ambito', { ...amb, [k]: v })
  const ubicaciones = [...CODIGOS_DE_PAIS, ...(opciones?.ciudades ?? [])]
  const grupos = (opciones?.grupos ?? []).map(g => g.id)
  const nombreDeGrupo = (id: string) => opciones?.grupos.find(g => g.id === id)?.nombre ?? id
  return (
    <div className="u-stack-14">
      <div className="pol-grid-2">
        <Input label={t('pol.nombre')} value={doc.nombre} aria-invalid={errorDe('nombre').length > 0} onChange={e => set('nombre', e.target.value)} required />
        <div>
          <Input label={t('pol.prioridad')} type="number" value={doc.prioridad} onChange={e => set('prioridad', Number(e.target.value))} />
          <span className="pol-ayuda"> {t('pol.prioridad_ayuda')}</span></div>
        <DateInput label={t('pol.vigente_desde')} value={doc.vigente_desde ?? ''} onChange={e => set('vigente_desde', e.target.value || null)} />
        <DateInput label={t('pol.vigente_hasta')} value={doc.vigente_hasta ?? ''} onChange={e => set('vigente_hasta', e.target.value || null)} />
      </div>
      {errorDe('vigente_hasta').map((e, i) => <p key={i} className="pol-error">{e.mensaje}</p>)}
      <Textarea label={t('pol.descripcion')} rows={2} value={doc.descripcion ?? ''} onChange={e => set('descripcion', e.target.value)} />
      <Input label={t('pol.nota_de_version')} value={doc.nota_de_version ?? ''} onChange={e => set('nota_de_version', e.target.value)} />
      <section className="pol-tarjeta" aria-labelledby="pol-ambito">
        <h3 id="pol-ambito" className="pol-titulo">{t('pol.ambito')}</h3>
        <p className="pol-ayuda">{t('pol.ambito_ayuda')}</p>
        <div className="pol-grid-2">
          <ListaDeValores etiqueta={t('pol.departamentos')} valores={amb.departamentos} opciones={opciones?.departamentos ?? []} onChange={v => setAmb('departamentos', v)} />
          <ListaDeValores etiqueta={t('pol.equipos')} valores={amb.equipos} opciones={opciones?.equipos ?? []} onChange={v => setAmb('equipos', v)} />
          <ListaDeValores etiqueta={t('pol.roles')} valores={amb.roles} opciones={opciones?.roles ?? []} onChange={v => setAmb('roles', v)} mostrar={r => t(`pol.rol_${r}`)} />
          <ListaDeValores etiqueta={t('pol.ubicaciones')} valores={amb.ubicaciones} opciones={ubicaciones} libre
            placeholder={t('pol.ubicacion_placeholder')} onChange={v => setAmb('ubicaciones', v.map(x => (x.length === 2 ? x.toUpperCase() : x)))}
            mostrar={u => (u.length === 2 ? pais(u) : u.includes('/') ? `${pais(u.split('/')[0])} / ${u.split('/')[1]}` : u)} />
          <ListaDeValores etiqueta={t('pol.grupos')} valores={amb.grupos ?? []} opciones={grupos} onChange={v => setAmb('grupos', v)} mostrar={nombreDeGrupo} />
        </div>
        <ListaDePersonas etiqueta={t('pol.personas')} anadir={t('pol.anadir_persona')} valores={amb.personas}
          onChange={v => setAmb('personas', v)} />
        <div className="pol-mt" role="group" aria-labelledby="pol-excepciones">
          <h4 id="pol-excepciones" className="pol-etiqueta">{t('pol.excepciones')}</h4>
          <p className="pol-ayuda">{t('pol.excepciones_ayuda')}</p>
          <div className="pol-grid-2">
            <ListaDeValores etiqueta={t('pol.excepto_grupos')} valores={amb.excepto_grupos ?? []} opciones={grupos}
              onChange={v => setAmb('excepto_grupos', v)} mostrar={nombreDeGrupo} />
          </div>
          <ListaDePersonas etiqueta={t('pol.excepto_personas')} anadir={t('pol.anadir_excepcion')} valores={amb.excepto_personas ?? []}
            onChange={v => setAmb('excepto_personas', v)} />
        </div>
      </section>
    </div>
  )
}

/** Personas elegidas (chips con su nombre) y el selector para añadir otra. */
function ListaDePersonas({ etiqueta, anadir, valores, onChange }: {
  etiqueta: string; anadir: string; valores: string[]; onChange: (v: string[]) => void
}) {
  const { t } = useTextos()
  const opciones = useOpciones().data
  const directorio = useQuery({ queryKey: ['users', 'directory'], queryFn: () => usersApi.directory().then(r => r.data) })
  const nombre = (id: string) => (directorio.data ?? []).find(u => u.id === id)?.full_name ?? `${id.slice(0, 8)}…`
  return (
    <div className="pol-mt">
      <span className="pol-etiqueta">{etiqueta}</span>
      <div className="pol-fila">
        {valores.map(p => <span key={p} className="pol-chip">{nombre(p)}
          <Pulsable aria-label={t('pol.quitar_valor', { valor: nombre(p) })} onClick={() => onChange(valores.filter(x => x !== p))}>×</Pulsable></span>)}
        <SelectorDeEntidad clase="usuario" valor="" opciones={opciones} etiqueta={anadir}
          onChange={v => { if (v && !valores.includes(v)) onChange([...valores, v]) }} />
      </div>
    </div>
  )
}

function Historial({ id, onAbrir }: { id: string; onAbrir: (id: string) => void }) {
  const { t } = useTextos()
  const q = useQuery({ queryKey: ['politicas', 'historial', id], queryFn: () => politicasApi.historial(id) })
  if (q.isLoading) return <Spinner label={t('pol.cargando')} />
  if (q.isError) return <div role="alert" className="pol-error">{extractErr(q.error, t('pol.error_cargar'))}</div>
  return (
    <ol className="pol-linea-tiempo" aria-label={t('pol.tab_historial')}>
      {(q.data ?? []).map(v => (
        <li key={v.id} data-estado={v.estado}>
          <Pulsable className="pol-item" onClick={() => onAbrir(v.id)} aria-current={v.id === id ? 'true' : undefined}>
            <span><strong>v{v.version}</strong> · {v.nota_de_version || t('pol.sin_nota')}
              <span className="pol-ayuda"> — {t('pol.creada_por', { quien: v.creada_por_nombre ?? '—', cuando: (v.created_at ?? '').slice(0, 16).replace('T', ' ') })}
                {v.publicada_en && ` · ${t('pol.publicada_por', { quien: v.publicada_por_nombre ?? '—', cuando: v.publicada_en.slice(0, 16).replace('T', ' ') })}`}</span></span>
            <span className={`pol-chip pol-chip--${v.estado}`}>{t(`pol.estado_${v.estado}`)}</span>
            <span className="pol-chip">{t('pol.n_reglas', { n: v.n_reglas })}</span>
            <span />
          </Pulsable>
        </li>
      ))}
    </ol>
  )
}
