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
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const RAIZ = join(__dirname, '..', '..')
const MODULO_A_MEDIDA = join('charts', 'PlotlyCustom.ts')

function ficherosDeCodigo(dir: string): string[] {
  return readdirSync(dir).flatMap((nombre) => {
    const ruta = join(dir, nombre)
    if (statSync(ruta).isDirectory()) return ficherosDeCodigo(ruta)
    return /\.(ts|tsx)$/.test(nombre) ? [ruta] : []
  })
}

// Presupuesto propio: esto no es un test unitario, es un barrido de E/S sobre
// los ~340 ficheros de `src/`. Aislado tarda dos segundos; con la suite entera
// compitiendo por disco se pasaba de los 5 s por defecto y fallaba por
// *timeout*, que se lee como si el guardián hubiera encontrado algo. Treinta
// segundos es holgado para lo que hace y sigue siendo un tope: si un día tarda
// más, es que el barrido creció y hay que mirarlo.
const TOPE_MS = 30_000

describe('bundle de plotly a medida', () => {
  it('ningún componente importa `react-plotly.js` directamente', () => {
    const culpables = ficherosDeCodigo(RAIZ).filter((ruta) => {
      if (ruta.endsWith(MODULO_A_MEDIDA)) return false
      const código = readFileSync(ruta, 'utf-8')
      // Sólo importaciones reales: el propio módulo a medida nombra el paquete
      // en su comentario para explicar qué no hay que hacer.
      return /^\s*import[^\n]*from\s*['"]react-plotly\.js['"]/m.test(código)
    })

    expect(
      culpables,
      'importan el bundle completo de plotly, que reintroduce `maplibre-gl` ' +
        '(2 críticos de npm audit) y los 4,6 MB de `vendor-plotly`. ' +
        'Usa `src/charts/PlotlyCustom.ts`; si te falta una traza, añádela allí.',
    ).toEqual([])
  }, TOPE_MS)

  it('el módulo a medida registra exactamente las trazas que se usan', () => {
    const código = readFileSync(join(RAIZ, MODULO_A_MEDIDA), 'utf-8')
    for (const traza of ['box', 'violin', 'scatter3d', 'surface']) {
      expect(código).toContain(`plotly.js/lib/${traza}`)
    }
    // Y ninguna de mapa: son las que arrastran `maplibre-gl`.
    for (const mapa of ['scattermapbox', 'choroplethmapbox', 'scattermap', 'choroplethmap', 'scattergeo']) {
      expect(código).not.toContain(`plotly.js/lib/${mapa}`)
    }
  })
})
