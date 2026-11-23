/**
 * Modal de subida y panel de compartición de un documento.
 * Troceado de DocumentsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useState, useRef, useCallback, useMemo, type CSSProperties, type DragEvent, useId } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { documentsApi, projectsApi, usersApi, esFichaCompleta, type PathId } from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import { Upload, Trash2, X, Check, Share2 } from 'lucide-react'
import { Button, useDialogoEditable, IconButton, Select, Checkbox, Input, Textarea } from '../../components/ui'
import { fmtDate, extractErr } from '../../utils/helpers'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import DateInput from '../../components/ui/DateInput'
import { STALE_DEFAULT_MS, STALE_SHORT_MS } from '../../constants/timings'
import { useRolesReales } from '../../hooks/useRolesReales'
import { detectFileType, type DocPermission, etiquetaCategoria, FILE_COLORS, FileIcon, fmtBytes, type PermissionGrant } from './compartido'

// ── Upload Modal ─────────────────────────────────────────

export const CATS = ['contract','deliverable','proposal','sop','legal','requirements','report','presentation','meeting_notes','other'];

export function UploadModal({ open, onClose, onSuccess }: { open: boolean; onClose: () => void; onSuccess: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [form, setForm] = useState({ title:'', description:'', category:'other', tags:'', requires_approval: false, project_id:'' });

  const { data: projects = [] } = useQuery({
    queryKey: ['projects-minimal'],
    queryFn: () => projectsApi.list().then(r => r.data),
    staleTime: STALE_SHORT_MS,
  });

  const uploadMutation = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append('file', file!);
      fd.append('title', form.title || file!.name);
      if (form.description) fd.append('description', form.description);
      fd.append('category', form.category);
      if (form.tags) fd.append('tags', form.tags);
      fd.append('requires_approval', String(form.requires_approval));
      if (form.project_id) fd.append('project_id', form.project_id);
      return documentsApi.upload(fd);
    },
    onSuccess: () => { toast.success(t('pagina_docs.documento_subido_correctamente')); onSuccess(); },
    onError: (e: unknown) => toast.error(extractErr(e, t('pagina_docs.error_al_subir'))),
  });

  const onDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) { setFile(f); setForm(p => ({ ...p, title: p.title || f.name.replace(/\.[^.]+$/, '') })); }
  }, []);

  const pickFile = (f: File) => { setFile(f); setForm(p => ({ ...p, title: p.title || f.name.replace(/\.[^.]+$/, '') })); };
  // Fondo, Esc y X preguntan si hay cambios sin guardar (kit, 23-11-2026). El
  // archivo llega también arrastrado (sin `input`): lo decide la pantalla.
  const { ref: dialogRef, pedirCierre } = useDialogoEditable<HTMLDivElement>(open, onClose, {
    cambiosSinGuardar: Boolean(file) || Boolean(form.title.trim() || form.description.trim() || form.tags.trim()),
  });

  if (!open) return null;

  const fileType = file ? detectFileType(undefined, file.name) : null;
  const fileFt = fileType ? FILE_COLORS[fileType] : null;

  return (
    <div role="presentation" className="docs-overlay" onMouseDown={pedirCierre}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="upload-dialog-title" className="docs-dialog" onMouseDown={e => e.stopPropagation()}>

        {/* Header */}
        <div className="docs-row-15">
          <div>
            <div id="upload-dialog-title" className="docs-box-10">{t('pagina_docs.subir_documento')}</div>
            <div className="docs-box-11">{t('documents.arrastra_un_archivo_o_haz_clic_para')}</div>
          </div>
          <IconButton onClick={pedirCierre} ariaLabel={t('pagina_docs.cerrar')}>
            <X size={18} />
          </IconButton>
        </div>

        {/* Body: dos columnas */}
        <div className="docs-grid">
          {/* Izquierda: zona de carga */}
          <div className="docs-box-12">
            <div
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              onClick={() => fileRef.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  fileRef.current?.click();
                }
              }}
              className={`docs-stack-3 document-sx8 ${dragOver ? 'document-sx18' : 'document-sx17'} documents-page-e4`} style={{ '--documents-page-border': `2px dashed ${dragOver ? 'var(--accent)' : file ? (fileFt?.c || 'var(--success)') : 'var(--surface-5)'}` } as CSSProperties}>
              <input ref={fileRef} type="file" aria-label={t('documents.clic_para_seleccionar_archivo')} className="docs-input" onChange={e => { const f = e.target.files?.[0]; if (f) pickFile(f); }} />
              {file ? (
                <>
                  <FileIcon mime={undefined} name={file.name} size={56} />
                  <div className="docs-box-13">{file.name}</div>
                  <div className="u-text3-mono-xs">{fmtBytes(file.size)}</div>
                  <Button size="sm" variant="secondary" onClick={e => { e.stopPropagation(); setFile(null); }}>
                    {t('pagina_docs.cambiar_archivo')}
                  </Button>
                </>
              ) : (
                <>
                  <div className="docs-row-16">
                    <Upload size={22} className="u-text3" />
                  </div>
                  <div className="docs-box-14">{t('pagina_docs.arrastra_aqui_tu_archivo')}</div>
                  <div className="u-text3-xs">{t('documents.o_haz_clic_para_seleccionar')}</div>
                  <div className="docs-box-15">{t('documents.pdf_word_excel_imagenes_max_100_mb')}</div>
                </>
              )}
            </div>
          </div>

          {/* Derecha: metadatos */}
          <div className="docs-stack-4">
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="documents-page-e7">{t('documents.titulo')}</label>
              <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))} placeholder={file?.name || t('pagina_docs.titulo_del_documento')} inputClassName="documents-page-e8" />
            </div>
            <div>
              <label className="documents-page-e7">{t('documents.descripcion')}</label>
              <Textarea value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} rows={2} placeholder={t('documents.descripcion_del_documento')} aria-label={t('documents.descripcion_del_documento')} inputClassName="documents-page-e5" />
            </div>
            <div className="u-grid2-10">
              <div>
                <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="documents-page-e7">{t('documents.categoria')}</label>
                <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.category} onChange={e => setForm(p => ({ ...p, category: e.target.value }))} className="documents-page-e8">
                  {CATS.map(c => <option key={c} value={c}>{etiquetaCategoria(t, c)}</option>)}
                </Select>
              </div>
              <div>
                <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="documents-page-e7">{t('pagina_docs.proyecto')}</label>
                <Select suelto placeholder={false} id={`${idCampo}-3`} value={form.project_id} onChange={e => setForm(p => ({ ...p, project_id: e.target.value }))} className="documents-page-e8">
                  <option value="">{t('documents.sin_proyecto')}</option>
                  {projects.map(p => <option key={p.id} value={p.id}>{p.code ? `${p.code} - ` : ''}{p.name}</option>)}
                </Select>
              </div>
            </div>
            <div>
              <label id={`${idCampo}-etiquetas-et`} htmlFor={`${idCampo}-etiquetas`} className="documents-page-e7">{t('pagina_docs.etiquetas')}</label>
              <Input id={`${idCampo}-etiquetas`} aria-labelledby={`${idCampo}-etiquetas-et`} value={form.tags} onChange={e => setForm(p => ({ ...p, tags: e.target.value }))} placeholder={t('documents.etiquetas_separadas_por_comas')} aria-label={t('documents.etiquetas_separadas_por_comas')} inputClassName="documents-page-e8" />
            </div>
            <label className="docs-label-2">
              <Checkbox aria-label={t('documents.requiere_aprobacion_antes_de_usar')} checked={form.requires_approval} onChange={(_, e) => setForm(p => ({ ...p, requires_approval: e.target.checked }))}
                className="docs-input-2" />
              <span className="u-text2-base">{t('documents.requiere_aprobacion_antes_de_usar')}</span>
            </label>
          </div>
        </div>

        {/* Footer */}
        <div className="docs-row-17">
          <Button variant="secondary" onClick={onClose}>
            {t('pagina_docs.cancelar')}
          </Button>
          <Button icon={<Upload size={14} />} onClick={() => uploadMutation.mutate()} disabled={!file} loading={uploadMutation.isPending}>
            {uploadMutation.isPending ? t('pagina_docs.subiendo') : t('pagina_docs.subir_documento')}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Document Drawer (panel lateral) ─────────────────────────────────────────

