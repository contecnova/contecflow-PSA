/**
 * Extensiones del editor del cuaderno (TipTap 3 sobre ProseMirror, con Yjs).
 *
 * Por qué TipTap: es ProseMirror (esquema estricto, JSON validable en el
 * servidor, sin HTML libre) con extensiones pequeñas por función (tablas,
 * casillas, resaltado, enlaces, menciones) y colaboración Yjs oficial
 * (`@tiptap/extension-collaboration` + `@tiptap/y-tiptap`, fork mantenido de
 * y-prosemirror); `yjs` ya estaba instalado. Se carga solo en las pantallas del
 * cuaderno (import diferido de la página y del panel).
 *
 * Nodos propios (los mismos nombres y atributos que valida
 * `app/services/cuaderno/contenido.py`):
 * - `taskItem` con `bid` (id estable de la casilla), `due` (fecha) y `remind` (aviso).
 * - `noteTag`: etiqueta tipo OneNote al principio de un párrafo (clave).
 * - `objectRef` (`#`): tarea, ticket, proyecto o cliente (y lo creado desde la nota).
 * - `mention` (`@`): persona.
 */
import { Extension, mergeAttributes, Node } from '@tiptap/core'
import type { Editor, Range } from '@tiptap/core'
import { ReactNodeViewRenderer, ReactRenderer } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { TaskItem, TaskList } from '@tiptap/extension-list'
import { TableKit } from '@tiptap/extension-table'
import Highlight from '@tiptap/extension-highlight'
import Image from '@tiptap/extension-image'
import Mention from '@tiptap/extension-mention'
import { Placeholder } from '@tiptap/extensions'
import Collaboration from '@tiptap/extension-collaboration'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import type { SuggestionKeyDownProps, SuggestionProps } from '@tiptap/suggestion'
import type * as Y from 'yjs'
import { cuadernoApi } from '../../services/api/cuaderno'
import type { Candidato, Etiqueta } from '../../services/api/cuaderno'
import ChipVivo from './ChipVivo'
import EtiquetaEnLinea from './EtiquetaEnLinea'
import ListaDeSugerencias from './ListaDeSugerencias'
import type { ManejadorDeSugerencias, PropsDeSugerencias } from './ListaDeSugerencias'

export const idCorto = (): string =>
  (globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`)
    .replace(/-/g, '').slice(0, 12)

const attr = (nombre: string) => ({
  default: null,
  keepOnSplit: false,
  parseHTML: (el: HTMLElement) => el.getAttribute(`data-${nombre}`),
  renderHTML: (a: Record<string, unknown>) => (a[nombre] ? { [`data-${nombre}`]: String(a[nombre]) } : {}),
})

/** Casilla con id estable, fecha y aviso. Asigna `bid` a las que no lo tienen (y a las duplicadas al partir). */
export const CasillaDeTarea = TaskItem.extend({
  addAttributes() {
    return { ...this.parent?.(), bid: attr('bid'), due: attr('due'), remind: attr('remind') }
  },
  addProseMirrorPlugins() {
    return [...(this.parent?.() ?? []), new Plugin({
      key: new PluginKey('cuadernoBid'),
      appendTransaction: (trs, _viejo, estado) => {
        if (!trs.some(t => t.docChanged)) return null
        const tr = estado.tr
        const vistos = new Set<string>()
        let cambio = false
        estado.doc.descendants((n, pos) => {
          if (n.type.name !== 'taskItem') return
          const bid = n.attrs.bid as string | null
          if (!bid || vistos.has(bid)) {
            tr.setNodeMarkup(pos, undefined, { ...n.attrs, bid: idCorto() })
            cambio = true
          } else {
            vistos.add(bid)
          }
        })
        return cambio ? tr.setMeta('addToHistory', false) : null
      },
    })]
  },
})

/** Etiqueta tipo OneNote (Pendiente, Importante, Pregunta, Idea, Llamar a…). */
export const EtiquetaDeNota = Node.create<{ etiquetas: () => Etiqueta[] }>({
  name: 'noteTag',
  group: 'inline',
  inline: true,
  atom: true,
  selectable: true,
  addOptions() { return { etiquetas: () => [] } },
  addAttributes() {
    return { key: { default: 'todo', parseHTML: el => el.getAttribute('data-note-tag'), renderHTML: a => ({ 'data-note-tag': a.key }) } }
  },
  parseHTML() { return [{ tag: 'span[data-note-tag]' }] },
  renderHTML({ HTMLAttributes }) { return ['span', mergeAttributes(HTMLAttributes, { class: 'cdn-etiqueta' })] },
  renderText({ node }) { return `[${node.attrs.key}] ` },
  addNodeView() { return ReactNodeViewRenderer(EtiquetaEnLinea) },
})

type Tipos = 'task,ticket,project,client' | 'user'

/** Sugerencias en una capa flotante junto al cursor. */
function sugerencias(tipos: Tipos, char: string, nodo: 'objectRef' | 'mention') {
  return {
    char,
    allowSpaces: false,
    items: async ({ query }: { query: string }): Promise<Candidato[]> => {
      try { return (await cuadernoApi.referencias(query, tipos)).slice(0, 12) } catch { return [] }
    },
    // Mention tipa `props` como sus atributos; aquí llega el Candidato elegido en la lista.
    command: ({ editor, range, props: elegido }: { editor: Editor; range: Range; props: unknown }) => {
      const props = elegido as Candidato
      const attrs = nodo === 'mention' ? { id: props.id, label: props.label } : { type: props.type, id: props.id, label: props.label }
      editor.chain().focus().insertContentAt(range, [{ type: nodo, attrs }, { type: 'text', text: ' ' }]).run()
    },
    render: () => {
      let r: ReactRenderer<ManejadorDeSugerencias, PropsDeSugerencias> | null = null
      let capa: HTMLDivElement | null = null
      const colocar = (p: SuggestionProps<Candidato>) => {
        const rect = p.clientRect?.()
        if (!capa || !rect) return
        capa.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - 320))}px`
        capa.style.top = `${rect.bottom + 6}px`
      }
      return {
        onStart: (p: SuggestionProps<Candidato>) => {
          r = new ReactRenderer(ListaDeSugerencias, { props: { items: p.items, command: p.command }, editor: p.editor })
          capa = document.createElement('div')
          capa.className = 'cdn-sugerencias'
          capa.appendChild(r.element)
          document.body.appendChild(capa)
          colocar(p)
        },
        onUpdate: (p: SuggestionProps<Candidato>) => {
          r?.updateProps({ items: p.items, command: p.command })
          colocar(p)
        },
        onKeyDown: (p: SuggestionKeyDownProps) => {
          if (p.event.key === 'Escape') { capa?.remove(); return true }
          return r?.ref?.onKeyDown({ event: p.event }) ?? false
        },
        onExit: () => { capa?.remove(); capa = null; r?.destroy(); r = null },
      }
    },
  }
}

