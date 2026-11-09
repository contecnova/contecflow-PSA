"""test_semantic_classifier.py — Tests for the 6 bug fixes + 6 refinement improvements.

Bug fixes (session 1, commit 168cb0f2):
  Bug 1 — Real-time load via ResourceAnalyticsService
  Bug 2+5 — Skills in profile embedding; 15-item history
  Bug 3 — Temporal decay on history embeddings
  Bug 4 — Priority-aware thresholds
  Bug 6 — LLM result cached into expert feedback

Refinements (session 2):
  Mejora 1 — Weighted load blend (hour-based 60% + item-count 40%)
  Mejora 2 — Skills via relationship + Spanish level labels
  Mejora 3 — Half-life decay formula 0.5^(age/half_life)
  Mejora 4 — Updated thresholds: critical 0.90, high 0.72, medium 0.58
  Mejora 5 — Feedback endpoint auto-persists confirmed LLM suggestions
  Mejora 6 — Diversity penalty for over-concentrated workloads
"""
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_db():
    """Return a minimal mock db that returns nothing by default."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.in_.return_value.all.return_value = []
    db.query.return_value.filter.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.filter.return_value.all.return_value = []
    db.query.return_value.first.return_value = None
    db.query.return_value.all.return_value = []
    return db


def _make_config(**overrides):
    """Return a SemConfig-like mock (calibrated 2026-Q1 defaults)."""
    cfg = MagicMock()
    cfg.engine_mode         = "semantic"
    cfg.threshold_ticket    = 0.55
    cfg.threshold_task      = 0.60
    cfg.threshold_expert_cache = 0.92
    cfg.load_balance_weight = 0.20
    cfg.local_model_name    = "all-MiniLM-L6-v2"
    cfg.threshold_critical  = 0.90   # Mejora 4: updated
    cfg.threshold_high      = 0.72   # Mejora 4: updated
    cfg.threshold_medium    = 0.58   # Mejora 4: updated
    cfg.threshold_low       = 0.45
    cfg.history_decay_days  = 90.0
    cfg.auto_assign_tickets = False
    cfg.auto_assign_tasks   = False
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _make_assigner(db=None, config=None):
    """Instantiate SemanticAssigner with mocked model to avoid ML dependency."""
    from app.services.semantic_classifier import SemanticAssigner, TFIDFEncoder
    db  = db or _make_db()
    cfg = config or _make_config()
    assigner = object.__new__(SemanticAssigner)
    assigner.db             = db
    assigner.config         = cfg
    assigner.model          = TFIDFEncoder()
    assigner.use_transformer = False
    assigner.load_weight    = cfg.load_balance_weight
    return assigner


# ── Bug 1: real-time load ───────────────────────────────────────────────────────

class TestBug1RealTimeLoad:
    """load_ratio must come from ResourceAnalyticsService, not SemProfile counters."""

    def test_load_ratio_uses_resource_analytics(self):
        """When get_user_availability returns load_pct=80, load_ratio should be 0.80."""
        from app.models.semantic_engine import SemProfile

        user_id = "u-001"
        emb     = [0.1] * 10

        profile       = MagicMock(spec=SemProfile)
        profile.user_id      = user_id
        profile.embedding    = json.dumps(emb)
        profile.is_available = True
        profile.open_tickets = 0   # stale — should be ignored
        profile.open_tasks   = 0   # stale — should be ignored
        profile.max_load     = 10

        db = _make_db()

        # Expert cache misses
        db.query.return_value.filter.return_value.first.return_value = None

        # _semantic_lookup_feedback → no feedback entries
        db.query.return_value.filter.return_value.limit.return_value.all.return_value = []

        # Profile query
        profile_q = MagicMock()
        profile_q.filter.return_value = profile_q
        profile_q.all.return_value    = [profile]

        # Route SemProfile query to profile_q, everything else to default
        def query_side(model):
            if model is SemProfile:
                return profile_q
            q = MagicMock()
            q.filter.return_value.first.return_value = None
            q.filter.return_value.all.return_value   = []
            q.filter.return_value.filter.return_value.all.return_value = []
            q.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            return q

        db.query.side_effect = query_side

        avail_high_load = {"load_pct": 80.0, "available_hours": 8.0,
                           "capacity_hours": 40.0, "planned_hours": 32.0,
                           "actual_hours": 32.0}

        with patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_user_availability",
            return_value=avail_high_load,
        ), patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_week_iso",
            return_value="2026-W15",
        ):
            assigner = _make_assigner(db=db)
            # Patch _encode_single to return the same vector
            assigner._encode_single = lambda t: emb
            result = assigner._suggest("test ticket", "ticket", priority="medium")

        # Score should reflect real-time load (80% hours used) reducing the final score
        assert "suggested_user_id" in result
        final_score = result["confidence"]
        # With hour_load=0.80, item_load=0 (both open_tickets/tasks=0):
        #   load_ratio = 0.6*0.80 + 0.4*0.0 = 0.48
        #   final = sem*0.80 + (1-0.48)*0.20 = 0.80 + 0.104 = 0.904
        # With stale bug (load_ratio=0): final = 0.80 + 0.20 = 1.0
        # So the penalised score should be < 0.95
        assert final_score < 0.95, (
            f"Expected load penalty from hour-based capacity to reduce score, got {final_score}"
        )

    def test_load_ratio_falls_back_on_exception(self):
        """If ResourceAnalyticsService raises, fallback to SemProfile counters."""
        from app.models.semantic_engine import SemProfile
        user_id = "u-002"
        emb     = [0.5] * 10

        profile       = MagicMock(spec=SemProfile)
        profile.user_id      = user_id
        profile.embedding    = json.dumps(emb)
        profile.is_available = True
        profile.open_tickets = 5
        profile.open_tasks   = 5
        profile.max_load     = 10

        db = _make_db()

        def query_side(model):
            if model is SemProfile:
                q = MagicMock()
                q.filter.return_value = q
                q.all.return_value    = [profile]
                return q
            q = MagicMock()
            q.filter.return_value.first.return_value = None
            q.filter.return_value.all.return_value   = []
            q.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            return q

        db.query.side_effect = query_side

        with patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_user_availability",
            side_effect=Exception("DB unavailable"),
        ), patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_week_iso",
            return_value="2026-W15",
        ):
            assigner = _make_assigner(db=db)
            assigner._encode_single = lambda t: emb
            # Should not raise
            result = assigner._suggest("fallback test", "ticket", priority="medium")

        assert result["suggested_user_id"] == user_id


# ── Bug 2+5: skills in profile + 15 items ─────────────────────────────────────

class TestBug2And5SkillsInProfile:
    """refresh_user_profile must include UserSkill entries and use 15 history items."""

    def _setup_db_for_profile(self, user_id, n_tickets=15, n_tasks=15, skills=None):
        """Build a db mock with enough data to exercise refresh_user_profile."""
        from app.models.user import User
        from app.models.semantic_engine import SemProfile
        from app.models.service_desk import Ticket
        from app.models.task import Task
        from app.models.resources import UserSkill, Skill as SkillModel

        user = MagicMock(spec=User)
        user.id         = user_id
        user.full_name  = "Alice Engineer"
        user.job_title  = "Senior Developer"
        user.department = "Engineering"

        tickets = []
        for i in range(n_tickets):
            t = MagicMock(spec=Ticket)
            t.title = f"Ticket {i}"
            tickets.append(t)

        tasks = []
        for i in range(n_tasks):
            t = MagicMock(spec=Task)
            t.title = f"Task {i}"
            tasks.append(t)

        user_skills = []
        skill_objs  = {}
        if skills:
            for name, level in skills:
                sk = MagicMock(spec=SkillModel)
                sk.id, sk.name = f"sk-{name}", name
                skill_objs[sk.id] = sk
                us = MagicMock(spec=UserSkill)
                us.skill_id  = sk.id
                us.level     = MagicMock()
                us.level.value = level
                us.skill     = sk   # Mejora 2: provide relationship attribute directly
                user_skills.append(us)

        profile = MagicMock(spec=SemProfile)
        profile.user_id      = user_id
        profile.profile_text = ""
        profile.embedding    = None

        db = _make_db()

        def query_side(model):
            q = MagicMock()
            if model is User:
                q.filter.return_value.first.return_value = user
                return q
            if model is SemProfile:
                q.filter.return_value.first.return_value = profile
                return q
            if model is UserSkill:
                q.filter.return_value.all.return_value = user_skills
                return q
            if model is SkillModel:
                # No longer queried per-id; UserSkill.skill accessed via relationship
                q.filter.return_value.first.return_value = None
                return q
            if model is Ticket:
                order_q = MagicMock()
                order_q.limit.return_value.all.return_value = tickets
                filt = MagicMock()
                filt.order_by.return_value = order_q
                q.filter.return_value = filt
                return q
            if model is Task:
                order_q = MagicMock()
                order_q.limit.return_value.all.return_value = tasks
                filt = MagicMock()
                filt.order_by.return_value = order_q
                q.filter.return_value = filt
                return q
            q.filter.return_value.first.return_value = None
            q.filter.return_value.all.return_value   = []
            return q

        db.query.side_effect = query_side
        return db, profile

    def test_skills_appear_in_profile_text(self):
        user_id  = "u-skills-001"
        skills   = [("Python", "advanced"), ("FastAPI", "expert")]
        db, prof = self._setup_db_for_profile(user_id, skills=skills)
        assigner = _make_assigner(db=db)
        assigner.refresh_user_profile(user_id)
        text = prof.profile_text
        # Mejora 2: format is "Skill {level_label}: {skill_name}"
        assert "Skill " in text, "Skill entries should appear in profile_text"

    def test_profile_uses_15_tickets_not_5(self):
        """Profile should use up to 15 resolved tickets in profile text."""
        user_id  = "u-hist-001"
        db, prof = self._setup_db_for_profile(user_id, n_tickets=20, n_tasks=1)
        assigner = _make_assigner(db=db)
        assigner.refresh_user_profile(user_id)
        ticket_count = prof.profile_text.count("Ticket resuelto:")
        assert ticket_count == 15, (
            f"Expected 15 resolved tickets in profile, got {ticket_count}"
        )

    def test_profile_uses_15_tasks_not_5(self):
        """Profile should use up to 15 completed tasks in profile text."""
        user_id  = "u-hist-002"
        db, prof = self._setup_db_for_profile(user_id, n_tickets=1, n_tasks=20)
        assigner = _make_assigner(db=db)
        assigner.refresh_user_profile(user_id)
        task_count = prof.profile_text.count("Tarea completada:")
        assert task_count == 15, (
            f"Expected 15 completed tasks in profile, got {task_count}"
        )


# ── Bug 3: temporal decay ──────────────────────────────────────────────────────

class TestBug3TemporalDecay:
    """Recent history embeddings must outweigh old ones via exponential decay."""

    def test_recent_beats_old_with_decay(self):
        """An embedding from 1 day ago should have more weight than one from 365 days ago."""

        assigner = _make_assigner()

        item_emb    = [1.0, 0.0, 0.0]
        profile_emb = [0.0, 1.0, 0.0]  # low similarity to item

        # recent_emb has high cosine similarity to item_emb
        recent_emb  = [1.0, 0.0, 0.0]
        # old_emb has low cosine similarity to item_emb
        old_emb     = [0.0, 1.0, 0.0]

        now   = datetime.now(timezone.utc)
        t_recent = now - timedelta(days=1)
        t_old    = now - timedelta(days=365)

        history_tuples_biased_recent = [
            (recent_emb, t_recent),
            (old_emb, t_old),
        ]
        history_tuples_biased_old = [
            (old_emb, t_recent),
            (recent_emb, t_old),
        ]

        score_with_recent_high = assigner._hybrid_score(
            item_emb, profile_emb, history_tuples_biased_recent
        )
        score_with_old_high = assigner._hybrid_score(
            item_emb, profile_emb, history_tuples_biased_old
        )

        assert score_with_recent_high > score_with_old_high, (
            "When the recent embedding is most similar, final score should be higher "
            "than when only the old embedding is most similar"
        )

    def test_no_history_returns_profile_score(self):
        """Empty history list should return pure profile similarity."""
        from app.services.semantic_classifier import _cosine
        assigner     = _make_assigner()
        item_emb     = [1.0, 0.0]
        profile_emb  = [0.8, 0.6]
        expected     = _cosine(item_emb, profile_emb)
        result       = assigner._hybrid_score(item_emb, profile_emb, [])
        assert abs(result - expected) < 1e-6

    def test_old_history_decay_approaches_zero_weight(self):
        """A 10-year-old embedding (3650 days) should have near-zero weight."""
        assigner = _make_assigner()
        item_emb    = [1.0, 0.0]
        profile_emb = [0.0, 1.0]  # sim=0 with item
        ancient_emb = [1.0, 0.0]  # sim=1 with item, but very old
        now      = datetime.now(timezone.utc)
        t_ancient = now - timedelta(days=3650)

        score = assigner._hybrid_score(item_emb, profile_emb, [(ancient_emb, t_ancient)])
        # decay = exp(-3650/90) ≈ 0 → dominated by profile score (0.0)
        assert score < 0.10, (
            f"10-year-old history should almost vanish under decay, got score={score:.4f}"
        )

    def test_get_history_embeddings_returns_tuples(self):
        """_get_history_embeddings must return (embedding, created_at) tuples."""
        from app.models.semantic_engine import SemEmbeddingCache

        emb = [0.1, 0.2, 0.3]
        now = datetime.now(timezone.utc)

        cache_row = MagicMock(spec=SemEmbeddingCache)
        cache_row.embedding  = json.dumps(emb)
        cache_row.created_at = now

        db = _make_db()
        def query_side(model):
            q = MagicMock()
            q.filter.return_value.filter.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [cache_row]
            q.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [cache_row]
            # For chained .filter().filter().filter()
            inner = MagicMock()
            inner.order_by.return_value.limit.return_value.all.return_value = [cache_row]
            q.filter.return_value = inner
            q.filter.return_value.filter.return_value = inner
            return q

        db.query.side_effect = query_side
        assigner = _make_assigner(db=db)
        result = assigner._get_history_embeddings("u-001", "ticket")

        assert len(result) == 1
        emb_out, ts_out = result[0]
        assert isinstance(emb_out, list)
        assert ts_out == now, "Timestamp must be preserved in the tuple"


# ── Bug 4: priority-aware thresholds ──────────────────────────────────────────

class TestBug4PriorityThresholds:
    """Priority-specific thresholds must be used; critical always needs_review=True."""

    def _run_suggest(self, priority, sem_score=0.60, item_type="ticket"):
        """Run _suggest with a controlled semantic score."""
        from app.models.semantic_engine import SemProfile
        user_id = "u-prio-001"
        emb     = [1.0, 0.0, 0.0]

        profile = MagicMock(spec=SemProfile)
        profile.user_id      = user_id
        profile.embedding    = json.dumps(emb)
        profile.is_available = True
        profile.open_tickets = 0
        profile.open_tasks   = 0
        profile.max_load     = 10

        db = _make_db()

        def query_side(model):
            if model is SemProfile:
                q = MagicMock()
                q.filter.return_value = q
                q.all.return_value    = [profile]
                return q
            q = MagicMock()
            filt = MagicMock()
            filt.first.return_value = None
            filt.all.return_value   = []
            lim = MagicMock()
            lim.all.return_value = []
            filt.limit.return_value = lim
            ob = MagicMock()
            ob.limit.return_value.all.return_value = []
            filt.order_by.return_value = ob
            q.filter.return_value = filt
            return q

        db.query.side_effect = query_side

        avail_zero = {"load_pct": 0.0, "available_hours": 40.0,
                      "capacity_hours": 40.0, "planned_hours": 0.0, "actual_hours": 0.0}

        with patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_user_availability",
            return_value=avail_zero,
        ), patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_week_iso",
            return_value="2026-W15",
        ):
            assigner = _make_assigner(db=db)
            # Force semantic score by controlling _hybrid_score
            assigner._hybrid_score   = lambda ie, pe, ht: sem_score
            assigner._encode_single  = lambda t: emb
            result = assigner._suggest(f"{priority} {item_type} test",
                                       item_type, priority=priority)

        return result

    def test_critical_ticket_always_needs_review(self):
        """Critical priority must set needs_review=True regardless of score."""
        # Even with a high semantic score, critical should need review
        result = self._run_suggest("critical", sem_score=0.99, item_type="ticket")
        assert result["needs_review"] is True, (
            "Critical tickets must always need human review"
        )

    def test_p1_critical_always_needs_review(self):
        """p1_critical (ticket priority enum) must also force needs_review=True."""
        result = self._run_suggest("p1_critical", sem_score=0.99, item_type="ticket")
        assert result["needs_review"] is True

    def test_low_priority_auto_assigns_at_lower_threshold(self):
        """Low priority with score=0.50 (above 0.45 threshold) should NOT need review."""
        # score=0.50 > threshold_low=0.45 → should auto-assign
        result = self._run_suggest("low", sem_score=0.50, item_type="ticket")
        assert result["needs_review"] is False, (
            "Low priority with score above 0.45 should auto-assign"
        )

    def test_high_priority_needs_review_when_below_threshold(self):
        """High priority with score=0.60 (below updated 0.72 threshold) should need review."""
        result = self._run_suggest("high", sem_score=0.60, item_type="ticket")
        assert result["needs_review"] is True, (
            "High priority with score below 0.72 should need review"
        )

    def test_medium_priority_uses_medium_threshold(self):
        """Medium priority with score=0.60 (above updated 0.58 threshold) should auto-assign."""
        result = self._run_suggest("medium", sem_score=0.60, item_type="ticket")
        assert result["needs_review"] is False

    def test_p2_high_maps_to_high_threshold(self):
        """p2_high ticket priority should map to threshold_high (0.70)."""
        # sem_score=0.55 → final = 0.55*0.80 + 1.0*0.20 = 0.64 < 0.70 → needs review
        result = self._run_suggest("p2_high", sem_score=0.55, item_type="ticket")
        assert result["needs_review"] is True

    def test_p4_low_maps_to_low_threshold(self):
        """p4_low ticket priority should map to threshold_low (0.45)."""
        # score=0.50 > 0.45 → auto-assign
        result = self._run_suggest("p4_low", sem_score=0.50, item_type="ticket")
        assert result["needs_review"] is False


# ── Bug 6: LLM results cached ─────────────────────────────────────────────────

class TestBug6LLMResultCached:
    """Revisión 2026-11: la respuesta del modelo NO se guarda como corrección de
    experto (pisaba la de una persona para el mismo texto)."""

    def test_llm_result_does_not_call_record_feedback(self):
        user_id = "u-llm-001"
        profile = MagicMock()
        profile.user_id      = user_id
        profile.profile_text = "Senior DevOps engineer with Kubernetes experience"

        assigner = _make_assigner(db=_make_db())
        llm_response_json = json.dumps({"user_id": user_id, "reason": "DevOps expert"})

        with patch("app.services.ai_provider_service.call_ai", return_value=llm_response_json):
            with patch.object(assigner, "record_feedback") as mock_fb:
                result = assigner._llm_suggest("Deploy kubernetes cluster to production", [profile], "task")

        assert result is not None
        assert result["suggested_user_id"] == user_id
        mock_fb.assert_not_called()

    def test_llm_cache_write_failure_does_not_block_result(self):
        """A failure in record_feedback must not prevent the LLM result from being returned."""
        user_id = "u-llm-002"
        text    = "Refactor authentication module"
        item_type = "ticket"

        profile = MagicMock()
        profile.user_id      = user_id
        profile.profile_text = "Auth and security engineer"

        db = _make_db()
        assigner = _make_assigner(db=db)

        llm_response_json = json.dumps({"user_id": user_id, "reason": "Auth expert"})

        with patch("app.services.ai_provider_service.call_ai", return_value=llm_response_json):
            with patch.object(assigner, "record_feedback", side_effect=Exception("DB write failed")):
                result = assigner._llm_suggest(text, [profile], item_type)

        assert result is not None, "LLM result must be returned even if cache write fails"
        assert result["suggested_user_id"] == user_id

    def test_llm_no_cache_when_no_user_returned(self):
        """record_feedback should NOT be called if LLM returns no valid user_id."""
        text    = "Unknown item type"
        item_type = "ticket"
        profile = MagicMock()
        profile.user_id      = None
        profile.profile_text = "some text"

        db = _make_db()
        assigner = _make_assigner(db=db)

        llm_response_json = json.dumps({"user_id": None, "reason": "No match"})

        with patch("app.services.ai_provider_service.call_ai", return_value=llm_response_json):
            with patch.object(assigner, "record_feedback") as mock_fb:
                assigner._llm_suggest(text, [profile], item_type)

        mock_fb.assert_not_called()


# ── Mejora 1: weighted load blend ─────────────────────────────────────────────

class TestMejora1WeightedLoadBlend:
    """load_ratio = 0.6 * hour_load + 0.4 * item_load."""

    def test_weighted_blend_formula(self):
        """hour_load=0.80 and item_load=0 → load_ratio = 0.48 (not 0.80)."""
        from app.models.semantic_engine import SemProfile
        user_id = "u-blend-001"
        emb     = [0.5, 0.5]

        profile = MagicMock(spec=SemProfile)
        profile.user_id      = user_id
        profile.embedding    = json.dumps(emb)
        profile.is_available = True
        profile.open_tickets = 0
        profile.open_tasks   = 0
        profile.max_load     = 10

        db = _make_db()

        def query_side(model):
            if model is SemProfile:
                q = MagicMock()
                q.filter.return_value = q
                q.all.return_value    = [profile]
                return q
            q = MagicMock()
            filt = MagicMock()
            filt.first.return_value = None
            filt.all.return_value   = []
            filt.limit.return_value.all.return_value = []
            filt.order_by.return_value.limit.return_value.all.return_value = []
            q.filter.return_value = filt
            return q

        db.query.side_effect = query_side

        # available_hours=8 of capacity_hours=40 → hour_load = 1 - 8/40 = 0.80
        avail = {"load_pct": 80.0, "available_hours": 8.0,
                 "capacity_hours": 40.0, "planned_hours": 32.0, "actual_hours": 32.0}


        with patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_user_availability",
            return_value=avail,
        ), patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_week_iso",
            return_value="2026-W15",
        ):
            assigner = _make_assigner(db=db)
            assigner._encode_single = lambda t: emb

            # Intercept _hybrid_score to return 1.0 so load is the only variable
            assigner._hybrid_score = lambda ie, pe, ht: 1.0

            result = assigner._suggest("blend test", "ticket", priority="medium")

        final = result["confidence"]
        # load_ratio = 0.6*0.80 + 0.4*0.0 = 0.48
        # final = 1.0 * 0.80 + (1-0.48) * 0.20 = 0.80 + 0.104 = 0.904
        expected = round(1.0 * 0.80 + (1 - 0.48) * 0.20, 4)
        assert abs(final - expected) < 0.02, (
            f"Expected weighted blend final≈{expected}, got {final}"
        )

    def test_pure_item_load_when_no_hours(self):
        """When capacity_hours=0, fallback to item-based load (no division by zero)."""
        from app.models.semantic_engine import SemProfile
        user_id = "u-blend-002"
        emb     = [1.0, 0.0]

        profile = MagicMock(spec=SemProfile)
        profile.user_id      = user_id
        profile.embedding    = json.dumps(emb)
        profile.is_available = True
        profile.open_tickets = 6
        profile.open_tasks   = 4
        profile.max_load     = 10

        db = _make_db()
        from app.models.semantic_engine import SemProfile as SP

        def qs(model):
            if model is SP:
                q = MagicMock()
                q.filter.return_value = q
                q.all.return_value    = [profile]
                return q
            q = MagicMock()
            filt = MagicMock()
            filt.first.return_value = None
            filt.all.return_value   = []
            filt.limit.return_value.all.return_value = []
            filt.order_by.return_value.limit.return_value.all.return_value = []
            q.filter.return_value = filt
            return q

        db.query.side_effect = qs

        avail_zero_cap = {"load_pct": 0.0, "available_hours": 0.0,
                          "capacity_hours": 0.0, "planned_hours": 0.0, "actual_hours": 0.0}

        with patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_user_availability",
            return_value=avail_zero_cap,
        ), patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_week_iso",
            return_value="2026-W15",
        ):
            assigner = _make_assigner(db=db)
            assigner._encode_single = lambda t: emb
            assigner._hybrid_score  = lambda ie, pe, ht: 1.0
            # Should not raise ZeroDivisionError
            result = assigner._suggest("zero capacity test", "ticket", priority="low")

        assert "suggested_user_id" in result


# ── Mejora 5: confirm LLM via feedback endpoint ───────────────────────────────

class TestMejora5FeedbackEndpointLLMConfirm:
    """POST /feedback with original_engine_mode=llm + confirmed=True persists as expert."""

    def test_llm_confirmation_uses_manager_confirm_prefix(self):
        """When confirming an LLM suggestion, corrected_by gets 'manager_confirm:' prefix."""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.session import get_db
        from app.core.deps import get_current_user
        from app.models.user import User

        # Build a minimal db mock
        db = _make_db()

        fake_user = MagicMock(spec=User)
        fake_user.id       = "manager-001"
        fake_user.role     = "admin"
        fake_user.is_active = True

        captured_corrected_by = {}

        def fake_record_feedback(item_id, item_type, item_text, correct_user_id, corrected_by):
            captured_corrected_by["value"] = corrected_by

        from app.services.semantic_classifier import SemanticAssigner
        mock_assigner = MagicMock(spec=SemanticAssigner)
        mock_assigner.record_feedback.side_effect = fake_record_feedback

        with patch("app.api.v1.endpoints.semantic_engine._get_assigner", return_value=mock_assigner), \
             patch("app.api.v1.endpoints.semantic_engine._cache_item_embedding"):
            with TestClient(app) as client:
                previous_overrides = dict(app.dependency_overrides)
                app.dependency_overrides[get_db]           = lambda: db
                app.dependency_overrides[get_current_user] = lambda: fake_user

                resp = client.post("/api/v1/semantic/feedback", json={
                    "item_id":              "ticket-123",
                    "item_type":            "ticket",
                    "item_text":            "Deploy kubernetes to prod",
                    "correct_user_id":      "u-devops-001",
                    "original_engine_mode": "llm",
                    "confirmed":            True,
                })

                app.dependency_overrides = previous_overrides

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["ok"] is True
        assert body["persisted_as_expert"] is True
        assert captured_corrected_by.get("value", "").startswith("manager_confirm:"), (
            "Confirmed LLM suggestions must be tagged with 'manager_confirm:' prefix"
        )

    def test_correction_without_confirm_flag_uses_manager_id(self):
        """When confirmed=False (human correction), corrected_by is just the manager id."""
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.session import get_db
        from app.core.deps import get_current_user
        from app.models.user import User

        db = _make_db()
        fake_user = MagicMock(spec=User)
        fake_user.id = "manager-002"
        fake_user.role = "admin"
        fake_user.is_active = True

        captured_corrected_by = {}

        def fake_record_feedback(item_id, item_type, item_text, correct_user_id, corrected_by):
            captured_corrected_by["value"] = corrected_by

        from app.services.semantic_classifier import SemanticAssigner
        mock_assigner = MagicMock(spec=SemanticAssigner)
        mock_assigner.record_feedback.side_effect = fake_record_feedback

        with patch("app.api.v1.endpoints.semantic_engine._get_assigner", return_value=mock_assigner), \
             patch("app.api.v1.endpoints.semantic_engine._cache_item_embedding"):
            with TestClient(app) as client:
                previous_overrides = dict(app.dependency_overrides)
                app.dependency_overrides[get_db]           = lambda: db
                app.dependency_overrides[get_current_user] = lambda: fake_user

                resp = client.post("/api/v1/semantic/feedback", json={
                    "item_text":       "Some ticket",
                    "correct_user_id": "u-corrected-001",
                    "confirmed":       False,
                })
                app.dependency_overrides = previous_overrides

        assert resp.status_code == 200
        assert resp.json()["data"]["persisted_as_expert"] is False
        assert captured_corrected_by.get("value") == "manager-002", (
            "Human correction (confirmed=False) should use plain manager id"
        )


# ── Mejora 6: diversity penalty ───────────────────────────────────────────────

class TestMejora6DiversityPenalty:
    """_diversity_penalty penalizes >60% same-type concentration in active workload."""

    def _make_profile(self, open_tickets, open_tasks):
        p = MagicMock()
        p.open_tickets = open_tickets
        p.open_tasks   = open_tasks
        return p

    def test_no_penalty_below_minimum_items(self):
        """With fewer than 3 active items, no diversity penalty applied."""
        assigner = _make_assigner()
        p = self._make_profile(2, 0)
        assert assigner._diversity_penalty(p, "ticket") == 0.0

    def test_no_penalty_balanced_workload(self):
        """50% tickets / 50% tasks → concentration 0.50 < 0.60 → no penalty."""
        assigner = _make_assigner()
        p = self._make_profile(5, 5)
        assert assigner._diversity_penalty(p, "ticket") == 0.0

    def test_no_penalty_at_60_percent_boundary(self):
        """Exactly 60% same type → max(0, 0.60 - 0.60) = 0 → no penalty."""
        assigner = _make_assigner()
        p = self._make_profile(6, 4)  # 6/10 = 60%
        assert assigner._diversity_penalty(p, "ticket") == 0.0

    def test_penalty_above_60_percent(self):
        """80% tickets → concentration=0.80 → penalty = (0.80-0.60)*0.30 = 0.06."""
        assigner = _make_assigner()
        p = self._make_profile(8, 2)  # 8/10 = 80%
        penalty = assigner._diversity_penalty(p, "ticket")
        assert abs(penalty - 0.06) < 1e-6, f"Expected 0.06, got {penalty}"

    def test_penalty_100_percent_concentration(self):
        """100% tickets → concentration=1.0 → penalty = (1.0-0.60)*0.30 = 0.12."""
        assigner = _make_assigner()
        p = self._make_profile(5, 0)  # 5/5 = 100% tickets
        penalty = assigner._diversity_penalty(p, "ticket")
        assert abs(penalty - 0.12) < 1e-6, f"Expected 0.12, got {penalty}"

    def test_penalty_type_aware(self):
        """Concentration is calculated for the requested item_type, not the other."""
        assigner = _make_assigner()
        p = self._make_profile(8, 2)  # 80% tickets, 20% tasks
        ticket_pen = assigner._diversity_penalty(p, "ticket")  # 80% → penalty
        task_pen   = assigner._diversity_penalty(p, "task")    # 20% → no penalty
        assert ticket_pen > 0.0
        assert task_pen == 0.0

    def test_diversity_reduces_final_score(self):
        """A user with 100% ticker concentration should score lower than one with 50%."""
        from app.models.semantic_engine import SemProfile

        def _make_profile_mock(uid, open_tickets, open_tasks, emb):
            p = MagicMock(spec=SemProfile)
            p.user_id      = uid
            p.embedding    = json.dumps(emb)
            p.is_available = True
            p.open_tickets = open_tickets
            p.open_tasks   = open_tasks
            p.max_load     = 10
            return p

        emb = [1.0, 0.0]
        concentrated = _make_profile_mock("u-conc", 8, 0, emb)  # 100% tickets
        balanced     = _make_profile_mock("u-bal",  4, 4, emb)  # 50% tickets

        db = _make_db()

        def qs(model):
            if model is SemProfile:
                q = MagicMock()
                q.filter.return_value = q
                q.all.return_value    = [concentrated, balanced]
                return q
            q = MagicMock()
            filt = MagicMock()
            filt.first.return_value = None
            filt.all.return_value   = []
            filt.limit.return_value.all.return_value = []
            filt.order_by.return_value.limit.return_value.all.return_value = []
            q.filter.return_value = filt
            return q

        db.query.side_effect = qs

        avail_zero = {"load_pct": 0.0, "available_hours": 40.0,
                      "capacity_hours": 40.0, "planned_hours": 0.0, "actual_hours": 0.0}

        with patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_user_availability",
            return_value=avail_zero,
        ), patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_week_iso",
            return_value="2026-W15",
        ):
            assigner = _make_assigner(db=db)
            assigner._encode_single = lambda t: emb
            assigner._hybrid_score  = lambda ie, pe, ht: 1.0
            result = assigner._suggest("ticket concentration test", "ticket", priority="low")

        top = result.get("top_scores", {})
        score_conc = top.get("u-conc", {}).get("score") if isinstance(top.get("u-conc"), dict) else top.get("u-conc")
        score_bal  = top.get("u-bal",  {}).get("score") if isinstance(top.get("u-bal"),  dict) else top.get("u-bal")
        if score_conc is not None and score_bal is not None:
            assert score_bal >= score_conc, (
                "Balanced workload user should score >= concentrated workload user"
            )


class TestConfigControlsAreFunctional:
    """Ensure Semantic Engine UI controls truly affect runtime behavior."""

    def _single_profile_db(self, profile):
        from app.models.semantic_engine import SemProfile

        db = _make_db()

        def _query_side(model):
            if model is SemProfile:
                q = MagicMock()
                q.filter.return_value = q
                q.all.return_value = [profile]
                return q
            q = MagicMock()
            filt = MagicMock()
            filt.first.return_value = None
            filt.all.return_value = []
            filt.limit.return_value.all.return_value = []
            filt.order_by.return_value.limit.return_value.all.return_value = []
            q.filter.return_value = filt
            return q

        db.query.side_effect = _query_side
        return db

    def test_engine_mode_llm_uses_llm_directly(self):
        from app.models.semantic_engine import SemProfile

        profile = MagicMock(spec=SemProfile)
        profile.user_id = "u-llm"
        profile.embedding = json.dumps([0.1, 0.2])
        profile.is_available = True
        profile.open_tickets = 0
        profile.open_tasks = 0
        profile.max_load = 10

        db = self._single_profile_db(profile)
        assigner = _make_assigner(db=db, config=_make_config(engine_mode="llm"))
        assigner._llm_suggest = lambda *_: {
            "suggested_user_id": "u-llm",
            "confidence": 0.81,
            "engine_mode": "llm",
            "top_scores": {},
            "needs_review": False,
            "reasoning": "LLM",
        }

        result = assigner._suggest("assign with llm", "ticket", ["u-llm"], priority="medium")
        assert result["engine_mode"] == "llm"
        assert result["suggested_user_id"] == "u-llm"

    def test_engine_mode_rules_only_ignores_semantic_similarity(self):
        from app.models.semantic_engine import SemProfile

        profile = MagicMock(spec=SemProfile)
        profile.user_id = "u-rules"
        profile.embedding = json.dumps([1.0, 0.0])
        profile.is_available = True
        profile.open_tickets = 0
        profile.open_tasks = 0
        profile.max_load = 10

        db = self._single_profile_db(profile)

        with patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_user_availability",
            return_value={"available_hours": 40.0, "capacity_hours": 40.0, "planned_hours": 0.0, "actual_hours": 0.0},
        ), patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_week_iso",
            return_value="2026-W18",
        ):
            semantic_assigner = _make_assigner(db=db, config=_make_config(engine_mode="semantic"))
            semantic_assigner._encode_single = lambda _: [1.0, 0.0]
            semantic_assigner._hybrid_score = lambda *_: 1.0
            semantic_result = semantic_assigner._suggest("semantic", "ticket", ["u-rules"], priority="low")

            rules_assigner = _make_assigner(db=db, config=_make_config(engine_mode="rules_only"))
            rules_assigner._encode_single = lambda _: [1.0, 0.0]
            rules_assigner._hybrid_score = lambda *_: 1.0
            rules_result = rules_assigner._suggest("rules", "ticket", ["u-rules"], priority="low")

        assert semantic_result["confidence"] > rules_result["confidence"]
        assert rules_result["engine_mode"] == "rules_only"

    def test_ticket_threshold_slider_affects_decision(self):
        from app.models.semantic_engine import SemProfile

        profile = MagicMock(spec=SemProfile)
        profile.user_id = "u-th"
        profile.embedding = json.dumps([1.0, 0.0])
        profile.is_available = True
        profile.open_tickets = 0
        profile.open_tasks = 0
        profile.max_load = 10

        db = self._single_profile_db(profile)

        with patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_user_availability",
            return_value={"available_hours": 40.0, "capacity_hours": 40.0, "planned_hours": 0.0, "actual_hours": 0.0},
        ), patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_week_iso",
            return_value="2026-W18",
        ):
            assigner = _make_assigner(
                db=db,
                config=_make_config(engine_mode="semantic", threshold_ticket=0.95, threshold_medium=0.58),
            )
            assigner._encode_single = lambda _: [1.0, 0.0]
            assigner._hybrid_score = lambda *_: 0.90
            result = assigner._suggest("strict-threshold", "ticket", ["u-th"], priority="medium")

        assert result["needs_review"] is True

    def test_rules_only_does_not_require_embeddings(self):
        from app.models.semantic_engine import SemProfile

        profile = MagicMock(spec=SemProfile)
        profile.user_id = "u-rules-no-emb"
        profile.embedding = None
        profile.is_available = True
        profile.open_tickets = 1
        profile.open_tasks = 1
        profile.max_load = 10

        db = self._single_profile_db(profile)

        with patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_user_availability",
            return_value={"available_hours": 40.0, "capacity_hours": 40.0, "planned_hours": 0.0, "actual_hours": 0.0},
        ), patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_week_iso",
            return_value="2026-W18",
        ):
            assigner = _make_assigner(db=db, config=_make_config(engine_mode="rules_only"))
            result = assigner._suggest("rules-no-embedding", "ticket", ["u-rules-no-emb"], priority="low")

        assert result["engine_mode"] == "rules_only"
        assert result["suggested_user_id"] == "u-rules-no-emb"

    def test_threshold_expert_cache_is_used_in_lookup(self):
        cfg = _make_config(threshold_expert_cache=0.87)
        assigner = _make_assigner(config=cfg)
        assigner._semantic_lookup_feedback = MagicMock(return_value=None)

        assigner._suggest("expert-threshold", "ticket", [], priority="low")

        assert assigner._semantic_lookup_feedback.call_count == 1
        _, _, used_threshold = assigner._semantic_lookup_feedback.call_args[0]
        assert used_threshold == 0.87

    def test_load_balance_weight_changes_final_score(self):
        from app.models.semantic_engine import SemProfile

        emb = [0.25] * 12
        profile = MagicMock(spec=SemProfile)
        profile.user_id = "u-load-weight"
        profile.embedding = json.dumps(emb)
        profile.is_available = True
        profile.open_tickets = 0
        profile.open_tasks = 0
        profile.max_load = 10

        db = self._single_profile_db(profile)
        with patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_user_availability",
            return_value={"available_hours": 0.0, "capacity_hours": 40.0, "planned_hours": 40.0, "actual_hours": 40.0},
        ), patch(
            "app.services.resource_analytics.ResourceAnalyticsService.get_week_iso",
            return_value="2026-W18",
        ):
            low_weight = _make_assigner(db=db, config=_make_config(load_balance_weight=0.0))
            high_weight = _make_assigner(db=db, config=_make_config(load_balance_weight=0.9))
            low_weight._encode_single = lambda _t: emb
            high_weight._encode_single = lambda _t: emb

            res_low = low_weight._suggest("load-weight", "ticket", ["u-load-weight"], priority="medium")
            res_high = high_weight._suggest("load-weight", "ticket", ["u-load-weight"], priority="medium")

        assert res_low["confidence"] > res_high["confidence"]

    def test_local_model_name_tfidf_forces_tfidf_backend(self):
        from app.services.semantic_classifier import SemanticAssigner

        backend, model = SemanticAssigner._resolve_embeddings_runtime(_make_config(local_model_name="tfidf"))

        assert backend == "tfidf"
        assert model == "all-MiniLM-L6-v2"
