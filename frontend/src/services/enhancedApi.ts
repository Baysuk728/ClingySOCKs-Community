/**
 * Enhanced Memory API — subconscious daemon, orient/ground, threads, schedules, presence.
 */
import { getApiUrlSync, API_KEY } from './apiConfig';

const API_URL = getApiUrlSync();

const headers = (json = false): Record<string, string> => ({
  ...(json ? { 'Content-Type': 'application/json' } : {}),
  ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
});

async function get<T = any>(path: string): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`, { headers: headers() });
  if (!resp.ok) throw new Error(`GET ${path}: ${resp.status}`);
  return resp.json();
}

async function post<T = any>(path: string, body?: unknown): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: headers(true),
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  if (!resp.ok) throw new Error(`POST ${path}: ${resp.status}`);
  return resp.json();
}

// ── Subconscious Daemon ──

export const getSubconsciousStatus = (entityId: string) =>
  get<SubconsciousResult>(`/enhanced/${entityId}/subconscious`);

export const triggerSubconsciousCycle = (entityId: string) =>
  post<SubconsciousResult>(`/enhanced/${entityId}/subconscious/run`);

// ── Orient / Ground / Boot ──

export const getOrient = (entityId: string) =>
  get(`/enhanced/${entityId}/orient`);

export const getGround = (entityId: string) =>
  get(`/enhanced/${entityId}/ground`);

export const getBoot = (entityId: string) =>
  get(`/enhanced/${entityId}/boot`);

export const getBootText = (entityId: string) =>
  get<{ text: string }>(`/enhanced/${entityId}/boot/text`);

// ── Persistent Threads ──

export const listThreads = (entityId: string) =>
  get<Thread[]>(`/enhanced/${entityId}/threads`);

export const createThread = (entityId: string, title: string, content: string) =>
  post(`/enhanced/${entityId}/threads`, { title, content });

// ── Schedules ──

export const listSchedules = (entityId: string) =>
  get<Schedule[]>(`/enhanced/${entityId}/schedules`);

// ── Types ──

export interface SubconsciousResult {
  entity_id?: string;
  timestamp?: string;
  orphans: Orphan[];
  patterns: Pattern[];
  proposals: Proposal[];
  mood_trends: MoodTrends;
  orphans_error?: string;
  patterns_error?: string;
  proposals_error?: string;
  mood_trends_error?: string;
}

export interface Orphan {
  type: string;
  id: string;
  label: string;
  created_at: string;
}

export interface Pattern {
  node_a: string;
  node_b: string;
  shared_neighbors: number;
  suggestion: string;
}

export interface Proposal {
  type: string;
  source_type?: string;
  source_id?: string;
  source_label?: string;
  node_a?: string;
  node_b?: string;
  reason: string;
  status: string;
  created_at: string;
}

export interface MoodTrends {
  status?: string;
  message?: string;
  period_days?: number;
  data_points?: number;
  averages?: Record<string, number>;
  trends?: Record<string, string>;
  latest?: Record<string, number>;
}

export interface Thread {
  id: string;
  title: string;
  content: string;
  status: string;
  pinned: boolean;
  created_at: string;
}

export interface Schedule {
  id: string;
  title: string;
  schedule_type: string;
  prompt: string;
  enabled: boolean;
  last_run: string | null;
  run_count: number;
}
