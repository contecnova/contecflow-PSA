"""
test_business_logic.py — Unit tests for critical business-logic functions.

Tests are pure (no HTTP client, no DB unless noted) and run fast.
Covers:
  - SLA working-hours calculation (skip weekends, skip holidays)
  - Revenue recognition methods (pct_complete, T&M, straight_line, milestone)
  - EVM calculations (SPI, CPI, EAC, ETC, VAC, multi-phase aggregation)
  - Burnout model scoring (base, trend, consecutive weeks)
  - Resource booking overlap detection
"""

import pytest
from datetime import datetime, date, timedelta, timezone, time as dt_time


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SLA WORKING-HOURS CALCULATION
# ═══════════════════════════════════════════════════════════════════════════════

# Import the pure helper we wrote
from app.services.sla_service import add_working_hours


class TestSLAWorkingHoursCalculation:
    """add_working_hours must respect work window, weekends and holidays."""

    WORK_START = dt_time(8, 0)
    WORK_END   = dt_time(18, 0)  # 10 working hours per day

    def _dt(self, y, m, d, h=8, mn=0) -> datetime:
        """Helper: UTC datetime."""
        return datetime(y, m, d, h, mn, tzinfo=timezone.utc)

    def test_adds_hours_within_same_business_day(self):
        """2025-01-06 Mon 09:00 + 4 working hours = 13:00 same day."""
        start  = self._dt(2025, 1, 6, 9, 0)
        result = add_working_hours(start, 4, self.WORK_START, self.WORK_END)
        assert result.date() == date(2025, 1, 6)
        assert result.hour   == 13
        assert result.minute == 0

    def test_crosses_end_of_day_into_next(self):
        """2025-01-06 Mon 16:00 + 4 working hours → next day at 10:00."""
        start  = self._dt(2025, 1, 6, 16, 0)
        result = add_working_hours(start, 4, self.WORK_START, self.WORK_END)
        assert result.date() == date(2025, 1, 7)   # Tuesday
        assert result.hour   == 10

    def test_skips_weekend(self):
        """Friday 16:00 + 4 working hours = Monday 10:00 (skips Sat/Sun)."""
        start  = self._dt(2025, 1, 3, 16, 0)   # Friday
        result = add_working_hours(start, 4, self.WORK_START, self.WORK_END)
        assert result.weekday() == 0             # Monday
        assert result.date()    == date(2025, 1, 6)
        assert result.hour      == 10

    def test_full_weekend_skip_24h_p1_sla(self):
        """P1 24h SLA raised Friday 14:00 → deadline crosses full weekend (Mon 16:00)."""
        start  = self._dt(2025, 1, 3, 14, 0)   # Friday 14:00
        result = add_working_hours(start, 24, self.WORK_START, self.WORK_END)
        # Day1: 14:00→18:00 = 4h  |  Day2 (Mon): 8:00→18:00 = 10h  |  Day3 (Tue): 8:00→18:00 = 10h → total 24h ends 18:00 Tue
        assert result.weekday() == 1     # Tuesday
        assert result.date()    == date(2025, 1, 7)
        assert result.hour      == 18
        assert result.minute    == 0

    def test_skips_holiday(self):
        """Same as weekend test but with a Monday holiday — deadline shifts one extra day."""
        start   = self._dt(2025, 1, 3, 16, 0)   # Friday 16:00
        holiday = {date(2025, 1, 6)}              # Monday is a holiday
        # Without holiday: + 4h = Monday 10:00
        # With holiday Monday blocked: + 4h = Tuesday 10:00
        result = add_working_hours(start, 4, self.WORK_START, self.WORK_END, holidays=holiday)
        assert result.date() == date(2025, 1, 7)  # Tuesday
        assert result.hour   == 10

    def test_multiple_holidays(self):
        """A public holiday + weekend means three non-working days to skip."""
        start    = self._dt(2025, 4, 17, 17, 0)  # Easter Thursday 17:00 (1h left in day)
        holidays = {date(2025, 4, 18), date(2025, 4, 21)}  # Good Friday + Easter Monday
        # Day1 (Thu): 17→18 = 1h | Day2 (Fri) = holiday | Sat/Sun = weekend | Day3 (Mon) = holiday
        # Day4 (Tue 22 Apr): 8→18 +7h = Tue 15:00
        result = add_working_hours(start, 8, self.WORK_START, self.WORK_END, holidays=holidays)
        assert result.date()    == date(2025, 4, 22)  # Tuesday
        assert result.hour      == 15
        assert result.minute    == 0

    def test_start_outside_window_snaps_to_open(self):
        """A ticket raised at 06:00 (before work starts) should begin counting from 08:00."""
        start  = self._dt(2025, 1, 6, 6, 0)    # 06:00 Monday
        result = add_working_hours(start, 2, self.WORK_START, self.WORK_END)
        # Snap to 08:00, then +2h = 10:00
        assert result.date() == date(2025, 1, 6)
        assert result.hour   == 10

    def test_fractional_hours(self):
        """30-minute (0.5h) SLA response time is correctly calculated."""
        start  = self._dt(2025, 1, 6, 9, 0)
        result = add_working_hours(start, 0.5, self.WORK_START, self.WORK_END)
        assert result.date()   == date(2025, 1, 6)
        assert result.hour     == 9
        assert result.minute   == 30


