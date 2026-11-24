/**
 * Programas de certificación (§3.2 y §4): lista, alta manual (marcos objetivo) y generación
 * desde plantilla con sus parámetros de alcance (sedes, OT, cotización, nivel TISAX, SL
 * objetivo, NIS2, prototipos, producto). Generar crea programa, proyecto con tareas RACI,
 * declaración de aplicabilidad, enlaces tarea↔control y documentos con aprobación.
 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileDown, Gauge, Plus, Wand2 } from 'lucide-react'
import { Button, Checkbox, DateInput, Input, Modal, Segmentado, SelectRico, Switch, Tabla } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import { useListaDeUsuarios } from '../../hooks/useListas'
import { CLAVES_CERT, certApi } from '../../services/api/certificaciones'
import type { Plantilla, Programa } from '../../services/api/certificaciones'
import { Estado, descargarJson } from './comun'

const ESTADOS = ['borrador', 'en_curso', 'certificado', 'suspendido', 'cerrado']

export default function ProgramasCert({ onElegir }: { onElegir: (id: string) => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { puede } = useAuth()
  const gestionar = puede('certificaciones.gestionar')
  const auditar = puede('certificaciones.auditar')
  const { data: programas = [], isLoading } = useQuery({ queryKey: CLAVES_CERT.programas, queryFn: certApi.programas })
  const [nuevo, setNuevo] = useState<'manual' | 'plantilla' | null>(null)
  const refrescar = () => qc.invalidateQueries({ queryKey: CLAVES_CERT.todo })
  const medir = useMutation({
    mutationFn: (id: string) => certApi.medir(id),
    onSuccess: r => { refrescar(); toast.success(t('cert.medido', { n: r.medidas, e: r.evidencias_sistema + r.evidencias_tarea })) },
    onError: e => toast.error(extractErr(e)),
  })
  const paquete = useMutation({
    mutationFn: (p: Programa) => certApi.paquete(p.id).then(d => ({ p, d })),
    onSuccess: ({ p, d }) => { descargarJson(`${p.codigo}-paquete-auditor.json`, d); toast.success(t('cert.paquete_generado')) },
    onError: e => toast.error(extractErr(e)),
  })
  const estado = useMutation({
    mutationFn: ({ id, valor }: { id: string; valor: string }) => certApi.editarPrograma(id, { estado: valor }),
    onSuccess: refrescar, onError: e => toast.error(extractErr(e)),
  })

  return (
    <div className="u-stack-12">
      {gestionar && (
        <div className="cert-acciones">
          <Button icon={<Wand2 size={14} />} onClick={() => setNuevo('plantilla')}>{t('cert.desde_plantilla')}</Button>
          <Button variant="secondary" icon={<Plus size={14} />} onClick={() => setNuevo('manual')}>{t('cert.programa_nuevo')}</Button>
        </div>
      )}
      <Tabla<Programa> etiqueta={t('cert.programas')} filas={programas} cargando={isLoading} ordenable
        onFila={p => onElegir(p.id)}
        vacio={{ titulo: t('cert.sin_programas'), descripcion: t('cert.sin_programas_desc') }}
        columnas={[
          { key: 'codigo', label: t('cert.codigo'), cabeceraDeFila: true },
          { key: 'nombre', label: t('cert.nombre'), render: (_v, p) => (
            <div className="cert-celda"><span>{p.nombre}</span>
              <span className="cert-apagado">{p.objetivos.map(o => t(`cert.marco_${o.marco}`) + (o.nivel ? ` ${o.nivel}` : '')).join(' · ')}</span></div>) },
          { key: 'estado', label: t('cert.estado'), render: (_v, p) => (gestionar
            ? <SelectRico aria-label={t('cert.estado')} valor={p.estado} onChange={v => estado.mutate({ id: p.id, valor: v })}
                opciones={ESTADOS.map(e => ({ valor: e, etiqueta: t(`cert.estado_${e}`) }))} />
            : <Estado valor={p.estado} />) },
          { key: 'responsable', label: t('cert.responsable'), render: (_v, p) => p.responsable || '—' },
          { key: 'fecha_objetivo', label: t('cert.fecha_objetivo'), render: (_v, p) => fmtDate(p.fecha_objetivo) },
          { key: 'acciones', label: t('cert.acciones'), sortable: false, render: (_v, p) => (
            <div className="cert-acciones">
              {gestionar && <Button size="sm" variant="secondary" icon={<Gauge size={14} />} loading={medir.isPending}
                onClick={() => medir.mutate(p.id)}>{t('cert.medir')}</Button>}
              {auditar && <Button size="sm" variant="secondary" icon={<FileDown size={14} />} loading={paquete.isPending}
                onClick={() => paquete.mutate(p)}>{t('cert.paquete')}</Button>}
            </div>) },
        ]} />
      {nuevo === 'manual' && <NuevoPrograma onClose={() => setNuevo(null)} onHecho={id => { setNuevo(null); refrescar(); onElegir(id) }} />}
      {nuevo === 'plantilla' && <DesdePlantilla onClose={() => setNuevo(null)} onHecho={id => { setNuevo(null); refrescar(); onElegir(id) }} />}
    </div>
  )
}

function NuevoPrograma({ onClose, onHecho }: { onClose: () => void; onHecho: (id: string) => void }) {
  const t = useAppT()
  const toast = useToast()
  const { data: marcos = [] } = useQuery({ queryKey: CLAVES_CERT.marcos, queryFn: certApi.marcos })
  const [nombre, setNombre] = useState('')
  const [elegidos, setElegidos] = useState<string[]>([])
  const crear = useMutation({
    mutationFn: () => certApi.crearPrograma({ nombre, objetivos: elegidos.map(m => ({ marco: m })) }),
    onSuccess: p => { toast.success(t('cert.programa_creado', { codigo: p.codigo })); onHecho(p.id) },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <Modal open title={t('cert.programa_nuevo')} onClose={onClose} size="md" cambiosSinGuardar={!!nombre}>
      <div className="u-stack-12">
        <Input label={t('cert.nombre')} value={nombre} onChange={e => setNombre(e.target.value)} required />
        <fieldset className="ds-grupo-opciones u-stack-6">
          <legend>{t('cert.marcos_objetivo')}</legend>
          {marcos.map(m => (
            <Checkbox key={m.clave} checked={elegidos.includes(m.clave)} label={`${m.nombre}${m.version ? ` (${m.version})` : ''}`}
              onChange={v => setElegidos(x => (v ? [...x, m.clave] : x.filter(y => y !== m.clave)))} />
          ))}
        </fieldset>
        <div className="cert-acciones">
          <Button disabled={!nombre.trim() || !elegidos.length} loading={crear.isPending} onClick={() => crear.mutate()}>
            {t('cert.crear')}</Button>
          <Button variant="secondary" onClick={onClose}>{t('cert.cancelar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function DesdePlantilla({ onClose, onHecho }: { onClose: () => void; onHecho: (id: string) => void }) {
  const t = useAppT()
  const toast = useToast()
  const { data: plantillas = [] } = useQuery({ queryKey: CLAVES_CERT.plantillas, queryFn: certApi.plantillas })
  const { data: usuarios = [] } = useListaDeUsuarios()
  const [clave, setClave] = useState('')
  const [nombre, setNombre] = useState('')
  const [empresa, setEmpresa] = useState('')
  const [inicio, setInicio] = useState('')
  const [responsable, setResponsable] = useState('')
  const [patrocinador, setPatrocinador] = useState('')
  const [valores, setValores] = useState<Record<string, unknown>>({})
  const plantilla: Plantilla | undefined = plantillas.find(p => p.clave === clave)
  const params = useMemo(() => {
    const salida: Record<string, unknown> = {}
    for (const p of plantilla?.parametros ?? []) salida[p.clave] = valores[p.clave] ?? p.por_defecto
    return salida
  }, [plantilla, valores])
  const personas = [{ valor: '', etiqueta: t('cert.sin_asignar') },
    ...usuarios.map(u => ({ valor: u.id, etiqueta: u.full_name }))]
  const generar = useMutation({
    mutationFn: () => certApi.desdePlantilla({
      plantilla: clave, nombre: nombre || undefined, parametros: params, empresa: empresa || undefined,
      fecha_inicio: inicio || undefined, responsable_id: responsable || undefined, patrocinador_id: patrocinador || undefined,
    }),
    onSuccess: r => {
      toast.success(t('cert.generado', { codigo: r.programa.codigo, proyecto: r.project_code, tareas: r.tareas,
        documentos: r.documentos }))
      onHecho(r.programa.id)
    },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <Modal open title={t('cert.desde_plantilla')} subtitle={t('cert.desde_plantilla_ayuda')} onClose={onClose} size="lg"
      cambiosSinGuardar={!!clave}>
      <div className="u-stack-12">
        <SelectRico label={t('cert.plantilla')} valor={clave} onChange={setClave} opciones={[
          { valor: '', etiqueta: t('cert.elige_plantilla') },
          ...plantillas.map(p => ({ valor: p.clave, etiqueta: t('cert.plantilla_resumen', { nombre: p.nombre, tareas: p.tareas,
            documentos: p.documentos }) })),
        ]} />
        {plantilla && (
          <>
            <div className="cert-rejilla">
              <Input label={t('cert.nombre')} value={nombre} placeholder={plantilla.nombre} onChange={e => setNombre(e.target.value)} />
              <Input label={t('cert.empresa_en_documentos')} value={empresa} onChange={e => setEmpresa(e.target.value)} />
              <DateInput label={t('cert.fecha_inicio')} value={inicio} onChange={e => setInicio(e.target.value)} />
              <SelectRico label={t('cert.responsable')} valor={responsable} onChange={setResponsable} opciones={personas} />
              <SelectRico label={t('cert.patrocinador')} valor={patrocinador} onChange={setPatrocinador} opciones={personas} />
            </div>
            <h4 className="cert-bloque__titulo">{t('cert.parametros_alcance')}</h4>
            <div className="cert-rejilla">
              {plantilla.parametros.map(p => {
                const etiqueta = t(`cert.param_${p.clave}`)
                if (p.tipo === 'booleano') return (
                  <Switch key={p.clave} label={etiqueta} checked={Boolean(params[p.clave])}
                    onChange={v => setValores(x => ({ ...x, [p.clave]: v }))} />)
                if (p.tipo === 'opcion') return (
                  <div key={p.clave} className="u-stack-6"><span className="cert-apagado">{etiqueta}</span>
                    <Segmentado aria-label={etiqueta} valor={String(params[p.clave] ?? '')}
                      onChange={v => setValores(x => ({ ...x, [p.clave]: v }))}
                      opciones={(p.opciones ?? []).map(o => ({ valor: o, etiqueta: t(`cert.opcion_${o}`) }))} /></div>)
                return (
                  <Input key={p.clave} label={etiqueta} type="number" min={0} value={String(params[p.clave] ?? 0)}
                    onChange={e => setValores(x => ({ ...x, [p.clave]: Math.max(0, Number(e.target.value) || 0) }))} />)
              })}
            </div>
          </>
        )}
        <div className="cert-acciones">
          <Button icon={<Wand2 size={14} />} disabled={!plantilla} loading={generar.isPending} onClick={() => generar.mutate()}>
            {t('cert.generar')}</Button>
          <Button variant="secondary" onClick={onClose}>{t('cert.cancelar')}</Button>
        </div>
      </div>
    </Modal>
  )
}
