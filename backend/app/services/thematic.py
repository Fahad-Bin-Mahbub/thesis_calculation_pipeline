from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from .common import add_key, load_excel, load_json_file


PROMPT_MAP = {
    2: ("protonmail", "task1", "Q1_thinking"),
    3: ("protonmail", "task1", "Q2_confusion"),
    4: ("protonmail", "task1", "Q3_improve"),
    5: ("protonmail", "task2", "Q1_thinking"),
    6: ("protonmail", "task2", "Q2_confusion"),
    7: ("protonmail", "task2", "Q3_improve"),
    8: ("protonmail", "task3", "Q1_thinking"),
    9: ("protonmail", "task3", "Q2_confusion"),
    10: ("protonmail", "task3", "Q3_improve"),
    11: ("securemyemail", "task1", "Q1_thinking"),
    12: ("securemyemail", "task1", "Q2_confusion"),
    13: ("securemyemail", "task1", "Q3_improve"),
    14: ("securemyemail", "task2", "Q1_thinking"),
    15: ("securemyemail", "task2", "Q2_confusion"),
    16: ("securemyemail", "task2", "Q3_improve"),
    17: ("securemyemail", "task3", "Q1_thinking"),
    18: ("securemyemail", "task3", "Q2_confusion"),
    19: ("securemyemail", "task3", "Q3_improve"),
    20: ("overall", "interview", "Q1_easier_tool"),
    21: ("overall", "interview", "Q2_trust"),
    22: ("overall", "interview", "Q3_frustration"),
    23: ("overall", "interview", "Q4_barrier"),
    24: ("overall", "interview", "Q5_learning_curve"),
    25: ("overall", "interview", "Q6_improvement"),
    26: ("overall", "interview", "Q7_recommend"),
    27: ("overall", "interview", "Q8_contexts"),
    28: ("overall", "interview", "Q9_final_feedback"),
}

STOPWORDS: Set[str] = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "because",
    "but",
    "by",
    "for",
    "from",
    "had",
    "has",
    "have",
    "i",
    "if",
    "in",
    "is",
    "it",
    "its",
    "me",
    "my",
    "not",
    "of",
    "on",
    "or",
    "so",
    "that",
    "the",
    "their",
    "them",
    "there",
    "they",
    "this",
    "to",
    "too",
    "was",
    "were",
    "with",
    "would",
    "you",
    "your",
}

NULL_LIKE_VALUES: Set[str] = {"", "nan", "none", "null", "nat"}


def _clean_csv_cell(value: Any) -> str:
    text = str(value if value is not None else "").replace("\ufeff", "").strip()
    if text.lower() in NULL_LIKE_VALUES:
        return ""
    return text


def _normalize_column_name(value: Any) -> str:
    text = _clean_csv_cell(value).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


def _find_csv_column(columns: List[str], aliases: Set[str]) -> str | None:
    for column in columns:
        if _normalize_column_name(column) in aliases:
            return column
    return None


def _normalize_excerpt_id(value: Any) -> str:
    return _clean_csv_cell(value)


def _normalize_struct_text(value: Any) -> str:
    return _clean_csv_cell(value).lower()


def _normalize_excel_row(value: Any) -> str:
    raw = _clean_csv_cell(value)
    if not raw:
        return ""
    digits = re.findall(r"\d+", raw)
    if not digits:
        return ""
    return str(int(digits[-1]))


def _split_theme_ids(value: Any) -> List[str]:
    raw = _clean_csv_cell(value)
    if not raw:
        return []
    return [item.strip() for item in re.split(r"[|;,]+", raw) if item.strip()]


def _merge_theme_cells(existing: str, incoming: str) -> str:
    merged: List[str] = []
    for theme_id in _split_theme_ids(existing) + _split_theme_ids(incoming):
        if theme_id not in merged:
            merged.append(theme_id)
    return "|".join(merged)


