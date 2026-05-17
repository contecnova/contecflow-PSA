/**
 * DocumentViewer  Visor de documentos rediseV3ado. 
 * Vista previa inline, historial de versiones, flujo de aprobación, resumen IA.
 * Usado como componente standalone (en modales, en DocumentsPage drawer, etc.)
 */
import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { documentsApi } from '../services/api';
import { useToast } from '../context/ToastContext';
import { useAppT } from '../i18n/AppLangContext';
import {
  Upload, Download, CheckCircle, XCircle, History,
  ChevronDown, ChevronUp, Eye, Sparkles, Loader, ExternalLink
} from 'lucide-react';
import type { CSSProperties, ChangeEvent } from 'react';

type DocCategory = 'contract' | 'deliverable' | 'proposal' | 'sop' | 'legal' | 'requirements' | 'report' | 'presentation' | 'other'

interface DocumentVersion {
  id: string | number
  version_num?: number
  file_name?: string
  file_mime_type?: string
  file_size?: number
  created_at?: string
  uploader_name?: string
  change_note?: string
  download_url?: string
  s3_url?: string
}

interface DocumentDetail {
  id: string | number
  title?: string
  description?: string
  category?: DocCategory
  approval_status?: string
  requires_approval?: boolean
  tags?: string[]
  created_by_name?: string
  created_at?: string
  approved_by_name?: string
  approved_at?: string
  versions?: DocumentVersion[]
}

interface TeamsErrorLike {
  response?: { data?: { detail?: string } }
}

function fmtBytes(b?: number) {
  if (!b) return '';
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}

function fmtDate(d?: string) {
  if (!d) return '';
  return new Date(d).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });
}

const FILE_COLORS = {
  pdf:         { c: 'var(--danger)',  bg: 'color-mix(in srgb, var(--danger) 9%, transparent)',  l: 'PDF' },
  image:       { c: 'var(--accent)',  bg: 'color-mix(in srgb, var(--accent) 9%, transparent)',  l: 'IMG' },
  spreadsheet: { c: 'var(--success)', bg: 'color-mix(in srgb, var(--success) 9%, transparent)', l: 'XLS' },
  word:        { c: 'var(--accent)',  bg: 'color-mix(in srgb, var(--accent) 9%, transparent)',  l: 'DOC' },
  presentation:{ c: 'var(--warning)', bg: 'color-mix(in srgb, var(--warning) 9%, transparent)', l: 'PPT' },
  archive:     { c: 'var(--purple)',  bg: 'color-mix(in srgb, var(--purple) 9%, transparent)',  l: 'ZIP' },
  text:        { c: 'var(--text-3)',  bg: 'color-mix(in srgb, var(--text-3) 9%, transparent)',  l: 'TXT' },
  other:       { c: 'var(--text-3)',  bg: 'color-mix(in srgb, var(--text-3) 9%, transparent)',  l: 'FILE' },
};

function detectType(mime?: string, name?: string): keyof typeof FILE_COLORS {
  const ext = (name || '').split('.').pop()?.toLowerCase();
  if (mime?.startsWith('image/')) return 'image';
  if (mime === 'application/pdf' || ext === 'pdf') return 'pdf';
  if (mime?.includes('spreadsheet') || mime?.includes('excel') || ['xls','xlsx','csv'].includes(ext)) return 'spreadsheet';
  if (mime?.includes('word') || ['doc','docx'].includes(ext)) return 'word';
  if (mime?.includes('presentation') || ['ppt','pptx'].includes(ext)) return 'presentation';
  if (['zip','tar','gz','rar'].includes(ext)) return 'archive';
  if (mime?.startsWith('text/') || ['txt','md'].includes(ext)) return 'text';
  return 'other';
}

function FileIcon({ mime, name, size = 36 }: { mime?: string; name?: string; size?: number }) {
  const ft = FILE_COLORS[detectType(mime, name)];
  return (
    <div style={{
      width: size, height: size, borderRadius: Math.round(size * 0.22),
      backgroundColor: ft.bg, display: 'flex', alignItems: 'center',
      justifyContent: 'center', flexShrink: 0,
      fontFamily: 'var(--font-mono)', fontSize: Math.round(size * 0.23),
      fontWeight: 700, color: ft.c, letterSpacing: '-0.03em',
    }}>
      {ft.l}
    </div>
  );
}

