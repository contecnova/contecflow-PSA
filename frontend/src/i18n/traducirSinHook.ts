import { APP_TRANSLATIONS, respaldoIngles } from './appTranslations.ts'
import { resolveTranslation } from './translationRuntime.mjs'
import { idiomaActivo } from '../utils/helpers'


/**
 * Traduce sin hooks y sin contexto de React.
 *
 * Existe por los **error boundaries**, y por dos motivos que se refuerzan:
 *
 * 1. `ErrorBoundary` y `RouteBoundary` son componentes de **clase** —lo exige
 *    React para capturar errores de render—, así que no pueden llamar a
 *    `useAppLang()`. Sin esto, sus textos se quedan en castellano para
 *    siempre: son las únicas cinco cadenas de toda la interfaz que no podían
 *    pasar por `t()`.
 *
 * 2. Y aunque pudieran, **no deberían depender del contexto**. Un boundary se
 *    pinta precisamente cuando el árbol de arriba ha fallado; si lo que falló
 *    fue el propio proveedor de idioma, un `useContext` devolvería `null` y la
 *    pantalla de último recurso fallaría también. Leer el idioma de
 *    `localStorage` no tiene esa dependencia.
 *
 * No sustituye a `t()` en ningún otro sitio: no reacciona al cambio de idioma,
 * porque se evalúa una vez por render y fuera del ciclo de React.
 */
export function traducirSinHook(claveCompleta: string): string {
  // Lee la misma clave que AppLangProvider; con el almacenamiento bloqueado
  // devuelve castellano: una pantalla de error nunca debe caerse por eso.
  const lang = idiomaActivo()

  const [modulo, ...resto] = claveCompleta.split('.')
  return resolveTranslation({
    lang,
    moduleName: modulo,
    keyPath: resto,
    runtimeTranslations: {},
    // Solo lo ya cargado: un boundary no espera descargas (#24a).
    baseTranslations: APP_TRANSLATIONS[lang] ?? APP_TRANSLATIONS.es,
    englishTranslations: respaldoIngles(),
    spanishTranslations: APP_TRANSLATIONS.es,
  })
}
