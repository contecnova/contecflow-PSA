import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
import { expensesApi } from '../services/api'
import type { Gasto } from '../services/api/tipos-finanzas'

const STALE = 2 * 60 * 1000

/** serialize_expense (services/api/tipos-finanzas.ts). */
export type Expense = Gasto

export type ExpenseListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }

export function useMyExpenses(params: ExpenseListParams = {}): UseQueryResult<Expense[]> {
  return useQuery<Expense[]>({
    queryKey: ['expenses-my', params],
    queryFn: () => expensesApi.my(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useTeamExpenses(params: ExpenseListParams = {}): UseQueryResult<Expense[]> {
  return useQuery({
    queryKey: ['expenses-team', params],
    queryFn: () => expensesApi.list(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function usePendingExpenses(): UseQueryResult<Expense[]> {
  return useQuery({
    queryKey: ['expenses-pending'],
    queryFn: () => expensesApi.pending().then(r => r.data),
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
