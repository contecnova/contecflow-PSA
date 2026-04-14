/**
 * DocumentViewer  Visor de documentos rediseV3ado. 
 * Vista previa inline, historial de versiones, flujo de aprobación, resumen IA.
 * Usado como componente standalone (en modales, en DocumentsPage drawer, etc.)
 */
import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { useToast } from '../context/ToastContext';
import {
  Upload, Download, CheckCircle, XCircle, History,
  ChevronDown, ChevronUp, Eye, Sparkles, Loader, ExternalLink
} from 'lucide-react';

function fmtBytes(b) {
  if (!b) return '';
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}

function fmtDate(d) {
  if (!d) return '';
  return new Date(d).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });
}

const FILE_COLORS = {
  pdf: { c: '#ef4444', bg: '#ef444418', l: 'PDF' },
  image: { c: '#3b82f6', bg: '#3b82f618', l: 'IMG' },
  spreadsheet: { c: '#10b981', bg: '#10b98118', l: 'XLS' },
  word: { c: '#6366f1', bg: '#6366f118', l: 'DOC' },
  presentation: { c: '#f59e0b', bg: '#f59e0b18', l: 'PPT' },
  archive: { c: '#8b5cf6', bg: '#8b5cf618', l: 'ZIP' },
  text: { c: '#64748b', bg: '#64748b18', l: 'TXT' },
  other: { c: '#6b7280', bg: '#6b728018', l: 'FILE' },
};

