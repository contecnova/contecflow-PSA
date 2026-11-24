/**
 * Editor de una página del cuaderno: título, barra de herramientas, texto rico
 * (TipTap + Yjs), guardado automático con indicador, sin conexión, edición
 * simultánea si la página está compartida, adjuntos, dibujos, voz, IA, de nota a
 * acción y exportar. Se monta con `key={pageId}` (un Y.Doc por página).
 *
 * Guardado: 1,2 s después de dejar de escribir (y al salir). Sin red, el cambio
 * queda en la cola de ESTA persona y empresa (`colaOffline`) y se manda al volver.
 * Si la página cambió entretanto, lo escrito se guarda como copia aparte.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { EditorContent, useEditor } from '@tiptap/react'
import type { Editor } from '@tiptap/core'
import { isChangeOrigin } from '@tiptap/extension-collaboration'
import * as Y from 'yjs'
import {
  Bold, Brain, CalendarClock, CheckSquare, CloudOff, Download, Heading1, Heading2, Heading3, Highlighter, Italic, Link2,
  List, ListOrdered, Mic, Paperclip, PenTool, Redo2, Square, Strikethrough, Table2, Tag, Trash2, Underline, Undo2, Users, Zap,
} from 'lucide-react'
import { Button, CampoFecha, IconButton, Input, Modal, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { confirmar, pedirTexto } from '../../context/ConfirmContext'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { cuadernoApi, CLAVES_CUADERNO } from '../../services/api/cuaderno'
import type { Adjunto, Chip, DocJSON, Etiqueta, Pagina } from '../../services/api/cuaderno'
import { extensionesDelCuaderno } from './extensiones'
import { aBase64, deBase64, useColaboracion } from './useColaboracion'
import { encolar, esErrorDeRed, guardarCopia, leerCopia } from './colaOffline'
import { descargarExportacion, IconoDeEtiqueta, nombreDeEtiqueta, puedeEscribir } from './comun'
import Menu from './Menu'
import ModalAccion from './ModalAccion'
import type { OrigenDeAccion } from './ModalAccion'
import ModalDibujo from './ModalDibujo'
import type { Dibujo } from '../../services/api/cuaderno'

type Estado = 'cargando' | 'guardado' | 'pendiente' | 'guardando' | 'sin_red' | 'error' | 'solo_lectura'
const ESPERA_MS = 1200
const ORIGEN_CARGA = 'cuaderno-carga'

/** Texto plano de la IA → nodos (## título, - viñeta, el resto párrafos). */
function textoANodos(texto: string): DocJSON[] {
  const nodos: DocJSON[] = []
  let lista: DocJSON | null = null
  for (const linea of texto.split('\n')) {
    const l = linea.trim()
    if (!l) { lista = null; continue }
    const titulo = l.match(/^#{1,3}\s+(.*)$/)
    const vineta = l.match(/^[-*•]\s+(.*)$/)
    if (titulo) {
      lista = null
      nodos.push({ type: 'heading', attrs: { level: 3 }, content: [{ type: 'text', text: titulo[1] }] })
    } else if (vineta) {
      if (!lista) { lista = { type: 'bulletList', content: [] }; nodos.push(lista) }
      lista.content!.push({ type: 'listItem', content: [{ type: 'paragraph', content: [{ type: 'text', text: vineta[1] }] }] })
    } else {
      lista = null
      nodos.push({ type: 'paragraph', content: [{ type: 'text', text: l }] })
    }
  }
  return nodos
}

function BotonDeBarra({ etiqueta, activo, onClick, children, apagado }: {
  etiqueta: string; activo?: boolean; onClick: () => void; children: ReactNode; apagado?: boolean
}) {
  return (
    <IconButton ariaLabel={etiqueta} title={etiqueta} aria-pressed={activo} onClick={onClick} disabled={apagado}
      className={`cdn-boton${activo ? ' cdn-boton--activo' : ''}`}>{children}</IconButton>
  )
}

export interface PropsDelEditor {
  pageId: string
  etiquetas: Etiqueta[]
  funciones?: { ai: boolean; voice: boolean }
  compacto?: boolean
  onCambioDeTitulo?: (titulo: string) => void
  onBorrada?: () => void
}

export default function EditorDeNota({ pageId, etiquetas, funciones = { ai: true, voice: true }, compacto, onCambioDeTitulo, onBorrada }: PropsDelEditor) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const ydoc = useMemo(() => new Y.Doc(), [])
  const [pagina, setPagina] = useState<Pagina | null>(null)
  const [titulo, setTitulo] = useState('')
  const [estado, setEstado] = useState<Estado>('cargando')
  const [guardadoEn, setGuardadoEn] = useState<string | null>(null)
  const [adjuntos, setAdjuntos] = useState<Adjunto[]>([])
  const [accion, setAccion] = useState<OrigenDeAccion | null>(null)
  const [dibujo, setDibujo] = useState<{ id?: string; inicial?: Dibujo | null } | null>(null)
  const [guardandoDibujo, setGuardandoDibujo] = useState(false)
  const [ia, setIa] = useState<{ accion: string; texto: string | null; tareas: { text: string; due_date: string | null }[] } | null>(null)
  const [iaCargando, setIaCargando] = useState(false)
  const [grabando, setGrabando] = useState(false)
  const [tareaActiva, setTareaActiva] = useState<{ due: string | null; remind: string | null } | null>(null)
  const version = useRef(1)
  const cargando = useRef(true)
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null)
  const tituloRef = useRef('')
  const tituloGuardado = useRef('')
  const etiquetasRef = useRef(etiquetas)
  etiquetasRef.current = etiquetas
  const grabador = useRef<MediaRecorder | null>(null)
  const editable = !!pagina && puedeEscribir(pagina.permission) && !pagina.deleted_at
  const compartida = !!pagina?.shared

  const subirImagen = useCallback(async (f: File): Promise<string | null> => {
    try {
      const a = await cuadernoApi.subir(pageId, f)
      setAdjuntos(xs => [...xs, a])
      return a.url
    } catch (e) {
      toast.error(extractErr(e))
      return null
    }
  }, [pageId, toast])

  const editor = useEditor({
    extensions: extensionesDelCuaderno({ ydoc, etiquetas: () => etiquetasRef.current, marcador: t('cuaderno.marcador'), subirImagen }),
    editable: false,
    // La barra pinta qué está activo (negrita, título…) en cada cambio de selección.
    shouldRerenderOnTransaction: true,
    editorProps: { attributes: { class: 'cdn-editor__texto', 'aria-label': t('cuaderno.contenido') } },
  }, [ydoc])

  const { conectado, companeros } = useColaboracion(pageId, ydoc, compartida && !!pagina)

  // ── Guardar ────────────────────────────────────────────────────────────────
  const guardarYa = useCallback(async () => {
    if (temporizador.current) { clearTimeout(temporizador.current); temporizador.current = null }
    if (!editor || !pagina || !puedeEscribir(pagina.permission)) return
    const contenido = editor.getJSON() as DocJSON
    const cuerpo = {
      content: contenido, title: tituloRef.current, base_version: version.current, collab: compartida,
      ...(compartida ? { yjs_state: aBase64(Y.encodeStateAsUpdate(ydoc)) } : {}),
    }
    setEstado('guardando')
    try {
      const r = await cuadernoApi.guardar(pageId, cuerpo)
      version.current = r.version
      setGuardadoEn(r.updated_at)
      if (tituloGuardado.current !== tituloRef.current) {
        tituloGuardado.current = tituloRef.current
        void qc.invalidateQueries({ queryKey: CLAVES_CUADERNO.arbol })
        void qc.invalidateQueries({ queryKey: CLAVES_CUADERNO.rapidas })
      }
      setEstado('guardado')
      void guardarCopia({ ...pagina, content: contenido, title: tituloRef.current, version: r.version })
    } catch (e) {
      if (esErrorDeRed(e)) {
        const ok = await encolar({ page_id: pageId, section_id: pagina.section_id, title: tituloRef.current, content: contenido,
          base_version: version.current, guardado_en: new Date().toISOString() })
        setEstado(ok ? 'sin_red' : 'error')
      } else if ((e as { response?: { status?: number } })?.response?.status === 409) {
        // Cambió en otro sitio: lo escrito aquí se guarda como copia y se recarga la página.
        try {
          await cuadernoApi.crearPagina(pagina.section_id, { title: `${tituloRef.current} ${t('cuaderno.sufijo_copia')}`.trim(), content: contenido })
          toast.error(t('cuaderno.conflicto_copia'))
          void qc.invalidateQueries({ queryKey: CLAVES_CUADERNO.arbol })
        } catch (e2) { toast.error(extractErr(e2)) }
        setEstado('error')
      } else {
        setEstado('error')
        toast.error(extractErr(e))
      }
    }
  }, [editor, pagina, compartida, ydoc, pageId, toast, t, qc])

  const programar = useCallback(() => {
    if (!pagina || !puedeEscribir(pagina.permission)) return
    setEstado('pendiente')
    if (temporizador.current) clearTimeout(temporizador.current)
    temporizador.current = setTimeout(() => { void guardarYa() }, ESPERA_MS)
  }, [pagina, guardarYa])

  // ── Cargar ─────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!editor) return undefined
    let vivo = true
    ;(async () => {
      let p: Pagina | null = null
      let estadoYjs: string | null = null
      try {
        p = await cuadernoApi.pagina(pageId)
        if (p.shared) estadoYjs = (await cuadernoApi.estadoColaborativo(pageId)).state
        void guardarCopia(p)
      } catch (e) {
        if (esErrorDeRed(e)) p = await leerCopia(pageId)
        if (!p) { if (vivo) { setEstado('error'); toast.error(extractErr(e)) } return }
        if (vivo) toast.info(t('cuaderno.abierta_sin_red'))
      }
      if (!vivo || !p) return
      cargando.current = true
      if (estadoYjs) {
        Y.applyUpdate(ydoc, deBase64(estadoYjs), ORIGEN_CARGA)
        if (ydoc.getXmlFragment('default').length === 0) editor.commands.setContent(p.content)
      } else {
        editor.commands.setContent(p.content)
      }
      version.current = p.version
      tituloRef.current = p.title
      tituloGuardado.current = p.title
      setTitulo(p.title)
      setAdjuntos(p.attachments)
      setPagina(p)
      setGuardadoEn(p.updated_at)
      const puede = puedeEscribir(p.permission) && !p.deleted_at
      editor.setEditable(puede)
      setEstado(puede ? 'guardado' : 'solo_lectura')
      setTimeout(() => { cargando.current = false }, 0)
    })()
    return () => { vivo = false }
  }, [editor, pageId, ydoc, toast, t])

  useEffect(() => {
    if (!editor) return undefined
    const alCambiar = ({ transaction }: { transaction: Parameters<typeof isChangeOrigin>[0] }) => {
      if (cargando.current || isChangeOrigin(transaction)) return
      programar()
    }
    const alMover = () => {
      if (editor.isActive('taskItem')) {
        const a = editor.getAttributes('taskItem')
        setTareaActiva({ due: (a.due as string) || null, remind: (a.remind as string) || null })
      } else setTareaActiva(null)
    }
    editor.on('update', alCambiar)
    editor.on('selectionUpdate', alMover)
    return () => { editor.off('update', alCambiar); editor.off('selectionUpdate', alMover) }
  }, [editor, programar])

  // Al salir (o cambiar de página): lo pendiente se guarda ya.
  const guardarRef = useRef(guardarYa)
  guardarRef.current = guardarYa
  useEffect(() => {
    const antes = () => { if (temporizador.current) void guardarRef.current() }
    window.addEventListener('beforeunload', antes)
    return () => {
      window.removeEventListener('beforeunload', antes)
      if (temporizador.current) void guardarRef.current()
    }
  }, [])
  useEffect(() => () => { ydoc.destroy() }, [ydoc])

  // ── Acciones de la barra ───────────────────────────────────────────────────
  const conEditor = (f: (e: Editor) => void) => () => { if (editor) f(editor) }
  const enlace = async () => {
    if (!editor) return
    const previo = editor.getAttributes('link').href as string | undefined
    const url = await pedirTexto({ message: t('cuaderno.enlace_url'), defaultValue: previo || 'https://' })
    if (url === null) return
    if (!url.trim()) editor.chain().focus().unsetLink().run()
    else if (/^(https?:\/\/|mailto:|\/)/i.test(url.trim())) editor.chain().focus().extendMarkRange('link').setLink({ href: url.trim() }).run()
    else toast.error(t('cuaderno.enlace_no_valido'))
  }
  const ponerEtiqueta = (clave: string) => conEditor(e => {
    const { $from } = e.state.selection
    e.chain().focus().insertContentAt($from.start(), [{ type: 'noteTag', attrs: { key: clave } }, { type: 'text', text: ' ' }]).run()
  })()
  const subirFichero = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.onchange = async () => {
      const f = input.files?.[0]
      if (!f) return
      try {
        const a = await cuadernoApi.subir(pageId, f)
        setAdjuntos(xs => [...xs, a])
        if (a.kind === 'image') editor?.chain().focus().setImage({ src: a.url, alt: a.file_name }).run()
        toast.success(t('cuaderno.adjunto_subido'))
      } catch (e) { toast.error(extractErr(e)) }
    }
    input.click()
  }
  const abrirAccion = () => {
    if (!editor) return
    const { from, to, empty } = editor.state.selection
    if (!empty) { setAccion({ texto: editor.state.doc.textBetween(from, to, '\n', ' ').trim() }); return }
    if (editor.isActive('taskItem')) {
      const a = editor.getAttributes('taskItem')
      const { $from } = editor.state.selection
      for (let d = $from.depth; d > 0; d -= 1) {
        const n = $from.node(d)
        if (n.type.name === 'taskItem') {
          setAccion({ texto: n.firstChild?.textContent?.trim() || '', blockId: a.bid as string, due: (a.due as string) || null })
          return
        }
      }
    }
    toast.error(t('cuaderno.accion_selecciona'))
  }
  const alCrearAccion = (c: Chip & { label: string }) => {
    setAccion(null)
    if (!editor) return
    let destino = editor.state.selection.to
    if (editor.state.selection.empty && editor.isActive('taskItem')) {
      const { $from } = editor.state.selection
      destino = $from.end()
    }
    editor.chain().focus().insertContentAt(destino, [{ type: 'text', text: ' ' }, { type: 'objectRef', attrs: { type: c.type, id: c.id, label: c.label } }]).run()
  }
  const fechaDeTarea = (campo: 'due' | 'remind', valor: string) => conEditor(e => {
    const v = campo === 'remind' && valor ? new Date(valor).toISOString() : (valor || null)
    e.chain().focus().updateAttributes('taskItem', { [campo]: v }).run()
    setTareaActiva(x => (x ? { ...x, [campo]: v } : x))
  })()
  const guardarDibujo = async (d: Dibujo) => {
    setGuardandoDibujo(true)
    try {
      const a = dibujo?.id ? await cuadernoApi.cambiarDibujo(dibujo.id, d) : await cuadernoApi.nuevoDibujo(pageId, d)
      setAdjuntos(xs => [...xs.filter(x => x.id !== a.id), a])
      if (!dibujo?.id) editor?.chain().focus().setImage({ src: a.url, alt: t('cuaderno.dibujo') }).run()
      setDibujo(null)
    } catch (e) { toast.error(extractErr(e)) } finally { setGuardandoDibujo(false) }
  }
  const voz = async () => {
    if (grabando) { grabador.current?.stop(); return }
    try {
      const flujo = await navigator.mediaDevices.getUserMedia({ audio: true })
      const trozos: Blob[] = []
      const r = new MediaRecorder(flujo)
      r.ondataavailable = ev => { if (ev.data.size) trozos.push(ev.data) }
      r.onstop = async () => {
        flujo.getTracks().forEach(x => x.stop())
        setGrabando(false)
        try {
          const res = await cuadernoApi.transcribir(pageId, new Blob(trozos, { type: r.mimeType || 'audio/webm' }))
          if (res.text) editor?.chain().focus().insertContent([{ type: 'paragraph', content: [{ type: 'text', text: res.text }] }]).run()
          else toast.info(t('cuaderno.voz_sin_texto'))
        } catch (e) { toast.error(extractErr(e)) }
      }
      grabador.current = r
      r.start()
      setGrabando(true)
    } catch { toast.error(t('cuaderno.voz_sin_microfono')) }
  }
  const pedirIa = async (accionIa: 'summarize' | 'extract_tasks' | 'organize') => {
    if (temporizador.current) await guardarYa()
    setIaCargando(true)
    try {
      const r = await cuadernoApi.ia(pageId, accionIa)
      setIa({ accion: accionIa, texto: r.text, tareas: r.tasks })
    } catch (e) { toast.error(extractErr(e)) } finally { setIaCargando(false) }
  }
  const insertarIa = () => {
    if (!editor || !ia) return
    const nodos: DocJSON[] = ia.accion === 'extract_tasks'
      ? [{ type: 'taskList', content: ia.tareas.map(x => ({ type: 'taskItem', attrs: { checked: false, due: x.due_date },
          content: [{ type: 'paragraph', content: [{ type: 'text', text: x.text }] }] })) }]
      : textoANodos(ia.texto || '')
    editor.chain().focus('end').insertContent(nodos).run()
    setIa(null)
  }
  const exportar = (formato: 'md' | 'pdf') => async () => {
    if (temporizador.current) await guardarYa()
    try { await descargarExportacion('page', pageId, formato, tituloRef.current || 'pagina') } catch (e) { toast.error(extractErr(e)) }
  }
  const borrarAdjunto = async (a: Adjunto) => {
    if (!(await confirmar({ message: t('cuaderno.borrar_adjunto_confirmar', { nombre: a.file_name }), danger: true }))) return
    try { await cuadernoApi.borrarAdjunto(a.id); setAdjuntos(xs => xs.filter(x => x.id !== a.id)) } catch (e) { toast.error(extractErr(e)) }
  }
  const borrarPagina = async () => {
    if (!(await confirmar({ message: t('cuaderno.borrar_pagina_confirmar'), danger: true }))) return
    try { await cuadernoApi.borrarPagina(pageId); onBorrada?.(); void qc.invalidateQueries({ queryKey: CLAVES_CUADERNO.arbol }) } catch (e) { toast.error(extractErr(e)) }
  }

  if (!editor || estado === 'cargando') return <div className="cdn-editor cdn-editor--cargando"><Spinner /></div>

  const B = BotonDeBarra
  const apagado = !editable
  const textoDeEstado = {
    cargando: '', guardado: guardadoEn ? t('cuaderno.guardado_a', { hora: fmtDateTime(guardadoEn) }) : t('cuaderno.guardado'),
    pendiente: t('cuaderno.cambios_pendientes'), guardando: t('cuaderno.guardando'), sin_red: t('cuaderno.guardado_sin_red'),
    error: t('cuaderno.error_al_guardar'), solo_lectura: t('cuaderno.solo_lectura'),
  }[estado]

  return (
    <div className={`cdn-editor${compacto ? ' cdn-editor--compacto' : ''}`}>
      <div className="cdn-editor__cabecera">
        {!compacto && pagina && (
          <div className="cdn-editor__ruta">
            <span className={`cdn-punto cdn-color--${pagina.section_color || 'gray'}`} aria-hidden />
            {pagina.notebook_title} › {pagina.section_title}
          </div>
        )}
        <Input aria-label={t('cuaderno.titulo_pagina')} value={titulo} placeholder={t('cuaderno.sin_titulo')} disabled={!editable}
          inputClassName="cdn-editor__titulo" maxLength={300}
          onChange={e => { setTitulo(e.target.value); tituloRef.current = e.target.value; onCambioDeTitulo?.(e.target.value); programar() }} />
        <div className="cdn-editor__estado" role="status" aria-live="polite">
          {estado === 'sin_red' && <CloudOff size={12} aria-hidden />}
          <span>{textoDeEstado}</span>
          {pagina?.created_at && !compacto && <span className="cdn-editor__fecha">· {t('cuaderno.creada_el', { fecha: fmtDateTime(pagina.created_at) })}</span>}
          {compartida && <span className="cdn-editor__colab"><Users size={12} aria-hidden />{conectado ? t('cuaderno.en_vivo', { n: companeros }) : t('cuaderno.colaboracion_desconectada')}</span>}
        </div>
      </div>

      <div className="cdn-barra" role="toolbar" aria-label={t('cuaderno.barra')}>
        <B apagado={apagado} etiqueta={t('cuaderno.deshacer')} onClick={conEditor(e => e.chain().focus().undo().run())}><Undo2 size={14} /></B>
        <B apagado={apagado} etiqueta={t('cuaderno.rehacer')} onClick={conEditor(e => e.chain().focus().redo().run())}><Redo2 size={14} /></B>
        <span className="cdn-barra__sep" />
        <B apagado={apagado} etiqueta={t('cuaderno.titulo_1')} activo={editor.isActive('heading', { level: 1 })} onClick={conEditor(e => e.chain().focus().toggleHeading({ level: 1 }).run())}><Heading1 size={14} /></B>
        <B apagado={apagado} etiqueta={t('cuaderno.titulo_2')} activo={editor.isActive('heading', { level: 2 })} onClick={conEditor(e => e.chain().focus().toggleHeading({ level: 2 }).run())}><Heading2 size={14} /></B>
        <B apagado={apagado} etiqueta={t('cuaderno.titulo_3')} activo={editor.isActive('heading', { level: 3 })} onClick={conEditor(e => e.chain().focus().toggleHeading({ level: 3 }).run())}><Heading3 size={14} /></B>
        <span className="cdn-barra__sep" />
        <B apagado={apagado} etiqueta={t('cuaderno.negrita')} activo={editor.isActive('bold')} onClick={conEditor(e => e.chain().focus().toggleBold().run())}><Bold size={14} /></B>
        <B apagado={apagado} etiqueta={t('cuaderno.cursiva')} activo={editor.isActive('italic')} onClick={conEditor(e => e.chain().focus().toggleItalic().run())}><Italic size={14} /></B>
        <B apagado={apagado} etiqueta={t('cuaderno.subrayado')} activo={editor.isActive('underline')} onClick={conEditor(e => e.chain().focus().toggleUnderline().run())}><Underline size={14} /></B>
        <B apagado={apagado} etiqueta={t('cuaderno.tachado')} activo={editor.isActive('strike')} onClick={conEditor(e => e.chain().focus().toggleStrike().run())}><Strikethrough size={14} /></B>
        <B apagado={apagado} etiqueta={t('cuaderno.resaltar')} activo={editor.isActive('highlight')} onClick={conEditor(e => e.chain().focus().toggleHighlight({ color: 'yellow' }).run())}><Highlighter size={14} /></B>
        <B apagado={apagado} etiqueta={t('cuaderno.enlace')} activo={editor.isActive('link')} onClick={() => { void enlace() }}><Link2 size={14} /></B>
        <span className="cdn-barra__sep" />
        <B apagado={apagado} etiqueta={t('cuaderno.lista')} activo={editor.isActive('bulletList')} onClick={conEditor(e => e.chain().focus().toggleBulletList().run())}><List size={14} /></B>
        <B apagado={apagado} etiqueta={t('cuaderno.lista_numerada')} activo={editor.isActive('orderedList')} onClick={conEditor(e => e.chain().focus().toggleOrderedList().run())}><ListOrdered size={14} /></B>
        <B apagado={apagado} etiqueta={t('cuaderno.casillas')} activo={editor.isActive('taskList')} onClick={conEditor(e => e.chain().focus().toggleTaskList().run())}><CheckSquare size={14} /></B>
        <B apagado={apagado} etiqueta={t('cuaderno.tabla')} onClick={conEditor(e => e.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run())}><Table2 size={14} /></B>
        {editable && (
          <Menu etiqueta={t('cuaderno.etiqueta')} icono={<Tag size={14} />} opciones={etiquetas.map(x => ({
            id: x.key, label: nombreDeEtiqueta(t, x, x.key), icon: <IconoDeEtiqueta icono={x.icon} />, onSelect: () => ponerEtiqueta(x.key),
          }))} />
        )}
        <span className="cdn-barra__sep" />
        <B apagado={apagado} etiqueta={t('cuaderno.adjuntar')} onClick={subirFichero}><Paperclip size={14} /></B>
        <B apagado={apagado} etiqueta={t('cuaderno.dibujar')} onClick={() => setDibujo({})}><PenTool size={14} /></B>
        {funciones.voice && (
          <B apagado={apagado} etiqueta={grabando ? t('cuaderno.voz_parar') : t('cuaderno.voz_grabar')} activo={grabando} onClick={() => { void voz() }}>
            {grabando ? <Square size={14} /> : <Mic size={14} />}
          </B>
        )}
        <B apagado={apagado} etiqueta={t('cuaderno.a_accion')} onClick={abrirAccion}><Zap size={14} /></B>
        {funciones.ai && (
          <Menu etiqueta={t('cuaderno.ia')} icono={iaCargando ? <Spinner size={14} /> : <Brain size={14} />} opciones={[
            { id: 's', label: t('cuaderno.ia_resumir'), onSelect: () => { void pedirIa('summarize') } },
            { id: 'e', label: t('cuaderno.ia_tareas'), onSelect: () => { void pedirIa('extract_tasks') } },
            { id: 'o', label: t('cuaderno.ia_ordenar'), onSelect: () => { void pedirIa('organize') } },
          ]} />
        )}
        <Menu etiqueta={t('cuaderno.exportar')} icono={<Download size={14} />} alinear="derecha" opciones={[
          { id: 'md', label: t('cuaderno.exportar_md'), onSelect: () => { void exportar('md')() } },
          { id: 'pdf', label: t('cuaderno.exportar_pdf'), onSelect: () => { void exportar('pdf')() } },
        ]} />
        {editable && !compacto && <B apagado={apagado} etiqueta={t('cuaderno.borrar_pagina')} onClick={() => { void borrarPagina() }}><Trash2 size={14} /></B>}
      </div>

      {tareaActiva && editable && (
        <div className="cdn-tarea-activa">
          <CalendarClock size={13} aria-hidden />
          <CampoFecha label={t('cuaderno.casilla_actual')} value={tareaActiva.due || ''} onChange={v => fechaDeTarea('due', v)} aria-label={t('cuaderno.fecha')} placeholder={t('cuaderno.fecha')} />
          <CampoFecha modo="fechaHora" value={tareaActiva.remind ? tareaActiva.remind.slice(0, 16) : ''} onChange={v => fechaDeTarea('remind', v)}
            aria-label={t('cuaderno.aviso')} placeholder={t('cuaderno.aviso')} />
        </div>
      )}

      <EditorContent editor={editor} className="cdn-editor__cuerpo" />

      {adjuntos.length > 0 && (
        <div className="cdn-adjuntos">
          <h3 className="ds-eyebrow">{t('cuaderno.adjuntos')}</h3>
          <ul className="cdn-lista">
            {adjuntos.map(a => (
              <li key={a.id} className="cdn-lista__fila">
                <a href={`${a.url}${a.kind === 'image' || a.kind === 'drawing' ? '' : '?download=1'}`} target="_blank" rel="noopener noreferrer" className="cdn-lista__texto">
                  {a.kind === 'drawing' ? t('cuaderno.dibujo') : a.file_name}
                </a>
                {a.kind === 'audio' && <audio controls src={a.url} className="cdn-audio"><track kind="captions" /></audio>}
                {a.kind === 'drawing' && editable && (
                  <Button size="sm" variant="ghost" onClick={async () => {
                    try { const d = await cuadernoApi.dibujo(a.id); setDibujo({ id: a.id, inicial: d.drawing }) } catch (e) { toast.error(extractErr(e)) }
                  }}>{t('cuaderno.editar_dibujo')}</Button>
                )}
                {editable && <IconButton ariaLabel={t('cuaderno.borrar_adjunto')} className="cdn-boton" onClick={() => { void borrarAdjunto(a) }}><Trash2 size={13} /></IconButton>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {accion && <ModalAccion pageId={pageId} origen={accion} onClose={() => setAccion(null)} onCreado={alCrearAccion} />}
      {dibujo && <ModalDibujo inicial={dibujo.inicial} onClose={() => setDibujo(null)} onGuardar={d => { void guardarDibujo(d) }} guardando={guardandoDibujo} />}
      {ia && (
        <Modal open onClose={() => setIa(null)} title={t(`cuaderno.ia_${ia.accion}`)} size="lg" avisarSinGuardar={false}>
          <div className="cdn-form">
            {ia.accion === 'extract_tasks'
              ? (ia.tareas.length ? <ul className="cdn-ia__tareas">{ia.tareas.map((x, i) => <li key={i}>{x.text}{x.due_date ? ` (${x.due_date})` : ''}</li>)}</ul>
                : <p className="cdn-ayuda">{t('cuaderno.ia_sin_tareas')}</p>)
              : <pre className="cdn-ia__texto">{ia.texto}</pre>}
            <p className="cdn-ayuda">{t('cuaderno.ia_aviso')}</p>
            <div className="cdn-form__acciones">
              <Button variant="secondary" onClick={() => setIa(null)}>{t('common.close')}</Button>
              {editable && (ia.texto || ia.tareas.length > 0) && <Button onClick={insertarIa}>{t('cuaderno.ia_insertar')}</Button>}
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
