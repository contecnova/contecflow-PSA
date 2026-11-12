/**
 * Collaboration API client — wraps /api/v1/collaboration endpoints.
 *
 * NOTE: many list endpoints were migrated to APIListResponse[T] in audit #67
 * (response shape: `{ items: [...], total }`). Older endpoints still return
 * a bare array. All list* methods go through `unwrapList` so callers always
 * receive a plain array regardless of backend shape.
 */
import api, { unwrapList, type PathId, type QueryParams } from './api'

const root = '/collaboration'

export const collabApi = {
  // Workspace
  getWorkspace:    () => api.get(`${root}/workspace`).then(r => r.data),

  // Teams
  listTeams:       () => api.get(`${root}/teams`).then(unwrapList),

  // Channels
  listChannels:    (team_id: PathId) => api.get(`${root}/channels`, { params: { team_id } }).then(unwrapList),
  createChannel:   (d: Record<string, unknown>) => api.post(`${root}/channels`, d).then(r => r.data),
  listChannelMembers: (id: PathId) => api.get(`${root}/channels/${id}/members`).then(unwrapList),

  // Conversations
  listConversations: () => api.get(`${root}/conversations`).then(unwrapList),
  openDirect:        (d: Record<string, unknown>) => api.post(`${root}/direct/open`, d).then(r => r.data),
  createGroup:       (d: Record<string, unknown>) => api.post(`${root}/groups`, d).then(r => r.data),
  listConversationMembers:   (cid: PathId) => api.get(`${root}/conversations/${cid}/members`).then(unwrapList),
  addConversationMembers:    (cid: PathId, body: Record<string, unknown>) => api.post(`${root}/conversations/${cid}/members`, body).then(r => r.data),
  removeConversationMember:  (cid: PathId, uid: PathId) => api.delete(`${root}/conversations/${cid}/members/${uid}`).then(r => r.data),

  // Messages
  listMessages: (cid: PathId, params?: QueryParams) => api.get(`${root}/conversations/${cid}/messages`, { params }).then(unwrapList),
  sendMessage:  (d: Record<string, unknown>) => api.post(`${root}/messages`, d).then(r => r.data),
  editMessage:  (id: PathId, d: Record<string, unknown>) => api.patch(`${root}/messages/${id}`, d).then(r => r.data),
  deleteMessage:(id: PathId) => api.delete(`${root}/messages/${id}`).then(r => r.data),
  toggleReaction: (id: PathId, emoji: string) => api.post(`${root}/messages/${id}/reactions`, { emoji }).then(r => r.data),
  markRead:    (cid: PathId, last_message_id: PathId) => api.post(`${root}/conversations/${cid}/read`, { last_message_id }).then(r => r.data),

  // Pins / saved
  pinMessage:   (cid: PathId, message_id: PathId) => api.post(`${root}/conversations/${cid}/pins`, { message_id }).then(r => r.data),
  listPins:     (cid: PathId) => api.get(`${root}/conversations/${cid}/pins`).then(unwrapList),
  saveMessage:  (message_id: PathId, note?: string) => api.post(`${root}/saved`, { message_id, note }).then(r => r.data),
  listSaved:    () => api.get(`${root}/saved`).then(unwrapList),
  listMyMentions: () => api.get(`${root}/mentions`).then(unwrapList),

  // Presence
  listPresence: () => api.get(`${root}/presence`).then(unwrapList),
  setPresence:  (d: Record<string, unknown>) => api.post(`${root}/presence/me`, d).then(r => r.data),

  // Notifications
  listNotifications: (unread_only=false) => api.get(`${root}/notifications`, { params: { unread_only } }).then(unwrapList),
  markAllRead:       () => api.post(`${root}/notifications/mark-all-read`).then(r => r.data),
  listRules:    () => api.get(`${root}/notification-rules`).then(unwrapList),
  upsertRule:   (d: Record<string, unknown>) => api.put(`${root}/notification-rules`, d).then(r => r.data),

  // Search
  search: (params?: QueryParams) => api.get(`${root}/search`, { params }).then(r => r.data),
  mentionSuggestions: (params?: QueryParams) => api.get(`${root}/mention-suggestions`, { params }).then(r => r.data),
  linkMessage: (id: PathId, body: Record<string, unknown>) => api.post(`${root}/messages/${id}/link`, body).then(r => r.data),
  linkCandidates: (id: PathId, params?: QueryParams) => api.get(`${root}/messages/${id}/link/candidates`, { params }).then(r => r.data),

  // Attachments
  uploadAttachment: (form: FormData) => api.post(`${root}/attachments`, form).then(r => r.data),
  getAttachment:    (id: PathId) => api.get(`${root}/attachments/${id}`).then(r => r.data),

  // Calls
  startCall: (d: Record<string, unknown>) => api.post(`${root}/calls/start`, d).then(r => r.data),
  leaveCall: (id: PathId) => api.post(`${root}/calls/${id}/leave`).then(r => r.data),
  endCall:   (id: PathId) => api.post(`${root}/calls/${id}/end`).then(r => r.data),
  startRecording: (id: PathId) => api.post(`${root}/calls/${id}/recording/start`).then(r => r.data),
  listCalls: (cid: PathId) => api.get(`${root}/conversations/${cid}/calls`).then(unwrapList),
  /** Subtítulos: un trozo de audio (multipart) → `{ text }`. */
  transcribeChunk: (id: PathId, fd: FormData) => api.post(`${root}/calls/${id}/transcribe-chunk`, fd).then(r => r.data),

  // Bots / slash
  listBots:    () => api.get(`${root}/bots`).then(unwrapList),
  slashHelp:   () => api.get(`${root}/slash/help`).then(r => r.data),

  // Integrations / webhooks
  listIntegrations: () => api.get(`${root}/integrations`).then(unwrapList),
  createIntegration: (d: Record<string, unknown>) => api.post(`${root}/integrations`, d).then(r => r.data),
  deleteIntegration: (id: PathId) => api.delete(`${root}/integrations/${id}`).then(r => r.data),
  listWebhooks:     () => api.get(`${root}/webhooks`).then(unwrapList),
  createWebhook:    (d: Record<string, unknown>) => api.post(`${root}/webhooks`, d).then(r => r.data),

  // Calendar
  calendarEvents: (days = 7) => api.get(`${root}/calendar/events`, { params: { days } }).then(unwrapList),

  // Decisions
  listDecisions: (limit = 100) => api.get(`${root}/decisions`, { params: { limit } }).then(unwrapList),

  // Compliance
  listRetention:     () => api.get(`${root}/retention`).then(unwrapList),
  createRetention:   (d: Record<string, unknown>) => api.post(`${root}/retention`, d).then(r => r.data),
  runRetention:      () => api.post(`${root}/retention/run`).then(r => r.data),
  listLegalHolds:    () => api.get(`${root}/legal-holds`).then(unwrapList),
  createLegalHold:   (d: Record<string, unknown>) => api.post(`${root}/legal-holds`, d).then(r => r.data),
  releaseLegalHold:  (id: PathId) => api.post(`${root}/legal-holds/${id}/release`).then(r => r.data),
  ediscoveryExport:  (d: Record<string, unknown>) => api.post(`${root}/ediscovery/export`, d).then(r => r.data),
  listAudit:         (limit=200) => api.get(`${root}/audit`, { params: { limit } }).then(unwrapList),
  verifyAudit:       () => api.get(`${root}/audit/verify`).then(r => r.data),

  // Web Push
  pushPublicKey: () => api.get(`${root}/push/public-key`).then(r => r.data as { configured?: boolean; public_key?: string }),
  pushSubscribe: (d: Record<string, unknown>) => api.post(`${root}/push/subscribe`, d).then(r => r.data),
}