// ── Share panel (per-document permissions) ────────────────────────────────────
const ACCESS_LEVELS = [
  { v: 'viewer', l: 'pagina_docs.lector_abrir_y_descargar' },
  { v: 'editor', l: 'pagina_docs.editor_subir_versiones' },
  { v: 'admin', l: 'pagina_docs.admin_gestionar_permisos' },
];

export function SharePanel({ documentId }: { documentId: PathId }) {
  const idCampo = useId()
  // 19-11-2026: roles reales del backend (`GET /auth/roles`).
  const roles = useRolesReales()
  const t = useAppT()
  const toast = useToast();
  const qc = useQueryClient();
  const [subjectType, setSubjectType] = useState('user'); // user | role | department
  const [userId, setUserId] = useState('');
  const [roleVal, setRoleVal] = useState('pm');
  const [deptVal, setDeptVal] = useState('');
  const [accessLevel, setAccessLevel] = useState('viewer');
  const [expiresAt, setExpiresAt] = useState('');

  const { data: perms = [] } = useQuery<DocPermission[]>({
    queryKey: ['document-permissions', documentId],
    queryFn: () => documentsApi.listPermissions(documentId).then(r => r.data),
  });

  const { data: users = [] } = useQuery({
    queryKey: ['users-min'],
    queryFn: () => usersApi.list().then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  });

  const departments = useMemo(() => {
    const s = new Set<string>();
    users.forEach(u => { if (u.department) s.add(u.department); });
    return [...s].sort();
  }, [users]);

  const grantMutation = useMutation({
    mutationFn: (payload: PermissionGrant) => documentsApi.grantPermission(documentId, payload),
    onSuccess: () => {
      toast.success(t('pagina_docs.permiso_concedido'));
      qc.invalidateQueries({ queryKey: ['document-permissions', documentId] });
      qc.invalidateQueries({ queryKey: ['document', documentId] });
      setUserId(''); setDeptVal(''); setExpiresAt('');
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('pagina_docs.no_se_pudo_conceder_el_permiso'))),
  });

  const revokeMutation = useMutation({
    mutationFn: (permId: string) => documentsApi.revokePermission(documentId, permId),
    onSuccess: () => {
      toast.success(t('pagina_docs.permiso_revocado'));
      qc.invalidateQueries({ queryKey: ['document-permissions', documentId] });
      qc.invalidateQueries({ queryKey: ['document', documentId] });
    },
    onError: (e: unknown) => toast.error(extractErr(e, t('pagina_docs.no_se_pudo_revocar'))),
  });

  const submitGrant = () => {
    const payload: PermissionGrant = { access_level: accessLevel };
    if (expiresAt) payload.expires_at = new Date(expiresAt).toISOString();
    if (subjectType === 'user') {
      if (!userId) { toast.error(t('pagina_docs.selecciona_un_usuario')); return; }
      payload.user_id = userId;
    } else if (subjectType === 'role') {
      payload.role = roleVal;
    } else if (subjectType === 'department') {
      const d = (deptVal || '').trim();
      if (!d) { toast.error(t('pagina_docs.indica_un_departamento')); return; }
      payload.department = d;
    }
    grantMutation.mutate(payload);
  };

  const subjectLabel = (p: DocPermission) => {
    if (p.user_id) return p.user_name || String(p.user_id);
    if (p.role) return t('pagina_docs.rol', { role: etiquetaCodigo(t, 'rol_usuario', p.role) });
    if (p.department) return t('pagina_docs.departamento', { department: p.department });
    return '—';
  };


  return (
    <div className="docs-stack-5">
      <div className="docs-card-2">
        <strong>{t('documents.por_defecto')}</strong>{t('documents.el_creador_del_documento_y_los_miembros')}
      </div>

      {/* Add grant */}
      <div className="docs-card-3">
        <div className="docs-row-18">
          <Share2 size={14} />{' '}{t('pagina_docs.conceder_acceso')}
        </div>

        <div className="u-mb-12">
          <Select suelto placeholder={false} value={subjectType} onChange={e => setSubjectType(e.target.value)} aria-label={t('pagina_docs.conceder_acceso')} className="documents-page-e10">
            <option value="user">{t('pagina_docs.usuario')}</option>
            <option value="role">{t('pagina_docs.rol_2')}</option>
            <option value="department">{t('pagina_docs.departamento_2')}</option>
          </Select>
        </div>

        {subjectType === 'user' && (
          <div className="u-mb-12">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="documents-page-e9">{t('pagina_docs.usuario')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-1`} value={userId} onChange={e => setUserId(e.target.value)} className="documents-page-e10">
              <option value="">{t('documents.selecciona_un_usuario')}</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name}{esFichaCompleta(u) ? ` (${u.email})` : ''}</option>)}
            </Select>
          </div>
        )}
        {subjectType === 'role' && (
          <div className="u-mb-12">
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="documents-page-e9">{t('pagina_docs.rol_2')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-2`} value={roleVal} onChange={e => setRoleVal(e.target.value)} className="documents-page-e10">
              {roles.map(r => <option key={r.id} value={r.id}>{r.etiqueta}</option>)}
            </Select>
          </div>
        )}
        {subjectType === 'department' && (
          <div className="u-mb-12">
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="documents-page-e9">{t('pagina_docs.departamento_2')}</label>
            <Input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="text" value={deptVal} onChange={e => setDeptVal(e.target.value)} list="departments-list" placeholder={t('pagina_docs.ej_finance')} inputClassName="documents-page-e10" />
            <datalist id="departments-list">
              {departments.map(d => <option key={d} value={d} aria-label={d} />)}
            </datalist>
          </div>
        )}

        <div className="docs-grid-3">
          <div>
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="documents-page-e9">{t('documents.nivel_de_acceso')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-4`} value={accessLevel} onChange={e => setAccessLevel(e.target.value)} className="documents-page-e10">
              {ACCESS_LEVELS.map(a => <option key={a.v} value={a.v}>{t(a.l)}</option>)}
            </Select>
          </div>
          <div>
            <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="documents-page-e9">{t('pagina_docs.caducidad_opcional')}</label>
            <DateInput id={`${idCampo}-5`} withTime value={expiresAt} onChange={e => setExpiresAt(e.target.value)} className="documents-page-e10" />
          </div>
        </div>

        <Button icon={<Check size={14} />} onClick={submitGrant} loading={grantMutation.isPending}>
          {grantMutation.isPending ? t('pagina_docs.concediendo') : t('pagina_docs.conceder_acceso')}
        </Button>
      </div>

      {/* Existing grants */}
      <div>
        <div className="docs-box-16">
          {t('pagina_docs.permisos_actuales')}{' '}<span className="docs-label-3">({perms.length})</span>
        </div>
        {perms.length === 0 ? (
          <div className="docs-card-4">
            {t('documents.sin_permisos_explicitos_solo_el_creador_y')}
          </div>
        ) : (
          <div className="u-stack-6">
            {perms.map(p => (
              <div key={p.id} className="docs-row-19">
                <div className="u-flex1-min0">
                  <div className="u-text1-sm-600">{subjectLabel(p)}</div>
                  <div className="u-text3-2xs">
                    {ACCESS_LEVELS.find(a => a.v === p.access_level)?.l ? t(ACCESS_LEVELS.find(a => a.v === p.access_level)!.l) : p.access_level}
                    {p.granted_by_name && t('pagina_docs.concedido_por', { granted_by_name: p.granted_by_name })}
                    {p.expires_at && t('pagina_docs.caduca', { v1: fmtDate(p.expires_at) })}
                  </div>
                </div>
                <Button size="sm" variant="danger" icon={<Trash2 size={12} />} onClick={() => revokeMutation.mutate(p.id)} disabled={revokeMutation.isPending}>
                  {t('pagina_docs.revocar')}
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
