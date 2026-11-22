/**
 * DocumentsPanel — panel embebible de documentos (proyecto, tarea, ticket) 
 * Integra el sistema visual de Contecflow. Props: projectId?, taskId?, ticketId?, compact?
 */
import _React, { type CSSProperties, useState, useRef, useCallback } from 'react';
import { openConfirmGlobal } from '../context/ConfirmContext';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { documentsApi } from '../services/api';
import { useToast } from '../context/ToastContext';
import { extractErr } from '../utils/helpers';
import { Upload, Download, Trash2, Plus, Sparkles, Loader, X, Check, Clock, FileText } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Button, EmptyState, IconButton, Pulsable, Select, Input } from './ui';
import { useAppT } from '../hooks/useAppT';

import type { DragEvent } from 'react';
import './DocumentsPanel.css'
import { useAppLang } from '../i18n/AppLangContext'
import { px } from '../utils/estilos'

function fmtBytes(b: number | null | undefined) {
  if (!b) return '';
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}

const FILE_COLORS = {
  pdf:         { c: 'var(--danger)',  bg: 'color-mix(in srgb, var(--danger) 9%, transparent)',  l: 'PDF' },
  image:       { c: 'var(--accent)',  bg: 'color-mix(in srgb, var(--accent) 9%, transparent)',  l: 'IMG' },
  spreadsheet: { c: 'var(--success)', bg: 'color-mix(in srgb, var(--success) 9%, transparent)', l: 'XLS' },
  word:        { c: 'var(--accent)',  bg: 'color-mix(in srgb, var(--accent) 9%, transparent)',  l: 'DOC' },
  presentation:{ c: 'var(--warning)', bg: 'color-mix(in srgb, var(--warning) 9%, transparent)', l: 'PPT' },
  other:       { c: 'var(--text-3)', bg: 'color-mix(in srgb, var(--text-3) 9%, transparent)',   l: 'FILE' },
};

function detectType(mime: string | null | undefined, name: string | null | undefined): keyof typeof FILE_COLORS {
  const ext = (name || '').split('.').pop()?.toLowerCase() ?? '';
  if (mime?.startsWith('image/')) return 'image';
  if (mime === 'application/pdf' || ext === 'pdf') return 'pdf';
  if (mime?.includes('spreadsheet') || mime?.includes('excel') || ['xls','xlsx','csv'].includes(ext)) return 'spreadsheet';
  if (mime?.includes('word') || ['doc','docx'].includes(ext)) return 'word';
  if (mime?.includes('presentation') || ['ppt','pptx'].includes(ext)) return 'presentation';
  return 'other';
}

function FileIcon({ mime, name, size = 30 }: { mime?: string | null; name?: string | null; size?: number }) {
  const ft = FILE_COLORS[detectType(mime, name)];
  return (
    <div className="docupane-row-8 documents-panel-e1" style={{ '--documents-panel-width': px(size), '--documents-panel-height': px(size), '--documents-panel-border-radius': px(Math.round(size * 0.25)), '--documents-panel-background-color': ft.bg, '--documents-panel-font-size': px(Math.round(size * 0.24)), '--documents-panel-color': ft.c } as CSSProperties}>
      {ft.l}
    </div>
  );
}

// 16-11-2026 (pasada de diseño): iconos lucide (antes ✓ ✕ ◷) con su texto
// accesible, y la categoría traducida (antes el código crudo: «meeting_notes»).
const APPROVAL_ICON: Record<string, { c: string; Icon: LucideIcon; label: string }> = {
  approved: { c: 'var(--success)', Icon: Check, label: 'pagina_docs.aprobado' },
  rejected: { c: 'var(--danger)', Icon: X, label: 'pagina_docs.rechazado_2' },
  pending:  { c: 'var(--warning)', Icon: Clock, label: 'pagina_docs.pendiente' },
};