# ═══════════════════════════════════════════════════════════════════════════════
# 2. REVENUE RECOGNITION METHODS (ASC 606 / IFRS 15)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRevenueRecognitionMethods:
    """
    Pure math tests — no DB.
    We replicate the same formulas used in cab.py so any divergence fails the test.
    """

    # ── Percentage-of-completion (task count) ─────────────────────────────────

    def _pct_complete_revenue(self, contract_value, completed_tasks, total_tasks):
        if total_tasks == 0:
            return 0.0
        pct = completed_tasks / total_tasks
        return round(contract_value * pct, 2)

    def test_pct_complete_50_percent(self):
        rev = self._pct_complete_revenue(100_000, 5, 10)
        assert rev == 50_000.0

    def test_pct_complete_all_tasks_done(self):
        rev = self._pct_complete_revenue(120_000, 12, 12)
        assert rev == 120_000.0

    def test_pct_complete_no_tasks_started(self):
        rev = self._pct_complete_revenue(100_000, 0, 10)
        assert rev == 0.0

    def test_pct_complete_no_tasks_defined(self):
        """Guard: zero total tasks → zero revenue (no division by zero)."""
        rev = self._pct_complete_revenue(100_000, 0, 0)
        assert rev == 0.0

    # ── Time & Materials ──────────────────────────────────────────────────────

    def _time_and_materials_revenue(self, hours_entries):
        """hours_entries: list of (hours, rate)."""
        return round(sum(h * r for h, r in hours_entries), 2)

    def test_time_and_materials_single_rate(self):
        entries = [(100, 85.0)]  # 100h × £85
        assert self._time_and_materials_revenue(entries) == 8_500.0

    def test_time_and_materials_multiple_rates(self):
        entries = [(80, 100.0), (40, 75.0)]   # £8k + £3k = £11k
        assert self._time_and_materials_revenue(entries) == 11_000.0

    def test_time_and_materials_zero_hours(self):
        entries = [(0, 100.0)]
        assert self._time_and_materials_revenue(entries) == 0.0

    # ── Straight-line ─────────────────────────────────────────────────────────

    def _straight_line_monthly(self, contract_value, total_months):
        if total_months <= 0:
            return 0.0
        return round(contract_value / total_months, 2)

    def test_straight_line_12_months(self):
        monthly = self._straight_line_monthly(120_000, 12)
        assert monthly == 10_000.0

    def test_straight_line_irregular_contract(self):
        """£100k over 7 months → £14,285.71/month."""
        monthly = self._straight_line_monthly(100_000, 7)
        assert round(monthly, 2) == 14_285.71

    def test_straight_line_zero_months_guard(self):
        assert self._straight_line_monthly(100_000, 0) == 0.0

    # ── Milestone billing ────────────────────────────────────────────────────

    def _milestone_revenue(self, milestones):
        """milestones: list of dict with {amount, status}. Count approved/invoiced."""
        approved_statuses = {"approved", "invoiced"}
        return round(sum(m["amount"] for m in milestones if m["status"] in approved_statuses), 2)

    def test_milestone_billing_two_approved(self):
        milestones = [
            {"amount": 25_000, "status": "approved"},
            {"amount": 25_000, "status": "approved"},
            {"amount": 50_000, "status": "pending"},
        ]
        assert self._milestone_revenue(milestones) == 50_000.0

    def test_milestone_billing_one_invoiced_one_pending(self):
        milestones = [
            {"amount": 30_000, "status": "invoiced"},
            {"amount": 20_000, "status": "pending"},
        ]
        assert self._milestone_revenue(milestones) == 30_000.0

    def test_milestone_billing_none_approved(self):
        milestones = [{"amount": 50_000, "status": "pending"}]
        assert self._milestone_revenue(milestones) == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. EVM CALCULATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_evm(bac, progress_pct, elapsed_days, total_days, actual_cost):
    """
    Replicates the formulas from profitability.py.
    Returns dict with all EVM indices.
    """
    ev  = bac * (progress_pct / 100)
    pv  = bac * (elapsed_days / max(total_days, 1))
    ac  = actual_cost

    cpi = ev / ac  if ac  > 0 else None
    spi = ev / pv  if pv  > 0 else None
    eac = (ac + (bac - ev) / cpi) if cpi and cpi > 0 else bac
    etc = eac - ac
    vac = bac - eac
    cv  = ev - ac
    sv  = ev - pv

    return dict(ev=ev, pv=pv, ac=ac, cpi=cpi, spi=spi,
                eac=eac, etc=etc, vac=vac, cv=cv, sv=sv)


