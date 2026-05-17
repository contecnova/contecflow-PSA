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

declare module '@tanstack/react-query' {
  export class QueryClient {
    constructor(...args: any[])
  }

  export function useQuery<TData = any, TError = any, TSelected = TData>(...args: any[]): any
  export function useMutation<TData = any, TError = any, TVariables = any, TContext = any>(...args: any[]): any
  export const useQueryClient: (...args: any[]) => any
  export const useQueries: (...args: any[]) => any
  export const useInfiniteQuery: (...args: any[]) => any
  export const QueryClientProvider: any

  export type UseQueryResult<TData = any, TError = any> = any
  export type UseMutationResult<TData = any, TError = any, TVariables = any, TContext = any> = any
}
