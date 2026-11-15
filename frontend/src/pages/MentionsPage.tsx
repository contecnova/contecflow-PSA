import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { mentionsApi } from '../services/api'
import type { ComentarioEnHilo, Mencion } from '../services/api/tipos-personas'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AtSign } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import './MentionsPage.css'

type MentionItem = Mencion
type CommentItem = ComentarioEnHilo

const ps: CSSProperties = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is: CSSProperties = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const ENTITY_ICONS: Record<string, string> = { task:'📌', ticket:'🎫', wiki_comment:'💬', wiki_page:'📄', comment:'💬' }
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const TASK_CODE_RE = /^TSK-\d{4,}$/i
const TICKET_NUMBER_RE = /^(INC|REQ|QST|PRB|CHG)-\d{4,}$/i

function MentionCard({ mention, onRead }: { mention: MentionItem; onRead: (id: string | number) => void }) {
  const t = useAppT()
  const icon = ENTITY_ICONS[mention.entity_type] || '🔔'
  const timeAgo = (iso: string) => {
    const diff = Date.now() - new Date(iso).getTime()
    const m = Math.floor(diff/60000), h = Math.floor(diff/3600000), d = Math.floor(diff/86400000)
    if(d>0) return t('mentions.time_days', { count: d })
    if(h>0) return t('mentions.time_hours', { count: h })
    return t('mentions.time_minutes', { count: m })
  }
  return (
    <div className={`ment-box mentions-sx1 ${mention.is_read ? 'mentions-sx2' : 'mentions-sx3'}`} style={{ border:`1px solid ${mention.is_read?'var(--surface-4)':'var(--accent-glow)'}` }}>
      <div className="ment-row">
        <div className="ment-box-2">{icon}</div>
        <div className="u-flex1">
          <div className="ment-row-2">
            <span className="ment-label">{mention.entity_type.replace(/_/g,' ')}</span>
            <span className="u-text3-xs">{mention.created_at?timeAgo(mention.created_at):''}</span>
            {!mention.is_read&&<span className="ment-card">{t('mentions.new')}</span>}
          </div>
          {mention.context_text&&(
            <div className="ment-card-2">
              &quot;...{mention.context_text.slice(0,200)}{mention.context_text.length>200?'...':''}&quot;
            </div>
          )}
          <div className="u-text3-mono-xs">
            {mention.entity_type} #{mention.entity_id?.slice(0,8)}
          </div>
        </div>
        {!mention.is_read&&(
          <button onClick={()=>onRead(mention.id)}
            className="ment-btn">
            {t('mentions.mark_read')}
          </button>
        )}
      </div>
    </div>
  )
}