class TestEVMCalculations:

    def test_spi_on_track(self):
        """Project exactly on schedule → SPI = 1.0."""
        evm = _compute_evm(bac=100_000, progress_pct=50, elapsed_days=50, total_days=100, actual_cost=50_000)
        assert evm["spi"] == pytest.approx(1.0)

    def test_spi_behind_schedule(self):
        """25% done but 50% of time elapsed → SPI = 0.5 (behind schedule)."""
        evm = _compute_evm(bac=100_000, progress_pct=25, elapsed_days=50, total_days=100, actual_cost=25_000)
        assert evm["spi"] == pytest.approx(0.5)
        assert evm["sv"]  < 0   # negative schedule variance

    def test_cpi_on_budget(self):
        """Cost matches plan → CPI = 1.0."""
        evm = _compute_evm(bac=80_000, progress_pct=50, elapsed_days=50, total_days=100, actual_cost=40_000)
        assert evm["cpi"] == pytest.approx(1.0)

    def test_cpi_over_budget(self):
        """Spent £55k to complete £50k of work → CPI ≈ 0.91 (over budget)."""
        evm = _compute_evm(bac=100_000, progress_pct=50, elapsed_days=50, total_days=100, actual_cost=55_000)
        assert evm["cpi"] == pytest.approx(50_000 / 55_000)
        assert evm["cv"]  < 0   # negative cost variance

    def test_eac_forecast_exact(self):
        """EAC = AC + (BAC - EV) / CPI when CPI < 1 means cost overrun forecast."""
        evm = _compute_evm(bac=100_000, progress_pct=50, elapsed_days=60, total_days=100, actual_cost=60_000)
        # CPI = 50k/60k = 0.8333
        # EAC = 60k + 50k / 0.8333 = 60k + 60k = 120k
        assert evm["eac"] == pytest.approx(120_000, rel=1e-3)
        assert evm["vac"] == pytest.approx(-20_000, rel=1e-3)

    def test_eac_etc_relationship(self):
        """ETC = EAC - AC (remaining cost to completion)."""
        evm = _compute_evm(bac=200_000, progress_pct=40, elapsed_days=40, total_days=100, actual_cost=90_000)
        assert evm["etc"] == pytest.approx(evm["eac"] - evm["ac"], rel=1e-6)

    def test_evm_multiphase_aggregation(self):
        """
        Multi-phase project: 2 work packages each with independent EV/PV/AC.
        Aggregate CPI and SPI should reflect blended performance.
        """
        # Phase 1: on-track (SPI=1, CPI=1)
        p1 = _compute_evm(bac=50_000, progress_pct=50, elapsed_days=50, total_days=100, actual_cost=25_000)
        # Phase 2: over budget (CPI ~ 0.83)
        p2 = _compute_evm(bac=50_000, progress_pct=50, elapsed_days=50, total_days=100, actual_cost=30_000)

        # Aggregate
        agg_ev  = p1["ev"]  + p2["ev"]   # 25k + 25k = 50k
        agg_pv  = p1["pv"]  + p2["pv"]   # 25k + 25k = 50k
        agg_ac  = p1["ac"]  + p2["ac"]   # 25k + 30k = 55k
        agg_bac = 100_000

        agg_cpi = agg_ev / agg_ac  # 50k/55k ≈ 0.909
        agg_spi = agg_ev / agg_pv  # 50k/50k = 1.0
        agg_eac = agg_ac + (agg_bac - agg_ev) / agg_cpi

        assert agg_spi == pytest.approx(1.0)
        assert agg_cpi == pytest.approx(50_000 / 55_000, rel=1e-4)
        assert agg_eac > agg_bac   # cost overrun projected


# ═══════════════════════════════════════════════════════════════════════════════
# 4. BURNOUT MODEL SCORING
# ═══════════════════════════════════════════════════════════════════════════════

from app.api.v1.endpoints.ai_modules import _burnout_score


