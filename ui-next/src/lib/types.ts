export type MethodId =
  | 'multi-perspective'
  | 'debate'
  | 'scientific'
  | 'socratic'
  | 'research'
  | 'jury'
  | 'pre-mortem'
  | 'bayesian'
  | 'dialectical'
  | 'analogical'
  | 'delphi'
  | 'cove'
  | 'sot'
  | 'tot'
  | 'pot'
  | 'self-discover'
  | 'writing'
  | 'brainstorming';

export interface TokenCount {
  input: number;
  output: number;
  total: number;
}

export interface PhaseEvent {
  type: 'start' | 'prompt_enhanced' | 'phase_start' | 'phase_complete' | 'phase_quality' | 'phase_retry' | 'phase_error' | 'error' | 'cancelled' | 'done' | 'agent_start' | 'agent_complete' | 'text_chunk' | 'widget' | 'recall_used' | 'research_step_emitted' | 'research_citations_ready' | 'method_selected';
  /** phase_quality fields */
  score?: number;
  passed?: boolean;
  reason?: string;
  attempt?: number;
  /** phase_retry fields */
  max_attempts?: number;
  phase?: number;
  name?: string;
  data?: Record<string, unknown>;
  cached?: boolean;
  errors?: string[];
  total_tokens?: TokenCount;
  duration?: number;
  message?: string;
  original?: string;
  enhanced?: string;
  /** Populated on `type === 'start'` when the backend auto-selected a method. */
  auto_selected_method?: string;
  /** Agent activity tracking */
  agent?: string;
  role?: string;
  task?: string;
  model?: string;
  models?: string[];
  error?: string | null;
  /** Streaming text chunk */
  text?: string;
  /** Structured error fields */
  error_type?: string;
  retryable?: boolean;
  retry_after?: number;
  /** Cost transparency fields on done event */
  total_cost_usd?: number;
  phase_costs?: Record<string, number>;
  /** Memory recall fields */
  memory_count?: number;
  memory_ids?: string[];
  /** Prism research step fields */
  step_type?: string;
  queries?: string[];
  plan?: string;
  urls?: string[];
  citation_count?: number;
  source_types?: string[];
  /** `method_selected` fields — HyperGate's routing decision, emitted once per run. */
  action?: 'direct' | 'pipeline' | 'web_search';
  method?: string;
  confidence?: number;
  reasoning?: string;
  alternatives?: MethodAlternative[] | null;
}

/** A runner-up method HyperGate considered but did not pick. */
export interface MethodAlternative {
  method: string;
  confidence: number;
  rationale: string;
}

export interface Attachment {
  id: string;
  name: string;
  size: number;
  type: string;
  previewUrl?: string;
  extractedText?: string;
}

export interface ResearchStepEvent {
  step_type: 'searching' | 'reasoning' | 'reading';
  queries: string[];
  plan: string;
  urls: string[];
}

export interface Citation {
  url: string;
  title: string;
  snippet: string;
  source_type: 'web' | 'academic' | 'discussion' | 'file' | 'scraped';
}

export interface ConversationTurn {
  role: 'user' | 'assistant';
  content: string;
  attachments?: Attachment[];
}

export interface WidgetData {
  widget_type: string;
  name: string;
  result: Record<string, unknown>;
  citations?: string[];
}

export interface Conversation {
  id: string;
  conversation_id: string;
  turn_number: number;
  timestamp: string;
  problem: string;
  phases: Array<{ phase: number; name: string; data: unknown }>;
  errors: string[];
  preset: string;
  method: string;
  total_tokens: TokenCount | null;
  duration?: number;
  kind?: 'pipeline' | 'search' | 'image';
  response_content?: string;
  images?: Array<{ data: string; model?: string }>;
  widgets?: WidgetData[];
  prompt_meta?: { original?: string; enhanced?: string };
  /** Pipeline aggregate ID for resume functionality */
  pipeline_id?: string;
}

export interface AttachmentRef {
  file_id: string;
  filename: string;
  mime_type: string;
  extracted_text: string;
  size: number;
}

export interface RunRequest {
  problem: string;
  preset: string;
  top_k: number;
  sequential: boolean;
  enhance_prompt: boolean;
  expert?: boolean;
  web_search?: boolean;
  smart_search?: boolean;
  attachments?: AttachmentRef[];
  file_ids?: string[];
  client_run_id?: string;
  /** Skip HyperGate re-classification — used when the client already resolved
   *  a specific preset via /api/gate (user confirmed or accepted a method). */
  force_pipeline?: boolean;
}

/** Response shape of POST /api/gate. */
export interface GateResponse {
  action: 'direct' | 'pipeline' | 'web_search';
  method: string | null;
  preset: string | null;
  confidence: number;
  reasoning: string | null;
  complexity: string | null;
  alternatives: (MethodAlternative & { preset: string | null })[];
  needs_confirmation: boolean;
}

export interface RunFollowupRequest {
  question: string;
  preset: string;
  top_k: number;
  sequential: boolean;
  enhance_prompt: boolean;
  expert?: boolean;
  web_search?: boolean;
  smart_search?: boolean;
  client_run_id?: string;
  conversation_id: string;
  history: ConversationTurn[];
  previous_synthesis: string;
  agent_model?: string | null;
  attachments?: AttachmentRef[];
  file_ids?: string[];
}

export interface PresetMeta {
  available: boolean;
  missing_keys?: string[];
}

export interface PresetsResponse {
  presets: Record<string, PresetMeta>;
  models: Record<string, unknown>;
}

export interface MethodPreset {
  id: string;
  label: string;
}

export interface MethodPhase {
  id: number;
  name: string;
  short: string;
}

export interface MethodDef {
  id: MethodId;
  name: string;
  icon: string;
  cost: number;
  description: string;
}
