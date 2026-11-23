/**
 * Licencias y hardware — fase 2: uso real (16-11-2026).
 *
 * Pestaña «Uso real» del módulo de licencias: uso, recuperación, ajuste de
 * nivel, cumplimiento, software no controlado y fuentes (esta última solo para
 * administradores). Quien no gestiona ve solo sus licencias en recuperación y
 * puede decir que las sigue necesitando.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, Layers3, PackageSearch, Recycle, ShieldCheck, ShieldHalf } from 'lucide-react'
import { Button, DataTable, EmptyState, Spinner, Tabs } from '../../../components/ui'
import type { ColumnaDeTabla } from '../../../components/ui'
import { pedirTexto } from '../../../context/ConfirmContext'
import { useAuth } from '../../../context/AuthContext'
import { useToast } from '../../../context/ToastContext'
import { useAppT } from '../../../i18n/AppLangContext'
import { almUsoApi } from '../../../services/api/almUso'
import type { Recuperacion } from '../../../services/api/almUso'
import { fmtDate } from '../../../utils/helpers'
import AjustePanel from './AjustePanel'
import CumplimientoPanel from './CumplimientoPanel'
import NoControladoPanel from './NoControladoPanel'
import RecuperacionPanel from './RecuperacionPanel'
import UsoPanel from './UsoPanel'
import { Estado, useErrorDeUso } from './comun'
import './uso.css'

function MisRecuperaciones() {
  const t = useAppT()
  const toast = useToast()
  const fallo = useErrorDeUso()
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['alm-uso-mias'], queryFn: () => almUsoApi.misRecuperaciones() })
  const conservar = useMutation({
    mutationFn: (d: { id: string; motivo: string }) => almUsoApi.conservar(d.id, d.motivo),
    onSuccess: () => { toast.success(t('alm_uso.conservada_ok')); qc.invalidateQueries({ queryKey: ['alm-uso-mias'] }) },
    onError: fallo,
  })
  const columnas: ColumnaDeTabla<Recuperacion>[] = [
    { key: 'licencia', label: t('alm_uso.licencia'), render: (_v, r) => r.licencia || '—' },
    { key: 'dias_sin_uso', label: t('alm_uso.dias_sin_uso') },
    { key: 'estado', label: t('alm_uso.estado_col'), render: (_v, r) => <Estado codigo={r.estado} catalogo="alm_uso.recuperacion" /> },
    { key: 'siguiente_paso_at', label: t('alm_uso.siguiente_paso'), render: (_v, r) => fmtDate(r.siguiente_paso_at) },
    { key: 'acciones', label: t('alm_uso.acciones'), sortable: false, render: (_v, r) => (
      <Button size="xs" icon={<ShieldCheck size={12} />} onClick={async () => {
        const motivo = await pedirTexto({ title: t('alm_uso.conservar_titulo'), message: t('alm_uso.conservar_msg'),
          label: t('alm_uso.motivo_col'), required: true, multiline: true })
        if (motivo) conservar.mutate({ id: r.id, motivo })
      }}>{t('alm_uso.la_sigo_necesitando')}</Button>
    ) },
  ]
  if (isLoading) return <Spinner />
  return (data?.items.length ?? 0) === 0
    ? <EmptyState svgIcon={<ShieldCheck size={28} aria-hidden="true" />} title={t('alm_uso.mias_vacio')} description={t('alm_uso.mias_vacio_desc')} />
    : <DataTable columns={columnas} data={data?.items ?? []} />
}

export default function UsoRealTab() {
  const t = useAppT()
  const { puede } = useAuth()
  const esAdmin = puede('org.administrar')
  const esGestor = esAdmin || puede('equipo.ver')
  const [tab, setTab] = useState('uso')
  if (!esGestor) return <MisRecuperaciones />
  const items = [
    { id: 'uso', label: t('alm_uso.tab_uso'), icon: <Activity size={14} /> },
    { id: 'recuperacion', label: t('alm_uso.tab_recuperacion'), icon: <Recycle size={14} /> },
    { id: 'ajuste', label: t('alm_uso.tab_ajuste'), icon: <Layers3 size={14} /> },
    { id: 'cumplimiento', label: t('alm_uso.tab_cumplimiento'), icon: <ShieldHalf size={14} /> },
    { id: 'no_controlado', label: t('alm_uso.tab_no_controlado'), icon: <PackageSearch size={14} /> },
  ]
  return (
    <div className="u-stack-16">
      <Tabs items={items} active={tab} onChange={setTab} size="sm" variant="underline" ariaLabel={t('alm_uso.tabs_aria')} />
      <div role="tabpanel" aria-label={items.find(i => i.id === tab)?.label}>
        {tab === 'uso' && <UsoPanel />}
        {tab === 'recuperacion' && <RecuperacionPanel />}
        {tab === 'ajuste' && <AjustePanel />}
        {tab === 'cumplimiento' && <CumplimientoPanel />}
        {tab === 'no_controlado' && <NoControladoPanel />}
      </div>
    </div>
  )
}
