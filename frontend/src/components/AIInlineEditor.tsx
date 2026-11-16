/**
 * AIInlineEditor — textarea con paleta de comandos IA activada con "/"
 *
 * Uso:
 *   <AIInlineEditor
 *     value={form.description}
 *     onChange={val => set('description')(val)}
 *     rows={4}
 *     placeholder={t('...')}
 *   />
 *
 * Comandos disponibles (etiquetas y ayudas en `traduccion_ui.editor`, es/en/zh; iconos lucide):
 *   /completar  — continúa el texto
 *   /resumir    — genera un resumen conciso
 *   /mejorar    — mejora redacción y claridad
 *   /traducir   — abre un submenú de idiomas (los de la configuración de traducción, el
 *                 de la interfaz primero, nombres con `Intl.DisplayNames`) y traduce a
 *                 CUALQUIERA con `/translation/text` (canal `editor`; usa el glosario y
 *                 la caché de la empresa). Si no hay traducción (`unavailable`/`disabled`)
 *                 se dice el motivo y el texto no cambia (traducción en tiempo real, 16-11-2026).
 *   /puntos     — extrae puntos clave como lista
 */

import { useState, useRef, useCallback, useEffect, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type ChangeEvent as ReactChangeEvent, type ReactNode } from 'react';
import { AlertTriangle, ChevronLeft, FileText, Info, Languages, ListChecks, PenLine, Sparkles, X } from 'lucide-react';
import { nexusAgentApi } from '../services/api';
import { traduccionApi } from '../services/api/traduccion';
import { useAppT, type TranslationParams } from '../hooks/useAppT';
import { errorDeTraduccion, motivoDeTraduccion, nombreDeIdioma } from '../hooks/useTraduccion';
import './AIInlineEditor.css'

const ICONO = { size: 15, 'aria-hidden': true } as const

const COMMANDS: { id: string; icono: ReactNode }[] = [
  { id: 'completar', icono: <PenLine {...ICONO} /> },
  { id: 'resumir',   icono: <FileText {...ICONO} /> },
  { id: 'mejorar',   icono: <Sparkles {...ICONO} /> },
  { id: 'traducir',  icono: <Languages {...ICONO} /> },
  { id: 'puntos',    icono: <ListChecks {...ICONO} /> },
];

// `traducir` no va por aquí: usa el servicio de traducción con el idioma elegido.
// Las instrucciones van en inglés (16-11-2026) y fijan el idioma de salida: el
// del propio texto; si no se puede deducir (texto vacío al completar, texto
// mezclado), el de la interfaz, que llega ya con su nombre en inglés.
const reglaIdioma = (idiomaUi: string) =>
  `Write the output in the same language as the text. If that language cannot be determined, write it in ${idiomaUi}. ` +
  'Return only the resulting text, with no preamble, explanations or quotation marks.'
const PROMPT_MAP: Record<string, (text: string, idiomaUi: string) => string> = {
  completar: (text, idiomaUi) => `Continue the following text coherently and professionally, without repeating what is already written. ${reglaIdioma(idiomaUi)}\n\nText:\n${text}`,
  resumir:   (text, idiomaUi) => `Summarize the following text in 2-4 concise sentences. ${reglaIdioma(idiomaUi)}\n\nText:\n${text}`,
  mejorar:   (text, idiomaUi) => `Improve the wording and clarity of the following text while keeping its original meaning. ${reglaIdioma(idiomaUi)}\n\nText:\n${text}`,
  puntos:    (text, idiomaUi) => `Extract the key points of the following text as a bulleted list, one point per line starting with "• ". ${reglaIdioma(idiomaUi)}\n\nText:\n${text}`,
};

/** El detalle de un error de la API (texto o lista de pydantic). */
function detalleDeError(err: unknown): string {
  const e = err as { response?: { data?: { detail?: unknown } }; message?: string }
  const raw = e?.response?.data?.detail
  if (Array.isArray(raw)) return raw.map((d: { msg?: string }) => d.msg).filter(Boolean).join(', ')
  return (typeof raw === 'string' ? raw : '') || e?.message || ''
}

