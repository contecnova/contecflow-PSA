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
  updateWorkspace: (d) => api.patch(`${root}/workspace`, d).then(r => r.data),

  // Teams
  listTeams:       () => api.get(`${root}/teams`).then(unwrapList),
  createTeam:      (d) => api.post(`${root}/teams`, d).then(r => r.data),
  updateTeam:      (id, d) => api.patch(`${root}/teams/${id}`, d).then(r => r.data),
  listTeamMembers: (id) => api.get(`${root}/teams/${id}/members`).then(unwrapList),
  addTeamMembers:  (id, body) => api.post(`${root}/teams/${id}/members`, body).then(r => r.data),
  removeTeamMember: (id, uid) => api.delete(`${root}/teams/${id}/members/${uid}`).then(r => r.data),

  // Channels
  listChannels:    (team_id) => api.get(`${root}/channels`, { params: { team_id } }).then(unwrapList),
  createChannel:   (d) => api.post(`${root}/channels`, d).then(r => r.data),
  updateChannel:   (id, d) => api.patch(`${root}/channels/${id}`, d).then(r => r.data),
  addChannelMembers: (id, body) => api.post(`${root}/channels/${id}/members`, body).then(r => r.data),
  listChannelMembers: (id) => api.get(`${root}/channels/${id}/members`).then(unwrapList),

  // Conversations
  listConversations: () => api.get(`${root}/conversations`).then(unwrapList),
  getConversation:   (id) => api.get(`${root}/conversations/${id}`).then(r => r.data),
  openDirect:        (d) => api.post(`${root}/direct/open`, d).then(r => r.data),
  createGroup:       (d) => api.post(`${root}/groups`, d).then(r => r.data),
  listConversationMembers:   (cid) => api.get(`${root}/conversations/${cid}/members`).then(unwrapList),
  addConversationMembers:    (cid, body) => api.post(`${root}/conversations/${cid}/members`, body).then(r => r.data),
  removeConversationMember:  (cid, uid) => api.delete(`${root}/conversations/${cid}/members/${uid}`).then(r => r.data),

  // Messages
  listMessages: (cid, params) => api.get(`${root}/conversations/${cid}/messages`, { params }).then(unwrapList),
  sendMessage:  (d) => api.post(`${root}/messages`, d).then(r => r.data),
  editMessage:  (id, d) => api.patch(`${root}/messages/${id}`, d).then(r => r.data),
  deleteMessage:(id) => api.delete(`${root}/messages/${id}`).then(r => r.data),
  getVersions:  (id) => api.get(`${root}/messages/${id}/versions`).then(r => r.data),
  toggleReaction: (id, emoji) => api.post(`${root}/messages/${id}/reactions`, { emoji }).then(r => r.data),
  markRead:    (cid, last_message_id) => api.post(`${root}/conversations/${cid}/read`, { last_message_id }).then(r => r.data),

  // Pins / saved
  pinMessage:   (cid, message_id) => api.post(`${root}/conversations/${cid}/pins`, { message_id }).then(r => r.data),
  unpinMessage: (cid, mid) => api.delete(`${root}/conversations/${cid}/pins/${mid}`).then(r => r.data),
  listPins:     (cid) => api.get(`${root}/conversations/${cid}/pins`).then(unwrapList),
  saveMessage:  (message_id, note) => api.post(`${root}/saved`, { message_id, note }).then(r => r.data),
  unsaveMessage:(mid) => api.delete(`${root}/saved/${mid}`).then(r => r.data),
  listSaved:    () => api.get(`${root}/saved`).then(unwrapList),
  listMyMentions: () => api.get(`${root}/mentions`).then(unwrapList),

  // Drafts
  saveDraft:    (cid, body, parent_message_id) => api.put(`${root}/conversations/${cid}/draft`, { body, parent_message_id }).then(r => r.data),
  getDraft:     (cid, parent_message_id) => api.get(`${root}/conversations/${cid}/draft`, { params: { parent_message_id } }).then(r => r.data),

  // Presence
  listPresence: () => api.get(`${root}/presence`).then(unwrapList),
  setPresence:  (d) => api.post(`${root}/presence/me`, d).then(r => r.data),

  // Notifications
  listNotifications: (unread_only=false) => api.get(`${root}/notifications`, { params: { unread_only } }).then(unwrapList),
  markAllRead:       () => api.post(`${root}/notifications/mark-all-read`).then(r => r.data),
  markNotifRead:     (id) => api.post(`${root}/notifications/${id}/read`).then(r => r.data),
  listRules:    () => api.get(`${root}/notification-rules`).then(unwrapList),
  upsertRule:   (d) => api.put(`${root}/notification-rules`, d).then(r => r.data),

  // Search
  search: (params) => api.get(`${root}/search`, { params }).then(r => r.data),
  mentionSuggestions: (params) => api.get(`${root}/mention-suggestions`, { params }).then(r => r.data),
  linkMessage: (id, body) => api.post(`${root}/messages/${id}/link`, body).then(r => r.data),
  linkCandidates: (id, params) => api.get(`${root}/messages/${id}/link/candidates`, { params }).then(r => r.data),

  // Attachments
  uploadAttachment: (form) => api.post(`${root}/attachments`, form).then(r => r.data),
  getAttachment:    (id) => api.get(`${root}/attachments/${id}`).then(r => r.data),

  // Calls
  startCall: (d) => api.post(`${root}/calls/start`, d).then(r => r.data),
  joinCall:  (id) => api.post(`${root}/calls/${id}/join`).then(r => r.data),
  leaveCall: (id) => api.post(`${root}/calls/${id}/leave`).then(r => r.data),
  endCall:   (id) => api.post(`${root}/calls/${id}/end`).then(r => r.data),
  startRecording: (id) => api.post(`${root}/calls/${id}/recording/start`).then(r => r.data),
  getCall: (id) => api.get(`${root}/calls/${id}`).then(r => r.data),
  listCalls: (cid) => api.get(`${root}/conversations/${cid}/calls`).then(unwrapList),

  // Bots / slash
  listBots:    () => api.get(`${root}/bots`).then(unwrapList),
  invokeBot:   (d) => api.post(`${root}/bots/invoke`, d).then(r => r.data),
  slash:       (d) => api.post(`${root}/slash`, d).then(r => r.data),
  slashHelp:   () => api.get(`${root}/slash/help`).then(r => r.data),

  // Integrations / webhooks
  listIntegrations: () => api.get(`${root}/integrations`).then(unwrapList),
  createIntegration: (d) => api.post(`${root}/integrations`, d).then(r => r.data),
  deleteIntegration: (id) => api.delete(`${root}/integrations/${id}`).then(r => r.data),
  listWebhooks:     () => api.get(`${root}/webhooks`).then(unwrapList),
  createWebhook:    (d) => api.post(`${root}/webhooks`, d).then(r => r.data),

  // Calendar
  calendarEvents: (days = 7) => api.get(`${root}/calendar/events`, { params: { days } }).then(unwrapList),

  // Decisions
  listDecisions: (limit = 100) => api.get(`${root}/decisions`, { params: { limit } }).then(unwrapList),

  // Compliance
  listRetention:     () => api.get(`${root}/retention`).then(unwrapList),
  createRetention:   (d) => api.post(`${root}/retention`, d).then(r => r.data),
  runRetention:      () => api.post(`${root}/retention/run`).then(r => r.data),
  listLegalHolds:    () => api.get(`${root}/legal-holds`).then(unwrapList),
  createLegalHold:   (d) => api.post(`${root}/legal-holds`, d).then(r => r.data),
  releaseLegalHold:  (id) => api.post(`${root}/legal-holds/${id}/release`).then(r => r.data),
  ediscoveryExport:  (d) => api.post(`${root}/ediscovery/export`, d).then(r => r.data),
  listAudit:         (limit=200) => api.get(`${root}/audit`, { params: { limit } }).then(unwrapList),
  verifyAudit:       () => api.get(`${root}/audit/verify`).then(r => r.data),
}
