import { CHART } from '../constants/theme'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useEffect, useRef, useState } from 'react'
import { useToast } from '../context/ToastContext'
import { useDocCollab } from '../hooks/useDocCollab'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const ps = { background:'var(--surface-2)', border:'1px solid #1e2d45', borderRadius:12, padding:'20px 24px' }
const is = { width:'100%', background:'var(--surface-3)', border:'1px solid #1e2d45', borderRadius:8, padding:'8px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const BLOCK_TYPES = [
  {type:'paragraph',icon:'¶',label:'Texto'},
  {type:'heading1',icon:'H1',label:'Título 1'},
  {type:'heading2',icon:'H2',label:'Título 2'},
  {type:'heading3',icon:'H3',label:'Título 3'},
  {type:'bullet',icon:'•',label:'Lista'},
  {type:'numbered',icon:'1.',label:'Numerada'},
  {type:'code',icon:'<>',label:'Código'},
  {type:'quote',icon:'"',label:'Cita'},
  {type:'divider',icon:'—',label:'Separador'},
  {type:'callout',icon:'💡',label:'Llamada'},
  {type:'task_list',icon:'☑',label:'Checklist'},
]

const TEMPLATES = [
  { id:'meeting', name:'📋 Acta de reunión', blocks:[
    {type:'heading1',content:'Acta de reunión — [fecha]'},
    {type:'heading2',content:'Asistentes'},{type:'bullet',content:''},
    {type:'heading2',content:'Puntos tratados'},{type:'numbered',content:''},
    {type:'heading2',content:'Decisiones'},{type:'bullet',content:''},
    {type:'heading2',content:'Próximas acciones'},{type:'task_list',content:''},
  ]},
  { id:'spec', name:'📐 Especificación técnica', blocks:[
    {type:'heading1',content:'Especificación: [nombre]'},
    {type:'heading2',content:'Objetivo'},{type:'paragraph',content:''},
    {type:'heading2',content:'Alcance'},{type:'paragraph',content:''},
    {type:'heading2',content:'Diseño técnico'},{type:'code',content:''},
    {type:'heading2',content:'Criterios de aceptación'},{type:'numbered',content:''},
  ]},
  { id:'retro', name:'🔄 Retrospectiva', blocks:[
    {type:'heading1',content:'Retrospectiva — Sprint [N]'},
    {type:'heading2',content:'Qué fue bien'},{type:'bullet',content:''},
    {type:'heading2',content:'Qué mejorar'},{type:'bullet',content:''},
    {type:'heading2',content:'Acciones para el próximo sprint'},{type:'task_list',content:''},
  ]},
  { id:'postmortem', name:'🔍 Post-mortem', blocks:[
    {type:'heading1',content:'Post-mortem'},
    {type:'heading2',content:'Resumen del incidente'},{type:'paragraph',content:''},
    {type:'heading2',content:'Cronología'},{type:'numbered',content:''},
    {type:'heading2',content:'Causa raíz'},{type:'paragraph',content:''},
    {type:'heading2',content:'Acciones correctivas'},{type:'task_list',content:''},
  ]},
  { id:'blank', name:'📄 Página en blanco', blocks:[{type:'paragraph',content:''}] },
]

function onKeyboardActivate(event, action) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}