type AIInlineEditorProps = {
  value: string
  onChange: (val: string) => void
  rows?: number
  placeholder?: string
  /** Sustituye la clase de aspecto por defecto (`ai-inline-editor-campo`); el estado de carga se suma siempre. */
  className?: string
  style?: CSSProperties
  disabled?: boolean
  inputId?: string
  ariaLabel?: string
}

export default function AIInlineEditor({ value, onChange, rows = 4, placeholder, className, style, disabled, inputId, ariaLabel }: AIInlineEditorProps) {
  const { t, lang } = useAppT();
  // `motivoDeTraduccion`/`errorDeTraduccion` piden una t con variables de cualquier tipo.
  const tt = useCallback((k: string, p?: string | Record<string, unknown>) => t(k, p as string | TranslationParams), [t]);
  const [palette, setPalette] = useState(false);   // palette visible?
  const [filter, setFilter]   = useState('');       // text after "/"
  const [loading, setLoading] = useState(false);    // AI in progress
  const [error, setError]     = useState('');
  const [aviso, setAviso]     = useState('');       // informativo (p. ej. ya está en ese idioma)
  // Revisión 2026-11: el texto de antes de aplicar la IA, para poder deshacer.
  const [anterior, setAnterior] = useState<string | null>(null);
  const [slashPos, setSlashPos] = useState(-1);     // caret position of "/"
  // Submenú de /traducir: la lista de idiomas (se pide al abrirlo, una vez).
  const [submenu, setSubmenu] = useState<'comandos' | 'idiomas'>('comandos');
  const [idiomas, setIdiomas] = useState<string[] | null>(null);
  const [cargandoIdiomas, setCargandoIdiomas] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const cajaRef = useRef<HTMLDivElement | null>(null);

  const filtered = COMMANDS.filter(c =>
    !filter || c.id.startsWith(filter.toLowerCase())
  );

  const cerrarPaleta = useCallback(() => {
    setPalette(false);
    setFilter('');
    setSubmenu('comandos');
  }, []);

  // Detect "/" keystroke to open palette
  const handleKeyDown = useCallback((e: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (palette) {
      if (e.key === 'Escape') {
        cerrarPaleta();
        // Remove the "/" we captured
        if (slashPos >= 0) {
          const v = value;
          onChange(v.slice(0, slashPos) + v.slice(slashPos + 1 + filter.length));
        }
        return;
      }
      if (e.key === 'Backspace' && filter.length === 0) {
        cerrarPaleta();
        // Remove the "/"
        if (slashPos >= 0) {
          const v = value;
          onChange(v.slice(0, slashPos) + v.slice(slashPos + 1));
        }
        return;
      }
    }
  }, [palette, filter, slashPos, value, onChange, cerrarPaleta]);

  const handleChange = useCallback((e: ReactChangeEvent<HTMLTextAreaElement>) => {
    const newVal = e.target.value;
    const caret  = e.target.selectionStart ?? 0;

    // Find if user just typed "/"
    if (!palette) {
      const lastChar = newVal[caret - 1];
      if (lastChar === '/') {
        // Only trigger if "/" is at word boundary (start of text or preceded by whitespace/newline)
        const before = newVal[caret - 2];
        if (caret === 1 || !before || /[\s\n]/.test(before)) {
          setSlashPos(caret - 1);
          setPalette(true);
          setFilter('');
          setSubmenu('comandos');
          onChange(newVal);
          return;
        }
      }
      onChange(newVal);
      return;
    }

    // Palette is open — accumulate filter text
    if (caret > slashPos) {
      const typed = newVal.slice(slashPos + 1, caret);
      if (/^[a-z]*$/.test(typed)) {
        setFilter(typed);
        onChange(newVal);
        return;
      }
    }
    // If caret moved before "/" or non-alpha typed, close palette
    cerrarPaleta();
    onChange(newVal);
  }, [palette, slashPos, onChange, cerrarPaleta]);

  /** El texto sin el "/comando" escrito y lo que queda para la IA. */
  const partes = useCallback(() => {
    const before = value.slice(0, slashPos);
    const after  = value.slice(slashPos + 1 + filter.length);
    return { before, after, contextText: (before + after).trim() };
  }, [value, slashPos, filter]);

  const runCommand = useCallback(async (cmd: string) => {
    const { before, after, contextText } = partes();
    cerrarPaleta();
    setError('');
    setAviso('');

    if (!contextText && cmd !== 'completar') {
      setError(t('ai_inline.field_empty'));
      return;
    }

    setLoading(true);
    try {
      // /ai/texto no guarda conversación y, si no hay proveedor, responde un
      // error en vez de un aviso: el texto del usuario no se sustituye nunca por él.
      const res = await nexusAgentApi.texto(PROMPT_MAP[cmd](contextText || '', nombreDeIdioma(lang, 'en') || 'Spanish'));
      const aiText = res.data.texto || '';
      if (!aiText) throw new Error(t('ai_inline.empty_response'));

      let newVal;
      if (cmd === 'completar') {
        // Append the completion
        newVal = (before + after).trimEnd() + (before + after ? ' ' : '') + aiText;
      } else {
        // Replace full content
        newVal = aiText;
      }
      setAnterior(value);
      onChange(newVal);
    } catch (err) {
      setError(detalleDeError(err) || t('ai_inline.contact_error'));
    } finally {
      setLoading(false);
      textareaRef.current?.focus();
    }
  }, [value, onChange, t, lang, partes, cerrarPaleta]);

  /** Abre el submenú de idiomas y, la primera vez, pide la lista a la configuración. */
  const abrirIdiomas = useCallback(async () => {
    setSubmenu('idiomas');
    if (idiomas !== null || cargandoIdiomas) return;
    setCargandoIdiomas(true);
    try {
      const cfg = await traduccionApi.config();
      setIdiomas(cfg.languages ?? []);
    } catch (err) {
      setIdiomas([]);
      setError(errorDeTraduccion(tt, detalleDeError(err)));
    } finally {
      setCargandoIdiomas(false);
    }
  }, [idiomas, cargandoIdiomas, tt]);

  const runTraducir = useCallback(async (destino: string) => {
    const { before, after, contextText } = partes();
    cerrarPaleta();
    setError('');
    setAviso('');
    // Fuera el "/traducir": el texto del usuario queda como estaba.
    const sinComando = before + after;
    if (sinComando !== value) onChange(sinComando);
    if (!contextText) { setError(t('ai_inline.field_empty')); return; }

    setLoading(true);
    try {
      const r = await traduccionApi.texto({ text: contextText, target_language: destino, channel: 'editor' });
      if (r.status === 'translated' && r.text) {
        setAnterior(sinComando);
        onChange(r.text);
      } else if (r.status === 'same_language') {
        setAviso(t('traduccion_ui.editor.mismo_idioma', { idioma: nombreDeIdioma(destino, lang) }));
      } else {
        const motivo = r.reason ?? (r.status === 'disabled' ? 'disabled' : null);
        setError(t('traduccion_ui.editor.no_disponible', { motivo: motivoDeTraduccion(tt, motivo) }));
      }
    } catch (err) {
      setError(errorDeTraduccion(tt, detalleDeError(err)));
    } finally {
      setLoading(false);
      textareaRef.current?.focus();
    }
  }, [partes, cerrarPaleta, value, onChange, t, tt, lang]);

  // Close palette on outside click (la paleta forma parte de la caja: el submenú no la cierra)
  useEffect(() => {
    if (!palette) return;
    const handler = (e: MouseEvent) => {
      if (!cajaRef.current?.contains(e.target as Node)) cerrarPaleta();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [palette, cerrarPaleta]);

  // El idioma de la interfaz primero; el resto por nombre en el idioma de quien mira.
  const idiomasOrdenados = (idiomas ?? []).slice().sort((a, b) => {
    if (a === lang) return -1;
    if (b === lang) return 1;
    return nombreDeIdioma(a, lang).localeCompare(nombreDeIdioma(b, lang), lang);
  });

  return (
    <div className="aiinedit-box-1" ref={cajaRef}>
      <textarea
        id={inputId}
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        rows={rows}
        aria-label={ariaLabel}
        placeholder={placeholder || t('ai_inline.default_placeholder')}
        disabled={disabled || loading}
        className={`${className ?? 'ai-inline-editor-campo'} ${loading ? 'ai-inline-editor-campo--cargando' : ''}`}
        style={style}
      />

      {/* Loading overlay */}
      {loading && (
        <div className="aiinedit-box-2" aria-live="polite">
          {t('ai_inline.processing')}
        </div>
      )}

      {anterior !== null && !loading && (
        <div className="aiinedit-row-1">
          <span>{t('ai_inline.aplicado')}</span>
          <button type="button" onClick={() => { onChange(anterior); setAnterior(null) }}
            className="aiinedit-box-3">
            {t('ai_inline.deshacer')}
          </button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="aiinedit-row-2" role="alert">
          <span className="aiinedit-msg"><AlertTriangle size={13} aria-hidden="true" /> <span>{error}</span></span>
          <button type="button" onClick={() => setError('')} aria-label={t('traduccion_ui.editor.cerrar_aviso')}
            className="aiinedit-box-4">
            <X size={13} aria-hidden="true" />
          </button>
        </div>
      )}

      {/* Aviso informativo */}
      {aviso && (
        <div className="aiinedit-row-aviso" role="status">
          <span className="aiinedit-msg"><Info size={13} aria-hidden="true" /> <span>{aviso}</span></span>
          <button type="button" onClick={() => setAviso('')} aria-label={t('traduccion_ui.editor.cerrar_aviso')}
            className="aiinedit-box-4 aiinedit-box-4--neutro">
            <X size={13} aria-hidden="true" />
          </button>
        </div>
      )}

      {/* Command palette */}
      {palette && submenu === 'comandos' && filtered.length > 0 && (
        <div className="ai-inline-editor-paleta" role="menu" aria-label={t('ai_inline.commands_title')}>
          <div className="aiinedit-row-3">
            <Sparkles size={13} aria-hidden="true" /> <strong className="aiinedit-txt-1">{t('ai_inline.commands_title')}</strong>
            {filter && <span>- {t('ai_inline.searching')} &quot;{filter}&quot;</span>}
            <span className="aiinedit-box-5">{t('ai_inline.esc_cancel')}</span>
          </div>
          {filtered.map(cmd => (
            <button
              type="button"
              role="menuitem"
              key={cmd.id}
              aria-haspopup={cmd.id === 'traducir' ? 'menu' : undefined}
              onMouseDown={(e) => { e.preventDefault(); if (cmd.id === 'traducir') abrirIdiomas(); else runCommand(cmd.id); }}
              className="aiinedit-row-4"
            >
              <span className="aiinedit-box-6">{cmd.icono}</span>
              <div>
                <div className="aiinedit-txt-2">{t(`traduccion_ui.editor.cmd.${cmd.id}`)}</div>
                <div className="aiinedit-box-7">{t(`traduccion_ui.editor.hint.${cmd.id}`)}</div>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Submenú de /traducir: cualquier idioma de la configuración */}
      {palette && submenu === 'idiomas' && (
        <div className="ai-inline-editor-paleta" role="menu" aria-label={t('traduccion_ui.editor.traducir_a')}>
          <div className="aiinedit-row-3">
            <button type="button" className="aiinedit-volver" aria-label={t('traduccion_ui.editor.volver')}
              onMouseDown={(e) => { e.preventDefault(); setSubmenu('comandos'); }}>
              <ChevronLeft size={14} aria-hidden="true" />
            </button>
            <Languages size={13} aria-hidden="true" /> <strong className="aiinedit-txt-1">{t('traduccion_ui.editor.traducir_a')}</strong>
            <span className="aiinedit-box-5">{t('ai_inline.esc_cancel')}</span>
          </div>
          <div className="aiinedit-idiomas">
            {cargandoIdiomas && <div className="aiinedit-vacio" aria-live="polite">{t('traduccion_ui.editor.cargando_idiomas')}</div>}
            {!cargandoIdiomas && idiomasOrdenados.length === 0 && <div className="aiinedit-vacio">{t('traduccion_ui.editor.sin_idiomas')}</div>}
            {idiomasOrdenados.map(codigo => (
              <button
                type="button"
                role="menuitem"
                key={codigo}
                onMouseDown={(e) => { e.preventDefault(); runTraducir(codigo); }}
                className="aiinedit-row-4 aiinedit-idioma"
              >
                <span className="aiinedit-txt-2">{nombreDeIdioma(codigo, lang)}</span>
                {codigo === lang && <span className="aiinedit-box-7">{t('traduccion_ui.editor.tu_idioma')}</span>}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
