import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { expensesApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface Expense {
  id: string
  amount?: number
  status?: string
  [extra: string]: unknown
}

export type ExpenseListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }

function unwrapList<T>(r: { data?: { items?: T[] } | T[] | null }): T[] {
  const d = r?.data
  if (Array.isArray(d)) return d
  return d?.items ?? []
}

export function useMyExpenses(params: ExpenseListParams = {}): UseQueryResult<Expense[]> {
  return useQuery<Expense[]>({
    queryKey: ['expenses-my', params],
    queryFn: () => expensesApi.my(params).then((r: { data?: { items?: Expense[] } | Expense[] | null }) => unwrapList<Expense>(r)),
    staleTime: STALE,
  })
}

export function useTeamExpenses(params: ExpenseListParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['expenses-team', params],
    queryFn: () => expensesApi.list(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function usePendingExpenses(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['expenses-pending'],
    queryFn: () => expensesApi.pending().then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useCreateExpense(): UseMutationResult<unknown, unknown, Partial<Expense>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Expense>) => expensesApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['expenses'] }),
  })
}

export function useUpdateExpense(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<Expense>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<Expense>>) => expensesApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['expenses'] }),
  })
}

export function useReimburseExpense(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => expensesApi.reimburse(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['expenses'] }),
  })
}

export function useSubmitExpense(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => expensesApi.submitMy(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['expenses-my'] })
      qc.invalidateQueries({ queryKey: ['expenses-pending'] })
    },
  })
}

export function useRecallExpense(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => expensesApi.recall(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['expenses-my'] }),
  })
}

export function useExpenseOCR(): UseMutationResult<unknown, unknown, FormData> {
  return useMutation({
    mutationFn: (fd: FormData) => expensesApi.ocr(fd),
  })
}
