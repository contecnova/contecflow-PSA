import { AVAILABLE_LANGUAGES } from '../i18n/appTranslations';
import { useAppLang } from '../i18n/AppLangContext';
import './LangSelector.css'
import type { CSSProperties } from 'react'

/**
 * LangSelector — Language picker for login and other screens
 * Props: optional dark (bool), style (object)
 *
 * Auditoría 2026-09. Este componente leía `l.partial` en tres sitios —el
 * `title`, el `aria-label` y una insignia «β» sobre la bandera— y **ese campo
 * no existe**: las entradas de `APP_LANGUAGES` sólo tienen `code`, `label` y
 * `flag`. Así que la insignia no se pintaba nunca y los dos textos accesibles
 * decían siempre la variante «completa».
 *
 * No era un fallo, era interfaz muerta: viene de cuando se anunciaban ocho
 * idiomas y algunos iban a medias. Hoy se declaran tres —`es`, `en`, `zh`— y
 * los tres están al 100 % con dos gates bloqueantes (hallazgo 16), así que el
 * concepto de «traducción parcial» ya no existe. Se quitan las tres ramas en
 * vez de añadir `partial?: boolean` al tipo: mantener viva la rama de una
 * funcionalidad retirada es lo que hace que estas cosas sobrevivan años.
 */
export default function LangSelector({ dark = false, style = {} }) {
  const { lang, setLang } = useAppLang();
  return (
    <div className="lang-selector-e4" style={style}>
      {AVAILABLE_LANGUAGES.map(l => (
        <button className={`langsele-box-1 langsele-sx1 lang-selector-e1 ${lang === l.code ? 'lang-selector-m2' : 'lang-selector-m3'}`}
          key={l.code}
          onClick={() => setLang(l.code)}
          title={l.label}
          aria-label={l.label}
          style={{ '--lang-selector-background': lang === l.code ? (dark ? 'var(--surface-4)' : 'var(--accent-glow)') : 'transparent', '--lang-selector-border': `1px solid ${lang === l.code ? 'var(--accent-glow)' : 'var(--surface-4)'}` } as CSSProperties}
        >
          {l.code.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
