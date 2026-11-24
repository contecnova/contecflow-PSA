/**
 * Certificados y etiquetas (§3.7): ciclo de vida como una licencia. Emisión, alcance, entidad
 * certificadora y número; auditorías de seguimiento (año 1 y 2) y renovación (año 3), que el
 * servidor calcula si no se dan; TISAX con identificador ENX y alcance (máximo 3 años).
 * Los avisos de vencimiento y de auditoría próxima los da el trabajo diario.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Award, Plus } from 'lucide-react'
import { Button, DateInput, Input, Modal, SelectRico, Tabla, Textarea } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import { CLAVES_CERT, certApi } from '../../services/api/certificaciones'
import type { Certificado } from '../../services/api/certificaciones'
import { Estado } from './comun'
import type { PropsDePestana } from './comun'

export default function CertificadosCert({ programaId }: PropsDePestana) {
  const t = useAppT()
  const { puede } = useAuth()
  const { data = [], isLoading } = useQuery({ queryKey: CLAVES_CERT.certificados, queryFn: certApi.certificados })
  const [ficha, setFicha] = useState<Certificado | 'nuevo' | null>(null)
  const gestionar = puede('certificaciones.gestionar')
  const filas = programaId ? data.filter(c => !c.programa_id || c.programa_id === programaId) : data
  return (
    <div className="u-stack-12">
      {gestionar && <div className="cert-acciones"><Button icon={<Plus size={14} />} onClick={() => setFicha('nuevo')}>
        {t('cert.certificado_nuevo')}</Button></div>}
      <Tabla<Certificado> etiqueta={t('cert.certificados')} filas={filas} cargando={isLoading} ordenable
        onFila={gestionar ? setFicha : undefined} vacio={{ icono: <Award size={28} />, titulo: t('cert.sin_certificados') }}
        columnas={[
          { key: 'numero', label: t('cert.numero'), cabeceraDeFila: true },
          { key: 'marco', label: t('cert.marco'), render: (_v, c) => `${c.marco ? t(`cert.marco_${c.marco}`) : '—'}${c.nivel ? ` ${c.nivel}` : ''}` },
          { key: 'entidad', label: t('cert.entidad'), render: (_v, c) => c.entidad || '—' },
          { key: 'emitido_el', label: t('cert.emitido'), render: (_v, c) => fmtDate(c.emitido_el) },
          { key: 'valido_hasta', label: t('cert.valido_hasta'), render: (_v, c) => (
            <div className="cert-celda"><span>{fmtDate(c.valido_hasta)}</span>
              {c.dias_para_vencer != null && <span className="cert-apagado">{t('cert.dias_para_vencer', { n: c.dias_para_vencer })}</span>}</div>) },
          { key: 'proxima_auditoria', label: t('cert.proxima_auditoria'), render: (_v, c) => (
            `${fmtDate(c.proxima_auditoria)}${c.tipo_proxima ? ` · ${t(`cert.proxima_${c.tipo_proxima}`)}` : ''}`) },
          { key: 'estado', label: t('cert.estado'), render: (_v, c) => <Estado valor={c.estado === 'caducado' ? 'caducado_cert' : c.estado} /> },
          { key: 'enx_id', label: t('cert.enx'), render: (_v, c) => c.enx_id || '—' },
        ]} />
      {ficha && <FichaCertificado certificado={ficha === 'nuevo' ? null : ficha} programaId={programaId} onClose={() => setFicha(null)} />}
    </div>
  )
}

function FichaCertificado({ certificado: c, programaId, onClose }: { certificado: Certificado | null; programaId: string; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: marcos = [] } = useQuery({ queryKey: CLAVES_CERT.marcos, queryFn: certApi.marcos })
  const { data: entidades = [] } = useQuery({ queryKey: CLAVES_CERT.entidades, queryFn: certApi.entidades })
  const [f, setF] = useState({ numero: c?.numero ?? '', marco: c?.marco ?? '', entidad_id: c?.entidad_id ?? '', nivel: c?.nivel ?? '',
    alcance: c?.alcance ?? '', emitido_el: c?.emitido_el ?? '', valido_hasta: c?.valido_hasta ?? '',
    proxima_auditoria: c?.proxima_auditoria ?? '', estado: c?.estado === 'caducado' ? 'vigente' : (c?.estado ?? 'vigente'),
    enx_id: c?.enx_id ?? '', enx_ambito: c?.enx_ambito ?? '' })
  const set = (k: keyof typeof f, v: string) => setF(x => ({ ...x, [k]: v }))
  const guardar = useMutation({
    mutationFn: () => certApi.guardarCertificado({ ...Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === '' ? null : v])),
      numero: f.numero, ...(c ? {} : { programa_id: programaId || null }) }, c?.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: CLAVES_CERT.todo }); onClose() },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <Modal open title={c ? c.numero : t('cert.certificado_nuevo')} subtitle={t('cert.certificado_ayuda')} onClose={onClose} size="lg">
      <div className="u-stack-12">
        <div className="cert-rejilla">
          <Input label={t('cert.numero')} value={f.numero} onChange={e => set('numero', e.target.value)} required />
          <SelectRico label={t('cert.marco')} valor={f.marco} onChange={v => set('marco', v)} opciones={[
            { valor: '', etiqueta: t('cert.ninguno') }, ...marcos.map(m => ({ valor: m.clave, etiqueta: m.nombre }))]} />
          <Input label={t('cert.nivel')} value={f.nivel} onChange={e => set('nivel', e.target.value)} />
          <SelectRico label={t('cert.entidad')} valor={f.entidad_id} onChange={v => set('entidad_id', v)} opciones={[
            { valor: '', etiqueta: t('cert.ninguna') }, ...entidades.map(e => ({ valor: e.id, etiqueta: e.nombre }))]} />
          <DateInput label={t('cert.emitido')} value={f.emitido_el} onChange={e => set('emitido_el', e.target.value)} />
          <DateInput label={t('cert.valido_hasta')} value={f.valido_hasta} onChange={e => set('valido_hasta', e.target.value)} />
          <DateInput label={t('cert.proxima_auditoria')} value={f.proxima_auditoria} onChange={e => set('proxima_auditoria', e.target.value)} />
          <SelectRico label={t('cert.estado')} valor={f.estado} onChange={v => set('estado', v)}
            opciones={['vigente', 'suspendido', 'retirado'].map(x => ({ valor: x, etiqueta: t(`cert.estado_${x}`) }))} />
          {f.marco === 'tisax' && <>
            <Input label={t('cert.enx_id')} value={f.enx_id} onChange={e => set('enx_id', e.target.value)} />
            <Input label={t('cert.enx_ambito')} value={f.enx_ambito} onChange={e => set('enx_ambito', e.target.value)} />
          </>}
        </div>
        <Textarea label={t('cert.alcance')} value={f.alcance} onChange={e => set('alcance', e.target.value)} />
        <div className="cert-acciones">
          <Button disabled={!f.numero.trim()} loading={guardar.isPending} onClick={() => guardar.mutate()}>{t('cert.guardar')}</Button>
          <Button variant="secondary" onClick={onClose}>{t('cert.cancelar')}</Button>
        </div>
      </div>
    </Modal>
  )
}
