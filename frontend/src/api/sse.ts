/**
 * SSE 流式接口封装
 * 基于 @microsoft/fetch-event-source，POST /api/research 建立 text/event-stream 连接，
 * 将后端事件按 event 名分发给调用方回调，支持 AbortController 中断。
 */
import { fetchEventSource } from '@microsoft/fetch-event-source'
import type {
  EndEvent,
  ErrorEvent,
  InterruptEvent,
  MessageChunkEvent,
  ResearchRequestBody,
  SSEEventData,
  StartEvent,
  StepResultEvent,
  ToolCallChunksEvent,
  ToolCallResultEvent,
  ToolCallsEvent,
} from '../types'

/** SSE 事件的回调集合（全部可选，按需订阅） */
export interface ResearchStreamHandlers {
  onStart?: (e: StartEvent) => void
  onMessageChunk?: (e: MessageChunkEvent) => void
  onToolCalls?: (e: ToolCallsEvent) => void
  onToolCallChunks?: (e: ToolCallChunksEvent) => void
  onToolCallResult?: (e: ToolCallResultEvent) => void
  onStepResult?: (e: StepResultEvent) => void
  onInterrupt?: (e: InterruptEvent) => void
  onErrorEvent?: (e: ErrorEvent) => void
  onEnd?: (e: EndEvent) => void
  /** 连接正常关闭（收到 end / interrupt 后后端主动断开都会触发） */
  onClosed?: () => void
}

/** 后端约定的全部事件名 */
const EVENT_NAMES = [
  'start',
  'message_chunk',
  'tool_calls',
  'tool_call_chunks',
  'tool_call_result',
  'step_result',
  'interrupt',
  'error',
  'end',
] as const

type EventName = (typeof EVENT_NAMES)[number]

function isKnownEvent(name: string): name is EventName {
  return (EVENT_NAMES as readonly string[]).includes(name)
}

/**
 * 发起研究请求并消费 SSE 流。
 * - 正常结束（流关闭）时 Promise resolve；
 * - 网络层错误（非用户主动中断）时 Promise reject；
 * - 用户 abort 时 Promise 静默 resolve。
 */
export async function streamResearch(
  body: ResearchRequestBody,
  handlers: ResearchStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  await fetchEventSource('/api/research', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(body),
    signal,
    // 页面切到后台时不中断连接
    openWhenHidden: true,
    async onopen(response) {
      if (response.ok && response.headers.get('content-type')?.includes('text/event-stream')) {
        return
      }
      throw new Error(`连接研究服务失败（HTTP ${response.status}）`)
    },
    onmessage(event) {
      const name = event.event
      if (!isKnownEvent(name) || !event.data) return
      let data: SSEEventData
      try {
        data = JSON.parse(event.data) as SSEEventData
      } catch {
        console.warn('[sse] 无法解析事件数据:', name, event.data)
        return
      }
      // 按 event 名分发到对应回调
      switch (name) {
        case 'start':
          handlers.onStart?.(data as StartEvent)
          break
        case 'message_chunk':
          handlers.onMessageChunk?.(data as MessageChunkEvent)
          break
        case 'tool_calls':
          handlers.onToolCalls?.(data as ToolCallsEvent)
          break
        case 'tool_call_chunks':
          handlers.onToolCallChunks?.(data as ToolCallChunksEvent)
          break
        case 'tool_call_result':
          handlers.onToolCallResult?.(data as ToolCallResultEvent)
          break
        case 'step_result':
          handlers.onStepResult?.(data as StepResultEvent)
          break
        case 'interrupt':
          handlers.onInterrupt?.(data as InterruptEvent)
          break
        case 'error':
          handlers.onErrorEvent?.(data as ErrorEvent)
          break
        case 'end':
          handlers.onEnd?.(data as EndEvent)
          break
      }
    },
    onclose() {
      handlers.onClosed?.()
    },
    onerror(err) {
      // 注意：fetch-event-source 的 onerror 若不抛错会按默认间隔自动重连，
      // 研究流程不能重放事件，因此这里一律抛出，由外层 catch 统一处理
      // （用户主动 abort 时该回调不会触发，promise 会直接 resolve）。
      throw err
    },
  })
}
