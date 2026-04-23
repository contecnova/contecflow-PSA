import { APP_LANGUAGES } from '../i18n/appTranslations';
import { useAppLang } from '../i18n/AppLangContext';

/**
 * LangSelector — Language picker for login and other screens
 * Props: optional dark (bool), style (object)
 */
export default function LangSelector({ dark = false, style = {} }) {
  const { lang, setLang } = useAppLang();
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', ...style }}>
      {APP_LANGUAGES.map(l => (
        <button
          key={l.code}
          onClick={() => setLang(l.code)}
          title={l.partial ? `${l.label} (traducción parcial — algunas claves en inglés)` : l.label}
          aria-label={l.partial ? `${l.label} — traducción parcial` : l.label}
          style={{
            position: 'relative',
            background: lang === l.code ? (dark ? 'var(--surface-4)' : 'var(--accent-glow)') : 'transparent',
            border: `1px solid ${lang === l.code ? 'var(--accent-glow)' : (dark ? 'var(--surface-4)' : 'rgba(0,180,255,0.12)')}`,
            borderRadius: 8,
            padding: '5px 9px',
            cursor: 'pointer',
            fontSize: 16,
            lineHeight: 1,
            fontFamily: 'inherit',
            transition: 'all 0.15s',
            opacity: lang === l.code ? 1 : 0.7,
          }}
        >
          {l.flag}
          {l.partial && (
            <span style={{
              position: 'absolute',
              top: -4,
              right: -4,
              background: 'var(--accent-glow, #0af)',
              color: '#000',
              fontSize: 8,
              fontWeight: 700,
              lineHeight: 1,
              borderRadius: 4,
              padding: '1px 3px',
              pointerEvents: 'none',
            }}>
              β
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
