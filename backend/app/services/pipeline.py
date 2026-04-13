from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .common import make_jsonable
from .survey import analyze_survey
from .thematic import analyze_thematic
from .usability import analyze_usability


def _merge(base: Dict[str, Any], part: Dict[str, Any]) -> None:
    for key in ["keys", "registry"]:
        base[key].update(part.get(key, {}))
    base["warnings"].extend(part.get("warnings", []))
    base["tables"].update(part.get("tables", {}))
    base["metadata"].update(part.get("metadata", {}))


def analyze_bundle(
    survey_path: str,
    usability_path: str,
    config: Optional[Dict[str, Any]] = None,
    task_outcomes_path: Optional[str] = None,
    theme_assignments_path: Optional[str] = None,
) -> Dict[str, Any]:
    config = config or {}
    response: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keys": {},
        "registry": {},
        "warnings": [],
        "tables": {},
        "metadata": {},
    }

    survey_part = analyze_survey(survey_path, config=config.get("survey", {}))
    usability_part = analyze_usability(
        usability_path,
        config=config.get("usability", {}),
        task_outcomes_path=task_outcomes_path,
    )
    thematic_part = analyze_thematic(
        usability_path,
        theme_assignments_path=theme_assignments_path,
    )

    for part in [survey_part, usability_part, thematic_part]:
        _merge(response, part)

    response["warnings"] = sorted(set(response["warnings"]))
    return make_jsonable(response)
