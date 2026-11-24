/*
 * 16-11-2026: pestañas Wiki / Etiquetas con Tabs bajo la cabecera (antes un
 * conmutador propio con emojis en la cabecera); "Nuevo espacio" con icono (antes
 * "+ " en el texto); vacíos con EmptyState e icono lucide (antes emojis y
 * textos sueltos en gris); árbol, plantillas, editor de bloques, acciones de
 * página e historial con iconos lucide, Button, IconButton y StatusBadge (antes
 * emojis y símbolos sueltos); campos con ds-input; fechas con el formateador de la app.
 */
import { CHART } from '../constants/theme'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, fmtDate, fmtDateTime } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useEffect, useRef, useState, useId } from 'react'
import { useToast } from '../context/ToastContext'
import { useDocCollab } from '../hooks/useDocCollab'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { nexusAgentApi, wikiApi } from '../services/api'
import type { VisibilidadDeWiki, WikiBloque, WikiEspacio, WikiEtiqueta, WikiPagina, WikiPaginaEnArbol, WikiResultadoDeBusqueda } from '../services/api/tipos-alm'
import { Buscador, Button, Spinner, EmptyState, IconButton, Modal, StatusBadge, Tabs, useDialogo, Select, Pulsable, Checkbox, useErroresDeCampo, Input, Textarea } from '../components/ui'
import { useListaDeProyectos } from '../hooks/useListas'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import {
  BookOpen, Building2, ChevronDown, ChevronUp, ClipboardList, FileText, Folder, FolderOpen, Globe, History,
  Lightbulb, Link2, Pencil, Play, Plus, RotateCcw, Ruler, Search, SearchX, Sparkles, Tag, Trash2, X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import type { CSSProperties } from 'react'
import { FOCUS_DEFER_MS } from '../constants/timings'
import './WikiPage.css'

type Block = WikiBloque
type Traducir = (clave: string, params?: Record<string, string | number>) => string

const BLOCK_TYPES = [
  {type:'paragraph',labelKey:'wiki.bloque_texto'},
  {type:'heading1',labelKey:'wiki.bloque_titulo1'},
  {type:'heading2',labelKey:'wiki.bloque_titulo2'},
  {type:'heading3',labelKey:'wiki.bloque_titulo3'},
  {type:'bullet',labelKey:'wiki.bloque_lista'},
  {type:'numbered',labelKey:'wiki.bloque_numerada'},
  {type:'code',labelKey:'wiki.bloque_codigo'},
  {type:'quote',labelKey:'wiki.bloque_cita'},
  {type:'divider',labelKey:'wiki.bloque_separador'},
  {type:'callout',labelKey:'wiki.bloque_llamada'},
  {type:'task_list',labelKey:'wiki.bloque_checklist'},
]

/** Plantillas: el texto sale del idioma activo al crear la página. */
const TEMPLATES: Array<{ id: string; icon: LucideIcon; nameKey: string; blocks: Array<{ type: string; key?: string }> }> = [
  { id:'meeting', icon:ClipboardList, nameKey:'wiki.tpl_meeting', blocks:[
    {type:'heading1',key:'wiki.tpl_meeting_h1'},
    {type:'heading2',key:'wiki.tpl_meeting_asistentes'},{type:'bullet'},
    {type:'heading2',key:'wiki.tpl_meeting_puntos'},{type:'numbered'},
    {type:'heading2',key:'wiki.tpl_meeting_decisiones'},{type:'bullet'},
    {type:'heading2',key:'wiki.tpl_meeting_acciones'},{type:'task_list'},
  ]},
  { id:'spec', icon:Ruler, nameKey:'wiki.tpl_spec', blocks:[
    {type:'heading1',key:'wiki.tpl_spec_h1'},
    {type:'heading2',key:'wiki.tpl_spec_objetivo'},{type:'paragraph'},
    {type:'heading2',key:'wiki.tpl_spec_alcance'},{type:'paragraph'},
    {type:'heading2',key:'wiki.tpl_spec_diseno'},{type:'code'},
    {type:'heading2',key:'wiki.tpl_spec_criterios'},{type:'numbered'},
  ]},
  { id:'retro', icon:RotateCcw, nameKey:'wiki.tpl_retro', blocks:[
    {type:'heading1',key:'wiki.tpl_retro_h1'},
    {type:'heading2',key:'wiki.tpl_retro_bien'},{type:'bullet'},
    {type:'heading2',key:'wiki.tpl_retro_mejorar'},{type:'bullet'},
    {type:'heading2',key:'wiki.tpl_retro_acciones'},{type:'task_list'},
  ]},
  { id:'postmortem', icon:Search, nameKey:'wiki.tpl_postmortem', blocks:[
    {type:'heading1',key:'wiki.tpl_postmortem'},
    {type:'heading2',key:'wiki.tpl_pm_resumen'},{type:'paragraph'},
    {type:'heading2',key:'wiki.tpl_pm_cronologia'},{type:'numbered'},
    {type:'heading2',key:'wiki.tpl_pm_causa'},{type:'paragraph'},
    {type:'heading2',key:'wiki.tpl_pm_acciones'},{type:'task_list'},
  ]},
  { id:'blank', icon:FileText, nameKey:'wiki.tpl_blank', blocks:[{type:'paragraph'}] },
]

const TA_CLASS: Record<string, string> = {
  heading1: 'wk-ta--heading1', heading2: 'wk-ta--heading2', heading3: 'wk-ta--heading3',
  code: 'wk-ta--code', quote: 'wk-ta--quote', callout: 'wk-ta--callout',
}

function onKeyboardActivate(event: { key: string; preventDefault: () => void }, action: () => void) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}

