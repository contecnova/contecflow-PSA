/**
 * Collaboration API client — wraps /api/v1/collaboration endpoints.
 *
 * NOTE: many list endpoints were migrated to APIListResponse[T] in audit #67
 * (response shape: `{ items: [...], total }`). Older endpoints still return
 * a bare array. All list* methods go through `unwrapList` so callers always
 * receive a plain array regardless of backend shape.
 */
import api, { unwrapList } from './api'

const root = '/collaboration'

export const collabApi = {
  // Workspace
  getWorkspace:    () => api.get(`${root}/workspace`).then(r => r.data),
  updateWorkspace: (d: Record<string, unknown>) => api.patch(`${root}/workspace`, d).then(r => r.data),

  // Teams
  listTeams:       () => api.get(`${root}/teams`).then(unwrapList),
  createTeam:      (d: Record<string, unknown>) => api.post(`${root}/teams`, d).then(r => r.data),
  updateTeam:      (id: any, d: Record<string, unknown>) => api.patch(`${root}/teams/${id}`, d).then(r => r.data),
  listTeamMembers: (id: any) => api.get(`${root}/teams/${id}/members`).then(unwrapList),
  addTeamMembers:  (id: any, body: Record<string, unknown>) => api.post(`${root}/teams/${id}/members`, body).then(r => r.data),
  removeTeamMember: (id: any, uid: any) => api.delete(`${root}/teams/${id}/members/${uid}`).then(r => r.data),

  // Channels
  listChannels:    (team_id: any) => api.get(`${root}/channels`, { params: { team_id } }).then(unwrapList),
  createChannel:   (d: Record<string, unknown>) => api.post(`${root}/channels`, d).then(r => r.data),
  updateChannel:   (id: any, d: Record<string, unknown>) => api.patch(`${root}/channels/${id}`, d).then(r => r.data),
  addChannelMembers: (id: any, body: Record<string, unknown>) => api.post(`${root}/channels/${id}/members`, body).then(r => r.data),
  listChannelMembers: (id: any) => api.get(`${root}/channels/${id}/members`).then(unwrapList),

  // Conversations
  listConversations: () => api.get(`${root}/conversations`).then(unwrapList),
  getConversation:   (id: any) => api.get(`${root}/conversations/${id}`).then(r => r.data),
  openDirect:        (d: Record<string, unknown>) => api.post(`${root}/direct/open`, d).then(r => r.data),
  createGroup:       (d: Record<string, unknown>) => api.post(`${root}/groups`, d).then(r => r.data),
  listConversationMembers:   (cid: any) => api.get(`${root}/conversations/${cid}/members`).then(unwrapList),
  addConversationMembers:    (cid: any, body: Record<string, unknown>) => api.post(`${root}/conversations/${cid}/members`, body).then(r => r.data),
  removeConversationMember:  (cid: any, uid: any) => api.delete(`${root}/conversations/${cid}/members/${uid}`).then(r => r.data),

  // Messages
  listMessages: (cid: any, params?: any) => api.get(`${root}/conversations/${cid}/messages`, { params }).then(unwrapList),
  sendMessage:  (d: Record<string, unknown>) => api.post(`${root}/messages`, d).then(r => r.data),
  editMessage:  (id: any, d: Record<string, unknown>) => api.patch(`${root}/messages/${id}`, d).then(r => r.data),
  deleteMessage:(id: any) => api.delete(`${root}/messages/${id}`).then(r => r.data),
  getVersions:  (id: any) => api.get(`${root}/messages/${id}/versions`).then(r => r.data),
  toggleReaction: (id: any, emoji: any) => api.post(`${root}/messages/${id}/reactions`, { emoji }).then(r => r.data),
  markRead:    (cid: any, last_message_id: any) => api.post(`${root}/conversations/${cid}/read`, { last_message_id }).then(r => r.data),

  // Pins / saved
  pinMessage:   (cid: any, message_id: any) => api.post(`${root}/conversations/${cid}/pins`, { message_id }).then(r => r.data),
  unpinMessage: (cid: any, mid: any) => api.delete(`${root}/conversations/${cid}/pins/${mid}`).then(r => r.data),
  listPins:     (cid: any) => api.get(`${root}/conversations/${cid}/pins`).then(unwrapList),
  saveMessage:  (message_id: any, note?: any) => api.post(`${root}/saved`, { message_id, note }).then(r => r.data),
  unsaveMessage:(mid: any) => api.delete(`${root}/saved/${mid}`).then(r => r.data),
  listSaved:    () => api.get(`${root}/saved`).then(unwrapList),
  listMyMentions: () => api.get(`${root}/mentions`).then(unwrapList),

  // Drafts
  saveDraft:    (cid: any, body: any, parent_message_id?: any) => api.put(`${root}/conversations/${cid}/draft`, { body, parent_message_id }).then(r => r.data),
  getDraft:     (cid: any, parent_message_id?: any) => api.get(`${root}/conversations/${cid}/draft`, { params: { parent_message_id } }).then(r => r.data),

  // Presence
  listPresence: () => api.get(`${root}/presence`).then(unwrapList),
  setPresence:  (d: Record<string, unknown>) => api.post(`${root}/presence/me`, d).then(r => r.data),

  // Notifications
  listNotifications: (unread_only=false) => api.get(`${root}/notifications`, { params: { unread_only } }).then(unwrapList),
  markAllRead:       () => api.post(`${root}/notifications/mark-all-read`).then(r => r.data),
  markNotifRead:     (id: any) => api.post(`${root}/notifications/${id}/read`).then(r => r.data),
  listRules:    () => api.get(`${root}/notification-rules`).then(unwrapList),
  upsertRule:   (d: Record<string, unknown>) => api.put(`${root}/notification-rules`, d).then(r => r.data),

  // Search
  search: (params?: any) => api.get(`${root}/search`, { params }).then(r => r.data),
  mentionSuggestions: (params?: any) => api.get(`${root}/mention-suggestions`, { params }).then(r => r.data),
  linkMessage: (id: any, body: Record<string, unknown>) => api.post(`${root}/messages/${id}/link`, body).then(r => r.data),
  linkCandidates: (id: any, params?: any) => api.get(`${root}/messages/${id}/link/candidates`, { params }).then(r => r.data),

  // Attachments
  uploadAttachment: (form: any) => api.post(`${root}/attachments`, form).then(r => r.data),
  getAttachment:    (id: any) => api.get(`${root}/attachments/${id}`).then(r => r.data),

  // Calls
  startCall: (d: Record<string, unknown>) => api.post(`${root}/calls/start`, d).then(r => r.data),
  joinCall:  (id: any) => api.post(`${root}/calls/${id}/join`).then(r => r.data),
  leaveCall: (id: any) => api.post(`${root}/calls/${id}/leave`).then(r => r.data),
  endCall:   (id: any) => api.post(`${root}/calls/${id}/end`).then(r => r.data),
  startRecording: (id: any) => api.post(`${root}/calls/${id}/recording/start`).then(r => r.data),
  getCall: (id: any) => api.get(`${root}/calls/${id}`).then(r => r.data),
  listCalls: (cid: any) => api.get(`${root}/conversations/${cid}/calls`).then(unwrapList),

  // Bots / slash
  listBots:    () => api.get(`${root}/bots`).then(unwrapList),
  invokeBot:   (d: Record<string, unknown>) => api.post(`${root}/bots/invoke`, d).then(r => r.data),
  slash:       (d: Record<string, unknown>) => api.post(`${root}/slash`, d).then(r => r.data),
  slashHelp:   () => api.get(`${root}/slash/help`).then(r => r.data),

  // Integrations / webhooks
  listIntegrations: () => api.get(`${root}/integrations`).then(unwrapList),
  createIntegration: (d: Record<string, unknown>) => api.post(`${root}/integrations`, d).then(r => r.data),
  deleteIntegration: (id: any) => api.delete(`${root}/integrations/${id}`).then(r => r.data),
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
  releaseLegalHold:  (id: any) => api.post(`${root}/legal-holds/${id}/release`).then(r => r.data),
  ediscoveryExport:  (d: Record<string, unknown>) => api.post(`${root}/ediscovery/export`, d).then(r => r.data),
  listAudit:         (limit=200) => api.get(`${root}/audit`, { params: { limit } }).then(unwrapList),
  verifyAudit:       () => api.get(`${root}/audit/verify`).then(r => r.data),
}
