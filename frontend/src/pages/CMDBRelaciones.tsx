// Modales de relaciones y cambios de un elemento de la CMDB y sus activos enlazados. 23-11-2026: troceado de CMDBPage sin cambio de comportamiento.
import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, fmtDateTime } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { cmdbApi } from '../services/api'
import { Button, Spinner, Modal, EmptyState, IconButton, Select } from '../components/ui'
import { History, Link2, Trash2 } from 'lucide-react'
import { IconoCi } from '../components/cmdb/iconosCi'
import { useAppT } from '../i18n/AppLangContext'
import { STALE_SHORT_MS } from '../constants/timings'
import { type CI, REL_TYPES, chip, useEtiqueta } from './CMDBComun'

type Rel = { id: string; relation_type: string; source: { id: string; name: string; type: string }; target: { id: string; name: string; type: string } }

/** Una relación leída desde un CI: `hosts` de A a B se lee «A aloja a B». */
export function RelLinea({ r, ciId }: { r: Rel; ciId: string }) {
  const t = useAppT()
  const etiqueta = useEtiqueta()
  const sale = r.source.id === ciId
  const otro = sale ? r.target : r.source
  return (
    <span className="cmdb-rel-text">
      {sale
        ? <>{etiqueta('rel_', r.relation_type)} <strong className="u-text1 cmdb-ci-ref"><IconoCi tipo={otro.type} size={13} />{otro.name}</strong></>
        : <><strong className="u-text1 cmdb-ci-ref"><IconoCi tipo={otro.type} size={13} />{otro.name}</strong> {etiqueta('rel_', r.relation_type)} {t('cmdb.this_ci')}</>}
    </span>
  )
}

export function useRelaciones(ciId?: string) {
  return useQuery<Rel[]>({
    queryKey: ['item-rels', ciId],
    queryFn: () => cmdbApi.sdRelations(ciId).then(r => r.data ?? []),
    enabled: !!ciId,
  })
}