def _build_theme_assignment_lookups(theme_assignments_path: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "by_excerpt": {},
        "by_struct": {},
        "has_theme_column": False,
        "has_matching_key": False,
        "read_error": None,
    }
    try:
        assignments = pd.read_csv(theme_assignments_path, dtype=str, keep_default_na=False)
    except Exception:
        result["read_error"] = "Theme assignments could not be read."
        return result

    columns = [str(column) for column in assignments.columns]
    theme_col = _find_csv_column(
        columns,
        {"theme_id", "theme", "themes", "theme_ids", "assigned_theme_id"},
    )
    excerpt_col = _find_csv_column(columns, {"excerpt_id", "excerpt", "id"})
    notes_col = _find_csv_column(columns, {"reviewer_notes", "review_notes", "notes", "comment", "comments"})
    tool_col = _find_csv_column(columns, {"tool"})
    task_col = _find_csv_column(columns, {"task"})
    prompt_col = _find_csv_column(columns, {"prompt_id", "prompt"})
    row_col = _find_csv_column(columns, {"excel_row", "row", "row_no", "row_number"})

    has_struct_key = all([tool_col, task_col, prompt_col, row_col])
    result["has_theme_column"] = bool(theme_col)
    result["has_matching_key"] = bool(excerpt_col or has_struct_key)
    if not theme_col or not result["has_matching_key"]:
        return result

    by_excerpt: Dict[str, Dict[str, str]] = {}
    by_struct: Dict[tuple[str, str, str, str], Dict[str, str]] = {}
    for _, row in assignments.iterrows():
        theme_cell = "|".join(_split_theme_ids(row.get(theme_col, "")))
        reviewer_notes = _clean_csv_cell(row.get(notes_col, "")) if notes_col else ""
        if not theme_cell and not reviewer_notes:
            continue

        if excerpt_col:
            excerpt_key = _normalize_excerpt_id(row.get(excerpt_col, ""))
            if excerpt_key:
                existing = by_excerpt.get(excerpt_key, {"theme_id": "", "reviewer_notes": ""})
                by_excerpt[excerpt_key] = {
                    "theme_id": _merge_theme_cells(existing["theme_id"], theme_cell),
                    "reviewer_notes": reviewer_notes or existing["reviewer_notes"],
                }

        if has_struct_key:
            struct_key = (
                _normalize_struct_text(row.get(tool_col, "")),
                _normalize_struct_text(row.get(task_col, "")),
                _normalize_struct_text(row.get(prompt_col, "")),
                _normalize_excel_row(row.get(row_col, "")),
            )
            if all(struct_key):
                existing = by_struct.get(struct_key, {"theme_id": "", "reviewer_notes": ""})
                by_struct[struct_key] = {
                    "theme_id": _merge_theme_cells(existing["theme_id"], theme_cell),
                    "reviewer_notes": reviewer_notes or existing["reviewer_notes"],
                }

    result["by_excerpt"] = by_excerpt
    result["by_struct"] = by_struct
    return result


def _apply_theme_assignments(
    excerpts: List[Dict[str, Any]],
    by_excerpt: Dict[str, Dict[str, str]],
    by_struct: Dict[tuple[str, str, str, str], Dict[str, str]],
) -> List[Dict[str, Any]]:
    merged_records: List[Dict[str, Any]] = []
    for excerpt in excerpts:
        row = excerpt.copy()
        assignment = by_excerpt.get(_normalize_excerpt_id(row.get("excerpt_id", "")))
        if not assignment:
            struct_key = (
                _normalize_struct_text(row.get("tool", "")),
                _normalize_struct_text(row.get("task", "")),
                _normalize_struct_text(row.get("prompt_id", "")),
                _normalize_excel_row(row.get("excel_row", "")),
            )
            if all(struct_key):
                assignment = by_struct.get(struct_key)
        row["theme_id"] = _clean_csv_cell(assignment.get("theme_id", "")) if assignment else ""
        row["reviewer_notes"] = _clean_csv_cell(assignment.get("reviewer_notes", "")) if assignment else ""
        merged_records.append(row)
    return merged_records


