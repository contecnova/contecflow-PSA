/**
 * Declaración de aplicabilidad (§3.3): cada control con aplica/justificación, estado de
 * implantación, eficacia, responsable, evidencias y última revisión. La ficha de la fila
 * reúne las pruebas de control (diseño y eficacia operativa: población, muestra, resultado,
 * quién probó), las tareas que lo implantan y sus evidencias. Segregación: quien implantó
 * no evalúa la eficacia ni prueba (el servidor responde 403 con su código).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ListChecks, ShieldCheck } from 'lucide-react'
import {
  Button, Buscador, Card, DateInput, FiltrosDeLista, Input, Modal, SelectRico, Switch, Tabla, Textarea,
} from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDate, fmtDateTime } from '../../utils/helpers'
import { useListaDeUsuarios } from '../../hooks/useListas'
import { CLAVES_CERT, certApi } from '../../services/api/certificaciones'
import type { Eficacia, FilaSoA, Prueba } from '../../services/api/certificaciones'
import { ESTADOS_MATRIZ, Estado } from './comun'
import type { PropsDePestana } from './comun'

export default function AplicabilidadCert({ programaId }: PropsDePestana) {
  const t = useAppT()
  const [q, setQ] = useState('')
  const [estado, setEstado] = useState('')
  const [marco, setMarco] = useState('')
  const [abierta, setAbierta] = useState<FilaSoA | null>(null)
  const filtros = { q: q || undefined, estado: estado || undefined, marco: marco || undefined }
  const { data: filas = [], isLoading } = useQuery({ queryKey: CLAVES_CERT.aplicabilidad(programaId, filtros),
    queryFn: () => certApi.aplicabilidad(programaId, filtros), enabled: !!programaId })
  const { data: marcos = [] } = useQuery({ queryKey: CLAVES_CERT.marcos, queryFn: certApi.marcos })
  if (!programaId) return <p className="cert-apagado">{t('cert.elige_programa')}</p>
  return (
    <div className="u-stack-12">
      <FiltrosDeLista aria-label={t('cert.filtros')}
        buscador={<Buscador value={q} onChange={setQ} retardo={300} placeholder={t('cert.buscar_control')} />}>
        <SelectRico aria-label={t('cert.estado')} valor={estado} onChange={setEstado} opciones={[
          { valor: '', etiqueta: t('cert.todos_los_estados') },
          ...ESTADOS_MATRIZ.map(e => ({ valor: e, etiqueta: t(`cert.estado_${e}`) }))]} />
        <SelectRico aria-label={t('cert.marco')} valor={marco} onChange={setMarco} opciones={[
          { valor: '', etiqueta: t('cert.todos_los_marcos') },
          ...marcos.map(m => ({ valor: m.clave, etiqueta: m.nombre }))]} />
      </FiltrosDeLista>
      <Tabla<FilaSoA> etiqueta={t('cert.aplicabilidad')} filas={filas} cargando={isLoading} ordenable
        onFila={setAbierta} vacio={{ icono: <ListChecks size={28} />, titulo: t('cert.sin_filas') }}
        columnas={[
          { key: 'control', label: t('cert.control'), cabeceraDeFila: true, render: (_v, f) => (
            <div className="cert-celda"><span>{f.titulo}</span>
              <span className="cert-apagado">{f.control}{f.sede ? ` · ${f.sede}` : ''}</span></div>) },
          { key: 'marcos', label: t('cert.marcos'), sortable: false, render: (_v, f) => (
            <div className="cert-marcos">{f.marcos.map(m => (
              <span key={`${m.marco}-${m.id_control}`} className="cert-apagado">{t(`cert.marco_${m.marco}`)} {m.id_control}</span>))}</div>) },
          { key: 'aplica', label: t('cert.aplica'), render: (_v, f) => (f.aplica ? t('cert.si') : t('cert.no')) },
          { key: 'estado', label: t('cert.implantacion'), render: (_v, f) => <Estado valor={f.estado} /> },
          { key: 'eficacia', label: t('cert.eficacia'), render: (_v, f) => <Estado valor={f.eficacia} /> },
          { key: 'evidencias_validas', label: t('cert.evidencias'), alinear: 'derecha',
            render: (_v, f) => `${f.evidencias_validas}/${f.evidencias}` },
          { key: 'medicion', label: t('cert.medicion'), render: (_v, f) => (f.medible ? <Estado valor={f.medicion} /> : '—') },
          { key: 'estado_matriz', label: t('cert.situacion'), render: (_v, f) => <Estado valor={f.estado_matriz} /> },
          { key: 'ultima_revision', label: t('cert.ultima_revision'), render: (_v, f) => fmtDate(f.ultima_revision) },
        ]} />
      {abierta && <FichaDeFila fila={abierta} onClose={() => setAbierta(null)} />}
    </div>
  )
}

function FichaDeFila({ fila, onClose }: { fila: FilaSoA; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { puede } = useAuth()
  const gestionar = puede('certificaciones.gestionar')
  const auditar = puede('certificaciones.auditar')
  const { data: usuarios = [] } = useListaDeUsuarios()
  const [f, setF] = useState(fila)
  const [aplica, setAplica] = useState(fila.aplica)
  const [justificacion, setJustificacion] = useState(fila.justificacion ?? '')
  const [responsable, setResponsable] = useState(fila.responsable_id ?? '')
  const [sede, setSede] = useState('')
  const { data: pruebas = [] } = useQuery({ queryKey: CLAVES_CERT.fila(fila.id, 'pruebas'), queryFn: () => certApi.pruebas(fila.id) })
  const { data: tareas = [] } = useQuery({ queryKey: CLAVES_CERT.fila(fila.id, 'tareas'), queryFn: () => certApi.tareasDeFila(fila.id) })
  const { data: evidencias = [] } = useQuery({ queryKey: CLAVES_CERT.fila(fila.id, 'evidencias'),
    queryFn: () => certApi.evidenciasDeFila(fila.id) })
  const listo = (x: FilaSoA) => { setF(x); qc.invalidateQueries({ queryKey: CLAVES_CERT.todo }); toast.success(t('cert.guardado')) }
  const error = (e: unknown) => toast.error(extractErr(e))
  const guardar = useMutation({ mutationFn: (d: Record<string, unknown>) => certApi.editarFila(f.id, d), onSuccess: listo, onError: error })
  const eficacia = useMutation({ mutationFn: (e: Eficacia) => certApi.eficacia(f.id, e), onSuccess: listo, onError: error })
  const dividir = useMutation({ mutationFn: () => certApi.dividirSede(f.id, sede), onSuccess: listo, onError: error })
  const personas = [{ valor: '', etiqueta: t('cert.sin_asignar') }, ...usuarios.map(u => ({ valor: u.id, etiqueta: u.full_name }))]
  return (
    <Modal open title={`${f.control} · ${f.titulo}`} subtitle={<Estado valor={f.estado_matriz} />} onClose={onClose} size="xl"
      avisarSinGuardar={false}>
      <div className="u-stack-16">
        <Card>
          <h3 className="cert-bloque__titulo"><ListChecks size={16} aria-hidden />{t('cert.aplicabilidad')}</h3>
          <div className="cert-rejilla">
            <Switch label={t('cert.aplica')} checked={aplica} onChange={setAplica} disabled={!gestionar} />
            <SelectRico label={t('cert.responsable')} valor={responsable} onChange={setResponsable} opciones={personas}
              disabled={!gestionar} />
          </div>
          <Textarea label={t('cert.justificacion')} value={justificacion} onChange={e => setJustificacion(e.target.value)}
            disabled={!gestionar} hint={aplica ? undefined : t('cert.justificacion_obligatoria')} />
          {gestionar && (
            <div className="cert-acciones">
              <Button size="sm" loading={guardar.isPending}
                onClick={() => guardar.mutate({ aplica, justificacion, responsable_id: responsable || null })}>{t('cert.guardar')}</Button>
              {(['pendiente', 'en_curso', 'implantado'] as const).map(e => (
                <Button key={e} size="sm" variant={f.estado === e ? 'primary' : 'secondary'} disabled={f.estado === e}
                  onClick={() => guardar.mutate({ estado: e })}>{t(`cert.marcar_${e}`)}</Button>))}
            </div>
          )}
          <p className="cert-apagado">{f.implantado_en ? t('cert.implantado_el', { fecha: fmtDateTime(f.implantado_en) }) : ''}</p>
        </Card>
        <Card>
          <h3 className="cert-bloque__titulo"><ShieldCheck size={16} aria-hidden />{t('cert.eficacia')}</h3>
          <p className="cert-apagado">{t('cert.ayuda_sod_eficacia')}</p>
          <div className="cert-acciones">
            <Estado valor={f.eficacia} />
            {auditar && (['eficaz', 'parcial', 'no_eficaz'] as Eficacia[]).map(e => (
              <Button key={e} size="sm" variant="secondary" disabled={f.estado !== 'implantado'} loading={eficacia.isPending}
                onClick={() => eficacia.mutate(e)}>{t(`cert.estado_${e}`)}</Button>))}
          </div>
        </Card>
        <Card>
          <h3 className="cert-bloque__titulo">{t('cert.pruebas')}</h3>
          <Tabla<Prueba> etiqueta={t('cert.pruebas')} filas={pruebas} vacio={{ titulo: t('cert.sin_pruebas') }}
            columnas={[
              { key: 'tipo', label: t('cert.tipo'), render: (_v, p) => t(`cert.prueba_${p.tipo}`) },
              { key: 'poblacion', label: t('cert.poblacion_muestra'), render: (_v, p) => `${p.muestra ?? '—'} / ${p.poblacion ?? '—'}` },
              { key: 'resultado', label: t('cert.resultado'), render: (_v, p) => t(`cert.resultado_${p.resultado}`) },
              { key: 'probado', label: t('cert.probado_por'), render: (_v, p) => `${p.probado ?? '—'} · ${fmtDate(p.probado_en)}` },
            ]} />
          {auditar && <NuevaPrueba filaId={f.id} />}
        </Card>
        <Card>
          <h3 className="cert-bloque__titulo">{t('cert.tareas')}</h3>
          <Tabla etiqueta={t('cert.tareas')} filas={tareas} vacio={{ titulo: t('cert.sin_tareas') }}
            columnas={[{ key: 'code', label: t('cert.codigo') }, { key: 'title', label: t('cert.titulo') },
              { key: 'status', label: t('cert.estado') }]} />
        </Card>
        <Card>
          <h3 className="cert-bloque__titulo">{t('cert.evidencias')}</h3>
          <Tabla etiqueta={t('cert.evidencias')} filas={evidencias} vacio={{ titulo: t('cert.sin_evidencias') }}
            columnas={[
              { key: 'titulo', label: t('cert.titulo') },
              { key: 'origen', label: t('cert.origen'), render: (_v, e) => t(`cert.origen_${e.origen}`) },
              { key: 'estado', label: t('cert.estado'), render: (_v, e) => <Estado valor={e.estado} /> },
              { key: 'caduca_el', label: t('cert.caduca'), render: (_v, e) => fmtDate(e.caduca_el) },
            ]} />
        </Card>
        {gestionar && !f.sede && (
          <Card>
            <h3 className="cert-bloque__titulo">{t('cert.por_sede')}</h3>
            <p className="cert-apagado">{t('cert.por_sede_ayuda')}</p>
            <div className="cert-acciones">
              <Input label={t('cert.sede')} value={sede} onChange={e => setSede(e.target.value)} />
              <Button size="sm" variant="secondary" disabled={!sede.trim()} loading={dividir.isPending}
                onClick={() => dividir.mutate()}>{t('cert.crear_fila_de_sede')}</Button>
            </div>
          </Card>
        )}
      </div>
    </Modal>
  )
}

function NuevaPrueba({ filaId }: { filaId: string }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const vacia = { tipo: 'eficacia_operativa', resultado: 'superada', poblacion: '', muestra: '', metodo: '', excepciones: '',
    periodo_desde: '', periodo_hasta: '' }
  const [p, setP] = useState(vacia)
  const set = (k: keyof typeof vacia, v: string) => setP(x => ({ ...x, [k]: v }))
  const crear = useMutation({
    mutationFn: () => certApi.registrarPrueba(filaId, {
      ...p, poblacion: p.poblacion === '' ? null : Number(p.poblacion), muestra: p.muestra === '' ? null : Number(p.muestra),
      periodo_desde: p.periodo_desde || null, periodo_hasta: p.periodo_hasta || null }),
    onSuccess: () => { setP(vacia); qc.invalidateQueries({ queryKey: CLAVES_CERT.fila(filaId, 'pruebas') }); toast.success(t('cert.guardado')) },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <div className="u-stack-8">
      <div className="cert-rejilla">
        <SelectRico label={t('cert.tipo')} valor={p.tipo} onChange={v => set('tipo', v)} opciones={[
          { valor: 'diseno', etiqueta: t('cert.prueba_diseno') }, { valor: 'eficacia_operativa', etiqueta: t('cert.prueba_eficacia_operativa') }]} />
        <SelectRico label={t('cert.resultado')} valor={p.resultado} onChange={v => set('resultado', v)} opciones={
          ['pendiente', 'superada', 'con_excepciones', 'fallida'].map(r => ({ valor: r, etiqueta: t(`cert.resultado_${r}`) }))} />
        <Input label={t('cert.poblacion')} type="number" min={0} value={p.poblacion} onChange={e => set('poblacion', e.target.value)} />
        <Input label={t('cert.muestra')} type="number" min={0} value={p.muestra} onChange={e => set('muestra', e.target.value)} />
        <DateInput label={t('cert.periodo_desde')} value={p.periodo_desde} onChange={e => set('periodo_desde', e.target.value)} />
        <DateInput label={t('cert.periodo_hasta')} value={p.periodo_hasta} onChange={e => set('periodo_hasta', e.target.value)} />
      </div>
      <Textarea label={t('cert.metodo')} value={p.metodo} onChange={e => set('metodo', e.target.value)} />
      <Textarea label={t('cert.excepciones')} value={p.excepciones} onChange={e => set('excepciones', e.target.value)} />
      <div className="cert-acciones">
        <Button size="sm" loading={crear.isPending} onClick={() => crear.mutate()}>{t('cert.registrar_prueba')}</Button>
      </div>
    </div>
  )
}
