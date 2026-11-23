// Panel de politicas de conversacion del portal. 23-11-2026: troceado de GovernedConversations sin cambio de comportamiento.
import { useEffect, useState, useId } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { portalConversationsApi, sdGroupsApi } from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { useAppLang } from '../../i18n/AppLangContext'
import { Button, Checkbox, Select, Input } from '../ui'
import { Save } from 'lucide-react'
import StatusBadge from '../ui/StatusBadge'
import { type AgentGroup, type ConversationPolicy, EMPTY_LIST, POLICY_FLAGS, type PolicyDraft, type PolicyPayload, etiquetaDeTema } from './GovernedConversationsComun'

export function ConversationPoliciesPanel() {
  const idCampo = useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [drafts, setDrafts] = useState<Record<string, PolicyDraft>>({})

  const { data: agentGroupsData } = useQuery<AgentGroup[]>({
    queryKey: ['sd-agent-groups', 'portal-conversations'],
    queryFn: () => sdGroupsApi.list().then((response) => response.data || []),
  })
  const agentGroups = agentGroupsData || EMPTY_LIST

  const { data: policiesData, isLoading } = useQuery<ConversationPolicy[]>({
    queryKey: ['portal-conversation-policies'],
    queryFn: () => portalConversationsApi.getPolicies().then((response) => response.data),
  })
  const policies = policiesData || EMPTY_LIST

  useEffect(() => {
    const nextDrafts: Record<string, PolicyDraft> = {}
    policies.forEach(policy => {
      nextDrafts[policy.topic_type] = {
        requires_client_message_approval: policy.requires_client_message_approval,
        requires_team_message_approval: policy.requires_team_message_approval,
        redact_sensitive_content: policy.redact_sensitive_content,
        allow_legacy_federation: policy.allow_legacy_federation,
        assignment_mode: policy.assignment_mode,
        default_role_key: policy.default_role_key || '',
        default_group_id: policy.default_group_id || '',
        first_response_hours: policy.first_response_hours || 0,
        escalation_hours: policy.escalation_hours || 0,
        approval_role_key: policy.approval_role_key || '',
        sensitive_keywords: Array.isArray(policy.sensitive_keywords) ? policy.sensitive_keywords.join(', ') : '',
      }
    })
    setDrafts((prev) => {
      const prevStr = JSON.stringify(prev)
      const nextStr = JSON.stringify(nextDrafts)
      return prevStr === nextStr ? prev : nextDrafts
    })
  }, [policies])

  const savePolicy = useMutation({
    mutationFn: ({ topicType, payload }: { topicType: string; payload: PolicyPayload }) => portalConversationsApi.updatePolicy(topicType, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portal-conversation-policies'] })
      toast.success(t('grc.retencion_guardada'))
    },
    onError: (error) => toast.error(extractErr(error, t('governedconversations.err_politica'))),
  })

  if (isLoading) return <div className="u-text2-base">{t('governedconversations.cargando_politicas')}</div>

  return (
    <div className="u-stack-14">
      {policies.map(policy => {
        const draft: PolicyDraft = drafts[policy.topic_type] || {}
        return (
          <div key={policy.id} className="goveconv-cardstyle4">
            <div className="goveconv-row-8">
              <div>
                <div className="goveconv-txt-6">{etiquetaDeTema(t, policy.topic_type)}</div>
                <div className="u-text2-sm">{t('governedconversations.politica_grc_y_de_enrutado_para_conversaciones')} {etiquetaDeTema(t, policy.topic_type).toLowerCase()}.</div>
              </div>
              <StatusBadge color={policy.is_active ? 'var(--success)' : 'var(--text-2)'}>{t(policy.is_active ? 'governedconversations.activa' : 'governedconversations.inactiva')}</StatusBadge>
            </div>

            <div className="goveconv-grid-2">
              <div>
                <label htmlFor={`${idCampo}-${policy.id}-modo`} className="goveconv-labelstyle">{t('governedconversations.modo_de_asignacion')}</label>
                <Select suelto placeholder={false} id={`${idCampo}-${policy.id}-modo`} value={draft.assignment_mode || 'manual'} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], assignment_mode: event.target.value } }))} className="goveconv-inputstyle">
                  <option value="manual">{t('governedconversations.manual')}</option>
                  <option value="owner_based">{t('governedconversations.owner_del_proyecto')}</option>
                  <option value="role_pool">{t('governedconversations.pool_rol')}</option>
                </Select>
              </div>
              <div>
                <label className="goveconv-labelstyle">{t('governedconversations.rol_por_defecto')}</label>
                <Input aria-label={t('governedconversations.rol_por_defecto')} value={draft.default_role_key || ''} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], default_role_key: event.target.value } }))} placeholder="admin, manager, pm..." inputClassName="goveconv-inputstyle" />
              </div>
              <div>
                <label id={`${idCampo}-${policy.id}-et-pool`} htmlFor={`${idCampo}-${policy.id}-pool`} className="goveconv-labelstyle">{t('governedconversations.pool_de_asignacion')}</label>
                <Select suelto placeholder={t('governedconversations.sin_pool')} id={`${idCampo}-${policy.id}-pool`} value={draft.default_group_id || ''} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], default_group_id: event.target.value } }))} className="goveconv-inputstyle">
                  {agentGroups.map(group => <option key={group.id} value={group.id}>{group.name}</option>)}
                </Select>
              </div>
              <div>
                <label id={`${idCampo}-${policy.id}-et-fr`} htmlFor={`${idCampo}-${policy.id}-fr`} className="goveconv-labelstyle">{t('governedconversations.primera_respuesta_sla_h')}</label>
                <Input id={`${idCampo}-${policy.id}-fr`} aria-labelledby={`${idCampo}-${policy.id}-et-fr`} type="number" min={0} value={draft.first_response_hours || 0} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], first_response_hours: Number(event.target.value) } }))} inputClassName="goveconv-inputstyle" />
              </div>
              <div>
                <label id={`${idCampo}-${policy.id}-et-esc`} htmlFor={`${idCampo}-${policy.id}-esc`} className="goveconv-labelstyle">{t('governedconversations.escalado_sla_h')}</label>
                <Input id={`${idCampo}-${policy.id}-esc`} aria-labelledby={`${idCampo}-${policy.id}-et-esc`} type="number" min={0} value={draft.escalation_hours || 0} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], escalation_hours: Number(event.target.value) } }))} inputClassName="goveconv-inputstyle" />
              </div>
              <div>
                <label id={`${idCampo}-${policy.id}-et-apr`} htmlFor={`${idCampo}-${policy.id}-apr`} className="goveconv-labelstyle">{t('governedconversations.rol_aprobador')}</label>
                <Input id={`${idCampo}-${policy.id}-apr`} aria-labelledby={`${idCampo}-${policy.id}-et-apr`} value={draft.approval_role_key || ''} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], approval_role_key: event.target.value } }))} placeholder="admin" inputClassName="goveconv-inputstyle" />
              </div>
              <div>
                <label id={`${idCampo}-${policy.id}-et-kw`} htmlFor={`${idCampo}-${policy.id}-kw`} className="goveconv-labelstyle">{t('governedconversations.keywords_sensibles')}</label>
                <Input id={`${idCampo}-${policy.id}-kw`} aria-labelledby={`${idCampo}-${policy.id}-et-kw`} value={draft.sensitive_keywords || ''} onChange={(event) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], sensitive_keywords: event.target.value } }))} placeholder="password, token, iban" inputClassName="goveconv-inputstyle" />
              </div>
            </div>

            <div className="goveconv-grid-3">
              {POLICY_FLAGS.map(([key, label]) => (
                <Checkbox key={key} className="goveconv-row-9" label={t(label)} checked={Boolean(draft[key])} onChange={(marcado) => setDrafts((prev) => ({ ...prev, [policy.topic_type]: { ...prev[policy.topic_type], [key]: marcado } }))} />
              ))}
            </div>

            <div className="goveconv-row-10">
              <Button
                icon={<Save size={13} />}
                loading={savePolicy.isPending}
                onClick={() => savePolicy.mutate({
                  topicType: policy.topic_type,
                  payload: {
                    requires_client_message_approval: Boolean(draft.requires_client_message_approval),
                    requires_team_message_approval: Boolean(draft.requires_team_message_approval),
                    redact_sensitive_content: Boolean(draft.redact_sensitive_content),
                    allow_legacy_federation: Boolean(draft.allow_legacy_federation),
                    assignment_mode: draft.assignment_mode,
                    default_group_id: draft.default_group_id || null,
                    default_role_key: draft.default_role_key || null,
                    first_response_hours: Number(draft.first_response_hours || 0),
                    escalation_hours: Number(draft.escalation_hours || 0),
                    approval_role_key: draft.approval_role_key || null,
                    sensitive_keywords: String(draft.sensitive_keywords || '').split(',').map((item) => item.trim()).filter(Boolean),
                  },
                })}
              >
                {t('governedconversations.guardar_politica')}
              </Button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
