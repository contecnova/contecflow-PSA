import { describe, it, expect } from 'vitest'
import {
  deepMergeTranslations,
  humanizeFallbackKey,
  resolveTranslation,
} from '../translationRuntime.mjs'

describe('translationRuntime', () => {
  it('deepMergeTranslations preserves nested fallback keys', () => {
    const base = {
      tasks: {
        filters: {
          all_projects: 'All projects',
          all_assignees: 'All assignees',
        },
      },
    }
    const override = {
      tasks: {
        filters: {
          all_projects: 'Tous les projets',
        },
      },
    }

    const merged = deepMergeTranslations(base, override)

    expect(merged.tasks.filters.all_projects).toBe('Tous les projets')
    expect(merged.tasks.filters.all_assignees).toBe('All assignees')
  })

  it('resolveTranslation falls back to english/spanish before humanized key', () => {
    const value = resolveTranslation({
      lang: 'fr',
      moduleName: 'tasks',
      keyPath: ['all_projects'],
      runtimeTranslations: { tasks: {} },
      baseTranslations: { tasks: {} },
      englishTranslations: { tasks: { all_projects: 'All projects' } },
      spanishTranslations: { tasks: { all_projects: 'Todos los proyectos' } },
    })

    expect(value).toBe('All projects')
  })

  it('humanizes leaked keys when no fallback exists', () => {
    const value = resolveTranslation({
      lang: 'fr',
      moduleName: 'tasks',
      keyPath: ['filter_priority'],
      runtimeTranslations: { tasks: {} },
      baseTranslations: { tasks: {} },
      englishTranslations: { tasks: {} },
      spanishTranslations: { tasks: {} },
    })

    expect(value).toBe('Filter priority')
    expect(humanizeFallbackKey('all_assignees')).toBe('All assignees')
  })
})
