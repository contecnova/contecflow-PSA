import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { mentionsApi } from '../services/api'
import type { ComentarioEnHilo, Mencion } from '../services/api/tipos-personas'
import { Button, Checkbox, Pulsable, Select, Spinner, EmptyState, Input, Textarea } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AtSign, Bell } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import './MentionsPage.css'
import { px } from '../utils/estilos'

type MentionItem = Mencion
type CommentItem = ComentarioEnHilo


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
    <div className={`ment-box mentions-sx1 ${mention.is_read ? 'mentions-sx2' : 'mentions-sx3'} mentions-page-e1`} style={{ '--mentions-page-border': `1px solid ${mention.is_read?'var(--surface-4)':'var(--accent-glow)'}` } as CSSProperties}>
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
          <Pulsable onClick={()=>onRead(mention.id)}
            className="ment-btn">
            {t('mentions.mark_read')}
          </Pulsable>
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
    queryFn:()=>mentionsApi.comments(entityType, entityId).then(r=>r.data),
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
    <div className="ment-box-3 mentions-page-e2" style={{ '--mentions-page-margin-left': px(depth*20) } as CSSProperties}>
      <div className={`ment-box-4 mentions-sx1 ${comment.is_resolved ? 'mentions-sx4' : 'mentions-sx5'} mentions-page-e1`} style={{ '--mentions-page-border': `1px solid ${comment.is_resolved?'var(--surface-4)':'var(--surface-4)'}` } as CSSProperties}>
        <div className="ment-row-3">
          <div className="u-row-center-8">
            <span className="ment-label">{comment.created_by_email || comment.created_by_name || t('pagina_ment.usuario')}</span>
            {comment.is_resolved&&<span className="ment-card-3">{t('mentions.resolved')}</span>}
          </div>
          <div className="u-row-6">
            {!comment.is_resolved&&<Pulsable onClick={()=>setReplyTo(comment.id)} className="ment-btn-2">{t('mentions.reply')}</Pulsable>}
            {!comment.is_resolved&&<Pulsable onClick={()=>resolveComment(comment.id)} className="ment-btn-3">✓ {t('mentions.resolve')}</Pulsable>}
            <Pulsable onClick={()=>{ openConfirmGlobal({ message: t('mentions.confirm_delete'), onConfirm: () => deleteComment(comment.id), danger: true }) }} className="ment-btn-4">✕</Pulsable>
          </div>
        </div>
        <div className="ment-box-5">{comment.content}</div>
        {replyTo===comment.id&&(
          <div className="ment-box-6">
            <Textarea aria-label={t('mentions.reply_placeholder')} value={replyContent} onChange={e=>setReplyContent(e.target.value)}
              placeholder={t('mentions.reply_placeholder')}
              rows={2} inputClassName="mentions-page-e3"/>
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
        <Textarea aria-label={t('mentions.comment_placeholder')} value={newContent} onChange={e=>setNewContent(e.target.value)}
          placeholder={t('mentions.comment_placeholder')}
          rows={2} inputClassName="mentions-page-e3"/>
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
    queryFn:()=>mentionsApi.mentions(onlyUnread).then(r=>r.data),
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
          <Pulsable key={tabKey} onClick={()=>setTab(tabKey)}
            className={`ment-btn-5 ${tab===tabKey ? 'mentions-sx6' : 'mentions-sx7'}`}>
            {label}
          </Pulsable>
        ))}
      </div>

      {/* TAB: Menciones */}
      {tab==='mentions'&&(
        <div data-export-table="mentions-list">
          <div className="u-row-between-mb16">
            <div className="u-row-center-8">
              <Checkbox className="ment-label-2" checked={!!onlyUnread} onChange={setOnlyUnread} label={t('mentions.only_unread')} />
              {unreadCount>0&&<span className="ment-card-4">{unreadCount} {t('mentions.new_plural')}</span>}
            </div>
            {unreadCount>0&&(
              <Button variant="secondary" onClick={()=>markAll()}>✓ {t('mentions.mark_all_read')}</Button>
            )}
          </div>

          {isLoading?<Spinner/>:mentions.length===0
            ?<EmptyState icon={<Bell size={28} strokeWidth={1.5} aria-hidden />} title={onlyUnread?t('mentions.no_new_mentions'):t('mentions.no_mentions')} description={onlyUnread?t('mentions.no_unread_mentions_desc'):t('mentions.no_mentions_desc')}/>
            :mentions.map((m) => <MentionCard key={m.id} mention={m} onRead={(id)=>markRead(id)}/>)
          }
        </div>
      )}

      {/* TAB: Comentarios threaded */}
      {tab==='comments'&&(
        <div>
          <div className="mentions-page-e4">
            <div className="ment-box-10">
              {t('mentions.threaded_comments_info')}
            </div>
            <div className="ment-grid">
              <Select label={t('mentions.type_label')} placeholder={false} id={`${idCampo}-1`} value={demoType} onChange={e=>setDemoType(e.target.value)}>
                  <option value="task">📌 {t('mentions.type_task')}</option>
                  <option value="ticket">🎫 {t('mentions.type_ticket')}</option>
                </Select>
              <Input label={t('mentions.entity_id_label')} id={`${idCampo}-2`} value={demoEntity} onChange={e=>setDemoEntity(e.target.value)} placeholder={t('mentions.entity_id_placeholder')} />
            </div>
          </div>

          {hasEntityInput && hasValidEntityId?(
            <div className="mentions-page-e11">
              <ThreadedCommentSection entityType={demoType} entityId={normalizedEntityId} title={`${demoType} #${normalizedEntityId.slice(0,8)}`}/>
            </div>
          ):hasEntityInput?(
            <div className="mentions-page-e6">
              <div className="u-text2-sm">
                {demoType === 'task'
                  ? t('mentions.invalid_entity_id_format_task')
                  : t('mentions.invalid_entity_id_format_ticket')}
              </div>
            </div>
          ):(
            <div className="mentions-page-e7">
              <div className="u-empty-icon">💬</div>
              <div className="ment-box-11">{t('mentions.enter_entity_id')}</div>
            </div>
          )}

          <div className="mentions-page-e8">
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
