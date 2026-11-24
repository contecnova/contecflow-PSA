/**
 * Auditores y empresas colaboradoras (§3.6): empresas (certificadoras, proveedores de auditoría
 * ENX, consultoras, laboratorios 62443…), personas (cualificación, independencia, conflictos,
 * NDA, periodo) y acceso temporal de solo lectura por enlace del portal, con todo lo consultado
 * registrado. RGPD de los externos: copia y supresión (administración).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Building2, KeyRound, Plus, UserCheck } from 'lucide-react'
import { Button, Card, Checkbox, DateInput, Input, Modal, SelectRico, Tabla, Textarea } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr, fmtDate, fmtDateTime } from '../../utils/helpers'
import { CLAVES_CERT, certApi } from '../../services/api/certificaciones'
import type { Acceso, Auditor, Entidad } from '../../services/api/certificaciones'
import { descargarJson } from './comun'
import type { PropsDePestana } from './comun'

const TIPOS_ENTIDAD = ['certificadora', 'proveedor_enx', 'consultora', 'auditor_sox', 'laboratorio_62443', 'autoridad', 'otra']

export default function ExternosCert({ programaId }: PropsDePestana) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { puede } = useAuth()
  const gestionar = puede('certificaciones.gestionar')
  const auditar = puede('certificaciones.auditar')
  const administrar = puede('certificaciones.administrar')
  const { data: entidades = [] } = useQuery({ queryKey: CLAVES_CERT.entidades, queryFn: certApi.entidades })
  const { data: auditores = [] } = useQuery({ queryKey: CLAVES_CERT.auditores, queryFn: certApi.auditores })
  const { data: accesos = [] } = useQuery({ queryKey: CLAVES_CERT.accesos(programaId), enabled: auditar,
    queryFn: () => certApi.accesos(programaId || undefined) })
  const [entidad, setEntidad] = useState<Entidad | 'nueva' | null>(null)
  const [auditor, setAuditor] = useState<Auditor | 'nuevo' | null>(null)
  const [conceder, setConceder] = useState(false)
  const [registro, setRegistro] = useState<Acceso | null>(null)
  const ok = () => qc.invalidateQueries({ queryKey: CLAVES_CERT.todo })
  const mal = (e: unknown) => toast.error(extractErr(e))
  const revocar = useMutation({ mutationFn: (id: string) => certApi.revocar(id), onSuccess: ok, onError: mal })
  const suprimir = useMutation({ mutationFn: (id: string) => certApi.suprimirAuditor(id), onSuccess: ok, onError: mal })
  const copia = useMutation({ mutationFn: (a: Auditor) => certApi.copiaAuditor(a.id).then(d => ({ a, d })),
    onSuccess: ({ a, d }) => descargarJson(`rgpd-auditor-${a.id}.json`, d), onError: mal })
  return (
    <div className="u-stack-16">
      <Card>
        <h3 className="cert-bloque__titulo"><Building2 size={16} aria-hidden />{t('cert.entidades')}</h3>
        {gestionar && <div className="cert-acciones"><Button size="sm" icon={<Plus size={14} />} onClick={() => setEntidad('nueva')}>
          {t('cert.entidad_nueva')}</Button></div>}
        <Tabla<Entidad> etiqueta={t('cert.entidades')} filas={entidades} onFila={gestionar ? setEntidad : undefined}
          vacio={{ titulo: t('cert.sin_entidades') }}
          columnas={[
            { key: 'nombre', label: t('cert.nombre'), cabeceraDeFila: true },
            { key: 'tipo', label: t('cert.tipo'), render: (_v, e) => t(`cert.entidad_${e.tipo}`) },
            { key: 'acreditaciones', label: t('cert.acreditaciones'), render: (_v, e) => e.acreditaciones.join(', ') || '—' },
            { key: 'subcontractor_id', label: t('cert.en_proveedores'), render: (_v, e) => (e.subcontractor_id ? t('cert.si') : t('cert.no')) },
          ]} />
      </Card>
      <Card>
        <h3 className="cert-bloque__titulo"><UserCheck size={16} aria-hidden />{t('cert.auditores')}</h3>
        {gestionar && <div className="cert-acciones"><Button size="sm" icon={<Plus size={14} />} onClick={() => setAuditor('nuevo')}>
          {t('cert.auditor_nuevo')}</Button></div>}
        <Tabla<Auditor> etiqueta={t('cert.auditores')} filas={auditores} onFila={gestionar ? (a => !a.suprimido && setAuditor(a)) : undefined}
          vacio={{ titulo: t('cert.sin_auditores') }}
          columnas={[
            { key: 'nombre', label: t('cert.nombre'), cabeceraDeFila: true },
            { key: 'entidad', label: t('cert.entidad'), render: (_v, a) => a.entidad || '—' },
            { key: 'independencia_declarada', label: t('cert.independencia'), render: (_v, a) => (a.independencia_declarada ? t('cert.si') : t('cert.no')) },
            { key: 'nda_firmado_el', label: t('cert.nda'), render: (_v, a) => fmtDate(a.nda_firmado_el) },
            { key: 'periodo', label: t('cert.periodo'), sortable: false, render: (_v, a) => `${fmtDate(a.desde)} – ${fmtDate(a.hasta)}` },
            ...(administrar ? [{ key: 'rgpd', label: t('cert.rgpd'), sortable: false, render: (_v: never, a: Auditor) => (a.suprimido
              ? <span className="cert-apagado">{t('cert.suprimido')}</span>
              : <div className="cert-acciones">
                  <Button size="xs" variant="secondary" onClick={() => copia.mutate(a)}>{t('cert.rgpd_copia')}</Button>
                  <Button size="xs" variant="danger" onClick={async () => {
                    if (await confirmar({ message: t('cert.confirmar_suprimir_auditor'), danger: true })) suprimir.mutate(a.id) }}>
                    {t('cert.rgpd_suprimir')}</Button>
                </div>) }] : []),
          ]} />
      </Card>
      {auditar && (
        <Card>
          <h3 className="cert-bloque__titulo"><KeyRound size={16} aria-hidden />{t('cert.accesos')}</h3>
          <p className="cert-apagado">{t('cert.accesos_ayuda')}</p>
          {programaId && <div className="cert-acciones"><Button size="sm" icon={<Plus size={14} />} onClick={() => setConceder(true)}>
            {t('cert.conceder_acceso')}</Button></div>}
          <Tabla<Acceso> etiqueta={t('cert.accesos')} filas={accesos} vacio={{ titulo: t('cert.sin_accesos') }}
            columnas={[
              { key: 'auditor', label: t('cert.auditor') },
              { key: 'programa', label: t('cert.programa') },
              { key: 'hasta', label: t('cert.hasta'), render: (_v, x) => fmtDateTime(x.hasta) },
              { key: 'usos', label: t('cert.consultas'), alinear: 'derecha' },
              { key: 'vigente', label: t('cert.estado'), render: (_v, x) => (x.vigente ? t('cert.vigente') : t('cert.no_vigente')) },
              { key: 'botones', label: t('cert.acciones'), sortable: false, render: (_v, x) => (
                <div className="cert-acciones">
                  <Button size="xs" variant="secondary" onClick={() => setRegistro(x)}>{t('cert.ver_registro')}</Button>
                  {x.vigente && <Button size="xs" variant="danger" onClick={() => revocar.mutate(x.id)}>{t('cert.revocar')}</Button>}
                </div>) },
            ]} />
        </Card>
      )}
      {entidad && <FichaEntidad entidad={entidad === 'nueva' ? null : entidad} onClose={() => setEntidad(null)} />}
      {auditor && <FichaAuditor auditor={auditor === 'nuevo' ? null : auditor} entidades={entidades} onClose={() => setAuditor(null)} />}
      {conceder && <ConcederAcceso programaId={programaId} auditores={auditores} onClose={() => setConceder(false)} />}
      {registro && <RegistroDeAcceso acceso={registro} onClose={() => setRegistro(null)} />}
    </div>
  )
}

function FichaEntidad({ entidad, onClose }: { entidad: Entidad | null; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [e, setE] = useState({ nombre: entidad?.nombre ?? '', tipo: entidad?.tipo ?? 'certificadora',
    acreditaciones: (entidad?.acreditaciones ?? []).join(', '), contacto_email: entidad?.contacto_email ?? '',
    web: entidad?.web ?? '', notas: entidad?.notas ?? '' })
  const guardar = useMutation({
    mutationFn: () => certApi.guardarEntidad({ ...e, acreditaciones: e.acreditaciones.split(',').map(x => x.trim()).filter(Boolean) },
      entidad?.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: CLAVES_CERT.todo }); onClose() },
    onError: err => toast.error(extractErr(err)),
  })
  return (
    <Modal open title={entidad ? entidad.nombre : t('cert.entidad_nueva')} onClose={onClose} size="md">
      <div className="u-stack-12">
        <Input label={t('cert.nombre')} value={e.nombre} onChange={x => setE({ ...e, nombre: x.target.value })} required />
        <SelectRico label={t('cert.tipo')} valor={e.tipo} onChange={v => setE({ ...e, tipo: v })}
          opciones={TIPOS_ENTIDAD.map(x => ({ valor: x, etiqueta: t(`cert.entidad_${x}`) }))} />
        <Input label={t('cert.acreditaciones')} value={e.acreditaciones} hint={t('cert.separadas_por_comas')}
          onChange={x => setE({ ...e, acreditaciones: x.target.value })} />
        <Input label={t('cert.correo')} value={e.contacto_email} onChange={x => setE({ ...e, contacto_email: x.target.value })} />
        <Input label={t('cert.web')} value={e.web} onChange={x => setE({ ...e, web: x.target.value })} />
        <Textarea label={t('cert.notas')} value={e.notas} onChange={x => setE({ ...e, notas: x.target.value })} />
        <div className="cert-acciones">
          <Button disabled={!e.nombre.trim()} loading={guardar.isPending} onClick={() => guardar.mutate()}>{t('cert.guardar')}</Button>
          <Button variant="secondary" onClick={onClose}>{t('cert.cancelar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function FichaAuditor({ auditor, entidades, onClose }: { auditor: Auditor | null; entidades: Entidad[]; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [a, setA] = useState({ nombre: auditor?.nombre ?? '', entidad_id: auditor?.entidad_id ?? '', email: auditor?.email ?? '',
    cualificaciones: (auditor?.cualificaciones ?? []).join(', '), independencia_declarada: auditor?.independencia_declarada ?? false,
    conflictos_interes: auditor?.conflictos_interes ?? '', nda_firmado_el: auditor?.nda_firmado_el ?? '',
    desde: auditor?.desde ?? '', hasta: auditor?.hasta ?? '' })
  const guardar = useMutation({
    mutationFn: () => certApi.guardarAuditor({ ...a, entidad_id: a.entidad_id || null, nda_firmado_el: a.nda_firmado_el || null,
      desde: a.desde || null, hasta: a.hasta || null,
      cualificaciones: a.cualificaciones.split(',').map(x => x.trim()).filter(Boolean) }, auditor?.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: CLAVES_CERT.todo }); onClose() },
    onError: err => toast.error(extractErr(err)),
  })
  return (
    <Modal open title={auditor ? auditor.nombre : t('cert.auditor_nuevo')} subtitle={t('cert.auditor_ayuda_rgpd')} onClose={onClose} size="lg">
      <div className="u-stack-12">
        <div className="cert-rejilla">
          <Input label={t('cert.nombre')} value={a.nombre} onChange={x => setA({ ...a, nombre: x.target.value })} required />
          <SelectRico label={t('cert.entidad')} valor={a.entidad_id} onChange={v => setA({ ...a, entidad_id: v })} opciones={[
            { valor: '', etiqueta: t('cert.ninguna') }, ...entidades.map(e => ({ valor: e.id, etiqueta: e.nombre }))]} />
          <Input label={t('cert.correo')} value={a.email} onChange={x => setA({ ...a, email: x.target.value })} />
          <DateInput label={t('cert.nda')} value={a.nda_firmado_el} onChange={x => setA({ ...a, nda_firmado_el: x.target.value })} />
          <DateInput label={t('cert.desde')} value={a.desde} onChange={x => setA({ ...a, desde: x.target.value })} />
          <DateInput label={t('cert.hasta')} value={a.hasta} onChange={x => setA({ ...a, hasta: x.target.value })} />
        </div>
        <Input label={t('cert.cualificaciones')} value={a.cualificaciones} hint={t('cert.separadas_por_comas')}
          onChange={x => setA({ ...a, cualificaciones: x.target.value })} />
        <Checkbox checked={a.independencia_declarada} label={t('cert.independencia_declarada')}
          onChange={v => setA({ ...a, independencia_declarada: v })} />
        <Textarea label={t('cert.conflictos_interes')} value={a.conflictos_interes}
          onChange={x => setA({ ...a, conflictos_interes: x.target.value })} />
        <div className="cert-acciones">
          <Button disabled={!a.nombre.trim()} loading={guardar.isPending} onClick={() => guardar.mutate()}>{t('cert.guardar')}</Button>
          <Button variant="secondary" onClick={onClose}>{t('cert.cancelar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function ConcederAcceso({ programaId, auditores, onClose }: { programaId: string; auditores: Auditor[]; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [auditorId, setAuditorId] = useState('')
  const [dias, setDias] = useState('7')
  const [hecho, setHecho] = useState<Acceso | null>(null)
  const conceder = useMutation({
    mutationFn: () => certApi.conceder({ auditor_id: auditorId, programa_id: programaId, dias: Number(dias) || 7 }),
    onSuccess: x => { setHecho(x); qc.invalidateQueries({ queryKey: CLAVES_CERT.todo }) },
    onError: e => toast.error(extractErr(e)),
  })
  const enlace = hecho?.url ? `${window.location.origin}${hecho.url}` : ''
  return (
    <Modal open title={t('cert.conceder_acceso')} subtitle={t('cert.conceder_ayuda')} onClose={onClose} size="md" avisarSinGuardar={false}>
      {hecho ? (
        <div className="u-stack-12">
          <p>{t('cert.enlace_una_vez')}</p>
          <p className="ds-codigo cert-token">{enlace}</p>
          <div className="cert-acciones">
            <Button onClick={() => { void navigator.clipboard?.writeText(enlace); toast.success(t('cert.copiado')) }}>{t('cert.copiar')}</Button>
            <Button variant="secondary" onClick={onClose}>{t('cert.cerrar')}</Button>
          </div>
        </div>
      ) : (
        <div className="u-stack-12">
          <SelectRico label={t('cert.auditor')} valor={auditorId} onChange={setAuditorId} opciones={[
            { valor: '', etiqueta: t('cert.elige_auditor') },
            ...auditores.filter(a => a.activo && !a.suprimido).map(a => ({ valor: a.id, etiqueta: a.nombre }))]} />
          <Input label={t('cert.dias')} type="number" min={1} max={365} value={dias} onChange={e => setDias(e.target.value)} />
          <div className="cert-acciones">
            <Button disabled={!auditorId} loading={conceder.isPending} onClick={() => conceder.mutate()}>{t('cert.conceder')}</Button>
            <Button variant="secondary" onClick={onClose}>{t('cert.cancelar')}</Button>
          </div>
        </div>
      )}
    </Modal>
  )
}

function RegistroDeAcceso({ acceso, onClose }: { acceso: Acceso; onClose: () => void }) {
  const t = useAppT()
  const { data = [], isLoading } = useQuery({ queryKey: ['cert', 'registro', acceso.id], queryFn: () => certApi.registroDeAcceso(acceso.id) })
  return (
    <Modal open title={t('cert.registro_de_consultas')} subtitle={`${acceso.auditor ?? ''} · ${acceso.programa ?? ''}`} onClose={onClose}
      size="lg" avisarSinGuardar={false}>
      <Tabla etiqueta={t('cert.registro_de_consultas')} filas={data} cargando={isLoading} claveDeFila={(_f, i) => i}
        vacio={{ titulo: t('cert.sin_consultas') }}
        columnas={[
          { key: 'en', label: t('cert.cuando'), render: (_v, r) => fmtDateTime(r.en) },
          { key: 'recurso', label: t('cert.recurso') },
          { key: 'detalle', label: t('cert.detalle'), render: (_v, r) => r.detalle || '—' },
          { key: 'ip', label: t('cert.ip'), render: (_v, r) => r.ip || '—' },
        ]} />
    </Modal>
  )
}
