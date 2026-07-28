// Provee una implementación de IndexedDB en jsdom (que no lo trae). Necesario para
// el código basado en Dexie (offline sync, AppLangProvider); sin esto los tests
// fallan con "IndexedDB API missing". Debe cargarse antes que cualquier módulo Dexie.
import 'fake-indexeddb/auto';

// Register @testing-library/jest-dom matchers for all test files
// (toBeInTheDocument, toHaveTextContent, toHaveValue, etc.)
import '@testing-library/jest-dom';
