import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const ps = { background:'var(--surface-2)', border:'1px solid #1e2d45', borderRadius:12, padding:'20px 24px' }
const is = { width:'100%', background:'var(--surface-3)', border:'1px solid #1e2d45', borderRadius:8, padding:'8px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const ENTITY_ICONS = { task:'📌', ticket:'🎫', wiki_comment:'💬', wiki_page:'📄', comment:'💬' }

function MentionCard({ mention, onRead }) {
  const icon = ENTITY_ICONS[mention.entity_type] || '🔔'
  const timeAgo = (iso) => {
    const diff = Date.now() - new Date(iso).getTime()
    const m = Math.floor(diff/60000), h = Math.floor(diff/3600000), d = Math.floor(diff/86400000)
    if(d>0) return `hace ${d}d`
    if(h>0) return `hace ${h}h`
    return `hace ${m}m`
  }
  return (
    <div style={{padding:'14px 16px',background: mention.is_read?'transparent':'var(--accent-muted)',border:`1px solid ${mention.is_read?'var(--surface-4)':'var(--accent-glow)'}`,borderRadius:10,marginBottom:8}}>
      <div style={{display:'flex',alignItems:'flex-start',gap:12}}>
        <div style={{fontSize:20,flexShrink:0,marginTop:2}}>{icon}</div>
        <div style={{flex:1}}>
          <div style={{display:'flex',gap:8,alignItems:'center',marginBottom:6}}>
            <span style={{fontSize:12,fontWeight:600,color:'var(--accent)'}}>{mention.entity_type.replace(/_/g,' ')}</span>
            <span style={{fontSize:11,color:'var(--text-3)'}}>{mention.created_at?timeAgo(mention.created_at):''}</span>
            {!mention.is_read&&<span style={{fontSize:10,padding:'1px 6px',borderRadius:4,background:'var(--accent-glow)',color:'var(--accent)',fontWeight:600}}>NUEVA</span>}
          </div>
          {mention.context_text&&(
            <div style={{fontSize:13,color:'var(--text-2)',lineHeight:1.5,marginBottom:8,background:'var(--surface-1)',padding:'8px 12px',borderRadius:6,borderLeft:'2px solid #1e2d45'}}>
              &quot;...{mention.context_text.slice(0,200)}{mention.context_text.length>200?'...':''}&quot;
            </div>
          )}
          <div style={{fontSize:11,color:'var(--text-3)',fontFamily:'monospace'}}>
            {mention.entity_type} #{mention.entity_id?.slice(0,8)}
          </div>
        </div>
        {!mention.is_read&&(
          <button onClick={()=>onRead(mention.id)}
            style={{background:'none',border:'1px solid #1e2d45',borderRadius:6,padding:'4px 10px',color:'var(--text-2)',cursor:'pointer',fontSize:11,flexShrink:0}}>
            Marcar leída
          </button>
        )}
      </div>
    </div>
  )
}

function ThreadedCommentSection({ entityType, entityId, title }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [newContent, setNewContent] = useState('')
  const [replyTo,    setReplyTo]    = useState(null)
  const [replyContent,setReplyContent]=useState('')

  const { data:comments=[], isLoading } = useQuery({
    queryKey:['comments',entityType,entityId],
    queryFn:()=>api.get(`comments?entity_type=${entityType}&entity_id=${entityId}`).then(r=>r.data).catch(()=>[]),
    enabled:!!entityId,
  })

  const { mutate:addComment, isPending:adding } = useMutation({
    mutationFn: d=>api.post(`comments?entity_type=${entityType}&entity_id=${entityId}`,d).then(r=>r.data),
    onSuccess: ()=>{ qc.invalidateQueries(['comments',entityType,entityId]); setNewContent(''); setReplyTo(null); setReplyContent('') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate:resolveComment } = useMutation({
    mutationFn: id=>api.patch(`comments/${id}/resolve`),
    onSuccess: ()=>qc.invalidateQueries(['comments',entityType,entityId]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate:deleteComment } = useMutation({
    mutationFn: id=>api.delete(`comments/${id}`),
    onSuccess: ()=>qc.invalidateQueries(['comments',entityType,entityId]),
    onError: _e=>toast.info('No se puede eliminar: tiene respuestas'),
  })

  const CommentNode = ({ comment, depth=0 }) => (
    <div style={{marginLeft:depth*20,marginBottom:8}}>
      <div style={{padding:'12px 14px',background:comment.is_resolved?'rgba(255,255,255,0.03)':'var(--surface-1)',borderRadius:8,border:`1px solid ${comment.is_resolved?'var(--surface-4)':'var(--surface-4)'}`,opacity:comment.is_resolved?0.6:1}}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:6}}>
          <div style={{display:'flex',gap:8,alignItems:'center'}}>
            <span style={{fontSize:12,fontWeight:600,color:'var(--accent)'}}>{comment.created_by?.slice(0,8)||'Usuario'}</span>
            {comment.is_resolved&&<span style={{fontSize:10,padding:'1px 6px',borderRadius:4,background:'var(--success-bg)',color:'var(--success)'}}>Resuelto</span>}
          </div>
          <div style={{display:'flex',gap:6}}>
            {!comment.is_resolved&&<button onClick={()=>setReplyTo(comment.id)} style={{background:'none',border:'none',color:'var(--text-2)',cursor:'pointer',fontSize:11}}>Responder</button>}
            {!comment.is_resolved&&<button onClick={()=>resolveComment(comment.id)} style={{background:'none',border:'none',color:'var(--success)',cursor:'pointer',fontSize:11}}>✓ Resolver</button>}
            <button onClick={()=>{ openConfirmGlobal({ message: '¿Eliminar?', onConfirm: () => deleteComment(comment.id), danger: true }) }} style={{background:'none',border:'none',color:'var(--danger)',cursor:'pointer',fontSize:11}}>✕</button>
          </div>
        </div>
        <div style={{fontSize:13,color:'var(--text-1)',lineHeight:1.5}}>{comment.content}</div>
        {replyTo===comment.id&&(
          <div style={{marginTop:10}}>
            <textarea value={replyContent} onChange={e=>setReplyContent(e.target.value)}
              placeholder="Escribe una respuesta... (usa @nombre para mencionar)"
              rows={2} style={{...is,marginBottom:8,resize:'vertical'}}/>
            <div style={{display:'flex',gap:6}}>
              <Button onClick={()=>addComment({content:replyContent,parent_id:comment.id})} disabled={adding||!replyContent.trim()}>
                {adding?'...':'Responder'}
              </Button>
              <Button variant="secondary" onClick={()=>{setReplyTo(null);setReplyContent('')}}>Cancelar</Button>
            </div>
          </div>
        )}
      </div>
      {(comment.replies||[]).map(r=><CommentNode key={r.id} comment={r} depth={depth+1}/>)}
    </div>
  )

  if(!entityId) return null

  return (
    <div>
      <div style={{fontSize:13,fontWeight:600,marginBottom:12}}>💬 Comentarios — {title}</div>
      {isLoading?<Spinner/>:(
        comments.length===0
          ?<div style={{fontSize:12,color:'var(--text-3)',marginBottom:12}}>Sin comentarios aún.</div>
          :comments.map(c=><CommentNode key={c.id} comment={c}/>)
      )}
      <div style={{marginTop:12}}>
        <textarea value={newContent} onChange={e=>setNewContent(e.target.value)}
          placeholder="Añadir comentario... (usa @nombre para mencionar)"
          rows={2} style={{...is,marginBottom:8,resize:'vertical'}}/>
        <Button onClick={()=>addComment({content:newContent,parent_id:null})} disabled={adding||!newContent.trim()}>
          {adding?'Enviando...':'Añadir comentario'}
        </Button>
      </div>
    </div>
  )
}

export default function MentionsPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab,        setTab]        = useState('mentions')
  const [onlyUnread, setOnlyUnread] = useState(true)
  const [demoEntity, setDemoEntity] = useState('')
  const [demoType,   setDemoType]   = useState('task')

  const { data:mentions=[], isLoading } = useQuery({
    queryKey:['mentions',onlyUnread],
    queryFn:()=>api.get(`mentions?only_unread=${onlyUnread}`).then(r=>r.data).catch(()=>[]),
  })

  const { mutate:markRead } = useMutation({
    mutationFn: id=>api.post(`mentions/${id}/read`),
    onSuccess: ()=>qc.invalidateQueries(['mentions']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate:markAll } = useMutation({
    mutationFn: ()=>api.post('mentions/read-all'),
    onSuccess: ()=>qc.invalidateQueries(['mentions']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const unreadCount = mentions.filter(m=>!m.is_read).length

  return (
    <div style={{padding:32}}>
      <PageHeader title={t('mentions.title')} subtitle="@menciones recibidas y comentarios threaded en tareas y tickets"/>

      {/* Tabs */}
      <div style={{display:'flex',gap:6,marginBottom:20}}>
        {[['mentions','🔔 Mis menciones'],['comments','💬 Comentarios threaded']].map(([t,label])=>(
          <button key={t} onClick={()=>setTab(t)}
            style={{padding:'7px 16px',borderRadius:8,border:'1px solid #1e2d45',background:tab===t?'var(--accent-muted)':'transparent',color:tab===t?'var(--accent)':'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize:13}}>
            {label}
          </button>
        ))}
      </div>

      {/* TAB: Menciones */}
      {tab==='mentions'&&(
        <div>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:16}}>
            <div style={{display:'flex',gap:8,alignItems:'center'}}>
              <label style={{display:'flex',alignItems:'center',gap:6,cursor:'pointer',fontSize:13}}>
                <input type="checkbox" checked={onlyUnread} onChange={e=>setOnlyUnread(e.target.checked)}/>
                Solo no leídas
              </label>
              {unreadCount>0&&<span style={{fontSize:12,padding:'2px 8px',borderRadius:20,background:'var(--accent-glow)',color:'var(--accent)',fontWeight:600}}>{unreadCount} nuevas</span>}
            </div>
            {unreadCount>0&&(
              <Button variant="secondary" onClick={()=>markAll()}>✓ Marcar todas leídas</Button>
            )}
          </div>

          {isLoading?<Spinner/>:mentions.length===0
            ?<EmptyState icon="🔔" title={onlyUnread?'Sin menciones nuevas':'Sin menciones'} description={onlyUnread?'No tienes @menciones sin leer':'Nadie te ha mencionado aún'}/>
            :mentions.map(m=><MentionCard key={m.id} mention={m} onRead={id=>markRead(id)}/>)
          }
        </div>
      )}

      {/* TAB: Comentarios threaded */}
      {tab==='comments'&&(
        <div>
          <div style={{...ps,marginBottom:20}}>
            <div style={{fontSize:13,color:'var(--text-2)',marginBottom:14,lineHeight:1.6}}>
              Los comentarios threaded están disponibles en cualquier tarea o ticket. Selecciona una entidad para ver y añadir comentarios:
            </div>
            <div style={{display:'grid',gridTemplateColumns:'auto 1fr',gap:12,alignItems:'flex-end'}}>
              <div>
                <label style={ls}>Tipo</label>
                <select value={demoType} onChange={e=>setDemoType(e.target.value)} style={{...is,width:130}}>
                  <option value="task">📌 Tarea</option>
                  <option value="ticket">🎫 Ticket</option>
                </select>
              </div>
              <div>
                <label style={ls}>ID de la entidad</label>
                <input value={demoEntity} onChange={e=>setDemoEntity(e.target.value)}
                  placeholder="Pega el ID de la tarea o ticket..." style={is}/>
              </div>
            </div>
          </div>

          {demoEntity?(
            <div style={ps}>
              <ThreadedCommentSection entityType={demoType} entityId={demoEntity} title={`${demoType} #${demoEntity.slice(0,8)}`}/>
            </div>
          ):(
            <div style={{...ps,textAlign:'center',padding:'40px 24px'}}>
              <div style={{fontSize:48,marginBottom:16}}>💬</div>
              <div style={{fontSize:14,color:'var(--text-2)'}}>Introduce el ID de una tarea o ticket para ver sus comentarios</div>
            </div>
          )}

          <div style={{...ps,marginTop:16,padding:'14px 18px'}}>
            <div style={{fontSize:12,fontWeight:600,color:'var(--text-3)',textTransform:'uppercase',letterSpacing:'.07em',marginBottom:8}}>Cómo usar @menciones</div>
            <div style={{fontSize:12,color:'var(--text-2)',lineHeight:1.8}}>
              En cualquier comentario escribe <code style={{color:'var(--accent)',background:'var(--accent-muted)',padding:'1px 5px',borderRadius:4}}>@uuid-del-usuario</code> para mencionarlo.
              Recibirá una notificación en la pestaña &quot;Mis menciones&quot; y en el panel de alertas del sistema.
              Los comentarios admiten respuestas anidadas (un nivel de profundidad) y se pueden marcar como resueltos.
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
