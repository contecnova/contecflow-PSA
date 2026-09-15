/**
 * Nadie vuelve a importar el bundle completo de plotly.
 *
 * Auditoría 2026-09. `react-plotly.js` arrastra `plotly.js` entero, y dentro
 * viaja `maplibre-gl`, que tenía dos avisos **críticos** de `npm audit` por una
 * librería que esta aplicación no usa: no dibuja ni una traza de mapa. El
 * arreglo fue un bundle a medida (`src/charts/PlotlyCustom.ts`) con las cuatro
 * trazas que sí usa.
 *
 * Ese arreglo se deshace con una sola línea: basta con que alguien escriba
 * `import Plot from 'react-plotly.js'` en un componente nuevo. Y el fallo sería
 * silencioso en lo que importa —el gráfico se vería perfectamente—; lo que
 * volvería es el peso y la dependencia vulnerable, que no se notan mirando la
 * pantalla. Por eso se vigila con un test y no con una norma escrita.
 *
 * Se mira el **código fuente** y no el grafo de módulos a propósito: lo que hay
 * que impedir es la línea, y leer los ficheros es la forma directa de verlo.
 *
 * Cómo se leen los ficheros, que tiene historia
 * ---------------------------------------------
 * La primera versión recorría el disco con `node:fs` y `__dirname`. Funcionaba,
 * y traía dos problemas que no se ven hasta que aparecen:
 *
 *  · **Metía los tipos de Node en todo el programa.** Una `/// <reference
 *    types="node" />` no es local al fichero: vale para la compilación entera.
 *    Con ella cargada, `window.setTimeout` pasa a resolverse contra la
 *    declaración de Node y devuelve `NodeJS.Timeout` en vez de `number`, y
 *    `PortalClientePage` —que guarda el identificador de un temporizador con el
 *    idioma correcto, `ReturnType<typeof window.setTimeout>`— dejaba de
 *    compilar. Un fichero de test no puede cambiarle los tipos al navegador.
 *
 *  · **Tardaba.** Era un barrido de E/S sobre los ~340 ficheros de `src/`, y
 *    con la suite entera compitiendo por disco se pasaba del tope por defecto
 *    de 5 s y fallaba por *timeout*, que se lee igual que si el guardián
 *    hubiera encontrado algo.
 *
 * `import.meta.glob` con `?raw` resuelve los dos: es la forma nativa de Vite,
 * el contenido lo inlinea el bundler en tiempo de compilación —así que aquí no
 * hay E/S ninguna— y no necesita un solo tipo de Node.
 */
import { describe, expect, it } from 'vitest'

// `eager: true` deja el contenido de cada fichero en el objeto, ya resuelto.
// La ruta es relativa a ESTE fichero: `../..` es `src/`.
const FUENTES = import.meta.glob('../../**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

// Vite normaliza cada clave a la ruta relativa **más corta** desde este
// fichero, no a la que se escribió en el patrón: `src/charts/PlotlyCustom.ts`
// vuelve como `../PlotlyCustom.ts` y no como `../../charts/PlotlyCustom.ts`.
// Por eso se busca por el nombre del fichero y no por igualdad de clave — que
// es lo que se intentó primero, y no encontraba nada. Lo cazó el primer test de
// abajo, que existe exactamente para eso.
const SUFIJO_A_MEDIDA = '/PlotlyCustom.ts'

function esElModuloAMedida(ruta: string): boolean {
  return ruta.endsWith(SUFIJO_A_MEDIDA)
}

const rutaDelModulo = Object.keys(FUENTES).find(esElModuloAMedida)

describe('bundle de plotly a medida', () => {
  it('el barrido encuentra el árbol de fuentes', () => {
    // Si un cambio de rutas dejara el glob vacío, los dos tests de abajo
    // pasarían sin mirar nada. Esto es el guardián del guardián.
    expect(Object.keys(FUENTES).length).toBeGreaterThan(100)
    expect(rutaDelModulo, 'el glob no encuentra `src/charts/PlotlyCustom.ts`').toBeDefined()
  })

  it('ningún componente importa `react-plotly.js` directamente', () => {
    const culpables = Object.entries(FUENTES)
      .filter(([ruta]) => !esElModuloAMedida(ruta))
      // Sólo importaciones reales: el propio módulo a medida nombra el paquete
      // en su comentario para explicar qué no hay que hacer.
      .filter(([, codigo]) => /^\s*import[^\n]*from\s*['"]react-plotly\.js['"]/m.test(codigo))
      .map(([ruta]) => ruta)

    expect(
      culpables,
      'importan el bundle completo de plotly, que reintroduce `maplibre-gl` ' +
        '(2 críticos de npm audit) y los 4,6 MB de `vendor-plotly`. ' +
        'Usa `src/charts/PlotlyCustom.ts`; si te falta una traza, añádela allí.',
    ).toEqual([])
  })

  it('el módulo a medida registra exactamente las trazas que se usan', () => {
    const codigo = (rutaDelModulo && FUENTES[rutaDelModulo]) ?? ''
    for (const traza of ['box', 'violin', 'scatter3d', 'surface']) {
      expect(codigo).toContain(`plotly.js/lib/${traza}`)
    }
    // Y ninguna de mapa: son las que arrastran `maplibre-gl`.
    for (const mapa of ['scattermapbox', 'choroplethmapbox', 'scattermap', 'choroplethmap', 'scattergeo']) {
      expect(codigo).not.toContain(`plotly.js/lib/${mapa}`)
    }
  })
})
