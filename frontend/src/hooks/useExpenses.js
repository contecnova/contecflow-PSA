import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { expensesApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useMyExpenses(params = {}) {
  return useQuery({
    queryKey: ['expenses-my', params],
    queryFn: () => expensesApi.my(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useTeamExpenses(params = {}) {
  return useQuery({
    queryKey: ['expenses-team', params],
    queryFn: () => expensesApi.list(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function usePendingExpenses() {
  return useQuery({
    queryKey: ['expenses-pending'],
    queryFn: () => expensesApi.pending().then(r => r.data),
    staleTime: STALE,
  })
}

export function useCreateExpense() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => expensesApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['expenses'] }),
  })
}

export function useUpdateExpense() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => expensesApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['expenses'] }),
  })
}

export function useApproveExpense() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => expensesApi.approve(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['expenses'] }),
  })
}

export function useDeleteExpense() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => expensesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['expenses'] }),
  })
}
