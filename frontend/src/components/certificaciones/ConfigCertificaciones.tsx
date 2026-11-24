/**
 * Sección «Certificaciones» de Configuración (`/settings/certificaciones`, capacidad
 * `certificaciones.administrar`; migración 212, docs/CERTIFICACIONES.md).
 *
 * - Avisos: días antes del vencimiento de un certificado, de la auditoría del ciclo y de la
 *   caducidad de una evidencia; caducidad por defecto de las evidencias.
 * - Evidencias: exigir que el documento esté aprobado para que cuente.
 * - Auditores: duración máxima del acceso temporal de solo lectura.
 * - NIS2: autoridad (CSIRT o autoridad competente) y plazos (24 h, 72 h, 1 mes).
 * - CAPA: proyecto donde nacen las tareas de acciones de programas sin proyecto.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, FileCheck2, KeyRound, Siren } from 'lucide-react'
import { Button, Card, Input, SelectRico, Spinner, Switch } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { useListaDeProyectos } from '../../hooks/useListas'
import { CLAVES_CERT, certApi } from '../../services/api/certificaciones'
import type { ConfigCert } from '../../services/api/certificaciones'
import './Certificaciones.css'

export default function ConfigCertificaciones() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: CLAVES_CERT.config, queryFn: certApi.config })
  const { data: proyectos = [] } = useListaDeProyectos()
  const [f, setF] = useState<ConfigCert | null>(null)
  useEffect(() => { if (data) setF(data) }, [data])
  const guardar = useMutation({
    mutationFn: (c: ConfigCert) => certApi.guardarConfig(c),
    onSuccess: c => { qc.setQueryData(CLAVES_CERT.config, c); toast.success(t('cert.guardado')) },
    onError: e => toast.error(extractErr(e)),
  })
  if (isLoading || !f) return <Spinner />
  const set = <K extends keyof ConfigCert>(k: K, v: ConfigCert[K]) => setF(x => (x ? { ...x, [k]: v } : x))
  const num = (k: keyof ConfigCert, etiqueta: string, max = 3650) => (
    <Input label={etiqueta} type="number" min={1} max={max} value={String(f[k] ?? '')}
      onChange={e => set(k, Math.max(1, Math.min(max, Number(e.target.value) || 1)) as never)} />)
  return (
    <div className="u-stack-16">
      <Card>
        <h3 className="cert-bloque__titulo"><Bell size={16} aria-hidden />{t('cert.cfg_avisos')}</h3>
        <div className="cert-rejilla">
          {num('aviso_certificado_dias', t('cert.cfg_aviso_certificado'))}
          {num('aviso_auditoria_dias', t('cert.cfg_aviso_auditoria'))}
          {num('aviso_evidencia_dias', t('cert.cfg_aviso_evidencia'))}
        </div>
      </Card>
      <Card>
        <h3 className="cert-bloque__titulo"><FileCheck2 size={16} aria-hidden />{t('cert.cfg_evidencias')}</h3>
        <div className="cert-rejilla">
          {num('caducidad_evidencia_dias', t('cert.cfg_caducidad_evidencia'))}
          <Switch checked={f.exigir_evidencia_aprobada} onChange={v => set('exigir_evidencia_aprobada', v)}
            label={t('cert.cfg_exigir_aprobada')} ayuda={t('cert.cfg_exigir_aprobada_ayuda')} />
        </div>
      </Card>
      <Card>
        <h3 className="cert-bloque__titulo"><KeyRound size={16} aria-hidden />{t('cert.cfg_auditores')}</h3>
        <div className="cert-rejilla">
          {num('acceso_auditor_max_dias', t('cert.cfg_acceso_max'), 365)}
          <SelectRico label={t('cert.cfg_proyecto_capa')} valor={f.proyecto_capa_id ?? ''} onChange={v => set('proyecto_capa_id', v || null)}
            opciones={[{ valor: '', etiqueta: t('cert.ninguno') }, ...proyectos.map(p => ({ valor: p.id, etiqueta: `${p.code} · ${p.name}` }))]} />
        </div>
      </Card>
      <Card>
        <h3 className="cert-bloque__titulo"><Siren size={16} aria-hidden />{t('cert.cfg_nis2')}</h3>
        <div className="cert-rejilla">
          <Input label={t('cert.cfg_autoridad')} value={f.autoridad_nis2 ?? ''} onChange={e => set('autoridad_nis2', e.target.value || null)} />
          {num('nis2_alerta_horas', t('cert.cfg_nis2_alerta'), 720)}
          {num('nis2_notificacion_horas', t('cert.cfg_nis2_notificacion'), 720)}
          {num('nis2_informe_final_dias', t('cert.cfg_nis2_informe'), 365)}
        </div>
      </Card>
      <div className="cert-acciones">
        <Button loading={guardar.isPending} onClick={() => guardar.mutate(f)}>{t('cert.guardar')}</Button>
      </div>
    </div>
  )
}