const CAT_STYLE = {
  contract:     { c: 'var(--accent)',  bg: 'color-mix(in srgb, var(--accent) 8%, transparent)' },
  deliverable:  { c: 'var(--success)', bg: 'color-mix(in srgb, var(--success) 8%, transparent)' },
  proposal:     { c: 'var(--purple)',  bg: 'color-mix(in srgb, var(--purple) 8%, transparent)' },
  sop:          { c: 'var(--warning)', bg: 'color-mix(in srgb, var(--warning) 8%, transparent)' },
  legal:        { c: 'var(--danger)',  bg: 'color-mix(in srgb, var(--danger) 8%, transparent)' },
  requirements: { c: 'var(--info)',    bg: 'color-mix(in srgb, var(--info) 8%, transparent)' },
  report:       { c: 'var(--orange)',  bg: 'color-mix(in srgb, var(--orange) 8%, transparent)' },
  presentation: { c: 'var(--coral)',   bg: 'color-mix(in srgb, var(--coral) 8%, transparent)' },
  other:        { c: 'var(--text-3)',  bg: 'color-mix(in srgb, var(--text-3) 8%, transparent)' },
};

const DocumentViewer = ({ documentId }: { documentId: string | number }) => {
  const toast = useToast();
  const t = useAppT();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [previewVer, setPreviewVer] = useState<DocumentVersion | null>(null);
  const [showVersions, setShowVersions] = useState(true);
  const [showUploadForm, setShowUploadForm] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [changeNote, setChangeNote] = useState('');

  const { data: doc, isLoading } = useQuery<DocumentDetail | null>({
    queryKey: ['document', documentId],
    queryFn: async () => {
      const res = await documentsApi.get(documentId);
      const d = res.data as DocumentDetail;
      if (d.versions) d.versions = d.versions.map(v => ({ ...v, download_url: v.download_url || v.s3_url }));
      return d;
    },
    onSuccess: (d) => { if (d?.versions?.length && !previewVer) setPreviewVer(d.versions[0]); },
  });

  const uploadMutation = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      fd.append('file', file);
      if (changeNote) fd.append('change_note', changeNote);
      return documentsApi.addVersion(documentId, fd);
    },
    onSuccess: () => {
      toast.success(t('document_viewer.uploaded_version'));
      qc.invalidateQueries({ queryKey: ['document', documentId] });
      setFile(null); setChangeNote(''); setShowUploadForm(false);
    },
    onError: (e: unknown) => toast.error((e as TeamsErrorLike).response?.data?.detail || t('common.error')),
  });

  const approveMutation = useMutation({
    mutationFn: (status: string) => documentsApi.approve(documentId, { status }),
    onSuccess: (_, s: string) => {
      toast.success(s === 'approved' ? t('document_viewer.approve_success') : t('document_viewer.reject_success'));
      qc.invalidateQueries({ queryKey: ['document', documentId] });
    },
    onError: (e: unknown) => toast.error((e as TeamsErrorLike).response?.data?.detail || t('common.error')),
  });

  const summaryMutation = useMutation({
    mutationFn: () => documentsApi.aiSummary(documentId),
    onSuccess: () => { toast.success(t('document_viewer.ai_summary_success')); qc.invalidateQueries({ queryKey: ['document', documentId] }); },
    onError: (e: unknown) => toast.error((e as TeamsErrorLike).response?.data?.detail || t('document_viewer.ai_error')),
  });

  if (isLoading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '40px 20px', color: 'var(--text-3)', fontSize: "var(--text-base)", gap: 8 }}>
      <Loader size={16} style={{ animation: 'spin 0.8s linear infinite' }} /> {t('document_viewer.loading')}
    </div>
  );
  if (!doc) return (
    <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--danger)', fontSize: "var(--text-base)" }}>{t('document_viewer.not_found')}</div>
  );

  const activeVer = previewVer || doc.versions?.[0] || null;
  const versions = doc.versions || [];
  const catS = CAT_STYLE[doc.category || 'other'] || CAT_STYLE.other;
  const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' };

  return (
    <div style={{ padding: '22px 24px', display: 'flex', flexDirection: 'column', gap: 18, color: 'var(--text-1)' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 14 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <FileIcon mime={activeVer?.file_mime_type} name={activeVer?.file_name} size={40} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <h2 style={{ fontSize: "var(--text-17)", fontWeight: 800, color: 'var(--text-1)', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.title}</h2>
              {doc.description && <p style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', margin: '3px 0 0' }}>{doc.description}</p>}
            </div>
          </div>

          {/* Badges */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', fontSize: "var(--text-2xs)", fontWeight: 700, padding: '2px 8px', borderRadius: 20, backgroundColor: catS.bg, color: catS.c, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              {doc.category}
            </span>
            {doc.approval_status === 'approved' && (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: "var(--text-2xs)", fontWeight: 700, padding: '2px 8px', borderRadius: 20, backgroundColor: 'color-mix(in srgb, var(--success) 8%, transparent)', color: 'var(--success)' }}>
                <CheckCircle size={9} /> {t('document_viewer.approved')}
              </span>
            )}
            {doc.requires_approval && doc.approval_status === 'pending' && (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: "var(--text-2xs)", fontWeight: 700, padding: '2px 8px', borderRadius: 20, backgroundColor: 'color-mix(in srgb, var(--warning) 8%, transparent)', color: 'var(--warning)' }}>
               {t('document_viewer.pending_approval')}
              </span>
            )}
            {doc.tags?.map((tag) => (
              <span key={tag} style={{ fontSize: "var(--text-2xs)", padding: '2px 7px', borderRadius: 10, backgroundColor: 'var(--surface-3)', color: 'var(--text-3)' }}>#{tag}</span>
            ))}
          </div>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, flexShrink: 0 }}>
          {doc.requires_approval && doc.approval_status === 'pending' && (
            <>
              <button onClick={() => approveMutation.mutate('approved')}
                style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '7px 14px', borderRadius: 8, border: 'none', backgroundColor: 'var(--success)', color: 'white', fontSize: "var(--text-sm)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
                <CheckCircle size={13} /> {t('document_viewer.approve')}
              </button>
              <button onClick={() => approveMutation.mutate('rejected')}
                style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '7px 14px', borderRadius: 8, border: 'none', backgroundColor: 'var(--danger)', color: 'white', fontSize: "var(--text-sm)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
                <XCircle size={13} /> {t('document_viewer.reject')}
              </button>
            </>
          )}
          <button onClick={() => summaryMutation.mutate()} disabled={summaryMutation.isPending}
            style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--purple)', fontSize: "var(--text-sm)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
            <Sparkles size={13} />
            {summaryMutation.isPending ? t('document_viewer.generating') : t('document_viewer.ai_summary')}
          </button>
          {activeVer?.download_url && (
            <a href={activeVer.download_url} target="_blank" rel="noreferrer"
              style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--text-2)', fontSize: "var(--text-sm)", fontWeight: 600, textDecoration: 'none' }}>
              <Download size={13} /> {t('document_viewer.download')}
            </a>
          )}
        </div>
      </div>

      {/* Inline Preview */}
      {activeVer?.download_url && (
        <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid var(--surface-4)' }}>
          <div style={{ padding: '8px 14px', backgroundColor: 'var(--surface-2)', borderBottom: '1px solid var(--surface-4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', display: 'flex', alignItems: 'center', gap: 5 }}>
              <Eye size={11} /> {activeVer.file_name}  {fmtBytes(activeVer.file_size)}
            </span>
            <a href={activeVer.download_url} target="_blank" rel="noreferrer"
              style={{ fontSize: "var(--text-xs)", color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 4, textDecoration: 'none' }}>
               <ExternalLink size={11} /> {t('document_viewer.open_new_tab')}
            </a>
          </div>
          {(() => {
            const type = detectType(activeVer.file_mime_type, activeVer.file_name);
            if (type === 'pdf') return <iframe src={activeVer.download_url} style={{ width: '100%', height: 480, border: 'none', display: 'block' }} title="Vista previa" />;
            if (type === 'image') return <img src={activeVer.download_url} alt={activeVer.file_name} loading="lazy" decoding="async" style={{ maxWidth: '100%', maxHeight: 400, objectFit: 'contain', display: 'block', margin: '0 auto', padding: 16 }} />;
            return (
              <div style={{ padding: 36, textAlign: 'center' }}>
                <FileIcon mime={activeVer.file_mime_type} name={activeVer.file_name} size={52} />
                <div style={{ marginTop: 12, fontSize: "var(--text-base)", color: 'var(--text-3)' }}>{t('document_viewer.preview_unavailable')}</div>
                <a href={activeVer.download_url} target="_blank" rel="noreferrer"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 12, padding: '8px 16px', borderRadius: 8, backgroundColor: 'var(--accent)', color: 'white', textDecoration: 'none', fontSize: "var(--text-base)", fontWeight: 700 }}>
                  <Download size={14} /> {t('document_viewer.download_to_view')}
                </a>
              </div>
            );
          })()}
        </div>
      )}

      {/* Version history */}
      <div style={{ borderRadius: 10, border: '1px solid var(--surface-4)', overflow: 'hidden' }}>
        <button onClick={() => setShowVersions(s => !s)}
          style={{ width: '100%', padding: '11px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: 'var(--surface-2)', border: 'none', cursor: 'pointer', color: 'var(--text-1)', fontSize: "var(--text-base)", fontWeight: 700, fontFamily: 'inherit' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <History size={14} style={{ color: 'var(--text-2)' }} /> {t('document_viewer.versions_history')} ({versions.length})
          </span>
          {showVersions ? <ChevronUp size={14} style={{ color: 'var(--text-3)' }} /> : <ChevronDown size={14} style={{ color: 'var(--text-3)' }} />}
        </button>

        {showVersions && (
          <div>
            {versions.map((v, i) => (
              <button key={v.id}
                onClick={() => setPreviewVer(v)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '11px 14px', cursor: 'pointer',
                  borderTop: '1px solid var(--surface-4)', transition: 'background 0.1s',
                  backgroundColor: activeVer?.id === v.id ? 'var(--surface-2)' : 'transparent',
                  width: '100%',
                  borderLeft: 'none',
                  borderRight: 'none',
                  textAlign: 'left',
                }}>
                <div style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: activeVer?.id === v.id ? 'var(--accent)' : 'var(--surface-3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-mono)', fontSize: "var(--text-xs)", fontWeight: 700, color: activeVer?.id === v.id ? 'white' : 'var(--text-2)', flexShrink: 0 }}>
                  v{v.version_num}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v.file_name}</div>
                  {v.change_note && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v.change_note}</div>}
                  <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>{v.uploader_name}  {fmtDate(v.created_at)}  {fmtBytes(v.file_size)}</div>
                </div>
                {i === 0 && <span style={{ fontSize: "var(--text-2xs)", padding: '2px 8px', borderRadius: 10, backgroundColor: 'var(--accent)20', color: 'var(--accent)', fontWeight: 700, flexShrink: 0 }}>{t('document_viewer.current')}</span>}
                {v.download_url && (
                  <a href={v.download_url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
                    style={{ width: 26, height: 26, borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', color: 'var(--text-2)', textDecoration: 'none', flexShrink: 0 }}>
                    <Download size={12} />
                  </a>
                )}
              </button>
            ))}

            {/* Upload new version */}
            <div style={{ borderTop: '1px solid var(--surface-4)', padding: 14 }}>
              {!showUploadForm ? (
                <button onClick={() => setShowUploadForm(true)}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--accent)', background: 'none', border: '1px dashed var(--surface-5)', borderRadius: 8, padding: '8px 14px', cursor: 'pointer', fontFamily: 'inherit', width: '100%', justifyContent: 'center' }}>
                   <Upload size={13} /> {t('document_viewer.upload_new_version')}
                </button>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <button type="button" onClick={() => fileRef.current?.click()}
                    style={{ border: `2px dashed ${file ? 'var(--success)' : 'var(--surface-5)'}`, borderRadius: 8, padding: '10px 14px', textAlign: 'center', cursor: 'pointer' }}>
                    {file ? <span style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)' }}>{file.name}</span>
                      : <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}><Upload size={12} style={{ display: 'inline', marginRight: 4 }} />{t('document_viewer.click_select_file')}</span>}
                    <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={(e: ChangeEvent<HTMLInputElement>) => setFile(e.target.files?.[0] || null)} />
                  </button>
                  <input placeholder={t('document_viewer.change_note_placeholder')} value={changeNote} onChange={e => setChangeNote(e.target.value)} style={fs} />
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={() => uploadMutation.mutate()} disabled={!file || uploadMutation.isPending}
                      style={{ flex: 1, padding: '8px', borderRadius: 8, border: 'none', backgroundColor: !file ? 'var(--surface-4)' : 'var(--accent)', color: !file ? 'var(--text-3)' : 'white', fontSize: "var(--text-base)", fontWeight: 700, cursor: !file ? 'not-allowed' : 'pointer', fontFamily: 'inherit' }}>
                       {uploadMutation.isPending ? t('common.saving') : t('document_viewer.upload_version')}
                    </button>
                    <button onClick={() => { setShowUploadForm(false); setFile(null); setChangeNote(''); }}
                      style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--text-2)', fontSize: "var(--text-base)", cursor: 'pointer', fontFamily: 'inherit' }}>
                      {t('common.cancel')}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Metadata */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        {[
          [t('document_viewer.created_by'), doc.created_by_name || ''],
          [t('document_viewer.created_date'), fmtDate(doc.created_at)],
          [t('document_viewer.category'), doc.category],
          [t('document_viewer.versions'), versions.length],
          doc.approved_by_name && [t('document_viewer.approved_by'), doc.approved_by_name],
          doc.approved_at && [t('document_viewer.approved_date'), fmtDate(doc.approved_at)],
        ].filter(Boolean).map(([k, v]) => (
          <div key={k} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px' }}>
            <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>{k}</div>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)' }}>{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default DocumentViewer;