export function RelationsModal({ item, allItems, onClose }: { item: CI; allItems: CI[]; onClose: () => void }) {
  const t = useAppT()
  const etiqueta = useEtiqueta()
  const toast = useToast()
  const qc = useQueryClient()
  const [toId, setToId] = useState('')
  const [relType, setRelType] = useState('depends_on')
  const { data: rels = [], isLoading } = useRelaciones(item.id)
  const refrescar = () => qc.invalidateQueries({ queryKey: ['item-rels'] })

  const { mutate: createRel, isPending } = useMutation({
    mutationFn: () => cmdbApi.sdCreateRelation({ source_ci_id: item.id, target_ci_id: toId, relation_type: relType }),
    onSuccess: () => { refrescar(); setToId('') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteRel } = useMutation({
    mutationFn: (id: string) => cmdbApi.sdDeleteRelation(id),
    onSuccess: refrescar,
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <Modal open onClose={onClose} title={t('cmdb.relations_of', { name: item.name ?? '' })}>
      <div className="u-stack-16">
        {isLoading ? <Spinner /> : rels.length === 0 ? (
          <EmptyState icon={<Link2 size={28} />} title={t('cmdb.sin_relaciones_definidas')} />
        ) : (
          <div className="cmdb-rel-list">
            {rels.map(r => (
              <div key={r.id} className="cmdb-rel-row">
                <RelLinea r={r} ciId={item.id} />
                <IconButton variante="caja" tono="peligro" ariaLabel={t('cmdb.delete_relation')}
                  onClick={() => openConfirmGlobal({ message: t('cmdb.delete_relation_q'), onConfirm: () => deleteRel(r.id), danger: true })}><Trash2 size={14} /></IconButton>
              </div>
            ))}
          </div>
        )}
        <div className="cmdb-rel-add">
          <div className="cmdb-rel-add__title">{t('cmdb.anadir_relacion')}</div>
          <div className="cmdb-rel-add__grid">
            <Select suelto placeholder={false} aria-label={t('cmdb.relation_type')} className="cmdb-input cmdb-input--w180" value={relType} onChange={e => setRelType(e.target.value)}>
              {REL_TYPES.map(r => <option key={r} value={r}>{etiqueta('rel_', r)}</option>)}
            </Select>
            <Select suelto placeholder={false} aria-label={t('cmdb.target_ci')} className="cmdb-input" value={toId} onChange={e => setToId(e.target.value)}>
              <option value="">{t('cmdb.target_ci')}</option>
              {allItems.filter(i => i.id !== item.id).map(i => (
                <option key={i.id} value={i.id}>{i.name}</option>
              ))}
            </Select>
          </div>
          <div className="cmdb-mt10">
            <Button onClick={() => createRel()} disabled={isPending || !toId} loading={isPending}>{t('cmdb.add_relation')}</Button>
          </div>
        </div>
        <div className="u-row-end">
          <Button variant="secondary" onClick={onClose}>{t('cmdb.close')}</Button>
        </div>
      </div>
    </Modal>
  )
}

type ChangelogEntry = { id: string; action?: string; created_at?: string; user_name?: string; summary?: string; field?: string; old_value?: string; new_value?: string }

export function ChangelogModal({ item, onClose }: { item: CI; onClose: () => void }) {
  const t = useAppT()
  const etiqueta = useEtiqueta()
  const { data: entries = [], isLoading } = useQuery<ChangelogEntry[]>({
    queryKey: ['cmdb-changelog', item.id],
    queryFn: () => cmdbApi.sdChangelog(item.id).then(r => r.data ?? []),
  })
  const ACTION_COLOR: Record<string, string> = { created: 'var(--success)', updated: 'var(--accent)', deleted: 'var(--danger)' }

  return (
    <Modal open onClose={onClose} title={t('cmdb.history_of', { name: item.name ?? '' })} width={580}>
      {isLoading ? <Spinner /> : entries.length === 0 ? (
        <EmptyState icon={<History size={28} />} title={t('cmdb.sin_cambios_registrados')} />
      ) : (
        <div className="cmdb-log">
          {entries.map(e => {
            const color = ACTION_COLOR[e.action ?? ''] || 'var(--text-2)'
            return (
              <div key={e.id} className="cmdb-log__entry">
                <div className="cmdb-log__head">
                  <span className="cmdb-chip cmdb-chip--bold" style={chip(color)}>{etiqueta('action_', e.action)}</span>
                  <span className="u-text2-xs">
                    {e.created_at ? fmtDateTime(e.created_at) : ''}
                    {e.user_name ? ` · ${t('cmdb.por')} ${e.user_name}` : ` · ${t('cmdb.by_discovery')}`}
                  </span>
                </div>
                <div className="cmdb-log__summary">{e.summary}</div>
                {e.field && (
                  <div className="cmdb-log__field">
                    <code className="ds-codigo cmdb-code">{e.field}</code>
                    {e.old_value && <span> · <span className="u-danger">−{e.old_value}</span></span>}
                    {e.new_value && <span> → <span className="u-success">+{e.new_value}</span></span>}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </Modal>
  )
}

// ── Linked assets for a CI (drill-down panel) ────────────────────────────────
/** Activo de ALM vinculado a un CI. */
interface LinkedAsset { id: string; name?: string; serial_number?: string | null; status?: string | null }

export function CILinkedAssets({ ciId }: { ciId: string }) {
  const t = useAppT()
  const { data: assets = [], isLoading } = useQuery<LinkedAsset[]>({
    queryKey: ['ci-assets', ciId],
    queryFn: () => cmdbApi.assetsByCI(ciId).then(r => r.data),
    staleTime: STALE_SHORT_MS,
  })
  if (isLoading) return null
  return (
    <div className="cmdb-assets">
      <div className="cmdb-section-title">
        {t('cmdb.linked_assets', { n: assets.length })}
      </div>
      {assets.length === 0 ? (
        <div className="u-text2-sm">{t('cmdb.ningun_activo_vinculado_a_este_ci')}</div>
      ) : (
        <div className="u-stack-6">
          {assets.map(a => (
            <div key={a.id} className="cmdb-asset">
              <div className="u-flex1-min0">
                <div className="cmdb-asset__name" title={a.name}>{a.name}</div>
                {a.serial_number ? <div className="u-text2-2xs">{t('cmdb.serial_number', { sn: String(a.serial_number) })}</div> : null}
              </div>
              {a.status ? <span className="cmdb-asset__status">{String(a.status)}</span> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
