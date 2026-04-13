from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd


def normalize_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("_x000a_", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def slugify(value: Any) -> str:
    text = normalize_label(value)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "blank"


def split_multiselect(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, float) and math.isnan(value):
        return []
    text = str(value).strip()
    if not text:
        return []
    parts = [part.strip() for part in text.split(",")]
    return [part for part in parts if part]


def load_excel(path: str | Path, sheet_name: Optional[str] = None) -> pd.DataFrame:
    if sheet_name is None:
        df = pd.read_excel(path)
    else:
        df = pd.read_excel(path, sheet_name=sheet_name)
    df = df.copy()
    df["_excel_row"] = df.index + 2
    return df


def load_json_file(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())


def load_optional_json(raw_text: Optional[str]) -> Dict[str, Any]:
    if not raw_text:
        return {}
    return json.loads(raw_text)


def apply_row_exclusions(df: pd.DataFrame, excel_rows: Optional[Sequence[int]]) -> pd.DataFrame:
    if not excel_rows:
        return df.copy()
    return df.loc[~df["_excel_row"].isin(set(excel_rows))].copy()


def find_column_by_contains(df: pd.DataFrame, phrases: Sequence[str]) -> Optional[str]:
    normalized = {normalize_label(col): col for col in df.columns}
    for phrase in phrases:
        phrase_norm = normalize_label(phrase)
        for norm, original in normalized.items():
            if phrase_norm in norm:
                return original
    return None


def safe_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def round2(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric):
        return None
    return round(numeric, 2)


def add_key(
    keys: Dict[str, Any],
    registry: Dict[str, Dict[str, str]],
    key: str,
    value: Any,
    description: str,
    source: str,
    group: str,
) -> None:
    keys[key] = value
    registry[key] = {
        "description": description,
        "source": source,
        "group": group,
    }


def value_counts_with_pct(
    series: pd.Series,
    denominator: Optional[int] = None,
) -> List[Tuple[Any, int, Optional[float]]]:
    cleaned = series.dropna()
    counts = cleaned.value_counts(dropna=False)
    if denominator is None:
        denominator = int(cleaned.shape[0])
    rows: List[Tuple[Any, int, Optional[float]]] = []
    for value, count in counts.items():
        pct = None if denominator == 0 else round((count / denominator) * 100, 2)
        rows.append((value, int(count), pct))
    return rows


def to_records_table(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return list(rows)


def make_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): make_jsonable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [make_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [make_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    try:
        import numpy as np  # type: ignore

        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass
    return value
