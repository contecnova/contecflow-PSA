/**
 * Versiones de un proceso BPM: cuál se ejecuta, publicar otra y abrirla.
 *
 * Revisión BPM 2026-11-16: la API versionaba y publicaba (`/versions`,
 * `/versions/{n}/publish`) pero ninguna pantalla lo usaba: no se podía elegir
 * qué versión ejecutan las instancias nuevas ni ver una anterior. El motor
 * ejecuta la publicada y, si no hay ninguna, la última guardada.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Modal, Spinner, EmptyState } from '../../components/ui'
import { History } from 'lucide-react'
import { bpmnProcessesApi, apiErrorMsg } from '../../services/api'
import type { ProblemaBpmn, VersionDeProcesoBpmn } from '../../services/api/tipos-documentos'
import { useToast } from '../../context/ToastContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { fmtDateTime } from '../../utils/helpers'
import { textoProblema } from './textos'
import './BpmRunPanel.css'

type Props = {
  processId: string
  puedePublicar: boolean
  onAbrir: (version: number, xml: string) => void
  onPublicada: () => void
  onClose: () => void
}

export default function BpmVersionsModal({ processId, puedePublicar, onAbrir, onPublicada, onClose }: Props): JSX.Element {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: versiones = [], isLoading, isError } = useQuery<VersionDeProcesoBpmn[]>({
    queryKey: ['bpmn-versions', processId],
    queryFn: () => bpmnProcessesApi.versions(processId).then(r => r.data),
  })
  const publicada = versiones.find(v => v.is_published)?.version ?? null
  const seEjecuta = publicada ?? (versiones.length ? Math.max(...versiones.map(v => v.version)) : null)

  const publicar = useMutation({
    mutationFn: (version: number) => bpmnProcessesApi.publish(processId, version),
    onSuccess: (_r, version) => {
      qc.invalidateQueries({ queryKey: ['bpmn-versions', processId] })
      toast.success(t('bpm.version_publicada', { n: version }))
      onPublicada()
    },
    onError: (e: unknown) => toast.error(apiErrorMsg(e, t('bpm.error_publicar'))),
  })
  const abrir = useMutation({
    mutationFn: (version: number) => bpmnProcessesApi.version(processId, version).then(r => r.data),
    onSuccess: v => { if (v.bpmn_xml) onAbrir(v.version, v.bpmn_xml) },
    onError: (e: unknown) => toast.error(apiErrorMsg(e, t('common.error'))),
  })

  return (
    <Modal open title={t('bpm.versiones')} onClose={onClose} width={640}>
      {isLoading ? <Spinner /> : isError ? (
        <div role="alert" className="bprupa-box-2">{t('bpm.error_cargar_versiones')}</div>
      ) : versiones.length === 0 ? (
        <EmptyState icon={<History size={28} />} title={t('bpm.sin_versiones')} />
      ) : (
        <div className="u-stack-10">
          <div className="u-text2-sm">
            {publicada ? t('bpm.se_ejecuta_publicada', { n: publicada }) : t('bpm.sin_publicar_ejecuta_ultima')}
          </div>
          <table className="table">
            <thead><tr><th>{t('bpm.version')}</th><th>{t('bpm.notas')}</th><th>{t('bpm.creada')}</th><th>{t('bpm.estado')}</th><th><span className="u-sr-only">{t('cmdb.actions')}</span></th></tr></thead>
            <tbody>
              {versiones.map(v => (
                <tr key={v.id}>
                  <td>v{v.version}</td>
                  <td className="u-xs">{v.notes || '—'}</td>
                  <td className="u-xs">{fmtDateTime(v.created_at)}</td>
                  <td className="u-xs">
                    {v.is_published ? t('bpm.publicada') : ''}
                    {v.version === seEjecuta ? ` ${t('bpm.se_ejecuta')}` : ''}
                  </td>
                  <td className="bprupa-txt-2">
                    <div className="u-actions-8">
                      <Button variant="secondary" onClick={() => abrir.mutate(v.version)} disabled={abrir.isPending}>{t('bpm.ver')}</Button>
                      {puedePublicar && !v.is_published && (
                        <Button onClick={() => publicar.mutate(v.version)} loading={publicar.isPending && publicar.variables === v.version} disabled={publicar.isPending}>
                          {t('bpm.publicar')}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  )
}

/** Lista de lo que impide ejecutar un diagrama, traducida. */
export function BpmProblemsModal({ problemas, onClose }: { problemas: ProblemaBpmn[]; onClose: () => void }): JSX.Element {
  const { t } = useAppLang()
  return (
    <Modal open title={t('bpm.no_ejecutable_titulo')} onClose={onClose} width={560}>
      <div className="u-stack-10">
        <div className="u-text2-sm">{t('bpm.no_ejecutable_desc')}</div>
        <ul role="alert">
          {problemas.map((p, i) => <li key={i}>{textoProblema(t, p)}</li>)}
        </ul>
        <div className="u-row-end"><Button onClick={onClose}>{t('common.close')}</Button></div>
      </div>
    </Modal>
  )
}
