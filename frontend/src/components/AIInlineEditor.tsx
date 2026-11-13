/**
 * AIInlineEditor — textarea con paleta de comandos IA activada con "/"
 *
 * Uso:
 *   <AIInlineEditor
 *     value={form.description}
 *     onChange={val => set('description')(val)}
 *     rows={4}
 *     placeholder="Escribe '/' para comandos IA..."
 *     style={...}
 *   />
 *
 * Comandos disponibles:
 *   /completar  — continúa el texto
 *   /resumir    — genera un resumen conciso
 *   /mejorar    — mejora redacción y claridad
 *   /traducir   — detecta idioma y traduce al otro (ES↔EN)
 *   /puntos     — extrae puntos clave como lista
 */

import { useState, useRef, useCallback, useEffect, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type ChangeEvent as ReactChangeEvent } from 'react';
import { nexusAgentApi } from '../services/api';
import { useAppT } from '../hooks/useAppT';

const COMMANDS = [
  { id: 'completar', label: '✏️ Completar', hint: 'Continúa el texto automáticamente' },
  { id: 'resumir',   label: '📝 Resumir',   hint: 'Genera un resumen conciso' },
  { id: 'mejorar',   label: '✨ Mejorar',   hint: 'Mejora redacción y claridad' },
  { id: 'traducir',  label: '🌐 Traducir',  hint: 'Traduce ES↔EN' },
  { id: 'puntos',    label: '📌 Puntos clave', hint: 'Extrae ideas principales como lista' },
];

const PROMPT_MAP: Record<string, (text: string) => string> = {
  completar: (text) => `Continúa el siguiente texto de forma coherente y profesional, sin repetir lo ya escrito:\n\n${text}`,
  resumir:   (text) => `Resume el siguiente texto en 2-4 frases concisas:\n\n${text}`,
  mejorar:   (text) => `Mejora la redacción y claridad del siguiente texto, manteniendo el significado original. Devuelve únicamente el texto mejorado, sin explicaciones:\n\n${text}`,
  traducir:  (text) => `Detecta el idioma del siguiente texto y tradúcelo al español si está en inglés, o al inglés si está en español. Devuelve únicamente el texto traducido:\n\n${text}`,
  puntos:    (text) => `Extrae los puntos clave del siguiente texto como una lista con viñetas (•):\n\n${text}`,
};

type AIInlineEditorProps = {
  value: string
  onChange: (val: string) => void
  rows?: number
  placeholder?: string
  style?: CSSProperties
  disabled?: boolean
  inputId?: string
  ariaLabel?: string
}