function CasillaTarea({ etiqueta, className }: { etiqueta: string; className?: string }) {
  const [marcada, setMarcada] = useState(false)
  return <Checkbox className={className} aria-label={etiqueta} checked={marcada} onChange={setMarcada} />
}

function BlockEditor({ blocks, onChange }: { blocks: Block[]; onChange: (b: Block[]) => void }) {
  const traducir = useAppT() as Traducir
  const toast = useToast()
  const update = (i: number, k: string, v: string) => { const n=[...blocks]; n[i]={...n[i],[k]:v}; onChange(n) }
  const add    = (after: number, type='paragraph') => { const n=[...blocks]; n.splice(after+1,0,{type,content:''}); onChange(n) }
  const remove = (i: number) => { if(blocks.length>1) onChange(blocks.filter((_,x)=>x!==i)) }
  const move   = (i: number, d: number) => { const n=[...blocks]; const t=i+d; if(t<0||t>=n.length) return; [n[i],n[t]]=[n[t],n[i]]; onChange(n) }

  const FORMATS = [
    {label:'B',cls:'wk-format-btn--bold',title:traducir('wiki.formato_negrita'),wrap:['**','**']},
    {label:'I',cls:'wk-format-btn--italic',title:traducir('wiki.formato_cursiva'),wrap:['*','*']},
    {label:'`',cls:'wk-format-btn--code',title:traducir('wiki.formato_codigo'),wrap:['`','`']},
    {label:'link',cls:'',title:traducir('wiki.formato_enlace'),wrap:['[','](url)']},
  ]

  return (
    <div className="wk-editor">
      {blocks.map((block,i) => (
        <div key={i} className="wk-block">
          <div className="wk-block-ctrl">
            <IconButton type="button" onClick={()=>move(i,-1)} ariaLabel={traducir('wiki.subir_bloque', { n: i+1 })} className="wk-block-ctrl-btn"><ChevronUp size={12} aria-hidden="true" /></IconButton>
            <IconButton type="button" onClick={()=>move(i, 1)} ariaLabel={traducir('wiki.bajar_bloque', { n: i+1 })} className="wk-block-ctrl-btn"><ChevronDown size={12} aria-hidden="true" /></IconButton>
            <IconButton type="button" onClick={()=>remove(i)} ariaLabel={traducir('wiki.eliminar_bloque', { n: i+1 })} className="wk-block-ctrl-btn wk-block-ctrl-btn--danger"><X size={12} aria-hidden="true" /></IconButton>
          </div>
          <div className="u-flex1">
            {block.type==='divider'
              ? <hr className="wk-divider-edit"/>
              : <div className="wk-block-body">
                  {block.type==='bullet'    && <span className="wk-bullet" aria-hidden="true">•</span>}
                  {block.type==='numbered'  && <span className="wk-bullet wk-bullet--num" aria-hidden="true">{i+1}.</span>}
                  {block.type==='task_list' && <CasillaTarea etiqueta={traducir('wiki.tarea_n', { n: i+1 })} className="wk-task-check" />}
                  <div className="wk-block-main">
                    {['paragraph','heading1','heading2','heading3','quote','callout'].includes(block.type) && (
                      <div className="wk-format-bar">
                        {FORMATS.map(({label,cls,title,wrap}) => (
                          <IconButton key={label} type="button"
                            onMouseDown={e=>{
                              e.preventDefault()
                              const ta = e.currentTarget.closest('div')?.parentElement?.querySelector('textarea')
                              if(!ta) return
                              const s=ta.selectionStart,en=ta.selectionEnd,sel=ta.value.slice(s,en)||label
                              const rep=wrap[0]+(sel===label?traducir('wiki.texto_ejemplo'):sel)+wrap[1]
                              const nv=ta.value.slice(0,s)+rep+ta.value.slice(en)
                              update(i,'content',nv)
                              setTimeout(()=>{ta.focus();ta.setSelectionRange(s,s+rep.length)},FOCUS_DEFER_MS)
                            }}
                            title={title} ariaLabel={title}
                            className={`wk-format-btn ${cls}`}>
                            {label === 'link' ? <Link2 size={12} aria-hidden="true" /> : label}
                          </IconButton>
                        ))}
                        {/* AI improve button */}
                        <IconButton type="button"
                          title={traducir('wiki.mejorar_redaccion_con_ia')}
                          ariaLabel={traducir('wiki.mejorar_redaccion_con_ia')}
                          onMouseDown={e=>{
                            e.preventDefault()
                            if(!block.content) return
                            // 23-11-2026 (M7 del 04b): la instrucción sale en el idioma del operador
                            // (`wiki.ia_mejorar_redaccion`); antes, castellano fijo. Y si falla, se avisa.
                            // 23-11-2026: por `/ai/texto` (módulo inline_editor: gobernanza, tope de gasto y registro, sin abrir
                            // conversación; si no hay IA da 503 y el texto no se toca), como el editor en línea.
                            nexusAgentApi.texto(traducir('wiki.ia_mejorar_redaccion', { texto: block.content }))
                              .then(r=>{ const t=r.data?.texto||''; if(t) update(i,'content',t) })
                              .catch((e: unknown)=>toast.error(extractErr(e, traducir('wiki.error_ia'))))
                          }}
                          className="wk-format-btn wk-format-btn--ai">
                          <Sparkles size={12} aria-hidden="true" />
                        </IconButton>
                      </div>
                    )}
                    <Textarea aria-label={traducir('wiki.bloque_n', { n: i+1 })} value={block.content||''} onChange={e=>update(i,'content',e.target.value)}
                      inputClassName={`wk-ta ${TA_CLASS[block.type] ?? ''}`}
                      rows={block.type==='code'?4:1}
                      onKeyDown={e=>{
                        if(e.key==='Enter'&&!e.shiftKey&&block.type!=='code'){e.preventDefault();add(i)}
                        if(e.key==='Backspace'&&!block.content&&blocks.length>1){e.preventDefault();remove(i)}
                      }}
                      placeholder={block.type==='paragraph'?traducir('wiki.escribe_aqui'):''} />
                  </div>
                </div>
            }
          </div>
          <Select suelto placeholder={false} value={block.type} onChange={e=>update(i,'type',e.target.value)}
            aria-label={traducir('wiki.tipo_de_bloque', { n: i+1 })}
            className="wk-type-select">
            {BLOCK_TYPES.map(bt=><option key={bt.type} value={bt.type}>{traducir(bt.labelKey)}</option>)}
          </Select>
        </div>
      ))}
      <div className="wk-add-block">
        <Button size="sm" variant="secondary" icon={<Plus size={13} />} onClick={()=>add(blocks.length-1)}>
          {traducir('wiki.anadir_bloque')}
        </Button>
      </div>
    </div>
  )
}

