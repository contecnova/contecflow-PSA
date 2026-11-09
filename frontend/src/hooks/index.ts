/**
 * Hooks index — re-exports all React Query hooks for the application.
 * Import from here: `import { useTasks, useCreateTask } from '../hooks'`
 */

export {
	useMyAbsences, usePendingAbsences, useTeamAbsences, useAbsenceCalendar,
} from './useAbsences'
export { useAlerts, useReadAlert, useResolveAlert, useRunAlerts } from './useAlerts'
export {
	useAnalyticsQuery, useAnalyticsFilterOptions, useHoursWeek, useUtilization, useMetricBreaches,
	useAnalyticsNarrative, useOlapKpis, useOlapPipelineFunnel, useOlapPortfolioHealth,
	useOlapMarginEvolution, useOlapUtilization, useAnalyticsCatalogue,
} from './useAnalytics'
export {
	useApprovalWorkflows, useApprovalWorkflow, useApprovalTemplates, useCreateApprovalWorkflow,
	useUpdateApprovalWorkflow, useDeleteApprovalWorkflow, usePublishApprovalWorkflow,
	useApprovalRequests, usePendingApprovalRequests, useApprovalStats, useCreateApprovalRequest,
	useApproveRequest, useRejectRequest, useCancelApprovalRequest, useApprovalGroups,
	useCreateApprovalGroup, useUpdateApprovalGroup, useDeleteApprovalGroup,
} from './useApprovals'
export { useAssets, useAllAssets, useAsset, useCreateAsset, useUpdateAsset, useDeleteAsset } from './useAssets'
export { useChanges, useAllChanges, useChange, useCreateChange, useUpdateChange, useApproveChange, useDeleteChange } from './useChanges'
export { useClients, useAllClients, useClient, useCreateClient, useUpdateClient, useDeleteClient } from './useClients'
export { useContracts, useAllContracts, useContract, useCreateContract, useUpdateContract, useDeleteContract } from './useContracts'
export { useKpis, useProjectsHealth, useResourceLoad, useProfitability, useTeamProductivity } from './useDashboard'
export { useEpics, useAllEpics, useCreateEpic, useUpdateEpic, useDeleteEpic } from './useEpics'
export {
	useMyExpenses, useTeamExpenses, usePendingExpenses, useCreateExpense, useUpdateExpense,
	useReimburseExpense, useSubmitExpense, useRecallExpense, useExpenseOCR,
} from './useExpenses'
export {
	useForecastHeatmap, useForecastUserDetail, useForecastAvailability, useForecastSummary,
	useBiForecastingMetrics, useBiForecast, useBiMultiForecast,
} from './useForecasts'
export {
	useMyWeek, useImputations, useCreateImputation, useDeleteImputation, useUpdateImputation,
	useApproveImputation, useRejectImputation, useTimerCurrent, useStartTimer, usePauseTimer,
	useResumeTimer, useStopTimer, useCancelTimer,
} from './useImputations'
export { useLicenses, useAllLicenses, useLicense, useCreateLicense, useUpdateLicense, useAssignLicense, useDeleteLicense } from './useLicenses'
export { useMilestones, useMilestoneDashboard, useCreateMilestone, useUpdateMilestone, useCompleteMilestone, useDeleteMilestone } from './useMilestones'
export { useOKRs, useCreateOKR, useUpdateOKR, useDeleteOKR } from './useOKRs'
export { useProblems, useAllProblems, useCreateProblem, useUpdateProblem, useDeleteProblem } from './useProblems'
export {
	useProjects, useAllProjects, useProject, useCreateProject, useUpdateProject, useDeleteProject,
	useProjectTeam, useProjectMembers, useProjectEVM, useProjectEVMPortfolio,
	useAddProjectMember, useRemoveProjectMember,
} from './useProjects'
export {
	useRateCards, useRateCard, useEffectiveRate, useCreateRateCard, useUpdateRateCard,
	useDeleteRateCard, useDuplicateRateCard, useAddRateCardEntry,
	useUpdateRateCardEntry, useDeleteRateCardEntry,
} from './useRateCards'
export { useRisks, useAllRisks, useRisk, useCreateRisk, useUpdateRisk, useDeleteRisk } from './useRisks'
export { useSprints, useAllSprints } from './useSprints'
export { useSubcontractors, useAllSubcontractors, useCreateSubcontractor, useUpdateSubcontractor, useDeleteSubcontractor } from './useSubcontractors'
export {
	useTasks, useTask, useKanban, useCreateTask, useUpdateTask,
	useDeleteTask, useBulkUpdateTasks, useAddTaskComment, useTaskMovementLog,
} from './useTasks'
export {
	useTickets, useTicket, useCreateTicket, useUpdateTicket, useCommentTicket,
	useTicketMyQueue, useEscalateTicket, 
	 useTicketTimelog, useAiSuggestTicket,
} from './useTickets'
export {
	useTrainingCourses, useTrainingCerts, useTrainingEnrollments, useCreateCourse,
	useUpdateCourse, useDeleteCourse, useCreateCert, useUpdateCert,
	useDeleteCert, useEnroll,
} from './useTraining'
export { useUsers, useAllUsers, useUser, useCreateUser, useUpdateUser, useDeactivateUser } from './useUsers'
export { useVendors, useAllVendors, useCreateVendor, useUpdateVendor, useDeleteVendor } from './useVendors'
export {
	usePipeline, useOpportunity, useCreateOpportunity, useUpdateOpportunity,
	useDeleteOpportunity, useGenerateProposal, useMarkProposalSent, useConvertToProject,
} from './usePipeline'

// Utility / UI hooks (not query-related) — exported for convenience
export { useInvalidate } from './useInvalidate'
export { useFormValidation } from './useFormValidation'
export { useIdleTimeout } from './useIdleTimeout'
export { default as useMediaQuery } from './useMediaQuery'
export { useNotificationBadges } from './useNotificationBadges'
export { default as useOfflineSync } from './useOfflineSync'
export { useOnlineStatus } from './useOnlineStatus'
export { useOrgSettings } from './useOrgSettings'
export { useSwipeGesture } from './useSwipeGesture'
export { useUserPreferences } from './useUserPreferences'
export { useDocCollab } from './useDocCollab'
export { useAppT } from './useAppT'
