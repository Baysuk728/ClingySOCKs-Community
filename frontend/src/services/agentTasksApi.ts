/**
 * Agent Tasks API — Service layer for agent task management.
 */

import { getApiUrlSync } from './apiConfig';

const API_URL = getApiUrlSync();
const API_KEY = import.meta.env.VITE_MEMORY_API_KEY || '';

const getHeaders = () => ({
    'Content-Type': 'application/json',
    ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
});

// ── Types ──

export interface AgentTask {
    id: string;
    entity_id: string;
    goal: string;
    status: 'pending' | 'planning' | 'running' | 'completed' | 'failed' | 'cancelled';
    task_type: string;
    priority: number;
    source: string;
    current_step: number;
    max_steps: number;
    result?: string;
    error?: string;
    model_used?: string;
    total_tokens?: number;
    plan?: string[];
    steps_log?: StepLog[];
    created_at?: string;
    started_at?: string;
    completed_at?: string;
}

export interface StepLog {
    step: number;
    type: 'tool_call' | 'response' | 'error' | 'reflection';
    tools?: { name: string; args: Record<string, any> }[];
    observations?: string[];
    thought?: string;
    content?: string;
    error?: string;
    reflection?: string;
    is_done?: boolean;
    timestamp?: string;
}

export interface CreateTaskPayload {
    goal: string;
    task_type?: string;
    priority?: number;
    source?: string;
    max_steps?: number;
    push_telegram?: boolean;
    push_websocket?: boolean;
    metadata?: Record<string, any>;
    async_exec?: boolean;
}

export interface HeartbeatConfig {
    entity_id: string;
    enabled: boolean;
    interval_seconds: number;
    quiet_hours_start: string;
    quiet_hours_end: string;
    min_idle_gap_seconds: number;
    cooldown_seconds: number;
    max_autonomous_per_day: number;
    last_heartbeat_at?: string;
    last_action_at?: string;
    actions_today: number;
}

// ── API Functions ──

export async function createTask(entityId: string, payload: CreateTaskPayload): Promise<AgentTask> {
    const res = await fetch(`${API_URL}/agent/task/${entityId}`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`Failed to create task: ${res.status} ${await res.text()}`);
    return res.json();
}

export async function getTaskStatus(taskId: string): Promise<AgentTask> {
    const res = await fetch(`${API_URL}/agent/task/${taskId}/status`, {
        headers: getHeaders(),
    });
    if (!res.ok) throw new Error(`Failed to get task: ${res.status}`);
    return res.json();
}

export async function listTasks(
    entityId: string,
    options?: { status?: string; limit?: number; offset?: number }
): Promise<AgentTask[]> {
    const params = new URLSearchParams();
    if (options?.status) params.set('status', options.status);
    if (options?.limit) params.set('limit', String(options.limit));
    if (options?.offset) params.set('offset', String(options.offset));

    const res = await fetch(`${API_URL}/agent/tasks/${entityId}?${params}`, {
        headers: getHeaders(),
    });
    if (!res.ok) throw new Error(`Failed to list tasks: ${res.status}`);
    const data = await res.json();
    return data.tasks || [];
}

export async function cancelTask(taskId: string): Promise<AgentTask> {
    const res = await fetch(`${API_URL}/agent/task/${taskId}/cancel`, {
        method: 'POST',
        headers: getHeaders(),
    });
    if (!res.ok) throw new Error(`Failed to cancel task: ${res.status}`);
    return res.json();
}

export async function triggerHeartbeat(entityId: string): Promise<any> {
    const res = await fetch(`${API_URL}/agent/heartbeat/${entityId}`, {
        method: 'POST',
        headers: getHeaders(),
    });
    if (!res.ok) throw new Error(`Failed to trigger heartbeat: ${res.status}`);
    return res.json();
}

export async function getHeartbeatConfig(entityId: string): Promise<HeartbeatConfig> {
    const res = await fetch(`${API_URL}/agent/heartbeat/${entityId}/config`, {
        headers: getHeaders(),
    });
    if (!res.ok) throw new Error(`Failed to get heartbeat config: ${res.status}`);
    return res.json();
}

export async function updateHeartbeatConfig(
    entityId: string,
    config: Partial<HeartbeatConfig>
): Promise<HeartbeatConfig> {
    const res = await fetch(`${API_URL}/agent/heartbeat/${entityId}/config`, {
        method: 'PUT',
        headers: getHeaders(),
        body: JSON.stringify(config),
    });
    if (!res.ok) throw new Error(`Failed to update heartbeat config: ${res.status}`);
    return res.json();
}
