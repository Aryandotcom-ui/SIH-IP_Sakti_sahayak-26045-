from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.patent_prep.deadlines import compute_deadlines  # noqa: E402
from ai.patent_prep.forms import draft_all  # noqa: E402
from ai.patent_prep.handoff import handoff_case as run_handoff  # noqa: E402
from ai.patent_prep.intake import CaseIntake  # noqa: E402
from ai.patent_prep.precheck import run_prechecks  # noqa: E402
from ai.patent_prep.tracker import CaseTracker  # noqa: E402

from ..config import settings  # noqa: E402

# Structured logging for the patent-prep path, matching the convention
# AIService.answer() uses: key=value pairs, greppable, and deliberately
# carrying no free text from the case itself. A case id, a status and a
# count are safe to log; an invention title or a formulation description
# is the applicant's unpublished IP and must never reach a log file,
# because a patent application's novelty is destroyed by disclosure and
# a log is a disclosure surface.
log = logging.getLogger(__name__)


class PatentPrepService:
    """Application-facing adapter around ai/patent_prep — same relationship
    to that module as AIService has to ai/ and UpdatesService has to
    ai/updates: converts HTTP input into ai/patent_prep calls and back,
    without owning any of the intake/precheck/drafting/deadline logic
    itself."""

    def __init__(self) -> None:
        self._tracker: CaseTracker | None = None

    @property
    def tracker(self) -> CaseTracker:
        if self._tracker is None:
            self._tracker = CaseTracker(settings.patent_cases_db_path)
        return self._tracker

    def create_case(self, intake_dict: dict[str, Any]) -> str:
        case = CaseIntake.from_dict(intake_dict)
        case_id = self.tracker.create_case(case)
        log.info("patent_case=created case_id=%s", case_id)
        return case_id

    def update_intake(self, case_id: str, intake_dict: dict[str, Any]) -> None:
        case = CaseIntake.from_dict(intake_dict)
        self.tracker.update_intake(case_id, case)
        log.info("patent_case=intake_updated case_id=%s", case_id)

    def get_case(self, case_id: str) -> dict[str, Any]:
        return self.tracker.get_case(case_id)

    def list_cases(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return self.tracker.list_cases(status=status, limit=limit)

    def events(self, case_id: str) -> list[dict[str, Any]]:
        return self.tracker.events(case_id)

    def precheck(self, case_id: str) -> dict[str, Any]:
        case = self.tracker.get_intake(case_id)
        report = run_prechecks(case, corpus_path=settings.corpus_manifest_path)
        result = report.to_dict()
        self.tracker.record_precheck(case_id, result)
        # The blocking-check outcome is the single most consequential
        # thing this service decides: a RED precheck is the difference
        # between "file this" and "do not file this yet".
        checks = result.get("checks") or []
        log.info(
            "patent_precheck=ran case_id=%s status=%s checks=%d blocking=%d",
            case_id,
            result.get("status"),
            len(checks),
            sum(1 for c in checks if (c or {}).get("blocking")),
        )
        return result

    def draft_forms(self, case_id: str) -> dict[str, Any]:
        case = self.tracker.get_intake(case_id)
        forms = draft_all(case)
        result = {form_id: draft.to_dict() for form_id, draft in forms.items()}
        self.tracker.record_forms(case_id, result)
        log.info(
            "patent_forms=drafted case_id=%s forms=%s",
            case_id, ",".join(sorted(result)) or "none",
        )
        return result

    def deadlines(self, case_id: str) -> list[dict[str, Any]]:
        case = self.tracker.get_intake(case_id)
        result = [d.to_dict() for d in compute_deadlines(case)]
        log.info("patent_deadlines=computed case_id=%s count=%d", case_id, len(result))
        return result

    def handoff(self, case_id: str, *, recipient: str, notes: str | None = None) -> dict[str, Any]:
        # `notes` and `recipient` are free text supplied by the caller and
        # are deliberately not logged — only that a handoff happened.
        result = run_handoff(
            self.tracker, case_id, recipient=recipient, notes=notes,
            corpus_path=settings.corpus_manifest_path,
        )
        log.info("patent_case=handoff case_id=%s", case_id)
        return result

    def update_status(self, case_id: str, status: str, *, detail: str | None = None) -> None:
        self.tracker.update_status(case_id, status, detail=detail)
        log.info("patent_case=status_changed case_id=%s status=%s", case_id, status)


patent_prep_service = PatentPrepService()
