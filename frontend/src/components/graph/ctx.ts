// What the graph screen gives its nodes: the shots' live state (lib/shots.ts, the video screen's), the estimate
// (what is cached, what will be shot), the state of the assembly / music / output, and which nodes are lit.
import type { ComputedRef, InjectionKey } from 'vue'
import type { useShots } from '../../lib/shots'

export interface StepState { state: '' | 'now' | 'ok' | 'stale'; text: string }
export interface GraphCtx {
  shots: ReturnType<typeof useShots>
  est: ComputedRef<Record<string, any> | null>
  step: (id: string) => StepState | null
  lit: ComputedRef<Set<string> | null>
}
export const GRAPH: InjectionKey<GraphCtx> = Symbol('graph')
