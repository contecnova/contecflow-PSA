/**
 * Árbol del cuaderno: cuadernos → secciones (pestañas de color) → páginas y
 * subpáginas. Orden libre arrastrando (páginas entre sí o sobre una sección) y,
 * para teclado y lectores de pantalla, con botones del menú de cada elemento
 * (subir, bajar, convertir en subpágina, sacar de la subpágina, mover).
 */
import { useMemo, useState } from 'react'
import type { CSSProperties, DragEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowDown, ArrowUp, ChevronDown, ChevronRight, Download, FilePlus, FolderPlus, IndentDecrease, IndentIncrease,
  MoreHorizontal, Palette, Pencil, Share2, Trash2,
} from 'lucide-react'
import { Pulsable } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { confirmar, pedirTexto } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { cuadernoApi, CLAVES_CUADERNO } from '../../services/api/cuaderno'
import type { Arbol, Cuaderno, PaginaCorta, Seccion } from '../../services/api/cuaderno'
import { COLORES, descargarExportacion, puedeEscribir } from './comun'
import Menu from './Menu'
import type { OpcionDeMenu } from './Menu'
import ModalCompartir from './ModalCompartir'

interface Props {
  arbol: Arbol
  paginaActiva: string | null
  seccionActiva: string | null
  onPagina: (pageId: string, sectionId: string) => void
  onSeccion: (sectionId: string) => void
}

const ordenar = <T extends { sort_order: number }>(xs: T[]) => [...xs].sort((a, b) => a.sort_order - b.sort_order)

/** Hermanas de una página (mismo padre), en orden. */
function hermanas(pages: PaginaCorta[], parent: string | null) {
  return ordenar(pages.filter(p => (p.parent_id || null) === parent))
}