function BlockEditor({ blocks, onChange }) {
  const update = (i, k, v) => { const n=[...blocks]; n[i]={...n[i],[k]:v}; onChange(n) }
  const add    = (after, type='paragraph') => { const n=[...blocks]; n.splice(after+1,0,{type,content:''}); onChange(n) }
  const remove = (i) => { if(blocks.length>1) onChange(blocks.filter((_,x)=>x!==i)) }
  const move   = (i, d) => { const n=[...blocks]; const t=i+d; if(t<0||t>=n.length) return; [n[i],n[t]]=[n[t],n[i]]; onChange(n) }

  const styleForType = (type) => {
    const base = {width:'100%',background:'transparent',border:'none',outline:'none',color:'var(--text-1)',fontFamily:'inherit',resize:'none',lineHeight:1.7,padding:'2px 0'}
    if(type==='heading1') return {...base,fontSize:24,fontWeight:800}
    if(type==='heading2') return {...base,fontSize:18,fontWeight:700}
    if(type==='heading3') return {...base,fontSize:15,fontWeight:700}
    if(type==='code')     return {...base,fontFamily:'monospace',fontSize:13,background:'var(--surface-1)',padding:'8px 12px',borderRadius:6,color:'var(--success)'}
    if(type==='quote')    return {...base,borderLeft:'3px solid #00d4ff',paddingLeft:12,color:'var(--text-2)',fontStyle:'italic'}
    if(type==='callout')  return {...base,background:'var(--accent-muted)',padding:'8px 12px',borderRadius:8,border:'1px solid #00d4ff20'}
    return {...base,fontSize:14}
  }

  return (
    <div style={{display:'flex',flexDirection:'column',gap:4}}>
      {blocks.map((block,i) => (
        <div key={i} style={{display:'flex',gap:8,alignItems:'flex-start',padding:'2px 0'}}
          onPointerEnter={e=>e.currentTarget.querySelector('.bc').style.opacity='1'}
          onPointerLeave={e=>e.currentTarget.querySelector('.bc').style.opacity='0'}>
          <div className="bc" style={{display:'flex',flexDirection:'column',gap:2,opacity:0,transition:'opacity .15s',flexShrink:0,paddingTop:4}}>
            <button onClick={()=>move(i,-1)} style={{background:'none',border:'none',color:'var(--text-3)',cursor:'pointer',fontSize:10,padding:'1px 4px'}}>▲</button>
            <button onClick={()=>move(i, 1)} style={{background:'none',border:'none',color:'var(--text-3)',cursor:'pointer',fontSize:10,padding:'1px 4px'}}>▼</button>
            <button onClick={()=>remove(i)}  style={{background:'none',border:'none',color:'var(--danger)',cursor:'pointer',fontSize:10,padding:'1px 4px'}}>✕</button>
          </div>
          <div style={{flex:1}}>
            {block.type==='divider'
              ? <hr style={{border:'none',borderTop:'1px solid #1e2d45',margin:'8px 0'}}/>
              : <div style={{display:'flex',alignItems:'flex-start',gap:6}}>
                  {block.type==='bullet'    && <span style={{color:'var(--purple)',marginTop:4,flexShrink:0}}>•</span>}
                  {block.type==='numbered'  && <span style={{color:'var(--purple)',marginTop:4,flexShrink:0,fontSize:12}}>{i+1}.</span>}
                  {block.type==='task_list' && <input type="checkbox" style={{marginTop:6,flexShrink:0}}/>}
                  <div style={{flex:1,display:'flex',flexDirection:'column',gap:3}}>
                    {['paragraph','heading1','heading2','heading3','quote','callout'].includes(block.type) && (
                      <div style={{display:'flex',gap:3}}>
                        {[
                          {label:'B',style:{fontWeight:700},title:'Negrita',wrap:['**','**']},
                          {label:'I',style:{fontStyle:'italic'},title:'Cursiva',wrap:['*','*']},
                          {label:'`',style:{fontFamily:'monospace'},title:'Código',wrap:['`','`']},
                          {label:'🔗',style:{},title:'Enlace',wrap:['[','](url)']},
                        ].map(({label,style,title,wrap}) => (
                          <button key={label}
                            onMouseDown={e=>{
                              e.preventDefault()
                              const ta = e.currentTarget.closest('div').querySelector('textarea')
                              if(!ta) return
                              const s=ta.selectionStart,en=ta.selectionEnd,sel=ta.value.slice(s,en)||label
                              const rep=wrap[0]+(sel===label?'texto':sel)+wrap[1]
                              const nv=ta.value.slice(0,s)+rep+ta.value.slice(en)
                              update(i,'content',nv)
                              setTimeout(()=>{ta.focus();ta.setSelectionRange(s,s+rep.length)},10)
                            }}
                            title={title}
                            style={{background:'var(--surface-3)',border:'1px solid #1e2d45',
                              borderRadius:4,padding:'1px 7px',color:'var(--text-2)',
                              cursor:'pointer',fontSize:11,lineHeight:'18px',...style}}>
                            {label}
                          </button>
                        ))}
                        {/* AI improve button */}
                        <button
                          title="Mejorar redaccion con IA"
                          onMouseDown={e=>{
                            e.preventDefault()
                            if(!block.content) return
                            api.post('/ai/chat',{message:`Mejora la redacción y claridad del siguiente texto, manteniendo el significado original. Devuelve únicamente el texto mejorado:\n\n${block.content}`,context_type:'inline_editor'})
                              .then(r=>{ const t=r.data?.response||r.data?.message||''; if(t) update(i,'content',t) })
                              .catch(()=>{})
                          }}
                          style={{background:'var(--surface-3)',border:'1px solid #4a5568',
                            borderRadius:4,padding:'1px 7px',color:'#90cdf4',
                            cursor:'pointer',fontSize:11,lineHeight:'18px'}}>
                          ✨
                        </button>
                      </div>
                    )}
                    <textarea value={block.content||''} onChange={e=>update(i,'content',e.target.value)}
                      className="wiki-ta"
                      rows={block.type==='code'?4:1}
                      style={{...styleForType(block.type)}}
                      onKeyDown={e=>{
                        if(e.key==='Enter'&&!e.shiftKey&&block.type!=='code'){e.preventDefault();add(i)}
                        if(e.key==='Backspace'&&!block.content&&blocks.length>1){e.preventDefault();remove(i)}
                      }}
                      placeholder={block.type==='paragraph'?'Escribe aquí...':''} />
                  </div>
                </div>
            }
          </div>
          <select value={block.type} onChange={e=>update(i,'type',e.target.value)}
            style={{background:'var(--surface-3)',border:'1px solid #1e2d45',borderRadius:6,padding:'3px 6px',color:'var(--text-2)',fontSize:11,cursor:'pointer',flexShrink:0}}>
            {BLOCK_TYPES.map(bt=><option key={bt.type} value={bt.type}>{bt.icon} {bt.label}</option>)}
          </select>
        </div>
      ))}
      <button onClick={()=>add(blocks.length-1)}
        style={{alignSelf:'flex-start',background:'var(--surface-3)',border:'1px solid #1e2d45',borderRadius:6,padding:'5px 12px',color:'var(--text-2)',cursor:'pointer',fontSize:12,fontFamily:'inherit',marginTop:8}}>
        + Añadir bloque
      </button>
    </div>
  )
}