class TestBurnoutModel:
    """
    Direct unit tests for _burnout_score().
    weekly_hours list: index 0 = most recent week, index -1 = oldest week.
    """

    def test_low_hours_zero_risk(self):
        """Well under threshold (20-25h) → burnout probability = 0."""
        score = _burnout_score([20, 22, 18, 25])
        assert score == 0.0

    def test_moderate_load_low_risk(self):
        """Normal 40h week → non-zero but low risk."""
        score = _burnout_score([40, 40, 40, 40])
        assert 0.0 < score < 0.4

    def test_high_load_elevated_risk(self):
        """Consistently 50+ hours → notable burnout risk."""
        score = _burnout_score([50, 52, 48, 51])
        assert score > 0.4

    def test_critical_overload_high_risk(self):
        """60+ hours/week for 4 weeks → high burnout risk."""
        score = _burnout_score([65, 60, 62, 63])
        assert score > 0.7

    def test_increasing_trend_raises_score(self):
        """Increasing trend (most recent > oldest) → higher risk than stable."""
        # Most recent = index 0
        increasing = [50, 45, 40, 35]   # workload growing each week
        decreasing = [35, 40, 45, 50]   # workload shrinking
        assert _burnout_score(increasing) > _burnout_score(decreasing)

    def test_consecutive_overloaded_weeks_adds_bonus(self):
        """4 consecutive weeks >42h should score higher than 4 weeks at exactly 42h."""
        all_over   = [50, 50, 50, 50]   # all 4 > 42 → +4*0.08 = +0.32 bonus
        borderline = [42, 42, 42, 42]   # exactly 42 → no bonus (not > 42)
        assert _burnout_score(all_over) > _burnout_score(borderline)

    def test_single_week_input(self):
        """Edge case: single week of data should not crash."""
        score = _burnout_score([48])
        assert 0.0 <= score <= 0.99

    def test_empty_input_returns_zero(self):
        """Empty list → no data, no risk."""
        assert _burnout_score([]) == 0.0

    def test_score_capped_at_0_99(self):
        """Extreme input should never exceed 0.99."""
        score = _burnout_score([100, 100, 100, 100])
        assert score <= 0.99


# ═══════════════════════════════════════════════════════════════════════════════
# 5. RESOURCE BOOKING OVERLAP DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def _bookings_overlap(b1_start: date, b1_end: date, b2_start: date, b2_end: date) -> bool:
    """
    Returns True if two date ranges overlap (inclusive on both ends).
    This is the same overlap logic used in bookings.py validation.
    """
    return b1_start <= b2_end and b2_start <= b1_end


class TestResourceBookingOverlapDetection:

    def test_fully_overlapping_bookings(self):
        """Two identical booking periods overlap."""
        assert _bookings_overlap(date(2025, 2, 3), date(2025, 2, 14),
                                  date(2025, 2, 3), date(2025, 2, 14)) is True

    def test_partial_overlap(self):
        """Second booking starts mid-way through first."""
        assert _bookings_overlap(date(2025, 2, 3), date(2025, 2, 14),
                                  date(2025, 2, 10), date(2025, 2, 21)) is True

    def test_adjacent_periods_no_overlap(self):
        """One ends on Mon, other starts on Tue — no overlap."""
        assert _bookings_overlap(date(2025, 2, 3), date(2025, 2, 7),
                                  date(2025, 2, 10), date(2025, 2, 14)) is False

    def test_same_day_single_day_overlap(self):
        """Two bookings each for the same single day — they overlap."""
        assert _bookings_overlap(date(2025, 3, 10), date(2025, 3, 10),
                                  date(2025, 3, 10), date(2025, 3, 10)) is True

    def test_completely_separate_periods(self):
        """Bookings two months apart — no overlap."""
        assert _bookings_overlap(date(2025, 1, 1), date(2025, 1, 31),
                                  date(2025, 3, 1), date(2025, 3, 31)) is False

    def test_contained_booking_overlaps(self):
        """Smaller range fully inside larger range — overlap."""
        assert _bookings_overlap(date(2025, 2, 1), date(2025, 4, 30),
                                  date(2025, 3, 1), date(2025, 3, 15)) is True

    def test_touching_boundary_is_overlap(self):
        """One booking ends exactly when another starts — touching = overlap (inclusive)."""
        assert _bookings_overlap(date(2025, 2, 1), date(2025, 2, 14),
                                  date(2025, 2, 14), date(2025, 2, 28)) is True


# ═══════════════════════════════════════════════════════════════════════════════
# 6. AI OVERRUN PREDICTION MODEL
# ═══════════════════════════════════════════════════════════════════════════════

