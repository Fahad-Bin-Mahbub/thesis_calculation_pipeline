from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .common import add_key, apply_row_exclusions, load_excel


PM_NASA_BLOCKS = {
    "task1": (3, 6),
    "task2": (17, 20),
    "task3": (31, 34),
}
SME_NASA_BLOCKS = {
    "task1": (45, 48),
    "task2": (59, 62),
    "task3": (73, 76),
}

# tuples are (subtask_a_col, subtask_b_col, subtask_c_col, total_col)
PM_TIME_BLOCKS = {
    "task1": (13, 14, 15, 16),
    "task2": (27, 28, 29, 30),
    "task3": (41, 42, 43, 44),
}
SME_TIME_BLOCKS = {
    "task1": (55, 56, 57, 58),
    "task2": (69, 70, 71, 72),
    "task3": (83, 84, 85, 86),
}

TSR_TASK_ROWS: List[Tuple[str, str, str]] = [
    ("task1", "a", "Create a new account and complete the initial security setup"),
    ("task1", "b", "Navigate to encryption key area and inspect account keys"),
    ("task1", "c", "Find how to share key information with others"),
    ("task2", "a", "Compose and send an encrypted email"),
    ("task2", "b", "Attach a PDF file and send"),
    ("task2", "c", "Send to external recipient with extra security options"),
    ("task3", "a", "Identify encrypted messages and open one"),
    ("task3", "b", "Open and view a password-protected message"),
    ("task3", "c", "Reply while maintaining encryption"),
]


def _col(df: pd.DataFrame, idx: int) -> str:
    return df.columns[idx]


def _nasa_score(df: pd.DataFrame, start_idx: int, end_idx: int) -> float:
    cols = [_col(df, idx) for idx in range(start_idx, end_idx + 1)]
    block = df[cols].apply(pd.to_numeric, errors="coerce").copy()
    # Invert success item to align with NASA-TLX burden direction.
    block.iloc[:, 1] = 10 - block.iloc[:, 1]
    return float(block.stack().mean() * 10)


def _mean_time(df: pd.DataFrame, idx: int) -> float:
    return float(pd.to_numeric(df[_col(df, idx)], errors="coerce").mean())


def _normalize_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"pass", "passed"}:
        return "pass"
    if text in {"partial", "partially_passed", "partially passed"}:
        return "partial"
    if text in {"fail", "failed"}:
        return "failed"
    return text


def _status_weight(status: str) -> float:
    if status == "pass":
        return 1.0
    if status == "partial":
        return 0.5
    return 0.0


def _build_tool_metrics(
    df: pd.DataFrame,
    tool_slug: str,
    time_blocks: Dict[str, Tuple[int, int, int, int]],
    nasa_blocks: Dict[str, Tuple[int, int]],
    keys: Dict[str, Any],
    registry: Dict[str, Dict[str, str]],
    source: str,
) -> Dict[str, Any]:
    task_totals: List[pd.Series] = []
    subtask_time_rows: List[Dict[str, Any]] = []
    task_time_rows: List[Dict[str, Any]] = []
    task_nasa_rows: List[Dict[str, Any]] = []

    for task_name, (a_idx, b_idx, c_idx, total_idx) in time_blocks.items():
        for subtask, idx in zip(["a", "b", "c"], [a_idx, b_idx, c_idx]):
            value = _mean_time(df, idx)
            rounded = round(value, 2)
            subtask_time_rows.append(
                {
                    "tool": tool_slug,
                    "task": task_name,
                    "subtask": subtask,
                    "minutes": rounded,
                }
            )
            add_key(
                keys,
                registry,
                f"usability.{tool_slug}.{task_name}.subtask_{subtask}.time_mean_min",
                rounded,
                f"Mean completion time for {tool_slug} {task_name} subtask {subtask}",
                source,
                "usability",
            )

        total_series = pd.to_numeric(df[_col(df, total_idx)], errors="coerce")
        task_totals.append(total_series)
        task_mean = round(float(total_series.mean()), 2)
        task_time_rows.append(
            {
                "tool": tool_slug,
                "task": task_name,
                "minutes": task_mean,
            }
        )
        add_key(
            keys,
            registry,
            f"usability.{tool_slug}.{task_name}.time_mean_min",
            task_mean,
            f"Mean total completion time for {tool_slug} {task_name}",
            source,
            "usability",
        )

    total_time = float(pd.concat(task_totals, axis=1).sum(axis=1).mean())
    add_key(
        keys,
        registry,
        f"usability.{tool_slug}.time_mean_min",
        round(total_time, 2),
        f"Overall mean completion time for {tool_slug}",
        source,
        "usability",
    )

    nasa_scores: List[float] = []
    for task_name, (start_idx, end_idx) in nasa_blocks.items():
        score = _nasa_score(df, start_idx, end_idx)
        nasa_scores.append(score)
        task_nasa_rows.append(
            {
                "tool": tool_slug,
                "task": task_name,
                "nasa_tlx": round(score, 2),
            }
        )
        add_key(
            keys,
            registry,
            f"usability.{tool_slug}.{task_name}.nasa_tlx",
            round(score, 2),
            f"Task-level NASA-TLX score for {tool_slug} {task_name}",
            source,
            "usability",
        )
    nasa_mean = float(sum(nasa_scores) / len(nasa_scores))
    add_key(
        keys,
        registry,
        f"usability.{tool_slug}.nasa_tlx",
        round(nasa_mean, 2),
        f"Overall NASA-TLX score for {tool_slug}",
        source,
        "usability",
    )

    return {
        "tool": tool_slug,
        "time_mean_min": round(total_time, 2),
        "nasa_tlx": round(nasa_mean, 2),
        "task_time_rows": task_time_rows,
        "subtask_time_rows": subtask_time_rows,
        "task_nasa_rows": task_nasa_rows,
    }


