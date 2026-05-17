// @ts-nocheck
import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { mentionsApi } from '../services/api'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AtSign } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const ENTITY_ICONS = { task:'📌', ticket:'🎫', wiki_comment:'💬', wiki_page:'📄', comment:'💬' }
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const TASK_CODE_RE = /^TSK-\d{4,}$/i
const TICKET_NUMBER_RE = /^(INC|REQ|QST|PRB|CHG)-\d{4,}$/i

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
        <div style={{fontSize: "var(--text-xl)",flexShrink:0,marginTop:2}}>{icon}</div>
        <div style={{flex:1}}>
          <div style={{display:'flex',gap:8,alignItems:'center',marginBottom:6}}>
            <span style={{fontSize: "var(--text-sm)",fontWeight:600,color:'var(--accent)'}}>{mention.entity_type.replace(/_/g,' ')}</span>
            <span style={{fontSize: "var(--text-xs)",color:'var(--text-3)'}}>{mention.created_at?timeAgo(mention.created_at):''}</span>
            {!mention.is_read&&<span style={{fontSize: "var(--text-2xs)",padding:'1px 6px',borderRadius:4,background:'var(--accent-glow)',color:'var(--accent)',fontWeight:600}}>{t('mentions.new')}</span>}
          </div>
          {mention.context_text&&(
            <div style={{fontSize: "var(--text-base)",color:'var(--text-2)',lineHeight:1.5,marginBottom:8,background:'var(--surface-1)',padding:'8px 12px',borderRadius:6,borderLeft:'2px solid var(--surface-4)'}}>
              &quot;...{mention.context_text.slice(0,200)}{mention.context_text.length>200?'...':''}&quot;
            </div>
          )}
          <div style={{fontSize: "var(--text-xs)",color:'var(--text-3)',fontFamily:'var(--font-mono)'}}>
            {mention.entity_type} #{mention.entity_id?.slice(0,8)}
          </div>
        </div>
        {!mention.is_read&&(
          <button onClick={()=>onRead(mention.id)}
            style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'4px 10px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-xs)",flexShrink:0}}>
            {t('mentions.mark_read')}
          </button>
        )}
      </div>
    </div>
  )
}

