# NexusPM SDK

Official client libraries for the NexusPM REST API.

---

## Python SDK

### Installation

```bash
pip install requests      # only dependency
# Copy sdk/python/nexuspm_sdk.py into your project
```

### Quick start

```python
from nexuspm_sdk import NexusPMClient

client = NexusPMClient(
    base_url="https://nexuspm.example.com",
    token="your-jwt-token",          # or set NEXUSPM_TOKEN env var
)

# List projects
projects = client.projects.list(status="active")

# Create a task
task = client.tasks.create(
    project_id="proj-123",
    title="Implement feature X",
    status="todo",
    priority="high",
)

# Log hours
client.imputations.create(
    task_id=task["id"],
    user_id="usr-456",
    hours=4.5,
    date="2024-06-15",
    notes="Initial implementation",
)

# AI overrun prediction
prediction = client.ai.overrun_prediction("proj-123")
print(f"Cost overrun probability: {prediction['cost_overrun_prob']:.0%}")
print(f"Schedule delay: {prediction['schedule_overrun_days']} days")
print(f"Recommendation: {prediction['recommendation']}")

# Revenue journal entries (ASC 606 / IFRS 15)
journal = client.financials.revenue_journal("proj-123")
for line in journal["journal_lines"]:
    print(f"{line['line']} {line['account_code']} {line['account_name']}: {line['debit'] or line['credit']}")

# Export journal to CSV
csv_data = client.financials.revenue_journal_csv("proj-123")
with open("journal.csv", "w") as f:
    f.write(csv_data)

# Jira integration
client.jira.save_config(
    jira_url="https://mycompany.atlassian.net",
    jira_email="admin@mycompany.com",
    jira_api_token="ATATT3xFfGF0...",
    jira_project_key="MYP",
)
status = client.jira.test_connection()
if status["ok"]:
    result = client.jira.sync_from_jira()
    print(f"Synced: {result['created']} created, {result['updated']} updated")
```

### Authentication

```python
# With environment variable (recommended for production)
import os
os.environ["NEXUSPM_TOKEN"] = "your-jwt"
client = NexusPMClient(base_url="https://nexuspm.example.com")

# Login programmatically
client = NexusPMClient(base_url="https://nexuspm.example.com")
token = client.login("admin@example.com", "password")
```

### Error handling

```python
from nexuspm_sdk import NexusPMError, AuthError, NotFoundError

try:
    project = client.projects.get("nonexistent")
except NotFoundError:
    print("Project not found")
except AuthError:
    print("Authentication failed — check your token")
except NexusPMError as e:
    print(f"API error {e.status_code}: {e}")
```

---

## JavaScript SDK

### Installation

```bash
# Copy sdk/javascript/nexuspm_sdk.js into your project
# Requires fetch (Node.js 18+ or any browser)
```

### Quick start

```javascript
import { NexusPMClient } from './nexuspm_sdk.js'

const client = new NexusPMClient({
  baseUrl: 'https://nexuspm.example.com',
  token:   'your-jwt-token',   // or set NEXUSPM_TOKEN env var
})

// List projects
const projects = await client.projects.list({ status: 'active' })

// Create a task
const task = await client.tasks.create({
  projectId: 'proj-123',
  title:     'Implement feature X',
  status:    'todo',
})

// Log hours
await client.imputations.create({
  taskId: task.id,
  userId: 'usr-456',
  hours:  4.5,
  date:   '2024-06-15',
})

// AI overrun prediction
const prediction = await client.ai.overrunPrediction('proj-123')
console.log(`Cost overrun: ${(prediction.cost_overrun_prob * 100).toFixed(0)}%`)

// Revenue journal
const journal = await client.financials.revenueJournal('proj-123')
console.log(`Total recognised: €${journal.summary.total_recognised}`)

// Jira integration
await client.jira.saveConfig({
  jira_url:         'https://mycompany.atlassian.net',
  jira_email:       'admin@mycompany.com',
  jira_api_token:   'ATATT3xFfGF0...',
  jira_project_key: 'MYP',
})
const sync = await client.jira.syncFromJira()
console.log(`Synced ${sync.created} tasks from Jira`)
```

### Authentication

```javascript
// Login programmatically
const client = new NexusPMClient({ baseUrl: 'https://nexuspm.example.com' })
const token = await client.login('admin@example.com', 'password')

// With environment variable (Node.js)
process.env.NEXUSPM_TOKEN = 'your-jwt'
const client = new NexusPMClient({ baseUrl: 'https://nexuspm.example.com' })
```

### Error handling

```javascript
import { NexusPMClient, AuthError, NotFoundError, NexusPMError } from './nexuspm_sdk.js'

try {
  const project = await client.projects.get('nonexistent')
} catch (e) {
  if (e instanceof NotFoundError) console.error('Project not found')
  else if (e instanceof AuthError) console.error('Auth failed')
  else if (e instanceof NexusPMError) console.error(`API error ${e.statusCode}: ${e.message}`)
  else throw e
}
```

---

## API Reference — Resources

| Namespace | Methods |
|-----------|---------|
| `projects` | `list(opts)`, `get(id)`, `create(data)`, `update(id, data)`, `delete(id)` |
| `tasks` | `list(opts)`, `get(id)`, `create(data)`, `update(id, data)`, `bulkUpdateDates(updates)` |
| `imputations` | `list(opts)`, `create(data)`, `update(id, data)`, `delete(id)` |
| `users` | `list(opts)`, `get(id)`, `me()` |
| `resources` | `list()`, `get(id)`, `capacity(id, start, end)`, `utilizationTrend()` |
| `financials` | `profitability(projectId)`, `evm(projectId)`, `revenueJournal(projectId)`, `revenueJournalCsv(projectId)`, `milestoneBilling(projectId)`, `invoices(opts)` |
| `ai` | `overrunPrediction(projectId)`, `chat(message, context)`, `summarizeProject(projectId)`, `detectBurnout()` |
| `jira` | `config()`, `saveConfig(data)`, `testConnection()`, `issues(jql?)`, `syncFromJira(projectId?)`, `pushToJira()`, `linkedTasks()` |

---

## Environment variables

| Variable | Description |
|----------|-------------|
| `NEXUSPM_TOKEN` | JWT access token used when no `token` is passed to the constructor |

---

## Versioning

SDK version `1.0.0` is compatible with NexusPM API v23.4+.
