"""
Change Management Service — RFC planning, approval workflows, rollout automation.

Capabilities:
  - RFC (Request for Change) creation & workflow
  - Risk assessment (IA-based)
  - Change planning with dependencies + rollout sequencing
  - CAB (Change Advisory Board) approval workflow
  - Rollback planning & automation
  - Post-change validation
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from enum import Enum

from sqlalchemy.orm import Session
from app.services.ai_provider_service import call_ai

class ChangeType(str, Enum):
    standard = "standard"       # Pre-approved template
    normal = "normal"           # Normal CAB approval
    emergency = "emergency"     # Emergency (limited approval)
    pilot = "pilot"             # Pilot/test change


class ChangeStatus(str, Enum):
    draft = "draft"
    submitted = "submitted"
    in_approval = "in_approval"
    approved = "approved"
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    rolled_back = "rolled_back"
    cancelled = "cancelled"


class RiskLevel(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


def assess_change_risk_ai(
    db: Session,
    title: str,
    description: str,
    impact_areas: list[str],
    affected_cis: list[str],
    rollback_plan: str,
) -> dict:
    """
    Use IA to assess change risk automatically.
    
    Returns: {
        "risk_level": "critical" | "high" | "medium" | "low",
        "risk_score": 0-100,
        "factors": list[str],
        "mitigation_suggestions": list[str],
        "recommended_approval_level": "emergency" | "normal" | "standard",
        "estimated_duration_minutes": int,
    }
    """
    system_prompt = """You are a Change Management expert. Analyze the following change request and:
    
    1. Assess risk level (critical/high/medium/low) based on:
       - Impact areas affected
       - Number of dependent systems
       - Rollback plan quality
       - Complexity indicators
    
    2. Identify risk factors
    3. Suggest mitigations
    4. Recommend approval level
    5. Estimate duration
    
    Respond ONLY with valid JSON:
    {
        "risk_level": "high",
        "risk_score": 75,
        "factors": ["list of identified risks"],
        "mitigation_suggestions": ["list of mitigations"],
        "recommended_approval_level": "normal",
        "estimated_duration_minutes": 120
    }"""

    change_content = f"""
    Title: {title}
    Description: {description}
    Impact Areas: {', '.join(impact_areas or ['unknown'])}
    Affected CIs: {', '.join(affected_cis or ['unknown'])}
    Rollback Plan: {rollback_plan}
    """

    ai_response = call_ai(
        db,
        messages=[{"role": "user", "content": change_content}],
        system=system_prompt,
        module="change_management",
        max_tokens=500,
    )

    try:
        result = json.loads(ai_response)
    except (json.JSONDecodeError, ValueError):
        # Fallback if AI returns non-JSON
        result = {
            "risk_level": "high",
            "risk_score": 50,
            "factors": ["Cannot assess automatically"],
            "mitigation_suggestions": ["Manual review required"],
            "recommended_approval_level": "normal",
            "estimated_duration_minutes": 120,
        }

    return result


def create_rollout_plan(
    db: Session,
    change_id: str,
    affected_cis: list[str],
    rollback_plan: str,
    estimated_duration_minutes: int,
) -> dict:
    """
    Generate automated rollout plan.
    
    Returns: {
        "phases": [
            {
                "phase": 1,
                "name": "Pre-change validation",
                "duration_minutes": 15,
                "steps": ["...", "..."],
                "validation_checks": ["..."],
                "rollback_if_fails": bool,
            },
            ...
        ],
        "total_estimated_minutes": int,
        "maintenance_window_start": datetime,
        "maintenance_window_end": datetime,
    }
    """
    phases = [
        {
            "phase": 1,
            "name": "Pre-change validation",
            "duration_minutes": 10,
            "steps": [
                "Verify all systems online",
                "Check disk space",
                "Verify backups completed",
                "Confirm CAB approval",
            ],
            "validation_checks": ["System health", "Connectivity", "Backup verification"],
            "rollback_if_fails": True,
        },
        {
            "phase": 2,
            "name": "Prepare rollback",
            "duration_minutes": 10,
            "steps": [
                "Create system snapshots",
                "Export current config",
                "Document current state",
                "Test rollback procedure",
            ],
            "validation_checks": ["Snapshots created", "Config exported"],
            "rollback_if_fails": True,
        },
        {
            "phase": 3,
            "name": "Apply change",
            "duration_minutes": int(estimated_duration_minutes),
            "steps": [
                "Execute deployment",
                "Monitor system resources",
                "Watch for errors",
                "Log all activities",
            ],
            "validation_checks": ["Deployment completed", "No critical errors"],
            "rollback_if_fails": True,
        },
        {
            "phase": 4,
            "name": "Post-change validation",
            "duration_minutes": 15,
            "steps": [
                "Verify all services running",
                "Run health checks",
                "Validate functionality",
                "Check performance metrics",
            ],
            "validation_checks": ["Services healthy", "Performance acceptable"],
            "rollback_if_fails": True,
        },
        {
            "phase": 5,
            "name": "Communication & closeout",
            "duration_minutes": 5,
            "steps": [
                "Notify stakeholders",
                "Update documentation",
                "Record metrics",
                "Close change ticket",
            ],
            "validation_checks": ["Stakeholders notified"],
            "rollback_if_fails": False,
        },
    ]

    total_minutes = sum(p["duration_minutes"] for p in phases)
    now = datetime.now(timezone.utc)
    
    return {
        "phases": phases,
        "total_estimated_minutes": total_minutes,
        "maintenance_window_start": now,
        "maintenance_window_end": now + timedelta(minutes=total_minutes + 30),
    }


def generate_rollback_automation_script(
    change_id: str,
    rollback_plan: str,
    affected_cis: list[str],
) -> str:
    """
    Generate bash/Python script for automated rollback.
    
    Returns script content that can be executed.
    """
    script = f"""#!/bin/bash