/** Clave de la etiqueta de cada categoría (las mismas que /documents). */
const CAT_LABEL: Record<string, string> = {
  contract: 'pagina_docs.contrato',
  deliverable: 'pagina_docs.entregable',
  proposal: 'pagina_docs.propuesta',
  sop: 'pagina_docs.procedimiento_sop',
  legal: 'pagina_docs.legal',
  requirements: 'pagina_docs.requisitos',
  report: 'pagina_docs.cat_report',
  presentation: 'pagina_docs.cat_presentation',
  meeting_notes: 'documents.notas_de_reunion',
  other: 'pagina_docs.otro',
};

const CATS = ['contract','deliverable','proposal','sop','legal','requirements','meeting_notes','other'];

type IdVal = string | number | null | undefined;

function resolveQueryKey(projectId: IdVal, taskId: IdVal, ticketId: IdVal): (string | number | null | undefined)[] {
  if (taskId) return ['docs-task', taskId];
  if (ticketId) return ['docs-ticket', ticketId];
  return ['docs-project', projectId];
}

function resolveApiFn(projectId: IdVal, taskId: IdVal, ticketId: IdVal) {
  if (taskId) return () => documentsApi.byTask(taskId, {});
  if (ticketId) return () => documentsApi.byTicket(ticketId, {});
  return () => documentsApi.byProject(projectId, {});
}

interface DocumentsPanelProps {
  projectId?: IdVal;
  taskId?: IdVal;
  ticketId?: IdVal;
  _compact?: boolean;
}

