import re, os

BASE = "/Users/oriolvallsanton/Code/contecflow-PSA/frontend/src/pages"

# Files where showListExport ended up INSIDE the icon prop (wrongly placed)
WRONG_FILES = [
    "AIHubPage.jsx",
    "ALMPage.jsx",
    "AgentDashboardPage.jsx",
    "AlertsPage.jsx",
    "BPMPage.jsx",
    "ClientPortalPage.jsx",
    "DataExplorerPage.jsx",
    "DataGovernancePage.jsx",
    "DataPlatformPage.jsx",
    "DeveloperPortalPage.jsx",
    "EnterprisePage.jsx",
    "EpicGanttPage.jsx",
    "EpicsPage.jsx",
    "GanttPage.jsx",
    "ImputarPage.jsx",
    "InboxPage.jsx",
    "JiraIntegrationPage.jsx",
    "KanbanAdvancedPage.jsx",
    "MeetingsAIPage.jsx",
    "MilestoneBillingPage.jsx",
    "NPSPage.jsx",
    "NexusAgentPage.jsx",
    "NotificationsPage.jsx",
    "OKRsPage.jsx",
    "OraclePage.jsx",
    "PerformanceReviewsPage.jsx",
    "PredictionsPage.jsx",
    "ProfitabilityPage.jsx",
    "ProjectTemplatesPage.jsx",
    "ReportBuilderPage.jsx",
    "SearchPage.jsx",
    "SemanticEnginePage.jsx",
    "SprintChartsPage.jsx",
    "SprintPlanningPage.jsx",
    "UATPage.jsx",
    "WikiPage.jsx",
    "WorkflowsPage.jsx",
    "service-desk/WorkflowDesignerPage.jsx",
]

modified = []
errors = []

for rel in WRONG_FILES:
    path = os.path.join(BASE, rel)
    if not os.path.exists(path):
        errors.append(f"NOT FOUND: {rel}")
        continue
    with open(path, 'r') as f:
        lines = f.readlines()

    # Step 1: Remove showListExport={false} from inside the icon prop line
    # Pattern: size={N} showListExport={false} />
    icon_fixed = False
    for i, line in enumerate(lines):
        if 'showListExport={false}' in line and 'icon={<' in line:
            lines[i] = line.replace(' showListExport={false}', '')
            icon_fixed = True
            break

    if not icon_fixed:
        errors.append(f"Could not find icon line to fix: {rel}")
        continue

    # Step 2: Find the <PageHeader JSX line index
    ph_line_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('<PageHeader') and 'import' not in line:
            ph_line_idx = i
            break

    if ph_line_idx is None:
        errors.append(f"No JSX PageHeader found: {rel}")
        continue

    # Step 3: Find the standalone closing /> for PageHeader (line with only whitespace + />)
    close_line_idx = None
    for i in range(ph_line_idx + 1, min(ph_line_idx + 40, len(lines))):
        stripped = lines[i].strip()
        if stripped == '/>':
            close_line_idx = i
            break

    if close_line_idx is None:
        errors.append(f"No standalone /> found for PageHeader: {rel}")
        continue

    # Step 4: Add showListExport={false} as a new line before the closing />
    # Get the indentation of the closing />
    indent = len(lines[close_line_idx]) - len(lines[close_line_idx].lstrip())
    indent_str = ' ' * indent
    new_line = f"{indent_str}showListExport={{false}}\n"
    lines.insert(close_line_idx, new_line)

    with open(path, 'w') as f:
        f.writelines(lines)
    modified.append(rel)

print("FIXED:", len(modified))
for m in modified:
    print(" ", m)
print("\nERRORS:", len(errors))
for e in errors:
    print(" ", e)
