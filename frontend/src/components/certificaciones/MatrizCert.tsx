/**
 * Matriz cruzada (§3.3): control × marco × sede × estado, con totales por norma y por sede.
 * Una sede sin fila propia hereda la general.
 */
import { useQuery } from '@tanstack/react-query'
import { Grid3x3 } from 'lucide-react'
import { Card, Spinner, Tabla } from '../ui'
import type { ColumnaTabla } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { CLAVES_CERT, certApi } from '../../services/api/certificaciones'
import type { Matriz } from '../../services/api/certificaciones'
import { ESTADOS_MATRIZ, Estado } from './comun'
import type { PropsDePestana } from './comun'

type FilaMatriz = Matriz['controles'][number]

export default function MatrizCert({ programaId }: PropsDePestana) {
  const t = useAppT()
  const { data, isLoading } = useQuery({ queryKey: CLAVES_CERT.matriz(programaId), queryFn: () => certApi.matriz(programaId),
    enabled: !!programaId })
  if (!programaId) return <p className="cert-apagado">{t('cert.elige_programa')}</p>
  if (isLoading || !data) return <Spinner />
  const nombreSede = (s: string) => (s ? s : t('cert.toda_la_organizacion'))
  const columnas: ColumnaTabla<FilaMatriz>[] = [
    { key: 'control', label: t('cert.control'), cabeceraDeFila: true, render: (_v, c) => (
      <div className="cert-celda"><span>{c.titulo}</span><span className="cert-apagado">{c.control}</span></div>) },
    ...data.marcos.map(m => ({ key: `m_${m}`, label: t(`cert.marco_${m}`), sortable: false,
      render: (_v: never, c: FilaMatriz) => c.marcos.filter(x => x.marco === m).map(x => x.id_control).join(', ') || '—' })),
    ...data.sedes.map(s => ({ key: `s_${s}`, label: nombreSede(s), sortable: false,
      render: (_v: never, c: FilaMatriz) => <Estado valor={c.sedes[s]} /> })),
  ]
  const totales = data.marcos.map(m => ({ id: m, marco: m, ...data.totales_por_marco[m] }))
  return (
    <div className="u-stack-16">
      <Card>
        <h3 className="cert-bloque__titulo">{t('cert.totales_por_norma')}</h3>
        <Tabla etiqueta={t('cert.totales_por_norma')} filas={totales} claveDeFila={f => f.id}
          columnas={[{ key: 'marco', label: t('cert.marco'), cabeceraDeFila: true, render: (_v, f) => t(`cert.marco_${f.marco}`) },
            ...ESTADOS_MATRIZ.map(e => ({ key: e, label: t(`cert.estado_${e}`), alinear: 'derecha' as const }))]} />
      </Card>
      <div className="cert-matriz">
        <Tabla<FilaMatriz> etiqueta={t('cert.matriz')} filas={data.controles} claveDeFila={c => c.control_id} cabeceraFija
          densidad="compacta" vacio={{ icono: <Grid3x3 size={28} />, titulo: t('cert.sin_filas') }} columnas={columnas} />
      </div>
    </div>
  )
}
