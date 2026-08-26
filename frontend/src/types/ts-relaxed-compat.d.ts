import 'react'

declare module '*.css' {
  const css: string
  export default css
}

declare global {
  interface ImportMetaEnv {
    readonly DEV: boolean
    readonly PROD: boolean
    readonly [key: string]: boolean | string | undefined
  }

  interface ImportMeta {
    readonly env: ImportMetaEnv
    readonly hot?: {
      decline: () => void
    }
  }
}

declare module 'react' {
  interface HTMLAttributes<T> {
    style?: any
  }

  interface SVGAttributes<T> {
    style?: any
  }

  interface CSSProperties {
    [key: string]: string | number | undefined | null
  }
}