function renderBlocks(blocks) {
  return (blocks||[]).map((b,i)=>{
    const text = b.content||''
    const st = {margin:'4px 0',lineHeight:1.7}
    switch(b.type){
      case 'heading1':  return <h1  key={i} style={{...st,fontSize:26,fontWeight:800,marginTop:20}}>{text}</h1>
      case 'heading2':  return <h2  key={i} style={{...st,fontSize:18,fontWeight:700,marginTop:16}}>{text}</h2>
      case 'heading3':  return <h3  key={i} style={{...st,fontSize:15,fontWeight:700,marginTop:12,color:'var(--text-2)'}}>{text}</h3>
      case 'code':      return <pre key={i} style={{...st,background:'var(--surface-1)',padding:'12px 16px',borderRadius:8,fontFamily:'monospace',fontSize:13,color:'var(--success)',overflow:'auto'}}>{text}</pre>
      case 'quote':     return <blockquote key={i} style={{...st,borderLeft:'3px solid #00d4ff',paddingLeft:14,color:'var(--text-2)',fontStyle:'italic'}}>{text}</blockquote>
      case 'bullet':    return <div key={i} style={{...st,display:'flex',gap:10}}><span style={{color:'var(--purple)'}}>•</span><span>{text}</span></div>
      case 'numbered':  return <div key={i} style={{...st,display:'flex',gap:10}}><span style={{color:'var(--purple)',minWidth:20,fontSize:12}}>{i+1}.</span><span>{text}</span></div>
      case 'task_list': return <div key={i} style={{...st,display:'flex',gap:10,alignItems:'center'}}><input type="checkbox" readOnly/><span>{text}</span></div>
      case 'divider':   return <hr  key={i} style={{border:'none',borderTop:'1px solid #1e2d45',margin:'16px 0'}}/>
      case 'callout':   return <div key={i} style={{...st,background:'var(--accent-muted)',border:'1px solid #00d4ff20',borderRadius:8,padding:'12px 16px'}}>💡 {text}</div>
      default:          return <p   key={i} style={{...st,color:text?'var(--text-1)':'var(--text-3)'}}>{text||<em>Párrafo vacío</em>}</p>
    }
  })
}

function PageModal({ spaceId, parentId, editPage, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!editPage
  const autoSlug = t => t.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')
  const [title,      setTitle]     = useState(editPage?.title || '')
  const [slug,       setSlug]      = useState(editPage?.slug  || '')
  const [blocks,     setBlocks]    = useState(editPage?.content || [{type:'paragraph',content:''}])
  const [visibility, setVisibility]= useState(editPage?.visibility || 'team')
  const [tplStep,    setTplStep]   = useState(!isEdit)
  const applyingRemoteRef = useRef(false)

  const { connected: collabConnected, peers: collabPeers, sendUpdate: sendCollabUpdate } = useDocCollab(
    editPage?.id,
    (remoteBlocks) => {
      applyingRemoteRef.current = true
      setBlocks(Array.isArray(remoteBlocks) ? remoteBlocks : [{ type: 'paragraph', content: '' }])
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
  const VIS_OPTS = [
    { value: 'team',   label: '🔒 Solo equipo' },
    { value: 'portal', label: '🌐 Portal cliente' },
    { value: 'public', label: '🌍 Público' },
  ]

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit
      ? api.patch(`wiki/pages/${editPage.id}`, d).then(r=>r.data)
      : api.post(`wiki/spaces/${spaceId}/pages`, d).then(r=>r.data),
    onSuccess: () => { qc.invalidateQueries(['wiki-pages', spaceId]); onClose() },
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar página' : 'Nueva página'}>
      <div style={{display:'flex',flexDirection:'column',gap:14}}>
        {tplStep && !isEdit && (
          <div>
            <label style={ls}>Empezar desde plantilla</label>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8,marginBottom:10}}>
              {TEMPLATES.map(t=>(
                <button key={t.id} onClick={()=>{setBlocks(t.blocks);if(!title)setTitle(t.name.replace(/^.\s/,''));setTplStep(false)}}
                  style={{padding:'10px 14px',borderRadius:8,border:'1px solid #1e2d45',background:'var(--surface-3)',color:'var(--text-1)',cursor:'pointer',fontFamily:'inherit',fontSize:13,textAlign:'left'}}>
                  {t.name}
                </button>
              ))}
            </div>
            <button onClick={()=>setTplStep(false)} style={{background:'none',border:'none',color:'var(--text-3)',cursor:'pointer',fontSize:12}}>Continuar sin plantilla →</button>
          </div>
        )}
        {!tplStep && <>
          {isEdit && (
            <div style={{display:'flex',alignItems:'center',gap:8,padding:'8px 10px',borderRadius:8,background:collabConnected?'var(--success-bg)':'var(--surface-3)',border:`1px solid ${collabConnected?'#00e5a050':'#1e2d45'}`}}>
              <span style={{fontSize:11,color:collabConnected?'var(--success)':'var(--text-2)',fontWeight:700}}>
                {collabConnected ? `● Colaboración activa (${collabPeers} en vivo)` : '○ Reconectando colaboración...'}
              </span>
            </div>
          )}
          <div>
            <label style={ls}>Título</label>
            <input style={is} value={title} onChange={e=>{setTitle(e.target.value);if(!isEdit)setSlug(autoSlug(e.target.value))}} placeholder="Titulo de la pagina" aria-label="Titulo de la pagina"/>
          </div>
          <div>
            <label style={ls}>Slug</label>
            <input style={{...is,fontFamily:'monospace',fontSize:12}} value={slug} onChange={e=>setSlug(e.target.value)}/>
          </div>
          <div>
            <label style={ls}>Contenido</label>
            <div style={{background:'var(--surface-1)',border:'1px solid #1e2d45',borderRadius:8,padding:16}}>
              <BlockEditor blocks={blocks} onChange={setBlocks}/>
            </div>
          </div>
          <div style={{display:'flex',justifyContent:'flex-end',gap:10,marginTop:8}}>
            <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <div>
            <label style={ls}>Visibilidad</label>
            <div style={{display:'flex',gap:8}}>
              {VIS_OPTS.map(o=>(
                <button key={o.value} onClick={()=>setVisibility(o.value)}
                  style={{flex:1,padding:'8px 10px',borderRadius:8,border:`1px solid ${visibility===o.value?'var(--accent-glow)':'var(--surface-4)'}`,background:visibility===o.value?'var(--accent-muted)':'transparent',color:visibility===o.value?'var(--accent)':'var(--text-2)',fontSize:12,cursor:'pointer',fontFamily:'inherit'}}>
                  {o.label}
                </button>
              ))}
            </div>
          </div>
            <Button onClick={()=>mutate({title,slug,content:blocks,parent_id:parentId,is_published:true,visibility})} disabled={isPending||!title||!slug} loading={isPending}>
              {isPending?'Guardando...':(isEdit?'Guardar':'Crear página')}
            </Button>
          </div>
        </>}
      </div>
    </Modal>
  )
}