/** `#`: tarea, ticket, proyecto, cliente (y demanda, idea, recordatorio creados desde la nota). */
export const ReferenciaAObjeto = Mention.extend({
  name: 'objectRef',
  addAttributes() {
    return {
      type: { default: 'task', parseHTML: el => el.getAttribute('data-ref-type'), renderHTML: a => ({ 'data-ref-type': a.type }) },
      id: { default: null, parseHTML: el => el.getAttribute('data-id'), renderHTML: a => ({ 'data-id': a.id }) },
      label: { default: null, parseHTML: el => el.getAttribute('data-label'), renderHTML: a => ({ 'data-label': a.label }) },
    }
  },
  parseHTML() { return [{ tag: 'span[data-ref-type]' }] },
  addNodeView() { return ReactNodeViewRenderer(ChipVivo) },
}).configure({
  renderText: ({ node }) => `#${node.attrs.label ?? node.attrs.id}`,
  suggestion: sugerencias('task,ticket,project,client', '#', 'objectRef'),
})

/** `@`: persona. */
export const MencionDePersona = Mention.extend({
  addNodeView() { return ReactNodeViewRenderer(ChipVivo) },
}).configure({
  renderText: ({ node }) => `@${node.attrs.label ?? node.attrs.id}`,
  suggestion: sugerencias('user', '@', 'mention'),
})

/** Pegar o soltar imágenes: se suben como adjuntos (validador de subidas) y se insertan. */
export function PegarImagenes(subir: (f: File) => Promise<string | null>) {
  return Extension.create({
    name: 'cuadernoPegarImagenes',
    addProseMirrorPlugins() {
      const editor = this.editor
      const manejar = (ficheros: File[]) => {
        const imagenes = ficheros.filter(f => /^image\/(png|jpe?g|gif|webp)$/.test(f.type))
        if (!imagenes.length) return false
        for (const f of imagenes) {
          void subir(f).then(src => { if (src) editor.chain().focus().setImage({ src, alt: f.name }).run() })
        }
        return true
      }
      return [new Plugin({
        key: new PluginKey('cuadernoPegarImagenes'),
        props: {
          handlePaste: (_v, e) => manejar(Array.from(e.clipboardData?.files ?? [])),
          handleDrop: (_v, e) => manejar(Array.from((e as DragEvent).dataTransfer?.files ?? [])),
        },
      })]
    },
  })
}

export interface OpcionesDelEditor {
  ydoc: Y.Doc
  etiquetas: () => Etiqueta[]
  marcador: string
  subirImagen: (f: File) => Promise<string | null>
}

/** Todas las extensiones del editor, en el orden en que se registran. */
export function extensionesDelCuaderno(o: OpcionesDelEditor) {
  return [
    // Con Yjs el deshacer lo lleva la colaboración: el de StarterKit se apaga.
    StarterKit.configure({ undoRedo: false, link: { openOnClick: false, autolink: true, protocols: ['http', 'https', 'mailto'] } }),
    TaskList,
    CasillaDeTarea.configure({ nested: true }),
    TableKit.configure({ table: { resizable: false } }),
    Highlight.configure({ multicolor: true }),
    Image.configure({ inline: false, allowBase64: false }),
    Placeholder.configure({ placeholder: o.marcador }),
    EtiquetaDeNota.configure({ etiquetas: o.etiquetas }),
    ReferenciaAObjeto,
    MencionDePersona,
    PegarImagenes(o.subirImagen),
    Collaboration.configure({ document: o.ydoc, field: 'default' }),
  ]
}
