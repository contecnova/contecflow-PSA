/**
 * Políticas y reglas (tarea #26): el motor común de gastos, ausencias y lo que
 * venga. Lista por dominio, editor visual de políticas (condiciones, resultados
 * graduados y bandas), tablas de referencia, simulador e historial.
 * Los flujos de aprobación se diseñan gráficamente en «Flujos de aprobación».
 *
 * 16-11-2026: pasada de diseño. Los dominios (Ausencias, Gastos…) con Tabs
 * del kit (antes pastillas rellenas propias); vacío con botón del kit e icono
 * de tamaño estándar; el enlace a «Flujos de aprobación» con el color de
 * acento del tema (antes el azul de enlace del navegador).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { FileText, Plus, Scale, Sparkles, Table2 } from 'lucide-react'
import { politicasApi } from '../services/api'
import { AvisoDeConfiguracion, Button, EmptyState, Page, Spinner, Tabs, Pulsable } from '../components/ui'
import { extractErr } from '../utils/helpers'
import EditorDePolitica from '../components/politicas/EditorDePolitica'
import EditorDeTablas from '../components/politicas/EditorDeTablas'
import EditorDeTiposDeDocumento from '../components/politicas/EditorDeTiposDeDocumento'
import { useToast } from '../context/ToastContext'
import { useCatalogo, useTextos } from '../components/politicas/comun'
import './PoliticasPage.css'

export default function PoliticasPage() {
  const { t } = useTextos()
  const [tab, setTab] = useState('politicas')
  const [abierta, setAbierta] = useState<string | null>(null)
  const [nueva, setNueva] = useState<string | null>(null)
  const catalogo = useCatalogo()
  // `?dominio=ausencias`: las pantallas de cada dominio enlazan aquí con su dominio elegido (rev. 167).
  const [params] = useSearchParams()
  const [dominio, setDominio] = useState<string | null>(params.get('dominio'))
  const actual = dominio ?? catalogo.data?.dominios[0]?.clave ?? null

  if (abierta || nueva) {
    return (
      <Page title={t('pol.modulo')} icon={<Scale size={18} />}>
        <EditorDePolitica key={abierta ?? 'nueva'} id={abierta} nuevoDominio={nueva}
          onVolver={() => { setAbierta(null); setNueva(null) }} onAbrir={id => { setNueva(null); setAbierta(id) }} />
      </Page>
    )
  }
  return (
    <Page title={t('pol.modulo')} subtitle={t('pol.modulo_sub')} icon={<Scale size={18} />}
      actions={tab === 'politicas' && actual
        ? <Button icon={<Plus size={14} />} onClick={() => setNueva(actual)}>{t('pol.nueva_politica')}</Button> : undefined}>
      <Tabs active={tab} onChange={setTab} items={[
        { id: 'politicas', label: t('pol.tab_politicas'), icon: <Scale size={14} /> },
        { id: 'tablas', label: t('pol.tab_tablas'), icon: <Table2 size={14} /> },
        { id: 'documentos', label: t('pol.tab_documentos'), icon: <FileText size={14} /> },
      ]} />
      <div className="pol-mt">
        {tab === 'politicas' && (catalogo.isLoading ? <Spinner label={t('pol.cargando')} />
          : catalogo.isError ? <div role="alert" className="pol-error">{extractErr(catalogo.error, t('pol.error_cargar'))}</div>
          : (
            <>
              {(catalogo.data?.dominios.length ?? 0) > 1 && (
                <Tabs className="polp-dominios" ariaLabel={t('pol.dominio')} active={actual ?? undefined} onChange={setDominio}
                  items={(catalogo.data?.dominios ?? []).map(d => ({ id: d.clave, label: t(`pol.dominio_${d.clave}`) }))} />
              )}
              {actual && catalogo.data?.dominios.find(d => d.clave === actual)?.tiene_ejemplos && <CargarEjemplos dominio={actual} />}
              {actual && <Lista dominio={actual} onAbrir={setAbierta} onNueva={() => setNueva(actual)} />}
              <p className="pol-ayuda pol-mt">{t('pol.flujos_aqui')} <AvisoDeConfiguracion seccion="approval-workflows" variante="enlace" texto={t('pol.ir_a_flujos')} /></p>
            </>
          ))}
        {tab === 'tablas' && <EditorDeTablas />}
        {tab === 'documentos' && <EditorDeTiposDeDocumento />}
      </div>
    </Page>
  )
}

function Lista({ dominio, onAbrir, onNueva }: { dominio: string; onAbrir: (id: string) => void; onNueva: () => void }) {
  const { t } = useTextos()
  const q = useQuery({ queryKey: ['politicas', 'lista', dominio], queryFn: () => politicasApi.listar(dominio) })
  if (q.isLoading) return <Spinner label={t('pol.cargando')} />
  if (q.isError) return <div role="alert" className="pol-error">{extractErr(q.error, t('pol.error_cargar'))}</div>
  const items = q.data ?? []
  if (!items.length) {
    return <EmptyState icon={<Scale size={28} />} title={t('pol.sin_politicas')} description={t('pol.sin_politicas_texto')}
      action={<Button icon={<Plus size={14} />} onClick={onNueva}>{t('pol.nueva_politica')}</Button>} />
  }
  return (
    <div className="pol-lista">
      {items.map(p => (
        <Pulsable key={p.familia_id} className="pol-item" onClick={() => onAbrir(p.id)}>
          <span><strong>{p.nombre}</strong> <span className="pol-ayuda">{p.descripcion}</span></span>
          <span className={`pol-chip pol-chip--${p.estado}`}>{t(`pol.estado_${p.estado}`)} · v{p.version}
            {p.version_publicada && p.version_publicada !== p.version ? ` · ${t('pol.publicada_v', { v: p.version_publicada })}` : ''}</span>
          <span className="pol-chip">{t('pol.prioridad')} {p.prioridad}</span>
          <span className="pol-chip">{p.activa ? t('pol.activa') : t('pol.desactivada')}</span>
        </Pulsable>
      ))}
    </div>
  )
}


/** Rev. 166 (#27): crea las políticas y tablas de ejemplo del dominio como BORRADOR (nunca se aplican solas). */
function CargarEjemplos({ dominio }: { dominio: string }) {
  const { t } = useTextos()
  const toast = useToast()
  const qc = useQueryClient()
  const m = useMutation({
    mutationFn: () => politicasApi.cargarEjemplos(dominio),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ['politicas'] })
      toast.success(r.politicas_creadas || r.tablas_creadas.length
        ? t('pol.ejemplos_cargados', { n: r.politicas_creadas, tablas: r.tablas_creadas.length })
        : t('pol.ejemplos_ya_estaban'))
    },
    onError: e => toast.error(extractErr(e, t('pol.error_guardar'))),
  })
  return (
    <div className="pol-fila pol-mb">
      <Button variant="secondary" size="sm" icon={<Sparkles size={14} />} loading={m.isPending} onClick={() => m.mutate()}>
        {t('pol.cargar_ejemplos')}
      </Button>
      <span className="pol-ayuda">{t('pol.cargar_ejemplos_ayuda')}</span>
    </div>
  )
}