export default function DocumentsPanel({ projectId, taskId, ticketId, _compact = false }: DocumentsPanelProps) {
  const { t: traducir } = useAppLang()
  const { t } = useAppT();
  const toast = useToast();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('other');
  const [dragOver, setDragOver] = useState(false);

  const qKey = resolveQueryKey(projectId, taskId, ticketId);
  const apiFn = resolveApiFn(projectId, taskId, ticketId);

  const { data: docs = [], isLoading } = useQuery({
    queryKey: qKey,
    queryFn: () => apiFn().then(r => r.data),
    enabled: !!(projectId || taskId || ticketId),
  });

  const uploadMutation = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append('file', file as File);
      fd.append('title', title || (file as File).name);
      fd.append('category', category);
      if (projectId) fd.append('project_id', String(projectId));
      if (taskId)    fd.append('task_id',    String(taskId));
      if (ticketId)  fd.append('ticket_id',  String(ticketId));
      return documentsApi.upload(fd);
    },
    onSuccess: () => {
      toast.success(t('documents_panel.uploaded_ok'));
      qc.invalidateQueries({ queryKey: qKey });
      setFile(null); setTitle(''); setShowForm(false);
    },
    onError: e => toast.error(extractErr(e, t('documents_panel.upload_error'))),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string | number) => documentsApi.delete(id),
    onSuccess: () => { toast.success(t('documents_panel.deleted_ok')); qc.invalidateQueries({ queryKey: qKey }); },
    onError: e => toast.error(extractErr(e, t('documents_panel.delete_error'))),
  });

  const summaryMutation = useMutation({
    mutationFn: (id: string | number) => documentsApi.aiSummary(id),
    onSuccess: () => { toast.success(t('documents_panel.ai_summary_saved')); qc.invalidateQueries({ queryKey: qKey }); },
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  });

  const onDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) { setFile(f); setTitle(t => t || f.name.replace(/\.[^.]+$/, '')); setShowForm(true); }
  }, []);


  return (
    <div className="docupane-box-1">

      {/* Header */}
      <div className="docupane-row-1">
        <div className="docupane-row-2">
          <div className="docupane-row-3">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <span className="docupane-txt-1">
            {traducir('docs.titulo')}
            {!isLoading && <span className="docupane-box-2">({docs.length})</span>}
          </span>
        </div>
        <Button size="sm" variant={showForm ? 'secondary' : 'primary'} icon={showForm ? <X size={13} /> : <Plus size={13} />} onClick={() => setShowForm(s => !s)}>
          {showForm ? t('documents_panel.close') : t('documents_panel.add')}
        </Button>
      </div>

      {/* Upload form */}
      {showForm && (
        <div role="presentation"
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className="docupane-stack-1">
          <Pulsable className="docupane-box-8 document-sx2 documents-panel-e4" onClick={() => fileRef.current?.click()}
            style={{ '--documents-panel-border': `2px dashed ${dragOver || file ? 'var(--accent)' : 'var(--surface-5)'}` } as CSSProperties}>
            <input ref={fileRef} type="file" aria-label={t('documents_panel.click_or_drag')} className="docupane-box-3"
              onChange={e => { const f = e.target.files?.[0]; if (f) { setFile(f); setTitle(t => t || f.name.replace(/\.[^.]+$/, '')); } }} />
            {file
              ? <span className="u-text1-sm-600">{file.name}</span>
              : <span className="u-text3-xs">
                  <Upload size={12} className="document-sx3" />{t('documents_panel.click_or_drag')}
                </span>}
          </Pulsable>
          <Input aria-label={t('documents_panel.title_placeholder')} value={title} onChange={e => setTitle(e.target.value)} placeholder={t('documents_panel.title_placeholder')} inputClassName="docupane-fs" />
          <Select suelto value={category} onChange={e => setCategory(e.target.value)} className="docupane-fs" placeholder={false}>
            {CATS.map(c => <option key={c} value={c}>{t(CAT_LABEL[c])}</option>)}
          </Select>
          <div className="u-row-6">
            <Button size="sm" icon={<Upload size={13} />} onClick={() => uploadMutation.mutate()} disabled={!file} loading={uploadMutation.isPending}>
              {uploadMutation.isPending ? t('documents_panel.uploading') : t('documents_panel.upload')}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => { setShowForm(false); setFile(null); setTitle(''); }}>
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      )}

      {/* Document list */}
      <div>
        {isLoading ? (
          <div className="docupane-box-5">
            <Loader size={16} className="document-sx5" />
          </div>
        ) : docs.length === 0 ? (
          <EmptyState icon={<FileText size={28} />} title={t('documents_panel.no_documents')} />
        ) : (
          docs.map((doc, i) => {
            const lv = doc.latest_version;
            const approval = doc.requires_approval ? APPROVAL_ICON[doc.approval_status || 'pending'] : null;
            return (
              <div className={`docupane-row-11 ${i < docs.length - 1 ? 'documents-panel-m7' : 'documents-panel-m8'}`} key={doc.id}>
                <FileIcon mime={lv?.file_mime_type} name={lv?.file_name} size={28} />
                <div className="u-flex1-min0">
                  <div className="docupane-box-7">{doc.title}</div>
                  <div className="docupane-row-4">
                    <span>{doc.category && CAT_LABEL[doc.category] ? t(CAT_LABEL[doc.category]) : doc.category}</span>
                    {lv && <span className="u-mono">{fmtBytes(lv.file_size)}</span>}
                    {approval && <span className="docupane-txt-2 documents-panel-e9" style={{ '--documents-panel-color': approval.c } as CSSProperties} title={t(approval.label)}><approval.Icon size={11} aria-hidden /><span className="u-sr-only">{t(approval.label)}</span></span>}
                  </div>
                </div>
                <div className="docupane-row-5">
                  {lv?.download_url && (
                    <a href={lv.download_url} target="_blank" rel="noreferrer" title={t('documents_panel.download_title')}
                      className="docupane-row-6">
                      <Download size={11} />
                    </a>
                  )}
                  <IconButton ariaLabel={t('documents_panel.ai_summary_title')} title={t('documents_panel.ai_summary_title')} onClick={() => summaryMutation.mutate(doc.id)}>
                    <Sparkles size={13} />
                  </IconButton>
                  <IconButton ariaLabel={t('documents_panel.delete_title')} title={t('documents_panel.delete_title')} onClick={() => { openConfirmGlobal({message:`${t('documents_panel.delete_confirm')} "${doc.title}"?`,onConfirm:()=>deleteMutation.mutate(doc.id),danger:true}) }}>
                    <Trash2 size={13} />
                  </IconButton>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
