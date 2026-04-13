"use client";

import { startTransition, useDeferredValue, useEffect, useMemo, useState } from "react";
import { analyzeBundle, bootstrapThemeTemplate, loadThemeCodebook } from "../lib/api";
import type { AnalysisResponse, ThemeCodebookItem } from "../types";

const defaultConfig = JSON.stringify(
  {
    survey: { exclude_excel_rows: [] },
    usability: { exclude_excel_rows: [] }
  },
  null,
  2
);

type ViewMode = "paper" | "keys" | "thematic";
type Primitive = string | number | null | undefined;
type PaperRow = Record<string, Primitive>;

type ThematicRecord = {
  excerpt_id: string;
  excel_row?: number;
  participant_name: string;
  tool: string;
  task: string;
  prompt_id: string;
  source_column: string;
  text: string;
  theme_id: string;
  reviewer_notes: string;
  selectedThemes: string[];
  selectedCodeIds: string[];
};

type CodeDefinition = {
  code_id: string;
  label: string;
  description: string;
  mapped_theme_id: string;
  origin: "common" | "candidate" | "custom";
};

const DEFAULT_CODEBOOK: ThemeCodebookItem[] = [
  { theme_id: "TH01_interface_complexity", label: "Interface Complexity & Cognitive Load" },
  { theme_id: "TH02_authentication_setup", label: "Authentication & Setup Barriers" },
  { theme_id: "TH03_encryption_transparency", label: "Encryption Transparency & Understanding" },
  { theme_id: "TH04_trust_security", label: "Trust & Security Perception" },
  { theme_id: "TH05_learning_curve", label: "Learning Curve & Adoption Challenges" }
];

function toRows(value: unknown): PaperRow[] {
  if (!Array.isArray(value)) return [];
  return value.filter((row): row is PaperRow => !!row && typeof row === "object");
}

