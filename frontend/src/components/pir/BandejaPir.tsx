/**
 * PIR en la bandeja (pestaña «PIR», migración 206, docs/PIR.md): las que tengo asignadas
 * (responsable o participante) sin terminar y, si puedo aprobar, las enviadas que me
 * tocaría aprobar (sin ser implicado). Las vencidas salen marcadas.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ClipboardCheck } from 'lucide-react'
import { Tabla } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { fmtDate } from '../../utils/helpers'
import { CLAVES_PIR, pirApi } from '../../services/api/pir'
import type { Pir } from '../../services/api/pir'
import { EstadoDePir, OrigenDePir } from './comun'
import FichaDePir from './FichaDePir'
import './Pir.css'

export default function BandejaPir() {
  const t = useAppT()
  const [abierta, setAbierta] = useState<string | null>(null)
  const { data = [], isLoading } = useQuery({ queryKey: CLAVES_PIR.mias, queryFn: () => pirApi.mias() })
  return (
    <div className="u-stack-12">
      <Tabla<Pir>
        etiqueta={t('pir.mis_pir')}
        filas={data}
        cargando={isLoading}
        onFila={p => setAbierta(p.id)}
        claseDeFila={p => (p.vencida ? 'pir-fila--vencida' : undefined)}
        vacio={{ icono: <ClipboardCheck size={28} />, titulo: t('pir.bandeja_vacia'), descripcion: t('pir.bandeja_vacia_desc') }}
        columnas={[
          { key: 'codigo', label: t('pir.codigo'), cabeceraDeFila: true },
          { key: 'titulo', label: t('pir.titulo'), render: (_v, p) => (
            <div className="pir-celda"><span>{p.titulo}</span><OrigenDePir pir={p} /></div>) },
          { key: 'estado', label: t('pir.estado'), render: (_v, p) => <EstadoDePir pir={p} /> },
          { key: 'fecha_prevista', label: t('pir.fecha_prevista'), render: (_v, p) => fmtDate(p.fecha_prevista) },
        ]}
      />
      {abierta && <FichaDePir id={abierta} onClose={() => setAbierta(null)} />}
    </div>
  )
}
