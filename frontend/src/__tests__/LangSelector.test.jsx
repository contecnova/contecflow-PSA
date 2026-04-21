import { toHaveStyle } from '@testing-library/jest-dom/matchers';
expect.extend({ toHaveStyle });
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import LangSelector from '../components/LangSelector';
import { AppLangProvider } from '../i18n/AppLangContext';
import { AuthProvider } from '../context/AuthContext';
import { MemoryRouter } from 'react-router-dom';

import { APP_LANGUAGES } from '../i18n/appTranslations';

describe('LangSelector', () => {
  beforeEach(() => {
    render(
      <MemoryRouter>
        <AuthProvider>
          <AppLangProvider>
            <LangSelector />
          </AppLangProvider>
        </AuthProvider>
      </MemoryRouter>
    );
  });

  afterEach(() => {
    cleanup();
  });

  APP_LANGUAGES.forEach(({ code, label }) => {
    it(`permite cambiar a ${label} (${code})`, async () => {
      const btn = await screen.findByLabelText(label);
      fireEvent.click(btn);
      // El botón debe estar activo (opacity 1)
      expect(btn).toHaveStyle({ opacity: 1 });
    });
  });
});
