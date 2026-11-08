/**
 * Un documento de contecmind visto desde contecflow (revisión 2026-11).
 *
 * Datos, extracto del texto, versiones con su estado y la aprobación en curso.
 * Pedir la aprobación de una versión sólo si el rol puede escribir y contecmind
 * lo permite (`puedo_pedir`). Subir una versión NUEVA no se puede desde aquí:
 * contecmind lo tiene sólo en su administración, cerrada a las integraciones.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { CSSProperties } from 'react'
import { Download, ShieldCheck } from 'lucide-react'
import { conectoresApi, mensajeDeConector } from '../../services/api'
import { Button, Modal, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { fmtDate as formatDate } from '../../utils/helpers'
import { tamano } from './DocumentosDeFicha'

export async function descargarOriginal(id: string, nombre: string) {
  const r = await conectoresApi.original(id)
  const disp = String(r.headers?.['content-disposition'] ?? '')
  const deCabecera = /filename="?([^";]+)"?/.exec(disp)?.[1]
  const url = URL.createObjectURL(r.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = deCabecera || nombre
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const etiqueta: CSSProperties = { fontSize: 'var(--text-xs)', color: 'var(--text-3)' }
const valor: CSSProperties = { fontSize: 'var(--text-sm)', color: 'var(--text-1)', marginTop: 2 }

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
        : doc.isError ? <div role="alert" style={{ color: 'var(--danger)', fontSize: 'var(--text-sm)' }}>{mensajeDeConector(doc.error, t('docs.error_generico'))}</div>
        : d && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
              <div><div style={etiqueta}>{t('docs.tipo')}</div><div style={valor}>{d.mime_type || '—'}</div></div>
              <div><div style={etiqueta}>{t('docs.tamano')}</div><div style={valor}>{tamano(d.size_bytes) || '—'}</div></div>
              <div><div style={etiqueta}>{t('docs.estado')}</div><div style={valor}>{estado(d.status)}</div></div>
              <div><div style={etiqueta}>{t('docs.actualizado')}</div><div style={valor}>{d.updated_at ? formatDate(d.updated_at) : '—'}</div></div>
              {d.review_deadline && <div><div style={etiqueta}>{t('docs.revisar_antes')}</div><div style={valor}>{formatDate(d.review_deadline)}</div></div>}
              {d.locked_by && <div><div style={etiqueta}>{t('docs.bloqueado')}</div><div style={valor}>{d.lock_note || t('docs.en_edicion')}</div></div>}
            </div>
            {d.error && <div role="alert" style={{ fontSize: 'var(--text-sm)', color: 'var(--warning)' }}>{d.error}</div>}

            {d.extracto && (
              <div>
                <div style={etiqueta}>{t('docs.extracto')}</div>
                <div style={{ marginTop: 6, maxHeight: 260, overflow: 'auto', whiteSpace: 'pre-wrap', fontSize: 'var(--text-sm)', lineHeight: 1.55, color: 'var(--text-2)', background: 'var(--surface-1)', border: '1px solid var(--surface-3)', borderRadius: 8, padding: 12 }}>
                  {d.extracto}{d.extracto_recortado ? '…' : ''}
                </div>
              </div>
            )}

            <div>
              <div style={{ ...etiqueta, display: 'flex', alignItems: 'center', gap: 6 }}><ShieldCheck size={13} />{t('docs.versiones')}</div>
              {apr.isLoading ? <Spinner size={16} />
                : apr.isError ? <div style={{ ...valor, color: 'var(--text-3)' }}>{mensajeDeConector(apr.error, t('docs.error_generico'))}</div>
                : (apr.data?.versions ?? []).length === 0 ? <div style={{ ...valor, color: 'var(--text-3)' }}>{t('docs.sin_versiones')}</div>
                : (
                  <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 6, fontSize: 'var(--text-sm)' }}>
                    <thead><tr style={{ color: 'var(--text-3)', textAlign: 'left' }}>
                      <th style={{ padding: 6 }}>{t('docs.version')}</th><th style={{ padding: 6 }}>{t('docs.estado')}</th>
                      <th style={{ padding: 6 }}>{t('docs.fichero')}</th><th style={{ padding: 6 }}>{t('docs.fecha')}</th><th aria-label={t('docs.pedir_aprobacion')} />
                    </tr></thead>
                    <tbody>
                      {apr.data!.versions!.map(v => (
                        <tr key={v.version_no} style={{ borderTop: '1px solid var(--surface-3)' }}>
                          <td style={{ padding: 6, fontFamily: 'var(--font-mono)' }}>v{v.version_no}</td>
                          <td style={{ padding: 6 }}>{estado(v.state)}</td>
                          <td style={{ padding: 6 }}>{v.filename}{v.change_note ? ` — ${v.change_note}` : ''}</td>
                          <td style={{ padding: 6 }}>{formatDate(v.published_at || v.created_at)}</td>
                          <td style={{ padding: 6, textAlign: 'right' }}>
                            {puedeEscribir && apr.data?.puedo_pedir && v.state !== 'published' && (
                              <Button size="xs" variant="secondary" loading={pedir.isPending} onClick={() => pedir.mutate(v.version_no)}>{t('docs.pedir_aprobacion')}</Button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              {apr.data?.solicitud && (
                <div style={{ ...valor, marginTop: 8 }}>{t('docs.solicitud_en_curso')}: <strong>{estado(apr.data.solicitud.status)}</strong></div>
              )}
              <div style={{ ...etiqueta, marginTop: 8 }}>{t('docs.versiones_nota')}</div>
            </div>

            <div style={{ display: 'flex', gap: 8, borderTop: '1px solid var(--surface-3)', paddingTop: 12 }}>
              <Button icon={<Download size={14} />} onClick={() => descargarOriginal(id, d.title).catch(e => toast.error(mensajeDeConector(e, t('docs.error_generico'))))}>{t('docs.descargar')}</Button>
              <Button variant="secondary" onClick={onClose}>{t('docs.cerrar')}</Button>
            </div>
          </div>
        )}
    </Modal>
  )
}