function detectType(mime, name) {
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

function FileIcon({ mime, name, size = 36 }) {
  const ft = FILE_COLORS[detectType(mime, name)];
  return (
    <div style={{
      width: size, height: size, borderRadius: Math.round(size * 0.22),
      backgroundColor: ft.bg, display: 'flex', alignItems: 'center',
      justifyContent: 'center', flexShrink: 0,
      fontFamily: "'Space Mono', monospace", fontSize: Math.round(size * 0.23),
      fontWeight: 700, color: ft.c, letterSpacing: '-0.03em',
    }}>
      {ft.l}
    </div>
  );
}

const CAT_STYLE = {
  contract: { c: '#3b82f6', bg: '#3b82f615' }, deliverable: { c: '#10b981', bg: '#10b98115' },
  proposal: { c: '#8b5cf6', bg: '#8b5cf615' }, sop: { c: '#f59e0b', bg: '#f59e0b15' },
  legal: { c: '#ef4444', bg: '#ef444415' }, requirements: { c: '#06b6d4', bg: '#06b6d415' },
  report: { c: '#f97316', bg: '#f9731615' }, presentation: { c: '#ec4899', bg: '#ec489915' },
  other: { c: '#6b7280', bg: '#6b728015' },
};

const DocumentViewer = ({ documentId }) => {
  const toast = useToast();
  const qc = useQueryClient();
  const fileRef = useRef();
  const [previewVer, setPreviewVer] = useState(null);
  const [showVersions, setShowVersions] = useState(true);
  const [showUploadForm, setShowUploadForm] = useState(false);
  const [file, setFile] = useState(null);
  const [changeNote, setChangeNote] = useState('');

  const { data: doc, isLoading } = useQuery({
    queryKey: ['document', documentId],
    queryFn: async () => {
      const res = await axios.get(`/api/v1/documents/${documentId}`);
      const d = res.data;
      if (d.versions) d.versions = d.versions.map(v => ({ ...v, download_url: v.download_url || v.s3_url }));
      return d;
    },
    onSuccess: d => { if (d.versions?.length && !previewVer) setPreviewVer(d.versions[0]); },
  });

  const uploadMutation = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      fd.append('file', file);
      if (changeNote) fd.append('change_note', changeNote);
      return axios.post(`/api/v1/documents/${documentId}/versions`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
    },
    onSuccess: () => {
      toast.success('Nueva versión subida');
      qc.invalidateQueries({ queryKey: ['document', documentId] });
      setFile(null); setChangeNote(''); setShowUploadForm(false);
    },
    onError: e => toast.error(e.response?.data?.detail || 'Error'),
  });

  const approveMutation = useMutation({
    mutationFn: status => axios.post(`/api/v1/documents/${documentId}/approve`, { status }),
    onSuccess: (_, s) => {
      toast.success(s === 'approved' ? 'Documento aprobado' : 'Documento rechazado');
      qc.invalidateQueries({ queryKey: ['document', documentId] });
    },
    onError: e => toast.error(e.response?.data?.detail || 'Error'),
  });

  const summaryMutation = useMutation({
    mutationFn: () => axios.post(`/api/v1/documents/${documentId}/ai-summary`),
    onSuccess: () => { toast.success('Resumen IA generado'); qc.invalidateQueries({ queryKey: ['document', documentId] }); },
    onError: e => toast.error(e.response?.data?.detail || 'Error IA'),
  });

  if (isLoading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '40px 20px', color: 'var(--text-3)', fontSize: 13, gap: 8 }}>
      <Loader size={16} style={{ animation: 'spin 0.8s linear infinite' }} /> Cargando documento
    </div>
  );
  if (!doc) return (
    <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--danger)', fontSize: 13 }}>Documento no encontrado</div>
  );

  const activeVer = previewVer || doc.versions?.[0] || null;
  const versions = doc.versions || [];
  const catS = CAT_STYLE[doc.category] || CAT_STYLE.other;
  const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' };

  return (
    <div style={{ padding: '22px 24px', display: 'flex', flexDirection: 'column', gap: 18, color: 'var(--text-1)' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 14 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <FileIcon mime={activeVer?.file_mime_type} name={activeVer?.file_name} size={40} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <h2 style={{ fontSize: 17, fontWeight: 800, color: 'var(--text-1)', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.title}</h2>
              {doc.description && <p style={{ fontSize: 12, color: 'var(--text-3)', margin: '3px 0 0' }}>{doc.description}</p>}
            </div>
          </div>

          {/* Badges */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20, backgroundColor: catS.bg, color: catS.c, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              {doc.category}
            </span>
            {doc.approval_status === 'approved' && (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20, backgroundColor: '#10b98115', color: '#10b981' }}>
                <CheckCircle size={9} /> Aprobado
              </span>
            )}
            {doc.requires_approval && doc.approval_status === 'pending' && (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20, backgroundColor: '#f59e0b15', color: '#f59e0b' }}>
               ⏳ Pendiente aprobación
              </span>
            )}
            {doc.tags?.map(t => (
              <span key={t} style={{ fontSize: 10, padding: '2px 7px', borderRadius: 10, backgroundColor: 'var(--surface-3)', color: 'var(--text-3)' }}>#{t}</span>
            ))}
          </div>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, flexShrink: 0 }}>
          {doc.requires_approval && doc.approval_status === 'pending' && (
            <>
              <button onClick={() => approveMutation.mutate('approved')}
                style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '7px 14px', borderRadius: 8, border: 'none', backgroundColor: '#10b981', color: 'white', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
                <CheckCircle size={13} /> Aprobar
              </button>
              <button onClick={() => approveMutation.mutate('rejected')}
                style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '7px 14px', borderRadius: 8, border: 'none', backgroundColor: 'var(--danger)', color: 'white', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
                <XCircle size={13} /> Rechazar
              </button>
            </>
          )}
          <button onClick={() => summaryMutation.mutate()} disabled={summaryMutation.isPending}
            style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--purple)', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
            <Sparkles size={13} />
            {summaryMutation.isPending ? '' : 'Resumen IA'}Generando
          </button>
          {activeVer?.download_url && (
            <a href={activeVer.download_url} target="_blank" rel="noreferrer"
              style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '7px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--text-2)', fontSize: 12, fontWeight: 600, textDecoration: 'none' }}>
              <Download size={13} /> Descargar
            </a>
          )}
        </div>
      </div>

      {/* Inline Preview */}
      {activeVer?.download_url && (
        <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid var(--surface-4)' }}>
          <div style={{ padding: '8px 14px', backgroundColor: 'var(--surface-2)', borderBottom: '1px solid var(--surface-4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 11, color: 'var(--text-3)', display: 'flex', alignItems: 'center', gap: 5 }}>
              <Eye size={11} /> {activeVer.file_name}  {fmtBytes(activeVer.file_size)}
            </span>
            <a href={activeVer.download_url} target="_blank" rel="noreferrer"
              style={{ fontSize: 11, color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 4, textDecoration: 'none' }}>
               <ExternalLink size={11} /> Abrir en nueva pestaña
            </a>
          </div>
          {(() => {
            const type = detectType(activeVer.file_mime_type, activeVer.file_name);
            if (type === 'pdf') return <iframe src={activeVer.download_url} style={{ width: '100%', height: 480, border: 'none', display: 'block' }} title="Vista previa" />;
            if (type === 'image') return <img src={activeVer.download_url} alt={activeVer.file_name} style={{ maxWidth: '100%', maxHeight: 400, objectFit: 'contain', display: 'block', margin: '0 auto', padding: 16 }} />;
            return (
              <div style={{ padding: 36, textAlign: 'center' }}>
                <FileIcon mime={activeVer.file_mime_type} name={activeVer.file_name} size={52} />
                <div style={{ marginTop: 12, fontSize: 13, color: 'var(--text-3)' }}>Vista previa no disponible para este tipo de archivo</div>
                <a href={activeVer.download_url} target="_blank" rel="noreferrer"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 12, padding: '8px 16px', borderRadius: 8, backgroundColor: 'var(--accent)', color: 'white', textDecoration: 'none', fontSize: 13, fontWeight: 700 }}>
                  <Download size={14} /> Descargar para ver
                </a>
              </div>
            );
          })()}
        </div>
      )}

      {/* Version history */}
      <div style={{ borderRadius: 10, border: '1px solid var(--surface-4)', overflow: 'hidden' }}>
        <button onClick={() => setShowVersions(s => !s)}
          style={{ width: '100%', padding: '11px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: 'var(--surface-2)', border: 'none', cursor: 'pointer', color: 'var(--text-1)', fontSize: 13, fontWeight: 700, fontFamily: 'inherit' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <History size={14} style={{ color: 'var(--text-2)' }} /> Historial de versiones ({versions.length})
          </span>
          {showVersions ? <ChevronUp size={14} style={{ color: 'var(--text-3)' }} /> : <ChevronDown size={14} style={{ color: 'var(--text-3)' }} />}
        </button>

        {showVersions && (
          <div>
            {versions.map((v, i) => (
              <div key={v.id}
                onClick={() => setPreviewVer(v)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '11px 14px', cursor: 'pointer',
                  borderTop: '1px solid var(--surface-4)', transition: 'background 0.1s',
                  backgroundColor: activeVer?.id === v.id ? 'var(--surface-2)' : 'transparent',
                }}>
                <div style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: activeVer?.id === v.id ? 'var(--accent)' : 'var(--surface-3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Space Mono', monospace", fontSize: 11, fontWeight: 700, color: activeVer?.id === v.id ? 'white' : 'var(--text-2)', flexShrink: 0 }}>
                  v{v.version_num}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v.file_name}</div>
                  {v.change_note && <div style={{ fontSize: 11, color: 'var(--text-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v.change_note}</div>}
                  <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{v.uploader_name}  {fmtDate(v.created_at)}  {fmtBytes(v.file_size)}</div>
                </div>
                {i === 0 && <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 10, backgroundColor: 'var(--accent)20', color: 'var(--accent)', fontWeight: 700, flexShrink: 0 }}>Actual</span>}
                {v.download_url && (
                  <a href={v.download_url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
                    style={{ width: 26, height: 26, borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--surface-3)', color: 'var(--text-2)', textDecoration: 'none', flexShrink: 0 }}>
                    <Download size={12} />
                  </a>
                )}
              </div>
            ))}

            {/* Upload new version */}
            <div style={{ borderTop: '1px solid var(--surface-4)', padding: 14 }}>
              {!showUploadForm ? (
                <button onClick={() => setShowUploadForm(true)}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600, color: 'var(--accent)', background: 'none', border: '1px dashed var(--surface-5)', borderRadius: 8, padding: '8px 14px', cursor: 'pointer', fontFamily: 'inherit', width: '100%', justifyContent: 'center' }}>
                   <Upload size={13} /> Subir nueva versión
                </button>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div onClick={() => fileRef.current?.click()}
                    style={{ border: `2px dashed ${file ? '#10b981' : 'var(--surface-5)'}`, borderRadius: 8, padding: '10px 14px', textAlign: 'center', cursor: 'pointer' }}>
                    {file ? <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)' }}>{file.name}</span>
                      : <span style={{ fontSize: 12, color: 'var(--text-3)' }}><Upload size={12} style={{ display: 'inline', marginRight: 4 }} />Clic para seleccionar</span>}
                    <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={e => setFile(e.target.files?.[0])} />
                  </div>
                  <input placeholder="Nota del cambio (opcional)" value={changeNote} onChange={e => setChangeNote(e.target.value)} style={fs} />
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={() => uploadMutation.mutate()} disabled={!file || uploadMutation.isPending}
                      style={{ flex: 1, padding: '8px', borderRadius: 8, border: 'none', backgroundColor: !file ? 'var(--surface-4)' : 'var(--accent)', color: !file ? 'var(--text-3)' : 'white', fontSize: 13, fontWeight: 700, cursor: !file ? 'not-allowed' : 'pointer', fontFamily: 'inherit' }}>
                       {uploadMutation.isPending ? 'Subiendo...' : 'Subir versión'}
                    </button>
                    <button onClick={() => { setShowUploadForm(false); setFile(null); setChangeNote(''); }}
                      style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', backgroundColor: 'transparent', color: 'var(--text-2)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>
                      Cancelar
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
          ['Creado por', doc.created_by_name || ''],
          ['Fecha creación', fmtDate(doc.created_at)],
          ['Categor', doc.category],
          ['Versiones', versions.length],
          doc.approved_by_name && ['Aprobado por', doc.approved_by_name],
          doc.approved_at && ['Fecha aprobación', fmtDate(doc.approved_at)],
        ].filter(Boolean).map(([k, v]) => (
          <div key={k} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px' }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>{k}</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)' }}>{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default DocumentViewer;