export default function ArbolDeCuadernos({ arbol, paginaActiva, seccionActiva, onPagina, onSeccion }: Props) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [abiertos, setAbiertos] = useState<Set<string>>(() => new Set(arbol.notebooks.map(n => n.id)))
  const [compartiendo, setCompartiendo] = useState<{ nb: Cuaderno; seccion?: string | null } | null>(null)
  const [arrastrando, setArrastrando] = useState<string | null>(null)
  const { data: plantillas = [] } = useQuery({ queryKey: CLAVES_CUADERNO.plantillas, queryFn: cuadernoApi.plantillas, staleTime: 300_000 })
  const refrescar = () => qc.invalidateQueries({ queryKey: CLAVES_CUADERNO.arbol })
  const hacer = async (f: () => Promise<unknown>, ok?: string) => {
    try { await f(); await refrescar(); if (ok) toast.success(ok) } catch (e) { toast.error(extractErr(e)) }
  }
  const propios = useMemo(() => ordenar(arbol.notebooks.filter(n => n.permission === 'owner')), [arbol])

  const renombrar = async (actual: string, guardar: (v: string) => Promise<unknown>) => {
    const v = await pedirTexto({ message: t('cuaderno.nuevo_nombre'), defaultValue: actual, required: true })
    if (v && v.trim() && v.trim() !== actual) await hacer(() => guardar(v.trim()))
  }
  const mover = async <T extends { id: string; sort_order: number }>(kind: 'notebook' | 'section' | 'page', lista: T[], id: string, paso: -1 | 1) => {
    const xs = ordenar(lista)
    const i = xs.findIndex(x => x.id === id)
    const j = i + paso
    if (i < 0 || j < 0 || j >= xs.length) return
    ;[xs[i], xs[j]] = [xs[j], xs[i]]
    await hacer(() => cuadernoApi.reordenar(kind, xs.map(x => x.id)))
  }
  const nuevaPagina = async (s: Seccion, padre?: string, plantilla?: string) => {
    try {
      const p = await cuadernoApi.crearPagina(s.id, { title: '', parent_id: padre, template_key: plantilla })
      await refrescar()
      onPagina(p.id, s.id)
    } catch (e) { toast.error(extractErr(e)) }
  }
  const exportar = (kind: 'section' | 'notebook', id: string, nombre: string, f: 'md' | 'pdf') =>
    descargarExportacion(kind, id, f, nombre).catch(e => toast.error(extractErr(e)))

  // ── Arrastrar páginas ──────────────────────────────────────────────────────
  const soltarEnPagina = (s: Seccion, destino: PaginaCorta) => async (e: DragEvent) => {
    e.preventDefault()
    const id = arrastrando || e.dataTransfer.getData('text/x-cuaderno-pagina')
    setArrastrando(null)
    if (!id || id === destino.id) return
    const enSeccion = s.pages.find(p => p.id === id)
    const padre = destino.parent_id || null
    if (!enSeccion || (enSeccion.parent_id || null) !== padre) {
      await hacer(() => cuadernoApi.moverPagina(id, padre ? { section_id: s.id, parent_id: padre } : { section_id: s.id, detach: true }))
    }
    const lista = hermanas(s.pages, padre).filter(p => p.id !== id).map(p => p.id)
    lista.splice(lista.indexOf(destino.id), 0, id)
    await hacer(() => cuadernoApi.reordenar('page', lista))
  }
  const soltarEnSeccion = (s: Seccion) => async (e: DragEvent) => {
    e.preventDefault()
    const id = arrastrando || e.dataTransfer.getData('text/x-cuaderno-pagina')
    setArrastrando(null)
    if (id) await hacer(() => cuadernoApi.moverPagina(id, { section_id: s.id, detach: true, sort_order: 9999 }))
  }

  const opcionesDePagina = (s: Seccion, p: PaginaCorta): OpcionDeMenu[] => {
    const hs = hermanas(s.pages, p.parent_id || null)
    const i = hs.findIndex(x => x.id === p.id)
    const padre = p.parent_id ? s.pages.find(x => x.id === p.parent_id) : null
    return [
      { id: 'sub', label: t('cuaderno.nueva_subpagina'), icon: <FilePlus size={13} />, onSelect: () => { void nuevaPagina(s, p.id) } },
      { id: 'up', label: t('cuaderno.subir'), icon: <ArrowUp size={13} />, disabled: i <= 0, onSelect: () => { void mover('page', hs, p.id, -1) } },
      { id: 'down', label: t('cuaderno.bajar'), icon: <ArrowDown size={13} />, disabled: i >= hs.length - 1, onSelect: () => { void mover('page', hs, p.id, 1) } },
      { id: 'in', label: t('cuaderno.hacer_subpagina'), icon: <IndentIncrease size={13} />, disabled: i <= 0,
        onSelect: () => { void hacer(() => cuadernoApi.moverPagina(p.id, { parent_id: hs[i - 1].id })) } },
      { id: 'out', label: t('cuaderno.sacar_de_subpagina'), icon: <IndentDecrease size={13} />, disabled: !padre,
        onSelect: () => { void hacer(() => cuadernoApi.moverPagina(p.id, padre?.parent_id ? { parent_id: padre.parent_id } : { detach: true })) } },
      { id: 'del', label: t('cuaderno.borrar_pagina'), icon: <Trash2 size={13} />, peligro: true, onSelect: async () => {
        if (await confirmar({ message: t('cuaderno.borrar_pagina_confirmar'), danger: true })) await hacer(() => cuadernoApi.borrarPagina(p.id), t('cuaderno.a_la_papelera'))
      } },
    ]
  }

  const pintarPaginas = (s: Seccion, padre: string | null, nivel: number) => hermanas(s.pages, padre).map(p => (
    <li key={p.id} className="cdn-arbol__pagina" style={{ '--cdn-nivel': nivel } as CSSProperties}
      draggable={puedeEscribir(s.permission)}
      onDragStart={e => { e.dataTransfer.setData('text/x-cuaderno-pagina', p.id); e.dataTransfer.effectAllowed = 'move'; setArrastrando(p.id) }}
      onDragOver={e => { if (arrastrando) e.preventDefault() }}
      onDrop={e => { void soltarEnPagina(s, p)(e) }}>
      <div className={`cdn-arbol__fila${p.id === paginaActiva ? ' cdn-arbol__fila--activa' : ''}`}>
        <Pulsable className="cdn-arbol__nombre" aria-current={p.id === paginaActiva ? 'page' : undefined} onClick={() => onPagina(p.id, s.id)}>
          {p.title || t('cuaderno.sin_titulo')}
        </Pulsable>
        {puedeEscribir(s.permission) && <Menu etiqueta={t('cuaderno.acciones_de', { nombre: p.title || t('cuaderno.sin_titulo') })} icono={<MoreHorizontal size={13} />} opciones={opcionesDePagina(s, p)} alinear="derecha" />}
      </div>
      {s.pages.some(x => x.parent_id === p.id) && <ul className="cdn-arbol__lista">{pintarPaginas(s, p.id, nivel + 1)}</ul>}
    </li>
  ))

  const opcionesDeSeccion = (nb: Cuaderno, s: Seccion, secs: Seccion[]): OpcionDeMenu[] => {
    const escribe = puedeEscribir(s.permission)
    const op: OpcionDeMenu[] = []
    if (escribe) {
      op.push({ id: 'new', label: t('cuaderno.nueva_pagina'), icon: <FilePlus size={13} />, onSelect: () => { void nuevaPagina(s) } })
      for (const pl of plantillas) op.push({ id: `tpl-${pl.key}`, label: t('cuaderno.desde_plantilla', { plantilla: pl.name }), icon: <FilePlus size={13} />, onSelect: () => { void nuevaPagina(s, undefined, pl.key) } })
      op.push({ id: 'ren', label: t('cuaderno.renombrar'), icon: <Pencil size={13} />, onSelect: () => { void renombrar(s.title, v => cuadernoApi.editarSeccion(s.id, { title: v })) } })
      for (const c of COLORES) op.push({ id: `c-${c}`, label: t('cuaderno.color_de', { color: t(`cuaderno.color_${c}`) }), icon: <Palette size={13} className={`cdn-color--${c}`} />, onSelect: () => { void hacer(() => cuadernoApi.editarSeccion(s.id, { color: c })) } })
      op.push({ id: 'up', label: t('cuaderno.subir'), icon: <ArrowUp size={13} />, onSelect: () => { void mover('section', secs, s.id, -1) } })
      op.push({ id: 'down', label: t('cuaderno.bajar'), icon: <ArrowDown size={13} />, onSelect: () => { void mover('section', secs, s.id, 1) } })
    }
    if (nb.permission === 'owner') {
      op.push({ id: 'share', label: t('cuaderno.compartir_seccion'), icon: <Share2 size={13} />, onSelect: () => setCompartiendo({ nb, seccion: s.id }) })
      for (const otro of propios.filter(x => x.id !== nb.id && !x.is_quick)) {
        op.push({ id: `mv-${otro.id}`, label: t('cuaderno.mover_a', { cuaderno: otro.title }), icon: <FolderPlus size={13} />, onSelect: () => { void hacer(() => cuadernoApi.editarSeccion(s.id, { notebook_id: otro.id })) } })
      }
    }
    op.push({ id: 'md', label: t('cuaderno.exportar_md'), icon: <Download size={13} />, onSelect: () => { void exportar('section', s.id, s.title, 'md') } })
    op.push({ id: 'pdf', label: t('cuaderno.exportar_pdf'), icon: <Download size={13} />, onSelect: () => { void exportar('section', s.id, s.title, 'pdf') } })
    if (escribe) op.push({ id: 'del', label: t('cuaderno.borrar_seccion'), icon: <Trash2 size={13} />, peligro: true, onSelect: async () => {
      if (await confirmar({ message: t('cuaderno.borrar_seccion_confirmar', { nombre: s.title }), danger: true })) await hacer(() => cuadernoApi.borrarSeccion(s.id), t('cuaderno.a_la_papelera'))
    } })
    return op
  }

  const opcionesDeCuaderno = (nb: Cuaderno): OpcionDeMenu[] => {
    const op: OpcionDeMenu[] = []
    if (puedeEscribir(nb.permission)) op.push({ id: 'sec', label: t('cuaderno.nueva_seccion'), icon: <FolderPlus size={13} />, onSelect: async () => {
      const v = await pedirTexto({ message: t('cuaderno.nombre_de_seccion'), required: true })
      if (v?.trim()) await hacer(() => cuadernoApi.crearSeccion(nb.id, { title: v.trim(), color: COLORES[nb.sections.length % COLORES.length] }))
    } })
    if (nb.permission === 'owner') {
      op.push({ id: 'ren', label: t('cuaderno.renombrar'), icon: <Pencil size={13} />, onSelect: () => { void renombrar(nb.title, v => cuadernoApi.editarCuaderno(nb.id, { title: v })) } })
      if (!nb.is_quick) op.push({ id: 'share', label: t('cuaderno.compartir_cuaderno'), icon: <Share2 size={13} />, onSelect: () => setCompartiendo({ nb }) })
      op.push({ id: 'up', label: t('cuaderno.subir'), icon: <ArrowUp size={13} />, onSelect: () => { void mover('notebook', propios, nb.id, -1) } })
      op.push({ id: 'down', label: t('cuaderno.bajar'), icon: <ArrowDown size={13} />, onSelect: () => { void mover('notebook', propios, nb.id, 1) } })
    }
    op.push({ id: 'md', label: t('cuaderno.exportar_md'), icon: <Download size={13} />, onSelect: () => { void exportar('notebook', nb.id, nb.title, 'md') } })
    op.push({ id: 'pdf', label: t('cuaderno.exportar_pdf'), icon: <Download size={13} />, onSelect: () => { void exportar('notebook', nb.id, nb.title, 'pdf') } })
    if (nb.permission === 'owner') op.push({ id: 'del', label: t('cuaderno.borrar_cuaderno'), icon: <Trash2 size={13} />, peligro: true, onSelect: async () => {
      if (await confirmar({ message: t('cuaderno.borrar_cuaderno_confirmar', { nombre: nb.title }), danger: true })) await hacer(() => cuadernoApi.borrarCuaderno(nb.id), t('cuaderno.a_la_papelera'))
    } })
    return op
  }

  return (
    <nav className="cdn-arbol" aria-label={t('cuaderno.arbol')}>
      <ul className="cdn-arbol__lista">
        {arbol.notebooks.map(nb => {
          const abierto = abiertos.has(nb.id)
          const secs = ordenar(nb.sections)
          return (
            <li key={nb.id} className="cdn-arbol__cuaderno">
              <div className="cdn-arbol__fila cdn-arbol__fila--cuaderno">
                <Pulsable className="cdn-arbol__nombre" aria-expanded={abierto}
                  onClick={() => setAbiertos(a => { const n = new Set(a); if (n.has(nb.id)) n.delete(nb.id); else n.add(nb.id); return n })}>
                  {abierto ? <ChevronDown size={13} aria-hidden /> : <ChevronRight size={13} aria-hidden />}
                  <span className={`cdn-punto cdn-color--${nb.color || 'blue'}`} aria-hidden />
                  <span className="cdn-arbol__titulo">{nb.title}</span>
                  {nb.permission !== 'owner' && <span className="cdn-arbol__dueno">{nb.owner_name}</span>}
                  {nb.shared && nb.permission === 'owner' && <Share2 size={11} aria-label={t('cuaderno.compartido')} />}
                </Pulsable>
                <Menu etiqueta={t('cuaderno.acciones_de', { nombre: nb.title })} icono={<MoreHorizontal size={13} />} opciones={opcionesDeCuaderno(nb)} alinear="derecha" />
              </div>
              {abierto && (
                <ul className="cdn-arbol__lista">
                  {secs.map(s => (
                    <li key={s.id} className={`cdn-arbol__seccion cdn-color--${s.color || 'gray'}`}
                      onDragOver={e => { if (arrastrando) e.preventDefault() }} onDrop={e => { void soltarEnSeccion(s)(e) }}>
                      <div className={`cdn-arbol__fila cdn-arbol__pestana${s.id === seccionActiva ? ' cdn-arbol__fila--activa' : ''}`}>
                        <Pulsable className="cdn-arbol__nombre" aria-current={s.id === seccionActiva ? 'true' : undefined} onClick={() => onSeccion(s.id)}>
                          <span className="cdn-arbol__titulo">{s.title}</span>
                          <span className="cdn-arbol__cuenta">{s.pages.length}</span>
                        </Pulsable>
                        <Menu etiqueta={t('cuaderno.acciones_de', { nombre: s.title })} icono={<MoreHorizontal size={13} />} opciones={opcionesDeSeccion(nb, s, secs)} alinear="derecha" />
                      </div>
                      {s.id === seccionActiva && (
                        <ul className="cdn-arbol__lista">
                          {pintarPaginas(s, null, 0)}
                          {puedeEscribir(s.permission) && (
                            <li><Pulsable className="cdn-arbol__nueva" onClick={() => { void nuevaPagina(s) }}><FilePlus size={12} aria-hidden />{t('cuaderno.nueva_pagina')}</Pulsable></li>
                          )}
                        </ul>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          )
        })}
      </ul>
      {compartiendo && <ModalCompartir cuaderno={compartiendo.nb} seccionId={compartiendo.seccion} permitido={arbol.features.sharing} onClose={() => setCompartiendo(null)} />}
    </nav>
  )
}
