import { QueryClientProvider } from '@tanstack/react-query'
import { AppLangProvider } from './i18n/AppLangContext'
import { AuthProvider } from './context/AuthContext'
import { ToastProvider } from './context/ToastContext'
import ChatRealtimeProvider from './context/ChatRealtimeContext'

/**
 * Composición única de providers globales — resuelve audit #112 "provider hell".
 *
 * Orden requerido:
 *   AppLang -> Toast -> Auth -> QueryClient -> ChatRealtime
 *
 * - Toast antes que Auth: AuthContext puede emitir toasts en flujos de login fallido.
 * - Auth antes que QueryClient: queries autenticadas leen el token del AuthContext.
 * - QueryClient antes que ChatRealtime: el WebSocket invalida queries al recibir eventos.
 */
export default function AppProviders({ queryClient, children }) {
  return (
    <AppLangProvider>
      <ToastProvider>
        <AuthProvider>
          <QueryClientProvider client={queryClient}>
            <ChatRealtimeProvider>
              {children}
            </ChatRealtimeProvider>
          </QueryClientProvider>
        </AuthProvider>
      </ToastProvider>
    </AppLangProvider>
  )
}
