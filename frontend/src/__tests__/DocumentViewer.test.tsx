import { vi, describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DocumentViewer from '../components/DocumentViewer';

vi.mock('../i18n/AppLangContext', () => ({
  useAppT: () => (key) => key,
  useAppLang: () => ({ t: (key) => key, lang: 'es' }),
}));

vi.mock('../context/ToastContext', () => ({
  useToast: () => ({ show: vi.fn() }),
}));

vi.mock('../services/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: null }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    patch: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

describe('DocumentViewer', () => {
  it('renderiza el visor de documentos', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <DocumentViewer />
      </QueryClientProvider>
    );
    expect(container.firstChild).toBeDefined();
  });
});
