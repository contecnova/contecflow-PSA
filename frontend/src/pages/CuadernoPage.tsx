/**
 * «Mi cuaderno» (`/notebook`, Mi trabajo): cuadernos → secciones → páginas a la
 * izquierda y el editor a la derecha; pestaña «Tareas y etiquetas» con lo
 * pendiente de todos los cuadernos. Privado por defecto (docs/CUADERNO.md).
 *
 * URL: `?page=<id>` abre una página (lo usan la búsqueda global, los avisos y
 * los enlaces de vuelta), `?tab=tasks` la vista de tareas, `?notebook=<id>`
 * despliega un cuaderno compartido.
 */
import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { CheckSquare, CloudOff, NotebookPen, Plus, Trash2 } from 'lucide-react'
import { Buscador, Button, EmptyState, IconButton, Page, Pulsable, Spinner, Tabs } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { useToast } from '../context/ToastContext'
import { pedirTexto } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { cuadernoApi, CLAVES_CUADERNO } from '../services/api/cuaderno'
import ArbolDeCuadernos from '../components/cuaderno/ArbolDeCuadernos'
import EditorDeNota from '../components/cuaderno/EditorDeNota'
import TodasMisTareas from '../components/cuaderno/TodasMisTareas'
import ModalPapelera from '../components/cuaderno/ModalPapelera'
import { useSinRed } from '../components/cuaderno/useSinRed'
import '../components/cuaderno/cuaderno.css'

export default function CuadernoPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const pageId = params.get('page')
  const tab = params.get('tab') === 'tasks' ? 'tasks' : 'notes'
  const [seccion, setSeccion] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [papelera, setPapelera] = useState(false)
  const { enLinea, pendientes } = useSinRed()
  const { data: arbol, isLoading } = useQuery({ queryKey: CLAVES_CUADERNO.arbol, queryFn: cuadernoApi.arbol })
  const { data: resultados = [], isFetching: buscando } = useQuery({
    queryKey: ['cuaderno', 'buscar', q], queryFn: () => cuadernoApi.buscar(q), enabled: q.trim().length >= 2,
  })

  // La sección activa: la de la página abierta o la primera del primer cuaderno.
  const seccionDePagina = useMemo(() => {
    if (!arbol || !pageId) return null
    for (const nb of arbol.notebooks) for (const s of nb.sections) if (s.pages.some(p => p.id === pageId)) return s.id
    return null
  }, [arbol, pageId])
  useEffect(() => {
    if (seccionDePagina) setSeccion(seccionDePagina)
    else if (!seccion && arbol?.notebooks[0]?.sections[0]) setSeccion(arbol.notebooks[0].sections[0].id)
  }, [seccionDePagina, arbol, seccion])

  const irA = (nuevo: Record<string, string | null>) => {
    const p = new URLSearchParams(params)
    for (const [k, v] of Object.entries(nuevo)) { if (v) p.set(k, v); else p.delete(k) }
    setParams(p, { replace: false })
  }
  const nuevoCuaderno = async () => {
    const titulo = await pedirTexto({ message: t('cuaderno.nombre_de_cuaderno'), required: true })
    if (!titulo?.trim()) return
    try {
      await cuadernoApi.crearCuaderno({ title: titulo.trim(), section_title: t('cuaderno.seccion_inicial') })
      await qc.invalidateQueries({ queryKey: CLAVES_CUADERNO.arbol })
    } catch (e) { toast.error(extractErr(e)) }
  }

  return (
    <Page icon={<NotebookPen size={18} />} title={t('nav.notebook')} subtitle={t('cuaderno.subtitulo')}
      actions={(
        <div className="cdn-cabecera-acciones">
          {!enLinea && <span className="cdn-sin-red" role="status"><CloudOff size={13} aria-hidden />{t('cuaderno.sin_red', { n: pendientes })}</span>}
          <IconButton ariaLabel={t('cuaderno.papelera_con', { n: arbol?.trash_count ?? 0 })} title={t('cuaderno.papelera')} onClick={() => setPapelera(true)} className="cdn-boton">
            <Trash2 size={15} />
          </IconButton>
          <Button icon={<Plus size={14} />} onClick={() => { void nuevoCuaderno() }}>{t('cuaderno.nuevo_cuaderno')}</Button>
        </div>
      )}>
      <Tabs ariaLabel={t('nav.notebook')} active={tab} onChange={id => irA({ tab: id === 'tasks' ? 'tasks' : null })} items={[
        { id: 'notes', label: t('cuaderno.notas'), icon: <NotebookPen size={14} /> },
        { id: 'tasks', label: t('cuaderno.tareas_y_etiquetas'), icon: <CheckSquare size={14} /> },
      ]} />
      {tab === 'tasks' ? <TodasMisTareas /> : (
        <div className="cdn-pagina">
          <aside className="cdn-pagina__lateral" aria-label={t('cuaderno.arbol')}>
            <Buscador value={q} onChange={setQ} retardo={300} placeholder={t('cuaderno.buscar')} aria-label={t('cuaderno.buscar')} />
            {q.trim().length >= 2 ? (
              <div className="cdn-resultados" role="region" aria-label={t('cuaderno.resultados')} aria-busy={buscando}>
                {resultados.length === 0 && !buscando && <p className="cdn-ayuda">{t('cuaderno.sin_resultados')}</p>}
                {resultados.map(r => (
                  <Pulsable key={r.id} className="cdn-resultado" onClick={() => { setQ(''); setSeccion(r.section_id); irA({ page: r.id, tab: null }) }}>
                    <strong>{r.title || t('cuaderno.sin_titulo')}</strong>
                    <span className="cdn-lista__sub">{[r.notebook_title, r.section_title].filter(Boolean).join(' › ')}</span>
                    {r.snippet && <span className="cdn-resultado__fragmento">{r.snippet}</span>}
                  </Pulsable>
                ))}
              </div>
            ) : isLoading || !arbol ? <Spinner /> : (
              <ArbolDeCuadernos arbol={arbol} paginaActiva={pageId} seccionActiva={seccion}
                onPagina={(id, s) => { setSeccion(s); irA({ page: id }) }} onSeccion={setSeccion} />
            )}
          </aside>
          <section className="cdn-pagina__principal" aria-label={t('cuaderno.pagina')}>
            {pageId && arbol ? (
              <EditorDeNota key={pageId} pageId={pageId} etiquetas={arbol.tags} funciones={arbol.features}
                onCambioDeTitulo={() => { /* el árbol se refresca al guardar */ }}
                onBorrada={() => irA({ page: null })} />
            ) : (
              <EmptyState icon={<NotebookPen size={28} />} title={t('cuaderno.elige_pagina')} description={t('cuaderno.elige_pagina_ayuda')} />
            )}
          </section>
        </div>
      )}
      {papelera && <ModalPapelera onClose={() => setPapelera(false)} />}
    </Page>
  )
}
