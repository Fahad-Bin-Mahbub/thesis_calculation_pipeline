export type KeyInfo = {
  description: string;
  source: string;
  group: string;
};

export type PaperTableRow = Record<string, string | number | null>;

export type AnalysisResponse = {
  generated_at: string;
  keys: Record<string, string | number | null>;
  registry: Record<string, KeyInfo>;
  warnings: string[];
  tables: Record<string, unknown>;
  metadata: Record<string, unknown>;
};

export type BootstrapTemplateResponse = {
  generated_at: string;
  records: Record<string, unknown>[];
};

export type ThemeCodebookItem = {
  theme_id: string;
  label: string;
  description?: string;
};
