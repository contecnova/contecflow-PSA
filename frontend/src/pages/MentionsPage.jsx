import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { AtSign } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding:'8px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const ENTITY_ICONS = { task:'📌', ticket:'🎫', wiki_comment:'💬', wiki_page:'📄', comment:'💬' }

function MentionCard({ mention, onRead }) {
  const t = useAppT()
  const icon = ENTITY_ICONS[mention.entity_type] || '🔔'
  const timeAgo = (iso) => {
    const diff = Date.now() - new Date(iso).getTime()
    const m = Math.floor(diff/60000), h = Math.floor(diff/3600000), d = Math.floor(diff/86400000)
    if(d>0) return t('mentions.time_days', { count: d })
    if(h>0) return t('mentions.time_hours', { count: h })
    return t('mentions.time_minutes', { count: m })
  }
  return (
    <div style={{padding:'14px 16px',background: mention.is_read?'transparent':'var(--accent-muted)',border:`1px solid ${mention.is_read?'var(--surface-4)':'var(--accent-glow)'}`,borderRadius: 8,marginBottom:8}}>
      <div style={{display:'flex',alignItems:'flex-start',gap:12}}>
        <div style={{fontSize:20,flexShrink:0,marginTop:2}}>{icon}</div>
        <div style={{flex:1}}>
          <div style={{display:'flex',gap:8,alignItems:'center',marginBottom:6}}>
            <span style={{fontSize:12,fontWeight:600,color:'var(--accent)'}}>{mention.entity_type.replace(/_/g,' ')}</span>
            <span style={{fontSize:11,color:'var(--text-3)'}}>{mention.created_at?timeAgo(mention.created_at):''}</span>
            {!mention.is_read&&<span style={{fontSize:10,padding:'1px 6px',borderRadius:4,background:'var(--accent-glow)',color:'var(--accent)',fontWeight:600}}>{t('mentions.new')}</span>}
          </div>
          {mention.context_text&&(
            <div style={{fontSize:13,color:'var(--text-2)',lineHeight:1.5,marginBottom:8,background:'var(--surface-1)',padding:'8px 12px',borderRadius:6,borderLeft:'2px solid var(--surface-4)'}}>
              &quot;...{mention.context_text.slice(0,200)}{mention.context_text.length>200?'...':''}&quot;
            </div>
          )}
          <div style={{fontSize:11,color:'var(--text-3)',fontFamily:'monospace'}}>
            {mention.entity_type} #{mention.entity_id?.slice(0,8)}
          </div>
        </div>
        {!mention.is_read&&(
          <button onClick={()=>onRead(mention.id)}
            style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'4px 10px',color:'var(--text-2)',cursor:'pointer',fontSize:11,flexShrink:0}}>
            {t('mentions.mark_read')}
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
    queryFn:()=>api.get(`/epics/comments?entity_type=${entityType}&entity_id=${entityId}`).then(r=>r.data).catch(()=>[]),
    enabled:!!entityId,
  })

  const { mutate:addComment, isPending:adding } = useMutation({
    mutationFn: d=>api.post(`/epics/comments?entity_type=${entityType}&entity_id=${entityId}`,d).then(r=>r.data),
    onSuccess: ()=>{ qc.invalidateQueries(['comments',entityType,entityId]); setNewContent(''); setReplyTo(null); setReplyContent('') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate:resolveComment } = useMutation({
    mutationFn: id=>api.patch(`/epics/comments/${id}/resolve`),
    onSuccess: ()=>qc.invalidateQueries(['comments',entityType,entityId]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate:deleteComment } = useMutation({
    mutationFn: id=>api.delete(`/epics/comments/${id}`),
    onSuccess: ()=>qc.invalidateQueries(['comments',entityType,entityId]),
    onError: _e=>toast.info(t('mentions.cannot_delete_with_replies')),
  })

  const CommentNode = ({ comment, depth=0 }) => (
    <div style={{marginLeft:depth*20,marginBottom:8}}>
      <div style={{padding:'12px 14px',background:comment.is_resolved?'rgba(255,255,255,0.03)':'var(--surface-1)',borderRadius:8,border:`1px solid ${comment.is_resolved?'var(--surface-4)':'var(--surface-4)'}`,opacity:comment.is_resolved?0.6:1}}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:6}}>
          <div style={{display:'flex',gap:8,alignItems:'center'}}>
            <span style={{fontSize:12,fontWeight:600,color:'var(--accent)'}}>{comment.created_by?.slice(0,8)||'Usuario'}</span>
            {comment.is_resolved&&<span style={{fontSize:10,padding:'1px 6px',borderRadius:4,background:'var(--success-bg)',color:'var(--success)'}}>{t('mentions.resolved')}</span>}
          </div>
          <div style={{display:'flex',gap:6}}>
            {!comment.is_resolved&&<button onClick={()=>setReplyTo(comment.id)} style={{background:'none',border:'none',color:'var(--text-2)',cursor:'pointer',fontSize:11}}>{t('mentions.reply')}</button>}
            {!comment.is_resolved&&<button onClick={()=>resolveComment(comment.id)} style={{background:'none',border:'none',color:'var(--success)',cursor:'pointer',fontSize:11}}>✓ {t('mentions.resolve')}</button>}
            <button onClick={()=>{ openConfirmGlobal({ message: t('mentions.confirm_delete'), onConfirm: () => deleteComment(comment.id), danger: true }) }} style={{background:'none',border:'none',color:'var(--danger)',cursor:'pointer',fontSize:11}}>✕</button>
          </div>
        </div>
        <div style={{fontSize:13,color:'var(--text-1)',lineHeight:1.5}}>{comment.content}</div>
        {replyTo===comment.id&&(
          <div style={{marginTop:10}}>
            <textarea value={replyContent} onChange={e=>setReplyContent(e.target.value)}
              placeholder={t('mentions.reply_placeholder')}
              rows={2} style={{...is,marginBottom:8,resize:'vertical'}}/>
            <div style={{display:'flex',gap:6}}>
              <Button onClick={()=>addComment({content:replyContent,parent_id:comment.id})} disabled={adding||!replyContent.trim()}>
                {adding?t('mentions.sending') : t('mentions.reply_btn')}
              </Button>
              <Button variant="secondary" onClick={()=>{setReplyTo(null);setReplyContent('')}}>{t('mentions.cancel')}</Button>
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
      <div style={{fontSize:13,fontWeight:600,marginBottom:12}}>💬 {t('mentions.comments_title', { title })}</div>
      {isLoading?<Spinner/>:(
        comments.length===0
          ?<div style={{fontSize:12,color:'var(--text-3)',marginBottom:12}}>{t('mentions.no_comments')}</div>
          :comments.map(c=><CommentNode key={c.id} comment={c}/>)
      )}
      <div style={{marginTop:12}}>
        <textarea value={newContent} onChange={e=>setNewContent(e.target.value)}
          placeholder={t('mentions.comment_placeholder')}
          rows={2} style={{...is,marginBottom:8,resize:'vertical'}}/>
        <Button onClick={()=>addComment({content:newContent,parent_id:null})} disabled={adding||!newContent.trim()}>
          {adding?t('mentions.sending'):t('mentions.add_comment_btn')}
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
    queryFn:()=>api.get(`/epics/mentions?only_unread=${onlyUnread}`).then(r=>r.data).catch(()=>[]),
  })

  const { mutate:markRead } = useMutation({
    mutationFn: id=>api.post(`/activity/mentions/${id}/read`),
    onSuccess: ()=>qc.invalidateQueries(['mentions']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate:markAll } = useMutation({
    mutationFn: ()=>api.post('/epics/mentions/read-all'),
    onSuccess: ()=>qc.invalidateQueries(['mentions']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const unreadCount = mentions.filter(m=>!m.is_read).length

  return (
    <div style={{padding:32}}>
      <PageHeader icon={<AtSign size={18} />} title={t('mentions.title')} subtitle={t('mentions.subtitle')}/>

      {/* Tabs */}
      <div style={{display:'flex',gap:6,marginBottom:20}}>
        {[
          ['mentions', t('mentions.tab_mentions')],
          ['comments', t('mentions.tab_comments')],
        ].map(([tabKey, label])=>(
          <button key={tabKey} onClick={()=>setTab(tabKey)}
            style={{padding:'7px 16px',borderRadius:8,border:'1px solid var(--surface-4)',background:tab===tabKey?'var(--accent-muted)':'transparent',color:tab===tabKey?'var(--accent)':'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize:13}}>
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
                {t('mentions.only_unread')}
              </label>
              {unreadCount>0&&<span style={{fontSize:12,padding:'2px 8px',borderRadius:20,background:'var(--accent-glow)',color:'var(--accent)',fontWeight:600}}>{unreadCount} {t('mentions.new_plural')}</span>}
            </div>
            {unreadCount>0&&(
              <Button variant="secondary" onClick={()=>markAll()}>✓ {t('mentions.mark_all_read')}</Button>
            )}
          </div>

          {isLoading?<Spinner/>:mentions.length===0
            ?<EmptyState icon="🔔" title={onlyUnread?t('mentions.no_new_mentions'):t('mentions.no_mentions')} description={onlyUnread?t('mentions.no_unread_mentions_desc'):t('mentions.no_mentions_desc')}/>
            :mentions.map(m=><MentionCard key={m.id} mention={m} onRead={id=>markRead(id)}/>)
          }
        </div>
      )}

      {/* TAB: Comentarios threaded */}
      {tab==='comments'&&(
        <div>
          <div style={{...ps,marginBottom:20}}>
            <div style={{fontSize:13,color:'var(--text-2)',marginBottom:14,lineHeight:1.6}}>
              {t('mentions.threaded_comments_info')}
            </div>
            <div style={{display:'grid',gridTemplateColumns:'auto 1fr',gap:12,alignItems:'flex-end'}}>
              <div>
                <label style={ls}>{t('mentions.type_label')}</label>
                <select value={demoType} onChange={e=>setDemoType(e.target.value)} style={{...is,width:130}}>
                  <option value="task">📌 {t('mentions.type_task')}</option>
                  <option value="ticket">🎫 {t('mentions.type_ticket')}</option>
                </select>
              </div>
              <div>
                <label style={ls}>{t('mentions.entity_id_label')}</label>
                <input value={demoEntity} onChange={e=>setDemoEntity(e.target.value)}
                  placeholder={t('mentions.entity_id_placeholder')} style={is}/>
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
              <div style={{fontSize:14,color:'var(--text-2)'}}>{t('mentions.enter_entity_id')}</div>
            </div>
          )}

          <div style={{...ps,marginTop:16,padding:'14px 18px'}}>
            <div style={{fontSize:12,fontWeight:600,color:'var(--text-3)',textTransform:'uppercase',letterSpacing:'.07em',marginBottom:8}}>{t('mentions.how_to_use_title')}</div>
            <div style={{fontSize:12,color:'var(--text-2)',lineHeight:1.8}}>
              {t('mentions.how_to_use_desc')}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
