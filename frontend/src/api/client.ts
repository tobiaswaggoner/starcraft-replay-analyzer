export type TagCategory = "strategy" | "tech" | "build" | "tempo" | "outcome";
export type TagSource = "llm" | "manual";

export interface Tag {
  slug: string;
  name: string;
  category: TagCategory;
  description: string | null;
  applies_to_races: string[] | null;
  color: string | null;
  created_by: "system" | "user";
  created_at: string;
}

export interface PlayerTag {
  tag_slug: string;
  source: TagSource;
  confidence: number | null;
  reasoning: string | null;
  model: string | null;
  name: string;
  category: TagCategory;
  color: string | null;
}

export interface Player {
  id: number;
  match_id: number;
  player_index: number;
  toon_handle: string | null;
  name: string;
  race: "Terran" | "Zerg" | "Protoss" | string;
  result: "Win" | "Loss" | "Tie" | null;
  mmr: number | null;
  is_me: 0 | 1;
  is_human: 0 | 1;
  metrics: Record<string, number | null>;
  tags: PlayerTag[];
}

export type MatchMode = "PvP" | "PvAI" | "AI";

export interface TaggingRun {
  model: string;
  prompt_version: string;
  match_summary: string | null;
  created_at: string;
}

export interface Match {
  id: number;
  file_hash: string;
  file_path: string;
  filename: string;
  played_at: string;
  duration_seconds: number;
  map_name: string;
  game_version: string | null;
  game_type: string | null;
  matchup: string | null;
  region: string | null;
  game_format: string | null;
  mode: MatchMode;
  player_count_label: string;
  players: Player[];
}

export interface TimeseriesRow {
  game_time_seconds: number;
  workers: number | null;
  supply_used: number | null;
  supply_cap: number | null;
  minerals_collected: number | null;
  gas_collected: number | null;
  army_value: number | null;
}

export interface BuildEvent {
  game_time_seconds: number;
  supply: number | null;
  event_type: "born" | "init" | "upgrade";
  name: string;
}

export interface ApmMinute {
  minute: number;
  apm: number;
}

export interface MatchDetail extends Match {
  players: (Player & {
    timeseries: TimeseriesRow[];
    build_events: BuildEvent[];
    apm_minutes: ApmMinute[];
  })[];
  target_evaluations: TargetEvaluation[];
  tagging_run: TaggingRun | null;
}

export type Operator = ">=" | "<=" | "==";

export interface TrainingTarget {
  id: number;
  name: string;
  metric_name: string;
  operator: Operator;
  threshold: number;
  race: string | null;
  matchup: string | null;
  mode: string | null;
  enabled: boolean;
  created_at: string;
}

export interface TrainingTargetInput {
  name: string;
  metric_name: string;
  operator: Operator;
  threshold: number;
  race?: string | null;
  matchup?: string | null;
  mode?: string | null;
  enabled: boolean;
}

export interface TargetEvaluation {
  target: TrainingTarget;
  target_id: number;
  value: number | null;
  pass: boolean | null;
  delta: number | null;
}

export interface TrendPoint {
  match_id: number;
  played_at: string;
  map_name: string;
  matchup: string | null;
  result: string | null;
  value: number | null;
}

export interface FacetTag {
  slug: string;
  name: string;
  category: TagCategory;
  color: string | null;
  usage_count: number;
}

export interface Facets {
  maps: string[];
  matchups: string[];
  game_formats: string[];
  races: string[];
  results: string[];
  modes: MatchMode[];
  tags: FacetTag[];
}

export interface AppSettings {
  tagging_model: string;
  auto_tag_on_ingest: boolean;
  openrouter_api_key_masked: string;
  openrouter_api_key_set: boolean;
  available_models: { id: string; label: string; tier: string }[];
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${await r.text()}`);
  return r.json();
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${await r.text()}`);
  return r.json();
}