def _time_plot_rows(
    df: pd.DataFrame,
    time_blocks: Dict[str, Tuple[int, int, int, int]],
    tool_slug: str,
) -> List[Dict[str, Any]]:
    participant_col = "Participant Name " if "Participant Name " in df.columns else None
    rows: List[Dict[str, Any]] = []
    for idx, row in df.iterrows():
        participant = str(row[participant_col]).strip() if participant_col else f"row_{idx + 1}"
        for task, (a_idx, b_idx, c_idx, _total_idx) in time_blocks.items():
            for subtask, col_idx in zip(["a", "b", "c"], [a_idx, b_idx, c_idx]):
                value = pd.to_numeric(row[_col(df, col_idx)], errors="coerce")
                if pd.isna(value):
                    continue
                rows.append(
                    {
                        "tool": tool_slug,
                        "participant": participant,
                        "task": task,
                        "subtask": subtask,
                        "subtask_id": f"{task}.{subtask}",
                        "minutes": round(float(value), 2),
                    }
                )
    return rows


def _tsr_from_task_outcomes(
    path: str,
    keys: Dict[str, Any],
    registry: Dict[str, Dict[str, str]],
    warnings: List[str],
    source: str,
) -> Optional[Dict[str, Any]]:
    df = pd.read_csv(path)
    required = {"participant_name", "tool", "task", "subtask", "status"}
    missing = required - set(df.columns)
    if missing:
        warnings.append(f"TSR skipped: task outcomes file is missing columns: {sorted(missing)}")
        return None

    df = df.copy()
    df["tool"] = df["tool"].astype(str).str.strip().str.lower()
    df["task"] = df["task"].astype(str).str.strip().str.lower()
    df["subtask"] = df["subtask"].astype(str).str.strip().str.lower()
    df["status"] = df["status"].map(_normalize_status)
    valid_statuses = {"pass", "partial", "failed"}
    invalid_rows = int((~df["status"].isin(valid_statuses)).sum())
    if invalid_rows:
        warnings.append(f"TSR ignored {invalid_rows} task outcome rows with blank/unknown status values.")
    df = df.loc[df["status"].isin(valid_statuses)].copy()
    if df.empty:
        warnings.append("TSR skipped: no valid pass/partial/failed status rows were provided.")
        return None

    overall_rows: List[Dict[str, Any]] = []
    subtask_rows: List[Dict[str, Any]] = []
    tsr_lookup: Dict[Tuple[str, str, str], float] = {}
    overall_lookup: Dict[str, float] = {}

    for tool in ["protonmail", "securemyemail"]:
        tool_df = df.loc[df["tool"] == tool].copy()
        if tool_df.empty:
            warnings.append(f"TSR skipped for {tool}: no task outcome rows found.")
            continue
        overall = (tool_df["status"].map(_status_weight).sum() / len(tool_df)) * 100
        overall_rounded = round(float(overall), 2)
        overall_lookup[tool] = overall_rounded
        overall_rows.append({"tool": tool, "tsr_overall": overall_rounded})
        add_key(
            keys,
            registry,
            f"usability.{tool}.tsr_overall",
            overall_rounded,
            f"Overall task success rate for {tool}",
            source,
            "usability",
        )
        for (task, subtask), group in tool_df.groupby(["task", "subtask"]):
            tsr = (group["status"].map(_status_weight).sum() / len(group)) * 100
            tsr_rounded = round(float(tsr), 2)
            tsr_lookup[(tool, task, subtask)] = tsr_rounded
            subtask_rows.append(
                {
                    "tool": tool,
                    "task": task,
                    "subtask": subtask,
                    "tsr": tsr_rounded,
                }
            )
            add_key(
                keys,
                registry,
                f"usability.{tool}.{task}.subtask_{subtask}.tsr",
                tsr_rounded,
                f"Task success rate for {tool} {task} subtask {subtask}",
                source,
                "usability",
            )

    table6_rows: List[Dict[str, Any]] = []
    for task, subtask, label in TSR_TASK_ROWS:
        table6_rows.append(
            {
                "task": task,
                "subtask": subtask,
                "label": label,
                "protonmail": tsr_lookup.get(("protonmail", task, subtask)),
                "securemyemail": tsr_lookup.get(("securemyemail", task, subtask)),
            }
        )

    return {
        "overall_rows": overall_rows,
        "subtask_rows": subtask_rows,
        "table6_rows": table6_rows,
        "overall_lookup": overall_lookup,
    }


