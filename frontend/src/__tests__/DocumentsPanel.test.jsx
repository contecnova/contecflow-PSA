import { vi, describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DocumentsPanel from '../components/DocumentsPanel';

vi.mock('../context/ToastContext', () => ({
  useToast: () => ({ show: vi.fn() }),
}));

vi.mock('../context/ConfirmContext', () => ({
  openConfirmGlobal: vi.fn().mockResolvedValue(true),
}));

// Some child may import AppLangContext as default or named export
vi.mock('../i18n/AppLangContext', () => {
  const ctx = { _currentValue: null };
  return {
    default: ctx,
    AppLangContext: ctx,
    useAppT: () => (key) => key,
    useAppLang: () => ({ t: (key) => key, lang: 'es' }),
  };
});

vi.mock('../services/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    patch: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

describe('DocumentsPanel', () => {
  it('renderiza el panel de documentos', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <DocumentsPanel entityType="project" entityId="proj-1" />
      </QueryClientProvider>
    );
    expect(container.firstChild).toBeDefined();
  });
});