async function del<T>(path: string): Promise<T> {
  const r = await fetch(path, { method: "DELETE" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export const api = {
  health: () => get<{ ok: boolean; replay_dir: string | null; db_path: string }>("/api/health"),
  metrics: () => get<{ metrics: string[] }>("/api/metrics"),
  facets: () => get<Facets>("/api/facets"),
  listMatches: (params: Record<string, string | number | undefined> = {}) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") q.set(k, String(v));
    const qs = q.toString();
    return get<{ items: Match[]; total: number; limit: number; offset: number }>(
      `/api/matches${qs ? `?${qs}` : ""}`,
    );
  },
  getSettings: () => get<AppSettings>("/api/settings"),
  patchSettings: (body: Partial<{ openrouter_api_key: string; tagging_model: string; auto_tag_on_ingest: boolean }>) =>
    patch<AppSettings>("/api/settings", body),
  testConnection: () => post<{ ok: boolean; model: string; response?: string; error?: string }>("/api/settings/test-connection"),
  listTagVocab: () => get<{ items: Tag[] }>("/api/tags"),
  createTagVocab: (t: Partial<Tag> & { slug: string; name: string; category: TagCategory }) =>
    post<Tag>("/api/tags", t),
  updateTagVocab: (slug: string, t: Partial<Tag>) => patch<Tag>(`/api/tags/${slug}`, t),
  deleteTagVocab: (slug: string) => del<{ ok: true }>(`/api/tags/${slug}`),
  resetSeedTags: () => post<{ imported: number }>("/api/tags/reset-seed"),
  tagMatch: (id: number, retag = false) =>
    post<{ status: string; match_id: number; model: string; tags_written?: number; summary?: string }>(
      `/api/matches/${id}/tag${retag ? "?retag=true" : ""}`,
    ),
  runBatchTagging: (limit?: number) =>
    post<{ candidates: number; tagged: number; errors: { match_id: number; error: string }[] }>(
      `/api/tagging/run${limit ? `?limit=${limit}` : ""}`,
    ),
  addPlayerTag: (playerId: number, tagSlug: string) =>
    post<{ player_id: number; tag_slug: string; source: string }>(`/api/players/${playerId}/tags`, { tag_slug: tagSlug }),
  removePlayerTag: (playerId: number, tagSlug: string, source: string = "manual") =>
    del<{ ok: true }>(`/api/players/${playerId}/tags/${tagSlug}?source=${source}`),
  getMatch: (id: number) => get<MatchDetail>(`/api/matches/${id}`),
  trend: (metric: string, params: Record<string, string | undefined> = {}) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
    const qs = q.toString();
    return get<{ metric: string; points: TrendPoint[] }>(
      `/api/trends/${metric}${qs ? `?${qs}` : ""}`,
    );
  },
  scan: () => post<{ seen: number; new: number; errors: number }>("/api/ingest/scan"),
  recompute: () => post<{ players: number; metrics: string[]; elapsed_seconds: number }>("/api/ingest/recompute"),
  reparseApm: () => post<{ matches: number; updated_players: number; skipped_missing_files: number; errors: number; elapsed_seconds: number }>("/api/ingest/reparse-apm"),
  listTargets: () => get<{ items: TrainingTarget[] }>("/api/targets"),
  createTarget: (t: TrainingTargetInput) => post<TrainingTarget>("/api/targets", t),
  updateTarget: (id: number, t: TrainingTargetInput) => patch<TrainingTarget>(`/api/targets/${id}`, t),
  deleteTarget: (id: number) => del<{ ok: true }>(`/api/targets/${id}`),
};

export function formatDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function formatMetric(name: string, value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (name.endsWith("_seconds") || name.startsWith("time_to_")) return formatDuration(value);
  if (Number.isInteger(value)) return value.toString();
  return value.toFixed(1);
}

const METRIC_LABELS: Record<string, string> = {
  apm: "APM",
  workers_at_4min: "Workers @ 4:00",
  workers_at_8min: "Workers @ 8:00",
  workers_peak: "Workers (peak)",
  supply_peak: "Supply (peak)",
  supply_blocked_seconds: "Supply blocked",
  time_to_max_supply: "Time to max",
};

export function metricLabel(name: string): string {
  return METRIC_LABELS[name] ?? name;
}

export function shortenAIName(name: string): string {
  // "A.I. 1 (Very Hard)" -> "AI (Very Hard)"
  const m = name.match(/^A\.I\.\s*\d+\s*\((.+)\)$/);
  return m ? `AI (${m[1]})` : name;
}

// Distinct, accessible-on-dark colors assigned per-player by index.
// Used in charts where race-color would collide (e.g. 2 Terrans, 1v7 coop).
// Race is still conveyed in the legend label and in non-chart UI via RacePill.
const PLAYER_COLORS = [
  "#5aa9ff",  // sky blue
  "#f78fb3",  // pink
  "#a3d977",  // green
  "#f1c83b",  // yellow
  "#b45cff",  // purple
  "#fb923c",  // orange
  "#22d3ee",  // cyan
  "#e879f9",  // magenta
];

export function playerColor(playerIndex: number): string {
  // player_index in sc2reader is 1-based; clamp to palette length.
  const i = Math.max(0, (playerIndex - 1)) % PLAYER_COLORS.length;
  return PLAYER_COLORS[i];
}

// Build event categorization — used for color-coding in the build-order list.
export type BuildCategory = "worker" | "unit" | "building" | "upgrade" | "other";

const WORKER_NAMES = new Set(["SCV", "Drone", "Probe", "MULE"]);

export function categorizeBuildEvent(eventType: string, name: string): BuildCategory {
  if (eventType === "upgrade") return "upgrade";
  if (eventType === "init") return "building";
  if (eventType === "born") {
    if (WORKER_NAMES.has(name)) return "worker";
    return "unit";
  }
  return "other";
}

export const BUILD_CATEGORY_COLORS: Record<BuildCategory, string> = {
  worker: "#a3d977",   // green
  unit: "#f87171",     // red
  building: "#5aa9ff", // blue
  upgrade: "#b45cff",  // purple
  other: "#9aa3b6",    // grey
};

export const BUILD_CATEGORY_LABELS: Record<BuildCategory, string> = {
  worker: "WORKER",
  unit: "UNIT",
  building: "BUILDING",
  upgrade: "UPGRADE",
  other: "OTHER",
};

export function findMe(players: Player[]): Player | undefined {
  return players.find((p) => p.is_me === 1) ?? players.find((p) => p.is_human === 1);
}

export function opponentsOf(players: Player[], me: Player | undefined): Player[] {
  if (!me) return players;
  return players.filter((p) => p.id !== me.id);
}

export function targetScopeChips(t: TrainingTarget): string[] {
  const out: string[] = [];
  if (t.race) out.push(t.race);
  if (t.matchup) out.push(t.matchup);
  if (t.mode) out.push(t.mode);
  if (out.length === 0) out.push("any match");
  return out;
}

export function targetSummary(t: TrainingTarget): string {
  return `${metricLabel(t.metric_name)} ${t.operator} ${formatMetric(t.metric_name, t.threshold)}`;
}