// `traducir` entra por parametro y no por hook: `renderBlocks` NO es un
// componente —se llama como funcion corriente desde el JSX de dos de ellos—, y
// un hook ahi es una violacion de las reglas de React que ESLint marca y que en
// tiempo de ejecucion rompe el orden de los hooks del componente que la invoca.
function renderBlocks(blocks: Block[], traducir: (clave: string) => string) {
  return (blocks||[]).map((b,i)=>{
    const text = b.content||''
    switch(b.type){
      case 'heading1':  return <h1  key={i} className="wk-r wk-r--h1">{text}</h1>
      case 'heading2':  return <h2  key={i} className="wk-r wk-r--h2">{text}</h2>
      case 'heading3':  return <h3  key={i} className="wk-r wk-r--h3">{text}</h3>
      case 'code':      return <pre key={i} className="ds-codigo wk-r wk-r--code">{text}</pre>
      case 'quote':     return <blockquote key={i} className="wk-r wk-r--quote">{text}</blockquote>
      case 'bullet':    return <div key={i} className="wk-r wk-r--row"><span className="wk-r-mark" aria-hidden="true">•</span><span>{text}</span></div>
      case 'numbered':  return <div key={i} className="wk-r wk-r--row"><span className="wk-r-mark wk-r-mark--num">{i+1}.</span><span>{text}</span></div>
      case 'task_list': return <div key={i} className="wk-r wk-r--row wk-r--task"><CasillaTarea etiqueta={text || traducir('wiki.tarea')} /><span>{text}</span></div>
      case 'divider':   return <hr  key={i} className="wk-r-divider"/>
      case 'callout':   return <div key={i} className="wk-r wk-r--callout"><Lightbulb size={16} aria-hidden="true" className="wk-r-callout-icon" /><span>{text}</span></div>
      default:          return <p   key={i} className={`wk-r ${text ? 'wk-r--p' : 'wk-r--empty'}`}>{text||<em>{traducir('wiki.parrafo_vacio')}</em>}</p>
    }
  })
}

