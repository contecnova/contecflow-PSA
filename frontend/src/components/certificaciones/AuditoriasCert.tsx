/**
 * Auditorías, hallazgos y acciones correctivas (§3.5). Cada acción (CAPA) nace como tarea del
 * proyecto del programa. Segregación: quien corrigió un hallazgo no lo cierra y quien hizo una
 * acción no verifica su eficacia (el servidor responde 403 con su código).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCheck, ClipboardList, Plus, Search, Wrench } from 'lucide-react'
import { Button, Card, DateInput, Input, Modal, SelectRico, Tabla, Textarea } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useConfirm } from '../../context/ConfirmContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import { useListaDeUsuarios } from '../../hooks/useListas'
import { CLAVES_CERT, certApi } from '../../services/api/certificaciones'
import type { Accion, Auditoria, Hallazgo } from '../../services/api/certificaciones'
import { Estado } from './comun'
import type { PropsDePestana } from './comun'

const TIPOS = ['interna', 'certificacion_f1', 'certificacion_f2', 'seguimiento', 'renovacion', 'cliente', 'regulatoria']
const TIPOS_HALLAZGO = ['nc_mayor', 'nc_menor', 'observacion', 'oportunidad']
const ESTADOS = ['planificada', 'en_curso', 'informe', 'cerrada']

export default function AuditoriasCert({ programaId }: PropsDePestana) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { puede } = useAuth()
  const { pedirTexto } = useConfirm()
  const auditar = puede('certificaciones.auditar')
  const gestionar = puede('certificaciones.gestionar')
  const { data: auditorias = [], isLoading } = useQuery({ queryKey: CLAVES_CERT.auditorias(programaId),
    queryFn: () => certApi.auditorias(programaId || undefined) })
  const { data: hallazgos = [] } = useQuery({ queryKey: CLAVES_CERT.hallazgos(programaId),
    queryFn: () => certApi.hallazgos(programaId || undefined) })
  const [nueva, setNueva] = useState(false)
  const [hallazgoDe, setHallazgoDe] = useState<Auditoria | null>(null)
  const [accionDe, setAccionDe] = useState<Hallazgo | null>(null)
  const ok = () => { qc.invalidateQueries({ queryKey: CLAVES_CERT.todo }); toast.success(t('cert.guardado')) }
  const mal = (e: unknown) => toast.error(extractErr(e))
  const accion = useMutation({ mutationFn: (f: () => Promise<unknown>) => f(), onSuccess: ok, onError: mal })
  const verificar = async (a: Accion, eficaz: boolean) => {
    const texto = await pedirTexto({ title: t('cert.verificar'), message: t('cert.verificar_ayuda'), label: t('cert.verificacion'),
      multiline: true })
    if (texto !== null && texto !== undefined) accion.mutate(() => certApi.verificar(a.id, eficaz, texto))
  }
  return (
    <div className="u-stack-16">
      {auditar && programaId && (
        <div className="cert-acciones"><Button icon={<Plus size={14} />} onClick={() => setNueva(true)}>{t('cert.auditoria_nueva')}</Button></div>)}
      <Tabla<Auditoria> etiqueta={t('cert.auditorias')} filas={auditorias} cargando={isLoading} ordenable
        vacio={{ icono: <Search size={28} />, titulo: t('cert.sin_auditorias') }}
        columnas={[
          { key: 'codigo', label: t('cert.codigo'), cabeceraDeFila: true },
          { key: 'tipo', label: t('cert.tipo'), render: (_v, a) => t(`cert.auditoria_${a.tipo}`) },
          { key: 'marco', label: t('cert.marco'), render: (_v, a) => (a.marco ? t(`cert.marco_${a.marco}`) : '—') },
          { key: 'fecha_inicio', label: t('cert.fechas'), render: (_v, a) => `${fmtDate(a.fecha_inicio)} – ${fmtDate(a.fecha_fin)}` },
          { key: 'entidad', label: t('cert.entidad'), render: (_v, a) => [a.entidad, a.auditor].filter(Boolean).join(' · ') || '—' },
          { key: 'estado', label: t('cert.estado'), render: (_v, a) => (auditar
            ? <SelectRico aria-label={t('cert.estado')} valor={a.estado}
                onChange={v => accion.mutate(() => certApi.editarAuditoria(a.id, { estado: v }))}
                opciones={ESTADOS.map(e => ({ valor: e, etiqueta: t(`cert.estado_${e}`) }))} />
            : <Estado valor={a.estado} />) },
          { key: 'hallazgos_abiertos', label: t('cert.hallazgos_abiertos'), alinear: 'derecha' },
          { key: 'acciones', label: t('cert.acciones'), sortable: false, render: (_v, a) => (auditar
            ? <Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={() => setHallazgoDe(a)}>{t('cert.hallazgo_nuevo')}</Button>
            : null) },
        ]} />
      <Card>
        <h3 className="cert-bloque__titulo"><ClipboardList size={16} aria-hidden />{t('cert.hallazgos_y_capa')}</h3>
        <div className="u-stack-12">
          {hallazgos.length === 0 && <p className="cert-apagado">{t('cert.sin_hallazgos')}</p>}
          {hallazgos.map(h => (
            <Card key={h.id}>
              <div className="cert-acciones">
                <strong>{h.codigo}</strong><Estado valor={h.tipo} /><Estado valor={h.estado} />
                <span>{h.titulo}</span>
                {h.vencido && <span className="cert-aviso cert-aviso--peligro">{t('cert.vencido_el', { fecha: fmtDate(h.fecha_limite) })}</span>}
              </div>
              {h.descripcion && <p className="cert-texto">{h.descripcion}</p>}
              <Tabla<Accion> etiqueta={t('cert.acciones_correctivas')} filas={h.acciones ?? []} densidad="compacta"
                vacio={{ titulo: t('cert.sin_acciones') }}
                columnas={[
                  { key: 'plan', label: t('cert.plan'), render: (_v, a) => (
                    <div className="cert-celda"><span>{a.plan}</span>
                      {a.analisis_causa && <span className="cert-apagado">{t('cert.causa')}: {a.analisis_causa}</span>}</div>) },
                  { key: 'responsable', label: t('cert.responsable'), render: (_v, a) => a.responsable || '—' },
                  { key: 'fecha_limite', label: t('cert.fecha_limite'), render: (_v, a) => fmtDate(a.fecha_limite) },
                  { key: 'tarea', label: t('cert.tarea'), render: (_v, a) => a.tarea?.code ?? '—' },
                  { key: 'estado', label: t('cert.estado'), render: (_v, a) => <Estado valor={a.estado} /> },
                  { key: 'botones', label: t('cert.acciones'), sortable: false, render: (_v, a) => (
                    <div className="cert-acciones">
                      {gestionar && ['abierta', 'en_curso', 'no_eficaz'].includes(a.estado) && (
                        <Button size="xs" variant="secondary" onClick={() => accion.mutate(() => certApi.accionHecha(a.id))}>
                          {t('cert.marcar_hecha')}</Button>)}
                      {auditar && a.estado === 'hecha' && (<>
                        <Button size="xs" variant="secondary" onClick={() => verificar(a, true)}>{t('cert.eficaz')}</Button>
                        <Button size="xs" variant="secondary" onClick={() => verificar(a, false)}>{t('cert.no_eficaz')}</Button>
                      </>)}
                    </div>) },
                ]} />
              <div className="cert-acciones">
                {gestionar && h.estado !== 'cerrado' && (
                  <Button size="sm" variant="secondary" icon={<Wrench size={14} />} onClick={() => setAccionDe(h)}>{t('cert.accion_nueva')}</Button>)}
                {gestionar && ['abierto', 'en_correccion'].includes(h.estado) && (
                  <Button size="sm" variant="secondary" onClick={() => accion.mutate(() => certApi.corregido(h.id))}>{t('cert.marcar_corregido')}</Button>)}
                {auditar && h.estado === 'corregido' && (
                  <Button size="sm" icon={<CheckCheck size={14} />} onClick={() => accion.mutate(() => certApi.cerrarHallazgo(h.id))}>
                    {t('cert.cerrar_hallazgo')}</Button>)}
              </div>
            </Card>
          ))}
        </div>
      </Card>
      {nueva && <NuevaAuditoria programaId={programaId} onClose={() => setNueva(false)} />}
      {hallazgoDe && <NuevoHallazgo auditoria={hallazgoDe} onClose={() => setHallazgoDe(null)} />}
      {accionDe && <NuevaAccion hallazgo={accionDe} onClose={() => setAccionDe(null)} />}
    </div>
  )
}

function NuevaAuditoria({ programaId, onClose }: { programaId: string; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: marcos = [] } = useQuery({ queryKey: CLAVES_CERT.marcos, queryFn: certApi.marcos })
  const { data: entidades = [] } = useQuery({ queryKey: CLAVES_CERT.entidades, queryFn: certApi.entidades })
  const { data: auditores = [] } = useQuery({ queryKey: CLAVES_CERT.auditores, queryFn: certApi.auditores })
  const vacia = { tipo: 'interna', marco: '', fecha_inicio: '', fecha_fin: '', entidad_id: '', auditor_id: '', plan: '' }
  const [a, setA] = useState(vacia)
  const set = (k: keyof typeof vacia, v: string) => setA(x => ({ ...x, [k]: v }))
  const crear = useMutation({
    mutationFn: () => certApi.crearAuditoria({ programa_id: programaId,
      ...Object.fromEntries(Object.entries(a).filter(([, v]) => v !== '')) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: CLAVES_CERT.todo }); onClose() },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <Modal open title={t('cert.auditoria_nueva')} onClose={onClose} size="lg" cambiosSinGuardar={!!a.plan}>
      <div className="u-stack-12">
        <div className="cert-rejilla">
          <SelectRico label={t('cert.tipo')} valor={a.tipo} onChange={v => set('tipo', v)}
            opciones={TIPOS.map(x => ({ valor: x, etiqueta: t(`cert.auditoria_${x}`) }))} />
          <SelectRico label={t('cert.marco')} valor={a.marco} onChange={v => set('marco', v)} opciones={[
            { valor: '', etiqueta: t('cert.todos_los_marcos') }, ...marcos.map(m => ({ valor: m.clave, etiqueta: m.nombre }))]} />
          <DateInput label={t('cert.fecha_inicio')} value={a.fecha_inicio} onChange={e => set('fecha_inicio', e.target.value)} />
          <DateInput label={t('cert.fecha_fin')} value={a.fecha_fin} onChange={e => set('fecha_fin', e.target.value)} />
          <SelectRico label={t('cert.entidad')} valor={a.entidad_id} onChange={v => set('entidad_id', v)} opciones={[
            { valor: '', etiqueta: t('cert.ninguna') }, ...entidades.map(e => ({ valor: e.id, etiqueta: e.nombre }))]} />
          <SelectRico label={t('cert.auditor')} valor={a.auditor_id} onChange={v => set('auditor_id', v)} opciones={[
            { valor: '', etiqueta: t('cert.ninguno') }, ...auditores.filter(x => x.activo).map(x => ({ valor: x.id, etiqueta: x.nombre }))]} />
        </div>
        <Textarea label={t('cert.plan_de_auditoria')} value={a.plan} onChange={e => set('plan', e.target.value)} rows={5} />
        <div className="cert-acciones">
          <Button loading={crear.isPending} onClick={() => crear.mutate()}>{t('cert.crear')}</Button>
          <Button variant="secondary" onClick={onClose}>{t('cert.cancelar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function NuevoHallazgo({ auditoria, onClose }: { auditoria: Auditoria; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: filas = [] } = useQuery({ queryKey: CLAVES_CERT.aplicabilidad(auditoria.programa_id, {}),
    queryFn: () => certApi.aplicabilidad(auditoria.programa_id) })
  const vacio = { tipo: 'nc_menor', titulo: '', descripcion: '', control_id: '', fecha_limite: '' }
  const [h, setH] = useState(vacio)
  const set = (k: keyof typeof vacio, v: string) => setH(x => ({ ...x, [k]: v }))
  const crear = useMutation({
    mutationFn: () => certApi.crearHallazgo(auditoria.id, Object.fromEntries(Object.entries(h).filter(([, v]) => v !== ''))),
    onSuccess: () => { qc.invalidateQueries({ queryKey: CLAVES_CERT.todo }); onClose() },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <Modal open title={t('cert.hallazgo_nuevo')} subtitle={auditoria.codigo} onClose={onClose} size="lg" cambiosSinGuardar={!!h.titulo}>
      <div className="u-stack-12">
        <div className="cert-rejilla">
          <SelectRico label={t('cert.tipo')} valor={h.tipo} onChange={v => set('tipo', v)}
            opciones={TIPOS_HALLAZGO.map(x => ({ valor: x, etiqueta: t(`cert.estado_${x}`) }))} />
          <SelectRico label={t('cert.control')} valor={h.control_id} onChange={v => set('control_id', v)} opciones={[
            { valor: '', etiqueta: t('cert.ninguno') },
            ...filas.filter(f => !f.sede).map(f => ({ valor: f.control_id, etiqueta: `${f.control} · ${f.titulo}` }))]} />
          <DateInput label={t('cert.fecha_limite')} value={h.fecha_limite} onChange={e => set('fecha_limite', e.target.value)} />
        </div>
        <Input label={t('cert.titulo')} value={h.titulo} onChange={e => set('titulo', e.target.value)} required />
        <Textarea label={t('cert.descripcion')} value={h.descripcion} onChange={e => set('descripcion', e.target.value)} rows={4} />
        <div className="cert-acciones">
          <Button disabled={!h.titulo.trim()} loading={crear.isPending} onClick={() => crear.mutate()}>{t('cert.crear')}</Button>
          <Button variant="secondary" onClick={onClose}>{t('cert.cancelar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function NuevaAccion({ hallazgo, onClose }: { hallazgo: Hallazgo; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: usuarios = [] } = useListaDeUsuarios()
  const vacia = { analisis_causa: '', plan: '', responsable_id: '', fecha_limite: hallazgo.fecha_limite ?? '' }
  const [a, setA] = useState(vacia)
  const set = (k: keyof typeof vacia, v: string) => setA(x => ({ ...x, [k]: v }))
  const crear = useMutation({
    mutationFn: () => certApi.crearAccion(hallazgo.id, Object.fromEntries(Object.entries(a).filter(([, v]) => v !== ''))),
    onSuccess: r => { qc.invalidateQueries({ queryKey: CLAVES_CERT.todo });
      toast.success(r.tarea ? t('cert.accion_con_tarea', { tarea: r.tarea.code }) : t('cert.accion_sin_tarea')); onClose() },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <Modal open title={t('cert.accion_nueva')} subtitle={`${hallazgo.codigo} · ${hallazgo.titulo}`} onClose={onClose} size="lg"
      cambiosSinGuardar={!!a.plan}>
      <div className="u-stack-12">
        <Textarea label={t('cert.analisis_causa')} value={a.analisis_causa} onChange={e => set('analisis_causa', e.target.value)} rows={3} />
        <Textarea label={t('cert.plan')} value={a.plan} onChange={e => set('plan', e.target.value)} rows={3} required />
        <div className="cert-rejilla">
          <SelectRico label={t('cert.responsable')} valor={a.responsable_id} onChange={v => set('responsable_id', v)} opciones={[
            { valor: '', etiqueta: t('cert.sin_asignar') }, ...usuarios.map(u => ({ valor: u.id, etiqueta: u.full_name }))]} />
          <DateInput label={t('cert.fecha_limite')} value={a.fecha_limite} onChange={e => set('fecha_limite', e.target.value)} />
        </div>
        <div className="cert-acciones">
          <Button disabled={!a.plan.trim()} loading={crear.isPending} onClick={() => crear.mutate()}>{t('cert.crear')}</Button>
          <Button variant="secondary" onClick={onClose}>{t('cert.cancelar')}</Button>
        </div>
      </div>
    </Modal>
  )
}
