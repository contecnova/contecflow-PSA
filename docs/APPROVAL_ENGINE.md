# Approval Engine — State Machine Documentation

**Created:** May 8, 2026  
**Status:** Production  
**Location:** `app/services/approval_engine.py` (1,685 LOC)  

---

## 📊 State Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ APPROVAL REQUEST LIFECYCLE                                      │
└─────────────────────────────────────────────────────────────────┘

                    ┏━━━━━━━━━━━━━━━┓
                    ┃  DRAFT        ┃  ← Initial state
                    ┃  ════════════  ┃     (editable by requester)
                    ┗━━━━━━━┳━━━━━━━┛
                             │ submit()
                             ↓
                    ┏━━━━━━━━━━━━━━━┓
                    ┃  PENDING      ┃  ← Waiting for approvers
                    ┃  ════════════  ┃
                    ┗━━━━━┳━━━━━┳━━━━┛
            ┌──────────────┼──────────────┐
            ↓              ↓              ↓
        ┏─────────┓   ┏─────────┓   ┏─────────┐
        ┃ APPROVED┃   ┃ REJECTED┃   ┃ EXPIRED┃
        ┃═════════┃   ┃═════════┃   ┃════════┃
        ┗────┬────┘   ┗────┬────┘   ┗────┬───┘
             │             │             │
             ├─────────────┴─────────────┤
             ↓                           ↓
        ┏──────────────────────────────────────┐
        ┃  ARCHIVED (or CANCELLED/REVOKED)    ┃
        ┃  ════════════════════════════════════ ┃
        ┗──────────────────────────────────────┘

Key transitions:
  • DRAFT → PENDING:  submit() called by requester
  • PENDING → APPROVED: all approvers approve OR auto-approval threshold met
  • PENDING → REJECTED:  any required approver rejects
  • PENDING → EXPIRED:   due_date passed without final decision
  • Any → ARCHIVED:      explicit archive action OR auto-cleanup
  • DRAFT → CANCELLED:   requester cancels before submission
```

---

## 🔄 Detailed State Transitions

### **DRAFT** (Initial)
- **Allowed actions:**
  - `submit()`: Move to PENDING (locks request for editing)
  - `cancel()`: Move to CANCELLED (soft delete)
  - Edit fields (on the request directly)
  
- **Permissions:**
  - Only requester can modify
  
- **Characteristics:**
  - Request can be edited before submission
  - No approvers assigned yet (or assigned but not active)

---

### **PENDING** (Active)
- **Allowed actions:**
  - `approve(approver_id, comment)`: Approver votes YES
  - `reject(approver_id, reason)`: Approver votes NO
  - `recall()`: Requester takes back (return to DRAFT)
  - `escalate()`: Send to higher authority
  
- **Transitions:**
  - If ALL required approvers vote YES → **APPROVED**
  - If ANY required approver votes NO → **REJECTED**
  - If due_date passed → **EXPIRED**
  - If delegated approver reviews after time limit → **EXPIRED**
  
- **Permissions:**
  - Approvers assigned to step(s) can vote
  - Requester can recall if not yet approved/rejected
  
- **Characteristics:**
  - Read-only to requester (cannot modify)
  - Voting is recorded in `ApprovalRequestStep` records
  - Audit trail logged for each action

---

### **APPROVED** (Terminal)
- **Allowed actions:**
  - `execute()`: Run the associated workflow/action
  - `archive()`: Move to ARCHIVED
  
- **Permissions:**
  - Executor/admin can trigger execution
  
- **Characteristics:**
  - All approvals satisfied
  - Ready for implementation
  - Can be executed immediately or scheduled

---

### **REJECTED** (Terminal)
- **Allowed actions:**
  - `archive()`: Move to ARCHIVED
  - `resubmit()`: Go back to PENDING (optional, depends on policy)
  
- **Permissions:**
  - Admin can resubmit if policy allows
  
- **Characteristics:**
  - At least one required approver voted NO
  - Cannot proceed without resubmission
  - Reason logged in step record

---

### **EXPIRED** (Terminal)
- **Allowed actions:**
  - `archive()`: Move to ARCHIVED
  - `resubmit()`: Move back to PENDING (request fresh approvals)
  
- **Permissions:**
  - Requester or admin can resubmit
  
- **Characteristics:**
  - Due date passed without final decision
  - Request is stale and no longer valid
  - Approval decisions may not reflect current context

---

### **ARCHIVED** (Terminal)
- **Allowed actions:**
  - None (terminal state)
  
- **Permissions:**
  - Read-only to all
  
- **Characteristics:**
  - Historic record retained for audit
  - Not included in active approval lists
  - Soft-delete (not physically removed from DB)

---

### **CANCELLED** (Terminal, from DRAFT)
- **Allowed actions:**
  - None (terminal state)
  
- **Permissions:**
  - Read-only to all
  
- **Characteristics:**
  - Request was withdrawn before submission
  - Approvers never notified
  - Soft-delete

---

## 🧮 Approval Logic (Core Algorithm)

```python
def check_approval_status(request: ApprovalRequest, db: Session):
    """Determine if request meets approval criteria."""
    
    steps = db.query(ApprovalRequestStep)\
        .filter(ApprovalRequestStep.request_id == request.id)\
        .order_by(ApprovalRequestStep.order)\
        .all()
    
    for step in steps:
        votes = db.query(ApprovalVote)\
            .filter(ApprovalVote.step_id == step.id)\
            .all()
        
        approved_count = sum(1 for v in votes if v.decision == "approve")
        rejected_count = sum(1 for v in votes if v.decision == "reject")
        
        # Rule 1: Any required rejection fails the entire request
        if step.is_required and rejected_count > 0:
            return "REJECTED"
        
        # Rule 2: All approvers in step must approve (for sequential)
        if step.approval_type == "sequential":
            if approved_count < len(step.assigned_approvers):
                if step.order == 0:  # First step
                    return "PENDING"
                else:  # Waiting for next step
                    return "PENDING"
        
        # Rule 3: Quorum-based (threshold)
        elif step.approval_type == "quorum":
            if approved_count < step.quorum_threshold:
                return "PENDING"
        
        # Rule 4: Any approver (single approval sufficient)
        elif step.approval_type == "any":
            if approved_count == 0:
                return "PENDING"
    
    # All steps completed successfully
    return "APPROVED"
