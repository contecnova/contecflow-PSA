/**
 * Vista del auditor externo (`/auditor/:token`, sin sesión; migración 212, docs/CERTIFICACIONES.md §3.6).
 *
 * Acceso temporal de SOLO LECTURA a un programa: declaración de aplicabilidad, matriz,
 * evidencias (metadatos y huellas), pruebas, auditorías, hallazgos, acciones y certificados.
 * Puede descargar el paquete firmado. Todo lo que consulta queda registrado en el servidor.
 */
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { FileDown, ShieldCheck } from 'lucide-react'
import { Button, Card, EmptyState, Page, Spinner, Tabla, Tabs } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { fmtDate, fmtDateTime } from '../utils/helpers'
import { certPublicoApi } from '../services/api/certificaciones'
import type { Evidencia, FilaSoA, Hallazgo } from '../services/api/certificaciones'
import { Estado, descargarJson } from '../components/certificaciones/comun'

type Pestana = 'aplicabilidad' | 'evidencias' | 'hallazgos'

export default function AuditorPublicoPage(): JSX.Element {
  const t = useAppT()
  const { token = '' } = useParams()
  const [tab, setTab] = useState<Pestana>('aplicabilidad')
  const { data, isLoading, isError } = useQuery({ queryKey: ['cert', 'auditor', token], queryFn: () => certPublicoApi.vista(token),
    retry: false })
  const paquete = useMutation({ mutationFn: () => certPublicoApi.paquete(token),
    onSuccess: d => descargarJson(`${data?.programa.codigo ?? 'programa'}-paquete-auditor.json`, d) })
  if (isLoading) return <Spinner />
  if (isError || !data) return <EmptyState icon={<ShieldCheck size={28} />} title={t('cert.auditor_enlace_no_valido')}
    description={t('cert.auditor_enlace_no_valido_desc')} />
  return (
    <Page icon={<ShieldCheck size={18} />} title={`${data.programa.codigo} · ${data.programa.nombre}`}
      subtitle={t('cert.auditor_subtitulo', { auditor: data.acceso.auditor ?? '', hasta: fmtDateTime(data.acceso.hasta) })}
      rightActions={<Button icon={<FileDown size={14} />} loading={paquete.isPending} onClick={() => paquete.mutate()}>{t('cert.paquete')}</Button>}>
      <Card><p className="cert-apagado">{t('cert.auditor_aviso_registro')}</p></Card>
      <Tabs ariaLabel={t('cert.auditor_vista')} active={tab} onChange={id => setTab(id as Pestana)} items={[
        { id: 'aplicabilidad', label: t('cert.tab_aplicabilidad') },
        { id: 'evidencias', label: t('cert.tab_evidencias') },
        { id: 'hallazgos', label: t('cert.hallazgos_y_capa') },
      ]} />
      {tab === 'aplicabilidad' && (
        <Tabla<FilaSoA> etiqueta={t('cert.aplicabilidad')} filas={data.declaracion_de_aplicabilidad} ordenable
          columnas={[
            { key: 'control', label: t('cert.control'), cabeceraDeFila: true, render: (_v, f) => (
              <div className="cert-celda"><span>{f.titulo}</span><span className="cert-apagado">{f.control}{f.sede ? ` · ${f.sede}` : ''}</span></div>) },
            { key: 'marcos', label: t('cert.marcos'), sortable: false, render: (_v, f) => f.marcos.map(m => `${m.marco} ${m.id_control}`).join(', ') },
            { key: 'aplica', label: t('cert.aplica'), render: (_v, f) => (f.aplica ? t('cert.si') : `${t('cert.no')} · ${f.justificacion ?? ''}`) },
            { key: 'eficacia', label: t('cert.eficacia'), render: (_v, f) => <Estado valor={f.eficacia} /> },
            { key: 'estado_matriz', label: t('cert.situacion'), render: (_v, f) => <Estado valor={f.estado_matriz} /> },
          ]} />
      )}
      {tab === 'evidencias' && (
        <Tabla<Evidencia> etiqueta={t('cert.evidencias')} filas={data.evidencias} ordenable
          columnas={[
            { key: 'titulo', label: t('cert.titulo'), cabeceraDeFila: true },
            { key: 'control', label: t('cert.control') },
            { key: 'estado', label: t('cert.estado'), render: (_v, e) => <Estado valor={e.estado} /> },
            { key: 'sha256', label: t('cert.huella'), render: (_v, e) => e.sha256 ?? '—' },
            { key: 'caduca_el', label: t('cert.caduca'), render: (_v, e) => fmtDate(e.caduca_el) },
          ]} />
      )}
      {tab === 'hallazgos' && (
        <Tabla<Hallazgo> etiqueta={t('cert.hallazgos_y_capa')} filas={data.hallazgos}
          columnas={[
            { key: 'codigo', label: t('cert.codigo'), cabeceraDeFila: true },
            { key: 'tipo', label: t('cert.tipo'), render: (_v, h) => <Estado valor={h.tipo} /> },
            { key: 'titulo', label: t('cert.titulo') },
            { key: 'estado', label: t('cert.estado'), render: (_v, h) => <Estado valor={h.estado} /> },
            { key: 'acciones', label: t('cert.acciones_correctivas'), render: (_v, h) => String(h.acciones?.length ?? 0) },
          ]} />
      )}
    </Page>
  )
}
