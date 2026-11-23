// Secciones de hoja de ruta, documentos y wiki del portal de cliente. 23-11-2026: troceado de PortalAdvancedSections sin cambio de comportamiento.
import { type CSSProperties, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Map, BookOpen, FileText, Search, ArrowLeft, FileSignature, Download, CheckCircle2, Package, Wallet, CalendarDays, Eye, ThumbsUp, Tag } from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { fmtDate } from '../../utils/helpers'
import { CLIENT_API, useErrorDelPortal, useLang, useIdiomaDelPortal, rellenar } from './portalClientContext'
import type { ApiError } from '../../services/api'
import PortalKbArticulo from './PortalKbArticulo'
import { MarcaDeTraduccion, textoDe } from './TraduccionAutomatica'
import { Buscador } from '../../components/ui'
import { PortalPageHeader, PortalCard, PortalSection, PortalEmpty, PortalBadge, PortalButton, PortalModal, PortalField, PortalInput, PortalProgress, PortalBanner, PortalTabs } from './PortalUI'
import { isSafeUrl, sanitizeUrl } from '../../utils/security'
import { type ClientDocument, type ClientProjectDetail, type KbArticle, type RoadmapDeliverable, type RoadmapMilestone, StatusBadge, type WikiPageDetail, type WikiPageSummary } from './PortalAdvancedComun'