function PageModal({ spaceId, parentId, editPage, onClose }: { spaceId?: string; parentId?: string | null; editPage?: WikiPagina | null; onClose: () => void }) {
  const idCampo = useId()
  const traducir = useAppT() as Traducir
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!editPage
  const autoSlug = (t: string) => t.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')
  const [title,      setTitle]     = useState(editPage?.title || '')
  const [slug,       setSlug]      = useState(editPage?.slug  || '')
  const [blocks,     setBlocks]    = useState<Block[]>(editPage?.content || [{type:'paragraph',content:''}])
  const [visibility, setVisibility]= useState<VisibilidadDeWiki>(editPage?.visibility || 'team')
  const [tplStep,    setTplStep]   = useState(!isEdit)
  const applyingRemoteRef = useRef(false)

  const { connected: collabConnected, peers: collabPeers, sendUpdate: sendCollabUpdate } = useDocCollab(
    editPage?.id,
    (remoteBlocks) => {
      applyingRemoteRef.current = true
      setBlocks(Array.isArray(remoteBlocks) ? (remoteBlocks as Block[]) : [{ type: 'paragraph', content: '' }])
    }
  )

  useEffect(() => {
    if (!editPage?.id) return
    if (applyingRemoteRef.current) {
      applyingRemoteRef.current = false
      return
    }
    sendCollabUpdate(blocks)
  }, [blocks, editPage?.id, sendCollabUpdate])
  const VIS_OPTS: Array<{ value: VisibilidadDeWiki; label: string }> = [
    { value: 'team',   label: traducir('wiki.vis_solo_equipo') },
    { value: 'portal', label: traducir('wiki.vis_portal_cliente') },
    { value: 'public', label: traducir('wiki.vis_public') },
  ]

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    // `WikiPageIn` no lleva visibilidad (se ignoraba): va por su ruta propia si cambia.
    mutationFn: async (d: Record<string, unknown>) => {
      const guardada = (isEdit ? await wikiApi.updatePage(editPage!.id, d) : await wikiApi.createPage(spaceId, d)).data
      if (guardada.visibility !== visibility) await wikiApi.portalUpdatePage(guardada.id, { visibility })
      return guardada
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['wiki-pages', spaceId] }); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, traducir('wiki.error_guardar'))) },
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? traducir('wiki.edit_page') : traducir('wiki.nueva_pagina')}>
      <div className="u-stack-14">
        {tplStep && !isEdit && (
          <div>
            <div id={`${idCampo}-plantilla-et`} className="wk-label">{traducir('wiki.empezar_desde_plantilla')}</div>
            <div role="group" aria-labelledby={`${idCampo}-plantilla-et`} className="wk-templates">
              {TEMPLATES.map(tpl=>(
                <Pulsable key={tpl.id} type="button"
                  onClick={()=>{
                    setBlocks(tpl.blocks.map(b => ({ type: b.type, content: b.key ? traducir(b.key) : '' })))
                    if(!title){ const n = traducir(tpl.nameKey); setTitle(n); setSlug(autoSlug(n)) }
                    setTplStep(false)
                  }}
                  className="wk-template">
                  <tpl.icon size={15} aria-hidden="true" /> {traducir(tpl.nameKey)}
                </Pulsable>
              ))}
            </div>
            <Pulsable type="button" onClick={()=>setTplStep(false)} className="wk-link-btn">{traducir('wiki.continuar_sin_plantilla')}</Pulsable>
          </div>
        )}
        {!tplStep && <>
          {isEdit && (
            <div className={`wk-collab${collabConnected ? ' wk-collab--on' : ''}`} role="status">
              <span className="wk-collab-dot" aria-hidden="true" />
              <span className="wk-collab-text">
                {collabConnected ? traducir('wiki.colaboracion_activa', { n: collabPeers }) : traducir('wiki.reconectando_colaboracion')}
              </span>
            </div>
          )}
          <div>
            <label id={`${idCampo}-ettitulo`} htmlFor={`${idCampo}-titulo`} className="wk-label">{traducir('wiki.page_title')}</label>
            <Input id={`${idCampo}-titulo`} aria-labelledby={`${idCampo}-ettitulo`} value={title} onChange={e=>{setTitle(e.target.value);if(!isEdit)setSlug(autoSlug(e.target.value))}} placeholder={traducir('wiki.titulo_de_la_pagina')} inputClassName="wk-input" />{msg('title')}{msg('title')}
          </div>
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="wk-label">{traducir('wiki.slug')}</label>
            <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={slug} onChange={e=>setSlug(e.target.value)} inputClassName="wk-input wk-input--mono ds-campo-codigo" />{msg('slug')}{msg('slug')}
          </div>
          <div>
            <div id={`${idCampo}-contenido-et`} className="wk-label">{traducir('wiki.content')}</div>
            <div role="group" aria-labelledby={`${idCampo}-contenido-et`} className="wk-content-box">
              <BlockEditor blocks={blocks} onChange={setBlocks}/>
            </div>
          </div>
          <div>
            <div id={`${idCampo}-visibilidad-et`} className="wk-label">{traducir('wiki.visibility')}</div>
            <div className="u-row-8" role="group" aria-labelledby={`${idCampo}-visibilidad-et`}>
              {VIS_OPTS.map(o=>(
                <Pulsable key={o.value} type="button" onClick={()=>setVisibility(o.value)} aria-pressed={visibility===o.value}
                  className={`wk-vis-btn${visibility===o.value ? ' wk-vis-btn--active' : ''}`}>
                  {o.label}
                </Pulsable>
              ))}
            </div>
          </div>
          <div className="wk-actions">
            <Button variant="secondary" onClick={onClose}>{traducir('wiki.cancelar')}</Button>
            <Button onClick={()=>mutate({title,slug,content:blocks,parent_id:isEdit?editPage!.parent_id:parentId,sort_order:isEdit?(editPage!.sort_order ?? 0):0,is_published:isEdit?editPage!.is_published:true})} disabled={isPending||!title||!slug} loading={isPending}>
              {isPending?traducir('wiki.guardando'):(isEdit?traducir('wiki.guardar'):traducir('wiki.crear_pagina'))}
            </Button>
          </div>
        </>}
      </div>
    </Modal>
  )
}

function PageTree({ pages, selectedId, onSelect, onNew, level=0 }: { pages: WikiPaginaEnArbol[]; selectedId?: string; onSelect: (p: WikiPaginaEnArbol) => void; onNew: (pid: string) => void; level?: number }) {
  const traducir = useAppT() as Traducir
  return (
    <div className="wk-tree">
      {pages.map(p=>(
        <div key={p.id}>
          <div onClick={()=>onSelect(p)}
            role="button"
            tabIndex={0}
            aria-current={selectedId===p.id ? 'page' : undefined}
            onKeyDown={e => { if (e.target === e.currentTarget) onKeyboardActivate(e, () => onSelect(p)) }}
            className={`wk-tree-item${selectedId===p.id ? ' wk-tree-item--active' : ''}`}
            style={{ '--wk-level': level } as CSSProperties}>
            <FileText size={13} aria-hidden="true" className="wk-tree-icon" />
            <span className="wk-tree-title">{p.title}</span>
            {p.visibility === 'portal' && <span title={traducir('wiki.visible_portal')} aria-label={traducir('wiki.visible_portal')} className="wk-vis-icon"><Building2 size={12} aria-hidden="true" /></span>}
            {p.visibility === 'public' && <span title={traducir('wiki.visible_publico')} aria-label={traducir('wiki.visible_publico')} className="wk-vis-icon wk-vis-icon--public"><Globe size={12} aria-hidden="true" /></span>}
            <IconButton type="button" onClick={e=>{e.stopPropagation();onNew(p.id)}}
              ariaLabel={traducir('wiki.nueva_subpagina_de', { titulo: p.title })} title={traducir('wiki.nueva_subpagina')}
              className="wk-tree-add"><Plus size={13} aria-hidden="true" /></IconButton>
          </div>
          {(p.children?.length ?? 0)>0 && <PageTree pages={p.children || []} selectedId={selectedId} onSelect={onSelect} onNew={onNew} level={level+1}/>}
        </div>
      ))}
    </div>
  )
}

