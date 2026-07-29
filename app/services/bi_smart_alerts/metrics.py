"""Metric time-series extraction for the BI Smart Alerts engine.

Pulls monthly series for every supported metric (and composite/custom metrics)
directly from real DB data.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .constants import CUSTOM_METRICS_KEY
from .persistence import _get_json

logger = logging.getLogger(__name__)


def _fetch_metric_series(db: Session, metric_key: str, organization_id: Optional[str]) -> list[float]:
    """Pull last 24 months of the requested metric from real DB data."""
    from collections import defaultdict
    from datetime import date

    from app.services.bi_intelligence_service import _month_series
    try:
        series = _month_series(db, organization_id, months_history=24)
    except Exception:
        logger.warning("Failed to load _month_series for smart alerts org=%s", organization_id, exc_info=True)
        series = []
    if not series:
        _cur_year = datetime.now(timezone.utc).year
        series = [{"month": f"{_cur_year}-{m:02d}", "revenue": 0.0, "cost": 0.0, "hours": 0.0} for m in range(1, 13)]

    def _empty_like() -> list[float]:
        return [0.0 for _ in series]

    def _bucket_count(rows, date_field_idx=0, *, start: date) -> list[float]:
        bkt: dict[str, float] = defaultdict(float)
        for row in rows:
            d = row[date_field_idx] if isinstance(row, (list, tuple)) else row
            if d:
                bkt[f"{d.year:04d}-{d.month:02d}"] += 1.0
        return [float(bkt.get(m["month"], 0.0)) for m in series]

    def _bucket_sum(rows, date_idx=0, value_idx=1, *, start: date) -> list[float]:
        bkt: dict[str, float] = defaultdict(float)
        for row in rows:
            d, v = row[date_idx], row[value_idx]
            if d and v is not None:
                bkt[f"{d.year:04d}-{d.month:02d}"] += float(v)
        return [float(bkt.get(m["month"], 0.0)) for m in series]

    def _current(val: float) -> list[float]:
        return [val] * len(series)

    start_date = date.fromisoformat(series[0]["month"] + "-01")

    # ── custom metric ──────────────────────────────────────────────────────────
    if metric_key.startswith("custom_"):
        customs = _get_json(db, CUSTOM_METRICS_KEY, organization_id, default=[])
        cm = next((c for c in customs if c.get("key") == metric_key), None)
        if not cm:
            return _empty_like()
        f = cm.get("formula", {})
        a_s = _fetch_metric_series(db, f.get("operand_a", ""), organization_id)
        op = f.get("operator", "+")
        b_s = (_fetch_metric_series(db, f.get("operand_b", ""), organization_id)
               if f.get("operand_b_type") == "metric"
               else [float(f.get("operand_b", 0) or 0)] * len(a_s))
        scale = float(f.get("scale", 1) or 1)
        result = []
        for a, b in zip(a_s, b_s):
            try:
                v = {"+": a+b, "-": a-b, "*": a*b, "/": a/b if b else 0.0}.get(op, a)
            except Exception:
                logger.debug("Custom metric %s arithmetic failed (op=%s a=%s b=%s)", metric_key, op, a, b, exc_info=True)
                v = 0.0
            result.append(round(v * scale, 4))
        return result

    # ── Financial ──────────────────────────────────────────────────────────────
    if metric_key == "revenue":
        return [float(m.get("revenue", 0)) for m in series]
    if metric_key == "cost":
        return [float(m.get("cost", 0)) for m in series]
    if metric_key == "margin":
        return [float(m.get("revenue", 0)) - float(m.get("cost", 0)) for m in series]
    if metric_key == "margin_pct":
        return [round((float(m.get("revenue",0))-float(m.get("cost",0)))/float(m.get("revenue",0))*100,2)
                if float(m.get("revenue",0)) > 0 else 0.0 for m in series]
    if metric_key == "budget_used_pct":
        return [round(float(m.get("cost",0))/float(m.get("revenue",0))*100,2)
                if float(m.get("revenue",0)) > 0 else 0.0 for m in series]

    # invoices
    if metric_key in ("invoice_overdue_count","invoice_overdue_amount","invoices_draft_count",
                       "invoices_sent_count","invoices_paid_count","invoices_paid_total","invoice_days_to_pay_avg"):
        try:
            from app.models.billing_reports import Invoice
            rows = db.query(Invoice.due_date, Invoice.issue_date, Invoice.paid_date,
                            Invoice.status, Invoice.total).filter(Invoice.due_date >= start_date).all()
            if metric_key == "invoice_overdue_count":
                bkt: dict[str,float] = defaultdict(float)
                for due, iss, paid, st, tot in rows:
                    if due and str(getattr(st,"value",st)) == "overdue":
                        bkt[f"{due.year:04d}-{due.month:02d}"] += 1.0
                return [float(bkt.get(m["month"],0.0)) for m in series]
            if metric_key == "invoice_overdue_amount":
                bkt = defaultdict(float)
                for due, iss, paid, st, tot in rows:
                    if due and str(getattr(st,"value",st)) == "overdue":
                        bkt[f"{due.year:04d}-{due.month:02d}"] += float(tot or 0)
                return [float(bkt.get(m["month"],0.0)) for m in series]
            if metric_key == "invoices_draft_count":
                bkt = defaultdict(float)
                for due, iss, paid, st, tot in rows:
                    if iss and str(getattr(st,"value",st)) == "draft":
                        bkt[f"{iss.year:04d}-{iss.month:02d}"] += 1.0
                return [float(bkt.get(m["month"],0.0)) for m in series]
            if metric_key == "invoices_sent_count":
                bkt = defaultdict(float)
                for due, iss, paid, st, tot in rows:
                    if iss and str(getattr(st,"value",st)) == "sent":
                        bkt[f"{iss.year:04d}-{iss.month:02d}"] += 1.0
                return [float(bkt.get(m["month"],0.0)) for m in series]
            if metric_key == "invoices_paid_count":
                bkt = defaultdict(float)
                for due, iss, paid, st, tot in rows:
                    if (iss or paid) and str(getattr(st,"value",st)) == "paid":
                        d = paid or iss
                        bkt[f"{d.year:04d}-{d.month:02d}"] += 1.0
                return [float(bkt.get(m["month"],0.0)) for m in series]
            if metric_key == "invoices_paid_total":
                bkt = defaultdict(float)
                for due, iss, paid, st, tot in rows:
                    if (iss or paid) and str(getattr(st,"value",st)) == "paid":
                        d = paid or iss
                        bkt[f"{d.year:04d}-{d.month:02d}"] += float(tot or 0)
                return [float(bkt.get(m["month"],0.0)) for m in series]
            if metric_key == "invoice_days_to_pay_avg":
                bkt_sum: dict[str,float] = defaultdict(float)
                bkt_cnt: dict[str,float] = defaultdict(float)
                for due, iss, paid, st, tot in rows:
                    if iss and paid and str(getattr(st,"value",st)) == "paid":
                        days = (paid - iss).days
                        k = f"{iss.year:04d}-{iss.month:02d}"
                        bkt_sum[k] += days; bkt_cnt[k] += 1.0
                return [round(bkt_sum[m["month"]]/bkt_cnt[m["month"]],1)
                        if bkt_cnt.get(m["month"],0) > 0 else 0.0 for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

    # expenses
    if metric_key in ("expense_total","expenses_travel","expenses_software","expenses_hardware",
                       "expenses_subcontract","expenses_training_exp",
                       "expenses_draft_count","expenses_submitted_count",
                       "expenses_approved_count","expenses_rejected_count"):
        try:
            from app.models.expenses import Expense
            rows = db.query(Expense.expense_date, Expense.amount, Expense.category, Expense.status).filter(
                Expense.expense_date >= start_date
            ).all()
            CAT_MAP = {
                "expenses_travel": "travel", "expenses_software": "software",
                "expenses_hardware": "hardware", "expenses_subcontract": "subcontract",
                "expenses_training_exp": "training",
            }
            STATUS_MAP = {
                "expenses_draft_count": "draft", "expenses_submitted_count": "submitted",
                "expenses_approved_count": "approved", "expenses_rejected_count": "rejected",
            }
            bkt: dict[str,float] = defaultdict(float)
            for d, amt, cat, st in rows:
                if not d: continue
                k = f"{d.year:04d}-{d.month:02d}"
                sv = str(getattr(st,"value",st)); cv = str(getattr(cat,"value",cat))
                if metric_key == "expense_total" and sv != "rejected":
                    bkt[k] += float(amt or 0)
                elif metric_key in CAT_MAP and cv == CAT_MAP[metric_key] and sv != "rejected":
                    bkt[k] += float(amt or 0)
                elif metric_key in STATUS_MAP and sv == STATUS_MAP[metric_key]:
                    bkt[k] += 1.0
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

    # imputations financial
    if metric_key in ("imputations_approved_hours","imputations_invoiced_count",
                       "imputations_cost_total","hourly_rate_avg"):
        try:
            from app.models.imputation import Imputation
            from sqlalchemy import func as sqf
            if metric_key == "imputations_approved_hours":
                rows = db.query(Imputation.date, Imputation.hours).filter(
                    Imputation.date >= start_date, Imputation.is_approved == True  # noqa: E712
                ).all()
                return _bucket_sum(rows, start=start_date)
            if metric_key == "imputations_invoiced_count":
                rows = db.query(Imputation.date).filter(
                    Imputation.date >= start_date, Imputation.is_invoiced == True  # noqa: E712
                ).all()
                return _bucket_count(rows, start=start_date)
            if metric_key == "imputations_cost_total":
                rows = db.query(Imputation.date, Imputation.cost_amount).filter(
                    Imputation.date >= start_date
                ).all()
                return _bucket_sum(rows, start=start_date)
            if metric_key == "hourly_rate_avg":
                rows = db.query(Imputation.date, Imputation.hourly_rate_snapshot).filter(
                    Imputation.date >= start_date, Imputation.hourly_rate_snapshot != None  # noqa: E711
                ).all()
                bkt_s: dict[str,float] = defaultdict(float)
                bkt_c: dict[str,float] = defaultdict(float)
                for d, r in rows:
                    if d and r:
                        k = f"{d.year:04d}-{d.month:02d}"; bkt_s[k] += r; bkt_c[k] += 1.0
                return [round(bkt_s[m["month"]]/bkt_c[m["month"]],2)
                        if bkt_c.get(m["month"],0) > 0 else 0.0 for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

    # ── Cost structure (UserCostProfile snapshots end-of-month) ────────────────
    COST_PROFILE_KEYS = {
        "cost_profile_avg_per_hour", "cost_profile_max_per_hour",
        "cost_profile_p95_per_hour", "cost_profile_dept_max_per_hour",
        "cost_profile_country_max_per_hour",
        "cost_profile_total_annual", "cost_profile_top_person_annual",
        "cost_profile_top_country_annual",
        "cost_profile_users_with", "cost_profile_users_legacy",
        "cost_profile_users_missing",
        "cost_profile_employer_pct_avg", "cost_profile_employer_pct_max",
    }
    if metric_key in COST_PROFILE_KEYS:
        try:
            from datetime import date as _D, timedelta as _T
            from sqlalchemy import or_ as _or
            from app.models.user_cost import UserCostProfile, CountryEmployerCost
            from app.models.user import User as _User

            def _eom(year: int, month: int) -> _D:
                if month == 12:
                    return _D(year, 12, 31)
                return _D(year, month + 1, 1) - _T(days=1)

            def _percentile(vals: list[float], pct: float) -> float:
                if not vals:
                    return 0.0
                ordered = sorted(vals)
                k = (len(ordered) - 1) * (pct / 100.0)
                lo = int(k)
                hi = min(lo + 1, len(ordered) - 1)
                frac = k - lo
                return ordered[lo] * (1 - frac) + ordered[hi] * frac

            # Active users count (snapshot-independent — current state used as proxy)
            active_users = db.query(_User).filter(_User.status == "active").all()
            total_active = len(active_users)
            users_by_id = {u.id: u for u in active_users}
            legacy_user_ids = {u.id for u in active_users if (u.hourly_rate or 0) > 0}

            # Country presets (used for employer_pct metrics — stable across snapshots)
            country_presets = db.query(CountryEmployerCost).all()
            employer_pcts = [c.employer_cost_pct for c in country_presets if c.employer_cost_pct is not None]

            out: list[float] = []
            for m in series:
                yyyy, mm = m["month"].split("-")
                snap = _eom(int(yyyy), int(mm))
                profiles = (db.query(UserCostProfile)
                              .filter(UserCostProfile.valid_from <= snap,
                                      _or(UserCostProfile.valid_to.is_(None),
                                          UserCostProfile.valid_to >= snap))
                              .all())
                rates = [p.cost_per_hour for p in profiles if p.cost_per_hour]

                if metric_key == "cost_profile_avg_per_hour":
                    out.append(round(sum(rates) / len(rates), 2) if rates else 0.0)
                elif metric_key == "cost_profile_max_per_hour":
                    out.append(round(max(rates), 2) if rates else 0.0)
                elif metric_key == "cost_profile_p95_per_hour":
                    out.append(round(_percentile(rates, 95), 2))
                elif metric_key == "cost_profile_dept_max_per_hour":
                    bucket: dict[str, list[float]] = {}
                    for p in profiles:
                        u = users_by_id.get(p.user_id)
                        if u and p.cost_per_hour:
                            bucket.setdefault(u.department or "—", []).append(p.cost_per_hour)
                    dept_avgs = [sum(v) / len(v) for v in bucket.values() if v]
                    out.append(round(max(dept_avgs), 2) if dept_avgs else 0.0)
                elif metric_key == "cost_profile_country_max_per_hour":
                    bucket = {}
                    for p in profiles:
                        if p.country_code and p.cost_per_hour:
                            bucket.setdefault(p.country_code, []).append(p.cost_per_hour)
                    country_avgs = [sum(v) / len(v) for v in bucket.values() if v]
                    out.append(round(max(country_avgs), 2) if country_avgs else 0.0)
                elif metric_key == "cost_profile_total_annual":
                    out.append(round(sum(p.total_annual_cost or 0 for p in profiles), 2))
                elif metric_key == "cost_profile_top_person_annual":
                    annuals = [p.total_annual_cost for p in profiles if p.total_annual_cost]
                    out.append(round(max(annuals), 2) if annuals else 0.0)
                elif metric_key == "cost_profile_top_country_annual":
                    bucket_a: dict[str, float] = {}
                    for p in profiles:
                        if p.country_code:
                            bucket_a[p.country_code] = bucket_a.get(p.country_code, 0) + (p.total_annual_cost or 0)
                    out.append(round(max(bucket_a.values()), 2) if bucket_a else 0.0)
                elif metric_key == "cost_profile_users_with":
                    out.append(float(len({p.user_id for p in profiles})))
                elif metric_key == "cost_profile_users_legacy":
                    with_ids = {p.user_id for p in profiles}
                    out.append(float(len(legacy_user_ids - with_ids)))
                elif metric_key == "cost_profile_users_missing":
                    with_ids = {p.user_id for p in profiles}
                    legacy_only = legacy_user_ids - with_ids
                    out.append(float(max(total_active - len(with_ids) - len(legacy_only), 0)))
                elif metric_key == "cost_profile_employer_pct_avg":
                    out.append(round(sum(employer_pcts) / len(employer_pcts) * 100, 2) if employer_pcts else 0.0)
                elif metric_key == "cost_profile_employer_pct_max":
                    out.append(round(max(employer_pcts) * 100, 2) if employer_pcts else 0.0)
                else:
                    out.append(0.0)
            return out
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

    # ── Resource / Capacity ────────────────────────────────────────────────────
    if metric_key == "hours_logged":
        return [float(m.get("hours", 0) or 0) for m in series]
    if metric_key == "hours_billable":
        try:
            from app.models.imputation import Imputation
            rows = db.query(Imputation.date, Imputation.hours).filter(
                Imputation.date >= start_date, Imputation.is_billable == True  # noqa: E712
            ).all()
            return _bucket_sum(rows, start=start_date)
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "billable_pct":
        t = _fetch_metric_series(db, "hours_logged", organization_id)
        b = _fetch_metric_series(db, "hours_billable", organization_id)
        return [round(bv/tv*100,2) if tv > 0 else 0.0 for tv,bv in zip(t,b)]
    if metric_key == "utilization":
        return [min(100.0, round(float(m.get("hours",0) or 0)/160.0*100.0,2)) for m in series]
    if metric_key == "overloaded_users":
        try:
            from app.models.imputation import Imputation
            from sqlalchemy import func as sqf
            rows = db.query(sqf.strftime("%Y-%m",Imputation.date).label("mo"),
                            Imputation.user_id, sqf.sum(Imputation.hours).label("tot")
                            ).filter(Imputation.date >= start_date
                            ).group_by("mo",Imputation.user_id).all()
            bkt: dict[str,float] = defaultdict(float)
            for mo, uid, tot in rows:
                if tot and tot > 160: bkt[str(mo)] += 1.0
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "avg_user_load_pct":
        try:
            from app.models.resources import ResourceUtilizationSnapshot
            rows = db.query(ResourceUtilizationSnapshot.week_iso, ResourceUtilizationSnapshot.utilization_pct).all()
            bkt_s: dict[str,float] = defaultdict(float)
            bkt_c: dict[str,float] = defaultdict(float)
            for w, p in rows:
                if w and p is not None:
                    mo = w[:7]
                    bkt_s[mo] += float(p); bkt_c[mo] += 1.0
            return [round(bkt_s[m["month"]]/bkt_c[m["month"]],2)
                    if bkt_c.get(m["month"],0) > 0 else 0.0 for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "users_at_capacity":
        try:
            from app.models.resources import ResourceUtilizationSnapshot
            rows = db.query(ResourceUtilizationSnapshot.week_iso, ResourceUtilizationSnapshot.utilization_pct).all()
            bkt: dict[str,float] = defaultdict(float)
            for w, p in rows:
                if w and p is not None and 80 <= float(p) <= 100:
                    bkt[w[:7]] += 1.0
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "users_underutilized":
        try:
            from app.models.resources import ResourceUtilizationSnapshot
            rows = db.query(ResourceUtilizationSnapshot.week_iso, ResourceUtilizationSnapshot.utilization_pct).all()
            bkt: dict[str,float] = defaultdict(float)
            for w, p in rows:
                if w and p is not None and float(p) < 50:
                    bkt[w[:7]] += 1.0
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "snapshot_billable_pct":
        try:
            from app.models.resources import ResourceUtilizationSnapshot
            rows = db.query(ResourceUtilizationSnapshot.week_iso, ResourceUtilizationSnapshot.billable_pct).all()
            bkt_s: dict[str,float] = defaultdict(float)
            bkt_c: dict[str,float] = defaultdict(float)
            for w, p in rows:
                if w and p is not None:
                    bkt_s[w[:7]] += float(p); bkt_c[w[:7]] += 1.0
            return [round(bkt_s[m["month"]]/bkt_c[m["month"]],2)
                    if bkt_c.get(m["month"],0)>0 else 0.0 for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key in ("pending_timesheets","timesheets_draft_count","timesheets_submitted_count",
                       "timesheets_rejected_count","timesheet_cost_total","timesheet_avg_hours"):
        try:
            from app.models.financial import Timesheet, TimesheetStatus
            rows = db.query(Timesheet.week_start, Timesheet.status, Timesheet.total_hours, Timesheet.total_cost).filter(
                Timesheet.week_start >= start_date
            ).all()
            STATUS = {"pending_timesheets":"submitted","timesheets_draft_count":"draft",
                      "timesheets_submitted_count":"submitted","timesheets_rejected_count":"rejected"}
            if metric_key in STATUS:
                bkt: dict[str,float] = defaultdict(float)
                if metric_key == "pending_timesheets":
                    n = db.query(Timesheet).filter(Timesheet.status == TimesheetStatus.submitted).count()
                    return _current(float(n))
                for ws, st, h, c in rows:
                    if ws and str(getattr(st,"value",st)) == STATUS[metric_key]:
                        bkt[f"{ws.year:04d}-{ws.month:02d}"] += 1.0
                return [float(bkt.get(m["month"],0.0)) for m in series]
            if metric_key == "timesheet_cost_total":
                bkt = defaultdict(float)
                for ws, st, h, c in rows:
                    if ws: bkt[f"{ws.year:04d}-{ws.month:02d}"] += float(c or 0)
                return [float(bkt.get(m["month"],0.0)) for m in series]
            if metric_key == "timesheet_avg_hours":
                bkt_s: dict[str,float] = defaultdict(float); bkt_c: dict[str,float] = defaultdict(float)
                for ws, st, h, c in rows:
                    if ws and h: k=f"{ws.year:04d}-{ws.month:02d}"; bkt_s[k]+=float(h); bkt_c[k]+=1.0
                return [round(bkt_s[m["month"]]/bkt_c[m["month"]],2)
                        if bkt_c.get(m["month"],0)>0 else 0.0 for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key in ("absence_days","absence_vacation_days","absence_sick_days",
                       "absence_training_days","absence_pending_count"):
        try:
            from app.models.resources import Absence
            rows = db.query(Absence.start_date, Absence.working_days, Absence.type, Absence.status).filter(
                Absence.start_date >= start_date
            ).all()
            TYPE_MAP = {"absence_vacation_days":"vacation","absence_sick_days":"sick","absence_training_days":"training"}
            if metric_key == "absence_pending_count":
                bkt: dict[str,float] = defaultdict(float)
                for sd, wd, tp, st in rows:
                    if sd and str(getattr(st,"value",st)) == "pending":
                        bkt[f"{sd.year:04d}-{sd.month:02d}"] += 1.0
                return [float(bkt.get(m["month"],0.0)) for m in series]
            bkt = defaultdict(float)
            for sd, wd, tp, st in rows:
                if not sd or str(getattr(st,"value",st)) != "approved": continue
                tv = str(getattr(tp,"value",tp))
                k = f"{sd.year:04d}-{sd.month:02d}"
                if metric_key == "absence_days":
                    bkt[k] += float(wd or 0)
                elif metric_key in TYPE_MAP and tv == TYPE_MAP[metric_key]:
                    bkt[k] += float(wd or 0)
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "certified_users_count":
        try:
            from app.models.resources import UserSkill
            from sqlalchemy import func as sqf
            count = db.query(sqf.count(sqf.distinct(UserSkill.user_id))).filter(
                UserSkill.certified == True  # noqa: E712
            ).scalar() or 0
            return _current(float(count))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key in ("resource_alerts_overload","resource_alerts_skill_gap"):
        try:
            from app.models.resources import ResourceAlert, ResourceAlertType
            atype = ResourceAlertType.overload_warning if metric_key=="resource_alerts_overload" else ResourceAlertType.skill_gap
            q = db.query(ResourceAlert).filter(ResourceAlert.alert_type == atype)
            if metric_key == "resource_alerts_overload":
                q = q.filter(ResourceAlert.acknowledged_at == None)  # noqa: E711
            return _current(float(q.count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

    # ── Projects ───────────────────────────────────────────────────────────────
    if metric_key == "active_projects":
        try:
            from app.models.project import Project, ProjectStatus as PS
            return _current(float(db.query(Project).filter(Project.status == PS.active).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "projects_at_risk":
        try:
            from app.models.project import Project, ProjectStatus as PS, ProjectRisk as PR
            return _current(float(db.query(Project).filter(
                Project.status == PS.active, Project.risk_level.in_([PR.high, PR.critical])
            ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "projects_over_budget":
        try:
            from app.models.project import Project, ProjectStatus as PS
            from app.models.imputation import Imputation
            from sqlalchemy import func as sqf
            costs = {pid: float(c or 0) for pid, c in
                     db.query(Imputation.project_id, sqf.sum(Imputation.cost_amount)
                              ).group_by(Imputation.project_id).all() if pid}
            projects = db.query(Project.id, Project.budget_amount).filter(
                Project.status == PS.active, Project.budget_amount > 0
            ).all()
            return _current(float(sum(1 for pid, bgt in projects if costs.get(pid, 0) > float(bgt or 0))))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "projects_overdue":
        try:
            from app.models.project import Project, ProjectStatus as PS
            from datetime import date as dc
            today = dc.today()
            return _current(float(db.query(Project).filter(
                Project.status == PS.active,
                Project.end_date_planned != None,  # noqa: E711
                Project.end_date_planned < today
            ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "projects_on_hold":
        try:
            from app.models.project import Project, ProjectStatus as PS
            return _current(float(db.query(Project).filter(Project.status == PS.on_hold).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "projects_cancelled":
        try:
            from app.models.project import Project, ProjectStatus as PS
            return _current(float(db.query(Project).filter(Project.status == PS.cancelled).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "projects_completed_count":
        try:
            from app.models.project import Project, ProjectStatus as PS
            return _current(float(db.query(Project).filter(Project.status == PS.completed).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key in ("milestones_overdue","milestones_pending","milestones_completed",
                       "milestones_invoiced","milestones_pending_approval"):
        try:
            from app.models.financial import ProjectMilestone
            from datetime import date as dc
            today = dc.today()
            if metric_key == "milestones_overdue":
                return _current(float(db.query(ProjectMilestone).filter(
                    ProjectMilestone.is_completed == False,  # noqa: E712
                    ProjectMilestone.due_date != None,  # noqa: E711
                    ProjectMilestone.due_date < today
                ).count()))
            if metric_key == "milestones_pending":
                return _current(float(db.query(ProjectMilestone).filter(
                    ProjectMilestone.billing_status == "pending"
                ).count()))
            if metric_key == "milestones_completed":
                return _current(float(db.query(ProjectMilestone).filter(
                    ProjectMilestone.is_completed == True  # noqa: E712
                ).count()))
            if metric_key == "milestones_invoiced":
                return _current(float(db.query(ProjectMilestone).filter(
                    ProjectMilestone.is_billed == True  # noqa: E712
                ).count()))
            if metric_key == "milestones_pending_approval":
                return _current(float(db.query(ProjectMilestone).filter(
                    ProjectMilestone.billing_status == "pending_approval"
                ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key in ("deliverables_in_progress","deliverables_in_review",
                       "deliverables_accepted","deliverables_rejected"):
        try:
            from app.models.resources import Deliverable, DeliverableStatus
            STATUS = {"deliverables_in_progress": DeliverableStatus.in_progress,
                      "deliverables_in_review":   DeliverableStatus.in_review,
                      "deliverables_accepted":    DeliverableStatus.accepted,
                      "deliverables_rejected":    DeliverableStatus.rejected}
            return _current(float(db.query(Deliverable).filter(
                Deliverable.status == STATUS[metric_key]
            ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key in ("change_requests_total","change_requests_pending",
                       "change_requests_cost_impact","change_requests_schedule"):
        try:
            from app.models.resources import ChangeRequest, ChangeRequestStatus
            if metric_key == "change_requests_total":
                return _current(float(db.query(ChangeRequest).count()))
            if metric_key == "change_requests_pending":
                return _current(float(db.query(ChangeRequest).filter(
                    ChangeRequest.status.in_([ChangeRequestStatus.draft, ChangeRequestStatus.submitted])
                ).count()))
            if metric_key == "change_requests_cost_impact":
                from sqlalchemy import func as sqf
                v = db.query(sqf.sum(ChangeRequest.cost_impact)).scalar() or 0.0
                return _current(float(v))
            if metric_key == "change_requests_schedule":
                from sqlalchemy import func as sqf
                v = db.query(sqf.sum(ChangeRequest.schedule_impact_days)).scalar() or 0.0
                return _current(float(v))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

    # ── Tasks ──────────────────────────────────────────────────────────────────
    if metric_key == "tasks_overdue":
        try:
            from app.models.task import Task
            rows = db.query(Task.due_date, Task.status).filter(
                Task.due_date != None, Task.due_date >= start_date  # noqa: E711
            ).all()
            bkt: dict[str,float] = defaultdict(float)
            for dd, st in rows:
                if dd and str(getattr(st,"value",st)) not in ("done","cancelled"):
                    bkt[f"{dd.year:04d}-{dd.month:02d}"] += 1.0
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "tasks_blocked":
        try:
            from app.models.task import Task, TaskStatus
            return _current(float(db.query(Task).filter(Task.status == TaskStatus.blocked).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "tasks_created":
        try:
            from app.models.task import Task
            rows = db.query(Task.created_at).filter(Task.created_at >= start_date).all()
            return _bucket_count(rows, start=start_date)
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "tasks_completed":
        try:
            from app.models.task import Task, TaskStatus
            rows = db.query(Task.completed_at).filter(
                Task.status == TaskStatus.done,
                Task.completed_at != None,  # noqa: E711
                Task.completed_at >= start_date
            ).all()
            return _bucket_count(rows, start=start_date)
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "task_completion_rate":
        c = _fetch_metric_series(db, "tasks_completed", organization_id)
        o = _fetch_metric_series(db, "tasks_overdue", organization_id)
        return [round(cv/(cv+ov)*100,2) if (cv+ov) > 0 else 0.0 for cv,ov in zip(c,o)]

    # ── Service Desk / ITSM ────────────────────────────────────────────────────
    if metric_key in ("tickets_open","tickets_created","tickets_resolved",
                       "tickets_p1_count","tickets_p2_count",
                       "first_response_time_avg","resolution_time_avg","csat_avg",
                       "sla_response_breached","sla_resolution_breached",
                       "auto_resolved_count","ticket_time_spent_total"):
        try:
            from app.models.service_desk import Ticket
            rows = db.query(Ticket.created_at, Ticket.status, Ticket.priority,
                            Ticket.first_response_minutes, Ticket.resolution_minutes,
                            Ticket.csat_score, Ticket.sla_response_breached,
                            Ticket.sla_resolution_breached, Ticket.auto_resolved,
                            Ticket.time_spent_minutes).filter(
                Ticket.created_at >= start_date
            ).all()
            bkt: dict[str,float] = defaultdict(float)
            bkt_cnt: dict[str,float] = defaultdict(float)
            for (cat, st, pri, frm, resm, csat, srb, slrb, ar, tsm) in rows:
                if not cat: continue
                k = f"{cat.year:04d}-{cat.month:02d}"
                sv = str(getattr(st,"value",st))
                pv = str(getattr(pri,"value",pri))
                if metric_key == "tickets_open" and sv not in ("closed","resolved","cancelled"):
                    bkt[k] += 1.0
                elif metric_key == "tickets_created":
                    bkt[k] += 1.0
                elif metric_key == "tickets_resolved" and sv in ("closed","resolved"):
                    bkt[k] += 1.0
                elif metric_key == "tickets_p1_count" and pv == "p1_critical":
                    bkt[k] += 1.0
                elif metric_key == "tickets_p2_count" and pv == "p2_high":
                    bkt[k] += 1.0
                elif metric_key == "first_response_time_avg" and frm is not None:
                    bkt[k] += float(frm); bkt_cnt[k] += 1.0
                elif metric_key == "resolution_time_avg" and resm is not None:
                    bkt[k] += float(resm); bkt_cnt[k] += 1.0
                elif metric_key == "csat_avg" and csat is not None:
                    bkt[k] += float(csat); bkt_cnt[k] += 1.0
                elif metric_key == "sla_response_breached" and srb:
                    bkt[k] += 1.0
                elif metric_key == "sla_resolution_breached" and slrb:
                    bkt[k] += 1.0
                elif metric_key == "auto_resolved_count" and ar:
                    bkt[k] += 1.0
                elif metric_key == "ticket_time_spent_total" and tsm:
                    bkt[k] += float(tsm)
            if metric_key in ("first_response_time_avg","resolution_time_avg","csat_avg"):
                return [round(bkt[m["month"]]/bkt_cnt[m["month"]],2)
                        if bkt_cnt.get(m["month"],0)>0 else 0.0 for m in series]
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "ticket_time_log_total":
        try:
            from app.models.service_desk import TicketTimeLog
            rows = db.query(TicketTimeLog.logged_at, TicketTimeLog.minutes).filter(
                TicketTimeLog.logged_at >= start_date
            ).all()
            return _bucket_sum(rows, start=start_date)
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "sla_breach_count":
        try:
            from app.models.billing_reports import SLABreachLog
            rows = db.query(SLABreachLog.breached_at).filter(
                SLABreachLog.breached_at >= start_date
            ).all()
            return _bucket_count(rows, start=start_date)
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "sla_compliance_pct":
        try:
            from app.models.service_desk import ITSMMetricSnapshot
            row = db.query(ITSMMetricSnapshot.sla_compliance_pct).order_by(
                ITSMMetricSnapshot.snapshot_at.desc()
            ).first()
            return _current(float(row[0]) if row and row[0] is not None else 0.0)
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key in ("kb_articles_published","kb_views_total","kb_helpful_count"):
        try:
            from app.models.service_desk import KBArticle, KBStatus
            from sqlalchemy import func as sqf
            if metric_key == "kb_articles_published":
                return _current(float(db.query(KBArticle).filter(KBArticle.status == KBStatus.published).count()))
            if metric_key == "kb_views_total":
                v = db.query(sqf.sum(KBArticle.view_count)).scalar() or 0
                return _current(float(v))
            if metric_key == "kb_helpful_count":
                v = db.query(sqf.sum(KBArticle.helpful_count)).scalar() or 0
                return _current(float(v))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "problems_open":
        try:
            from app.models.service_desk import Problem, ProblemStatus
            return _current(float(db.query(Problem).filter(
                Problem.status.in_([ProblemStatus.open, ProblemStatus.investigating])
            ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "known_errors_active":
        try:
            from app.models.service_desk import KnownError
            return _current(float(db.query(KnownError).filter(KnownError.is_active == True).count()))  # noqa: E712
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key in ("itsm_changes_total","itsm_changes_emergency","itsm_changes_downtime"):
        try:
            from app.models.service_desk import ITSMChangeRequest, ChangeType
            from sqlalchemy import func as sqf
            if metric_key == "itsm_changes_total":
                return _current(float(db.query(ITSMChangeRequest).count()))
            if metric_key == "itsm_changes_emergency":
                return _current(float(db.query(ITSMChangeRequest).filter(
                    ITSMChangeRequest.change_type == ChangeType.emergency
                ).count()))
            if metric_key == "itsm_changes_downtime":
                v = db.query(sqf.sum(ITSMChangeRequest.downtime_minutes)).scalar() or 0
                return _current(float(v))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key in ("assets_total","assets_deployed","assets_in_repair",
                       "license_seats_total","license_used_total","asset_value_total"):
        try:
            from app.models.service_desk import Asset, AssetStatus
            from sqlalchemy import func as sqf
            if metric_key == "assets_total":
                return _current(float(db.query(Asset).count()))
            if metric_key == "assets_deployed":
                return _current(float(db.query(Asset).filter(Asset.status == AssetStatus.deployed).count()))
            if metric_key == "assets_in_repair":
                return _current(float(db.query(Asset).filter(Asset.status == AssetStatus.in_repair).count()))
            if metric_key == "license_seats_total":
                v = db.query(sqf.sum(Asset.license_seats)).filter(Asset.license_seats != None).scalar() or 0  # noqa: E711
                return _current(float(v))
            if metric_key == "license_used_total":
                v = db.query(sqf.sum(Asset.license_used)).filter(Asset.license_used != None).scalar() or 0  # noqa: E711
                return _current(float(v))
            if metric_key == "asset_value_total":
                v = db.query(sqf.sum(Asset.current_value)).filter(Asset.current_value != None).scalar() or 0  # noqa: E711
                return _current(float(v))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "major_incidents_active":
        try:
            from app.models.service_desk import MajorIncident, MajorIncidentStatus
            return _current(float(db.query(MajorIncident).filter(
                MajorIncident.status == MajorIncidentStatus.active
            ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key == "escalations_total":
        try:
            from app.models.service_desk import EscalationLog
            rows = db.query(EscalationLog.triggered_at).filter(
                EscalationLog.triggered_at >= start_date
            ).all()
            return _bucket_count(rows, start=start_date)
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key in ("playbook_success_count","playbook_failure_count"):
        try:
            from app.models.service_desk import AutonomousPlaybook
            from sqlalchemy import func as sqf
            field = AutonomousPlaybook.success_count if metric_key=="playbook_success_count" else AutonomousPlaybook.failure_count
            v = db.query(sqf.sum(field)).scalar() or 0
            return _current(float(v))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

    # ── Approvals & Workflows ──────────────────────────────────────────────────
    if metric_key in ("pending_approvals","approvals_approved_count","approvals_rejected_count"):
        try:
            from app.models.billing_reports import ApprovalRequest
            STATUS = {"pending_approvals":"pending","approvals_approved_count":"approved","approvals_rejected_count":"rejected"}
            return _current(float(db.query(ApprovalRequest).filter(
                ApprovalRequest.status == STATUS[metric_key]
            ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key in ("workflow_runs_total","workflow_success_total","workflow_error_total"):
        try:
            from app.models.billing_reports import AutomationWorkflow
            from sqlalchemy import func as sqf
            FIELD = {"workflow_runs_total": AutomationWorkflow.run_count,
                     "workflow_success_total": AutomationWorkflow.success_count,
                     "workflow_error_total": AutomationWorkflow.error_count}
            v = db.query(sqf.sum(FIELD[metric_key])).scalar() or 0
            return _current(float(v))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

    # ── GRC & Compliance ──────────────────────────────────────────────────────
    if metric_key in ("sod_violations_total","sod_violations_unresolved"):
        try:
            from app.models.billing_reports import SodViolation
            q = db.query(SodViolation)
            if metric_key == "sod_violations_unresolved":
                q = q.filter(SodViolation.resolved == False)  # noqa: E712
            return _current(float(q.count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
    if metric_key in ("grc_audit_events_total","grc_critical_events"):
        try:
            from app.models.billing_reports import GrcAuditLog
            rows = db.query(GrcAuditLog.timestamp, GrcAuditLog.severity).filter(
                GrcAuditLog.timestamp >= start_date
            ).all()
            bkt: dict[str,float] = defaultdict(float)
            for ts, sev in rows:
                if ts:
                    if metric_key == "grc_audit_events_total":
                        bkt[f"{ts.year:04d}-{ts.month:02d}"] += 1.0
                    elif sev == "critical":
                        bkt[f"{ts.year:04d}-{ts.month:02d}"] += 1.0
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

    # ── Imports & Data ────────────────────────────────────────────────────────
    if metric_key in ("imports_completed_count","imports_failed_count","imports_success_rate"):
        try:
            from app.models.billing_reports import ImportJob
            rows = db.query(ImportJob.completed_at, ImportJob.status,
                            ImportJob.succeeded, ImportJob.total_rows).filter(
                ImportJob.completed_at >= start_date
            ).all()
            bkt: dict[str,float] = defaultdict(float)
            bkt_ok: dict[str,float] = defaultdict(float)
            bkt_tot: dict[str,float] = defaultdict(float)
            for ca, st, ok, tot in rows:
                if not ca: continue
                k = f"{ca.year:04d}-{ca.month:02d}"; sv = str(getattr(st,"value",st))
                if metric_key == "imports_completed_count" and sv == "completed":
                    bkt[k] += 1.0
                elif metric_key == "imports_failed_count" and sv in ("failed","partial"):
                    bkt[k] += 1.0
                elif metric_key == "imports_success_rate":
                    bkt_ok[k] += float(ok or 0); bkt_tot[k] += float(tot or 0)
            if metric_key == "imports_success_rate":
                return [round(bkt_ok[m["month"]]/bkt_tot[m["month"]]*100,2)
                        if bkt_tot.get(m["month"],0)>0 else 0.0 for m in series]
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

    return _empty_like()
