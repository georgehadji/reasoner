import { fetchWithCsrf } from './security-client';
import { API, LIMITS } from './config';
import { GateResponse } from './types';

const _widgetCache = new Map<string, { data: unknown; expiry: number }>();
const WIDGET_TTL_MS = 30_000;

function withWidgetCache<T>(fn: (...args: string[]) => Promise<T>, keyFn: (...args: string[]) => string) {
  return async (...args: string[]): Promise<T> => {
    const key = keyFn(...args);
    const cached = _widgetCache.get(key);
    if (cached && cached.expiry > Date.now()) {
      return cached.data as T;
    }
    const data = await fn(...args);
    _widgetCache.set(key, { data, expiry: Date.now() + WIDGET_TTL_MS });
    return data;
  };
}

export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  return fetchWithCsrf(path, options);
}

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const resp = await fetchWithCsrf(url, options);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json() as Promise<T>;
}

/** Ask HyperGate which method it would pick, without running the pipeline. */
export async function fetchGateDecision(problem: string, preset: string): Promise<GateResponse> {
  return fetchJSON<GateResponse>(API.GATE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problem, preset }),
  });
}

function formatApiError(status: number, data: unknown): string {
  if (data && typeof data === 'object') {
    const payload = data as Record<string, unknown>;
    const detail = payload.detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => {
          if (!item || typeof item !== 'object') return null;
          const err = item as Record<string, unknown>;
          const loc = Array.isArray(err.loc)
            ? err.loc.filter((part) => part !== 'body').join('.')
            : '';
          const msg = typeof err.msg === 'string' ? err.msg : 'Invalid request';
          return loc ? `${loc}: ${msg}` : msg;
        })
        .filter(Boolean);
      if (messages.length > 0) {
        return `HTTP ${status}: ${messages.join('; ')}`;
      }
    }
    if (typeof detail === 'string') {
      return `HTTP ${status}: ${detail}`;
    }
    if (typeof payload.error === 'string') {
      return `HTTP ${status}: ${payload.error}`;
    }
  }
  return `HTTP ${status}`;
}

export async function clearCache() {
  const resp = await fetchWithCsrf(API.CACHE, { method: 'DELETE' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
}

export async function stopPipeline() {
  await fetchWithCsrf(API.STOP, { method: 'POST' }).catch(() => {});
}

export async function fetchPresets() {
  return fetchJSON(API.PRESETS);
}

async function _fetchWeather(location: string) {
  return fetchJSON(`${API.WEATHER}?location=${encodeURIComponent(location)}`);
}
export const fetchWeather = withWidgetCache(_fetchWeather, (city: string) => `weather:${city}`);

async function _fetchStocks(symbol: string) {
  return fetchJSON(`${API.STOCKS}?symbol=${encodeURIComponent(symbol)}`);
}
export const fetchStocks = withWidgetCache(_fetchStocks, (symbol: string) => `stocks:${symbol}`);

async function _calculate(expression: string) {
  return fetchJSON(API.CALCULATE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ expression }),
  });
}
export const calculate = withWidgetCache(_calculate, (expr: string) => `calc:${expr}`);

export async function resumePipelineStream(pipelineId: string) {
  const resp = await fetchWithCsrf(API.PIPELINE_RESUME(pipelineId), {
    method: 'POST',
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  if (!resp.body) throw new Error('No response body');
  return resp.body;
}

export async function neuroSessions(agent_id?: string, limit = LIMITS.neuroSessionsLimit, offset = 0) {
  const params = new URLSearchParams();
  if (agent_id) params.set('agent_id', agent_id);
  params.set('limit', String(limit));
  params.set('offset', String(offset));
  return fetchJSON<{
    entries: Array<{
      timestamp: string;
      prompt_preview: string;
      response_preview: string;
      session_id: string;
    }>;
    total: number;
  }>(`${API.NEURO_SESSIONS}?${params}`);
}

export async function neuroRecall(query: string, agent_id?: string) {
  return fetchJSON<{ chunks: Array<{ content: string; source: string; relevance: number }>; total_found: number }>(API.NEURO_RECALL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: query, agent_id, max_results: LIMITS.neuroRecallMaxResults }),
  });
}

export async function neuroLearn(prompt: string, response: string, agent_id?: string) {
  return fetchJSON<{ status: string; session_id: string }>(API.NEURO_LEARN, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, response, agent_id }),
  });
}

export async function searchWeb(query: string, sourceType = 'general', numResults = 10, smart = false) {
  return fetchJSON<{ query: string; source_type: string; results: Array<{ title: string; url: string; snippet?: string; content?: string; source?: string; group?: string }> }>(API.SEARCH, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, source_type: sourceType, num_results: numResults || LIMITS.webSearchNumResults, smart }),
  });
}

export interface UploadResult {
  success: boolean;
  file_id?: string;
  filename?: string;
  size?: number;
  mime_type?: string;
  text?: string;
  path?: string;
  error?: string;
}

export async function uploadFiles(files: File[]): Promise<{ success: boolean; files: UploadResult[]; error?: string }> {
  const formData = new FormData();
  files.forEach((file) => formData.append('file', file));

  const resp = await fetchWithCsrf(API.UPLOAD, {
    method: 'POST',
    body: formData,
  });

  const data = await resp.json();
  if (!resp.ok || !data.success) {
    const msg = data.error || `HTTP ${resp.status}`;
    throw new Error(msg);
  }

  return data;
}

export interface GenerateImageResult {
  success: boolean;
  images?: Array<{ image_data: string; model_used: string }>;
  enhanced_prompt?: string;
  rewritten_prompt?: string;
  error?: string;
}

export async function generateImageEnhancement(prompt: string, preset: 'budget' | 'premium' = 'budget'): Promise<GenerateImageResult> {
  const resp = await fetchWithCsrf(API.GENERATE_IMAGE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, preset: `image-gen-${preset}`, preview_only: true, enhance: true }),
  });
  const data = await resp.json();
  if (!resp.ok || !data.success) {
    return { success: false, error: formatApiError(resp.status, data) };
  }
  return data;
}

export async function generateImage(
  prompt: string,
  preset: 'budget' | 'premium' = 'budget',
  enhance = true,
  referenceImages: string[] = [],
  numImages?: number,
): Promise<GenerateImageResult> {
  const body: Record<string, unknown> = { prompt, preset: `image-gen-${preset}`, enhance, reference_images: referenceImages };
  if (numImages !== undefined) body.num_images = numImages;
  const resp = await fetchWithCsrf('/api/generate-image', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await resp.json();
  if (!resp.ok || !data.success) {
    return { success: false, error: formatApiError(resp.status, data) };
  }
  return data;
}

export async function deleteAccount(): Promise<{ status: string; user_id?: string; deleted?: Record<string, unknown> }> {
  const resp = await fetchWithCsrf(API.ACCOUNT_DELETE, { method: 'POST' });
  const data = await resp.json();
  if (!resp.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : (typeof data.error === 'string' ? data.error : `HTTP ${resp.status}`);
    throw new Error(detail);
  }
  return data;
}

export async function submitFeedback(payload: {
  conversation_id: string;
  message_id: string;
  rating: 'up' | 'down';
  reason?: 'incorrect' | 'outdated' | 'off_topic' | 'too_verbose' | 'unsafe' | 'other';
  comment?: string;
  context?: Record<string, unknown>;
}) {
  return fetchJSON<{ status: string }>(API.FEEDBACK, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
