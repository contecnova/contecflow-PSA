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

import { useState, useRef, useCallback, useEffect } from 'react';
import api from '../services/api';

const COMMANDS = [
  { id: 'completar', label: '✏️ Completar', hint: 'Continúa el texto automáticamente' },
  { id: 'resumir',   label: '📝 Resumir',   hint: 'Genera un resumen conciso' },
  { id: 'mejorar',   label: '✨ Mejorar',   hint: 'Mejora redacción y claridad' },
  { id: 'traducir',  label: '🌐 Traducir',  hint: 'Traduce ES↔EN' },
  { id: 'puntos',    label: '📌 Puntos clave', hint: 'Extrae ideas principales como lista' },
];

const PROMPT_MAP = {
  completar: (text) => `Continúa el siguiente texto de forma coherente y profesional, sin repetir lo ya escrito:\n\n${text}`,
  resumir:   (text) => `Resume el siguiente texto en 2-4 frases concisas:\n\n${text}`,
  mejorar:   (text) => `Mejora la redacción y claridad del siguiente texto, manteniendo el significado original. Devuelve únicamente el texto mejorado, sin explicaciones:\n\n${text}`,
  traducir:  (text) => `Detecta el idioma del siguiente texto y tradúcelo al español si está en inglés, o al inglés si está en español. Devuelve únicamente el texto traducido:\n\n${text}`,
  puntos:    (text) => `Extrae los puntos clave del siguiente texto como una lista con viñetas (•):\n\n${text}`,
};

export default function AIInlineEditor({ value, onChange, rows = 4, placeholder, style, disabled }) {
  const [palette, setPalette] = useState(false);   // palette visible?
  const [filter, setFilter]   = useState('');       // text after "/"
  const [loading, setLoading] = useState(false);    // AI in progress
  const [error, setError]     = useState('');
  const [slashPos, setSlashPos] = useState(-1);     // caret position of "/"
  const textareaRef = useRef(null);

  const filtered = COMMANDS.filter(c =>
    !filter || c.id.startsWith(filter.toLowerCase())
  );

  // Detect "/" keystroke to open palette
  const handleKeyDown = useCallback((e) => {
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

  const handleChange = useCallback((e) => {
    const newVal = e.target.value;
    const caret  = e.target.selectionStart;

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

  const runCommand = useCallback(async (cmd) => {
    // Remove "/command" from the textarea value
    const before = value.slice(0, slashPos);
    const after   = value.slice(slashPos + 1 + filter.length);

    setPalette(false);
    setFilter('');
    setError('');

    const contextText = (before + after).trim();
    if (!contextText && cmd !== 'completar') {
      setError('El campo está vacío. Escribe algo primero.');
      return;
    }

    setLoading(true);
    try {
      const res = await api.post('/ai/chat', {
        message: PROMPT_MAP[cmd](contextText || ''),
        context_type: 'inline_editor',
      });
      const aiText = res.data?.response || res.data?.message || '';
      if (!aiText) throw new Error('Respuesta IA vacía');

      let newVal;
      if (cmd === 'completar') {
        // Append the completion
        newVal = (before + after).trimEnd() + (before + after ? ' ' : '') + aiText;
      } else {
        // Replace full content
        newVal = aiText;
      }
      onChange(newVal);
    } catch (err) {
      const _raw = err?.response?.data?.detail
      const msg = Array.isArray(_raw) ? _raw.map(d => d.msg).join(', ') : (_raw || err.message || 'Error al contactar con la IA');
      setError(msg);
    } finally {
      setLoading(false);
      textareaRef.current?.focus();
    }
  }, [value, slashPos, filter, onChange]);

  // Close palette on outside click
  useEffect(() => {
    if (!palette) return;
    const handler = (e) => {
      if (!textareaRef.current?.contains(e.target)) {
        setPalette(false);
        setFilter('');
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [palette]);

  const baseStyle = {
    width: '100%',
    padding: '8px 12px',
    borderRadius: 6,
    border: '1px solid #4a5568',
    background: '#2d3748',
    color: '#e2e8f0',
    fontSize: 14,
    resize: 'vertical',
    lineHeight: 1.6,
    ...style,
  };

  const paletteStyle = {
    position: 'absolute',
    top: '100%',
    left: 0,
    right: 0,
    zIndex: 9999,
    background: '#1a202c',
    border: '1px solid #4a5568',
    borderRadius: 8,
    boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
    marginTop: 4,
    overflow: 'hidden',
  };

  return (
    <div style={{ position: 'relative', width: '100%' }}>
      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        rows={rows}
        placeholder={placeholder || "Escribe '/' para comandos IA..."}
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
          color: '#63b3ed', fontSize: 13, pointerEvents: 'none',
        }}>
          ✨ Procesando...
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{
          fontSize: 12, color: '#fc8181', marginTop: 4,
          display: 'flex', justifyContent: 'space-between',
        }}>
          <span>⚠ {error}</span>
          <button onClick={() => setError('')}
            style={{ background: 'none', border: 'none', color: '#fc8181', cursor: 'pointer', fontSize: 12 }}>
            ✕
          </button>
        </div>
      )}

      {/* Command palette */}
      {palette && filtered.length > 0 && (
        <div style={paletteStyle}>
          <div style={{
            padding: '6px 12px',
            fontSize: 11,
            color: '#718096',
            borderBottom: '1px solid #2d3748',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}>
            ✨ <strong style={{ color: '#90cdf4' }}>Comandos IA</strong>
            {filter && <span>— buscando &quot;{filter}&quot;</span>}
            <span style={{ marginLeft: 'auto', fontSize: 10 }}>Esc para cancelar</span>
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
                borderBottom: '1px solid #2d3748',
                color: '#e2e8f0',
                cursor: 'pointer',
                textAlign: 'left',
                transition: 'background 0.15s',
              }}
              onMouseEnter={e => e.currentTarget.style.background = '#2d3748'}
              onMouseLeave={e => e.currentTarget.style.background = 'none'}
            >
              <span style={{ fontSize: 15, minWidth: 22 }}>{cmd.label.split(' ')[0]}</span>
              <div>
                <div style={{ fontSize: 13, fontWeight: 500 }}>
                  {cmd.label.slice(cmd.label.indexOf(' ') + 1)}
                </div>
                <div style={{ fontSize: 11, color: '#718096', marginTop: 1 }}>{cmd.hint}</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
