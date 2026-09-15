/**
 * Plotly a medida: sólo las cuatro trazas que esta aplicación dibuja.
 *
 * Auditoría 2026-09. `react-plotly.js` importa el bundle **completo** de
 * `plotly.js`, y ese bundle trae dentro `maplibre-gl` para las trazas de mapa.
 * Dos consecuencias, las dos medidas:
 *
 *   1. `maplibre-gl` <= 6.4.0 tiene un bypass del sanitizador (XSS) sin versión
 *      parcheada dentro del rango que arrastra `plotly.js` 2.x. Dos avisos
 *      **críticos** de `npm audit` por una librería que esta aplicación **no
 *      usa**: el barrido de tipos de traza sobre `src/` da `box`, `violin`,
 *      `scatter3d` y `surface` en plotly, y ni una de mapa.
 *   2. `vendor-plotly` pesaba 4.633 kB, el 38 % del build — lo dice el
 *      comentario de `CMDBPage.tsx`, que por eso ya lo carga en diferido.
 *
 * Registrar sólo lo que se usa arregla las dos cosas a la vez, y sin salto de
 * versión mayor: `plotly.js/lib/core` no incluye ninguna traza, se añaden a
 * mano, y el grafo de módulos deja de alcanzar `maplibre`, `mapbox` y `geo`.
 *
 * ## Si mañana hace falta otra traza
 *
 * Se añade su `import` y su entrada en `register`, y no pasa nada más. Lo que
 * **no** hay que hacer es volver a `import Plot from 'react-plotly.js'` en un
 * componente suelto: eso reintroduce el bundle entero —y `maplibre` con él— por
 * la puerta de atrás, y el resto de componentes seguirían usando éste, así que
 * el build acabaría con las dos copias. Hay un test que lo vigila:
 * `src/charts/__tests__/plotly-custom.test.ts`.
 *
 * ## Por qué `candlestick`, `funnel`, `gauge` y `heatmap` no están aquí
 *
 * Porque no son de plotly: esos cuatro los dibuja `echarts-for-react`. Se
 * comprobó fichero a fichero antes de recortar, que es la diferencia entre
 * recortar y romper.
 */
// @ts-expect-error — `plotly.js/lib/*` no publica tipos; el componente que se
// exporta abajo sí los tiene, vía `@types/react-plotly.js/factory`.
import Plotly from 'plotly.js/lib/core'
// @ts-expect-error — idem.
import box from 'plotly.js/lib/box'
// @ts-expect-error — idem.
import violin from 'plotly.js/lib/violin'
// @ts-expect-error — idem.
import scatter3d from 'plotly.js/lib/scatter3d'
// @ts-expect-error — idem.
import surface from 'plotly.js/lib/surface'
import createPlotlyComponent from 'react-plotly.js/factory'

Plotly.register([box, violin, scatter3d, surface])

/** El mismo componente que exportaba `react-plotly.js`, con menos dentro. */
const Plot = createPlotlyComponent(Plotly)

export default Plot
