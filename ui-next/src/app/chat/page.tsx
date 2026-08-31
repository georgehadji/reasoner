'use client';

import { useState, useRef, useCallback, useReducer, useMemo, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useTheme } from 'next-themes';
import { useAppStore } from '@/stores/app-store';

import { usePipelineStream } from '@/hooks/usePipelineStream';
import { useWebSocketPipeline } from '@/hooks/useWebSocketPipeline';
import { useServerStatus } from '@/hooks/useServerStatus';
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts';
import { useConversationHistory } from '@/hooks/useConversationHistory';
import { useScrollAnchor } from '@/hooks/useScrollAnchor';
import { Sidebar } from '@/components/layout/Sidebar';
import { Composer } from '@/components/layout/Composer';
import { ShortcutModal } from '@/components/layout/ShortcutModal';
import { CommandPalette } from '@/components/layout/CommandPalette';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { Tooltip } from '@/components/ui/Tooltip';
import { PhaseTimeline } from '@/components/layout/PhaseTimeline';
import { UserMenu } from '@/components/layout/UserMenu';
import { UpgradeModal } from '@/components/layout/UpgradeModal';
import { SecurityBadge } from '@/components/layout/SecurityBadge';
import { PipelineError } from '@/hooks/usePipelineStream';

import { ChatFeed, ChatFeedMessage, RenderedPhase } from '@/components/chat/ChatFeed';
import { ChatErrorBoundary } from '@/components/chat/ChatErrorBoundary';
import { PipelineSkeleton } from '@/components/chat/PipelineSkeleton';
import { PhaseEvent, Conversation, RunFollowupRequest, ConversationTurn, GateResponse } from '@/lib/types';
import { METHOD_PHASES, METHOD_DESCRIPTIONS, LIMITS, PIPELINE_DEFAULTS } from '@/lib/config';
import { buildMarkdownFromPhases } from '@/lib/markdown';
import { saveConversation } from '@/lib/db';
import { conversationToMessages } from '@/lib/conversation-history';
import { readSSEStream } from '@/lib/sse-reader';
import { clearCache, uploadFiles, generateImage, generateImageEnhancement, resumePipelineStream, submitFeedback, fetchGateDecision } from '@/lib/api-client';
import { MethodChoicePrompt, MethodChoiceLoading } from '@/components/chat/MethodChoicePrompt';

// --- Reducer function for managing messages state ---
type MessagesAction =
  | { type: 'ADD_MESSAGES'; payload: ChatFeedMessage[] }
  | { type: 'UPDATE_MESSAGE'; payload: { messageId: string; updates: Partial<ChatFeedMessage> } }
  | { type: 'SET_MESSAGES'; payload: ChatFeedMessage[] }
  | { type: 'ADD_STREAMING_CONTENT'; payload: { messageId: string; text: string } }
  | { type: 'UPDATE_PHASE_DATA'; payload: { messageId: string; phaseIndex: number; data: unknown } }
  | { type: 'UPDATE_PHASE_MODELS'; payload: { messageId: string; phaseIndex: number; models: string[] | undefined } }
  | { type: 'APPEND_WIDGET'; payload: { messageId: string; widget: { widget_type: string; name: string; result: Record<string, unknown>; citations?: string[] } } }
  | { type: 'ADD_ACTIVE_AGENT'; payload: { messageId: string; agent: { name: string; task: string } } }
  | { type: 'REMOVE_ACTIVE_AGENT'; payload: { messageId: string; agentName: string } }
  | { type: 'SET_CURRENT_PHASE'; payload: { phase?: number; phaseName?: string } }
  | { type: 'SET_COMPLETED_PHASES'; payload: number[] }
  | { type: 'SET_ERROR_PHASES'; payload: number[] }
  | { type: 'SET_PHASE_DURATIONS'; payload: Record<number, number> }
  | { type: 'SET_IS_STREAMING'; payload: boolean }
  | { type: 'CLEAR_MESSAGES' }
  | { type: 'RESET_STATE' };

function messagesReducer(state: ChatFeedMessage[], action: MessagesAction): ChatFeedMessage[] {
  switch (action.type) {
    case 'ADD_MESSAGES':
      return [...state, ...action.payload];
    case 'UPDATE_MESSAGE': {
      const { messageId, updates } = action.payload;
      return state.map(msg =>
        msg.id === messageId ? { ...msg, ...updates } : msg
      );
    }
    case 'SET_MESSAGES':
      return action.payload;
    case 'ADD_STREAMING_CONTENT': {
      const { messageId, text } = action.payload;
      return state.map(msg =>
        msg.id === messageId ? { ...msg, streamingContent: (msg.streamingContent || '') + text } : msg
      );
    }
    case 'UPDATE_PHASE_DATA': {
      const { messageId, phaseIndex, data } = action.payload;
      return state.map(msg => {
        if (msg.id === messageId && msg.phases) {
          const phase = msg.phases[phaseIndex];
          if (phase) {
            const updatedPhase = { ...phase, data };
            const updatedPhases = [...msg.phases];
            updatedPhases[phaseIndex] = updatedPhase;
            return { ...msg, phases: updatedPhases };
          }
        }
        return msg;
      });
    }
    case 'UPDATE_PHASE_MODELS': {
      const { messageId, models } = action.payload;
      return state.map(msg =>
        msg.id === messageId ? { ...msg, phaseModels: models } : msg
      );
    }
    case 'APPEND_WIDGET': {
      const { messageId, widget } = action.payload;
      return state.map(msg =>
        msg.id === messageId ? { ...msg, widgets: [...(msg.widgets || []), widget] } : msg
      );
    }
    case 'ADD_ACTIVE_AGENT': {
      const { messageId, agent } = action.payload;
      return state.map(msg => {
        if (msg.id === messageId) {
          const currentAgents = msg.activeAgents || [];
          if (!currentAgents.find(a => a.name === agent.name)) {
            return { ...msg, activeAgents: [...currentAgents, agent] };
          }
        }
        return msg;
      });
    }
    case 'REMOVE_ACTIVE_AGENT': {
      const { messageId, agentName } = action.payload;
      return state.map(msg => {
        if (msg.id === messageId && msg.activeAgents) {
          return { ...msg, activeAgents: msg.activeAgents.filter(a => a.name !== agentName) };
        }
        return msg;
      });
    }
    case 'SET_CURRENT_PHASE': {
      // This action is primarily managed by the parent component's state,
      // but we can update the message if it represents the active streaming state.
      // The actual state update is in the parent component.
      // For simplicity here, we assume the parent updates its local state.
      // If this reducer were to manage phase state directly, it would need more logic.
      return state; // No direct state change in messages array for current phase number itself.
    }
    case 'SET_COMPLETED_PHASES': {
      // This action is also managed by the parent component's state.
      return state;
    }
    case 'SET_ERROR_PHASES': {
      // This action is also managed by the parent component's state.
      return state;
    }
    case 'SET_PHASE_DURATIONS': {
      // This action is also managed by the parent component's state.
      return state;
    }
    case 'SET_IS_STREAMING': {
      // This action is also managed by the parent component's state.
      return state;
    }
    case 'CLEAR_MESSAGES':
      return [];
    case 'RESET_STATE':
      return []; // Resetting messages to empty array
    default:
      return state;
  }
}

