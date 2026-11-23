/**
 * Editor de un flujo de demanda (22-11-2026): datos generales, campos, fases y
 * editor JSON avanzado. Validar llama a `POST /demand/flows/validate` (manda el
 * servidor); guardar sube la versión (`POST`/`PATCH /demand/flows`). Los
 * expedientes en curso conservan la foto del flujo con el que nacieron.
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CheckCircle2, Download, Plus, Save } from 'lucide-react'
import { Button, Checkbox, Input, Spinner, Tabs, Textarea } from '../ui'
import { demandaApi, type DefinicionDeFlujo, type ErrorDeDefinicion } from '../../services/api/demanda'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { downloadBlob, extractErr } from '../../utils/helpers'
import { useCatalogoDemanda } from './comunes'
import EditorDeCampos from './EditorDeCampos'
import EditorDeFase from './EditorDeFase'
import AccionesDeCierre from './AccionesDeCierre'
import DiagramaDeFlujoVista from './DiagramaDeFlujo'
import SimuladorDeFlujo from './SimuladorDeFlujo'
import { definicionVacia, faseNueva, leerDefinicion, mover, renombrarFase, siguienteClave, validarLocal } from './utilDemanda'
import './demanda.css'

type Seccion = 'general' | 'campos' | 'fases' | 'cierre' | 'simulador' | 'diagrama' | 'json'

export default function EditorDeFlujo({ flujoId, onVolver }: { flujoId: string | null; onVolver: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const catalogo = useCatalogoDemanda()
  const [seccion, setSeccion] = useState<Seccion>('fases')
  const [faseAbierta, setFaseAbierta] = useState('')
  const [nombre, setNombre] = useState('')
  const [activo, setActivo] = useState(true)
  const [def, setDef] = useState<DefinicionDeFlujo>(definicionVacia)
  const [id, setId] = useState<string | null>(flujoId)
  const [version, setVersion] = useState<number | null>(null)
  const [json, setJson] = useState('')
  const [errorJson, setErrorJson] = useState('')
  const [errores, setErrores] = useState<ErrorDeDefinicion[] | null>(null)
  const { data, isLoading } = useQuery({ queryKey: ['demand-flow', flujoId], queryFn: () => demandaApi.flujo(flujoId as string), enabled: !!flujoId })
  useEffect(() => {
    if (!data) return
    setNombre(data.name); setActivo(data.is_active); setVersion(data.version)
    setDef({ ...definicionVacia(), ...(data.definition || {}) })
  }, [data])
  useEffect(() => { if (seccion === 'json') { setJson(JSON.stringify(def, null, 2)); setErrorJson('') } }, [seccion]) // eslint-disable-line react-hooks/exhaustive-deps

  const onError = (e: unknown) => toast.error(extractErr(e, t('demanda.error')))
  const validar = useMutation({
    mutationFn: () => demandaApi.validarFlujo(def),
    onSuccess: r => { const e = r?.errors ?? []; setErrores(e); if (e.length === 0) toast.success(t('demanda.cfg_flujo_valido')) },
    onError,
  })
  const guardar = useMutation({
    mutationFn: () => id ? demandaApi.editarFlujo(id, { name: nombre.trim(), definition: def, is_active: activo }) : demandaApi.crearFlujo({ name: nombre.trim(), definition: def, is_active: activo }),
    onSuccess: f => {
      setId(f.id); if (f.version) setVersion(f.version)
      toast.success(t('demanda.cfg_flujo_guardado', { n: f.version ?? '' }))
      qc.invalidateQueries({ queryKey: ['demand-flows'] }); qc.invalidateQueries({ queryKey: ['demand-flow', f.id] })
    },
    onError: (e: unknown) => {
      // El servidor devuelve la lista de errores de la definición en el 422.
      const cuerpo = (e as { response?: { data?: { errors?: ErrorDeDefinicion[]; params?: { errors?: unknown }; detail?: { params?: { errors?: unknown } } } } } | null)?.response?.data
      let lista: unknown = cuerpo?.errors ?? cuerpo?.params?.errors ?? cuerpo?.detail?.params?.errors
      if (typeof lista === 'string') { try { lista = JSON.parse(lista) } catch { /* accesorio: lista de errores no legible; el aviso general sale igualmente */ lista = null } }
      if (Array.isArray(lista)) setErrores(lista as ErrorDeDefinicion[])
      onError(e)
    },
  })
  const exportar = useMutation({
    mutationFn: () => demandaApi.exportarFlujo(id as string),
    onSuccess: r => downloadBlob(new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' }), `${(nombre || 'flujo').replace(/\W+/g, '_')}.json`),
    onError,
  })
  const abrirFase = (clave: string) => { setFaseAbierta(clave); setSeccion('fases') }
  const locales = useMemo(() => validarLocal(def), [def])
  const aplicarJson = () => {
    const r = leerDefinicion(json)
    if (r.def) { setDef(r.def); setErrorJson(''); toast.success(t('demanda.cfg_json_aplicado')) } else setErrorJson(r.error || 'JSON')
  }
  const ponerFase = (i: number, f: DefinicionDeFlujo['phases'][number]) => setDef(d => ({ ...d, phases: d.phases.map((x, j) => j === i ? f : x) }))

  if (flujoId && isLoading) return <Spinner />
  const todos = [...(errores ?? []), ...locales.filter(l => !(errores ?? []).some(e => e.path === l.path && e.code === l.code))]
  return (
    <div className="u-stack-16">
      <div className="dem-fila dem-fila--entre">
        <Button variant="subtle" icon={<ArrowLeft size={13} />} onClick={onVolver}>{t('demanda.volver')}</Button>
        <span className="dem-fila">
          {version != null && <span className="plan-muted">{t('demanda.cfg_version', { n: version })}</span>}
          {id && <Button variant="secondary" icon={<Download size={13} />} loading={exportar.isPending} onClick={() => exportar.mutate()}>{t('demanda.cfg_exportar')}</Button>}
          <Button variant="secondary" icon={<CheckCircle2 size={13} />} loading={validar.isPending} onClick={() => validar.mutate()}>{t('demanda.cfg_validar')}</Button>
          <Button icon={<Save size={13} />} loading={guardar.isPending} disabled={!nombre.trim()} onClick={() => guardar.mutate()}>{t('demanda.cfg_guardar_flujo')}</Button>
        </span>
      </div>
      {errores && errores.length === 0 && locales.length === 0 && <ul className="dem-errores dem-errores--ok"><li>{t('demanda.cfg_flujo_valido')}</li></ul>}
      {todos.length > 0 && (
        <div className="ds-card u-stack-12">
          <strong>{t('demanda.cfg_errores', { n: todos.length })}</strong>
          <ul className="dem-errores">{todos.map((e, i) => <li key={i}><span className="u-mono dem-mono">{e.path}</span> — {etiquetaDeError(t, e.code)}</li>)}</ul>
        </div>
      )}
      <Tabs ariaLabel={t('demanda.pestanas')} active={seccion} onChange={s => setSeccion(s as Seccion)}
        items={[
          { id: 'general', label: t('demanda.cfg_general') },
          { id: 'campos', label: t('demanda.cfg_campos'), count: def.fields.length },
          { id: 'fases', label: t('demanda.cfg_fases'), count: def.phases.length },
          { id: 'cierre', label: t('demanda.cfg_cierre'), count: def.on_close_actions?.length || undefined },
          { id: 'simulador', label: t('demanda.cfg_simulador') },
          { id: 'diagrama', label: t('demanda.cfg_diagrama') },
          { id: 'json', label: t('demanda.cfg_json') },
        ]} />
      <div className="ds-card">
        {seccion === 'general' && (
          <div className="dem-editor">
            <Input label={t('demanda.cfg_nombre_flujo')} required value={nombre} onChange={e => setNombre(e.target.value)} />
            <Checkbox label={t('demanda.cfg_activo')} checked={activo} onChange={setActivo} />
            <p className="plan-muted">{t('demanda.cfg_versionado_ayuda')}</p>
          </div>
        )}
        {seccion === 'campos' && <EditorDeCampos def={def} catalogo={catalogo} onChange={setDef} />}
        {seccion === 'fases' && (
          <div className="dem-editor">
            {def.phases.length === 0 && <p className="plan-muted">{t('demanda.cfg_sin_fases')}</p>}
            {def.phases.map((f, i) => (
              <EditorDeFase key={i} forzarAbierta={faseAbierta === f.key} fase={f} indice={i} total={def.phases.length} def={def} catalogo={catalogo}
                onChange={n => ponerFase(i, n)}
                onBorrar={() => setDef(d => renombrarFase(d, f.key, null))}
                onMover={dir => setDef(d => ({ ...d, phases: mover(d.phases, i, dir) }))}
                onRenombrar={(de, a) => setDef(d => renombrarFase(d, de, a))} />
            ))}
            <div><Button size="sm" variant="subtle" icon={<Plus size={13} />} onClick={() => setDef(d => ({ ...d, phases: [...d.phases, faseNueva(siguienteClave('fase', d.phases.map(x => x.key)))] }))}>{t('demanda.cfg_anadir_fase')}</Button></div>
          </div>
        )}
        {seccion === 'cierre' && <AccionesDeCierre def={def} catalogo={catalogo} onChange={setDef} />}
        {seccion === 'simulador' && <SimuladorDeFlujo def={def} />}
        {seccion === 'diagrama' && <DiagramaDeFlujoVista def={def} onAbrirFase={abrirFase} />}
        {seccion === 'json' && (
          <div className="dem-editor">
            <p className="plan-muted">{t('demanda.cfg_json_ayuda')}</p>
            <Textarea aria-label={t('demanda.cfg_json')} inputClassName="u-mono dem-json" rows={22} value={json} error={errorJson || undefined} onChange={e => setJson(e.target.value)} />
            <div className="dem-acciones"><Button variant="secondary" onClick={aplicarJson}>{t('demanda.cfg_aplicar_json')}</Button></div>
          </div>
        )}
      </div>
    </div>
  )
}

function etiquetaDeError(t: ReturnType<typeof useAppT>, code: string): string {
  const clave = `demanda.err_${code}`
  const v = t(clave)
  return v === clave ? code : v
}