function PageTree({ pages, selectedId, onSelect, onNew, level=0 }) {
  return (
    <div style={{display:'flex',flexDirection:'column',gap:1}}>
      {pages.map(p=>(
        <div key={p.id}>
          <div onClick={()=>onSelect(p)}
            role="button"
            tabIndex={0}
            onKeyDown={e => onKeyboardActivate(e, () => onSelect(p))}
            style={{display:'flex',alignItems:'center',gap:8,padding:`6px 10px 6px ${10+level*14}px`,borderRadius:6,cursor:'pointer',background:selectedId===p.id?'var(--accent-muted)':'transparent',color:selectedId===p.id?'var(--accent)':'var(--text-1)',fontSize:13}}>
            <span style={{fontSize:11,color:'var(--text-3)'}}>📄</span>
            <span style={{flex:1,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{p.title}</span>
            {p.visibility === 'portal' && <span title="Visible en portal cliente" style={{fontSize:10,color:'var(--accent)'}}>🌐</span>}
            {p.visibility === 'public' && <span title="Visible publicamente" style={{fontSize:10,color:'var(--success)'}}>🌍</span>}
            <button onClick={e=>{e.stopPropagation();onNew(p.id)}} style={{background:'none',border:'none',color:'var(--text-3)',cursor:'pointer',fontSize:14,padding:'0 2px'}}>+</button>
          </div>
          {p.children?.length>0 && <PageTree pages={p.children} selectedId={selectedId} onSelect={onSelect} onNew={onNew} level={level+1}/>}
        </div>
      ))}
    </div>
  )
}

// ── Wiki Tags (integrado en WikiPage) ─────────────────────────────────────────
function CollabIndicator({ docId }) {
  const { connected, peers } = useDocCollab(docId)
  if (!connected) return null
  return (
    <div title={`${peers} editor${peers !== 1 ? 'es' : ''} activo${peers !== 1 ? 's' : ''}`}
      style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: '#68d391',
        background: '#1a3a2a', border: '1px solid #2d6a4f', borderRadius: 20, padding: '4px 10px' }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#68d391', display: 'inline-block',
        boxShadow: '0 0 6px #68d391' }} />
      {peers} en vivo
    </div>
  )
}