/** Resolve METHOD_PHASES by normalizing method name and falling back to multi-perspective. */
function getMethodPhases(method: string) {
  const normalized = method.replace(/_/g, '-');
  return METHOD_PHASES[normalized] || METHOD_PHASES['multi-perspective'] || [];
}

const IMAGE_PROMPT_MAX_CHARS = LIMITS.imagePromptMaxChars;

/** Strip model-name prefixes like "DALL-E 3, Midjourney, Flux prompt:" or "**DALL-E 3, Midjourney, Flux Prompt:**" from enhanced prompts for display. */
function cleanDisplayPrompt(prompt: string): string {
  return prompt.replace(/^(?:\*{2})?[\w\s,'-]+prompt:\*{0,2}\s+/i, '');
}

const CONTINUATION_RE = /\b(continue|cont\.?|keep going|more|expand|elaborate|extend|add more|next (step|section|part)|again|revise|rewrite|improve|same topic|build on|follow up)\b/i;

function clampImagePrompt(prompt: string) {
  const trimmed = prompt.trim();
  if (trimmed.length <= IMAGE_PROMPT_MAX_CHARS) {
    return { prompt: trimmed, truncated: false };
  }
  return { prompt: trimmed.slice(0, IMAGE_PROMPT_MAX_CHARS), truncated: true };
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        resolve(reader.result);
        return;
      }
      reject(new Error(`Failed to read ${file.name}`));
    };
    reader.onerror = () => reject(reader.error || new Error(`Failed to read ${file.name}`));
    reader.readAsDataURL(file);
  });
}

