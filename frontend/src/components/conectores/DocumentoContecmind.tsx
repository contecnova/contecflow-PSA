/**
 * Un documento de contecmind visto desde contecflow (revisión 2026-11).
 *
 * Datos, extracto del texto, versiones con su estado y la aprobación en curso.
 * Pedir la aprobación de una versión sólo si el rol puede escribir y contecmind
 * lo permite (`puedo_pedir`). Subir una versión NUEVA no se puede desde aquí:
 * contecmind lo tiene sólo en su administración, cerrada a las integraciones.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Download, ShieldCheck } from 'lucide-react'
import { conectoresApi, mensajeDeConector } from '../../services/api'
import { Button, Modal, Spinner, TablaSimple } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { fmtDate as formatDate } from '../../utils/helpers'
import { tamano } from './DocumentosDeFicha'
import { OBJECT_URL_REVOKE_DELAY_MS } from '../../constants/timings'
import './DocumentoContecmind.css'

export async function descargarOriginal(id: string, nombre: string) {
  const r = await conectoresApi.original(id)
  const disp = String(r.headers?.['content-disposition'] ?? '')
  const deCabecera = /filename="?([^";]+)"?/.exec(disp)?.[1]
  const url = URL.createObjectURL(r.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = deCabecera || nombre
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), OBJECT_URL_REVOKE_DELAY_MS)
}


export default function DocumentoContecmind({ id, puedeEscribir, onClose }: { id: string; puedeEscribir: boolean; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const doc = useQuery({ queryKey: ['conectores', 'doc', id], queryFn: () => conectoresApi.documento(id), retry: false })
  const apr = useQuery({ queryKey: ['conectores', 'aprobacion', id], queryFn: () => conectoresApi.aprobacion(id), retry: false })
  const pedir = useMutation({
    mutationFn: (v?: number) => conectoresApi.pedirAprobacion(id, v),
    onSuccess: () => { toast.success(t('docs.aprobacion_pedida')); qc.invalidateQueries({ queryKey: ['conectores', 'aprobacion', id] }) },
    onError: (e: unknown) => toast.error(mensajeDeConector(e, t('docs.error_generico'))),
  })
  const d = doc.data
  // Los estados vienen de contecmind: los conocidos se traducen; uno nuevo se enseña tal cual.
  const estado = (e?: string | null) => (e ? t(`docs.estado_${e}`, e) : '—')

  return (
    <Modal open onClose={onClose} size="lg" title={d?.title ?? t('docs.documento')} subtitle="contecmind">
      {doc.isLoading ? <Spinner />
        : doc.isError ? <div role="alert" className="docucont-txt-1">{mensajeDeConector(doc.error, t('docs.error_generico'))}</div>
        : d && (
          <div className="u-stack-16">
            <div className="docucont-grid-1">
              <div><div className="docucont-etiqueta">{t('docs.tipo')}</div><div className="docucont-valor">{d.mime_type || '—'}</div></div>
              <div><div className="docucont-etiqueta">{t('docs.tamano')}</div><div className="docucont-valor">{tamano(d.size_bytes) || '—'}</div></div>
              <div><div className="docucont-etiqueta">{t('docs.estado')}</div><div className="docucont-valor">{estado(d.status)}</div></div>
              <div><div className="docucont-etiqueta">{t('docs.actualizado')}</div><div className="docucont-valor">{d.updated_at ? formatDate(d.updated_at) : '—'}</div></div>
              {d.review_deadline && <div><div className="docucont-etiqueta">{t('docs.revisar_antes')}</div><div className="docucont-valor">{formatDate(d.review_deadline)}</div></div>}
              {d.locked_by && <div><div className="docucont-etiqueta">{t('docs.bloqueado')}</div><div className="docucont-valor">{d.lock_note || t('docs.en_edicion')}</div></div>}
            </div>
            {d.error && <div role="alert" className="docucont-txt-2">{d.error}</div>}

            {d.extracto && (
              <div>
                <div className="docucont-etiqueta">{t('docs.extracto')}</div>
                <div className="docucont-box-1">
                  {d.extracto}{d.extracto_recortado ? '…' : ''}
                </div>
              </div>
            )}

            <div>
              <div className="docucont-etiqueta2"><ShieldCheck size={13} />{t('docs.versiones')}</div>
              {apr.isLoading ? <Spinner size={16} />
                : apr.isError ? <div className="docucont-valor2">{mensajeDeConector(apr.error, t('docs.error_generico'))}</div>
                : (apr.data?.versions ?? []).length === 0 ? <div className="docucont-valor2">{t('docs.sin_versiones')}</div>
                : (
                  <TablaSimple claseTabla="docucont-box-2">
                    <thead><tr className="docucont-txt-3">
                      <th className="docucont-sp-1">{t('docs.version')}</th><th className="docucont-sp-1">{t('docs.estado')}</th>
                      <th className="docucont-sp-1">{t('docs.fichero')}</th><th className="docucont-sp-1">{t('docs.fecha')}</th><th aria-label={t('docs.pedir_aprobacion')} />
                    </tr></thead>
                    <tbody>
                      {apr.data!.versions!.map(v => (
                        <tr key={v.version_no} className="docucont-box-3">
                          <td className="docucont-box-4">v{v.version_no}</td>
                          <td className="docucont-sp-1">{estado(v.state)}</td>
                          <td className="docucont-sp-1">{v.filename}{v.change_note ? ` — ${v.change_note}` : ''}</td>
                          <td className="docucont-sp-1">{formatDate(v.published_at || v.created_at)}</td>
                          <td className="docucont-box-5">
                            {puedeEscribir && apr.data?.puedo_pedir && v.state !== 'published' && (
                              <Button size="xs" variant="secondary" loading={pedir.isPending} onClick={() => pedir.mutate(v.version_no)}>{t('docs.pedir_aprobacion')}</Button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </TablaSimple>
                )}
              {apr.data?.solicitud && (
                <div className="docucont-valor3">{t('docs.solicitud_en_curso')}: <strong>{estado(apr.data.solicitud.status)}</strong></div>
              )}
              <div className="docucont-etiqueta3">{t('docs.versiones_nota')}</div>
            </div>

            <div className="docucont-row-1">
              <Button icon={<Download size={14} />} onClick={() => descargarOriginal(id, d.title).catch(e => toast.error(mensajeDeConector(e, t('docs.error_generico'))))}>{t('docs.descargar')}</Button>
              <Button variant="secondary" onClick={onClose}>{t('docs.cerrar')}</Button>
            </div>
          </div>
        )}
    </Modal>
  )
}