function ThreadedCommentSection({ entityType, entityId, title }: { entityType: string; entityId: string; title: string }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [newContent, setNewContent] = useState('')
  const [replyTo,    setReplyTo]    = useState<string | number | null>(null)
  const [replyContent,setReplyContent]=useState('')

  const { data:comments=[], isLoading } = useQuery({
    queryKey:['comments',entityType,entityId],
    queryFn:()=>mentionsApi.comments(entityType, entityId).then(r=>r.data).catch(():CommentItem[]=>[]),
    enabled:!!entityId,
  })

  const { mutate:addComment, isPending:adding } = useMutation({
    mutationFn: (d: { content: string; parent_id: string | number | null }) => mentionsApi.createComment(entityType, entityId, d).then(r=>r.data),
    onSuccess: ()=>{ qc.invalidateQueries({ queryKey: ['comments',entityType,entityId] }); setNewContent(''); setReplyTo(null); setReplyContent('') },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate:resolveComment } = useMutation({
    mutationFn: (id: string | number)=>mentionsApi.resolveComment(id),
    onSuccess: ()=>qc.invalidateQueries({ queryKey: ['comments',entityType,entityId] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate:deleteComment } = useMutation({
    mutationFn: (id: string | number)=>mentionsApi.deleteComment(id),
    onSuccess: ()=>qc.invalidateQueries({ queryKey: ['comments',entityType,entityId] }),
    onError: _e=>toast.info(t('mentions.cannot_delete_with_replies')),
  })

  const CommentNode = ({ comment, depth=0 }: { comment: CommentItem; depth?: number }) => (
    <div className="ment-box-3" style={{ marginLeft:depth*20 }}>
      <div className={`ment-box-4 mentions-sx1 ${comment.is_resolved ? 'mentions-sx4' : 'mentions-sx5'}`} style={{ border:`1px solid ${comment.is_resolved?'var(--surface-4)':'var(--surface-4)'}` }}>
        <div className="ment-row-3">
          <div className="u-row-center-8">
            <span className="ment-label">{comment.created_by_email || comment.created_by_name || t('pagina_ment.usuario')}</span>
            {comment.is_resolved&&<span className="ment-card-3">{t('mentions.resolved')}</span>}
          </div>
          <div className="u-row-6">
            {!comment.is_resolved&&<button onClick={()=>setReplyTo(comment.id)} className="ment-btn-2">{t('mentions.reply')}</button>}
            {!comment.is_resolved&&<button onClick={()=>resolveComment(comment.id)} className="ment-btn-3">✓ {t('mentions.resolve')}</button>}
            <button onClick={()=>{ openConfirmGlobal({ message: t('mentions.confirm_delete'), onConfirm: () => deleteComment(comment.id), danger: true }) }} className="ment-btn-4">✕</button>
          </div>
        </div>
        <div className="ment-box-5">{comment.content}</div>
        {replyTo===comment.id&&(
          <div className="ment-box-6">
            <textarea aria-label={t('mentions.reply_placeholder')} value={replyContent} onChange={e=>setReplyContent(e.target.value)}
              placeholder={t('mentions.reply_placeholder')}
              rows={2} style={{...is,marginBottom:8,resize:'vertical'}}/>
            <div className="u-row-6">
              <Button onClick={()=>addComment({content:replyContent,parent_id:comment.id})} disabled={adding||!replyContent.trim()}>
                {adding?t('mentions.sending') : t('mentions.reply_btn')}
              </Button>
              <Button variant="secondary" onClick={()=>{setReplyTo(null);setReplyContent('')}}>{t('mentions.cancel')}</Button>
            </div>
          </div>
        )}
      </div>
      {(comment.replies||[]).map((r) => <CommentNode key={r.id} comment={r} depth={depth+1}/>)}
    </div>
  )

  if(!entityId) return null

  return (
    <div data-export-table="mention-comments-list">
      <div className="ment-box-7">💬 {t('mentions.comments_title', { title })}</div>
      {isLoading?<Spinner/>:(
        comments.length===0
          ?<div className="ment-box-8">{t('mentions.no_comments')}</div>
            :comments.map((c) => <CommentNode key={c.id} comment={c}/>)
      )}
      <div className="ment-box-9">
        <textarea aria-label={t('mentions.comment_placeholder')} value={newContent} onChange={e=>setNewContent(e.target.value)}
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
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab,        setTab]        = useState<'mentions' | 'comments'>('mentions')
  const [onlyUnread, setOnlyUnread] = useState(true)
  const [demoEntity, setDemoEntity] = useState('')
  const [demoType,   setDemoType]   = useState('task')

  const { data:mentions=[], isLoading } = useQuery({
    queryKey:['mentions',onlyUnread],
    queryFn:()=>mentionsApi.mentions(onlyUnread).then(r=>r.data).catch(():MentionItem[]=>[]),
  })

  const { mutate:markRead } = useMutation({
    mutationFn: (id: string | number)=>mentionsApi.markMentionRead(id),
    onSuccess: ()=>qc.invalidateQueries({ queryKey: ['mentions'] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate:markAll } = useMutation({
    mutationFn: ()=>mentionsApi.markAllMentionsRead(),
    onSuccess: ()=>qc.invalidateQueries({ queryKey: ['mentions'] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const normalizedEntityId = demoEntity.trim()
  const hasEntityInput = normalizedEntityId.length > 0
  const hasValidEntityId =
    demoType === 'task'
      ? (UUID_RE.test(normalizedEntityId) || TASK_CODE_RE.test(normalizedEntityId))
      : (UUID_RE.test(normalizedEntityId) || TICKET_NUMBER_RE.test(normalizedEntityId))
  const unreadCount = mentions.filter((m) => !m.is_read).length

  return (
    <PageShell>
      <PageHeader
        icon={<AtSign size={18} />}
        title={t('mentions.title')}
        subtitle={t('mentions.subtitle')}
        showListExport={tab === 'mentions' ? mentions.length > 0 : Boolean(normalizedEntityId && hasValidEntityId)}
        exportTargetSelector={tab === 'mentions' ? '[data-export-table="mentions-list"]' : '[data-export-table="mention-comments-list"]'}
        exportFilePrefix={tab === 'mentions' ? 'mentions' : 'thread_comments'}
      />

      {/* Tabs */}
      <div className="ment-row-4">
        {([
          ['mentions', t('mentions.tab_mentions')],
          ['comments', t('mentions.tab_comments')],
        ] as const).map(([tabKey, label])=>(
          <button key={tabKey} onClick={()=>setTab(tabKey)}
            className={`ment-btn-5 ${tab===tabKey ? 'mentions-sx6' : 'mentions-sx7'}`}>
            {label}
          </button>
        ))}
      </div>

      {/* TAB: Menciones */}
      {tab==='mentions'&&(
        <div data-export-table="mentions-list">
          <div className="u-row-between-mb16">
            <div className="u-row-center-8">
              <label className="ment-label-2">
                <input type="checkbox" aria-label={t('mentions.only_unread')} checked={onlyUnread} onChange={e=>setOnlyUnread(e.target.checked)}/>
                {t('mentions.only_unread')}
              </label>
              {unreadCount>0&&<span className="ment-card-4">{unreadCount} {t('mentions.new_plural')}</span>}
            </div>
            {unreadCount>0&&(
              <Button variant="secondary" onClick={()=>markAll()}>✓ {t('mentions.mark_all_read')}</Button>
            )}
          </div>

          {isLoading?<Spinner/>:mentions.length===0
            ?<EmptyState icon="🔔" title={onlyUnread?t('mentions.no_new_mentions'):t('mentions.no_mentions')} description={onlyUnread?t('mentions.no_unread_mentions_desc'):t('mentions.no_mentions_desc')}/>
            :mentions.map((m) => <MentionCard key={m.id} mention={m} onRead={(id)=>markRead(id)}/>)
          }
        </div>
      )}

      {/* TAB: Comentarios threaded */}
      {tab==='comments'&&(
        <div>
          <div style={{...ps,marginBottom:20}}>
            <div className="ment-box-10">
              {t('mentions.threaded_comments_info')}
            </div>
            <div className="ment-grid">
              <div>
                <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('mentions.type_label')}</label>
                <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={demoType} onChange={e=>setDemoType(e.target.value)} style={{...is,width:130}}>
                  <option value="task">📌 {t('mentions.type_task')}</option>
                  <option value="ticket">🎫 {t('mentions.type_ticket')}</option>
                </select>
              </div>
              <div>
                <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('mentions.entity_id_label')}</label>
                <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={demoEntity} onChange={e=>setDemoEntity(e.target.value)}
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
              <div className="u-text2-sm">
                {demoType === 'task'
                  ? t('mentions.invalid_entity_id_format_task', 'Introduce un UUID o codigo de tarea valido (ej: TSK-0011).')
                  : t('mentions.invalid_entity_id_format_ticket', 'Introduce un UUID o numero de ticket valido (ej: INC-0001).')}
              </div>
            </div>
          ):(
            <div style={{...ps,textAlign:'center',padding:'40px 24px'}}>
              <div className="u-empty-icon">💬</div>
              <div className="ment-box-11">{t('mentions.enter_entity_id')}</div>
            </div>
          )}

          <div style={{...ps,marginTop:16,padding:'14px 18px'}}>
            <div className="ment-box-12">{t('mentions.how_to_use_title')}</div>
            <div className="ment-box-13">
              {t('mentions.how_to_use_desc')}
            </div>
          </div>
        </div>
      )}
    </PageShell>
  )
}