export default function ChatPage() {
  const router = useRouter();
  const user = useAppStore((s) => s.user);
  const running = useAppStore((s) => s.running);
  const setRunning = useAppStore((s) => s.setRunning);
  const composerText = useAppStore((s) => s.composerText);
  const setComposerText = useAppStore((s) => s.setComposerText);
  const attachments = useAppStore((s) => s.attachments);
  const clearAttachments = useAppStore((s) => s.clearAttachments);
  const isImageMode = useAppStore((s) => s.isImageMode);
  const tier = useAppStore((s) => s.tier);
  const getAutoPreset = useAppStore((s) => s.getAutoPreset);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const toggleNeuroPanel = useAppStore((s) => s.toggleNeuroPanel);
  const toggleTier = useAppStore((s) => s.toggleTier);
  const recentCommands = useAppStore((s) => s.recentCommands);
  const addRecentCommand = useAppStore((s) => s.addRecentCommand);
  const collapsed = useAppStore((s) => s.sidebarCollapsed);
  const autoMethodAlways = useAppStore((s) => s.autoMethodAlways);
  const toggleAutoMethodAlways = useAppStore((s) => s.toggleAutoMethodAlways);

  const { history, refresh: refreshHistory, remove: removeHistory } = useConversationHistory();
  const { startRun, startFollowup, stopRun } = usePipelineStream();
  const { connect: wsConnect, disconnect: wsDisconnect, sendStop: wsSendStop, status: wsStatus, lastError: wsLastError } = useWebSocketPipeline();
  const serverOnline = useServerStatus();
  const { resolvedTheme, setTheme } = useTheme();
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  // REFACTOR: Replace useState with useReducer for messages state
  const [messages, dispatchMessages] = useReducer(messagesReducer, []);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  // `conversationIdRef` is the source of truth read from async SSE/event
  // callbacks (handleFeedback, onEvent, ...): those closures need the latest
  // value the instant it changes, without waiting for a re-render, so a ref
  // is correct there. `conversationId` mirrors it purely for render — refs
  // must never be read during render (`react-hooks/refs`) — and is updated
  // at every site that writes the ref, right below each write.
  const conversationIdRef = useRef<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const clientRunIdRef = useRef<string | null>(null);

  // Auto-selected method from HyperGate — populated from the 'start' SSE event.
  const [autoSelectedMethod, setAutoSelectedMethod] = useState<string>(PIPELINE_DEFAULTS.method);

  const [completedPhases, setCompletedPhases] = useState<number[]>([]);
  const [errorPhases, setErrorPhases] = useState<number[]>([]);
  const [currentPhase, setCurrentPhase] = useState<number | undefined>(undefined);
  const [phaseDurations, setPhaseDurations] = useState<Record<number, number>>({});
  const [phaseOpenMode, setPhaseOpenMode] = useState<'auto' | 'expand' | 'collapse'>('auto');

  // HyperGate method-confirmation gate — set while /api/gate is in flight,
  // and when it returns a low-confidence decision needing user input.
  const [gateChecking, setGateChecking] = useState(false);
  const [pendingChoice, setPendingChoice] = useState<{ problem: string; decision: GateResponse } | null>(null);
  const phaseStartTimesRef = useRef<Record<number, number>>({});
  const chunkBufferRef = useRef('');
  const chunkFlushRafRef = useRef<number | null>(null);

  // Cleanup RAF timer on unmount to prevent dispatching to a dismounted reducer
  useEffect(() => {
    return () => {
      if (chunkFlushRafRef.current !== null) {
        cancelAnimationFrame(chunkFlushRafRef.current);
        chunkFlushRafRef.current = null;
      }
    };
  }, []);

  const isContinuation = (text: string) => CONTINUATION_RE.test(text);

  const findLastAssistant = (msgs: ChatFeedMessage[]) => {
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'assistant' && !msgs[i].isStreaming) return msgs[i];
    }
    return undefined;
  };

  const {
    scrollToBottom,
    showNewContentIndicator,
    dismissIndicator,
  } = useScrollAnchor(scrollContainerRef);

  useKeyboardShortcuts({
    onToggleSidebar: toggleSidebar,
    onShowShortcuts: () => setShortcutsOpen(true),
    onStop: () => {
      if (running) {
        stopRun();
        wsSendStop(clientRunIdRef.current || '');
      }
      setRunning(false);
    },
    onClearComposer: () => setComposerText(''),
    onFocusComposer: () => {
      const textarea = document.querySelector('textarea');
      textarea?.focus();
    },
    onCopyLastResponse: () => {
      const last = messages.filter((m) => m.role === 'assistant' && !m.isStreaming).at(-1);
      if (last?.content) navigator.clipboard.writeText(last.content);
    },
    onCommandPalette: () => setCommandPaletteOpen((v) => !v),
  });

  const handleSubmit = useCallback(async (
    providedText?: string,
    opts?: { presetOverride?: string; skipGate?: boolean },
  ) => {
    const problem = (providedText ?? composerText).trim();
    if (!problem || running) return;

    // ── HyperGate confirmation gate ──
    // Ask HyperGate which method it would pick BEFORE running anything. If it's
    // confident, proceed silently (today's UX). If it's not, pause here and let
    // the user confirm or pick a runner-up — skipped for image mode, follow-ups
    // (which don't go through HyperGate at all), and once the user opts out via
    // "always pick automatically".
    if (!opts?.skipGate && !isImageMode && !autoMethodAlways) {
      const lastAssistantMsgForGate = findLastAssistant(messages);
      const isFollowupForGate = !!lastAssistantMsgForGate && messages.length > 0 && isContinuation(problem);
      if (!isFollowupForGate) {
        setGateChecking(true);
        try {
          const gateResult = await fetchGateDecision(problem, getAutoPreset());
          setGateChecking(false);
          if (gateResult.needs_confirmation && gateResult.preset) {
            setPendingChoice({ problem, decision: gateResult });
            return;
          }
        } catch (err) {
          // Fail open — HyperGate confirmation is a UX nicety, not a gate on
          // being able to submit at all.
          console.error('Gate check failed, proceeding with auto-routing:', err);
          setGateChecking(false);
        }
      }
    }
    setPendingChoice(null);

    setComposerText('');
    setRunning(true);
    // Resetting state that's managed by the parent component's state, not in the reducer
    setCompletedPhases([]);
    setErrorPhases([]);
    setCurrentPhase(undefined);
    setPhaseDurations({});
    setAutoSelectedMethod(PIPELINE_DEFAULTS.method);
    setPhaseOpenMode('auto');
    phaseStartTimesRef.current = {};
    chunkBufferRef.current = '';
    if (chunkFlushRafRef.current !== null) {
      cancelAnimationFrame(chunkFlushRafRef.current);
      chunkFlushRafRef.current = null;
    }

    // Upload attachments before running
    let uploadedAttachments: { file_id: string; filename: string; mime_type: string; extracted_text: string; size: number }[] = [];
    if (attachments.length > 0 && !isImageMode) {
      try {
        const uploadResult = await uploadFiles(attachments.map((a) => a.file));
        uploadedAttachments = (uploadResult.files || [])
          .filter((f) => f.success && f.file_id)
          .map((f) => ({
            file_id: f.file_id!,
            filename: f.filename!,
            mime_type: f.mime_type || 'application/octet-stream',
            extracted_text: f.text || '',
            size: f.size || 0,
          }));
      } catch (err) {
        console.error('Attachment upload failed:', err);
      }
    }

    const userMsg: ChatFeedMessage = {
      id: 'u-' + Date.now(),
      role: 'user',
      content: problem,
      attachments: attachments.length > 0
        ? attachments.map((a) => ({
            id: a.id,
            name: a.name,
            size: a.size,
            type: a.type,
            previewUrl: a.previewUrl,
          }))
        : undefined,
    };
    const assistantId = 'a-' + Date.now();
    const assistantMsg: ChatFeedMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      phases: [],
      isStreaming: true,
      currentPhaseName: undefined,
      loadingKind: undefined,
      loadingPrompt: undefined,
    };
    // Dispatch action to add user message and initial assistant message
    dispatchMessages({ type: 'ADD_MESSAGES', payload: isImageMode ? [userMsg] : [userMsg, assistantMsg] });

    // ── Image Generation mode ──
    if (isImageMode) {
      const genStart = performance.now();
      try {
        const basePrompt = clampImagePrompt(problem);
        if (basePrompt.truncated) {
          dispatchMessages({
            type: 'ADD_MESSAGES',
            payload: [{
              id: 'info-trim-' + Date.now(),
              role: 'info',
              content: `Prompt truncated to ${IMAGE_PROMPT_MAX_CHARS} characters to fit image limits.`,
            }],
          });
        }
        const referenceImages = await Promise.all(
          attachments
            .filter((attachment) => attachment.type.startsWith('image/'))
            .slice(0, LIMITS.maxReferenceImages)
            .map((attachment) => fileToDataUrl(attachment.file)),
        );
        const enhancement = await generateImageEnhancement(basePrompt.prompt, tier);
        if (!enhancement.success) {
          throw new Error(enhancement.error || 'Image prompt enhancement failed');
        }
        const enhancedBase = clampImagePrompt(enhancement.enhanced_prompt || basePrompt.prompt);
        if (enhancedBase.truncated) {
          dispatchMessages({
            type: 'ADD_MESSAGES',
            payload: [{
              id: 'info-trim-enhanced-' + Date.now(),
              role: 'info',
              content: `Enhanced prompt truncated to ${IMAGE_PROMPT_MAX_CHARS} characters to fit image limits.`,
            }],
          });
        }
        const enhancedPrompt = enhancedBase.prompt;
        const displayPrompt = cleanDisplayPrompt(enhancedPrompt);
        dispatchMessages({
          type: 'ADD_MESSAGES',
          payload: [
            {
              id: 'info-enhanced-img-' + Date.now(),
              role: 'info',
              content:
                enhancedPrompt === basePrompt.prompt
                  ? `Prompt used for generation: “${displayPrompt}”`
                  : `Enhanced prompt: “${displayPrompt}”`,
              meta: enhancedPrompt === basePrompt.prompt ? undefined : { original: basePrompt.prompt, enhanced: displayPrompt },
            },
            {
              ...assistantMsg,
              loadingKind: 'image-generation',
              loadingPrompt:
                referenceImages.length > 0
                  ? `${displayPrompt} [using ${referenceImages.length} reference image${referenceImages.length === 1 ? '' : 's'}]`
                  : displayPrompt,
            },
          ],
        });

        const result = await generateImage(enhancedPrompt, tier, false, referenceImages, tier === 'budget' ? 4 : undefined);
        const genDuration = (performance.now() - genStart) / 1000;
        if (result.success && result.images && result.images.length > 0) {
          const formattedImages =
            result.images?.map((img) => ({
              data: img.image_data,
              model: img.model_used,
            })) || [];
          // Update assistant message with generated images
          dispatchMessages({ type: 'UPDATE_MESSAGE', payload: { messageId: assistantId, updates: {
            content:
              formattedImages.length >= 2
                ? `Generated ${formattedImages.length} images`
                : `Generated image using **${formattedImages[0]?.model || 'model'}**`,
            images: formattedImages,
            isStreaming: false,
            duration: genDuration,
            loadingKind: undefined,
            loadingPrompt: undefined,
          }}});
          await saveConversation({
            id: assistantId,
            conversation_id: assistantId,
            turn_number: 1,
            timestamp: new Date().toISOString(),
            problem,
            phases: [],
            errors: [],
            preset: tier,
            method: 'image',
            total_tokens: null,
            duration: genDuration,
            kind: 'image',
            response_content:
              formattedImages.length >= 2
                ? `Generated ${formattedImages.length} images`
                : `Generated image using **${formattedImages[0]?.model || 'model'}**`,
            images: formattedImages,
            prompt_meta: { original: problem, enhanced: enhancedPrompt },
          });
          refreshHistory();
        } else {
          // Update assistant message with generation failure
          dispatchMessages({ type: 'UPDATE_MESSAGE', payload: { messageId: assistantId, updates: {
            content: `**Image generation failed:** ${result.error || 'Unknown error'}`,
            isStreaming: false,
            loadingKind: undefined,
            loadingPrompt: undefined,
          }}});
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Image generation failed';
        // Update assistant message with error
        dispatchMessages({ type: 'UPDATE_MESSAGE', payload: { messageId: assistantId, updates: {
          content: `**Error:** ${msg}`,
          isStreaming: false,
          loadingKind: undefined,
          loadingPrompt: undefined,
        }}});
      } finally {
        setRunning(false);
        clearAttachments();
      }
      return;
    }

    // ── Detect follow-up mode ──
    const lastAssistantMsg = findLastAssistant(messages);
    const isFollowup = !!lastAssistantMsg && messages.length > 0 && isContinuation(problem);

    let phases: RenderedPhase[] = [];
    let finalErrors: string[] = [];
    let finalTokens = { input: 0, output: 0, total: 0 };
    // Track the method discovered from the 'start' event within this run
    let runMethod = PIPELINE_DEFAULTS.method;

    // Shared event handler for SSE stream processing
    const onEvent = (ev: PhaseEvent) => {
      // Dispatch actions to the reducer based on event type
      switch (ev.type) {
        case 'start':
          if (ev.auto_selected_method) {
            runMethod = ev.auto_selected_method;
            setAutoSelectedMethod(ev.auto_selected_method);
          }
          break;
        case 'method_selected':
          if (ev.action === 'pipeline' && ev.method) {
            const prettyMethod = ev.method.replace(/_/g, '-').replace(/\b\w/g, (l: string) => l.toUpperCase());
            const alts = (ev.alternatives || [])
              .map((a) => a.method.replace(/_/g, '-').replace(/\b\w/g, (l: string) => l.toUpperCase()))
              .join(', ');
            const lowConfidence = typeof ev.confidence === 'number' && ev.confidence < 0.7;
            const content = [
              `Using: ${prettyMethod}${ev.reasoning ? ` — ${ev.reasoning}` : ''}`,
              lowConfidence && alts ? `Also considered: ${alts}` : null,
            ].filter(Boolean).join(' · ');
            dispatchMessages({
              type: 'ADD_MESSAGES',
              payload: [{
                id: 'info-method-' + Date.now(),
                role: 'info',
                content,
              }],
            });
          }
          break;
        case 'prompt_enhanced':
          if (ev.enhanced) {
            dispatchMessages({
              type: 'ADD_MESSAGES',
              payload: [{
                id: 'info-enhance-' + Date.now(),
                role: 'info',
                content: `Prompt enhanced: "${ev.enhanced}"`,
                meta: { original: ev.original, enhanced: ev.enhanced },
              }],
            });
          }
          break;
        case 'phase_start':
          if (typeof ev.phase === 'number') {
            const methodPhases = getMethodPhases(runMethod);
            const displayName = ev.name || methodPhases.find((p) => p.id === ev.phase)?.name || '';
            const startModels = Array.isArray(ev.models) ? (ev.models as string[]) : undefined;
            phaseStartTimesRef.current[ev.phase] = performance.now();
            setCurrentPhase(ev.phase);
            // Update the assistant message to show current phase and models
            dispatchMessages({ type: 'UPDATE_MESSAGE', payload: { messageId: assistantId, updates: { currentPhaseName: displayName, phaseModels: startModels } } });
          }
          break;
        case 'agent_start':
          if (ev.agent) {
            dispatchMessages({ type: 'ADD_ACTIVE_AGENT', payload: { messageId: assistantId, agent: { name: ev.agent, task: ev.task || ev.agent } } });
          }
          break;
        case 'agent_complete':
          if (ev.agent) {
            dispatchMessages({ type: 'REMOVE_ACTIVE_AGENT', payload: { messageId: assistantId, agentName: ev.agent } });
          }
          break;
        case 'text_chunk':
          if (typeof ev.text === 'string') {
            chunkBufferRef.current += ev.text;
            if (chunkFlushRafRef.current === null) {
              chunkFlushRafRef.current = requestAnimationFrame(() => {
                const buffered = chunkBufferRef.current;
                chunkBufferRef.current = '';
                chunkFlushRafRef.current = null;
                if (buffered) {
                  dispatchMessages({ type: 'ADD_STREAMING_CONTENT', payload: { messageId: assistantId, text: buffered } });
                }
              });
            }
          }
          break;
        case 'research_step_emitted': {
          const step = {
            step_type: String(ev.step_type || 'reasoning'),
            queries: Array.isArray(ev.queries) ? ev.queries : [],
            plan: String(ev.plan || ''),
            urls: Array.isArray(ev.urls) ? ev.urls : [],
          };
          dispatchMessages({
            type: 'UPDATE_MESSAGE',
            payload: {
              messageId: assistantId,
              updates: {
                researchSteps: [...(messages.find((m) => m.id === assistantId)?.researchSteps || []), step],
              },
            },
          });
          break;
        }
        case 'phase_complete':
          if (typeof ev.phase === 'number') {
            const methodPhases = getMethodPhases(runMethod);
            const displayName = ev.name || methodPhases.find((p) => p.id === ev.phase)?.name || '';
            const phaseNum = ev.phase;
            const phaseData = ev.data ?? {};
            const renderedPhase: RenderedPhase = {
              index: phases.length,
              phase: phaseNum,
              name: displayName,
              data: phaseData,
            };
            phases = [...phases, renderedPhase];
            const serverDuration = typeof (phaseData as Record<string, unknown>).duration === 'number'
              ? (phaseData as Record<string, unknown>).duration as number
              : undefined;
            const durationMs = serverDuration !== undefined
              ? serverDuration * 1000
              : performance.now() - (phaseStartTimesRef.current[phaseNum] ?? performance.now());
            setPhaseDurations((prev) => ({ ...prev, [phaseNum]: durationMs / 1000 }));
            setCompletedPhases((prev) => (prev.includes(phaseNum) ? prev : [...prev, phaseNum]));
            setCurrentPhase(undefined);

            const phaseModels = (phaseData as Record<string, unknown>).models as string[] | undefined;
            
            // Update the assistant message with completed phase and markdown content
            const phaseCompleteUpdates: Partial<ChatFeedMessage> = {
              content: buildMarkdownFromPhases(phases),
              phases: [...phases],
              currentPhaseName: undefined,
            };
            if (displayName === 'Synthesis') {
              phaseCompleteUpdates.streamingContent = undefined; // Clear streaming if Synthesis completes
            }
            if (phaseModels) {
              phaseCompleteUpdates.phaseModels = phaseModels;
            }
            dispatchMessages({ type: 'UPDATE_MESSAGE', payload: { messageId: assistantId, updates: phaseCompleteUpdates } });
          }
          break;
        case 'phase_quality':
          if (typeof ev.phase === 'number' && phases.length > 0) {
            const lastPhase = phases[phases.length - 1];
            if (lastPhase && lastPhase.phase === ev.phase) {
              const updatedPhase = {
                ...lastPhase,
                data: {
                  ...(lastPhase.data as Record<string, unknown>),
                  quality: { score: ev.score, passed: ev.passed },
                },
              };
              phases = [...phases.slice(0, -1), updatedPhase];
              dispatchMessages({
                type: 'UPDATE_MESSAGE',
                payload: {
                  messageId: assistantId,
                  updates: { phases: [...phases] },
                },
              });
            }
          }
          break;
        case 'phase_retry':
          if (typeof ev.phase === 'number') {
            dispatchMessages({
              type: 'UPDATE_MESSAGE',
              payload: {
                messageId: assistantId,
                updates: {
                  currentPhaseName: `${ev.name} (retry ${ev.attempt}/${ev.max_attempts})`,
                },
              },
            });
          }
          break;
        case 'phase_error':
          if (typeof ev.phase === 'number') {
            setErrorPhases((prev) => (prev.includes(ev.phase!) ? prev : [...prev, ev.phase!]));
            setCurrentPhase(undefined);
          }
          break;
        case 'error': {
          // Flush any remaining buffered text before stopping
          if (chunkFlushRafRef.current !== null) {
            cancelAnimationFrame(chunkFlushRafRef.current);
            chunkFlushRafRef.current = null;
          }
          const errorChunk = chunkBufferRef.current;
          chunkBufferRef.current = '';
          if (errorChunk) {
            dispatchMessages({ type: 'ADD_STREAMING_CONTENT', payload: { messageId: assistantId, text: errorChunk } });
          }
          // Add an error message and stop streaming
          dispatchMessages({ type: 'UPDATE_MESSAGE', payload: { messageId: assistantId, updates: { isStreaming: false, currentPhaseName: undefined } } });
          dispatchMessages({ type: 'ADD_MESSAGES', payload: [{
            id: 'err-' + Date.now(),
            role: 'error',
            content: ev.message || 'Pipeline error',
            errorType: ev.error_type || null,
            errorRetryable: ev.retryable ?? null,
            errorRetryAfter: ev.retry_after ?? null,
          }] });
          setCurrentPhase(undefined);
          break;
        }
        case 'recall_used':
          if (ev.memory_count && ev.memory_count > 0) {
            dispatchMessages({
              type: 'UPDATE_MESSAGE',
              payload: {
                messageId: assistantId,
                updates: {
                  memoryCount: ev.memory_count,
                },
              },
            });
          }
          break;
        case 'widget':
          {
            const widgetData = {
              widget_type: (ev.data?.widget_type as string) || '',
              name: (ev.data?.name as string) || '',
              result: (ev.data?.result as Record<string, unknown>) || {},
              citations: (ev.data?.citations as string[]) || undefined,
            };
            dispatchMessages({
              type: 'APPEND_WIDGET',
              payload: {
                messageId: assistantId,
                widget: widgetData,
              },
            });
          }
          break;
        case 'cancelled': {
          if (chunkFlushRafRef.current !== null) {
            cancelAnimationFrame(chunkFlushRafRef.current);
            chunkFlushRafRef.current = null;
          }
          const cancelledChunk = chunkBufferRef.current;
          chunkBufferRef.current = '';
          if (cancelledChunk) {
            dispatchMessages({ type: 'ADD_STREAMING_CONTENT', payload: { messageId: assistantId, text: cancelledChunk } });
          }
          // Add a cancellation message
          dispatchMessages({ type: 'ADD_MESSAGES', payload: [{ id: 'info-' + Date.now(), role: 'error', content: ev.message || 'Stopped by user' }] });
          setCurrentPhase(undefined);
          break;
        }
        case 'done': {
          // Flush any remaining buffered text before final update
          if (chunkFlushRafRef.current !== null) {
            cancelAnimationFrame(chunkFlushRafRef.current);
            chunkFlushRafRef.current = null;
          }
          const doneChunk = chunkBufferRef.current;
          chunkBufferRef.current = '';
          if (doneChunk) {
            dispatchMessages({ type: 'ADD_STREAMING_CONTENT', payload: { messageId: assistantId, text: doneChunk } });
          }
          finalErrors = ev.errors || [];
          finalTokens = ev.total_tokens || { input: 0, output: 0, total: 0 };
          const totalDuration = ev.duration;
          setCurrentPhase(undefined);

          const finalContent = buildMarkdownFromPhases(phases);
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const doneUpdates: any = {
            phases: [...phases],
            isStreaming: false,
            currentPhaseName: undefined,
            tokens: finalTokens,
            streamingContent: undefined,
            duration: totalDuration,
            cost: ev.total_cost_usd,
          };
          if (finalContent) {
            doneUpdates.content = finalContent;
          }

          // Final update to assistant message, clear streaming content, set tokens and duration
          dispatchMessages({ type: 'UPDATE_MESSAGE', payload: { messageId: assistantId, updates: doneUpdates }});
          
          if (finalErrors.length > 0) {
            // Add error messages if any
            dispatchMessages({ type: 'ADD_MESSAGES', payload: finalErrors.map((err, i) => ({ id: 'err-' + Date.now() + '-' + i, role: 'error', content: err })) });
          }

          // Save conversation to DB
          const convId = conversationIdRef.current || assistantId;
          const historyTurns: ConversationTurn[] = messages
            .filter((m): m is ChatFeedMessage & { role: 'user' | 'assistant' } => m.role === 'user' || m.role === 'assistant')
            .map((m) => ({ role: m.role, content: m.content || '' }));
          const turnNumber = Math.max(1, (historyTurns.length / 2) + 1);

          const conv: Conversation = {
            id: assistantId,
            conversation_id: convId,
            turn_number: Math.floor(turnNumber),
            timestamp: new Date().toISOString(),
            problem,
            phases: phases.map((p) => ({ phase: p.phase, name: p.name, data: p.data })),
            errors: finalErrors,
            preset: getAutoPreset(),
            method: runMethod,
            total_tokens: finalTokens,
            duration: totalDuration,
            kind: 'pipeline',
            response_content: buildMarkdownFromPhases(phases),
            pipeline_id: clientRunIdRef.current || undefined,
          };
          saveConversation(conv).then(refreshHistory).catch(console.error);
          break;
        }
      }
    };

    // Generate a client-side run ID so WebSocket can subscribe to the same pipeline
    const clientRunId = 'run-' + (crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`);
    clientRunIdRef.current = clientRunId;

    try {
      const state = useAppStore.getState();
      // Connect WebSocket for control (stop) and status only.
      // Phase events come exclusively via SSE to avoid double-processing.
      wsConnect(clientRunId, () => {});

      if (isFollowup) {
        const followupReq: RunFollowupRequest = {
          question: problem,
          preset: getAutoPreset(),
          top_k: 2,
          sequential: false,
          enhance_prompt: true,
          expert: state.isExpert,
          web_search: false,
          smart_search: true,
          conversation_id: conversationIdRef.current || lastAssistantMsg.id,
          history: messages
            .filter((m): m is ChatFeedMessage & { role: 'user' | 'assistant' } => m.role === 'user' || m.role === 'assistant')
            .map((m) => ({ role: m.role, content: m.content || '' })),
          previous_synthesis: lastAssistantMsg.content || '',
          agent_model: null,
          attachments: uploadedAttachments.length > 0 ? uploadedAttachments : undefined,
          file_ids: uploadedAttachments.length > 0 ? uploadedAttachments.map((a) => a.file_id) : undefined,
          client_run_id: clientRunId,
        };
        await startFollowup(followupReq, onEvent);
      } else {
        const newConvId = assistantId;
        conversationIdRef.current = newConvId;
        setConversationId(newConvId);
        const req = {
          problem,
          preset: opts?.presetOverride || getAutoPreset(),
          top_k: 2,
          sequential: false,
          enhance_prompt: true,
          expert: state.isExpert,
          web_search: false,
          smart_search: true,
          attachments: uploadedAttachments.length > 0 ? uploadedAttachments : undefined,
          file_ids: uploadedAttachments.length > 0 ? uploadedAttachments.map((a) => a.file_id) : undefined,
          client_run_id: clientRunId,
          // The user already confirmed a specific method via the gate picker —
          // skip re-running HyperGate so the chosen preset is locked in.
          force_pipeline: !!opts?.presetOverride,
        };
        await startRun(req, onEvent);
      }
    } catch (err) {
      if (err instanceof PipelineError && err.status === 429) {
        try {
          const data = JSON.parse(err.body);
          if (data.detail?.upgrade_url) {
            setShowUpgradeModal(true);
            dispatchMessages({ type: 'UPDATE_MESSAGE', payload: { messageId: assistantId, updates: { isStreaming: false } } });
            wsDisconnect();
            clientRunIdRef.current = null;
            setRunning(false);
            clearAttachments();
            return;
          }
        } catch {
          // body wasn't JSON, fall through to generic error
        }
      }
      let msg = err instanceof Error ? err.message : 'Connection error';
      // Extract clean server error from PipelineError body
      if (err instanceof PipelineError) {
        try {
          const data = JSON.parse(err.body);
          // For 422 validation errors, show which fields failed
          if (err.status === 422 && data.detail?.validation_errors) {
            const fields = data.detail.validation_errors
              .map((e: { loc: string[]; msg: string }) => `${e.loc.join('.')}: ${e.msg}`)
              .join('; ');
            msg = `Validation failed: ${fields}`;
          } else {
            msg = data.error || data.detail || msg;
          }
        } catch { /* use raw message */ }
      }
      // Update assistant message with connection error
      dispatchMessages({ type: 'UPDATE_MESSAGE', payload: { messageId: assistantId, updates: { isStreaming: false } } });
      dispatchMessages({ type: 'ADD_MESSAGES', payload: [{ id: 'err-' + Date.now(), role: 'error', content: msg }] });
      setCurrentPhase(undefined);
    } finally {
      dispatchMessages({ type: 'UPDATE_MESSAGE', payload: { messageId: assistantId, updates: { isStreaming: false } } });
      wsDisconnect();
      clientRunIdRef.current = null;
      setRunning(false);
      clearAttachments();
    }
  }, [composerText, running, attachments, isImageMode, tier, messages, startRun, startFollowup, wsConnect, wsDisconnect, dispatchMessages, setRunning, setComposerText, clearAttachments, refreshHistory, setCompletedPhases, setErrorPhases, setCurrentPhase, setPhaseDurations, setAutoSelectedMethod, setPhaseOpenMode, isContinuation, getAutoPreset, autoMethodAlways]);

  const handleMethodChoice = useCallback((preset: string) => {
    const choice = pendingChoice;
    setPendingChoice(null);
    if (!choice) return;
    handleSubmit(choice.problem, { presetOverride: preset, skipGate: true });
  }, [pendingChoice, handleSubmit]);

  const handleMethodChoiceCancel = useCallback(() => {
    if (pendingChoice) setComposerText(pendingChoice.problem);
    setPendingChoice(null);
  }, [pendingChoice, setComposerText]);

  const handleStop = useCallback(() => {
    stopRun();
    wsSendStop(clientRunIdRef.current || '');
    setRunning(false);
    setCurrentPhase(undefined);
  }, [stopRun, wsSendStop, setRunning, setCurrentPhase]);

  function handleNew() {
    // Dispatch action to clear messages and reset other states managed by parent
    dispatchMessages({ type: 'CLEAR_MESSAGES' });
    setComposerText('');
    setCompletedPhases([]);
    setErrorPhases([]);
    setCurrentPhase(undefined);
    setPhaseDurations({});
    setAutoSelectedMethod(PIPELINE_DEFAULTS.method);
    setPhaseOpenMode('auto');
    phaseStartTimesRef.current = {};
    conversationIdRef.current = null;
    setConversationId(null);
  }

  async function handleResume(pipelineId: string) {
    if (running) return;
    setRunning(true);
    setCompletedPhases([]);
    setErrorPhases([]);
    setCurrentPhase(undefined);
    setPhaseDurations({});

    const assistantId = 'a-resume-' + Date.now();
    const assistantMsg: ChatFeedMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      phases: [],
      isStreaming: true,
    };
    dispatchMessages({ type: 'ADD_MESSAGES', payload: [assistantMsg] });

    let resumePhases: RenderedPhase[] = [];
    let resumeErrors: string[] = [];

    const onResumeEvent = (ev: PhaseEvent) => {
      switch (ev.type) {
        case 'phase_start':
          if (typeof ev.phase === 'number') {
            setCurrentPhase(ev.phase);
            dispatchMessages({ type: 'UPDATE_MESSAGE', payload: { messageId: assistantId, updates: { currentPhaseName: ev.name } } });
          }
          break;
        case 'phase_complete':
          if (typeof ev.phase === 'number') {
            const renderedPhase: RenderedPhase = {
              index: resumePhases.length,
              phase: ev.phase,
              name: ev.name || '',
              data: ev.data ?? {},
            };
            resumePhases = [...resumePhases, renderedPhase];
            setCompletedPhases((prev) => (prev.includes(ev.phase!) ? prev : [...prev, ev.phase!]));
            setCurrentPhase(undefined);
            dispatchMessages({ type: 'UPDATE_MESSAGE', payload: { messageId: assistantId, updates: { content: buildMarkdownFromPhases(resumePhases), phases: [...resumePhases], currentPhaseName: undefined } } });
          }
          break;
        case 'phase_error':
          if (typeof ev.phase === 'number') {
            setErrorPhases((prev) => (prev.includes(ev.phase!) ? prev : [...prev, ev.phase!]));
            setCurrentPhase(undefined);
          }
          break;
        case 'error':
          dispatchMessages({ type: 'UPDATE_MESSAGE', payload: { messageId: assistantId, updates: { isStreaming: false } } });
          dispatchMessages({ type: 'ADD_MESSAGES', payload: [{ id: 'err-' + Date.now(), role: 'error', content: ev.message || 'Resume error' }] });
          break;
        case 'done':
          resumeErrors = ev.errors || [];
          dispatchMessages({ type: 'UPDATE_MESSAGE', payload: { messageId: assistantId, updates: { content: buildMarkdownFromPhases(resumePhases), phases: [...resumePhases], isStreaming: false, currentPhaseName: undefined } } });
          if (resumeErrors.length > 0) {
            dispatchMessages({ type: 'ADD_MESSAGES', payload: resumeErrors.map((err, i) => ({ id: 'err-' + Date.now() + '-' + i, role: 'error', content: err })) });
          }
          break;
      }
    };

    try {
      const body = await resumePipelineStream(pipelineId);
      await readSSEStream(body, onResumeEvent);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Resume failed';
      dispatchMessages({ type: 'UPDATE_MESSAGE', payload: { messageId: assistantId, updates: { isStreaming: false } } });
      dispatchMessages({ type: 'ADD_MESSAGES', payload: [{ id: 'err-' + Date.now(), role: 'error', content: msg }] });
    } finally {
      setRunning(false);
      setCurrentPhase(undefined);
    }
  }

  function handleLoad(conv: Conversation) {
    conversationIdRef.current = conv.conversation_id || conv.id;
    setConversationId(conversationIdRef.current);
    const renderedPhases: RenderedPhase[] = conv.phases.map((p, idx) => ({
      index: idx,
      phase: p.phase,
      name: p.name,
      data: p.data,
    }));
    const loadedMessages = conversationToMessages(conv, buildMarkdownFromPhases) as ChatFeedMessage[];
    // Dispatch action to set loaded messages
    dispatchMessages({ type: 'SET_MESSAGES', payload: loadedMessages });
    
    // Restore the method so PhaseTimeline shows the right phases for loaded conversations
    setAutoSelectedMethod(conv.method || PIPELINE_DEFAULTS.method);
    setCompletedPhases(renderedPhases.map((p) => p.phase));
    setErrorPhases([]);
    setCurrentPhase(undefined);
    setPhaseDurations({});
    phaseStartTimesRef.current = {};
  }

  async function handleClearCache() {
    await clearCache();
  }

  const hasMessages = messages.length > 0;
  const activeAssistantMsg = messages.find((m) => m.role === 'assistant' && m.isStreaming);
  const lastAssistantMsg = useMemo(() => findLastAssistant(messages), [messages]);
  const followupAgentBadge = lastAssistantMsg ? 'Follow-up mode active' : null;

  async function handleFeedback(messageId: string, rating: 'up' | 'down') {
    try {
      await submitFeedback({
        conversation_id: conversationIdRef.current || messageId,
        message_id: messageId,
        rating,
      });
    } catch (err) {
      console.error('Feedback submission failed:', err);
    }
  }

  function handleContinueGenerating() {
    if (lastAssistantMsg) {
      setComposerText('Continue');
      handleSubmit('Continue');
    }
  }

  return (
    <div className="flex h-[100dvh] w-full bg-[var(--bg)] text-[var(--text)] overflow-hidden">
      <Sidebar
        conversations={history}
        onLoad={handleLoad}
        onDelete={removeHistory}
        onClear={handleClearCache}
        onNew={handleNew}
        onResume={handleResume}
        conversationId={conversationId}
        lastUserPrompt={messages.filter((m) => m.role === 'user').at(-1)?.content}
        lastAssistantResponse={messages.filter((m) => m.role === 'assistant' && !m.isStreaming).at(-1)?.content}
      />

      <div className="relative flex flex-1 flex-col sm:ml-0 overflow-hidden">
        {/* Borderless: the sidebar's own ground already separates rail from
            conversation, so a rule here just boxes the column in. */}
        <header className={`flex h-14 shrink-0 items-center justify-between px-4 ${collapsed ? 'sm:ml-14' : ''}`}>
          <div className="flex items-center gap-3">
            {/* --ok/--unknown are reserved for epistemic labels now. A filled
                dot vs. a hollow ring carries "connected" vs. "undetermined"
                by shape (fill state), the same way epistemic marks carry
                their state by border-style — --red stays for a real fault. */}
            <Tooltip text={serverOnline === true ? 'Online' : serverOnline === false ? 'Offline' : 'Checking…'}>
              <div
                className={`h-2 w-2 rounded-full ${
                  serverOnline === true
                    ? 'bg-[var(--text)]'
                    : serverOnline === false
                    ? 'bg-[var(--red)]'
                    : 'border border-[var(--text-subtle)]'
                }`}
              />
            </Tooltip>
            {wsStatus !== 'idle' && (
              <div className="flex items-center gap-1.5">
                <Tooltip text={wsStatus === 'error' && wsLastError ? wsLastError : `WebSocket: ${wsStatus}`}>
                  <div
                    className={`h-2 w-2 rounded-full ${
                      wsStatus === 'connected'
                        ? 'bg-[var(--text)]'
                        : wsStatus === 'reconnecting'
                        ? 'bg-[var(--accent)] animate-pulse'
                        : wsStatus === 'error'
                        ? 'bg-[var(--red)]'
                        : 'border border-[var(--text-subtle)]'
                    }`}
                    aria-label={`WebSocket ${wsStatus}`}
                  />
                </Tooltip>
                <span className="hidden text-[10px] text-[var(--text-muted)] sm:inline">
                  {wsStatus === 'connected' ? 'Live' : wsStatus}
                </span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            {!user && (
              <>
                <button
                  onClick={() => router.push('/about')}
                  className="text-[length:var(--text-sm)] font-medium text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
                >
                  About
                </button>
                <button
                  onClick={() => router.push('/pricing')}
                  className="text-[length:var(--text-sm)] font-medium text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
                >
                  Pricing
                </button>
                <button
                  onClick={() => router.push('/login')}
                  className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-[length:var(--text-sm)] font-medium text-[var(--accent-text)] transition-opacity hover:opacity-90"
                >
                  Sign In
                </button>
              </>
            )}
            <SecurityBadge className="hidden sm:flex" />
            <UserMenu />
            <ThemeToggle />
          </div>
        </header>

        {hasMessages && activeAssistantMsg && (
          <div>
            <div className="px-4 pt-2 text-[length:var(--text-xs)] text-[var(--text-muted)]">
              <Tooltip text={METHOD_DESCRIPTIONS[autoSelectedMethod.replace(/_/g, '-')] || ''}>
                <span className="cursor-help">
                  Method: <span className="text-[var(--text)]">{autoSelectedMethod.replace(/_/g, '-').replace(/\b\w/g, (l) => l.toUpperCase())}</span>
                </span>
              </Tooltip>
            </div>
            <PhaseTimeline
            method={autoSelectedMethod}
            currentPhase={currentPhase}
            completedPhases={completedPhases}
            errorPhases={errorPhases}
            phaseDurations={phaseDurations}
            onExpandAll={() => setPhaseOpenMode('expand')}
            onCollapseAll={() => setPhaseOpenMode('collapse')}
          />
          </div>
        )}

        <div
          id="main-content"
          ref={scrollContainerRef}
          className="relative flex-1 overflow-y-auto scroll-smooth scrollbar-gray"
          style={{
            contain: 'layout paint',
            overscrollBehavior: 'contain',
          }}
        >
          {hasMessages ? (
            <>
              <ChatErrorBoundary fallback={<div className="p-4 text-[var(--red)]">Display error. Please refresh.</div>}>
                <>
                  {activeAssistantMsg && activeAssistantMsg.phases?.length === 0 && activeAssistantMsg.isStreaming && (
                    <PipelineSkeleton method={autoSelectedMethod} />
                  )}
                  <ChatFeed
                    messages={messages}
                    onScrollToBottom={dismissIndicator}
                    showNewContentIndicator={showNewContentIndicator}
                    phaseOpenMode={phaseOpenMode}
                    errorPhases={errorPhases}
                    onFeedback={handleFeedback}
                    onContinueGenerating={handleContinueGenerating}
                    currentPhaseName={activeAssistantMsg?.currentPhaseName}
                  />
                </>
              </ChatErrorBoundary>
            </>
          ) : (
            <>
              {gateChecking && <MethodChoiceLoading />}
              {pendingChoice && (
                <MethodChoicePrompt
                  decision={pendingChoice.decision}
                  alwaysAuto={autoMethodAlways}
                  onChoose={handleMethodChoice}
                  onToggleAlwaysAuto={toggleAutoMethodAlways}
                  onCancel={handleMethodChoiceCancel}
                />
              )}
              <Composer running={running} onSubmit={() => handleSubmit()} onStop={handleStop} centered />
            </>
          )}
        </div>

        {hasMessages && (
          <div className="w-full">
            {followupAgentBadge && (
              <div className="mx-auto max-w-3xl px-4 pb-2 text-[length:var(--text-xs)] text-muted-foreground">
                {followupAgentBadge}
              </div>
            )}
            {gateChecking && <MethodChoiceLoading />}
            {pendingChoice && (
              <MethodChoicePrompt
                decision={pendingChoice.decision}
                alwaysAuto={autoMethodAlways}
                onChoose={handleMethodChoice}
                onToggleAlwaysAuto={toggleAutoMethodAlways}
                onCancel={handleMethodChoiceCancel}
              />
            )}
            <Composer
              running={running}
              onSubmit={() => handleSubmit()}
              onStop={handleStop}
              isFollowup={!!lastAssistantMsg}
            />
          </div>
        )}
      </div>

      <UpgradeModal open={showUpgradeModal} onClose={() => setShowUpgradeModal(false)} />
      <ShortcutModal isOpen={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
      <CommandPalette
        isOpen={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        onNew={handleNew}
        onClearComposer={() => setComposerText('')}
        // Toggling the class directly added `.dark` while next-themes' own
        // `.light` stayed put, so nothing changed and the stored preference
        // desynchronised. Go through next-themes.
        onToggleTheme={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
        onToggleSidebar={toggleSidebar}
        onToggleNeuro={toggleNeuroPanel}
        onToggleTier={toggleTier}
        tier={tier}
        onCopyLastResponse={() => {
          const last = messages.filter((m) => m.role === 'assistant' && !m.isStreaming).at(-1);
          if (last?.content) navigator.clipboard.writeText(last.content);
        }}
        recentCommands={recentCommands}
        onRecordCommand={addRecentCommand}
      />
    </div>
  );
}
