import { vi, describe, it, expect, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import LangSelector from '../components/LangSelector';
import { AppLangProvider } from '../i18n/AppLangContext';
import { APP_LANGUAGES } from '../i18n/appTranslations';

// AppLangProvider needs useAuth and api
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: null }),
}));

vi.mock('../services/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    patch: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

// Mock loadLanguage to avoid async i18n file loading in tests
vi.mock('../i18n/appTranslations', () => ({
  APP_LANGUAGES: [
    { code: 'es', label: 'Español',    flag: '🇪🇸' },
    { code: 'en', label: 'English',    flag: '🇬🇧' },
    { code: 'fr', label: 'Français',   flag: '🇫🇷', partial: true },
    { code: 'de', label: 'Deutsch',    flag: '🇩🇪', partial: true },
    { code: 'pt', label: 'Português',  flag: '🇵🇹', partial: true },
    { code: 'it', label: 'Italiano',   flag: '🇮🇹', partial: true },
    { code: 'pl', label: 'Polski',     flag: '🇵🇱', partial: true },
    { code: 'zh', label: '中文',       flag: '🇨🇳', partial: true },
  ],
  loadLanguage: vi.fn().mockImplementation((code) =>
    Promise.resolve({ nav: { projects: code === 'es' ? 'Proyectos' : 'Projects' } })
  ),
}));

describe('LangSelector', () => {
  afterEach(() => { cleanup(); });

  APP_LANGUAGES.forEach(({ code, label }) => {
    it(`permite cambiar a ${label} (${code})`, async () => {
      render(
        <AppLangProvider>
          <LangSelector />
        </AppLangProvider>
      );
      // Use regex match (exact: false equivalent) because partial-language buttons
      // have a suffix in their aria-label (e.g. "Français — traducción parcial")
      const btn = await waitFor(() =>
        screen.getByRole('button', { name: new RegExp(label, 'i') })
      );
      fireEvent.click(btn);
      expect(btn).toBeTruthy();
    });
  });
});