function ThreadedCommentSection({ entityType, entityId, title }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [newContent, setNewContent] = useState('')
  const [replyTo,    setReplyTo]    = useState(null)
  const [replyContent,setReplyContent]=useState('')

  const { data:comments=[], isLoading } = useQuery({
    queryKey:['comments',entityType,entityId],
    queryFn:()=>mentionsApi.comments(entityType, entityId).then(r=>r.data).catch(()=>[]),
    enabled:!!entityId,
  })

  const { mutate:addComment, isPending:adding } = useMutation({
    mutationFn: d=>mentionsApi.createComment(entityType, entityId, d).then(r=>r.data),
    onSuccess: ()=>{ qc.invalidateQueries(['comments',entityType,entityId]); setNewContent(''); setReplyTo(null); setReplyContent('') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate:resolveComment } = useMutation({
    mutationFn: id=>mentionsApi.resolveComment(id),
    onSuccess: ()=>qc.invalidateQueries(['comments',entityType,entityId]),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate:deleteComment } = useMutation({
    mutationFn: id=>mentionsApi.deleteComment(id),
    onSuccess: ()=>qc.invalidateQueries(['comments',entityType,entityId]),
    onError: _e=>toast.info(t('mentions.cannot_delete_with_replies')),
  })

  const CommentNode = ({ comment, depth=0 }) => (
    <div style={{marginLeft:depth*20,marginBottom:8}}>
      <div style={{padding:'12px 14px',background:comment.is_resolved?'rgba(255,255,255,0.03)':'var(--surface-1)',borderRadius:8,border:`1px solid ${comment.is_resolved?'var(--surface-4)':'var(--surface-4)'}`,opacity:comment.is_resolved?0.6:1}}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:6}}>
          <div style={{display:'flex',gap:8,alignItems:'center'}}>
            <span style={{fontSize: "var(--text-sm)",fontWeight:600,color:'var(--accent)'}}>{comment.created_by_email || comment.created_by_name || 'Usuario'}</span>
            {comment.is_resolved&&<span style={{fontSize: "var(--text-2xs)",padding:'1px 6px',borderRadius:4,background:'var(--success-bg)',color:'var(--success)'}}>{t('mentions.resolved')}</span>}
          </div>
          <div style={{display:'flex',gap:6}}>
            {!comment.is_resolved&&<button onClick={()=>setReplyTo(comment.id)} style={{background:'none',border:'none',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-xs)"}}>{t('mentions.reply')}</button>}
            {!comment.is_resolved&&<button onClick={()=>resolveComment(comment.id)} style={{background:'none',border:'none',color:'var(--success)',cursor:'pointer',fontSize: "var(--text-xs)"}}>✓ {t('mentions.resolve')}</button>}
            <button onClick={()=>{ openConfirmGlobal({ message: t('mentions.confirm_delete'), onConfirm: () => deleteComment(comment.id), danger: true }) }} style={{background:'none',border:'none',color:'var(--danger)',cursor:'pointer',fontSize: "var(--text-xs)"}}>✕</button>
          </div>
        </div>
        <div style={{fontSize: "var(--text-base)",color:'var(--text-1)',lineHeight:1.5}}>{comment.content}</div>
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
    <div data-export-table="mention-comments-list">
      <div style={{fontSize: "var(--text-base)",fontWeight:600,marginBottom:12}}>💬 {t('mentions.comments_title', { title })}</div>
      {isLoading?<Spinner/>:(
        comments.length===0
          ?<div style={{fontSize: "var(--text-sm)",color:'var(--text-3)',marginBottom:12}}>{t('mentions.no_comments')}</div>
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
    queryFn:()=>mentionsApi.mentions(onlyUnread).then(r=>r.data).catch(()=>[]),
  })

  const { mutate:markRead } = useMutation({
    mutationFn: id=>mentionsApi.markMentionRead(id),
    onSuccess: ()=>qc.invalidateQueries(['mentions']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate:markAll } = useMutation({
    mutationFn: ()=>mentionsApi.markAllMentionsRead(),
    onSuccess: ()=>qc.invalidateQueries(['mentions']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const normalizedEntityId = demoEntity.trim()
  const hasEntityInput = normalizedEntityId.length > 0
  const hasValidEntityId =
    demoType === 'task'
      ? (UUID_RE.test(normalizedEntityId) || TASK_CODE_RE.test(normalizedEntityId))
      : (UUID_RE.test(normalizedEntityId) || TICKET_NUMBER_RE.test(normalizedEntityId))
  const unreadCount = mentions.filter(m=>!m.is_read).length

  return (
    <PageShell>
      <PageHeader
        icon={<AtSign size={18} />}
        title={t('mentions.title')}
        subtitle={t('mentions.subtitle')}
        showListExport={tab === 'mentions' ? mentions.length > 0 : Boolean(normalizedEntityId && comments.length > 0)}
        exportTargetSelector={tab === 'mentions' ? '[data-export-table="mentions-list"]' : '[data-export-table="mention-comments-list"]'}
        exportFilePrefix={tab === 'mentions' ? 'mentions' : 'thread_comments'}
      />

      {/* Tabs */}
      <div style={{display:'flex',gap:6,marginBottom:20}}>
        {[
          ['mentions', t('mentions.tab_mentions')],
          ['comments', t('mentions.tab_comments')],
        ].map(([tabKey, label])=>(
          <button key={tabKey} onClick={()=>setTab(tabKey)}
            style={{padding:'7px 16px',borderRadius:8,border:'1px solid var(--surface-4)',background:tab===tabKey?'var(--accent-muted)':'transparent',color:tab===tabKey?'var(--accent)':'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize: "var(--text-base)"}}>
            {label}
          </button>
        ))}
      </div>

      {/* TAB: Menciones */}
      {tab==='mentions'&&(
        <div data-export-table="mentions-list">
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:16}}>
            <div style={{display:'flex',gap:8,alignItems:'center'}}>
              <label style={{display:'flex',alignItems:'center',gap:6,cursor:'pointer',fontSize: "var(--text-base)"}}>
                <input type="checkbox" checked={onlyUnread} onChange={e=>setOnlyUnread(e.target.checked)}/>
                {t('mentions.only_unread')}
              </label>
              {unreadCount>0&&<span style={{fontSize: "var(--text-sm)",padding:'2px 8px',borderRadius:20,background:'var(--accent-glow)',color:'var(--accent)',fontWeight:600}}>{unreadCount} {t('mentions.new_plural')}</span>}
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
            <div style={{fontSize: "var(--text-base)",color:'var(--text-2)',marginBottom:14,lineHeight:1.6}}>
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

          {hasEntityInput && hasValidEntityId?(
            <div style={ps}>
              <ThreadedCommentSection entityType={demoType} entityId={normalizedEntityId} title={`${demoType} #${normalizedEntityId.slice(0,8)}`}/>
            </div>
          ):hasEntityInput?(
            <div style={{...ps,textAlign:'center',padding:'28px 24px'}}>
              <div style={{fontSize: "var(--text-sm)",color:'var(--text-2)'}}>
                {demoType === 'task'
                  ? t('mentions.invalid_entity_id_format_task', 'Introduce un UUID o codigo de tarea valido (ej: TSK-0011).')
                  : t('mentions.invalid_entity_id_format_ticket', 'Introduce un UUID o numero de ticket valido (ej: INC-0001).')}
              </div>
            </div>
          ):(
            <div style={{...ps,textAlign:'center',padding:'40px 24px'}}>
              <div style={{fontSize: "var(--text-6xl)",marginBottom:16}}>💬</div>
              <div style={{fontSize: "var(--text-md)",color:'var(--text-2)'}}>{t('mentions.enter_entity_id')}</div>
            </div>
          )}

          <div style={{...ps,marginTop:16,padding:'14px 18px'}}>
            <div style={{fontSize: "var(--text-sm)",fontWeight:600,color:'var(--text-3)',textTransform:'uppercase',letterSpacing:'.07em',marginBottom:8}}>{t('mentions.how_to_use_title')}</div>
            <div style={{fontSize: "var(--text-sm)",color:'var(--text-2)',lineHeight:1.8}}>
              {t('mentions.how_to_use_desc')}
            </div>
          </div>
        </div>
      )}
    </PageShell>
  )
}
