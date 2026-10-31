// What the server sends. Only the fields the page reads are named; the project's plan is the server's JSON
// (projects/<id>/project.json), edited here and sent back whole, so its parts stay open.
export interface Quality { id: string; mp: number; w: number; h: number; per_scene: number }
// phase 10: a video model's card (app/videomodels.py)
export interface VideoModel {
  id: string; name: string; short: string; text: string; sound: boolean; voice: boolean; refs: boolean; track: boolean; ends?: boolean
  max_seconds: number; grid_seconds?: number; license: string; steps: number; sizes: Record<string, { w: number; h: number }>; missing: string[]
  mp: Record<string, number>; step: number; per_scene: Record<string, number>
  imported?: boolean   // shots brought from remiqora-video: named on a scene, never offered
  color: string        // the shelf's ribbon and filter dots, «Модели и настройки»'s disk bar
}
// phase 11: a song for a clip (app/song.py public): its parts, bars, chorus, the sung lines with their times, loudness
export interface Song {
  id: string; name: string; duration: number; bpm: number; bar_s: number; bars: number[]
  sections: { kind: string; start: number; end: number; energy: number }[]
  chorus: [number, number][]; lines: { start: number; end: number; text: string }[]
  text: string; recognised: boolean; language: string | null; peaks: number[]
}
export interface Config {
  version?: string                     // the commit the server runs (the footer)
  aspects: { id: string; ratio: number }[]
  qualities: Quality[]
  video_models: VideoModel[]
  problems: string[]
  max_prompt: number
  fps: number
  lora_dirs: string[]
  output_dir: string
}
export interface Job {
  id: string
  kind: 'scene' | 'render' | 'write' | 'rewrite' | string
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled'
  phase: string
  step: number
  steps: number
  estimate: number
  elapsed: number
  file: string | null
  error: string | null
  stop_after?: boolean
  created?: number
  finished?: number
  params: Record<string, any>
  progress: Record<string, any>
  result?: any
}
export interface Mem { used: number; total: number; name?: string; load?: number | null; temp?: number | null }
export interface Sys {
  ram: Mem | null
  vram: Mem | null
  engine: string
  engine_ram: number | null
  engine_model?: string | null   // phase 10: whose weights sit in memory (H3, LTX 2.5...)
  busy: boolean
  llm: string | null
  procs: Record<string, number | null>
  vram_by: { key: string; gb: number }[]
}
export interface LlmModel { id: string; name: string; size_gb: number; vision: boolean }
export interface LlmList { models: LlmModel[]; default: string | null; server_ok: boolean }
export interface Lora {
  id: string; model: string; name: string; folder: string; size_mb: number; kind: string; verdict: string; note: string
  rank: number; blocks: number; base: string; trigger: string; preview: string | null
  strength?: number   // the strength it takes when added (the «LoRA» tab of its model's card, app/lora_prefs.py)
  v2v?: V2VProfile   // a LoRA that reads a clip (app/v2v.py)
}
export interface V2VProfile { engine: string; reads: 'clip' | 'voice'; identity?: number; voice_secs?: number
  prompt: 'none' | 'optional' | 'required'; template: string; lead: string; stages: number; out: 'video' | 'matte'
  scale: number; ref_down: number; max_frames: number; sound: string; note: string; own: boolean; known: boolean }
export type Scene = Record<string, any>
export type Plan = Record<string, any> & { scenes: Scene[]; cast?: Record<string, any>[] }
export interface Project {
  id: string
  name: string
  plan: Plan | null
  settings: Record<string, any>
  renders?: Record<string, any>
  [k: string]: any
}
export interface Take { file: string; poster: string | null; params: Record<string, any>; created?: string; seconds?: number }