function asString(value: Primitive): string {
  if (value === null || value === undefined) return "—";
  return String(value);
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value.toFixed(2)}%`;
}

function formatMaybeNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(2);
}

function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function downloadCsv(filename: string, rows: string[][]) {
  const csv = rows
    .map((row) =>
      row
        .map((cell) => {
          const escaped = String(cell ?? "").replace(/"/g, "\"\"");
          return `"${escaped}"`;
        })
        .join(",")
    )
    .join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function normalizeThemeIds(raw: string): string[] {
  return raw
    .split(/[|;,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeCodeIds(raw: string): string[] {
  return raw
    .split(/[|;,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function uniqueStrings(values: string[]): string[] {
  const seen = new Set<string>();
  const output: string[] = [];
  for (const value of values) {
    if (!value || seen.has(value)) continue;
    seen.add(value);
    output.push(value);
  }
  return output;
}

function primitiveToText(value: Primitive): string {
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

function buildCodeDefinitions(commonRows: PaperRow[], candidateRows: PaperRow[]): CodeDefinition[] {
  const map: Record<string, CodeDefinition> = {};
  for (const row of commonRows) {
    const codeId = primitiveToText(row.code_id);
    if (!codeId) continue;
    map[codeId] = {
      code_id: codeId,
      label: primitiveToText(row.label) || codeId,
      description: primitiveToText(row.description),
      mapped_theme_id: primitiveToText(row.suggested_theme_id),
      origin: "common"
    };
  }
  for (const row of candidateRows) {
    const codeId = primitiveToText(row.candidate_code_id);
    if (!codeId) continue;
    if (!map[codeId]) {
      map[codeId] = {
        code_id: codeId,
        label: primitiveToText(row.candidate_code_label) || codeId,
        description: "Candidate code generated from unmatched excerpts.",
        mapped_theme_id: "",
        origin: "candidate"
      };
    }
  }
  return Object.values(map).sort((a, b) => a.code_id.localeCompare(b.code_id));
}

function customCodeIdFromLabel(label: string, existingIds: Set<string>): string {
  const base = label.toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 20) || "CODE";
  let candidate = `CU_${base}`;
  let suffix = 2;
  while (existingIds.has(candidate)) {
    candidate = `CU_${base}_${suffix}`;
    suffix += 1;
  }
  return candidate;
}

function recordFromUnknown(value: Record<string, unknown>): ThematicRecord {
  const themeRaw = typeof value.theme_id === "string" ? value.theme_id : "";
  const selectedThemes = normalizeThemeIds(themeRaw);
  return {
    excerpt_id: typeof value.excerpt_id === "string" ? value.excerpt_id : "",
    excel_row: asNumber(value.excel_row) ?? undefined,
    participant_name: typeof value.participant_name === "string" ? value.participant_name : "",
    tool: typeof value.tool === "string" ? value.tool : "",
    task: typeof value.task === "string" ? value.task : "",
    prompt_id: typeof value.prompt_id === "string" ? value.prompt_id : "",
    source_column: typeof value.source_column === "string" ? value.source_column : "",
    text: typeof value.text === "string" ? value.text : "",
    theme_id: selectedThemes.join("|"),
    reviewer_notes: typeof value.reviewer_notes === "string" ? value.reviewer_notes : "",
    selectedThemes,
    selectedCodeIds: []
  };
}

function PaperTable({
  title,
  rows,
  orderedKeys
}: {
  title: string;
  rows: PaperRow[];
  orderedKeys?: string[];
}) {
  const columns = useMemo(() => {
    if (orderedKeys && orderedKeys.length > 0) return orderedKeys;
    const first = rows[0];
    return first ? Object.keys(first) : [];
  }, [orderedKeys, rows]);

  if (rows.length === 0) {
    return (
      <div className="rounded-2xl border border-amber-300/40 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        {title}: No rows yet.
      </div>
    );
  }

  return (
    <section className="rounded-2xl border border-[#d8dde9] bg-white">
      <div className="border-b border-[#e6e9f2] px-4 py-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-[#1e2a45]">{title}</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-[#f3f6fd] text-left text-[#405175]">
            <tr>
              {columns.map((column) => (
                <th key={column} className="px-4 py-2 font-medium">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[#edf0f7] text-[#27344f]">
            {rows.map((row, index) => (
              <tr key={`${title}-${index}`}>
                {columns.map((column) => (
                  <td key={column} className="px-4 py-2 align-top">
                    {asString(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function HorizontalBars({ title, rows }: { title: string; rows: PaperRow[] }) {
  if (rows.length === 0) return null;
  const max = Math.max(...rows.map((row) => asNumber(row.n) ?? 0), 1);
  return (
    <section className="rounded-2xl border border-[#d8dde9] bg-white p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-[#1e2a45]">{title}</h3>
      <div className="mt-3 space-y-3">
        {rows.map((row, index) => {
          const label = asString(row.label);
          const count = asNumber(row.n) ?? 0;
          const pct = asNumber(row.pct);
          const width = `${Math.max((count / max) * 100, 3)}%`;
          return (
            <div key={`${label}-${index}`}>
              <div className="mb-1 flex items-center justify-between text-sm text-[#304166]">
                <span>{label}</span>
                <span>
                  {count} ({formatPct(pct)})
                </span>
              </div>
              <div className="h-2 rounded-full bg-[#edf2fb]">
                <div className="h-2 rounded-full bg-gradient-to-r from-[#1f6fba] to-[#47a4d9]" style={{ width }} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default function HomePage() {
  const [surveyFile, setSurveyFile] = useState<File | null>(null);
  const [usabilityFile, setUsabilityFile] = useState<File | null>(null);
  const [taskOutcomesFile, setTaskOutcomesFile] = useState<File | null>(null);
  const [themeAssignmentsFile, setThemeAssignmentsFile] = useState<File | null>(null);
  const [analysisConfig, setAnalysisConfig] = useState(defaultConfig);
  const [search, setSearch] = useState("");
  const [view, setView] = useState<ViewMode>("paper");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [thematicError, setThematicError] = useState<string | null>(null);
  const [thematicLoading, setThematicLoading] = useState(false);
  const [thematicRecords, setThematicRecords] = useState<ThematicRecord[]>([]);
  const [themeSearch, setThemeSearch] = useState("");
  const [themeToolFilter, setThemeToolFilter] = useState("all");
  const [themeTaskFilter, setThemeTaskFilter] = useState("all");
  const [visibleExcerpts, setVisibleExcerpts] = useState(36);
  const [codebook, setCodebook] = useState<ThemeCodebookItem[]>(DEFAULT_CODEBOOK);
  const [codeDefinitions, setCodeDefinitions] = useState<CodeDefinition[]>([]);
  const [newCodeLabel, setNewCodeLabel] = useState("");
  const [newCodeThemeId, setNewCodeThemeId] = useState("");
  const [newCodeDescription, setNewCodeDescription] = useState("");
  const deferredSearch = useDeferredValue(search);
  const deferredThemeSearch = useDeferredValue(themeSearch);

  useEffect(() => {
    let active = true;
    loadThemeCodebook()
      .then((items) => {
        if (!active || items.length === 0) return;
        setCodebook(items);
      })
      .catch(() => {
        // Fallback to defaults when API is unavailable.
      });
    return () => {
      active = false;
    };
  }, []);

  const filteredEntries = useMemo(() => {
    if (!result) return [];
    const entries = Object.entries(result.keys).sort(([a], [b]) => a.localeCompare(b));
    if (!deferredSearch.trim()) return entries;
    const term = deferredSearch.toLowerCase();
    return entries.filter(([key]) => key.toLowerCase().includes(term));
  }, [deferredSearch, result]);

  const paperTable2 = useMemo(() => toRows(result?.tables?.paper_table_2), [result]);
  const paperTable3 = useMemo(() => toRows(result?.tables?.paper_table_3), [result]);
  const paperTable4 = useMemo(() => toRows(result?.tables?.paper_table_4), [result]);
  const paperTable5 = useMemo(() => toRows(result?.tables?.paper_table_5), [result]);
  const paperTable6 = useMemo(() => toRows(result?.tables?.paper_table_6), [result]);
  const commonCodes = useMemo(() => toRows(result?.tables?.common_codes), [result]);
  const excerptCodeSuggestions = useMemo(() => toRows(result?.tables?.excerpt_code_suggestions), [result]);
  const candidateNewCodes = useMemo(() => toRows(result?.tables?.candidate_new_codes), [result]);
  const excerptCandidateCodeSuggestions = useMemo(() => toRows(result?.tables?.excerpt_candidate_code_suggestions), [result]);
  const usageBars = useMemo(() => toRows(result?.tables?.paper_section_5 && (result.tables.paper_section_5 as Record<string, unknown>).email_usage_distribution), [result]);
  const barrierBars = useMemo(() => toRows(result?.tables?.paper_section_5 && (result.tables.paper_section_5 as Record<string, unknown>).barrier_distribution), [result]);

  useEffect(() => {
    if (commonCodes.length === 0 && candidateNewCodes.length === 0) return;
    setCodeDefinitions(buildCodeDefinitions(commonCodes, candidateNewCodes));
  }, [candidateNewCodes, commonCodes]);

  const codeLabelById = useMemo(() => {
    const map: Record<string, string> = {};
    for (const code of codeDefinitions) {
      map[code.code_id] = code.label || code.code_id;
    }
    return map;
  }, [codeDefinitions]);

  const mappedThemeByCode = useMemo(() => {
    const map: Record<string, string> = {};
    for (const code of codeDefinitions) {
      if (!code.mapped_theme_id) continue;
      map[code.code_id] = code.mapped_theme_id;
    }
    return map;
  }, [codeDefinitions]);

  const suggestedCodeIdsByExcerpt = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const row of excerptCodeSuggestions) {
      const excerptId = primitiveToText(row.excerpt_id);
      if (!excerptId) continue;
      map[excerptId] = normalizeCodeIds(primitiveToText(row.suggested_code_ids));
    }
    return map;
  }, [excerptCodeSuggestions]);

  const candidateCodeIdByExcerpt = useMemo(() => {
    const map: Record<string, string> = {};
    for (const row of excerptCandidateCodeSuggestions) {
      const excerptId = primitiveToText(row.excerpt_id);
      const candidateId = primitiveToText(row.candidate_code_id);
      if (!excerptId || !candidateId) continue;
      map[excerptId] = candidateId;
    }
    return map;
  }, [excerptCandidateCodeSuggestions]);

  const suggestionMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const row of excerptCodeSuggestions) {
      const excerptId = primitiveToText(row.excerpt_id);
      if (!excerptId) continue;
      map[excerptId] = primitiveToText(row.suggested_code_labels);
    }
    return map;
  }, [excerptCodeSuggestions]);

  const candidateSuggestionMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const row of excerptCandidateCodeSuggestions) {
      const excerptId = primitiveToText(row.excerpt_id);
      if (!excerptId) continue;
      map[excerptId] = primitiveToText(row.candidate_code_label);
    }
    return map;
  }, [excerptCandidateCodeSuggestions]);

  const filteredThematicRecords = useMemo(() => {
    const searchTerm = deferredThemeSearch.trim().toLowerCase();
    return thematicRecords.filter((record) => {
      const matchesTool = themeToolFilter === "all" || record.tool === themeToolFilter;
      const matchesTask = themeTaskFilter === "all" || record.task === themeTaskFilter;
      const matchesSearch =
        searchTerm.length === 0 ||
        record.text.toLowerCase().includes(searchTerm) ||
        record.participant_name.toLowerCase().includes(searchTerm) ||
        record.excerpt_id.toLowerCase().includes(searchTerm);
      return matchesTool && matchesTask && matchesSearch;
    });
  }, [deferredThemeSearch, thematicRecords, themeTaskFilter, themeToolFilter]);

  const resolvedThemeInfoByExcerpt = useMemo(() => {
    const map: Record<
      string,
      {
        derivedThemes: string[];
        resolvedThemes: string[];
        unmappedCodeIds: string[];
      }
    > = {};
    for (const record of thematicRecords) {
      const derivedThemes = uniqueStrings(
        record.selectedCodeIds.map((codeId) => mappedThemeByCode[codeId]).filter((themeId): themeId is string => !!themeId)
      );
      const unmappedCodeIds = uniqueStrings(record.selectedCodeIds.filter((codeId) => !mappedThemeByCode[codeId]));
      const manualThemes = record.selectedThemes;
      map[record.excerpt_id] = {
        derivedThemes,
        resolvedThemes: uniqueStrings([...derivedThemes, ...manualThemes]),
        unmappedCodeIds
      };
    }
    return map;
  }, [mappedThemeByCode, thematicRecords]);

  const thematicThemeCounts = useMemo(() => {
    const counts: Record<string, { excerpts: number; participants: Set<string> }> = {};
    for (const record of thematicRecords) {
      const resolved = resolvedThemeInfoByExcerpt[record.excerpt_id]?.resolvedThemes ?? [];
      for (const themeId of resolved) {
        if (!counts[themeId]) {
          counts[themeId] = { excerpts: 0, participants: new Set<string>() };
        }
        counts[themeId].excerpts += 1;
        counts[themeId].participants.add(record.participant_name);
      }
    }
    return Object.entries(counts)
      .map(([themeId, data]) => ({
        theme_id: themeId,
        excerpts_n: data.excerpts,
        participants_n: data.participants.size,
        label: codebook.find((item) => item.theme_id === themeId)?.label ?? themeId
      }))
      .sort((a, b) => b.excerpts_n - a.excerpts_n);
  }, [codebook, resolvedThemeInfoByExcerpt, thematicRecords]);

  const codeUsageById = useMemo(() => {
    const map: Record<string, { excerpts: number; participants: Set<string> }> = {};
    for (const record of thematicRecords) {
      for (const codeId of uniqueStrings(record.selectedCodeIds)) {
        if (!map[codeId]) {
          map[codeId] = { excerpts: 0, participants: new Set<string>() };
        }
        map[codeId].excerpts += 1;
        map[codeId].participants.add(record.participant_name);
      }
    }
    return map;
  }, [thematicRecords]);

  const unmappedCodeUsageRows = useMemo(() => {
    return Object.entries(codeUsageById)
      .filter(([codeId]) => !mappedThemeByCode[codeId])
      .map(([codeId, payload]) => ({
        code_id: codeId,
        label: codeLabelById[codeId] ?? codeId,
        excerpts_n: payload.excerpts,
        participants_n: payload.participants.size
      }))
      .sort((a, b) => b.excerpts_n - a.excerpts_n);
  }, [codeLabelById, codeUsageById, mappedThemeByCode]);

  const thematicProcess = useMemo(() => {
    const codedExcerptCount = thematicRecords.filter((item) => item.selectedCodeIds.length > 0).length;
    const reviewedCount = thematicRecords.filter((item) => item.reviewer_notes.trim().length > 0).length;
    const mappedCodes = codeDefinitions.filter((code) => code.mapped_theme_id.trim().length > 0).length;
    const themeLinks = thematicRecords.reduce(
      (sum, item) => sum + (resolvedThemeInfoByExcerpt[item.excerpt_id]?.resolvedThemes.length ?? 0),
      0
    );
    return [
      {
        id: "extract",
        label: "Extract excerpts",
        detail: "Load all interview/usability excerpts from the sheet.",
        count: thematicRecords.length
      },
      {
        id: "code",
        label: "Review and assign codes",
        detail: "Accept suggestions or manually tag excerpts with codes.",
        count: codedExcerptCount
      },
      {
        id: "map",
        label: "Map codes to themes",
        detail: "Map each code to a final theme for consistent aggregation.",
        count: mappedCodes
      },
      {
        id: "aggregate",
        label: "Aggregate theme counts",
        detail: "Compute theme support from mapped codes and manual overrides.",
        count: themeLinks
      },
      {
        id: "notes",
        label: "Review notes",
        detail: "Track rationale, disagreements, and audit notes per excerpt.",
        count: reviewedCount
      }
    ];
  }, [codeDefinitions, resolvedThemeInfoByExcerpt, thematicRecords]);

  const k = (key: string) => asNumber(result?.keys?.[key]);

  async function handleAnalyze() {
    if (!surveyFile || !usabilityFile) {
      setError("Please upload both survey and usability workbooks.");
      return;
    }

    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append("survey_file", surveyFile);
    formData.append("usability_file", usabilityFile);
    if (taskOutcomesFile) formData.append("task_outcomes_file", taskOutcomesFile);
    if (themeAssignmentsFile) formData.append("theme_assignments_file", themeAssignmentsFile);
    formData.append("analysis_config", analysisConfig);

    try {
      const payload = await analyzeBundle(formData);
      const rawExcerptRecords = payload.tables?.excerpt_records;
      const excerptRecords =
        Array.isArray(rawExcerptRecords)
          ? rawExcerptRecords
              .filter((record): record is Record<string, unknown> => !!record && typeof record === "object")
              .map(recordFromUnknown)
          : [];
      startTransition(() => {
        setResult(payload);
        if (excerptRecords.length > 0) {
          setThematicRecords(excerptRecords);
        }
        setView("paper");
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleLoadThematic() {
    if (!usabilityFile) {
      setThematicError("Upload the usability workbook first to build the thematic process.");
      return;
    }
    setThematicLoading(true);
    setThematicError(null);
    try {
      const payload = await bootstrapThemeTemplate(usabilityFile, themeAssignmentsFile);
      const records = payload.records
        .filter((record): record is Record<string, unknown> => !!record && typeof record === "object")
        .map(recordFromUnknown);
      startTransition(() => {
        setThematicRecords(records);
        setView("thematic");
        setVisibleExcerpts(36);
      });
    } catch (err) {
      setThematicError(err instanceof Error ? err.message : "Failed to load thematic excerpts");
    } finally {
      setThematicLoading(false);
    }
  }

  function updateThemes(excerptId: string, themeId: string, enabled: boolean) {
    setThematicRecords((previous) =>
      previous.map((record) => {
        if (record.excerpt_id !== excerptId) return record;
        const nextThemes = enabled
          ? Array.from(new Set([...record.selectedThemes, themeId]))
          : record.selectedThemes.filter((item) => item !== themeId);
        return {
          ...record,
          selectedThemes: nextThemes,
          theme_id: nextThemes.join("|")
        };
      })
    );
  }

  function updateCodes(excerptId: string, codeId: string, enabled: boolean) {
    setThematicRecords((previous) =>
      previous.map((record) => {
        if (record.excerpt_id !== excerptId) return record;
        const nextCodes = enabled
          ? uniqueStrings([...record.selectedCodeIds, codeId])
          : record.selectedCodeIds.filter((item) => item !== codeId);
        return {
          ...record,
          selectedCodeIds: nextCodes
        };
      })
    );
  }

  function acceptSuggestedCodes(excerptId: string) {
    const suggested = uniqueStrings([
      ...(suggestedCodeIdsByExcerpt[excerptId] ?? []),
      candidateCodeIdByExcerpt[excerptId] ?? ""
    ]);
    if (suggested.length === 0) return;
    setThematicRecords((previous) =>
      previous.map((record) =>
        record.excerpt_id === excerptId
          ? {
              ...record,
              selectedCodeIds: uniqueStrings([...record.selectedCodeIds, ...suggested])
            }
          : record
      )
    );
  }

  function applySuggestionsToFiltered() {
    const targetIds = new Set(filteredThematicRecords.map((item) => item.excerpt_id));
    setThematicRecords((previous) =>
      previous.map((record) => {
        if (!targetIds.has(record.excerpt_id)) return record;
        const suggested = uniqueStrings([
          ...(suggestedCodeIdsByExcerpt[record.excerpt_id] ?? []),
          candidateCodeIdByExcerpt[record.excerpt_id] ?? ""
        ]);
        if (suggested.length === 0) return record;
        return {
          ...record,
          selectedCodeIds: uniqueStrings([...record.selectedCodeIds, ...suggested])
        };
      })
    );
  }

  function clearCodes(excerptId: string) {
    setThematicRecords((previous) =>
      previous.map((record) =>
        record.excerpt_id === excerptId
          ? {
              ...record,
              selectedCodeIds: []
            }
          : record
      )
    );
  }

  function updateNote(excerptId: string, note: string) {
    setThematicRecords((previous) =>
      previous.map((record) =>
        record.excerpt_id === excerptId
          ? {
              ...record,
              reviewer_notes: note
            }
          : record
      )
    );
  }

  function updateCodeDefinition(codeId: string, patch: Partial<CodeDefinition>) {
    setCodeDefinitions((previous) =>
      previous.map((code) =>
        code.code_id === codeId
          ? {
              ...code,
              ...patch
            }
          : code
      )
    );
  }

  function addCustomCode() {
    const label = newCodeLabel.trim();
    if (!label) return;
    const existing = new Set(codeDefinitions.map((item) => item.code_id));
    const codeId = customCodeIdFromLabel(label, existing);
    setCodeDefinitions((previous) => [
      ...previous,
      {
        code_id: codeId,
        label,
        description: newCodeDescription.trim(),
        mapped_theme_id: newCodeThemeId,
        origin: "custom"
      }
    ]);
    setNewCodeLabel("");
    setNewCodeThemeId("");
    setNewCodeDescription("");
  }

  function exportCodeAssignments() {
    if (thematicRecords.length === 0) return;
    const rows = [
      ["excerpt_id", "code_ids", "reviewer_notes"],
      ...thematicRecords.map((record) => [record.excerpt_id, record.selectedCodeIds.join("|"), record.reviewer_notes])
    ];
    downloadCsv("code_assignments.reviewed.csv", rows);
  }

  function exportCodebook() {
    if (codeDefinitions.length === 0) return;
    const rows = [
      ["code_id", "label", "mapped_theme_id", "description", "origin"],
      ...codeDefinitions.map((code) => [code.code_id, code.label, code.mapped_theme_id, code.description, code.origin])
    ];
    downloadCsv("codebook.reviewed.csv", rows);
  }

  function exportThemeAssignments() {
    if (thematicRecords.length === 0) return;
    const rows = [
      ["excerpt_id", "theme_id", "reviewer_notes"],
      ...thematicRecords.map((record) => {
        const resolvedThemes = resolvedThemeInfoByExcerpt[record.excerpt_id]?.resolvedThemes ?? record.selectedThemes;
        return [record.excerpt_id, resolvedThemes.join("|"), record.reviewer_notes];
      })
    ];
    downloadCsv("theme_assignments.reviewed.csv", rows);
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_#f6fbff,_#edf2fb_45%,_#e8edf8)] px-4 py-6 text-[#1b2742]">
      <div className="mx-auto max-w-[1500px]">
        <header className="rounded-3xl border border-[#d6deef] bg-white/80 p-6 shadow-[0_20px_55px_-38px_rgba(16,44,98,0.75)] backdrop-blur">
          <h1 className="text-3xl font-semibold tracking-tight">Paper-Mapped Email Encryption Analysis</h1>
          <p className="mt-2 max-w-4xl text-sm text-[#405175]">
            Recompute survey, usability, and thematic findings in the same structure as your paper. Paragraph summaries, paper-style tables, and thematic coding updates are linked to live values.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {([
              ["paper", "Paper View"],
              ["keys", "Key Browser"],
              ["thematic", "Thematic Process"]
            ] as const).map(([mode, label]) => (
              <button
                key={mode}
                onClick={() => setView(mode)}
                className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
                  view === mode
                    ? "border-[#1f6fba] bg-[#1f6fba] text-white"
                    : "border-[#ccd6ea] bg-white text-[#355078] hover:border-[#9eb2d5]"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </header>

        <div className="mt-6 grid gap-6 lg:grid-cols-[390px,1fr]">
          <section className="rounded-3xl border border-[#d6deef] bg-white p-5 shadow-[0_20px_55px_-38px_rgba(16,44,98,0.75)]">
            <h2 className="text-lg font-semibold">Inputs & Controls</h2>
            <div className="mt-4 space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-[#3a5078]">Survey workbook</label>
                <input type="file" accept=".xlsx,.xls" onChange={(e) => setSurveyFile(e.target.files?.[0] ?? null)} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-[#3a5078]">Usability workbook</label>
                <input type="file" accept=".xlsx,.xls" onChange={(e) => setUsabilityFile(e.target.files?.[0] ?? null)} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-[#3a5078]">Task outcomes CSV (optional for TSR)</label>
                <input type="file" accept=".csv" onChange={(e) => setTaskOutcomesFile(e.target.files?.[0] ?? null)} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-[#3a5078]">Theme assignments CSV (optional)</label>
                <input type="file" accept=".csv" onChange={(e) => setThemeAssignmentsFile(e.target.files?.[0] ?? null)} />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-[#3a5078]">Analysis config JSON</label>
                <textarea rows={10} value={analysisConfig} onChange={(e) => setAnalysisConfig(e.target.value)} />
              </div>
              <button
                onClick={handleAnalyze}
                disabled={loading}
                className="w-full rounded-xl bg-[#1f6fba] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#195f9f] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading ? "Analyzing..." : "Run Full Analysis"}
              </button>
              <button
                onClick={handleLoadThematic}
                disabled={thematicLoading}
                className="w-full rounded-xl border border-[#a7badc] bg-[#f3f7fe] px-4 py-3 text-sm font-semibold text-[#1f4f87] transition hover:bg-[#eaf2fd] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {thematicLoading ? "Loading excerpts..." : "Load Thematic Process"}
              </button>
              {result ? (
                <button
                  onClick={() => downloadJson("analysis-results.json", result)}
                  className="w-full rounded-xl border border-[#c8d4eb] bg-white px-4 py-3 text-sm font-medium text-[#2d4369] hover:bg-[#f6f9fe]"
                >
                  Download Analysis JSON
                </button>
              ) : null}
              {error ? <div className="rounded-xl border border-[#d25f5f] bg-[#fff3f3] px-3 py-2 text-sm text-[#8a2222]">{error}</div> : null}
              {thematicError ? <div className="rounded-xl border border-[#d25f5f] bg-[#fff3f3] px-3 py-2 text-sm text-[#8a2222]">{thematicError}</div> : null}
            </div>
          </section>

          <section className="space-y-6">
            {view === "paper" ? (
              <div className="space-y-6">
                {result ? (
                  <>
                    <section className="rounded-3xl border border-[#d6deef] bg-white p-5 shadow-[0_20px_55px_-38px_rgba(16,44,98,0.75)]">
                      <h2 className="text-lg font-semibold">Section 5: Survey Findings & Analysis</h2>
                      <p className="mt-3 text-sm leading-6 text-[#2f446a]">
                        The included survey dataset contains <strong>{formatMaybeNumber(k("survey.total_n"))}</strong> responses (submitted:{" "}
                        <strong>{formatMaybeNumber(k("survey.total_submitted_n"))}</strong>). Awareness of email encryption is{" "}
                        <strong>{formatPct(k("survey.awareness.yes_pct"))}</strong>, while active encryption usage remains{" "}
                        <strong>{formatPct(k("survey.current_usage.yes_pct"))}</strong>. Interception-risk acknowledgement (Yes or Maybe) is{" "}
                        <strong>{formatPct(k("survey.risk_interception.acknowledge_pct"))}</strong>.
                      </p>
                      <p className="mt-2 text-sm leading-6 text-[#2f446a]">
                        The perceived or suspected breach proportion (Yes or Maybe) is{" "}
                        <strong>{formatPct(k("survey.security_breach.reported_or_suspected_pct"))}</strong>. With guidance, future adoption intent currently shows{" "}
                        <strong>{formatPct(k("survey.future_adoption_guided.yes_pct"))}</strong> positive responses.
                      </p>
                    </section>
                    <div className="grid gap-6 xl:grid-cols-2">
                      <PaperTable title="Table 2: Awareness & Usage" rows={paperTable2} orderedKeys={["category", "response", "n", "pct"]} />
                      <PaperTable title="Table 3: Adoption Intent & Learning" rows={paperTable3} orderedKeys={["category", "response", "n", "pct"]} />
                    </div>
                    <PaperTable title="Table 4: Chi-square Correlations" rows={paperTable4} orderedKeys={["test", "chi2", "p_value", "interpretation"]} />
                    <div className="grid gap-6 xl:grid-cols-2">
                      <HorizontalBars title="Email Usage Pattern" rows={usageBars} />
                      <HorizontalBars title="Top Encryption Barriers" rows={barrierBars} />
                    </div>

                    <section className="rounded-3xl border border-[#d6deef] bg-white p-5 shadow-[0_20px_55px_-38px_rgba(16,44,98,0.75)]">
                      <h2 className="text-lg font-semibold">Section 6: Usability Findings & Analysis</h2>
                      <p className="mt-3 text-sm leading-6 text-[#2f446a]">
                        ProtonMail mean completion time is <strong>{formatMaybeNumber(k("usability.protonmail.time_mean_min"))}</strong> minutes with NASA-TLX{" "}
                        <strong>{formatMaybeNumber(k("usability.protonmail.nasa_tlx"))}</strong>. SecureMyEmail mean completion time is{" "}
                        <strong>{formatMaybeNumber(k("usability.securemyemail.time_mean_min"))}</strong> minutes with NASA-TLX{" "}
                        <strong>{formatMaybeNumber(k("usability.securemyemail.nasa_tlx"))}</strong>.{" "}
                        {k("usability.protonmail.tsr_overall") !== null
                          ? `TSR values are currently ${formatMaybeNumber(k("usability.protonmail.tsr_overall"))}% (ProtonMail) and ${formatMaybeNumber(
                              k("usability.securemyemail.tsr_overall")
                            )}% (SecureMyEmail).`
                          : "TSR rows will appear after uploading task outcomes."}
                      </p>
                    </section>

                    <div className="grid gap-6 xl:grid-cols-2">
                      <PaperTable title="Table 5: Performance Metrics" rows={paperTable5} orderedKeys={["metric", "protonmail", "securemyemail"]} />
                      <PaperTable title="Table 6: Task Success by Subtask" rows={paperTable6} orderedKeys={["task", "subtask", "label", "protonmail", "securemyemail"]} />
                    </div>

                    {result.warnings.length > 0 ? (
                      <section className="rounded-2xl border border-[#e5bb76] bg-[#fff9eb] p-4">
                        <h3 className="text-sm font-semibold uppercase tracking-wide text-[#8d5f1d]">Warnings</h3>
                        <ul className="mt-2 space-y-2 text-sm text-[#6c4a17]">
                          {result.warnings.map((warning) => (
                            <li key={warning}>{warning}</li>
                          ))}
                        </ul>
                      </section>
                    ) : null}
                  </>
                ) : (
                  <div className="rounded-3xl border border-dashed border-[#b8c7e4] bg-white/65 p-10 text-center text-sm text-[#49618d]">
                    Run analysis to render your results in paper-structured paragraphs and tables.
                  </div>
                )}
              </div>
            ) : null}

            {view === "keys" ? (
              <section className="rounded-3xl border border-[#d6deef] bg-white p-5 shadow-[0_20px_55px_-38px_rgba(16,44,98,0.75)]">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-lg font-semibold">Key Browser</h2>
                  <input
                    type="text"
                    placeholder="Search keys"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="max-w-sm"
                  />
                </div>
                {result ? (
                  <div className="mt-4 overflow-hidden rounded-xl border border-[#dde4f3]">
                    <table className="min-w-full text-sm">
                      <thead className="bg-[#f3f6fd] text-left text-[#3f5379]">
                        <tr>
                          <th className="px-4 py-2">Key</th>
                          <th className="px-4 py-2">Value</th>
                          <th className="px-4 py-2">Description</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#eef2f8] text-[#253752]">
                        {filteredEntries.map(([key, value]) => (
                          <tr key={key}>
                            <td className="px-4 py-2 font-mono text-xs text-[#1f5f9a]">{key}</td>
                            <td className="px-4 py-2">{String(value)}</td>
                            <td className="px-4 py-2">{result.registry[key]?.description ?? ""}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="mt-4 rounded-xl border border-dashed border-[#b8c7e4] p-6 text-sm text-[#4b628e]">No results yet.</div>
                )}
              </section>
            ) : null}

            {view === "thematic" ? (
              <div className="space-y-6">
                <section className="rounded-3xl border border-[#d6deef] bg-white p-5 shadow-[0_20px_55px_-38px_rgba(16,44,98,0.75)]">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h2 className="text-lg font-semibold">Thematic Analysis Process</h2>
                    <div className="flex gap-2">
                      <button
                        onClick={handleLoadThematic}
                        className="rounded-xl border border-[#9fb5da] px-3 py-2 text-sm font-medium text-[#255289] hover:bg-[#f3f7fe]"
                      >
                        Refresh Excerpts
                      </button>
                      <button
                        onClick={exportCodeAssignments}
                        disabled={thematicRecords.length === 0}
                        className="rounded-xl border border-[#9fb5da] px-3 py-2 text-sm font-medium text-[#255289] hover:bg-[#f3f7fe] disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        Export Code Assignments
                      </button>
                      <button
                        onClick={exportCodebook}
                        disabled={codeDefinitions.length === 0}
                        className="rounded-xl border border-[#9fb5da] px-3 py-2 text-sm font-medium text-[#255289] hover:bg-[#f3f7fe] disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        Export Codebook
                      </button>
                      <button
                        onClick={exportThemeAssignments}
                        disabled={thematicRecords.length === 0}
                        className="rounded-xl bg-[#1f6fba] px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        Export Final Theme Assignments
                      </button>
                    </div>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-[#324a74]">
                    Workflow: first review codes per excerpt, then map codes to themes, then aggregate final counts. Theme counts below are computed from
                    accepted codes and code-to-theme mappings (plus any manual theme override).
                  </p>
                  {codeDefinitions.length === 0 ? (
                    <p className="mt-2 rounded-xl border border-[#e3d7a3] bg-[#fff9e8] px-3 py-2 text-xs text-[#6f5a1e]">
                      No auto-generated codebook loaded yet. Run <strong>Full Analysis</strong> once to get code suggestions, or add custom codes manually.
                    </p>
                  ) : null}
                  <div className="mt-4 grid gap-3 md:grid-cols-5">
                    {thematicProcess.map((step, index) => (
                      <div key={step.id} className="rounded-xl border border-[#d8e0f1] bg-[#f8fbff] p-3">
                        <div className="text-xs uppercase tracking-wide text-[#58709b]">Step {index + 1}</div>
                        <div className="mt-1 text-sm font-semibold text-[#20375b]">{step.label}</div>
                        <p className="mt-1 text-xs leading-5 text-[#6078a3]">{step.detail}</p>
                        <div className="mt-2 text-2xl font-semibold text-[#1f6fba]">{step.count}</div>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="rounded-3xl border border-[#d6deef] bg-white p-5 shadow-[0_20px_55px_-38px_rgba(16,44,98,0.75)]">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold uppercase tracking-wide text-[#1e2a45]">Step 2: Code Review Per Excerpt</h3>
                      <p className="mt-1 text-sm text-[#4d648f]">
                        Accept suggested codes, add/remove codes manually, and keep notes for your interpretation decisions.
                      </p>
                    </div>
                    <button
                      onClick={applySuggestionsToFiltered}
                      disabled={filteredThematicRecords.length === 0}
                      className="rounded-xl border border-[#9fb5da] px-3 py-2 text-sm font-medium text-[#255289] hover:bg-[#f3f7fe] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      Accept Suggestions (Filtered)
                    </button>
                  </div>
                  <div className="grid gap-3 md:grid-cols-4">
                    <input
                      type="text"
                      value={themeSearch}
                      onChange={(e) => setThemeSearch(e.target.value)}
                      placeholder="Search excerpts or participant"
                      className="md:col-span-2"
                    />
                    <select
                      value={themeToolFilter}
                      onChange={(e) => setThemeToolFilter(e.target.value)}
                      className="rounded-lg border border-[#c8d4eb] bg-white px-3 py-2 text-sm text-[#253752]"
                    >
                      <option value="all">All tools</option>
                      <option value="protonmail">ProtonMail</option>
                      <option value="securemyemail">SecureMyEmail</option>
                      <option value="overall">Overall interview</option>
                    </select>
                    <select
                      value={themeTaskFilter}
                      onChange={(e) => setThemeTaskFilter(e.target.value)}
                      className="rounded-lg border border-[#c8d4eb] bg-white px-3 py-2 text-sm text-[#253752]"
                    >
                      <option value="all">All tasks</option>
                      <option value="task1">Task 1</option>
                      <option value="task2">Task 2</option>
                      <option value="task3">Task 3</option>
                      <option value="interview">Interview</option>
                    </select>
                  </div>

                  {filteredThematicRecords.length === 0 ? (
                    <div className="mt-4 rounded-xl border border-dashed border-[#b8c7e4] p-6 text-sm text-[#4b628e]">
                      No excerpts loaded yet. Use “Load Thematic Process” to start coding.
                    </div>
                  ) : (
                    <>
                      <p className="mt-4 text-sm text-[#3f567f]">
                        Showing {Math.min(visibleExcerpts, filteredThematicRecords.length)} of {filteredThematicRecords.length} filtered excerpts.
                      </p>
                      <div className="mt-3 space-y-4">
                        {filteredThematicRecords.slice(0, visibleExcerpts).map((record) => (
                          <article key={record.excerpt_id} className="rounded-2xl border border-[#dce4f2] bg-[#fcfdff] p-4">
                            {(() => {
                              const themeInfo = resolvedThemeInfoByExcerpt[record.excerpt_id] ?? {
                                derivedThemes: [],
                                resolvedThemes: [],
                                unmappedCodeIds: []
                              };
                              const suggestedCodeIds = uniqueStrings([
                                ...(suggestedCodeIdsByExcerpt[record.excerpt_id] ?? []),
                                candidateCodeIdByExcerpt[record.excerpt_id] ?? ""
                              ]);
                              const unacceptedSuggested = suggestedCodeIds.filter((codeId) => !record.selectedCodeIds.includes(codeId));
                              return (
                                <>
                                  <div className="flex flex-wrap items-center gap-2 text-xs text-[#5d759f]">
                                    <span className="rounded-full bg-[#eef3fc] px-2 py-1 font-mono">{record.excerpt_id}</span>
                                    <span>{record.participant_name || "Participant"}</span>
                                    <span>{record.tool}</span>
                                    <span>{record.task}</span>
                                    <span>{record.prompt_id}</span>
                                    <span
                                      className={`rounded-full px-2 py-1 text-[11px] font-semibold ${
                                        record.selectedCodeIds.length > 0 ? "bg-emerald-100 text-emerald-900" : "bg-[#edf2fb] text-[#4b628e]"
                                      }`}
                                    >
                                      {record.selectedCodeIds.length > 0 ? `Codes Assigned (${record.selectedCodeIds.length})` : "Codes Unassigned"}
                                    </span>
                                    <span
                                      className={`rounded-full px-2 py-1 text-[11px] font-semibold ${
                                        themeInfo.resolvedThemes.length > 0 ? "bg-sky-100 text-sky-900" : "bg-[#edf2fb] text-[#4b628e]"
                                      }`}
                                    >
                                      {themeInfo.resolvedThemes.length > 0 ? `Themes Resolved (${themeInfo.resolvedThemes.length})` : "Themes Unresolved"}
                                    </span>
                                  </div>
                                  <p className="mt-2 text-sm leading-6 text-[#213a5f]">{record.text}</p>
                                  {suggestionMap[record.excerpt_id] ? (
                                    <div className="mt-2 rounded-lg border border-[#d7e2f4] bg-[#f8fbff] px-3 py-2 text-xs text-[#2f4f80]">
                                      Suggested codes: {suggestionMap[record.excerpt_id]}
                                    </div>
                                  ) : null}
                                  {candidateSuggestionMap[record.excerpt_id] ? (
                                    <div className="mt-2 rounded-lg border border-[#e1e1ea] bg-[#fafafc] px-3 py-2 text-xs text-[#3f4a6a]">
                                      Candidate new code: {candidateSuggestionMap[record.excerpt_id]}
                                    </div>
                                  ) : null}
                                  <div className="mt-3 flex flex-wrap gap-2">
                                    <button
                                      onClick={() => acceptSuggestedCodes(record.excerpt_id)}
                                      disabled={unacceptedSuggested.length === 0}
                                      className="rounded-lg border border-[#a6bbde] px-3 py-1.5 text-xs font-medium text-[#264f82] hover:bg-[#f2f7ff] disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                      Accept Suggested Codes ({unacceptedSuggested.length})
                                    </button>
                                    <button
                                      onClick={() => clearCodes(record.excerpt_id)}
                                      disabled={record.selectedCodeIds.length === 0}
                                      className="rounded-lg border border-[#d8c2c2] px-3 py-1.5 text-xs font-medium text-[#7a3e3e] hover:bg-[#fff6f6] disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                      Clear Codes
                                    </button>
                                  </div>

                                  <div className="mt-3 rounded-xl border border-[#e0e8f5] bg-white p-3">
                                    <p className="text-xs font-semibold uppercase tracking-wide text-[#516a95]">Accepted Codes</p>
                                    {codeDefinitions.length === 0 ? (
                                      <p className="mt-2 text-xs text-[#5a719c]">
                                        No codebook available yet. Add codes in Step 3 or run full analysis for suggestions.
                                      </p>
                                    ) : (
                                      <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                                        {codeDefinitions.map((code) => {
                                          const checked = record.selectedCodeIds.includes(code.code_id);
                                          return (
                                            <label key={`${record.excerpt_id}-${code.code_id}`} className="flex items-start gap-2 text-xs text-[#2b436a]">
                                              <input
                                                type="checkbox"
                                                checked={checked}
                                                onChange={(e) => updateCodes(record.excerpt_id, code.code_id, e.target.checked)}
                                                className="mt-0.5"
                                              />
                                              <span>
                                                <span className="block font-medium">{code.label}</span>
                                                <span className="font-mono text-[11px] text-[#6f86ae]">{code.code_id}</span>
                                              </span>
                                            </label>
                                          );
                                        })}
                                      </div>
                                    )}
                                  </div>

                                  <div className="mt-3 rounded-xl border border-[#d8e4f5] bg-[#f7fbff] px-3 py-2">
                                    <p className="text-xs font-semibold uppercase tracking-wide text-[#4f6892]">Derived Themes From Accepted Codes</p>
                                    {themeInfo.derivedThemes.length > 0 ? (
                                      <div className="mt-2 flex flex-wrap gap-2">
                                        {themeInfo.derivedThemes.map((themeId) => (
                                          <span key={`${record.excerpt_id}-derived-${themeId}`} className="rounded-full bg-[#e3eefc] px-2 py-1 text-xs text-[#2a4d7d]">
                                            {codebook.find((item) => item.theme_id === themeId)?.label ?? themeId}
                                          </span>
                                        ))}
                                      </div>
                                    ) : (
                                      <p className="mt-2 text-xs text-[#5a719c]">No mapped theme yet from codes.</p>
                                    )}
                                    {themeInfo.unmappedCodeIds.length > 0 ? (
                                      <p className="mt-2 text-xs text-[#8b5f26]">
                                        Unmapped codes:{" "}
                                        {themeInfo.unmappedCodeIds.map((codeId) => codeLabelById[codeId] ?? codeId).join(", ")}. Map them in Step 3.
                                      </p>
                                    ) : null}
                                  </div>

                                  <details className="mt-3 rounded-xl border border-[#e0e8f5] bg-white p-3">
                                    <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-[#516a95]">
                                      Manual Theme Override (Optional)
                                    </summary>
                                    <p className="mt-2 text-xs text-[#59739f]">
                                      Use this only if a specific excerpt needs manual theme adjustment beyond the code mapping.
                                    </p>
                                    <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                                      {codebook.map((theme) => {
                                        const checked = record.selectedThemes.includes(theme.theme_id);
                                        return (
                                          <label key={`${record.excerpt_id}-${theme.theme_id}`} className="flex items-start gap-2 text-xs text-[#2b436a]">
                                            <input
                                              type="checkbox"
                                              checked={checked}
                                              onChange={(e) => updateThemes(record.excerpt_id, theme.theme_id, e.target.checked)}
                                              className="mt-0.5"
                                            />
                                            <span>
                                              <span className="block font-medium">{theme.label}</span>
                                              <span className="font-mono text-[11px] text-[#6f86ae]">{theme.theme_id}</span>
                                            </span>
                                          </label>
                                        );
                                      })}
                                    </div>
                                  </details>

                                  <textarea
                                    rows={3}
                                    value={record.reviewer_notes}
                                    onChange={(e) => updateNote(record.excerpt_id, e.target.value)}
                                    placeholder="Reviewer notes (why this coding decision was made)"
                                    className="mt-3"
                                  />
                                </>
                              );
                            })()}
                          </article>
                        ))}
                      </div>
                      {visibleExcerpts < filteredThematicRecords.length ? (
                        <button
                          onClick={() => setVisibleExcerpts((count) => count + 36)}
                          className="mt-4 rounded-xl border border-[#b5c7e7] px-4 py-2 text-sm font-medium text-[#2e4f7e] hover:bg-[#f3f7fe]"
                        >
                          Show More Excerpts
                        </button>
                      ) : null}
                    </>
                  )}
                </section>

                <section className="rounded-3xl border border-[#d6deef] bg-white p-5 shadow-[0_20px_55px_-38px_rgba(16,44,98,0.75)]">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-[#1e2a45]">Step 3: Codebook and Theme Mapping</h3>
                  <p className="mt-1 text-sm text-[#4d648f]">
                    Ensure each accepted code maps to a theme. Unmapped codes will not contribute to automatic theme counts.
                  </p>

                  <div className="mt-3 rounded-2xl border border-[#d9e3f3] bg-[#f8fbff] p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-[#4f6892]">Add Custom Code</p>
                    <div className="mt-2 grid gap-2 md:grid-cols-[2fr,1fr,2fr,auto]">
                      <input
                        type="text"
                        value={newCodeLabel}
                        onChange={(e) => setNewCodeLabel(e.target.value)}
                        placeholder="Code label (e.g., Credential confusion)"
                      />
                      <select
                        value={newCodeThemeId}
                        onChange={(e) => setNewCodeThemeId(e.target.value)}
                        className="rounded-lg border border-[#c8d4eb] bg-white px-3 py-2 text-sm text-[#253752]"
                      >
                        <option value="">No mapped theme yet</option>
                        {codebook.map((theme) => (
                          <option key={`new-${theme.theme_id}`} value={theme.theme_id}>
                            {theme.label}
                          </option>
                        ))}
                      </select>
                      <input
                        type="text"
                        value={newCodeDescription}
                        onChange={(e) => setNewCodeDescription(e.target.value)}
                        placeholder="Optional code description"
                      />
                      <button
                        onClick={addCustomCode}
                        className="rounded-xl border border-[#9fb5da] px-3 py-2 text-sm font-medium text-[#255289] hover:bg-[#f3f7fe]"
                      >
                        Add Code
                      </button>
                    </div>
                  </div>

                  {codeDefinitions.length > 0 ? (
                    <div className="mt-3 overflow-x-auto rounded-xl border border-[#dde4f3]">
                      <table className="min-w-full text-sm">
                        <thead className="bg-[#f3f6fd] text-left text-[#405175]">
                          <tr>
                            <th className="px-3 py-2">Code ID</th>
                            <th className="px-3 py-2">Label</th>
                            <th className="px-3 py-2">Mapped Theme</th>
                            <th className="px-3 py-2">Usage</th>
                            <th className="px-3 py-2">Origin</th>
                            <th className="px-3 py-2">Description</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#eef2f8] text-[#253752]">
                          {codeDefinitions.map((code) => {
                            const usage = codeUsageById[code.code_id];
                            const excerptsN = usage?.excerpts ?? 0;
                            const participantsN = usage?.participants.size ?? 0;
                            return (
                              <tr key={code.code_id}>
                                <td className="px-3 py-2 font-mono text-xs text-[#2a5f9d]">{code.code_id}</td>
                                <td className="px-3 py-2">
                                  <input
                                    value={code.label}
                                    onChange={(e) => updateCodeDefinition(code.code_id, { label: e.target.value })}
                                    className="w-full"
                                  />
                                </td>
                                <td className="px-3 py-2">
                                  <select
                                    value={code.mapped_theme_id}
                                    onChange={(e) => updateCodeDefinition(code.code_id, { mapped_theme_id: e.target.value })}
                                    className="w-full rounded-lg border border-[#c8d4eb] bg-white px-2 py-1 text-sm text-[#253752]"
                                  >
                                    <option value="">Unmapped</option>
                                    {codebook.map((theme) => (
                                      <option key={`${code.code_id}-${theme.theme_id}`} value={theme.theme_id}>
                                        {theme.label}
                                      </option>
                                    ))}
                                  </select>
                                </td>
                                <td className="px-3 py-2 text-xs text-[#4f6791]">
                                  {excerptsN} excerpts / {participantsN} participants
                                </td>
                                <td className="px-3 py-2 text-xs uppercase tracking-wide text-[#6d84ac]">{code.origin}</td>
                                <td className="px-3 py-2">
                                  <input
                                    value={code.description}
                                    onChange={(e) => updateCodeDefinition(code.code_id, { description: e.target.value })}
                                    className="w-full"
                                  />
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="mt-3 text-sm text-[#4d648f]">No codebook yet. Add custom codes, or run full analysis to generate common/candidate codes.</p>
                  )}
                </section>

                <section className="rounded-3xl border border-[#d6deef] bg-white p-5 shadow-[0_20px_55px_-38px_rgba(16,44,98,0.75)]">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-[#1e2a45]">Step 4: Aggregated Theme Coverage</h3>
                  {thematicThemeCounts.length > 0 ? (
                    <div className="mt-3 overflow-x-auto">
                      <table className="min-w-full text-sm">
                        <thead className="bg-[#f3f6fd] text-left text-[#405175]">
                          <tr>
                            <th className="px-4 py-2">Theme</th>
                            <th className="px-4 py-2">Excerpts</th>
                            <th className="px-4 py-2">Participants</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#eef2f8] text-[#253752]">
                          {thematicThemeCounts.map((row) => (
                            <tr key={row.theme_id}>
                              <td className="px-4 py-2">
                                {row.label}
                                <span className="ml-2 font-mono text-xs text-[#6280ae]">{row.theme_id}</span>
                              </td>
                              <td className="px-4 py-2">{row.excerpts_n}</td>
                              <td className="px-4 py-2">{row.participants_n}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="mt-2 text-sm text-[#4d648f]">No theme counts yet. Assign codes and map codes to themes first.</p>
                  )}

                  {unmappedCodeUsageRows.length > 0 ? (
                    <div className="mt-4 rounded-xl border border-[#edd8b4] bg-[#fff8ec] p-3 text-sm text-[#6f5422]">
                      <p className="font-semibold">Codes waiting for theme mapping</p>
                      <p className="mt-1">
                        {unmappedCodeUsageRows.map((row) => `${row.label} (${row.excerpts_n})`).join(", ")}
                      </p>
                    </div>
                  ) : null}
                </section>
              </div>
            ) : null}
          </section>
        </div>
      </div>
    </main>
  );
}
