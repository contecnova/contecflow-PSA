/**
 * Informes de PIR (migración 206, docs/PIR.md), con `pir.gestionar`:
 * - Tasa de éxito de cambios y proyectos (PIR aprobadas o cerradas del periodo, por
 *   ámbito y por tipo): éxito, parcial, fallo y marcha atrás.
 * - Cumplimiento: PIR obligatorias del periodo a tiempo, tarde, en plazo y vencidas
 *   (con la lista de vencidas, también las de antes del periodo que siguen sin hacer).
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Clock, Percent } from 'lucide-react'
import { CampoRangoDeFechas, KpiCard, Spinner, Tabla } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { fmtDate } from '../../utils/helpers'
import { CLAVES_PIR, pirApi } from '../../services/api/pir'
import type { GrupoExito, Pir } from '../../services/api/pir'
import { EstadoDePir, OrigenDePir } from './comun'
import './Pir.css'

export default function InformesPir({ onAbrir }: { onAbrir: (id: string) => void }) {
  const t = useAppT()
  const [rango, setRango] = useState<{ desde: string; hasta: string }>({ desde: '', hasta: '' })
  const desde = rango.desde || undefined
  const hasta = rango.hasta || undefined
  const exito = useQuery({ queryKey: CLAVES_PIR.informes('exito', desde, hasta), queryFn: () => pirApi.exito(desde, hasta) })
  const cumple = useQuery({ queryKey: CLAVES_PIR.informes('cumplimiento', desde, hasta), queryFn: () => pirApi.cumplimiento(desde, hasta) })
  const pct = (v: number | null) => (v === null ? '—' : `${v} %`)
  return (
    <div className="u-stack-16">
      <div className="u-stack-6"><span className="pir-apagado">{t('pir.periodo')}</span>
        <CampoRangoDeFechas desde={rango.desde} hasta={rango.hasta} onChange={r => setRango(r)} /></div>
      {cumple.isLoading || !cumple.data ? <Spinner /> : (
        <section className="pir-bloque" aria-label={t('pir.informe_cumplimiento')}>
          <h3 className="pir-bloque__titulo">{t('pir.informe_cumplimiento')}</h3>
          <div className="ds-grid-stats">
            <KpiCard icon={<Percent size={16} />} label={t('pir.tasa_cumplimiento')} value={pct(cumple.data.tasa_cumplimiento)}
              sub={t('pir.de_obligatorias', { n: cumple.data.obligatorias })} />
            <KpiCard icon={<CheckCircle2 size={16} />} label={t('pir.a_tiempo')} value={cumple.data.a_tiempo} />
            <KpiCard icon={<Clock size={16} />} label={t('pir.tarde')} value={cumple.data.tarde} warning={cumple.data.tarde > 0} />
            <KpiCard icon={<AlertTriangle size={16} />} label={t('pir.vencidas')} value={cumple.data.vencidas} danger={cumple.data.vencidas > 0} />
          </div>
          <Tabla<Pir>
            etiqueta={t('pir.lista_vencidas')}
            filas={cumple.data.lista_vencidas}
            onFila={p => onAbrir(p.id)}
            vacio={{ icono: <CheckCircle2 size={28} />, titulo: t('pir.sin_vencidas') }}
            columnas={[
              { key: 'codigo', label: t('pir.codigo'), cabeceraDeFila: true },
              { key: 'origen_ref', label: t('pir.origen'), render: (_v, p) => <OrigenDePir pir={p} /> },
              { key: 'estado', label: t('pir.estado'), render: (_v, p) => <EstadoDePir pir={p} /> },
              { key: 'fecha_prevista', label: t('pir.fecha_prevista'), render: (_v, p) => fmtDate(p.fecha_prevista) },
              { key: 'responsable', label: t('pir.responsable'), render: (_v, p) => p.responsable || '—' },
            ]}
          />
        </section>
      )}
      {exito.isLoading || !exito.data ? <Spinner /> : (
        <section className="pir-bloque" aria-label={t('pir.informe_exito')}>
          <h3 className="pir-bloque__titulo">{t('pir.informe_exito')}</h3>
          <Tabla<GrupoExito>
            etiqueta={t('pir.informe_exito')}
            filas={exito.data.grupos}
            claveDeFila={g => `${g.ambito}-${g.tipo ?? '*'}`}
            vacio={{ icono: <Percent size={28} />, titulo: t('pir.sin_revisadas') }}
            columnas={[
              { key: 'ambito', label: t('pir.ambito'), cabeceraDeFila: true, render: (_v, g) => t(`pir.origen_${g.ambito}`) },
              { key: 'tipo', label: t('pir.tipo'), render: (_v, g) => (g.tipo === null ? t('pir.todos') : g.tipo) },
              { key: 'revisadas', label: t('pir.revisadas'), alinear: 'derecha' },
              { key: 'exito', label: t('pir.resultado_exito'), alinear: 'derecha' },
              { key: 'exito_parcial', label: t('pir.resultado_exito_parcial'), alinear: 'derecha' },
              { key: 'fallo', label: t('pir.resultado_fallo'), alinear: 'derecha' },
              { key: 'marcha_atras', label: t('pir.marcha_atras'), alinear: 'derecha' },
              { key: 'tasa_exito', label: t('pir.tasa_exito'), alinear: 'derecha', render: (_v, g) => pct(g.tasa_exito) },
            ]}
          />
        </section>
      )}
    </div>
  )
}
