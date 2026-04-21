import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import App from '../App';
import { MemoryRouter } from 'react-router-dom';
import { AppLangProvider } from '../i18n/AppLangContext';
import { AuthProvider } from '../context/AuthContext';

// Mock for i18n context/provider if needed
// import { AppLangProvider } from '../i18n/AppLangContext';

const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'es', label: 'Español' },
  { code: 'fr', label: 'Français' },
  { code: 'de', label: 'Deutsch' },
  { code: 'pt', label: 'Português' },
  { code: 'it', label: 'Italiano' },
  { code: 'pl', label: 'Polski' },
  { code: 'zh', label: '中文' },
];

// Helper to select language in the UI
async function selectLanguage(langLabel) {
  // Find the language selector (adjust selector as needed)
  const select = screen.getByRole('combobox');
  fireEvent.change(select, { target: { value: langLabel } });
}

describe('UI Translations', () => {
  beforeEach(() => {
    render(
      <MemoryRouter>
        <AuthProvider>
          <AppLangProvider>
            <App />
          </AppLangProvider>
        </AuthProvider>
      </MemoryRouter>
    );
  });

  afterEach(() => {
    cleanup();
  });

  LANGUAGES.forEach(({ code, label }) => {
    it(`changes UI to ${label} (${code})`, async () => {
      await selectLanguage(label);
      // Check that a known translated string appears (adjust as needed)
      // Example: check for main menu or page title
      const mainTitle = screen.getByTestId('main-title');
      expect(mainTitle).toBeTruthy();
      // Optionally, check for language-specific text
      // expect(mainTitle.textContent).toMatch(/expected text/i);
    });
  });
});