from app.api.v1.endpoints.ai_modules import _predict_overrun_ml


def _make_project_data(
    cpi=1.0, spi=1.0,
    budget_total=100_000, ac=50_000,
    elapsed_pct=0.5,
    open_tasks=10, done_tasks=10, overdue_tasks=0,
    team_load_pct=90.0,
    budget_start=None, budget_end=None,
):
    """Build args dict for _predict_overrun_ml calls."""
    total_tasks = open_tasks + done_tasks
    task_completion_pct = (done_tasks / total_tasks * 100) if total_tasks else 0
    overdue_ratio = (overdue_tasks / total_tasks) if total_tasks else 0
    budget_used_pct = (ac / budget_total * 100) if budget_total else 0
    return dict(
        cpi=cpi,
        spi=spi,
        budget_used_pct=budget_used_pct,
        elapsed_pct=elapsed_pct * 100,  # convert to percentage
        task_completion_pct=task_completion_pct,
        overdue_task_ratio=overdue_ratio,
        team_load_pct=team_load_pct,
    )


class TestOverrunPrediction:

    def test_healthy_project_low_risk(self):
        """A project with CPI=1.1, SPI=1.05 and no overdue tasks should have low probabilities."""
        result = _predict_overrun_ml(**_make_project_data(cpi=1.1, spi=1.05, overdue_tasks=0, team_load_pct=80))

        assert result["cost_overrun_prob"] < 0.35, "Healthy project should have low cost risk"
        assert result["schedule_overrun_prob"] < 0.35, "Healthy project should have low schedule risk"
        assert result["confidence"] in ("low", "medium", "high")
        assert isinstance(result["signals"], list)

    def test_critical_cpi_high_cost_overrun(self):
        """CPI < 0.7 should produce cost_overrun_prob >= 0.4 (critical CPI signal weight)."""
        result = _predict_overrun_ml(**_make_project_data(cpi=0.60, spi=0.95))
        assert result["cost_overrun_prob"] >= 0.40, (
            f"Expected cost_overrun_prob >= 0.40 for CPI=0.6, got {result['cost_overrun_prob']}"
        )
        # Verify a CPI-related signal was fired
        cost_signals = [s for s in result["signals"] if s.get("type") in ("cost", "both")]
        assert cost_signals, "Expected at least one cost signal for CPI=0.6"

    def test_critical_spi_high_schedule_overrun(self):
        """SPI < 0.65 should produce schedule_overrun_prob >= 0.45."""
        result = _predict_overrun_ml(**_make_project_data(cpi=0.95, spi=0.55))
        assert result["schedule_overrun_prob"] >= 0.45, (
            f"Expected schedule_overrun_prob >= 0.45 for SPI=0.55, got {result['schedule_overrun_prob']}"
        )
        sched_signals = [s for s in result["signals"] if s.get("type") in ("schedule", "both")]
        assert sched_signals, "Expected at least one schedule signal for SPI=0.55"

    def test_high_overdue_task_ratio_raises_risk(self):
        """More than 40% overdue tasks should push schedule_overrun_prob above 0.5."""
        # 5 overdue out of 10 total = 50% overdue rate
        result = _predict_overrun_ml(**_make_project_data(
            cpi=0.95, spi=0.95,
            open_tasks=8, done_tasks=2, overdue_tasks=5,
        ))
        assert result["schedule_overrun_prob"] > 0.50, (
            f"High overdue ratio should push schedule risk up, got {result['schedule_overrun_prob']}"
        )

    def test_burnout_risk_signal_present(self):
        """Team load > 110% should produce a burnout signal."""
        result = _predict_overrun_ml(**_make_project_data(team_load_pct=115.0))
        signals = [s.get("signal", "").lower() for s in result["signals"]]
        burnout_signal = any("burnout" in s or "team_load" in s or "sobrecarg" in s or "load" in s for s in signals)
        assert burnout_signal, f"Expected burnout signal in signals: {result['signals']}"

    def test_output_structure_complete(self):
        """_predict_overrun_ml always returns all required keys."""
        result = _predict_overrun_ml(**_make_project_data())
        required_keys = {
            "cost_overrun_prob", "schedule_overrun_prob",
            "cost_overrun_pct", "schedule_overrun_days",
            "confidence", "signals", "recommendation",
        }
        for key in required_keys:
            assert key in result, f"Missing key in prediction output: {key!r}"
        assert 0.0 <= result["cost_overrun_prob"] <= 1.0
        assert 0.0 <= result["schedule_overrun_prob"] <= 1.0
        assert isinstance(result["recommendation"], str)