def _normalize_for_match(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _keyword_hit(text_normalized: str, token_set: Set[str], keyword: str) -> bool:
    k = _normalize_for_match(keyword)
    if not k:
        return False
    if " " in k:
        return k in text_normalized
    return k in token_set


def _candidate_tokens(text_normalized: str) -> List[str]:
    return [token for token in text_normalized.split() if len(token) >= 4 and token not in STOPWORDS]


def _candidate_key_from_excerpt(text_normalized: str) -> Optional[str]:
    tokens = _candidate_tokens(text_normalized)
    if not tokens:
        return None
    # Keep order of appearance for interpretability.
    ranked: List[str] = []
    for token in tokens:
        if token not in ranked:
            ranked.append(token)
    if len(ranked) >= 2:
        return f"{ranked[0]}_{ranked[1]}"
    return ranked[0]


def _candidate_label(candidate_key: str) -> str:
    return " ".join(part.capitalize() for part in candidate_key.split("_"))


def extract_excerpts(path: str) -> List[Dict[str, Any]]:
    df = load_excel(path, sheet_name="thematic")
    if "Participant Name " in df.columns:
        df = df.loc[df["Participant Name "].notna()].copy()

    records: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        participant_name = str(row.get("Participant Name ", "")).strip()
        excel_row = int(row["_excel_row"])
        for idx, column_name in enumerate(df.columns[2:29], start=2):
            value = row[column_name]
            text = "" if pd.isna(value) else str(value).strip()
            if not text:
                continue
            tool, task, prompt_id = PROMPT_MAP[idx]
            excerpt_id = f"{tool[:2].upper()}_{task.upper()}_{prompt_id}_R{excel_row:03d}"
            records.append(
                {
                    "excerpt_id": excerpt_id,
                    "excel_row": excel_row,
                    "participant_name": participant_name,
                    "tool": tool,
                    "task": task,
                    "prompt_id": prompt_id,
                    "source_column": column_name,
                    "text": text,
                    "theme_id": "",
                    "reviewer_notes": "",
                }
            )
    return records


def prepare_excerpt_records(
    usability_path: str,
    theme_assignments_path: str | None = None,
) -> List[Dict[str, Any]]:
    excerpts = extract_excerpts(usability_path)
    if not theme_assignments_path:
        return excerpts

    assignment_data = _build_theme_assignment_lookups(theme_assignments_path)
    if assignment_data["read_error"]:
        return excerpts
    if not assignment_data["has_theme_column"] or not assignment_data["has_matching_key"]:
        return excerpts
    return _apply_theme_assignments(excerpts, assignment_data["by_excerpt"], assignment_data["by_struct"])


def _derive_common_codes(
    excerpts: List[Dict[str, Any]],
    common_code_defs: List[Dict[str, Any]],
    codebook_by_id: Dict[str, Dict[str, Any]],
    keys: Dict[str, Any],
    registry: Dict[str, Dict[str, str]],
) -> Dict[str, Any]:
    source = "thematic_common_codes"
    code_stats: Dict[str, Dict[str, Any]] = {}
    suggestion_rows: List[Dict[str, Any]] = []
    unmatched_excerpt_rows: List[Dict[str, str]] = []

    for excerpt in excerpts:
        text_norm = _normalize_for_match(excerpt.get("text"))
        token_set = set(text_norm.split())
        matched_code_ids: List[str] = []
        matched_labels: List[str] = []

        for code in common_code_defs:
            code_id = str(code.get("code_id", "")).strip()
            if not code_id:
                continue
            keywords = code.get("keywords", [])
            keyword_hits = [kw for kw in keywords if _keyword_hit(text_norm, token_set, str(kw))]
            if not keyword_hits:
                continue

            matched_code_ids.append(code_id)
            matched_labels.append(str(code.get("label", code_id)))
            stats = code_stats.setdefault(
                code_id,
                {
                    "excerpt_ids": set(),
                    "participants": set(),
                    "keyword_hits": {},
                },
            )
            stats["excerpt_ids"].add(str(excerpt.get("excerpt_id", "")))
            stats["participants"].add(str(excerpt.get("participant_name", "")))
            for hit in keyword_hits:
                stats["keyword_hits"][hit] = stats["keyword_hits"].get(hit, 0) + 1

        if matched_code_ids:
            suggestion_rows.append(
                {
                    "excerpt_id": str(excerpt.get("excerpt_id", "")),
                    "participant_name": str(excerpt.get("participant_name", "")),
                    "tool": str(excerpt.get("tool", "")),
                    "task": str(excerpt.get("task", "")),
                    "suggested_code_ids": "|".join(matched_code_ids),
                    "suggested_code_labels": " | ".join(matched_labels),
                }
            )
        else:
            candidate_key = _candidate_key_from_excerpt(text_norm)
            if candidate_key:
                unmatched_excerpt_rows.append(
                    {
                        "excerpt_id": str(excerpt.get("excerpt_id", "")),
                        "participant_name": str(excerpt.get("participant_name", "")),
                        "tool": str(excerpt.get("tool", "")),
                        "task": str(excerpt.get("task", "")),
                        "candidate_key": candidate_key,
                    }
                )

    common_code_rows: List[Dict[str, Any]] = []
    for code in common_code_defs:
        code_id = str(code.get("code_id", "")).strip()
        label = str(code.get("label", code_id))
        suggested_theme_id = str(code.get("suggested_theme_id", "")).strip()
        suggested_theme_label = codebook_by_id.get(suggested_theme_id, {}).get("label", "")
        stats = code_stats.get(code_id, {"excerpt_ids": set(), "participants": set(), "keyword_hits": {}})

        top_keywords = sorted(
            stats["keyword_hits"].items(),
            key=lambda pair: (-pair[1], pair[0]),
        )[:5]

        excerpt_count = int(len(stats["excerpt_ids"]))
        participant_count = int(len(stats["participants"]))

        add_key(
            keys,
            registry,
            f"themes.common_codes.{code_id}.excerpts_n",
            excerpt_count,
            f"Number of excerpts matching common code {label}",
            source,
            "themes",
        )
        add_key(
            keys,
            registry,
            f"themes.common_codes.{code_id}.participants_n",
            participant_count,
            f"Number of participants represented by common code {label}",
            source,
            "themes",
        )

        common_code_rows.append(
            {
                "code_id": code_id,
                "label": label,
                "description": str(code.get("description", "")),
                "suggested_theme_id": suggested_theme_id,
                "suggested_theme_label": suggested_theme_label,
                "excerpts_n": excerpt_count,
                "participants_n": participant_count,
                "top_keyword_hits": " | ".join([f"{kw} ({n})" for kw, n in top_keywords]),
            }
        )

    common_code_rows.sort(key=lambda row: (-int(row["excerpts_n"]), str(row["code_id"])))

    candidate_stats: Dict[str, Dict[str, Any]] = {}
    for row in unmatched_excerpt_rows:
        candidate_key = row["candidate_key"]
        stats = candidate_stats.setdefault(
            candidate_key,
            {
                "excerpt_ids": set(),
                "participants": set(),
            },
        )
        stats["excerpt_ids"].add(row["excerpt_id"])
        stats["participants"].add(row["participant_name"])

    sorted_candidates = sorted(
        candidate_stats.items(),
        key=lambda pair: (-len(pair[1]["excerpt_ids"]), pair[0]),
    )
    candidate_lookup: Dict[str, Dict[str, str]] = {}
    candidate_new_code_rows: List[Dict[str, Any]] = []
    for idx, (candidate_key, stats) in enumerate(sorted_candidates, start=1):
        candidate_code_id = f"NC{idx:02d}_{candidate_key}"
        label = _candidate_label(candidate_key)
        candidate_lookup[candidate_key] = {"candidate_code_id": candidate_code_id, "candidate_code_label": label}
        candidate_new_code_rows.append(
            {
                "candidate_code_id": candidate_code_id,
                "candidate_code_label": label,
                "excerpt_n": int(len(stats["excerpt_ids"])),
                "participant_n": int(len(stats["participants"])),
            }
        )

    excerpt_candidate_rows: List[Dict[str, Any]] = []
    for row in unmatched_excerpt_rows:
        payload = candidate_lookup.get(row["candidate_key"])
        if not payload:
            continue
        excerpt_candidate_rows.append(
            {
                "excerpt_id": row["excerpt_id"],
                "participant_name": row["participant_name"],
                "tool": row["tool"],
                "task": row["task"],
                "candidate_code_id": payload["candidate_code_id"],
                "candidate_code_label": payload["candidate_code_label"],
            }
        )

    return {
        "common_codes": common_code_rows,
        "excerpt_code_suggestions": suggestion_rows,
        "candidate_new_codes": candidate_new_code_rows,
        "excerpt_candidate_code_suggestions": excerpt_candidate_rows,
    }


def analyze_thematic(
    usability_path: str,
    theme_assignments_path: str | None = None,
) -> Dict[str, Any]:
    warnings: List[str] = []
    keys: Dict[str, Any] = {}
    registry: Dict[str, Dict[str, str]] = {}
    tables: Dict[str, Any] = {}
    source = "theme_assignments_csv"

    excerpts = extract_excerpts(usability_path)
    tables["excerpt_preview"] = excerpts[:20]
    tables["excerpt_count"] = len(excerpts)
    tables["excerpt_records"] = excerpts

    codebook = load_json_file(Path(__file__).resolve().parent.parent / "config" / "theme_codebook.json")
    codebook_by_id = {item["theme_id"]: item for item in codebook}
    common_code_defs = load_json_file(Path(__file__).resolve().parent.parent / "config" / "thematic_common_codes.json")
    common_code_result = _derive_common_codes(excerpts, common_code_defs, codebook_by_id, keys, registry)

    tables["theme_codebook"] = codebook
    tables["common_codebook"] = common_code_defs
    tables["common_codes"] = common_code_result["common_codes"]
    tables["excerpt_code_suggestions"] = common_code_result["excerpt_code_suggestions"]
    tables["candidate_new_codes"] = common_code_result["candidate_new_codes"]
    tables["excerpt_candidate_code_suggestions"] = common_code_result["excerpt_candidate_code_suggestions"]
    tables["paper_thematic_process"] = {
        "steps": [
            {"id": "extract", "label": "Extract response excerpts", "count": len(excerpts)},
            {"id": "assign", "label": "Assign one or more themes", "count": 0},
            {"id": "review", "label": "Add reviewer notes", "count": 0},
            {"id": "aggregate", "label": "Recompute theme counts", "count": 0},
        ],
        "common_codes_n": len(common_code_result["common_codes"]),
        "candidate_new_codes_n": len(common_code_result["candidate_new_codes"]),
        "theme_counts": [],
    }

    if not theme_assignments_path:
        warnings.append("Theme counts were not computed because no theme_assignments.csv file was provided.")
        return {
            "keys": keys,
            "registry": registry,
            "warnings": warnings,
            "tables": tables,
            "metadata": {
                "excerpt_count": len(excerpts),
            },
        }

    assignment_data = _build_theme_assignment_lookups(theme_assignments_path)
    if assignment_data["read_error"]:
        warnings.append(assignment_data["read_error"])
        return {
            "keys": keys,
            "registry": registry,
            "warnings": warnings,
            "tables": tables,
            "metadata": {
                "excerpt_count": len(excerpts),
            },
        }
    if not assignment_data["has_theme_column"]:
        warnings.append("Thematic counts skipped: missing a theme_id column in theme assignments.")
        return {
            "keys": keys,
            "registry": registry,
            "warnings": warnings,
            "tables": tables,
            "metadata": {
                "excerpt_count": len(excerpts),
            },
        }
    if not assignment_data["has_matching_key"]:
        warnings.append(
            "Thematic counts skipped: missing assignment key columns. Provide excerpt_id or all of tool, task, prompt_id, excel_row."
        )
        return {
            "keys": keys,
            "registry": registry,
            "warnings": warnings,
            "tables": tables,
            "metadata": {
                "excerpt_count": len(excerpts),
            },
        }

    merged_records = _apply_theme_assignments(excerpts, assignment_data["by_excerpt"], assignment_data["by_struct"])
    tables["excerpt_records"] = merged_records

    exploded_rows: List[Dict[str, Any]] = []
    assigned_excerpt_ids: Set[str] = set()
    review_notes_count = 0
    for row in merged_records:
        theme_ids = _split_theme_ids(row.get("theme_id", ""))
        if theme_ids:
            assigned_excerpt_ids.add(str(row.get("excerpt_id", "")))
        if _clean_csv_cell(row.get("reviewer_notes", "")):
            review_notes_count += 1
        for theme_id in theme_ids:
            exploded_rows.append(
                {
                    "theme_id": theme_id,
                    "participant_name": row["participant_name"],
                    "excerpt_id": row["excerpt_id"],
                }
            )

    if not exploded_rows:
        warnings.append("No valid theme assignments were found.")
        return {
            "keys": keys,
            "registry": registry,
            "warnings": warnings,
            "tables": tables,
            "metadata": {
                "excerpt_count": len(excerpts),
            },
        }

    exploded = pd.DataFrame(exploded_rows)

    for theme_id, group in exploded.groupby("theme_id"):
        item = codebook_by_id.get(theme_id)
        if not item:
            warnings.append(f"Unknown theme_id in theme assignments: {theme_id}")
            continue
        add_key(
            keys,
            registry,
            f"themes.{theme_id}.excerpts_n",
            int(group["excerpt_id"].nunique()),
            f"Number of coded excerpts assigned to {item['label']}",
            source,
            "themes",
        )
        add_key(
            keys,
            registry,
            f"themes.{theme_id}.participants_n",
            int(group["participant_name"].nunique()),
            f"Number of unique participants represented in {item['label']}",
            source,
            "themes",
        )

    tables["theme_counts"] = (
        exploded.groupby("theme_id")
        .agg(excerpts_n=("excerpt_id", "nunique"), participants_n=("participant_name", "nunique"))
        .reset_index()
        .to_dict(orient="records")
    )
    tables["paper_thematic_process"] = {
        "steps": [
            {"id": "extract", "label": "Extract response excerpts", "count": len(excerpts)},
            {"id": "assign", "label": "Assign one or more themes", "count": len(assigned_excerpt_ids)},
            {
                "id": "review",
                "label": "Add reviewer notes",
                "count": review_notes_count,
            },
            {"id": "aggregate", "label": "Recompute theme counts", "count": int(exploded["theme_id"].shape[0])},
        ],
        "common_codes_n": len(common_code_result["common_codes"]),
        "candidate_new_codes_n": len(common_code_result["candidate_new_codes"]),
        "theme_counts": tables["theme_counts"],
    }

    return {
        "keys": keys,
        "registry": registry,
        "warnings": warnings,
        "tables": tables,
        "metadata": {
            "excerpt_count": len(excerpts),
            "assigned_excerpt_count": int(exploded["excerpt_id"].nunique()),
        },
    }
