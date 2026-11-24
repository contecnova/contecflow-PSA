/**
 * Cajón lateral de detalle de un documento.
 * Troceado de DocumentsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useState, useRef, useEffect, type CSSProperties, type ReactNode, useId } from 'react'
import type { AxiosError } from 'axios'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { documentsApi } from '../../services/api'
import { sanitizeUrl } from '../../utils/security'
import { PREFIJO_API_SERVIDOR } from '../../services/api/urls'
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import {
  Upload,
  Download,
  Pencil,
  Sparkles,
  History,
  X,
  Check,
  FolderOpen,
  FileClock,
  Eye,
  Info,
  Share2,
  CheckCircle,
  XCircle,
  ExternalLink,
  Loader,
  Lock,
  LockOpen,
} from 'lucide-react'
import { Button, Drawer, EmptyState, Tabs, IconButton, Select, Checkbox, Input, Textarea, cambiosGuardados } from '../../components/ui'
import { fmtDate, fmtDateTime, extractErr } from '../../utils/helpers'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import {
  APPROVAL_STYLE,
  CAT_STYLE,
  Chip,
  ChipAprobacion,
  detectFileType,
  type DocDetail,
  type DocVersion,
  etiquetaCategoria,
  FileIcon,
  fmtBytes,
  type MetaForm,
  type Reserva,
} from './compartido'
import { CATS, SharePanel } from './SubidaYCompartir'

export function DocumentDrawer({ documentId, onClose, onRefresh }: { documentId: string; onClose: () => void; onRefresh: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [tab, setTab] = useState('preview');  // preview | versions | meta
  const [file, setFile] = useState<File | null>(null);
  const [changeNote, setChangeNote] = useState('');
  const [showUploadVersion, setShowUploadVersion] = useState(false);
  const [previewVersion, setPreviewVersion] = useState<DocVersion | null>(null);
  const [previewError, setPreviewError] = useState(false);
  const [isEditingMeta, setIsEditingMeta] = useState(false);
  const [metaForm, setMetaForm] = useState<MetaForm | null>(null);

  const { data: doc, isLoading } = useQuery<DocDetail>({
    queryKey: ['document', documentId],
    queryFn: async () => {
      const res = await documentsApi.get(documentId);
      const d: DocDetail = res.data;
      if (d.versions) d.versions = d.versions.map(v => ({ ...v, download_url: v.download_url || v.s3_url }));
      return d;
    },
  });

  useEffect(() => {
    if (doc?.versions?.length && !previewVersion) setPreviewVersion(doc.versions[0]);
    // `previewVersion` faltaba (auditoría 2026-08, P1-6). El guard `!previewVersion`
    // impide reescribirlo, así que incluirlo es seguro y hace que el efecto
    // reaccione si la vista previa se limpia.
  }, [doc, previewVersion]);

  const approveMutation = useMutation({
    mutationFn: ({ status, note }: { status: string; note?: string }) => documentsApi.approve(documentId, { status, note }),
    onSuccess: (_: unknown, { status }: { status: string }) => { toast.success(status === 'approved' ? t('pagina_docs.paso_aprobado') : t('pagina_docs.documento_rechazado')); qc.invalidateQueries({ queryKey: ['document', documentId] }); onRefresh(); },
    onError: (e: unknown) => toast.error(extractErr(e, t('pagina_docs.error'))),
  });

  const submitApprovalMutation = useMutation({
    mutationFn: () => documentsApi.submitApproval(documentId),
    onSuccess: () => { toast.success(t('pagina_docs.solicitud_de_aprobacion_enviada')); qc.invalidateQueries({ queryKey: ['document', documentId] }); onRefresh(); },
    onError: (e: unknown) => toast.error(extractErr(e, t('pagina_docs.no_hay_ningun_flujo_de_aprobacion'))),
  });

  const summaryMutation = useMutation({
    mutationFn: () => documentsApi.aiSummary(documentId),
    onSuccess: () => {
      toast.success(t('pagina_docs.resumen_ia_generado'));
      qc.invalidateQueries({ queryKey: ['document', documentId] });
      setTab('meta');
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('pagina_docs.error_ia'))),
  });

  const reserva: Reserva = doc?.checkout
  const deOtro = !!reserva && !reserva.mine
  const reservaMutation = useMutation({
    mutationFn: (accion: 'checkout' | 'checkin' | 'force') =>
      accion === 'checkout' ? documentsApi.checkout(documentId) : documentsApi.checkin(documentId, accion === 'force'),
    onSuccess: (_: unknown, accion: 'checkout' | 'checkin' | 'force') => {
      toast.success(t(accion === 'checkout' ? 'documents.reserva_hecha' : 'documents.reserva_liberada'))
      qc.invalidateQueries({ queryKey: ['document', documentId] }); onRefresh()
    },
    // El 409 de la reserva trae `detail` como objeto `{ message, ... }`.
    onError: (e: AxiosError<{ detail?: string | { message?: string } }>) => {
      const d = e?.response?.data?.detail
      toast.error(typeof d === 'object' && d?.message ? d.message : extractErr(e, t('pagina_docs.error')))
    },
  });

  const versionMutation = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append('file', file!);
      if (changeNote) fd.append('change_note', changeNote);
      return documentsApi.addVersion(documentId, fd);
    },
    onSuccess: () => { toast.success(t('pagina_docs.nueva_version_subida')); qc.invalidateQueries({ queryKey: ['document', documentId] }); setFile(null); setChangeNote(''); setShowUploadVersion(false); cambiosGuardados(); onRefresh(); },
    onError: (e: unknown) => toast.error(extractErr(e, t('pagina_docs.error'))),
  });

  const updateMetaMutation = useMutation({
    mutationFn: (data: MetaForm) => documentsApi.update(documentId, data),
    onSuccess: () => {
      toast.success(t('pagina_docs.metadatos_actualizados'));
      qc.invalidateQueries({ queryKey: ['document', documentId] });
      qc.invalidateQueries({ queryKey: ['documents'] });
      setIsEditingMeta(false);
      cambiosGuardados();
      onRefresh();
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('pagina_docs.error_al_guardar'))),
  });

  const activeVer = previewVersion || doc?.versions?.[0] || null;
  const catS = doc ? (CAT_STYLE[doc.category] || CAT_STYLE.other) : null;

  useEffect(() => {
    if (!activeVer?.download_url) return;
    setPreviewError(false);
    // Only validate local API file URLs (S3 presigned URLs embed auth in query params)
    if (!activeVer.download_url.startsWith(`${PREFIJO_API_SERVIDOR}/`)) return;
    const fileType = detectFileType(activeVer.file_mime_type, activeVer.file_name);
    if (fileType !== 'pdf' && fileType !== 'image') return;
    // Por el cliente (refresco de sesión). La URL ya trae el prefijo de la API:
    // `baseURL: ''` evita que axios se lo añada otra vez.
    api.head(activeVer.download_url, { baseURL: '' })
      .catch(() => setPreviewError(true));
    // Faltaban file_mime_type y file_name (auditoría 2026-08, P1-6): el efecto
    // los usa para decidir el tipo, así que si cambiaban sin cambiar la URL la
    // comprobación se hacía con valores obsoletos.
  }, [activeVer?.download_url, activeVer?.file_mime_type, activeVer?.file_name]);

  return (
    <Drawer onClose={onClose} ariaLabel={doc?.title || t('pagina_docs.documento')} width={600} zIndex={900}>
        {isLoading ? (
          <div className="docs-row-20">
            <Loader size={18} className="docs-box-41" />{' '}{t('pagina_docs.cargando')}
          </div>
        ) : !doc ? (
          <div className="docs-row-21">{t('documents.documento_no_encontrado')}</div>
        ) : (
          <>
            {/* Drawer header */}
            <div className="docs-box-17">
              <div className="docs-row-22">
                <div className="u-flex1-min0">
                  <div className="docs-row-23">
                    <FileIcon mime={activeVer?.file_mime_type} name={activeVer?.file_name} size={38} />
                    <div className="u-flex1-min0">
                      <h2 className="docs-title">{doc.title}</h2>
                      {doc.description && <p className="docs-text">{doc.description}</p>}
                    </div>
                  </div>
                  <div className="docs-row-24">
                    <Chip text={etiquetaCategoria(t, doc.category)} color={catS!.c} bg={catS!.bg} />
                    {doc.requires_approval && <ChipAprobacion estado={doc.approval_status} />}
                    {doc.tags?.map(t => (
                      <span key={t} className="docs-label-4">#{t}</span>
                    ))}
                  </div>
                </div>
                <IconButton onClick={onClose} ariaLabel={t('pagina_docs.cerrar')} data-cierra-dialogo="">
                  <X size={18} />
                </IconButton>
              </div>

              {/* Action row */}
              <div className="u-wrap-8">
                {doc.requires_approval && doc.approval_status === 'pending' && !doc.approval_request && (
                  <Button size="sm" icon={<FileClock size={14} />}
                    onClick={() => submitApprovalMutation.mutate()}
                    loading={submitApprovalMutation.isPending}>
                    {submitApprovalMutation.isPending ? t('pagina_docs.enviando') : t('pagina_docs.enviar_para_aprobacion')}
                  </Button>
                )}
                {doc.requires_approval && doc.approval_status === 'rejected' && (
                  <Button size="sm" icon={<FileClock size={14} />}
                    onClick={() => submitApprovalMutation.mutate()}
                    loading={submitApprovalMutation.isPending}
                    title={t('documents.reabre_un_nuevo_flujo_de_aprobacion_el')}>
                    {submitApprovalMutation.isPending ? t('pagina_docs.reenviando') : t('pagina_docs.reenviar_a_aprobacion')}
                  </Button>
                )}
                {doc.requires_approval && doc.approval_status === 'pending' && doc.approval_request?.status === 'pending' && (
                  <>
                    <Button size="sm" icon={<CheckCircle size={14} />} onClick={() => approveMutation.mutate({ status: 'approved' })} disabled={approveMutation.isPending}>
                      {t('pagina_docs.aprobar_paso')}
                    </Button>
                    <Button size="sm" variant="danger" icon={<XCircle size={14} />} onClick={() => approveMutation.mutate({ status: 'rejected' })} disabled={approveMutation.isPending}>
                      {t('pagina_docs.rechazar')}
                    </Button>
                  </>
                )}
                {!reserva && (
                  <Button size="sm" variant="secondary" icon={<Lock size={14} />} onClick={() => reservaMutation.mutate('checkout')} disabled={reservaMutation.isPending}
                    title={t('documents.reserva_ayuda')}>
                    {t('documents.reservar')}
                  </Button>
                )}
                {reserva?.mine && (
                  <Button size="sm" variant="secondary" icon={<LockOpen size={14} />} onClick={() => reservaMutation.mutate('checkin')} disabled={reservaMutation.isPending}>
                    {t('documents.liberar')}
                  </Button>
                )}
                <Button size="sm" variant="secondary" icon={<Sparkles size={14} />} onClick={() => summaryMutation.mutate()} loading={summaryMutation.isPending}>
                  {summaryMutation.isPending ? t('pagina_docs.generando') : t('pagina_docs.resumen_ia')}
                </Button>
                {activeVer?.download_url && (
                  <a href={sanitizeUrl(activeVer.download_url)} target="_blank" rel="noreferrer"
                    className="docs-link-3">
                    <Download size={13} />{' '}{t('pagina_docs.descargar')}
                  </a>
                )}
              </div>
            </div>

            {deOtro && (
              <div role="status" className="docs-row-25">
                <Lock size={14} color="var(--warning)" />
                <span className="u-flex1">
                  {t('documents.reserva_aviso', { nombre: reserva?.user_name || '—', fecha: reserva?.expires_at ? fmtDateTime(reserva.expires_at) : '—' })}
                </span>
                <Button size="sm" variant="secondary" onClick={() => reservaMutation.mutate('force')} disabled={reservaMutation.isPending}>
                  {t('documents.reserva_forzar')}
                </Button>
              </div>
            )}

            {/* Tabs */}
            <div className="docs-row-26">
              <Tabs
                items={[
                  { id: 'preview', label: t('pagina_docs.vista_previa'), icon: <Eye size={14} /> },
                  { id: 'versions', label: t('pagina_docs.versiones'), icon: <History size={14} />, count: (doc.versions?.length ?? 0) > 0 ? doc.versions.length : undefined },
                  { id: 'meta', label: t('pagina_docs.metadatos'), icon: <Info size={14} /> },
                  { id: 'share', label: t('pagina_docs.compartir'), icon: <Share2 size={14} /> },
                ]}
                active={tab}
                onChange={setTab}
              />
            </div>

            {/* Tab content */}
            <div className="docs-box-18">

              {/* Preview */}
              {tab === 'preview' && activeVer?.download_url && (
                <div className="docs-card-5">
                  <div className="docs-row-27">
                    <span className="u-text3-xs">{activeVer.file_name} · {fmtBytes(activeVer.file_size)}</span>
                    <a href={sanitizeUrl(activeVer.download_url)} target="_blank" rel="noreferrer" className="docs-link-4">
                       <ExternalLink size={11} /> {t('documents.abrir_en_nueva_pestana')}
                    </a>
                  </div>
                  {(() => {
                    if (previewError) return (
                      <div className="docs-box-19">
                        <FileIcon mime={activeVer.file_mime_type} name={activeVer.file_name} size={56} />
                        <div className="docs-box-20">{t('documents.el_archivo_no_esta_disponible_en_el')}</div>
                        {activeVer.download_url && (
                          <a href={sanitizeUrl(activeVer.download_url)} target="_blank" rel="noreferrer"
                            className="docs-link-5">
                            <Download size={14} />{' '}{t('pagina_docs.intentar_descargar')}
                          </a>
                        )}
                      </div>
                    );
                    const type = detectFileType(activeVer.file_mime_type, activeVer.file_name);
                    if (type === 'pdf') return <iframe src={sanitizeUrl(activeVer.download_url)}className="docs-box-21" title={t('documents.vista_previa_del_pdf')} onError={() => setPreviewError(true)} />;
                    if (type === 'image') return <img src={sanitizeUrl(activeVer.download_url)} alt={activeVer.file_name} loading="lazy" decoding="async" className="docs-box-22" onError={() => setPreviewError(true)} />;
                    return (
                      <div className="docs-box-19">
                        <FileIcon mime={activeVer.file_mime_type} name={activeVer.file_name} size={56} />
                        <div className="docs-box-20">{t('documents.vista_previa_no_disponible_para_este_tipo')}</div>
                        <a href={sanitizeUrl(activeVer.download_url)} target="_blank" rel="noreferrer"
                          className="docs-link-5">
                          <Download size={14} /> {t('documents.descargar_para_ver')}
                        </a>
                      </div>
                    );
                  })()}
                </div>
              )}
              {tab === 'preview' && !activeVer?.download_url && (
                <EmptyState icon={<FolderOpen size={28} />} title={t('documents.este_documento_no_tiene_archivo_adjunto_todavia')} />
              )}

              {/* Versions */}
              {tab === 'versions' && (
                <div>
                  <div className="docs-stack-6">
                    {(doc.versions || []).map((v, i) => (
                      <div key={v.id}
                        onClick={() => { setPreviewVersion(v); setTab('preview'); }}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setPreviewVersion(v);
                            setTab('preview');
                          }
                        }}
                        className={`docs-row-28 document-sx24 ${activeVer?.id === v.id ? 'document-sx25' : 'document-sx18'} documents-page-e4`} style={{ '--documents-page-border': `1px solid ${activeVer?.id === v.id ? 'color-mix(in srgb, var(--accent) 25%, transparent)' : 'var(--surface-4)'}` } as CSSProperties}>
                        <div className={`docs-row-29 ${activeVer?.id === v.id ? 'document-sx26' : 'document-sx27'}`}>
                          v{v.version_num}
                        </div>
                        <div className="u-flex1-min0">
                          <div className="docs-box-8">{v.file_name}</div>
                          {v.change_note && <div className="docs-box-24">{v.change_note}</div>}
                          <div className="u-text3-2xs">{v.uploader_name} · {fmtDate(v.created_at)} · {fmtBytes(v.file_size)}</div>
                        </div>
                        {i === 0 && <span className="docs-label-5">{t('pagina_docs.actual')}</span>}
                        {v.download_url && (
                          <a href={sanitizeUrl(v.download_url)} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
                            className="docs-link-6">
                            <Download size={12} />
                          </a>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Upload new version */}
                  {!showUploadVersion ? (
                    <div className="docs-nueva-version">
                      <Button variant="secondary" icon={<Upload size={14} />} onClick={() => setShowUploadVersion(true)} disabled={deOtro}
                        title={deOtro ? t('documents.reserva_de', { nombre: reserva?.user_name || '—' }) : undefined}>
                        {t('documents.subir_nueva_version')}
                      </Button>
                    </div>
                  ) : (
                    <div className="docs-stack-7">
                      <div onClick={() => fileRef.current?.click()} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileRef.current?.click(); } }} className="docs-box-25 document-sx21 documents-page-e4" style={{ '--documents-page-border': `2px dashed ${file ? 'var(--success)' : 'var(--surface-5)'}` } as CSSProperties}>
                        {file ? <span className="u-text1-base-600">{file.name}</span>
                          : <span className="u-text3-sm"><Upload size={13} className="docs-box-42" />{t('documents.clic_para_seleccionar_archivo')}</span>}
                        <input ref={fileRef} type="file" aria-label={t('documents.clic_para_seleccionar_archivo')} className="docs-input" onChange={e => setFile(e.target.files?.[0] ?? null)} />
                      </div>
                      <Input placeholder={t('documents.nota_del_cambio')} value={changeNote} onChange={e => setChangeNote(e.target.value)} aria-label={t('documents.nota_del_cambio')} inputClassName="documents-page-e8" />
                      <div className="u-row-8">
                        <Button size="sm" icon={<Upload size={14} />} onClick={() => versionMutation.mutate()} disabled={!file} loading={versionMutation.isPending}>
                          {versionMutation.isPending ? t('pagina_docs.subiendo') : t('pagina_docs.subir')}
                        </Button>
                        <Button size="sm" variant="secondary" onClick={() => { setShowUploadVersion(false); setFile(null); setChangeNote(''); }}>
                          {t('pagina_docs.cancelar')}
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Metadata */}
              {tab === 'meta' && !isEditingMeta && (
                <div>
                  {/* AI Summary card */}
                  {doc.ai_summary && (
                    <div className="docs-card-6">
                      <div className="docs-row-30">
                        <Sparkles size={12} />{' '}{t('pagina_docs.resumen_ia')}
                      </div>
                      <div className="docs-box-26">{doc.ai_summary}</div>
                    </div>
                  )}
                  <div className="docs-grid-4">
                    {([
                      [t('pagina_docs.creado_por'), doc.created_by_name || '—'],
                      [t('pagina_docs.fecha_creacion'), fmtDate(doc.created_at)],
                      [t('pagina_docs.categoria'), etiquetaCategoria(t, doc.category)],
                      [t('pagina_docs.versiones'), doc.versions?.length || 1],
                      [t('pagina_docs.requiere_aprob'), doc.requires_approval ? t('pagina_docs.si') : t('pagina_docs.no')],
                      [t('pagina_docs.estado_aprob'), doc.approval_status ? t((APPROVAL_STYLE[doc.approval_status] || APPROVAL_STYLE.pending).label) : '—'],
                      doc.approved_by_name && [t('pagina_docs.aprobado_por'), doc.approved_by_name],
                      doc.approved_at && [t('pagina_docs.fecha_aprob'), fmtDate(doc.approved_at)],
                    ] as Array<[string, ReactNode] | null | undefined | ''>).filter((x): x is [string, ReactNode] => Boolean(x)).map(([k, v]) => (
                      <div key={k} className="docs-card-7">
                        <div className="docs-box-27">{k}</div>
                        <div className="u-text1-base-600">{v}</div>
                      </div>
                    ))}
                    {doc.description && (
                      <div className="docs-card-8">
                        <div className="docs-box-27">{t('documents.descripcion')}</div>
                        <div className="docs-box-28">{doc.description}</div>
                      </div>
                    )}
                    {(doc.tags?.length ?? 0) > 0 && (
                      <div className="docs-card-8">
                        <div className="docs-box-29">{t('pagina_docs.etiquetas')}</div>
                        <div className="docs-row-7">
                          {doc.tags.map(t => (
                            <span key={t} className="docs-label-6">#{t}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="docs-editar-meta">
                    <Button variant="secondary" icon={<Pencil size={14} />} onClick={() => {
                      setMetaForm({ title: doc.title || '', description: doc.description || '', category: doc.category || 'other', requires_approval: doc.requires_approval ?? false });
                      setIsEditingMeta(true);
                    }}>
                      {t('pagina_docs.editar_metadatos')}
                    </Button>
                  </div>
                </div>
              )}
                    {/* Approval workflow panel (solo en la pestaña de metadatos: salía en todas) */}
                    {tab === 'meta' && !isEditingMeta && doc.approval_request && (
                      <div className="docs-card-9">
                        <div className="docs-row-31">
                          <FileClock size={14} className="u-warning" />
                          {t('documents.flujo_de_aprobacion')} {doc.approval_request.workflow_name}
                        </div>
                        {/* Step indicator */}
                        <div className="docs-row-32">
                          {Array.from({ length: doc.approval_request.total_steps || 1 }, (_: unknown, i: number) => {
                            const stepNum = i + 1;
                            const isDone = stepNum < (doc.approval_request.current_step || 1);
                            const isCurrent = stepNum === (doc.approval_request.current_step || 1) && doc.approval_request.status === 'pending';
                            const isRejected = doc.approval_request.status === 'rejected';
                            const color = isDone ? 'var(--success)' : isCurrent ? 'var(--warning)' : isRejected && stepNum === doc.approval_request.current_step ? 'var(--danger)' : 'var(--surface-4)';
                            return (
                              <div key={stepNum} className="docs-row-33">
                                <div className={`docs-row-34 ${(isDone || isCurrent) ? 'document-sx30' : 'document-sx31'} documents-page-e3`} style={{ '--documents-page-background-color': color } as CSSProperties}>
                                  {isDone ? <Check size={12} aria-hidden /> : stepNum}
                                </div>
                                {stepNum < (doc.approval_request.total_steps || 1) && (
                                  <div className={`docs-box-30 ${isDone ? 'document-sx32' : 'document-sx33'}`} />
                                )}
                              </div>
                            );
                          })}
                          <span className="docs-label-7">
                            {t('pagina_docs.paso_x_de_y', { actual: doc.approval_request.current_step, total: doc.approval_request.total_steps })}
                          </span>
                        </div>
                        {/* Current step info */}
                        {doc.approval_request.status === 'pending' && doc.approval_request.current_step_name && (
                          <div className="docs-box-31">
                            <span className="docs-label-8">{doc.approval_request.current_step_name}</span>
                            {doc.approval_request.current_approver_name && (
                              <> {t('documents.pendiente_de')} <span className="u-accent">{doc.approval_request.current_approver_name}</span></>
                            )}
                            {!doc.approval_request.current_approver_name && doc.approval_request.current_approver_role && (
                              <> {t('documents.pendiente_de_rol')} <span className="u-accent">{etiquetaCodigo(t, 'rol_usuario', doc.approval_request.current_approver_role)}</span></>
                            )}
                          </div>
                        )}
                        {doc.approval_request.status === 'approved' && (
                          <div className="docs-box-32">{t('pagina_docs.aprobado_completamente')}</div>
                        )}
                        {doc.approval_request.status === 'rejected' && (
                          <div className="docs-box-33">{t('pagina_docs.rechazado')}</div>
                        )}
                        {/* Decisions trail */}
                        {(doc.approval_request.decisions?.length ?? 0) > 0 && (
                          <div className="docs-box-34">
                            <div className="docs-box-29">{t('documents.historial_de_decisiones')}</div>
                            {doc.approval_request.decisions.map((d, idx) => (
                              <div key={idx} className="docs-row-35">
                                <div className={`docs-row-36 ${d.decision === 'approved' ? 'document-sx34' : 'document-sx35'}`}>
                                  <span className={`docs-label-9 ${d.decision === 'approved' ? 'document-sx36' : 'document-sx37'}`}>{d.decision === 'approved' ? <Check size={10} aria-hidden /> : <X size={10} aria-hidden />}</span>
                                </div>
                                <div>
                                  <span className="docs-label-10">{d.approver_name || t('pagina_docs.desconocido')}</span>
                                  <span className="docs-label-11">{t('pagina_docs.paso')}{' '}{d.step_order} · {d.decided_at ? fmtDate(d.decided_at) : ''}</span>
                                  {d.note && <div className="docs-box-35">"{d.note}"</div>}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
              {tab === 'meta' && isEditingMeta && metaForm && (
                <div className="u-stack-14">
                  <Input label={t('documents.titulo')} id={`${idCampo}-1`} value={metaForm.title} onChange={e => setMetaForm(f => f && ({ ...f, title: e.target.value }))} />
                  <Textarea label={t('documents.descripcion')} id={`${idCampo}-2`} value={metaForm.description} onChange={e => setMetaForm(f => f && ({ ...f, description: e.target.value }))} rows={3} />
                  <Select label={t('documents.categoria')} placeholder={false} id={`${idCampo}-3`} value={metaForm.category} onChange={e => setMetaForm(f => f && ({ ...f, category: e.target.value }))}>
                      {CATS.map(c => <option key={c} value={c}>{etiquetaCategoria(t, c)}</option>)}
                    </Select>
                  <div className="u-row-center-10">
                    <Checkbox id="meta-req-approval" checked={metaForm.requires_approval} onChange={(_, e) => setMetaForm(f => f && ({ ...f, requires_approval: e.target.checked }))} className="docs-input-3" />
                    <label id="meta-req-approval-et" htmlFor="meta-req-approval" className="docs-label-13">{t('documents.requiere_aprobacion')}</label>
                  </div>
                  <div className="docs-row-37">
                    <Button variant="secondary" onClick={() => setIsEditingMeta(false)}>{t('pagina_docs.cancelar')}</Button>
                    <Button onClick={() => updateMetaMutation.mutate(metaForm)} disabled={!metaForm.title} loading={updateMetaMutation.isPending}>
                      {updateMetaMutation.isPending ? t('pagina_docs.guardando') : t('pagina_docs.guardar')}
                    </Button>
                  </div>
                </div>
              )}

              {/* Share */}
              {tab === 'share' && <SharePanel documentId={documentId} />}
            </div>
          </>
        )}
    </Drawer>
  );
}
