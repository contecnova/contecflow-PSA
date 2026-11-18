/**
 * Quita en desarrollo el aviso «Download the React DevTools…» (18-11-2026).
 *
 * Antes este filtro estaba en el cuerpo de main.tsx, pero los `import` se
 * evalúan antes que el cuerpo: react-dom ya había escrito el aviso cuando se
 * instalaba el filtro, así que nunca quitaba nada. Como primer import de
 * main.tsx se instala antes de cargar React.
 */
if (import.meta.env.DEV) {
  const esAviso = (msg: unknown): boolean => typeof msg === 'string' && msg.includes('Download the React DevTools')
  for (const metodo of ['log', 'info'] as const) {
    const original = console[metodo]
    console[metodo] = (...args: unknown[]) => {
      if (esAviso(args[0])) return
      original.apply(console, args as Parameters<typeof console.log>)
    }
  }
}

export {}
