/**
 * Pestaña Riesgo → Importar (22-11-2026): exportaciones de Trend Vision One,
 * Defender, Qualys, Tenable, Rapid7 o el CSV común. Lo que detectan a la vez
 * nuestra correlación y el tercero queda en un solo hallazgo. Las conexiones
 * por API se configuran con las conexiones de escaneo (Configuración).
 *
 * Diseño: docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md §11.9.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { FileUp } from 'lucide-react'
import { useAppT } from '../../../../i18n/AppLangContext'
import { useToast } from '../../../../context/ToastContext'
import { useAuth } from '../../../../context/AuthContext'
import { cmdbRiesgoApi } from '../../../../services/api/cmdbRiesgo'
import type { ResultadoDeImportacionDeTerceros } from '../../../../services/api/cmdbRiesgo'
import { Checkbox, EmptyState, Section, Select, Spinner } from '../../../ui'
import { BotonFichero, ListaKv, useErr } from '../comun'
import { AvisoDeConfiguracion } from '../Escaneos'
import { useEtiquetaSwr, useMetaRiesgo } from './comunRiesgo'

export default function Importar() {
  const t = useAppT()
  const e = useEtiquetaSwr()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { puede } = useAuth()
  const meta = useMetaRiesgo()
  const [fuente, setFuente] = useState('file')
  const [crearCis, setCrearCis] = useState(false)
  const [completa, setCompleta] = useState(false)
  const [resultado, setResultado] = useState<ResultadoDeImportacionDeTerceros | null>(null)
  const importar = useMutation({
    mutationFn: (f: File) => cmdbRiesgoApi.importarFichero(f, { source: fuente, create_cis: crearCis, complete: completa }),
    onSuccess: r => {
      setResultado(r)
      toast.success(t('swr.importado', { nuevos: r.findings_new, actualizados: r.findings_updated, resueltos: r.findings_resolved }))
      qc.invalidateQueries({ queryKey: ['swr'] }); qc.invalidateQueries({ queryKey: ['sw'] })
    },
    onError: err,
  })
  if (!puede('software.gestionar')) return <EmptyState icon={<FileUp size={28} />} title={t('swr.importar_sin_permiso')} />
  return (
    <div className="u-stack-20">
      <Section title={t('swr.importar')} subtitle={t('swr.importar_desc')}>
        <div className="u-stack-12">
          {meta.isLoading ? <Spinner size={16} /> : (
            <div className="sdm-form">
              <Select label={t('swr.fuente')} placeholder={false} value={fuente} onChange={ev => setFuente(ev.target.value)}>
                  {(meta.data?.sources ?? ['file']).map(s => <option key={s} value={s}>{e('fuente', s)}</option>)}
                </Select>
              <div className="sdm-field"><Checkbox checked={crearCis} onChange={setCrearCis} label={t('swr.crear_cis')} ayuda={t('swr.crear_cis_ayuda')} /></div>
              <div className="sdm-field"><Checkbox checked={completa} onChange={setCompleta} label={t('swr.completa')} ayuda={t('swr.completa_ayuda')} /></div>
            </div>
          )}
          <div className="u-text3-xs">{t(`swr.formato_${fuente}`)}</div>
          <div><BotonFichero variant="primary" accept=".json,.csv,.xml,application/json,text/csv,text/xml" icon={<FileUp size={14} />} loading={importar.isPending}
            onFichero={f => importar.mutate(f)}>{t('swr.elegir_fichero')}</BotonFichero></div>
          {resultado && (
            <div className="u-stack-12">
              <ListaKv filas={[
                [t('swr.fuente'), e('fuente', resultado.source)],
                [t('swr.r_detecciones'), resultado.detections],
                [t('swr.r_cis_creados'), resultado.cis_created],
                [t('swr.r_productos_creados'), resultado.products_created],
                [t('swr.r_instancias_creadas'), resultado.instances_created],
                [t('swr.r_hallazgos_nuevos'), resultado.findings_new],
                [t('swr.r_hallazgos_actualizados'), resultado.findings_updated],
                [t('swr.r_hallazgos_resueltos'), resultado.findings_resolved],
              ]} />
              {resultado.unmatched_hosts.length > 0 && (
                <div className="u-stack-6">
                  <div className="ds-eyebrow">{t('swr.r_sin_casar', { n: resultado.unmatched_hosts.length })}</div>
                  <div className="u-text3-xs u-mono sdm-wrap">{resultado.unmatched_hosts.slice(0, 100).join(', ')}</div>
                </div>
              )}
              {resultado.errors.length > 0 && (
                <div className="u-stack-6">
                  <div className="ds-eyebrow">{t('swr.errores_de_fila', { n: resultado.errors.length })}</div>
                  <ul className="sw-lista-simple">{resultado.errors.slice(0, 50).map((x, i) => <li key={i}>{t('swr.fila_n', { n: x.row })}: {x.error}</li>)}</ul>
                </div>
              )}
            </div>
          )}
        </div>
      </Section>
      <AvisoDeConfiguracion tono="warning">{t('swr.conexiones_api')}</AvisoDeConfiguracion>
    </div>
  )
}
