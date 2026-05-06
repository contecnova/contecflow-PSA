import re, os

BASE = "/Users/oriolvallsanton/Code/contecflow-PSA/frontend/src/pages"

FILES = [
    "AIHubPage.jsx",
    "ALMPage.jsx",
    "AgentDashboardPage.jsx",
    "AlertsPage.jsx",
    "BPMPage.jsx",
    "CalendarPage.jsx",
    "ChangelogPage.jsx",
    "ChangesPage.jsx",
    "ClientPortalPage.jsx",
    "DataExplorerPage.jsx",
    "DataGovernancePage.jsx",
    "DataPlatformPage.jsx",
    "DeveloperPortalPage.jsx",
    "EnterprisePage.jsx",
    "EpicGanttPage.jsx",
    "EpicsPage.jsx",
    "ExportsPage.jsx",
    "GanttPage.jsx",
    "GovernancePage.jsx",
    "ImportPage.jsx",
    "ImputarPage.jsx",
    "InboxPage.jsx",
    "InternalCommentsPage.jsx",
    "JiraIntegrationPage.jsx",
    "KanbanAdvancedPage.jsx",
    "MFAPage.jsx",
    "MeetingsAIPage.jsx",
    "MentionsPage.jsx",
    "MilestoneBillingPage.jsx",
    "NPSPage.jsx",
    "NexusAgentPage.jsx",
    "NotificationsPage.jsx",
    "OKRsPage.jsx",
    "OraclePage.jsx",
    "OrganizationsPage.jsx",
    "PerformanceReviewsPage.jsx",
    "PipelinePage.jsx",
    "PredictionsPage.jsx",
    "ProfitabilityPage.jsx",
    "ProjectTemplatesPage.jsx",
    "ReportBuilderPage.jsx",
    "RiskScoresPage.jsx",
    "ScenariosPage.jsx",
    "SearchPage.jsx",
    "SemanticEnginePage.jsx",
    "SettingsPage.jsx",
    "SettingsPageSections.jsx",
    "SprintChartsPage.jsx",
    "SprintPlanningPage.jsx",
    "SprintsPage.jsx",
    "TimesheetsPage.jsx",
    "UATPage.jsx",
    "WikiPage.jsx",
    "WorkflowsPage.jsx",
    "service-desk/WorkflowDesignerPage.jsx",
]

modified = []
skipped = []
errors = []

for rel in FILES:
    path = os.path.join(BASE, rel)
    if not os.path.exists(path):
        errors.append(f"NOT FOUND: {rel}")
        continue
    with open(path, 'r') as f:
        content = f.read()

    # Check if showListExport is already present
    if 'showListExport' in content:
        skipped.append(f"ALREADY HAS showListExport: {rel}")
        continue

    lines = content.split('\n')
    ph_line_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('<PageHeader') and 'import' not in line:
            ph_line_idx = i
            break

    if ph_line_idx is None:
        errors.append(f"No JSX PageHeader found: {rel}")
        continue

    # Find the closing /> starting from ph_line_idx
    close_line_idx = None
    for i in range(ph_line_idx, min(ph_line_idx + 20, len(lines))):
        if '/>' in lines[i]:
            close_line_idx = i
            break

    if close_line_idx is None:
        errors.append(f"No closing /> found within 20 lines: {rel}")
        continue

    line = lines[close_line_idx]
    pos = line.rfind('/>')
    if pos == -1:
        errors.append(f"No /> found in line {close_line_idx}: {rel}")
        continue

    if close_line_idx == ph_line_idx:
        lines[close_line_idx] = line[:pos] + 'showListExport={false} />' + line[pos+2:]
    else:
        before = line[:pos].rstrip()
        after = line[pos+2:]
        lines[close_line_idx] = before + ' showListExport={false} />' + after

    new_content = '\n'.join(lines)
    with open(path, 'w') as f:
        f.write(new_content)
    modified.append(rel)

print("MODIFIED:", len(modified))
for m in modified:
    print(" ", m)
print("\nSKIPPED:", len(skipped))
for s in skipped:
    print(" ", s)
print("\nERRORS:", len(errors))
for e in errors:
    print(" ", e)