// ════════════════════════════════════════════════════════════════════════════
// PortalRoadmap
// ════════════════════════════════════════════════════════════════════════════
export function PortalRoadmap() {
  const traducir = useLang()
  const t = useLang()
  const { data, isLoading, error } = useQuery<ClientProjectDetail | null>({
    queryKey: ['portal-project'],
    queryFn: () => CLIENT_API.get('/portal/project').then(r => r.data).catch((e: ApiError) => {
      if (e?.response?.status === 404 || e?.response?.status === 403) return null
      throw e
    }),
  })

  const milestones: RoadmapMilestone[] = data?.milestones || []
  const deliverables: RoadmapDeliverable[] = data?.deliverables || []
  const completedMs = milestones.filter(m => m.is_completed).length
  const completedDel = deliverables.filter(d => d.status === 'accepted').length

  if (isLoading) return (
    <div>
      <PortalPageHeader title={t('nav_roadmap')} icon={Map} />
      <div className="poadse-box-5">{traducir('common.loading')}</div>
    </div>
  )
  if (!data || error) return (
    <div>
      <PortalPageHeader title={t('nav_roadmap')} icon={Map} />
      <PortalEmpty icon={Map} title={traducir('portaladvanced.sin_proyecto_asignado')} description={traducir('portaladvanced.cuando_tengas_un_proyecto_activo_veras_aqui')} />
    </div>
  )

  return (
    <div>
      <PortalPageHeader
        title={traducir('portaladvanced.roadmap_del_proyecto')}
        subtitle={traducir('portaladvanced.hitos_planificados_y_entregables_del_proyecto')}
        icon={Map}
        meta={[
          { value: `${completedMs}/${milestones.length}`, label: t('pas_meta_ms_done'), color: 'var(--accent)' },
          { value: `${completedDel}/${deliverables.length}`, label: t('pas_meta_del_accepted'), color: 'var(--success)' },
        ]}
      />

      {milestones.length === 0 && deliverables.length === 0 ? (
        <PortalEmpty icon={Map} title={traducir('portaladvanced.aun_sin_plan_publicado')}
          description={traducir('portaladvanced.el_equipo_todavia_no_ha_publicado_hitos')} />
      ) : (
        <div className="poadse-grid-2">
          <PortalCard>
            <PortalSection title={traducir('pres.tipo_hitos')} hint={rellenar(t('pas_x_of_y_completed'), { x: completedMs, y: milestones.length })}>
              {milestones.length === 0 ? (
                <PortalEmpty icon={CalendarDays} title={traducir('portaladvanced.sin_hitos_planificados')} />
              ) : (
                <div className="u-stack-10">
                  <PortalProgress value={milestones.length ? (completedMs / milestones.length) * 100 : 0} color="var(--success)" />
                  {milestones.map((m, i) => (
                    <div key={m.id} className="poadse-row-19">
                      <div className="poadse-stack-2">
                        <div className={`poadse-row-31 portalad-sx6 portal-advanced-sections-e9 ${m.is_completed ? 'portal-advanced-sections-m10' : 'portal-advanced-sections-m11'}`} style={{ '--portal-advanced-sections-border': `2px solid ${m.is_completed ? 'var(--success)' : 'var(--surface-4)'}` } as CSSProperties}>
                          {m.is_completed ? <CheckCircle2 size={14} /> : i + 1}
                        </div>
                        {i < milestones.length - 1 && (
                          <div className={`poadse-box-30 ${m.is_completed ? 'portal-advanced-sections-m12' : 'portal-advanced-sections-m13'}`} />
                        )}
                      </div>
                      <div className="poadse-box-17">
                        <div className={`poadse-txt-8 ${m.is_completed ? 'portal-advanced-sections-m14' : 'portal-advanced-sections-m15'}`}>{m.name}</div>
                        <div className="poadse-row-20">
                          {m.due_date && <span className="poadse-con-icono"><CalendarDays size={12} aria-hidden="true" />{fmtDate(m.due_date)}</span>}
                          {m.billing_pct && <span className="u-warning poadse-con-icono"><Wallet size={12} aria-hidden="true" />{m.billing_pct}%</span>}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </PortalSection>
          </PortalCard>

          <PortalCard>
            <PortalSection title={traducir('nav.deliverables')} hint={rellenar(t('pas_x_of_y_accepted'), { x: completedDel, y: deliverables.length })}>
              {deliverables.length === 0 ? (
                <PortalEmpty icon={Package} title={traducir('portaladvanced.sin_entregables_planificados')} />
              ) : (
                <div className="u-stack-8">
                  {deliverables.map(d => (
                    <div key={d.id} className="poadse-row-21">
                      <Package size={15} className="portalad-sx7" />
                      <div className="u-flex1-min0">
                        <div className="poadse-box-18">{d.name}</div>
                        <div className="u-text3-xs">
                          {d.format && `${d.format} · `}{fmtDate(d.planned_date)}
                        </div>
                      </div>
                      <StatusBadge status={d.status} />
                    </div>
                  ))}
                </div>
              )}
            </PortalSection>
          </PortalCard>
        </div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// PortalDocuments
// ════════════════════════════════════════════════════════════════════════════
export function PortalDocuments() {
  const traducir = useLang()
  const errorDe = useErrorDelPortal()
  const t = useLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [signModal, setSignModal] = useState<{ id: string; title: string } | null>(null)
  const [signJobTitle, setSignJobTitle] = useState('')
  const [signedPdfB64, setSignedPdfB64] = useState<{ b64: string; title: string } | null>(null)

  const { data: docs = [] } = useQuery<ClientDocument[]>({
    queryKey: ['portal-docs-client'],
    queryFn: () => CLIENT_API.get('/portal/documents').then(r => r.data),
  })

  const { mutate: sign, isPending: signing } = useMutation({
    mutationFn: ({ id, job_title }: { id: string; job_title: string }) => CLIENT_API.post(`/portal/documents/${id}/sign`, { job_title }).then(r => r.data),
    onSuccess: (data: { pdf_b64?: string | null } | null) => {
      qc.invalidateQueries({ queryKey: ['portal-docs-client'] })
      setSignModal(null)
      setSignJobTitle('')
      if (data?.pdf_b64) {
        setSignedPdfB64({ b64: data.pdf_b64, title: signModal?.title || 'documento' })
      } else toast.success(traducir('portaladvanced.documento_firmado_correctamente'))
    },
    onError: (e: unknown) => toast.error(errorDe(e, t('pas_err_generic'))),
  })

  useEffect(() => {
    if (!signedPdfB64) return
    const bytes = atob(signedPdfB64.b64)
    const arr = new Uint8Array(bytes.length)
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
    const blob = new Blob([arr], { type: 'application/pdf' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Firmado_${signedPdfB64.title.replace(/\s+/g, '_').slice(0, 40)}.pdf`
    a.click()
    // 23-11-2026 (B7 del 04b): revocar en la vuelta siguiente; en el mismo tick algunos navegadores cancelan la descarga.
    setTimeout(() => URL.revokeObjectURL(url), 0)
    setSignedPdfB64(null)
    toast.success(traducir('portaladvanced.certificado_de_firma_descargado'))
  }, [signedPdfB64, toast, traducir])

  const pendingSign = docs.filter(d => d.requires_signature && !d.signed_by_client).length

  return (
    <div>
      <PortalPageHeader
        title={traducir('docs.titulo')}
        subtitle={traducir('portaladvanced.documentacion_compartida_del_proyecto_contratos_actas_informes')}
        icon={FileText}
        meta={[
          { value: docs.length, label: t('pas_meta_documents') },
          { value: pendingSign, label: t('pas_meta_to_sign'), color: pendingSign ? 'var(--warning)' : 'var(--text-3)' },
        ]}
      />

      {docs.length === 0 ? (
        <PortalEmpty icon={FileText} title={traducir('portaladvanced.sin_documentos')} description={traducir('portaladvanced.aqui_apareceran_contratos_informes_y_entregables_compartidos')} />
      ) : (
        <div className="u-stack-10">
          {docs.map(doc => (
            <PortalCard key={doc.id}>
              <div className="poadse-row-22">
                <div className="poadse-row-23"><FileText size={18} /></div>
                <div className="u-flex1-min0">
                  <div className="u-sm-700">{doc.title}</div>
                  {doc.description && <div className="u-text2-xs-mt2">{doc.description}</div>}
                  <div className="u-hint">
                    {doc.file_name || (doc.category ? t(`doc_cat_${doc.category}`) : '')} · {fmtDate(doc.created_at)}
                  </div>
                </div>
                <div className="poadse-row-24">
                  {doc.requires_signature && !doc.signed_by_client && (
                    <PortalButton size="sm" icon={<FileSignature size={13} />}
                      onClick={() => { setSignModal({ id: doc.id, title: doc.title }); setSignJobTitle('') }}>
                      {traducir('portaladvanced.firmar')}
                    </PortalButton>
                  )}
                  {doc.signed_by_client && (
                    <PortalBadge tone="success" icon={<CheckCircle2 size={11} />}>
                      {traducir('client_portal.docs_signed')} {doc.signed_at ? fmtDate(doc.signed_at) : ''}
                    </PortalBadge>
                  )}
                  {doc.file_url && isSafeUrl(doc.file_url) && (
                    <a href={sanitizeUrl(doc.file_url)} target="_blank" rel="noopener noreferrer"
                      className="poadse-row-25"><Download size={13} /> {traducir('aus.descargar')}</a>
                  )}
                </div>
              </div>
            </PortalCard>
          ))}
        </div>
      )}

      <PortalModal
        open={!!signModal}
        onClose={() => setSignModal(null)}
        title={traducir('portaladvanced.firmar_documento')}
        subtitle={signModal?.title || ''}
        footer={
          <>
            <PortalButton variant="secondary" onClick={() => setSignModal(null)}>{traducir('common.cancel')}</PortalButton>
            <PortalButton loading={signing} icon={<FileSignature size={13} />}
              onClick={() => { if (signModal) sign({ id: signModal.id, job_title: signJobTitle }) }}>
              {traducir('portaladvanced.firmar')}
            </PortalButton>
          </>
        }
      >
        <div className="u-stack-12">
          <PortalField label={traducir('portaladvanced.cargo_funcion')} hint={t('pas_sign_hint')}>
            <PortalInput value={signJobTitle} onChange={e => setSignJobTitle(e.target.value)} placeholder={traducir('portaladvanced.ej_director_de_operaciones')} />
          </PortalField>
          <PortalBanner tone="info" icon={<FileSignature size={16} />} title={traducir('portaladvanced.firma_con_certificado_pdf')} body={t('pas_sign_body')} />
        </div>
      </PortalModal>
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// PortalWiki
// ════════════════════════════════════════════════════════════════════════════
export function PortalWiki() {
  const traducir = useLang()
  const t = useLang()
  const idioma = useIdiomaDelPortal()
  const [selected, setSelected] = useState<string | null>(null)
  const [tab, setTab] = useState('docs')
  const [searchKB, setSearchKB] = useState('')
  // Revisión 2026-11: el artículo se listaba y no se podía abrir.
  const [articuloAbierto, setArticuloAbierto] = useState<string | null>(null)
  // «Ver original» de la página abierta (título y bloques traducidos automáticamente).
  const [wikiOriginal, setWikiOriginal] = useState(false)
  useEffect(() => { setWikiOriginal(false) }, [selected])

  const { data: pages = [], isLoading } = useQuery<WikiPageSummary[]>({
    // 16-11-2026: título y contenido en el idioma del portal (si la empresa traduce).
    queryKey: ['portal-wiki-pages', idioma],
    queryFn: () => CLIENT_API.get('/portal/wiki/pages', { params: { lang: idioma } }).then(r => r.data),
  })
  const { data: pageDetail } = useQuery<WikiPageDetail | null>({
    queryKey: ['portal-wiki-page', selected, idioma],
    queryFn: () => CLIENT_API.get(`/portal/wiki/pages/${selected}`, { params: { lang: idioma } }).then(r => r.data),
    enabled: !!selected,
  })
  const { data: kbArticles = [], isLoading: loadingKB } = useQuery<KbArticle[]>({
    queryKey: ['portal-wiki-kb', searchKB, idioma],
    queryFn: () => CLIENT_API.get('/sd/kb', { params: { public_only: true, search: searchKB || undefined, lang: idioma } }).then(r => r.data),
    enabled: tab === 'kb',
  })

  const tabs = [
    { id: 'docs', label: t('wiki_tab_docs'), icon: <FileText size={14} /> },
    { id: 'kb',   label: t('wiki_tab_kb'), icon: <BookOpen size={14} /> },
  ]

  if (articuloAbierto) {
    return <PortalKbArticulo id={articuloAbierto} onVolver={() => setArticuloAbierto(null)} migas={traducir('portalkb.migas_wiki')} />
  }
  if (selected && pageDetail) {
    const bloques = Array.isArray(pageDetail.content) ? pageDetail.content : []
    const origen = pageDetail.translated_from ?? bloques.find(b => b.translated_from)?.translated_from ?? null
    const titulo = textoDe(pageDetail, 'title', pageDetail.title, wikiOriginal)
    return (
      <div>
        <PortalPageHeader
          title={titulo}
          icon={BookOpen}
          breadcrumb={[{ label: traducir('portaladvanced.wiki_y_conocimiento'), onClick: () => setSelected(null) }, { label: titulo }]}
          actions={<PortalButton variant="secondary" size="sm" icon={<ArrowLeft size={13} />} onClick={() => setSelected(null)}>{traducir('chat.back')}</PortalButton>}
        />
        <PortalCard>
          <MarcaDeTraduccion origen={origen} verOriginal={wikiOriginal} onAlternar={() => setWikiOriginal(v => !v)} />
          <div className="poadse-txt-7" lang={wikiOriginal ? origen ?? undefined : undefined}>
            {typeof pageDetail.content === 'string' && (
              <p className="u-mb-10">{textoDe(pageDetail, 'content', pageDetail.content, wikiOriginal)}</p>
            )}
            {bloques.map((block, i) => {
              const contenido = textoDe(block, 'content', block.content, wikiOriginal)
              if (block.type === 'heading1') return <h1 key={i} className="poadse-box-19">{contenido}</h1>
              if (block.type === 'heading2') return <h2 key={i} className="poadse-box-20">{contenido}</h2>
              if (block.type === 'heading3') return <h3 key={i} className="poadse-box-21">{contenido}</h3>
              if (block.type === 'bullet') return <li key={i} className="poadse-sp-1">{contenido}</li>
              if (block.type === 'code') return <pre key={i} className="poadse-box-22">{contenido}</pre>
              if (block.type === 'callout') return <div key={i} className="poadse-box-23">{contenido}</div>
              if (block.type === 'separator') return <hr key={i} className="poadse-box-24" />
              return <p key={i} className="u-mb-10">{contenido}</p>
            })}
          </div>
          <div className="poadse-box-25">
            {traducir('portaladvanced.ultima_actualizacion')} {fmtDate(pageDetail.updated_at)}
          </div>
        </PortalCard>
      </div>
    )
  }

  return (
    <div>
      <PortalPageHeader
        title={traducir('portaladvanced.wiki_y_conocimiento')}
        subtitle={traducir('portaladvanced.documentacion_interna_del_proyecto_y_base_de')}
        icon={BookOpen}
        meta={[
          { value: pages.length, label: t('pas_meta_documents') },
          { value: kbArticles.length, label: t('pas_meta_kb_articles') },
        ]}
      />

      <PortalTabs tabs={tabs} value={tab} onChange={id => { setTab(id); setSelected(null) }} ariaLabel={traducir('portaladvanced.wiki_y_conocimiento')} />

      {tab === 'docs' && (
        <>
          {isLoading ? (
            <div className="poadse-box-5">{traducir('common.loading')}</div>
          ) : pages.length === 0 ? (
            <PortalEmpty icon={BookOpen} title={traducir('portaladvanced.sin_paginas')} description={traducir('portaladvanced.cuando_el_equipo_publique_documentacion_interna_la')} />
          ) : (
            <div className="poadse-grid-3">
              {pages.map(p => (
                <PortalCard key={p.id} onClick={() => setSelected(p.id)}>
                  <div className="poadse-row-19">
                    <div className="poadse-row-27">
                      <FileText size={16} />
                    </div>
                    <div className="u-flex1-min0">
                      <div className="poadse-box-2">{p.title}</div>
                      <div className="u-text3-xs">
                        {fmtDate(p.updated_at)}
                      </div>
                      {/* Solo la marca: el original se ve al abrir la página. */}
                      <MarcaDeTraduccion origen={p.translated_from} verOriginal={false} onAlternar={() => {}} puedeVerOriginal={false} />
                    </div>
                  </div>
                </PortalCard>
              ))}
            </div>
          )}
        </>
      )}

      {tab === 'kb' && (
        <>
          <Buscador className="poadse-box-26" value={searchKB} onChange={setSearchKB} placeholder={traducir('portaladvanced.buscar_en_la_base_de_conocimiento')} />
          {loadingKB ? (
            <div className="poadse-box-5">{traducir('common.loading')}</div>
          ) : kbArticles.length === 0 ? (
            <PortalEmpty icon={searchKB ? Search : BookOpen} title={searchKB ? rellenar(t('support_kb_no_results'), { q: searchKB }) : t('wiki_kb_empty')} />
          ) : (
            <div className="u-stack-10">
              {kbArticles.map(a => (
                <PortalCard key={a.id} onClick={() => setArticuloAbierto(a.id)}>
                  <div className="poadse-row-28">
                    <div className="u-sm-700">{a.title}</div>
                    <div className="u-text3-xs poadse-con-icono"><Eye size={12} aria-label={t('pas_views')} />{a.view_count ?? 0}<ThumbsUp size={12} aria-label={t('pas_helpful')} />{a.helpful_count ?? 0}</div>
                  </div>
                  {a.summary && <p className="poadse-box-27">{a.summary}</p>}
                  {a.tags && <div className="u-text3-xs poadse-con-icono"><Tag size={12} aria-hidden="true" />{a.tags}</div>}
                </PortalCard>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
