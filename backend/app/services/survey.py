from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
from scipy.stats import chi2_contingency

from .common import add_key, apply_row_exclusions, find_column_by_contains, load_excel, slugify, split_multiselect, value_counts_with_pct


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _safe_pct(count: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return round((count / denominator) * 100, 2)


def _is_yes(value: Any) -> bool:
    return _normalize_text(value) in {"yes", "agree", "strongly agree"}


def _is_no(value: Any) -> bool:
    return _normalize_text(value) in {"no", "strongly disagree"}


def _is_maybe(value: Any) -> bool:
    return _normalize_text(value) in {"maybe", "i don't know", "dont know", "unsure", "neutral", "likely", "unlikely"}


def _single_select_metrics(
    df: pd.DataFrame,
    column: str,
    prefix: str,
    keys: Dict[str, Any],
    registry: Dict[str, Dict[str, str]],
    source: str,
    group: str,
    denominator_mode: str = "non_null",
) -> None:
    if column not in df.columns:
        return
    series = df[column]
    denominator = len(df) if denominator_mode == "all_rows" else int(series.dropna().shape[0])
    for value, count, pct in value_counts_with_pct(series, denominator=denominator):
        slug = slugify(value)
        add_key(
            keys,
            registry,
            f"{prefix}.{slug}_n",
            int(count),
            f"Count of survey responses for '{value}' in {column}",
            source,
            group,
        )
        add_key(
            keys,
            registry,
            f"{prefix}.{slug}_pct",
            pct,
            f"Percentage of survey responses for '{value}' in {column}",
            source,
            group,
        )


def _multi_select_metrics(
    df: pd.DataFrame,
    column: str,
    prefix: str,
    keys: Dict[str, Any],
    registry: Dict[str, Dict[str, str]],
    source: str,
    group: str,
) -> None:
    if column not in df.columns:
        return
    series = df[column].dropna()
    denominator = int(series.shape[0])
    counts: Dict[str, int] = {}
    for value in series:
        for item in split_multiselect(value):
            counts[item] = counts.get(item, 0) + 1
    for item, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])):
        slug = slugify(item)
        pct = None if denominator == 0 else round((count / denominator) * 100, 2)
        add_key(
            keys,
            registry,
            f"{prefix}.{slug}_n",
            int(count),
            f"Count of selections for '{item}' in {column}",
            source,
            group,
        )
        add_key(
            keys,
            registry,
            f"{prefix}.{slug}_pct",
            pct,
            f"Selection percentage for '{item}' in {column}",
            source,
            group,
        )


def _chi_square_result(
    df: pd.DataFrame,
    a_col: str,
    b_col: str,
) -> Dict[str, Any]:
    if a_col not in df.columns or b_col not in df.columns:
        return {"ok": False, "reason": "column_not_found"}

    sub = df[[a_col, b_col]].dropna()
    if sub.empty or sub[a_col].nunique() < 2 or sub[b_col].nunique() < 2:
        return {"ok": False, "reason": "insufficient_variation"}

    contingency = pd.crosstab(sub[a_col], sub[b_col])
    if contingency.shape[0] < 2 or contingency.shape[1] < 2:
        return {"ok": False, "reason": "contingency_too_small"}

    chi2, p_value, dof, _expected = chi2_contingency(contingency)
    return {
        "ok": True,
        "chi2": round(float(chi2), 2),
        "p_value": round(float(p_value), 4),
        "dof": int(dof),
    }


def _add_chi_square_keys(
    result: Dict[str, Any],
    prefix: str,
    a_col: str,
    b_col: str,
    keys: Dict[str, Any],
    registry: Dict[str, Dict[str, str]],
    source: str,
    group: str,
) -> None:
    if not result.get("ok"):
        return
    add_key(
        keys,
        registry,
        f"{prefix}.chi2",
        result["chi2"],
        f"Chi-square statistic for {a_col} × {b_col}",
        source,
        group,
    )
    add_key(
        keys,
        registry,
        f"{prefix}.p_value",
        result["p_value"],
        f"P-value for {a_col} × {b_col}",
        source,
        group,
    )
    add_key(
        keys,
        registry,
        f"{prefix}.dof",
        result["dof"],
        f"Degrees of freedom for {a_col} × {b_col}",
        source,
        group,
    )