function WikiTagsInline() {
  const toast = useToast()
  const qc = useQueryClient()
  const [space, setSpace] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({ name: '', color: 'var(--accent)' })

  const { data: spaces = [] } = useQuery({
    queryKey: ['wiki-spaces-tags'],
    queryFn: () => api.get('wiki/spaces').then(r => r.data).catch(() => []),
  })
  const { data: tags = [], isLoading } = useQuery({
    queryKey: ['wiki-tags-inline', space],
    queryFn: () => space ? api.get(`/wiki-tags/${space}`).then(r => r.data).catch(() => []) : [],
    enabled: !!space,
  })

  const { mutate: save, isPending } = useMutation({
    mutationFn: d => editing
      ? api.patch(`/wiki-tags/${editing.id}`, d).then(r => r.data)
      : api.post(`/wiki-tags/${space}`, d).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries(['wiki-tags-inline', space])
      setShowForm(false); setEditing(null); setForm({ name: '', color: 'var(--accent)' })
      toast.success(editing ? 'Etiqueta actualizada' : 'Etiqueta creada')
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/wiki-tags/${id}`),
    onSuccess: () => { qc.invalidateQueries(['wiki-tags-inline', space]); toast.success('Etiqueta eliminada') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const COLORS = ['var(--accent)','var(--success)','var(--warning)','var(--danger)','var(--purple)','var(--warning)','var(--accent)',CHART.pink]

  return (
    <div>
      <div style={{display:'flex',gap:12,marginBottom:20,alignItems:'center'}}>
        <select value={space} onChange={e=>setSpace(e.target.value)}
          style={{background:'var(--surface-3)',border:'1px solid #1e2d45',borderRadius:8,padding:'8px 12px',color:'var(--text-1)',fontSize:13,outline:'none',fontFamily:'inherit',minWidth:220}}>
          <option value="">Seleccionar espacio wiki...</option>
          {spaces.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        {space && <Button size="sm" onClick={()=>{setEditing(null);setForm({name:'',color:'var(--accent)'});setShowForm(true)}}>+ Nueva etiqueta</Button>}
      </div>

      {showForm && (
        <div style={{background:'var(--surface-2)',border:'1px solid #1e2d45',borderRadius:12,padding:'20px 24px',marginBottom:20}}>
          <div style={{fontSize:13,fontWeight:700,marginBottom:14}}>{editing?'Editar':'Nueva'} etiqueta</div>
          <div style={{display:'grid',gridTemplateColumns:'1fr auto',gap:12,marginBottom:14}}>
            <div>
              <label style={{fontSize:11,fontWeight:600,color:'var(--text-2)',textTransform:'uppercase',display:'block',marginBottom:5}}>Nombre</label>
              <input value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))}
                style={{background:'var(--surface-3)',border:'1px solid #1e2d45',borderRadius:8,padding:'8px 12px',color:'var(--text-1)',fontSize:13,outline:'none',fontFamily:'inherit',width:'100%',boxSizing:'border-box'}}
                placeholder="Nombre de la etiqueta" aria-label="Nombre de la etiqueta" autoFocus />
            </div>
            <div>
              <label style={{fontSize:11,fontWeight:600,color:'var(--text-2)',textTransform:'uppercase',display:'block',marginBottom:5}}>Color</label>
              <div style={{display:'flex',gap:6}}>
                {COLORS.map(c=>(
                  <button key={c} onClick={()=>setForm(f=>({...f,color:c}))}
                    style={{width:28,height:28,borderRadius:6,background:c,border:form.color===c?'2px solid #fff':'2px solid transparent',cursor:'pointer'}} />
                ))}
              </div>
            </div>
          </div>
          <div style={{display:'flex',gap:8,justifyContent:'flex-end'}}>
            <button onClick={()=>{setShowForm(false);setEditing(null)}}
              style={{background:'transparent',border:'1px solid #1e2d45',borderRadius:8,padding:'7px 16px',color:'var(--text-2)',cursor:'pointer',fontSize:12,fontFamily:'inherit'}}>Cancelar</button>
            <Button onClick={()=>save(form)} loading={isPending} disabled={!form.name.trim()}>
              {editing?'Actualizar':'Crear'}
            </Button>
          </div>
        </div>
      )}

      {!space ? (
        <div style={{textAlign:'center',padding:'40px 0',color:'var(--text-2)',fontSize:13}}>
          Selecciona un espacio wiki para ver sus etiquetas
        </div>
      ) : isLoading ? <div style={{textAlign:'center',padding:40}}><Spinner /></div>
      : tags.length === 0 ? (
        <div style={{textAlign:'center',padding:'40px 0',color:'var(--text-2)',fontSize:13}}>
          <div style={{fontSize:32,marginBottom:8}}>🏷</div>
          Sin etiquetas en este espacio
        </div>
      ) : (
        <div style={{display:'flex',flexWrap:'wrap',gap:10}}>
          {tags.map(tag=>(
            <div key={tag.id} style={{display:'flex',alignItems:'center',gap:8,background:'var(--surface-2)',border:'1px solid #1e2d45',borderRadius:10,padding:'10px 14px'}}>
              <div style={{width:10,height:10,borderRadius:'50%',background:tag.color||'var(--text-2)',flexShrink:0}}/>
              <span style={{fontSize:13,fontWeight:600,color:'var(--text-1)'}}>{tag.name}</span>
              <span style={{fontSize:11,color:'var(--text-2)'}}>{tag.pages_count||0} páginas</span>
              <button onClick={()=>{setEditing(tag);setForm({name:tag.name,color:tag.color||'var(--accent)'});setShowForm(true)}}
                style={{background:'none',border:'none',color:'var(--text-2)',cursor:'pointer',fontSize:12,padding:'0 2px'}}>✎</button>
              <button onClick={()=>{ openConfirmGlobal({ message: '¿Eliminar etiqueta?', onConfirm: () => del(tag.id), danger: true }) }}
                style={{background:'none',border:'none',color:'var(--danger)',cursor:'pointer',fontSize:12,padding:'0 2px'}}>🗑</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


export default function WikiPage() {
  const t = useAppT()
  const toast = useToast()
  const [wikiMode, setWikiMode] = useState('wiki') // 'wiki' | 'tags'

  const qc = useQueryClient()
  const [space,      setSpace]     = useState(null)
  const [page,       setPage]      = useState(null)
  const [pageModal,  setPageModal] = useState(false)
  const [editPage,   setEditPage]  = useState(null)
  const [parentId,   setParentId]  = useState(null)
  const [presentMode, setPresentMode] = useState(false)
  const [spaceModal, setSpaceModal]= useState(false)
  const [searchQ,    setSearchQ]   = useState('')
  const [searchRes,  setSearchRes] = useState(null)
  const [spaceForm,  setSpaceForm] = useState({name:'',slug:'',description:'',project_id:'',is_public:false})
  const [showHistory, setShowHistory] = useState(false)

  const { data:projects=[] } = useQuery({queryKey:['projects'],queryFn:()=>api.get('/projects').then(r=>Array.isArray(r.data)?r.data:[]).catch(()=>[])})
  const { data:versions=[], isLoading:lVer } = useQuery({
    queryKey:['wiki-versions', page?.id],
    queryFn:()=>api.get(`wiki/pages/${page.id}/versions`).then(r=>r.data).catch(()=>[]),
    enabled:!!page?.id && showHistory,
  })

    const { data:spaces=[],isLoading:lSpaces } = useQuery({queryKey:['wiki-spaces'],queryFn:()=>api.get('wiki/spaces').then(r=>r.data).catch(()=>[])})
  const { data:pages=[],isLoading:lPages }   = useQuery({queryKey:['wiki-pages',space?.id],queryFn:()=>api.get(`wiki/spaces/${space.id}/pages`).then(r=>r.data).catch(()=>[]),enabled:!!space})

  const { mutate:createSpace,isPending:cSpace } = useMutation({
    mutationFn: d=>api.post('wiki/spaces',d).then(r=>r.data),
    onSuccess: ()=>{qc.invalidateQueries(['wiki-spaces']);setSpaceModal(false);setSpaceForm({name:'',slug:'',description:'',project_id:'',is_public:false})},
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate:restoreVersion, isPending:restoring } = useMutation({
    mutationFn: (vn)=>api.post(`wiki/pages/${page.id}/restore/${vn}`).then(r=>r.data),
    onSuccess: (d)=>{
      qc.invalidateQueries(['wiki-pages', space?.id])
      qc.invalidateQueries(['wiki-versions', page?.id])
      setShowHistory(false)
      toast.info(`Restaurado a versión ${d.restored_to}. Nueva versión: ${d.new_version}`)
      // Recargar página actual
      api.get(`wiki/pages/${page.id}`).then(r=>setPage(r.data)).catch(()=>{})
    },
    onError: e => toast.error(extractErr(e, 'Error al restaurar')),
  })

    const { mutate:deletePage } = useMutation({
    mutationFn: id=>api.delete(`wiki/pages/${id}`),
    onSuccess: ()=>{qc.invalidateQueries(['wiki-pages',space?.id]);setPage(null)},
    onError: e => toast.error(extractErr(e, 'Error al eliminar')),
  })

  const openPage = async (p) => {
    const full = await api.get(`wiki/pages/${p.id}`).then(r=>r.data).catch(()=>p)
    setPage(full)
  }

  const doSearch = async () => {
    if(!searchQ.trim()) return
    const r = await api.get(`wiki/search?q=${encodeURIComponent(searchQ)}${space?`&space_id=${space.id}`:''}`)
    setSearchRes(r.data)
  }

  const autoSlug = t => t.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')

  return (
    <div style={{padding:32}}>
      <PageHeader title={t('wiki.title')} subtitle={t('wiki.subtitle')}
        actions={
          <div style={{display:'flex',gap:8,alignItems:'center'}}>
            <div style={{display:'flex',gap:4,background:'var(--surface-2)',border:'1px solid #1e2d45',borderRadius:10,padding:4}}>
              {[['wiki','📚 Wiki'],['tags','🏷 Etiquetas']].map(([id,label])=>(
                <button key={id} onClick={()=>setWikiMode(id)}
                  style={{padding:'6px 14px',borderRadius:7,border:'none',
                    background:wikiMode===id?'var(--accent)':'transparent',
                    color:wikiMode===id?'var(--surface-0)':'var(--text-2)',
                    fontSize:12,fontWeight:700,cursor:'pointer',fontFamily:'inherit'}}>
                  {label}
                </button>
              ))}
            </div>
            {wikiMode==='wiki' && <Button onClick={()=>setSpaceModal(true)}>+ Nuevo espacio</Button>}
          </div>
        }/>

      {wikiMode === 'tags' ? <WikiTagsInline /> : <div style={{display:'none'}} />}
      {wikiMode === 'wiki' && <div style={{display:'flex',gap:8,marginBottom:20}}>
        <input value={searchQ} onChange={e=>{setSearchQ(e.target.value);if(!e.target.value)setSearchRes(null)}}
          onKeyDown={e=>e.key==='Enter'&&doSearch()}
          placeholder="Buscar paginas o contenido" aria-label="Buscar paginas o contenido" style={{...is,flex:1}}/>
        <Button onClick={doSearch}>Buscar</Button>
        {searchRes&&<Button variant="secondary" onClick={()=>{setSearchRes(null);setSearchQ('')}}>✕</Button>}
      </div>}

      {searchRes&&(
        <div style={{...ps,marginBottom:20}}>
          <div style={{fontSize:14,fontWeight:600,marginBottom:12}}>{searchRes.length} resultados para &quot;{searchQ}&quot;</div>
          {searchRes.length===0
            ? <EmptyState icon="🔍" title="Sin resultados" description="No se encontraron paginas para la busqueda actual"/>
            : searchRes.map(p=>(
              <div key={p.id} onClick={()=>openPage(p)}
                role="button"
                tabIndex={0}
                onKeyDown={e => onKeyboardActivate(e, () => openPage(p))}
                style={{padding:'10px 0',borderBottom:'1px solid #1e2d45',cursor:'pointer',color:'var(--accent)'}}>
                <div style={{fontWeight:500}}>{p.title}</div>
                <div style={{fontSize:11,color:'var(--text-2)'}}>{p.updated_at?new Date(p.updated_at).toLocaleDateString('es-ES'):''}</div>
              </div>
            ))
          }
        </div>
      )}

      <div style={{display:'grid',gridTemplateColumns:'240px 1fr',gap:20}}>
        <div style={{display:'flex',flexDirection:'column',gap:12}}>
          <div style={{...ps,padding:14}}>
            <div style={{fontSize:11,fontWeight:700,color:'var(--text-3)',textTransform:'uppercase',letterSpacing:'.07em',marginBottom:10}}>Espacios</div>
            {lSpaces?<Spinner/>:spaces.length===0
              ?<div style={{color:'var(--text-3)',fontSize:12}}>Sin espacios aún</div>
              :spaces.map(s=>(
                <div key={s.id} onClick={()=>{setSpace(s);setPage(null)}}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => onKeyboardActivate(e, () => { setSpace(s); setPage(null) })}
                  style={{padding:'8px 10px',borderRadius:6,cursor:'pointer',marginBottom:2,background:space?.id===s.id?'var(--accent-muted)':'transparent',color:space?.id===s.id?'var(--accent)':'var(--text-1)',fontSize:13}}>
                  <div style={{fontWeight:500,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>📁 {s.name}</div>
                  <div style={{fontSize:11,color:'var(--text-3)'}}>{s.page_count||0} páginas</div>
                </div>
              ))
            }
          </div>
          {space&&(
            <div style={{...ps,padding:14}}>
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:10}}>
                <div style={{fontSize:11,fontWeight:700,color:'var(--text-3)',textTransform:'uppercase',letterSpacing:'.07em'}}>Páginas</div>
                <button onClick={()=>{setParentId(null);setEditPage(null);setPageModal(true)}} style={{background:'none',border:'none',color:'var(--accent)',cursor:'pointer',fontSize:18,padding:0}}>+</button>
              </div>
              {lPages?<Spinner/>:pages.length===0
                ?<div style={{color:'var(--text-3)',fontSize:12}}>Sin páginas</div>
                :<PageTree pages={pages} selectedId={page?.id} onSelect={openPage}
                    onNew={pid=>{setParentId(pid);setEditPage(null);setPageModal(true)}}/>
              }
            </div>
          )}
        </div>

        <div style={ps}>
          {!space
            ? <EmptyState icon="📚" title="Selecciona un espacio" description="Elige un espacio wiki para ver o crear paginas"/>
            : !page
              ? <div style={{textAlign:'center',padding:'48px 24px'}}>
                  <div style={{fontSize:48,marginBottom:16}}>📄</div>
                  <div style={{fontSize:15,fontWeight:600,marginBottom:8}}>{space.name}</div>
                  <div style={{fontSize:13,color:'var(--text-2)',marginBottom:20}}>{space.description||'Sin descripción'}</div>
                  <Button onClick={()=>{setParentId(null);setEditPage(null);setPageModal(true)}}>+ Primera página</Button>
                </div>
              : <div>
                  <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:24}}>
                    <h1 style={{fontSize:26,fontWeight:800}}>{page.title}</h1>
                    <div style={{display:'flex',gap:8,flexShrink:0}}>
                      <Button variant="secondary" onClick={()=>{setEditPage(page);setPageModal(true)}}>✏ Editar</Button>
                      <Button variant="secondary" onClick={()=>setPresentMode(true)}>▶ Presentar</Button>
                      <Button variant="secondary" onClick={()=>setShowHistory(true)}>🕐 Historial</Button>
                      <CollabIndicator docId={page.id} />
                      <button onClick={()=>{ openConfirmGlobal({ message: `¿Eliminar "${page.title}"?`, onConfirm: () => deletePage(page.id), danger: true }) }}
                        style={{background:'none',border:'1px solid #ff475730',borderRadius:8,padding:'6px 12px',color:'var(--danger)',cursor:'pointer',fontFamily:'inherit',fontSize:13}}>
                        🗑
                      </button>
                    </div>
                  </div>
                  <div style={{maxWidth:760}}>
                    {(page.content||[]).length===0
                      ?<p style={{color:'var(--text-3)',fontStyle:'italic'}}>Página vacía. Pulsa Editar para añadir contenido.</p>
                      :renderBlocks(Array.isArray(page.content)?page.content:[])
                    }
                  </div>
                  <div style={{marginTop:32,paddingTop:12,borderTop:'1px solid #1e2d45',fontSize:11,color:'var(--text-3)'}}>
                    Última actualización: {page.updated_at?new Date(page.updated_at).toLocaleString('es-ES'):'—'}
                  </div>
                </div>
          }
        </div>
      </div>

      {spaceModal&&(
        <Modal open onClose={()=>setSpaceModal(false)} title="Nuevo espacio wiki">
          <div style={{display:'flex',flexDirection:'column',gap:14}}>
            <div><label style={ls}>Nombre</label><input style={is} value={spaceForm.name} onChange={e=>setSpaceForm(f=>({...f,name:e.target.value,slug:autoSlug(e.target.value)}))}/></div>
            <div><label style={ls}>Slug</label><input style={{...is,fontFamily:'monospace',fontSize:12}} value={spaceForm.slug} onChange={e=>setSpaceForm(f=>({...f,slug:e.target.value}))}/></div>
            <div><label style={ls}>Descripción</label><input style={is} value={spaceForm.description} onChange={e=>setSpaceForm(f=>({...f,description:e.target.value}))} placeholder="Describe el objetivo del espacio" aria-label="Descripcion del espacio"/></div>
            <div><label style={ls}>Proyecto (opcional)</label>
              <select style={is} value={spaceForm.project_id} onChange={e=>setSpaceForm(f=>({...f,project_id:e.target.value}))}>
                <option value="">Sin proyecto</option>
                {projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            <div style={{display:'flex',justifyContent:'flex-end',gap:10,marginTop:8}}>
              <Button variant="secondary" onClick={()=>setSpaceModal(false)}>Cancelar</Button>
              <Button onClick={()=>createSpace(spaceForm)} disabled={cSpace||!spaceForm.name||!spaceForm.slug}>
                {cSpace?'Creando...':'Crear espacio'}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {showHistory && page && (
        <Modal open onClose={()=>setShowHistory(false)} title={`Historial — ${page.title}`}>
          <div style={{display:'flex',flexDirection:'column',gap:0}}>
            <div style={{fontSize:12,color:'var(--text-2)',marginBottom:14,lineHeight:1.6}}>
              Cada vez que guardas una página se crea una versión. Puedes restaurar cualquier versión anterior.
            </div>
            {lVer && <div style={{textAlign:'center',padding:20,color:'var(--text-2)'}}>Cargando versiones...</div>}
            {!lVer && versions.length===0 && (
              <div style={{textAlign:'center',padding:20,color:'var(--text-3)',fontSize:13}}>Sin versiones registradas</div>
            )}
            {!lVer && versions.map((v,i)=>(
              <div key={v.id} style={{display:'flex',alignItems:'center',gap:12,padding:'12px 0',borderBottom:'1px solid #1a2640'}}>
                <div style={{flexShrink:0,width:36,height:36,borderRadius:'50%',background:i===0?'var(--accent-muted)':'var(--surface-3)',border:`1px solid ${i===0?'var(--accent-glow)':'var(--surface-4)'}`,display:'flex',alignItems:'center',justifyContent:'center',fontSize:12,fontWeight:700,color:i===0?'var(--accent)':'var(--text-2)'}}>
                  v{v.version_num}
                </div>
                <div style={{flex:1}}>
                  <div style={{fontWeight:500,fontSize:13}}>{v.title}</div>
                  <div style={{fontSize:11,color:'var(--text-2)',marginTop:2}}>
                    {v.change_note||'Actualización'} · {v.created_at?new Date(v.created_at).toLocaleString('es-ES'):'—'}
                  </div>
                </div>
                {i===0
                  ? <span style={{fontSize:11,padding:'2px 8px',borderRadius:20,background:'var(--accent-muted)',color:'var(--accent)'}}>Actual</span>
                  : <button onClick={()=>{ openConfirmGlobal({ message: `¿Restaurar a versión ${v.version_num}? Esto creará una nueva versión con el contenido anterior.`, onConfirm: () => restoreVersion(v.version_num), danger: true }) }}
                      disabled={restoring}
                      style={{background:'none',border:'1px solid #1e2d45',borderRadius:6,padding:'4px 10px',color:'var(--text-2)',cursor:'pointer',fontSize:11,fontFamily:'inherit'}}>
                      {restoring?'...':'Restaurar'}
                    </button>
                }
              </div>
            ))}
            <div style={{display:'flex',justifyContent:'flex-end',marginTop:16}}>
              <button onClick={()=>setShowHistory(false)}
                style={{background:'none',border:'1px solid #1e2d45',borderRadius:8,padding:'6px 16px',color:'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize:13}}>
                Cerrar
              </button>
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
        <div style={{ position:'fixed', inset:0, background:'var(--surface-1)', zIndex:999,
          overflowY:'auto', display:'flex', flexDirection:'column' }}>
          <div style={{ position:'sticky', top:0, background:'var(--surface-2)',
            borderBottom:'1px solid var(--surface-4)', padding:'10px 24px',
            display:'flex', alignItems:'center', justifyContent:'space-between', zIndex:10 }}>
            <div style={{ fontSize:14, fontWeight:700, color:'var(--text-1)' }}>
              ▶ {page.title}
            </div>
            <button onClick={() => setPresentMode(false)}
              style={{ background:'var(--danger)', border:'none', borderRadius:8,
                padding:'7px 18px', color:'#fff', cursor:'pointer',
                fontSize:13, fontFamily:'inherit', fontWeight:600 }}>
              ✕ Salir presentación
            </button>
          </div>
          <div style={{ maxWidth:860, margin:'0 auto', padding:'48px 32px', width:'100%' }}>
            <h1 style={{ fontSize:38, fontWeight:900, marginBottom:32, color:'var(--text-1)',
              lineHeight:1.2, borderBottom:'2px solid var(--accent)', paddingBottom:16 }}>
              {page.title}
            </h1>
            <div style={{ fontSize:17, lineHeight:1.9, color:'var(--text-1)' }}>
              {renderBlocks(Array.isArray(page.content) ? page.content : [])}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
