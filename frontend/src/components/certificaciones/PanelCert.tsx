/**
 * Panel de Certificaciones (§3.9): avance por norma, carencias, hallazgos abiertos, acciones
 * vencidas, certificados por vencer, cobertura de evidencias e incidentes NIS2 abiertos.
 */
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Award, FileCheck2, ShieldAlert, Siren } from 'lucide-react'
import { Card, KpiCard, Spinner, Tabla } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { fmtDate } from '../../utils/helpers'
import { CLAVES_CERT, certApi } from '../../services/api/certificaciones'
import type { Accion, Certificado } from '../../services/api/certificaciones'
import { ESTADOS_MATRIZ, Estado } from './comun'
import type { PropsDePestana } from './comun'

export default function PanelCert({ programaId }: PropsDePestana) {
  const t = useAppT()
  const { data, isLoading } = useQuery({ queryKey: CLAVES_CERT.panel(programaId),
    queryFn: () => certApi.panel(programaId || undefined) })
  if (isLoading || !data) return <Spinner />
  const normas = Object.entries(data.por_norma).map(([marco, d]) => ({ id: marco, marco, ...d }))
  return (
    <div className="u-stack-16">
      <div className="cert-kpis">
        <KpiCard icon={<FileCheck2 size={16} />} label={t('cert.cobertura')}
          value={data.cobertura_evidencias.porcentaje == null ? '—' : `${data.cobertura_evidencias.porcentaje} %`}
          sub={t('cert.cobertura_sub', { n: data.cobertura_evidencias.con_evidencia_valida, total: data.cobertura_evidencias.filas })} />
        <KpiCard icon={<AlertTriangle size={16} />} label={t('cert.hallazgos_abiertos')} value={data.hallazgos_abiertos}
          danger={(data.hallazgos_por_tipo.nc_mayor ?? 0) > 0}
          sub={t('cert.nc_mayores', { n: data.hallazgos_por_tipo.nc_mayor ?? 0 })} />
        <KpiCard icon={<ShieldAlert size={16} />} label={t('cert.acciones_vencidas')} value={data.acciones_vencidas.length}
          warning={data.acciones_vencidas.length > 0} />
        <KpiCard icon={<Award size={16} />} label={t('cert.certificados_por_vencer')} value={data.certificados_por_vencer.length}
          warning={data.certificados_por_vencer.length > 0} />
        <KpiCard icon={<Siren size={16} />} label={t('cert.incidentes_abiertos')} value={data.incidentes_nis2_abiertos.length}
          danger={data.incidentes_nis2_abiertos.some(i => Object.values(i.relojes).some(r => r.estado === 'vencido'))} />
      </div>
      <Card>
        <h3 className="cert-bloque__titulo">{t('cert.avance_por_norma')}</h3>
        <Tabla etiqueta={t('cert.avance_por_norma')} filas={normas} claveDeFila={f => f.id}
          vacio={{ titulo: t('cert.sin_programas'), descripcion: t('cert.sin_programas_desc') }}
          columnas={[
            { key: 'marco', label: t('cert.marco'), cabeceraDeFila: true, render: (_v, f) => t(`cert.marco_${f.marco}`) },
            { key: 'avance', label: t('cert.avance'), alinear: 'derecha', render: (_v, f) => (f.avance == null ? '—' : `${f.avance} %`) },
            ...ESTADOS_MATRIZ.map(e => ({ key: e, label: t(`cert.estado_${e}`), alinear: 'derecha' as const })),
          ]} />
      </Card>
      <div className="cert-rejilla">
        <Card>
          <h3 className="cert-bloque__titulo">{t('cert.carencias')}</h3>
          <Tabla etiqueta={t('cert.carencias')} filas={data.carencias} claveDeFila={f => f.fila_id}
            vacio={{ titulo: t('cert.sin_carencias') }}
            columnas={[
              { key: 'control', label: t('cert.control'), render: (_v, f) => (
                <div className="cert-celda"><span>{f.titulo}</span><span className="cert-apagado">{f.programa} · {f.control}</span></div>) },
              { key: 'estado', label: t('cert.estado'), render: (_v, f) => <Estado valor={f.estado} /> },
            ]} />
        </Card>
        <Card>
          <h3 className="cert-bloque__titulo">{t('cert.certificados_por_vencer')}</h3>
          <Tabla<Certificado> etiqueta={t('cert.certificados_por_vencer')} filas={data.certificados_por_vencer}
            vacio={{ titulo: t('cert.sin_vencimientos') }}
            columnas={[
              { key: 'numero', label: t('cert.numero') },
              { key: 'marco', label: t('cert.marco'), render: (_v, c) => (c.marco ? t(`cert.marco_${c.marco}`) : '—') },
              { key: 'valido_hasta', label: t('cert.valido_hasta'), render: (_v, c) => fmtDate(c.valido_hasta) },
            ]} />
        </Card>
        <Card>
          <h3 className="cert-bloque__titulo">{t('cert.acciones_vencidas')}</h3>
          <Tabla<Accion> etiqueta={t('cert.acciones_vencidas')} filas={data.acciones_vencidas}
            vacio={{ titulo: t('cert.sin_acciones_vencidas') }}
            columnas={[
              { key: 'plan', label: t('cert.plan') },
              { key: 'responsable', label: t('cert.responsable'), render: (_v, a) => a.responsable || '—' },
              { key: 'fecha_limite', label: t('cert.fecha_limite'), render: (_v, a) => fmtDate(a.fecha_limite) },
            ]} />
        </Card>
      </div>
    </div>
  )
}