// ── Wiki Tags (integrado en WikiPage) ─────────────────────────────────────────
function CollabIndicator({ docId }: { docId: string }) {
  const traducir = useAppT() as Traducir
  const { connected, peers } = useDocCollab(docId)
  if (!connected) return null
  return (
    <div title={traducir(peers === 1 ? 'wiki.editores_activos_uno' : 'wiki.editores_activos', { n: peers })} className="wk-live">
      <span className="wk-live-dot" aria-hidden="true" />
      {traducir('wiki.n_en_vivo', { n: peers })}
    </div>
  )
}

// Sin repetidos: con `var(--warning)` y `var(--accent)` dos veces, React avisaba
// de claves duplicadas y se pintaban muestras iguales.
const TAG_COLORS = ['var(--accent)','var(--success)','var(--warning)','var(--danger)','var(--purple)',CHART.pink]

function WikiTagsInline() {
  const idCampo = useId()
  const traducir = useAppT() as Traducir
  const toast = useToast()
  const qc = useQueryClient()
  const [space, setSpace] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<WikiEtiqueta | null>(null)
  const [form, setForm] = useState({ name: '', color: 'var(--accent)' })

  const { data: spaces = [] } = useQuery<WikiEspacio[]>({
    queryKey: ['wiki-spaces-tags'],
    queryFn: () => wikiApi.spaces().then(r => r.data),
  })
  const { data: tags = [], isLoading } = useQuery<WikiEtiqueta[]>({
    queryKey: ['wiki-tags-inline', space],
    queryFn: () => space ? wikiApi.tags(space).then(r => r.data) : [],
    enabled: !!space,
  })

  const { mutate: save, isPending } = useMutation({
    mutationFn: (d: Record<string, unknown>) => editing
      ? wikiApi.updateTag(editing.id, d).then(r => r.data)
      : wikiApi.createTag(space, d).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['wiki-tags-inline', space] })
      setShowForm(false); setEditing(null); setForm({ name: '', color: 'var(--accent)' })
      toast.success(editing ? traducir('wiki.etiqueta_actualizada') : traducir('wiki.etiqueta_creada'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id: string) => wikiApi.deleteTag(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['wiki-tags-inline', space] }); toast.success(traducir('wiki.etiqueta_eliminada')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div>
      <div className="wk-tags-bar">
        <Select suelto placeholder={false} value={space} onChange={e=>setSpace(e.target.value)} aria-label={traducir('wiki.espacio_wiki')}
          className="wk-input wk-input--auto">
          <option value="">{traducir('wiki.seleccionar_espacio')}</option>
          {spaces.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
        </Select>
        {space && <Button icon={<Plus size={14} />} onClick={()=>{setEditing(null);setForm({name:'',color:'var(--accent)'});setShowForm(true)}}>{traducir('wiki.nueva_etiqueta')}</Button>}
      </div>

      {showForm && (
        <div className="wk-panel wk-tag-form">
          <div className="wk-tag-form-title">{editing ? traducir('wiki.editar_etiqueta') : traducir('wiki.nueva_etiqueta_titulo')}</div>
          <div className="wk-tag-form-row">
            <div className="wk-tag-form-name">
              <label id={`${idCampo}-nombre-et`} htmlFor={`${idCampo}-nombre`} className="wk-label wk-label--plain">{traducir('wiki.nombre')}</label>
              <Input id={`${idCampo}-nombre`} aria-labelledby={`${idCampo}-nombre-et`} value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} placeholder={traducir('wiki.nombre_de_la_etiqueta')} autoFocus inputClassName="wk-input" />
            </div>
            <div>
              <div id={`${idCampo}-color-et`} className="wk-label wk-label--plain">{traducir('wiki.color')}</div>
              <div className="u-wrap-6" role="group" aria-labelledby={`${idCampo}-color-et`}>
                {TAG_COLORS.map(c=>(
                  <Pulsable key={c} type="button" aria-label={traducir('wiki.color_n', { color: c })} aria-pressed={form.color===c} onClick={()=>setForm(f=>({...f,color:c}))}
                    className={`wk-swatch${form.color===c ? ' wk-swatch--active' : ''}`}
                    style={{ '--wk-color': c } as CSSProperties}>{null}</Pulsable>
                ))}
              </div>
            </div>
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={()=>{setShowForm(false);setEditing(null)}}>{traducir('wiki.cancelar')}</Button>
            <Button onClick={()=>save(form)} loading={isPending} disabled={!form.name.trim()}>
              {editing ? traducir('wiki.actualizar') : traducir('wiki.crear')}
            </Button>
          </div>
        </div>
      )}

      {!space ? (
        <EmptyState icon={<Tag size={28} />} title={traducir('wiki.selecciona_un_espacio')}
          description={traducir('wiki.selecciona_un_espacio_wiki_para_ver_sus')} />
      ) : isLoading ? <div className="wk-center-pad"><Spinner /></div>
      : tags.length === 0 ? (
        <EmptyState icon={<Tag size={28} />} title={traducir('wiki.sin_etiquetas_en_este_espacio')}
          description={traducir('wiki.sin_etiquetas_desc')}
          action={<Button icon={<Plus size={14} />} onClick={()=>{setEditing(null);setForm({name:'',color:'var(--accent)'});setShowForm(true)}}>{traducir('wiki.nueva_etiqueta')}</Button>} />
      ) : (
        <div className="u-wrap-10">
          {tags.map(tag=>(
            <div key={tag.id} className="wk-tag">
              <div className="wk-tag-dot" style={{ '--wk-color': tag.color || 'var(--text-2)' } as CSSProperties} aria-hidden="true"/>
              <span className="u-text1-base-600">{tag.name}</span>
              <span className="u-text2-xs">{tag.page_count} {traducir('wiki.paginas')}</span>
              <IconButton variante="caja" onClick={()=>{setEditing(tag);setForm({name:tag.name||'',color:tag.color||'var(--accent)'});setShowForm(true)}}
                ariaLabel={traducir('wiki.editar_etiqueta_n', { nombre: tag.name ?? '' })} title={traducir('wiki.editar_etiqueta')}><Pencil size={13} /></IconButton>
              <IconButton variante="caja" tono="peligro" onClick={()=>{ openConfirmGlobal({ message: traducir('wiki.confirmar_eliminar_etiqueta'), onConfirm: () => del(tag.id), danger: true }) }}
                ariaLabel={traducir('wiki.eliminar_etiqueta_n', { nombre: tag.name ?? '' })} title={traducir('wiki.eliminar_etiqueta')}><Trash2 size={13} /></IconButton>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


export default function WikiPage() {
  const idCampo = useId()
  const traducir = useAppT() as Traducir
  const t = useAppT()
  const toast = useToast()
  const [wikiMode, setWikiMode] = useState('wiki') // 'wiki' | 'tags'

  const qc = useQueryClient()
  const [space,      setSpace]     = useState<WikiEspacio | null>(null)
  const [page,       setPage]      = useState<WikiPagina | null>(null)
  const [pageModal,  setPageModal] = useState(false)
  const [editPage,   setEditPage]  = useState<WikiPagina | null>(null)
  const [parentId,   setParentId]  = useState<string | null>(null)
  const [presentMode, setPresentMode] = useState(false)
  // Auditoria 2026-11 (#41): pantalla completa sin trampa de foco ni Esc.
  const presentRef = useDialogo<HTMLDivElement>(presentMode, () => setPresentMode(false))
  const [spaceModal, setSpaceModal]= useState(false)
  const [searchQ,    setSearchQ]   = useState('')
  const [searchRes,  setSearchRes] = useState<WikiResultadoDeBusqueda[] | null>(null)
  const [spaceForm,  setSpaceForm] = useState({name:'',slug:'',description:'',project_id:'',is_public:false})
  const [showHistory, setShowHistory] = useState(false)

  // 23-11-2026 (A8/A9 del 04): lista compartida; un fallo ya no se guarda como «sin proyectos».
  const { data:projects=[] } = useListaDeProyectos()
  const { data:versions=[], isLoading:lVer } = useQuery({
    queryKey:['wiki-versions', page?.id],
    queryFn:()=>wikiApi.versions(page!.id).then(r=>r.data),
    enabled:!!page?.id && showHistory,
  })

    const { data:spaces=[],isLoading:lSpaces } = useQuery<WikiEspacio[]>({queryKey:['wiki-spaces'],queryFn:()=>wikiApi.spaces().then(r=>r.data)})
  const { data:pages=[],isLoading:lPages }   = useQuery<WikiPaginaEnArbol[]>({queryKey:['wiki-pages',space?.id],queryFn:()=>wikiApi.pages(space!.id).then(r=>r.data),enabled:!!space})

  const { mutate:createSpace,isPending:cSpace } = useMutation({
    mutationFn: (d: Record<string, unknown>)=>wikiApi.createSpace(d).then(r=>r.data),
    onSuccess: ()=>{qc.invalidateQueries({ queryKey: ['wiki-spaces'] });setSpaceModal(false);setSpaceForm({name:'',slug:'',description:'',project_id:'',is_public:false})},
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate:restoreVersion, isPending:restoring } = useMutation({
    mutationFn: (vn: number)=>wikiApi.restorePage(page!.id, vn).then(r=>r.data),
    onSuccess: (d, vn)=>{
      qc.invalidateQueries({ queryKey: ['wiki-pages', space?.id] })
      qc.invalidateQueries({ queryKey: ['wiki-versions', page?.id] })
      setShowHistory(false)
      toast.info(traducir('wiki.restaurado_a_version', { version: vn, nueva: d.new_version ?? '' }))
      // Recargar página actual
      if (page) wikiApi.getPage(page.id).then(r=>setPage(r.data)).catch((e: unknown)=>toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)))
    },
    onError: (e: unknown) => toast.error(extractErr(e, traducir('wiki.error_restaurar'))),
  })

    const { mutate:deletePage } = useMutation({
    mutationFn: (id: string)=>wikiApi.deletePage(id),
    onSuccess: ()=>{qc.invalidateQueries({ queryKey: ['wiki-pages',space?.id] });setPage(null)},
    onError: (e: unknown) => toast.error(extractErr(e, traducir('wiki.error_eliminar'))),
  })

  const openPage = async (p: { id: string }) => {
    try { setPage((await wikiApi.getPage(p.id)).data) }
    catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }

  const doSearch = async () => {
    if(!searchQ.trim()) return
    const r = await wikiApi.search(searchQ, space?.id)
    setSearchRes(r.data)
  }

  const autoSlug = (t: string) => t.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')

  return (
    <PageShell>
      <PageHeader icon={<BookOpen size={18} />} title={t('nav.wiki')} subtitle={t('wiki.subtitle')}
        actions={wikiMode==='wiki' ? <Button icon={<Plus size={14} />} onClick={()=>setSpaceModal(true)}>{traducir('wiki.nuevo_espacio')}</Button> : undefined}
        showListExport={false}/>

      <div className="ds-page">
      <Tabs ariaLabel={traducir('wiki.modo')} active={wikiMode} onChange={setWikiMode}
        items={[
          { id: 'wiki', label: traducir('wiki.paginas_2'), icon: <BookOpen size={14} /> },
          { id: 'tags', label: traducir('wiki.etiquetas'), icon: <Tag size={14} /> },
        ]} />

      {wikiMode === 'tags' && <WikiTagsInline />}
      {wikiMode === 'wiki' && <div className="ds-toolbar wk-search" role="search">
        <Buscador value={searchQ} onChange={v => {setSearchQ(v);if(!v)setSearchRes(null)}}
          onKeyDown={e=>{ if (e.key==='Enter') doSearch() }}
          placeholder={traducir('wiki.buscar_placeholder')} aria-label={traducir('wiki.buscar_placeholder')} inputClassName="wk-input wk-input--search"/>
        <Button variant="secondary" icon={<Search size={14} />} onClick={doSearch}>{traducir('wiki.buscar')}</Button>
        {searchRes&&<IconButton onClick={()=>{setSearchRes(null);setSearchQ('')}} ariaLabel={traducir('wiki.limpiar_busqueda')}><X size={14} /></IconButton>}
      </div>}

      {searchRes&&(
        <div className="wk-panel wk-panel--results">
          <div className="wk-results-title">{searchRes.length} {traducir('wiki.resultados_para')}{searchQ}&quot;</div>
          {searchRes.length===0
            ? <EmptyState icon={<SearchX size={28} />} title={traducir('wiki.sin_resultados')} description={traducir('wiki.sin_resultados_desc')}/>
            : searchRes.map(p=>(
              <div key={p.id} onClick={()=>openPage(p)}
                role="button"
                tabIndex={0}
                onKeyDown={e => onKeyboardActivate(e, () => openPage(p))}
                className="wk-result">
                <div className="wk-strong-500">{p.title}</div>
                <div className="u-text2-xs">{p.updated_at?fmtDate(p.updated_at):''}</div>
              </div>
            ))
          }
        </div>
      )}

      {wikiMode === 'wiki' && <div className="wk-layout">
        <div className="u-stack-12">
          <div className="wk-panel wk-panel--side">
            <div className="wk-side-title">{traducir('wiki.espacios')}</div>
            {lSpaces?<Spinner/>:spaces.length===0
              ?<EmptyState icon={<FolderOpen size={28} />} title={traducir('wiki.sin_espacios_aun')} description={traducir('wiki.sin_espacios_desc')}/>
              :spaces.map(s=>(
                <div key={s.id} onClick={()=>{setSpace(s);setPage(null)}}
                  role="button"
                  tabIndex={0}
                  aria-pressed={space?.id===s.id}
                  onKeyDown={e => onKeyboardActivate(e, () => { setSpace(s); setPage(null) })}
                  className={`wk-space${space?.id===s.id ? ' wk-space--active' : ''}`}>
                  <div className="wk-space-name"><Folder size={13} aria-hidden="true" /> <span className="wk-space-label">{s.name}</span></div>
                  <div className="u-text3-xs">{s.page_count} {traducir('wiki.paginas')}</div>
                </div>
              ))
            }
          </div>
          {space&&(
            <div className="wk-panel wk-panel--side">
              <div className="wk-side-head">
                <div className="wk-side-title">{traducir('wiki.paginas_2')}</div>
                <IconButton onClick={()=>{setParentId(null);setEditPage(null);setPageModal(true)}}
                  ariaLabel={traducir('wiki.nueva_pagina')} title={traducir('wiki.nueva_pagina')}><Plus size={14} /></IconButton>
              </div>
              {lPages?<Spinner/>:pages.length===0
                ?<p className="wk-side-empty">{traducir('wiki.no_pages')}</p>
                :<PageTree pages={pages} selectedId={page?.id} onSelect={openPage}
                    onNew={pid=>{setParentId(pid);setEditPage(null);setPageModal(true)}}/>
              }
            </div>
          )}
        </div>

        <div className="wk-panel">
          {!space
            ? <EmptyState icon={<BookOpen size={28} />} title={traducir('wiki.selecciona_un_espacio')} description={traducir('wiki.selecciona_espacio_desc')}/>
            : !page
              ? <EmptyState icon={<FileText size={28} />} title={space.name}
                  description={space.description||traducir('wiki.sin_descripcion')}
                  action={<Button icon={<Plus size={14} />} onClick={()=>{setParentId(null);setEditPage(null);setPageModal(true)}}>{traducir('wiki.primera_pagina')}</Button>} />
              : <div>
                  <div className="wk-page-head">
                    <h1 className="wk-page-title">{page.title}</h1>
                    <div className="wk-page-actions">
                      <CollabIndicator docId={page.id} />
                      <Button variant="secondary" icon={<Pencil size={14} />} onClick={()=>{setEditPage(page);setPageModal(true)}}>{traducir('wiki.editar')}</Button>
                      <Button variant="secondary" icon={<Play size={14} />} onClick={()=>setPresentMode(true)}>{traducir('wiki.presentar')}</Button>
                      <Button variant="secondary" icon={<History size={14} />} onClick={()=>setShowHistory(true)}>{traducir('wiki.historial')}</Button>
                      <IconButton variante="caja" tono="peligro" onClick={()=>{ openConfirmGlobal({ message: traducir('wiki.confirmar_eliminar_pagina', { titulo: page.title }), onConfirm: () => deletePage(page.id), danger: true }) }}
                        ariaLabel={traducir('wiki.delete_page')}><Trash2 size={15} /></IconButton>
                    </div>
                  </div>
                  <div className="wk-page-body">
                    {(page.content||[]).length===0
                      ?<p className="wk-page-empty">{traducir('wiki.pagina_vacia_pulsa_editar_para_anadir_contenido')}</p>
                      :renderBlocks(Array.isArray(page.content)?page.content:[], traducir)
                    }
                  </div>
                  <div className="wk-page-meta">
                    {traducir('wiki.ultima_actualizacion')} {fmtDateTime(page.updated_at)}
                  </div>
                </div>
          }
        </div>
      </div>}
      </div>

      {spaceModal&&(
        <Modal open onClose={()=>setSpaceModal(false)} title={traducir('wiki.nuevo_espacio_wiki')}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="wk-label">{traducir('wiki.nombre')}</label><Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={spaceForm.name} onChange={e=>setSpaceForm(f=>({...f,name:e.target.value,slug:autoSlug(e.target.value)}))} inputClassName="wk-input" /></div>
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="wk-label">{traducir('wiki.slug')}</label><Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={spaceForm.slug} onChange={e=>setSpaceForm(f=>({...f,slug:e.target.value}))} inputClassName="wk-input wk-input--mono ds-campo-codigo" /></div>
            <div><label id={`${idCampo}-etdesc`} htmlFor={`${idCampo}-desc`} className="wk-label">{traducir('wiki.descripcion')}</label><Input id={`${idCampo}-desc`} aria-labelledby={`${idCampo}-etdesc`} value={spaceForm.description} onChange={e=>setSpaceForm(f=>({...f,description:e.target.value}))} placeholder={traducir('wiki.describe_el_objetivo_del_espacio')} inputClassName="wk-input" /></div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="wk-label">{traducir('wiki.proyecto_opcional')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-3`} className="wk-input" value={spaceForm.project_id} onChange={e=>setSpaceForm(f=>({...f,project_id:e.target.value}))}>
                <option value="">{traducir('wiki.sin_proyecto')}</option>
                {projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
              </Select>
            </div>
            <div className="wk-actions">
              <Button variant="secondary" onClick={()=>setSpaceModal(false)}>{traducir('wiki.cancelar')}</Button>
              <Button onClick={()=>createSpace(spaceForm)} disabled={cSpace||!spaceForm.name||!spaceForm.slug} loading={cSpace}>
                {cSpace?traducir('wiki.creando'):traducir('wiki.crear_espacio')}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {showHistory && page && (
        <Modal open onClose={()=>setShowHistory(false)} title={traducir('wiki.historial_de', { titulo: page.title })}>
          <div className="wk-history">
            <div className="wk-history-intro">
              {traducir('wiki.cada_vez_que_guardas_una_pagina_se')}
            </div>
            {lVer && <div className="wk-history-msg" role="status" aria-label={traducir('wiki.cargando_versiones')}><Spinner /></div>}
            {!lVer && versions.length===0 && (
              <EmptyState icon={<History size={28} />} title={traducir('wiki.sin_versiones_registradas')} description={traducir('wiki.sin_versiones_desc')} />
            )}
            {!lVer && versions.map((v,i)=>(
              <div key={v.id} className="wk-version">
                <div className={`wk-version-badge${i===0 ? ' wk-version-badge--current' : ''}`}>
                  v{v.version_num}
                </div>
                <div className="u-flex1">
                  <div className="wk-version-title">{v.title}</div>
                  <div className="u-text2-xs-mt2">
                    {v.change_note||traducir('wiki.actualizacion')} · {fmtDateTime(v.created_at)}
                  </div>
                </div>
                {i===0
                  ? <StatusBadge kind="accent" caps={false}>{traducir('wiki.actual')}</StatusBadge>
                  : <Button size="sm" variant="secondary" icon={<RotateCcw size={13} />} loading={restoring}
                      onClick={()=>{ openConfirmGlobal({ message: traducir('wiki.confirmar_restaurar', { version: v.version_num }), onConfirm: () => restoreVersion(v.version_num), danger: true }) }}>
                      {traducir('wiki.restaurar')}
                    </Button>
                }
              </div>
            ))}
            <div className="wk-history-foot">
              <Button variant="secondary" onClick={()=>setShowHistory(false)}>{traducir('wiki.cerrar')}</Button>
            </div>
          </div>
        </Modal>
      )}

            {pageModal&&(
        <PageModal spaceId={space?.id} parentId={parentId} editPage={editPage}
          onClose={()=>{setPageModal(false);setEditPage(null);setParentId(null)}}/>
      )}

      {/* Modo presentación full-screen */}
      {presentMode && page && (
        <div ref={presentRef} role="dialog" aria-modal="true" aria-label={page.title} tabIndex={-1} className="wk-present">
          <div className="wk-present-bar">
            <div className="wk-present-name">{page.title}</div>
            <Button variant="secondary" icon={<X size={14} />} onClick={() => setPresentMode(false)}>
              {traducir('wiki.salir_presentacion')}
            </Button>
          </div>
          <div className="wk-present-body">
            <h1 className="wk-present-title">
              {page.title}
            </h1>
            <div className="wk-present-content">
              {renderBlocks(Array.isArray(page.content) ? page.content : [], traducir)}
            </div>
          </div>
        </div>
      )}
    </PageShell>
  )
}