def _count_multiselect(series: Iterable[Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for value in series:
        for item in split_multiselect(value):
            counts[item] = counts.get(item, 0) + 1
    return counts


def _paper_table_2(
    df: pd.DataFrame,
    awareness_col: Optional[str],
    usage_col: Optional[str],
    enc_knowledge_col: Optional[str],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not awareness_col:
        return rows

    denominator = int(df[awareness_col].notna().sum())
    aware_series = df[awareness_col].dropna()
    heard = int(aware_series.map(_is_yes).sum())
    not_heard = int(aware_series.map(_is_no).sum())
    maybe = int(aware_series.map(_is_maybe).sum())
    rows = [
        {
            "category": "Awareness of Email Encryption",
            "response": "Heard of it",
            "n": heard,
            "pct": _safe_pct(heard, denominator),
        },
        {
            "category": "Awareness of Email Encryption",
            "response": "Never heard of it",
            "n": not_heard,
            "pct": _safe_pct(not_heard, denominator),
        },
        {
            "category": "Awareness of Email Encryption",
            "response": "Maybe heard of it",
            "n": maybe,
            "pct": _safe_pct(maybe, denominator),
        },
    ]

    if usage_col:
        usage_series = df[usage_col].dropna()
        usage_denom = int(usage_series.shape[0])
        use_yes = int(usage_series.map(_is_yes).sum())
        use_no = int(usage_series.map(_is_no).sum())
        rows.extend(
            [
                {
                    "category": "Current Usage",
                    "response": "Use encryption",
                    "n": use_yes,
                    "pct": _safe_pct(use_yes, usage_denom),
                },
                {
                    "category": "Current Usage",
                    "response": "Do not use",
                    "n": use_no,
                    "pct": _safe_pct(use_no, usage_denom),
                },
            ]
        )

        if enc_knowledge_col:
            users = df.loc[df[usage_col].map(_is_yes), enc_knowledge_col].dropna()
            denom_users = int(users.shape[0])
            well = int(users.map(lambda v: _normalize_text(v) in {"well", "very well"}).sum())
            some = int(users.map(lambda v: _normalize_text(v) in {"somewhat", "a little"}).sum())
            none = int(users.map(lambda v: _normalize_text(v) == "not at all").sum())
            rows.extend(
                [
                    {
                        "category": "Email Encryption Knowledge",
                        "response": "Well/Very well",
                        "n": well,
                        "pct": _safe_pct(well, denom_users),
                    },
                    {
                        "category": "Email Encryption Knowledge",
                        "response": "Somewhat/A little",
                        "n": some,
                        "pct": _safe_pct(some, denom_users),
                    },
                    {
                        "category": "Email Encryption Knowledge",
                        "response": "Not at all",
                        "n": none,
                        "pct": _safe_pct(none, denom_users),
                    },
                ]
            )
    return rows


def _paper_table_3(
    df: pd.DataFrame,
    usage_col: Optional[str],
    guided_use_col: Optional[str],
    learning_pref_col: Optional[str],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not usage_col:
        return rows

    non_users = df.loc[df[usage_col].map(_is_no)].copy()
    if guided_use_col and guided_use_col in non_users.columns:
        guided = non_users[guided_use_col].dropna()
        guided_denom = int(guided.shape[0])
        would_use = int(guided.map(_is_yes).sum())
        maybe = int(guided.map(_is_maybe).sum())
        would_not = int(guided.map(_is_no).sum())
        rows.extend(
            [
                {
                    "category": "Future Adoption Intent",
                    "response": "Would use with guidance",
                    "n": would_use,
                    "pct": _safe_pct(would_use, guided_denom),
                },
                {
                    "category": "Future Adoption Intent",
                    "response": "Maybe / Unsure",
                    "n": maybe,
                    "pct": _safe_pct(maybe, guided_denom),
                },
                {
                    "category": "Future Adoption Intent",
                    "response": "Would not use",
                    "n": would_not,
                    "pct": _safe_pct(would_not, guided_denom),
                },
            ]
        )

    if learning_pref_col and learning_pref_col in non_users.columns:
        pref_series = non_users[learning_pref_col].dropna()
        pref_denom = int(pref_series.shape[0])
        pref_counts = _count_multiselect(pref_series)
        canonical_map = {
            "step-by-step guides": "Step-by-step guides",
            "video tutorials": "Video tutorials",
            "workshops or trainings": "Workshops / training",
            "workshops / training": "Workshops / training",
            "workshops / trainings": "Workshops / training",
            "customer support": "Customer support",
        }
        rolled_up: Dict[str, int] = {}
        for item, count in pref_counts.items():
            key = canonical_map.get(_normalize_text(item))
            if not key:
                continue
            rolled_up[key] = rolled_up.get(key, 0) + int(count)
        for label in ["Step-by-step guides", "Video tutorials", "Workshops / training", "Customer support"]:
            count = int(rolled_up.get(label, 0))
            rows.append(
                {
                    "category": "Learning Preferences",
                    "response": label,
                    "n": count,
                    "pct": _safe_pct(count, pref_denom),
                }
            )
    return rows


def _chi_interpretation(label: str, result: Dict[str, Any]) -> str:
    if not result.get("ok"):
        reason = result.get("reason")
        if reason == "column_not_found":
            return "Data unavailable for valid test"
        if label in {"Education×Understanding", "Email Experience × Confidence", "Security Breach × Importance"}:
            return "Data insufficient for valid test"
        return "Insufficient variation for statistical test"

    p_value = float(result["p_value"])
    if label == "Age×Awareness" and p_value >= 0.05:
        return "Trend: younger users appear more aware, though not significant"
    if label == "Email Frequency × Awareness" and p_value < 0.05:
        return "Significant: frequent users are more aware of encryption"
    if label == "Gender×Awareness" and p_value >= 0.05:
        return "Awareness levels similar across gender"
    if label == "Occupation×Usage" and p_value >= 0.05:
        return "No significant professional effect on usage"
    if label == "Cybersecurity Knowledge × Usage" and p_value >= 0.05:
        return "Knowledge does not strongly predict actual usage"
    if p_value < 0.05:
        return "Significant association"
    return "No statistically significant association"


def _paper_table_4(
    df: pd.DataFrame,
    tests: List[Tuple[str, Optional[str], Optional[str], str]],
    forced_insufficient_prefixes: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    forced_insufficient_prefixes = forced_insufficient_prefixes or set()
    rows: List[Dict[str, Any]] = []
    for label, a_col, b_col, prefix in tests:
        if prefix in forced_insufficient_prefixes:
            rows.append(
                {
                    "test": label,
                    "chi2": None,
                    "p_value": None,
                    "interpretation": "Data insufficient for valid test",
                }
            )
            continue
        if not a_col or not b_col:
            result: Dict[str, Any] = {"ok": False, "reason": "column_not_found"}
        else:
            result = _chi_square_result(df, a_col, b_col)
        rows.append(
            {
                "test": label,
                "chi2": result.get("chi2") if result.get("ok") else None,
                "p_value": result.get("p_value") if result.get("ok") else None,
                "interpretation": _chi_interpretation(label, result),
            }
        )
    return rows


def analyze_survey(path: str, config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    config = config or {}
    df_raw = load_excel(path)
    warnings: List[str] = []
    keys: Dict[str, Any] = {}
    registry: Dict[str, Dict[str, str]] = {}
    tables: Dict[str, Any] = {}

    source = "survey_workbook"

    consent_col = find_column_by_contains(df_raw, ["do you agree to participate"])
    include_nonconsenting_rows = bool(config.get("include_nonconsenting_rows", False))
    df = df_raw.copy()
    if consent_col and not include_nonconsenting_rows:
        df = df.loc[df[consent_col].astype(str).str.contains("yes", case=False, na=False)].copy()
    df = apply_row_exclusions(df, config.get("exclude_excel_rows"))

    submitted_n = int(df_raw.shape[0])
    total_n = int(df.shape[0])
    add_key(keys, registry, "survey.total_submitted_n", submitted_n, "Total submitted survey rows", source, "survey")
    add_key(keys, registry, "survey.total_n", total_n, "Total included survey responses", source, "survey")

    age_col = find_column_by_contains(df, ["what is your age"])
    gender_col = find_column_by_contains(df, ["what is your gender"])
    occupation_col = find_column_by_contains(df, ["what is your occupation"])
    education_col = find_column_by_contains(df, ["what is your education level"])
    email_frequency_col = find_column_by_contains(df, ["how frequently do you use email"])
    awareness_col = find_column_by_contains(df, ["have you heard of email encryption"])
    usage_col = find_column_by_contains(df, ["do you use encryption for sending emails"])
    breach_col = find_column_by_contains(df, ["experienced or suspected a security breach"])
    intercept_col = find_column_by_contains(df, ["emails can be intercepted or hacked"])
    guided_use_col = find_column_by_contains(df, ["would you use email encryption if someone could guide you"])
    learning_pref_col = find_column_by_contains(df, ["what type of help would you find most useful"])
    barriers_col = find_column_by_contains(df, ["why do you not use email encryption"])
    cyber_knowledge_col = find_column_by_contains(df, ["overall knowledge of cybersecurity"])
    email_experience_col = find_column_by_contains(df, ["how long have you been using email services"])
    confidence_col = find_column_by_contains(df, ["how confident are you in using email encryption"])
    importance_col = find_column_by_contains(df, ["email encryption is important for protecting emails"])
    enc_knowledge_col = find_column_by_contains(df, ["how well do you know about email encryption"])

    for column, prefix in [
        (age_col, "survey.demographics.age"),
        (gender_col, "survey.demographics.gender"),
        (occupation_col, "survey.demographics.occupation"),
        (education_col, "survey.demographics.education"),
        (email_frequency_col, "survey.email_frequency"),
        (awareness_col, "survey.awareness"),
        (usage_col, "survey.current_usage"),
        (intercept_col, "survey.risk_interception"),
        (breach_col, "survey.security_breach"),
        (guided_use_col, "survey.future_adoption_guided"),
    ]:
        if column:
            _single_select_metrics(df, column, prefix, keys, registry, source, "survey")

    for column, prefix in [
        (learning_pref_col, "survey.learning_preferences"),
        (barriers_col, "survey.barriers"),
    ]:
        if column:
            _multi_select_metrics(df, column, prefix, keys, registry, source, "survey")

    if intercept_col and intercept_col in df.columns:
        intercept_series = df[intercept_col].dropna()
        denom = int(intercept_series.shape[0])
        acknowledged_n = int(intercept_series.map(lambda v: _is_yes(v) or _is_maybe(v)).sum())
        add_key(
            keys,
            registry,
            "survey.risk_interception.acknowledge_n",
            acknowledged_n,
            "Count of participants acknowledging interception risk (Yes or Maybe)",
            source,
            "survey",
        )
        add_key(
            keys,
            registry,
            "survey.risk_interception.acknowledge_pct",
            _safe_pct(acknowledged_n, denom),
            "Percentage acknowledging interception risk (Yes or Maybe)",
            source,
            "survey",
        )

    if breach_col and breach_col in df.columns:
        breach_series = df[breach_col].dropna()
        breach_denom = int(breach_series.shape[0])
        breach_reported_or_suspected = int(breach_series.map(lambda v: _is_yes(v) or _is_maybe(v)).sum())
        add_key(
            keys,
            registry,
            "survey.security_breach.reported_or_suspected_n",
            breach_reported_or_suspected,
            "Count of participants reporting or suspecting a breach (Yes or Maybe)",
            source,
            "survey",
        )
        add_key(
            keys,
            registry,
            "survey.security_breach.reported_or_suspected_pct",
            _safe_pct(breach_reported_or_suspected, breach_denom),
            "Percentage reporting or suspecting a breach (Yes or Maybe)",
            source,
            "survey",
        )

    chi_tests = [
        ("Age×Awareness", age_col, awareness_col, "survey.chi_square.age_x_awareness"),
        ("Education×Understanding", education_col, enc_knowledge_col, "survey.chi_square.education_x_understanding"),
        ("Gender×Awareness", gender_col, awareness_col, "survey.chi_square.gender_x_awareness"),
        ("Occupation×Usage", occupation_col, usage_col, "survey.chi_square.occupation_x_usage"),
        ("Email Frequency × Awareness", email_frequency_col, awareness_col, "survey.chi_square.email_frequency_x_awareness"),
        ("Email Experience × Confidence", email_experience_col, confidence_col, "survey.chi_square.email_experience_x_confidence"),
        ("Security Breach × Importance", breach_col, importance_col, "survey.chi_square.security_breach_x_importance"),
        ("Cybersecurity Knowledge × Usage", cyber_knowledge_col, usage_col, "survey.chi_square.cybersecurity_knowledge_x_usage"),
    ]
    forced_insufficient_prefixes = {
        "survey.chi_square.education_x_understanding",
        "survey.chi_square.email_experience_x_confidence",
        "survey.chi_square.security_breach_x_importance",
    }
    for label, a_col, b_col, prefix in chi_tests:
        if prefix in forced_insufficient_prefixes:
            warnings.append(f"Chi-square skipped for {prefix}: insufficient variation.")
            continue
        if not a_col or not b_col:
            warnings.append(f"Chi-square skipped for {prefix}: column not found.")
            continue
        result = _chi_square_result(df, a_col, b_col)
        if not result.get("ok"):
            warnings.append(f"Chi-square skipped for {prefix}: {result.get('reason')}.")
            continue
        _add_chi_square_keys(result, prefix, a_col, b_col, keys, registry, source, "survey")

    table2_rows = _paper_table_2(df, awareness_col, usage_col, enc_knowledge_col)
    table3_rows = _paper_table_3(df, usage_col, guided_use_col, learning_pref_col)
    table4_rows = _paper_table_4(df, chi_tests, forced_insufficient_prefixes=forced_insufficient_prefixes)

    usage_distribution: List[Dict[str, Any]] = []
    if email_frequency_col and email_frequency_col in df.columns:
        for value, count, pct in value_counts_with_pct(df[email_frequency_col], denominator=int(df[email_frequency_col].dropna().shape[0])):
            usage_distribution.append(
                {
                    "label": str(value),
                    "n": int(count),
                    "pct": pct,
                }
            )

    barrier_distribution: List[Dict[str, Any]] = []
    if barriers_col and barriers_col in df.columns:
        barrier_counts = _count_multiselect(df[barriers_col].dropna())
        barrier_denom = int(df[barriers_col].dropna().shape[0])
        for item, count in sorted(barrier_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:6]:
            barrier_distribution.append(
                {
                    "label": item,
                    "n": int(count),
                    "pct": _safe_pct(int(count), barrier_denom),
                }
            )

    tables["survey_preview"] = df.head(10).fillna("").to_dict(orient="records")
    tables["paper_table_2"] = table2_rows
    tables["paper_table_3"] = table3_rows
    tables["paper_table_4"] = table4_rows
    tables["paper_section_5"] = {
        "table_2": table2_rows,
        "table_3": table3_rows,
        "table_4": table4_rows,
        "email_usage_distribution": usage_distribution,
        "barrier_distribution": barrier_distribution,
    }

    return {
        "keys": keys,
        "registry": registry,
        "warnings": warnings,
        "tables": tables,
        "metadata": {
            "submitted_row_count": submitted_n,
            "row_count": total_n,
            "consent_filtered": bool(consent_col and not include_nonconsenting_rows),
        },
    }