```

---

## 🔗 Related Models

### `ApprovalRequest`
```python
class ApprovalRequest(Base):
    id: UUID
    title: str
    description: str
    status: str  # "draft", "pending", "approved", "rejected", "expired", "archived"
    requester_id: UUID  # User who initiated
    due_date: datetime
    submitted_at: datetime
    archived_at: datetime
    workflow_id: UUID  # Associated workflow template
    context_data: JSON  # Additional data for execution
    steps: List[ApprovalRequestStep]  # Ordered approval steps
    votes: List[ApprovalVote]  # Individual approver decisions
    audit_log: List[ApprovalAudit]  # State transitions + comments
```

### `ApprovalRequestStep`
```python
class ApprovalRequestStep(Base):
    id: UUID
    request_id: UUID
    order: int  # Execution order (0=first, sequential flow)
    assigned_approvers: List[User]  # Who must/can vote
    approval_type: str  # "sequential" | "quorum" | "any"
    quorum_threshold: int  # For quorum mode
    is_required: bool  # If False, can be skipped
    delegated_to: UUID  # If approver delegated
    votes: List[ApprovalVote]  # Votes on this step
```

### `ApprovalVote`
```python
class ApprovalVote(Base):
    id: UUID
    step_id: UUID
    approver_id: UUID
    decision: str  # "approve" | "reject" | "abstain"
    comment: str
    voted_at: datetime
```

---

## 📋 Workflow Patterns

### Pattern 1: Sequential Approval (Multi-level)
```
Step 1 (Manager)      → Approve/Reject
  ↓ (if approved)
Step 2 (Director)     → Approve/Reject
  ↓ (if approved)
Step 3 (CFO)          → Approve/Reject
  ↓ (if approved)
APPROVED → Execute
```

**Use case:** Budget requests, hiring approvals

---

### Pattern 2: Parallel Approval (Quorum)
```
Step 1 (All):
  ├─ Reviewer 1  → Approve/Reject
  ├─ Reviewer 2  → Approve/Reject
  ├─ Reviewer 3  → Approve/Reject
  └─ Reviewer 4  → Approve/Reject
  
Threshold: 3 of 4 must approve
Result: APPROVED (if quorum met)
```

**Use case:** PR reviews, policy approvals

---

### Pattern 3: Any Approver (Fast-track)
```
Step 1 (Any):
  ├─ Lead   → Can approve/reject
  └─ Any team member → Can approve/reject
  
Result: APPROVED (if any approves)
```

**Use case:** Quick decisions, support tickets

---

## 🔐 Permission Matrix

| Role | Can Submit | Can Approve | Can Reject | Can Recall | Can Archive |
|------|-----------|------------|-----------|-----------|------------|
| Requester | ✅ | ❌ | ❌ | ✅* | ❌ |
| Assigned Approver | ❌ | ✅ | ✅ | ❌ | ❌ |
| Manager | ✅ | ✅ | ✅ | ✅ | ✅ |
| Admin | ✅ | ✅ | ✅ | ✅ | ✅ |

*Can recall only if still PENDING and not yet approved/rejected

---

## ⏱️ Timeout & Escalation Rules

### Auto-Escalation
- If PENDING > X days (configurable per step) → escalate to next level
- Escalation sends notification to higher approver
- Original approver becomes CC'd

### Auto-Expiry
- If due_date passed → transition to EXPIRED
- No further votes accepted
- Can be resubmitted by requester

### Delegation
- Approver can delegate to substitute
- Substitute appears as effective approver
- Original approver informed

---

## 🧪 Testing Scenarios

1. **Happy path:** DRAFT → PENDING → APPROVED → Execute
2. **Rejection:** DRAFT → PENDING → REJECTED → Resubmit
3. **Timeout:** DRAFT → PENDING → (wait) → EXPIRED → Resubmit
4. **Escalation:** DRAFT → PENDING → (escalate) → Higher approver notified
5. **Delegation:** Approver delegates → Substitute votes → Same effect
6. **Multi-step:** Multiple steps in sequence, any rejection fails

---

## 📚 References

- Main file: `app/services/approval_engine.py` (line 1–1685)
- Models: `app/models/approvals.py`
- Endpoints: `app/api/v1/endpoints/approvals.py`
- Tests: `tests/test_approvals.py`
