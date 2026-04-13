import type { AnalysisResponse, BootstrapTemplateResponse, ThemeCodebookItem } from "../types";

const RAW_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const API_BASE_URL = RAW_API_BASE_URL.replace(/\/+$/, "");

export async function analyzeBundle(formData: FormData): Promise<AnalysisResponse> {
  const response = await fetch(`${API_BASE_URL}/api/analyze`, {
    method: "POST",
    body: formData
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Analysis failed");
  }

  return (await response.json()) as AnalysisResponse;
}

export async function bootstrapThemeTemplate(
  usabilityFile: File,
  themeAssignmentsFile?: File | null
): Promise<BootstrapTemplateResponse> {
  const formData = new FormData();
  formData.append("usability_file", usabilityFile);
  if (themeAssignmentsFile) formData.append("theme_assignments_file", themeAssignmentsFile);
  const response = await fetch(`${API_BASE_URL}/api/bootstrap/theme-template`, {
    method: "POST",
    body: formData
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Failed to bootstrap theme template");
  }
  return (await response.json()) as BootstrapTemplateResponse;
}

export async function bootstrapTaskTemplate(usabilityFile: File): Promise<BootstrapTemplateResponse> {
  const formData = new FormData();
  formData.append("usability_file", usabilityFile);
  const response = await fetch(`${API_BASE_URL}/api/bootstrap/task-template`, {
    method: "POST",
    body: formData
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Failed to bootstrap task template");
  }
  return (await response.json()) as BootstrapTemplateResponse;
}

export async function loadThemeCodebook(): Promise<ThemeCodebookItem[]> {
  const response = await fetch(`${API_BASE_URL}/api/theme-codebook`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Failed to load theme codebook");
  }
  const payload = (await response.json()) as { items?: ThemeCodebookItem[] };
  return payload.items ?? [];
}