export default function AIInlineEditor({ value, onChange, rows = 4, placeholder, style, disabled, inputId, ariaLabel }: AIInlineEditorProps) {
  const { t } = useAppT();
  const [palette, setPalette] = useState(false);   // palette visible?
  const [filter, setFilter]   = useState('');       // text after "/"
  const [loading, setLoading] = useState(false);    // AI in progress
  const [error, setError]     = useState('');
  // Revisión 2026-11: el texto de antes de aplicar la IA, para poder deshacer.
  const [anterior, setAnterior] = useState<string | null>(null);
  const [slashPos, setSlashPos] = useState(-1);     // caret position of "/"
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const filtered = COMMANDS.filter(c =>
    !filter || c.id.startsWith(filter.toLowerCase())
  );

  // Detect "/" keystroke to open palette
  const handleKeyDown = useCallback((e: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (palette) {
      if (e.key === 'Escape') {
        setPalette(false);
        setFilter('');
        // Remove the "/" we captured
        if (slashPos >= 0) {
          const v = value;
          onChange(v.slice(0, slashPos) + v.slice(slashPos + 1 + filter.length));
        }
        return;
      }
      if (e.key === 'Backspace' && filter.length === 0) {
        setPalette(false);
        setFilter('');
        // Remove the "/"
        if (slashPos >= 0) {
          const v = value;
          onChange(v.slice(0, slashPos) + v.slice(slashPos + 1));
        }
        return;
      }
    }
  }, [palette, filter, slashPos, value, onChange]);

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
    setPalette(false);
    setFilter('');
    onChange(newVal);
  }, [palette, slashPos, onChange]);

  const runCommand = useCallback(async (cmd: string) => {
    // Remove "/command" from the textarea value
    const before = value.slice(0, slashPos);
    const after   = value.slice(slashPos + 1 + filter.length);

    setPalette(false);
    setFilter('');
    setError('');

    const contextText = (before + after).trim();
    if (!contextText && cmd !== 'completar') {
      setError(t('ai_inline.field_empty'));
      return;
    }

    setLoading(true);
    try {
      // /ai/texto no guarda conversación y, si no hay proveedor, responde un
      // error en vez de un aviso: el texto del usuario no se sustituye nunca por él.
      const res = await nexusAgentApi.texto(PROMPT_MAP[cmd](contextText || ''));
      const aiText = (res.data as { texto?: string })?.texto || '';
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
      const e = err as { response?: { data?: { detail?: unknown } }; message?: string }
      const _raw = e?.response?.data?.detail
      const msg = Array.isArray(_raw)
        ? _raw.map((d: { msg?: string }) => d.msg).filter(Boolean).join(', ')
        : (_raw as string) || e.message || t('ai_inline.contact_error');
      setError(msg);
    } finally {
      setLoading(false);
      textareaRef.current?.focus();
    }
  }, [value, slashPos, filter, onChange, t]);

  // Close palette on outside click
  useEffect(() => {
    if (!palette) return;
    const handler = (e: MouseEvent) => {
      if (!textareaRef.current?.contains(e.target as Node)) {
        setPalette(false);
        setFilter('');
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [palette]);

  const baseStyle: CSSProperties = {
    width: '100%',
    padding: '8px 12px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--surface-5)',
    background: 'var(--surface-4)',
    color: 'var(--text-1)',
    fontSize: "var(--text-md)",
    resize: 'vertical',
    lineHeight: 1.6,
    ...style,
  };

  const paletteStyle: CSSProperties = {
    position: 'absolute',
    top: '100%',
    left: 0,
    right: 0,
    zIndex: 'var(--z-drag)',
    background: 'var(--surface-2)',
    border: '1px solid var(--surface-5)',
    borderRadius: 8,
    boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
    marginTop: 4,
    overflow: 'hidden',
  };

  return (
    <div style={{ position: 'relative', width: '100%' }}>
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
        style={{
          ...baseStyle,
          opacity: loading ? 0.6 : 1,
          cursor: loading ? 'wait' : 'text',
        }}
      />

      {/* Loading overlay */}
      {loading && (
        <div style={{
          position: 'absolute', top: 8, right: 12,
          color: 'var(--info)', fontSize: "var(--text-base)", pointerEvents: 'none',
        }}>
          {t('ai_inline.processing')}
        </div>
      )}

      {anterior !== null && !loading && (
        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 4, display: 'flex', gap: 8, alignItems: 'center' }}>
          <span>{t('ai_inline.aplicado')}</span>
          <button type="button" onClick={() => { onChange(anterior); setAnterior(null) }}
            style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-xs)", padding: 0, fontFamily: 'inherit' }}>
            {t('ai_inline.deshacer')}
          </button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{
          fontSize: "var(--text-sm)", color: 'var(--danger)', marginTop: 4,
          display: 'flex', justifyContent: 'space-between',
        }}>
          <span>⚠ {error}</span>
          <button onClick={() => setError('')}
            style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>
            ✕
          </button>
        </div>
      )}

      {/* Command palette */}
      {palette && filtered.length > 0 && (
        <div style={paletteStyle}>
          <div style={{
            padding: '6px 12px',
            fontSize: "var(--text-xs)",
            color: 'var(--text-2)',
            borderBottom: '1px solid var(--surface-4)',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}>
            ✨ <strong style={{ color: 'var(--info)' }}>{t('ai_inline.commands_title')}</strong>
            {filter && <span>- {t('ai_inline.searching')} &quot;{filter}&quot;</span>}
            <span style={{ marginLeft: 'auto', fontSize: "var(--text-2xs)" }}>{t('ai_inline.esc_cancel')}</span>
          </div>
          {filtered.map(cmd => (
            <button
              key={cmd.id}
              onMouseDown={(e) => { e.preventDefault(); runCommand(cmd.id); }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                width: '100%',
                padding: '10px 14px',
                background: 'none',
                border: 'none',
                borderBottom: '1px solid var(--surface-4)',
                color: 'var(--text-1)',
                cursor: 'pointer',
                textAlign: 'left',
                transition: 'background 0.15s',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-4)'}
              onMouseLeave={e => e.currentTarget.style.background = 'none'}
            >
              <span style={{ fontSize: "var(--text-md-em)", minWidth: 22 }}>{cmd.label.split(' ')[0]}</span>
              <div>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 500 }}>
                  {cmd.label.slice(cmd.label.indexOf(' ') + 1)}
                </div>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 1 }}>{cmd.hint}</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
