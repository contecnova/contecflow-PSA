import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppLangProvider } from './i18n/AppLangContext'
import { AuthProvider } from './context/AuthContext'
import { ToastProvider } from './context/ToastContext'
import { ConfirmProvider } from './context/ConfirmContext'
import ChatRealtimeProvider from './context/ChatRealtimeContext'

/**
 * Composición única de providers globales — resuelve audit #112 "provider hell".
 *
 * Orden requerido:
 *   AppLang -> Toast -> Confirm -> Auth -> QueryClient -> ChatRealtime
 *
 * - Toast antes que Auth: AuthContext puede emitir toasts en flujos de login fallido.
 * - Confirm tras Toast (solo necesita AppLang): único proveedor de diálogos de
 *   confirmación; antes estaba duplicado en App.tsx creando un árbol de contextos paralelo.
 * - Auth antes que QueryClient: queries autenticadas leen el token del AuthContext.
 * - QueryClient antes que ChatRealtime: el WebSocket invalida queries al recibir eventos.
 */
interface AppProvidersProps {
  queryClient: QueryClient
  children: ReactNode
}

export default function AppProviders({ queryClient, children }: AppProvidersProps) {
  return (
    <AppLangProvider>
      <ToastProvider>
        <ConfirmProvider>
          <AuthProvider>
            <QueryClientProvider client={queryClient}>
              <ChatRealtimeProvider>
                {children}
              </ChatRealtimeProvider>
            </QueryClientProvider>
          </AuthProvider>
        </ConfirmProvider>
      </ToastProvider>
    </AppLangProvider>
  )
}