def bootstrap_task_template(path: str) -> List[Dict[str, Any]]:
    df = load_excel(path, sheet_name="all data ")
    if "Participant Name " in df.columns:
        names = [str(value).strip() for value in df["Participant Name "].dropna().tolist() if str(value).strip()]
    else:
        names = [f"row_{row}" for row in df["_excel_row"].tolist()]

    rows: List[Dict[str, Any]] = []
    for name in names:
        for tool in ["protonmail", "securemyemail"]:
            for task in ["task1", "task2", "task3"]:
                for subtask in ["a", "b", "c"]:
                    rows.append(
                        {
                            "participant_name": name,
                            "tool": tool,
                            "task": task,
                            "subtask": subtask,
                            "status": "",
                        }
                    )
    return rows


def analyze_usability(
    path: str,
    config: Dict[str, Any] | None = None,
    task_outcomes_path: str | None = None,
) -> Dict[str, Any]:
    config = config or {}
    df = load_excel(path, sheet_name="all data ")
    warnings: List[str] = []
    keys: Dict[str, Any] = {}
    registry: Dict[str, Dict[str, str]] = {}
    tables: Dict[str, Any] = {}
    source = "usability_workbook"

    if "Participant Name " in df.columns:
        df = df.loc[df["Participant Name "].notna()].copy()
    df = apply_row_exclusions(df, config.get("exclude_excel_rows"))

    add_key(
        keys,
        registry,
        "usability.total_n",
        int(df.shape[0]),
        "Total included usability participants",
        source,
        "usability",
    )

    pm_metrics = _build_tool_metrics(df, "protonmail", PM_TIME_BLOCKS, PM_NASA_BLOCKS, keys, registry, source)
    sme_metrics = _build_tool_metrics(df, "securemyemail", SME_TIME_BLOCKS, SME_NASA_BLOCKS, keys, registry, source)

    tsr_result: Optional[Dict[str, Any]] = None
    if task_outcomes_path:
        tsr_result = _tsr_from_task_outcomes(task_outcomes_path, keys, registry, warnings, "task_outcomes_csv")
    else:
        warnings.append("Exact TSR values were not computed because no task_outcomes.csv file was provided.")

    table5_rows = [
        {
            "metric": "Time (min)",
            "protonmail": pm_metrics["time_mean_min"],
            "securemyemail": sme_metrics["time_mean_min"],
        },
        {
            "metric": "Task Success Rate (%)",
            "protonmail": tsr_result["overall_lookup"].get("protonmail") if tsr_result else None,
            "securemyemail": tsr_result["overall_lookup"].get("securemyemail") if tsr_result else None,
        },
        {
            "metric": "NASA-TLX",
            "protonmail": pm_metrics["nasa_tlx"],
            "securemyemail": sme_metrics["nasa_tlx"],
        },
    ]

    tables["usability_preview"] = df.head(10).fillna("").to_dict(orient="records")
    tables["paper_table_5"] = table5_rows
    tables["paper_table_6"] = tsr_result["table6_rows"] if tsr_result else []
    tables["usability_subtask_times"] = pm_metrics["subtask_time_rows"] + sme_metrics["subtask_time_rows"]
    tables["usability_task_times"] = pm_metrics["task_time_rows"] + sme_metrics["task_time_rows"]
    tables["usability_task_nasa"] = pm_metrics["task_nasa_rows"] + sme_metrics["task_nasa_rows"]
    tables["usability_time_plot"] = _time_plot_rows(df, PM_TIME_BLOCKS, "protonmail") + _time_plot_rows(df, SME_TIME_BLOCKS, "securemyemail")
    tables["paper_section_6"] = {
        "table_5": table5_rows,
        "table_6": tsr_result["table6_rows"] if tsr_result else [],
        "subtask_time_rows": pm_metrics["subtask_time_rows"] + sme_metrics["subtask_time_rows"],
        "task_nasa_rows": pm_metrics["task_nasa_rows"] + sme_metrics["task_nasa_rows"],
    }

    return {
        "keys": keys,
        "registry": registry,
        "warnings": warnings,
        "tables": tables,
        "metadata": {
            "row_count": int(df.shape[0]),
            "tsr_computed": bool(tsr_result),
        },
    }