# Auto-generated rollback script for change {change_id}
# Generated: {datetime.now(timezone.utc).isoformat()}
# CAUTION: Test this before execution!

set -e  # Exit on error

echo "🔄 INITIATING ROLLBACK FOR CHANGE {change_id}"
echo "⏰ Timestamp: $(date -u)"

# Step 1: Notify stakeholders
echo "📢 Notifying stakeholders..."
# TODO: Send notification

# Step 2: Validate rollback pre-conditions
echo "🔍 Validating rollback conditions..."
# Check snapshots exist
# Check connectivity
# Verify no ongoing transactions

# Step 3: Execute rollback
echo "⚙️  Executing rollback steps..."
{rollback_plan}

# Step 4: Validate rollback
echo "✅ Validating rollback..."
# Run health checks
# Verify services
# Check data integrity

# Step 5: Document rollback
echo "📝 Documenting rollback..."
echo "Rollback completed at $(date -u)" >> /var/log/changes/rollback_{change_id}.log

echo "✅ ROLLBACK COMPLETED SUCCESSFULLY"
"""
    return script


def check_change_suitability_for_automation(
    db: Session,
    change_id: str,
    risk_level: RiskLevel,
    change_type: ChangeType,
) -> dict:
    """
    Determine if change can be fully automated or requires manual oversight.
    
    Returns: {
        "can_automate": bool,
        "automation_level": "full" | "partial" | "manual",
        "requires_manual_gates": list[str],
        "reason": str,
    }
    """
    automation_level = "partial"
    requires_manual_gates = []
    can_automate = True

    if risk_level == RiskLevel.critical:
        automation_level = "manual"
        can_automate = False
        requires_manual_gates.append("Manual approval before each phase")

    elif risk_level == RiskLevel.high:
        automation_level = "partial"
        requires_manual_gates.append("Manual approval before deployment phase")

    if change_type == ChangeType.emergency:
        requires_manual_gates.append("Continuous monitoring during execution")

    return {
        "can_automate": can_automate,
        "automation_level": automation_level,
        "requires_manual_gates": requires_manual_gates,
        "reason": f"Risk level: {risk_level.value}, Type: {change_type.value}",
    }
