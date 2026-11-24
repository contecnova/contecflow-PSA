// Textos de los procesos lineales del catálogo BPM — en. Misma forma en los tres
// idiomas (ver tipos.ts): nombre, descripción y un texto por paso. 
import type { TextosLineales } from '../tipos'

const textos: TextosLineales = {
  "ticket_assignment_ml": {
    "name": "Smart Assignment (ML)",
    "description": "Automatic routing of the ticket to the best-suited agent.",
    "steps": [
      "Ticket created",
      "Extract features",
      "Predict agent",
      "Check workload",
      "Assign"
    ]
  },
  "auto_resolution": {
    "name": "Auto-Resolution",
    "description": "AI-driven suggestion and automatic application of a resolution.",
    "steps": [
      "Incoming ticket",
      "Find similar",
      "Confidence score",
      "Suggest reply",
      "Auto-close"
    ]
  },
  "alert_correlation": {
    "name": "Alert Correlation",
    "description": "Grouping of related alerts into a single incident.",
    "steps": [
      "Incoming alert",
      "Find correlation",
      "Group",
      "Create parent incident",
      "Notify"
    ]
  },
  "voice_agent_ivr": {
    "name": "Voice Agent / IVR",
    "description": "Conversational flow of the voice agent for support.",
    "steps": [
      "Incoming call",
      "Identify user",
      "Intent detection",
      "Resolve / escalate",
      "End call"
    ]
  },
  "multichannel_intake": {
    "name": "Multi-Channel Intake",
    "description": "Receiving tickets from email, chat, portal and mobile. With no recipient company (an address or number of no company, with several companies) the message is ignored and no ticket is opened.",
    "steps": [
      "Incoming message",
      "Identify the recipient company (ignored without one)",
      "Normalise channel",
      "Extract data",
      "Create ticket",
      "Confirmation"
    ]
  },
  "escalation_routing": {
    "name": "Escalation",
    "description": "Escalation rules by SLA, priority and on-call.",
    "steps": [
      "Threshold check",
      "Identify destination",
      "Notify",
      "Re-assign",
      "Audit"
    ]
  },
  "sla_monitoring": {
    "name": "SLA Monitoring",
    "description": "Continuous monitoring of the ticket's SLA deadlines.",
    "steps": [
      "Ticket open",
      "OK",
      "At risk",
      "Breach",
      "Report"
    ]
  },
  "oncall_scheduling": {
    "name": "On-Call Scheduling",
    "description": "Rotation and assignment of on-call shifts.",
    "steps": [
      "Define rotation",
      "Assign shift",
      "Notify",
      "Activate on-call",
      "End shift"
    ]
  },
  "cab_review": {
    "name": "CAB Committee",
    "description": "CAB review and approval meeting.",
    "steps": [
      "Pending changes",
      "Convene CAB",
      "Discussion",
      "Vote",
      "Decision recorded"
    ]
  },
  "change_impact_analysis": {
    "name": "Impact Analysis",
    "description": "Impact assessment on the CMDB and services.",
    "steps": [
      "Proposed change",
      "Identify affected CIs",
      "Calculate risk",
      "Document",
      "Attach to RFC"
    ]
  },
  "change_rollout": {
    "name": "Staged Rollout",
    "description": "Phased rollout with checkpoints.",
    "steps": [
      "Approved",
      "Pilot",
      "Wave 1",
      "Wave 2",
      "Production",
      "Closure"
    ]
  },
  "rca_wizard": {
    "name": "RCA Assistant",
    "description": "Guided root cause investigation (5 Whys).",
    "steps": [
      "Define problem",
      "Gather data",
      "5 Whys",
      "Root cause",
      "Action plan"
    ]
  },
  "kedb_lookup": {
    "name": "Known Error Database",
    "description": "Lookup and suggestion of existing solutions.",
    "steps": [
      "Symptoms detected",
      "Search KEDB",
      "Match score",
      "Apply workaround",
      "Feedback"
    ]
  },
  "kb_authoring": {
    "name": "KB Article Authoring",
    "description": "Editorial cycle of knowledge base articles.",
    "steps": [
      "Draft",
      "Review",
      "Published",
      "Maintenance",
      "Archived"
    ]
  },
  "smart_catalog": {
    "name": "Smart Catalogue",
    "description": "Service catalogue with contextual suggestions.",
    "steps": [
      "Customer searches",
      "AI recommendations",
      "Selection",
      "Request",
      "Tracking"
    ]
  },
  "project_lifecycle": {
    "name": "Project Lifecycle",
    "description": "Project states from planning to closure.",
    "steps": [
      "Planning",
      "Active",
      "On hold",
      "Paused",
      "Completed",
      "Closed"
    ]
  },
  "task_workflow": {
    "name": "Task Workflow",
    "description": "Standard states of an agile task.",
    "steps": [
      "Backlog",
      "To-do",
      "In progress",
      "Blocked",
      "Review",
      "Done"
    ]
  },
  "project_phase": {
    "name": "Project Phases",
    "description": "Milestones per phase and gate approval.",
    "steps": [
      "Initiation",
      "Design",
      "Build",
      "Testing",
      "Acceptance",
      "Closure"
    ]
  },
  "task_auto_assignment": {
    "name": "Task Auto-Assignment",
    "description": "ML assigns the task to the most suitable team member.",
    "steps": [
      "Task created",
      "Extract required skills",
      "Score per user",
      "Capacity",
      "Assign"
    ]
  },
  "multi_level_approval": {
    "name": "Multi-Level Approval",
    "description": "Approval chain with escalation and delegation.",
    "steps": [
      "Request",
      "Level 1",
      "Level 2",
      "Final decision",
      "Notification"
    ]
  },
  "invoice_workflow": {
    "name": "Invoice Workflow",
    "description": "Issuing, sending and reconciling invoices.",
    "steps": [
      "Draft",
      "Issued",
      "Sent",
      "Paid",
      "Closed"
    ]
  },
  "churn_prediction": {
    "name": "Churn Prediction",
    "description": "Early detection of at-risk customers.",
    "steps": [
      "Collect features",
      "ML inference",
      "Score",
      "Alert CSM",
      "Retention plan"
    ]
  },
  "anomaly_detection": {
    "name": "Login Anomaly Detection",
    "description": "Identification of unusual access patterns.",
    "steps": [
      "Login event",
      "Baseline check",
      "Anomaly score",
      "Alert SecOps",
      "Block"
    ]
  },
  "revenue_forecast": {
    "name": "Revenue Forecasting",
    "description": "Revenue projection based on the pipeline.",
    "steps": [
      "Pipeline snapshot",
      "Weight opportunities",
      "Predictive model",
      "Generate forecast",
      "Publish"
    ]
  },
  "incident_predictions": {
    "name": "Incident Predictions",
    "description": "Prediction of MTTR and ticket volume.",
    "steps": [
      "Historical data",
      "Train",
      "Inference",
      "Dashboard",
      "Retrain"
    ]
  },
  "semantic_feedback": {
    "name": "Semantic Feedback Loop",
    "description": "Continuous learning from user feedback.",
    "steps": [
      "AI prediction",
      "Receive feedback",
      "Label",
      "Retrain",
      "Deploy v+1"
    ]
  },
  "project_overrun_ml": {
    "name": "Overrun Prediction",
    "description": "ML to anticipate project deviations.",
    "steps": [
      "Project snapshot",
      "Inference",
      "Risk",
      "Alert PM",
      "Mitigation"
    ]
  },
  "resource_forecast": {
    "name": "Resource Forecast",
    "description": "Projection of capacity vs. demand.",
    "steps": [
      "Current capacity",
      "Expected demand",
      "Gap analysis",
      "Staffing plan",
      "Publish"
    ]
  },
  "training_plan": {
    "name": "Training Plan",
    "description": "Assignment and tracking of courses.",
    "steps": [
      "Detect gap",
      "Assign course",
      "In progress",
      "Completed",
      "Certified"
    ]
  },
  "onboarding": {
    "name": "Employee Onboarding",
    "description": "Joining and initial training.",
    "steps": [
      "Pre-boarding",
      "Day 1",
      "Week 1",
      "Month 1",
      "Confirmation"
    ]
  },
  "governance_compliance": {
    "name": "Governance Compliance",
    "description": "Periodic verification of governance controls.",
    "steps": [
      "Define control",
      "Audit",
      "Findings",
      "Remediation",
      "Closure"
    ]
  },
  "esign_workflow": {
    "name": "Electronic Signature",
    "description": "Request, signing and filing of a document.",
    "steps": [
      "Prepare",
      "Send for signing",
      "Signed",
      "File",
      "Notify"
    ]
  },
  "uat_acceptance": {
    "name": "UAT — User Acceptance Testing",
    "description": "Acceptance of deliverables by the customer.",
    "steps": [
      "UAT plan",
      "Execution",
      "Defects",
      "Re-test",
      "Accepted"
    ]
  },
  "workflow_blueprint": {
    "name": "Workflow Blueprint",
    "description": "Visual design of declarative Service Desk workflows.",
    "steps": [
      "Draft",
      "Compile rules",
      "Publish",
      "In use",
      "Archived"
    ]
  },
  "automation_workflow": {
    "name": "Automation Workflow",
    "description": "Triggers + conditions + programmatic actions.",
    "steps": [
      "Draft",
      "Active",
      "Triggered",
      "Paused",
      "Archived"
    ]
  },
  "data_import": {
    "name": "Data Import",
    "description": "Bulk CSV / Excel upload.",
    "steps": [
      "Upload file",
      "Validation",
      "Processing",
      "Completed",
      "Report"
    ]
  },
  "jira_sync": {
    "name": "Jira Synchronisation",
    "description": "Continuous two-way sync with Jira.",
    "steps": [
      "Pull Jira",
      "Diff",
      "Push local",
      "Reconcile",
      "Next cycle"
    ]
  },
  "etl_pipeline": {
    "name": "ETL Pipeline",
    "description": "Extraction, transformation and loading into the data warehouse.",
    "steps": [
      "Extract",
      "Transform",
      "Validate",
      "Load",
      "Quality check"
    ]
  },
  "data_governance_review": {
    "name": "Data Governance Review",
    "description": "Approval of datasets and access policies.",
    "steps": [
      "Catalogue",
      "Classify",
      "Approval",
      "Published",
      "Audit"
    ]
  },
  "portal_conversation": {
    "name": "Portal conversation (chat and calls)",
    "description": "Operator-customer chat (formal conversations, collaboration chat and Support live chat): validated attachments (content, AV/DLP, types and size per company); voice or video call started only by the operator, the customer accepts or declines; not recorded.",
    "steps": [
      "Customer message",
      "Validate attachments (content, AV/DLP)",
      "GRC policy and approval",
      "Operator reply",
      "Operator starts voice or video call",
      "Customer accepts or declines",
      "Call (not recorded) and wrap-up",
      "Conversation handled"
    ]
  },
  "cert_program": {
    "name": "Certification programme",
    "description": "Scope, statement of applicability, implementation, independent testing, audits and certificate (ISO 27001, TISAX, NIS2, SOX, J-SOX, IEC 62443).",
    "steps": [
      "Scope and objectives",
      "Gap and risk analysis",
      "Statement of applicability",
      "Control implementation",
      "Effectiveness testing (another person)",
      "Internal audit",
      "Management review",
      "Certification audit",
      "Certificate in force"
    ]
  },
  "cert_audit_capa": {
    "name": "Audit, finding and corrective action",
    "description": "From the audit to closing the finding: corrective action as a task, effectiveness check and closure by another person.",
    "steps": [
      "Audit planned",
      "Samples and fieldwork",
      "Finding recorded",
      "Corrective action (task)",
      "Action done",
      "Effectiveness check (another person)",
      "Finding corrected",
      "Closure (not the corrector)"
    ]
  },
  "nis2_incident": {
    "name": "NIS2 reportable incident",
    "description": "Significant incident from the Service Desk with the 24 h, 72 h and 1 month clocks and the log of communications to the authority.",
    "steps": [
      "Incident detected (ticket)",
      "Significance assessment",
      "Early warning (24 h)",
      "Notification (72 h)",
      "Intermediate reports",
      "Final report (1 month)",
      "Closure and lessons"
    ]
  }
}

export default textos
