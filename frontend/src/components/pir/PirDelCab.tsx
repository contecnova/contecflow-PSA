/**
 * PIR en el panel del CAB (migración 206, docs/PIR.md): de los cambios cerrados en los
 * últimos 90 días, cuántos están «cerrados del todo» (sin PIR obligatoria pendiente)
 * y la lista de PIR de cambios pendientes (vencidas primero en el aviso).
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, ClipboardCheck, Clock } from 'lucide-react'
import { KpiCard, Spinner, Tabla } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { fmtDate } from '../../utils/helpers'
import { CLAVES_PIR, pirApi } from '../../services/api/pir'
import type { Pir } from '../../services/api/pir'
import { EstadoDePir, OrigenDePir } from './comun'
import FichaDePir from './FichaDePir'
import './Pir.css'

export default function PirDelCab() {
  const t = useAppT()
  const { puede } = useAuth()
  const [abierta, setAbierta] = useState<string | null>(null)
  const { data, isLoading } = useQuery({ queryKey: CLAVES_PIR.cab, queryFn: () => pirApi.cab(), enabled: puede('pir.ver') })
  if (!puede('pir.ver')) return null
  if (isLoading || !data) return <Spinner />
  return (
    <section className="pir-bloque" aria-label={t('pir.cab_titulo')}>
      <h3 className="pir-bloque__titulo"><ClipboardCheck size={16} aria-hidden />{t('pir.cab_titulo')}</h3>
      <div className="ds-grid-stats">
        <KpiCard icon={<CheckCircle2 size={16} />} label={t('pir.cab_cerrados_del_todo')}
          value={`${data.cerrados_del_todo} / ${data.cambios_cerrados}`} sub={t('pir.cab_cerrados_sub')} />
        <KpiCard icon={<Clock size={16} />} label={t('pir.cab_con_pir_pendiente')} value={data.cerrados_con_pir_pendiente}
          warning={data.cerrados_con_pir_pendiente > 0} />
        <KpiCard icon={<AlertTriangle size={16} />} label={t('pir.cab_vencidas')} value={data.pir_vencidas} danger={data.pir_vencidas > 0} />
        <KpiCard icon={<ClipboardCheck size={16} />} label={t('pir.cab_por_aprobar')} value={data.pir_por_aprobar} />
      </div>
      <Tabla<Pir>
        etiqueta={t('pir.cab_pendientes')}
        filas={data.pendientes}
        onFila={p => setAbierta(p.id)}
        claseDeFila={p => (p.vencida ? 'pir-fila--vencida' : undefined)}
        vacio={{ icono: <ClipboardCheck size={28} />, titulo: t('pir.cab_sin_pendientes') }}
        columnas={[
          { key: 'codigo', label: t('pir.codigo'), cabeceraDeFila: true },
          { key: 'origen_ref', label: t('pir.cambio'), render: (_v, p) => <OrigenDePir pir={p} /> },
          { key: 'estado', label: t('pir.estado'), render: (_v, p) => <EstadoDePir pir={p} /> },
          { key: 'fecha_prevista', label: t('pir.fecha_prevista'), render: (_v, p) => fmtDate(p.fecha_prevista) },
          { key: 'responsable', label: t('pir.responsable'), render: (_v, p) => p.responsable || '—' },
        ]}
      />
      {abierta && <FichaDePir id={abierta} onClose={() => setAbierta(null)} />}
    </section>
  )
}
