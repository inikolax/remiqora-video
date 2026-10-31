// Phase 8: the montage of a storyboard's video (#/p/<id>/edit) or of a graph's «Монтаж» node (#/g/<id>/edit/<node>,
// kept in the node). The server's view of it (GET …/edit: the clips against the scenes and their shots, app/edit.py
// lay) is ED.view; ED.clips / ED.sounds / ED.off / ED.duck are
// the copy the editor changes - laid out here the way the server lays them out (layout), saved a moment after a
// change (PUT …/edit), the server's answer taking its place. Every change can be undone (Ctrl+Z) and redone.
// Nothing is shot again.
import { reactive } from 'vue'
import { api } from './api'
import { banner } from './store'
import { t } from '../i18n'
import { dec } from './format'

export interface Clip {
  id: string; scene: string; index: number; chain: number; kind: string; from: string | null; file: string | null; png: string | null
  length: number; in: number; out: number; tr: 'cut' | 'fade' | 'black' | 'flash'; td: number; speed: number; vol: number
  take: number | null; takes: number                // the clip's own take (a seed; null - the scene's chosen), how many the scene has
  name: string; chosen: number | null; take_list: { seed: number; key: string; cached: boolean; png: string | null }[]
  color?: ClipColor; scene_color?: ClipColor
  start: number; dur: number; frames: number; seamless: boolean; jump: boolean
}
export interface ClipColor { exposure: number; contrast: number; saturation: number; temperature: number }
export const COLOR_DEFAULT: ClipColor = { exposure: 0, contrast: 1, saturation: 1, temperature: 0 }
// A colour adjustment as the render makes it (app/edit.py color_filter, the same numbers): per channel
// out = in · gain · contrast + (1 - contrast) / 2 (exposure in stops, temperature tints red against blue), then the
// saturation about Rec.709 luma. The preview runs these as an SVG filter, so it shows what the built video shows.
export type ColorStep = { slope: [number, number, number]; intercept: number } | { matrix: string }
const TEMP = 0.12, LUMA = [0.2126, 0.7152, 0.0722]
function steps(gain: [number, number, number], contrast: number, saturation: number): ColorStep[] {
  const out: ColorStep[] = []
  const slope = gain.map((g) => g * contrast) as [number, number, number]
  if (slope.some((x) => x !== 1) || contrast !== 1) out.push({ slope, intercept: (1 - contrast) / 2 })
  if (saturation !== 1) {
    const s = saturation, m = (i: number, j: number) => LUMA[j] * (1 - s) + (i === j ? s : 0)
    out.push({ matrix: [0, 1, 2].map((i) => `${m(i, 0)} ${m(i, 1)} ${m(i, 2)} 0 0`).join(' ') + ' 0 0 0 1 0' })
  }
  return out
}
export function colorSteps(g?: ClipColor): ColorStep[] {
  if (!g) return []
  const e = Math.pow(2, g.exposure || 0), w = (g.temperature || 0) / 50
  return steps([e * (1 + TEMP * w), e, e * (1 - TEMP * w)], g.contrast ?? 1, g.saturation ?? 1)
}
// the video's looks (app/edit.py GRADES) near enough for the preview: their tint, contrast and saturation; the
// vignette is drawn over the stage, the grain and a LUT are seen only in the built video
const GRADE_PREVIEW: Record<string, [[number, number, number], number, number]> = {
  film: [[1, 1, 1], 1.06, 1.05], warm: [[1.06, 1.01, 0.94], 1.04, 1.08], cold: [[0.95, 1, 1.07], 1.06, 0.9],
  teal: [[0.95, 1, 1.07], 1.08, 1.1], bw: [[1, 1, 1], 1.12, 0],
}
export const gradeSteps = (grade: string): ColorStep[] => (GRADE_PREVIEW[grade] ? steps(...GRADE_PREVIEW[grade]) : [])
export interface Sound { id: string; file: string; name: string; length: number; start: number; in: number; out: number; vol: number; fade_in: number; fade_out: number }
// «Поверх»: a piece of a scene's shot (a take of it) over the video from `start` - its picture only (app/edit.py)
export interface Overlay {
  id: string; scene: string; index: number; name: string; take: number | null; chosen: number | null
  file: string | null; png: string | null; length: number; in: number; out: number; start: number; dur: number; frames: number
  take_list: { seed: number; key: string; cached: boolean; png: string | null }[]
}
export interface Look { grade: string; lut: string; lutMix: number; match: boolean; color?: ClipColor; vignette: number; grain: number }
export interface EditView {
  clips: Clip[]; off: string[]; sounds: Sound[]; overlays?: Overlay[]; duck: number; duration: number; complete: boolean; changed: boolean
  grade?: string; lut?: string; lut_mix?: number; match?: boolean; color?: ClipColor; scene_colors?: Record<string, ClipColor>
  vignette?: number; grain?: number
  quality: string; width: number; height: number; fps: number; sig: string; built_sig: string | null; built: boolean; to_shoot: number
  track: Record<string, any> | null
  kind?: 'board' | 'graph'; node?: string; title?: string; state?: string; error?: string | null
}

export const FPS = 24, FRAME = 1 / FPS, MIN_CLIP = 0.5, TD = 0.5
export const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2]
// a table of labels read through t() when read (the interface's language); enumerable, so a v-for works
function labels<K extends string>(area: string, keys: readonly K[]): Record<K, string> {
  const o = {} as Record<K, string>
  for (const k of keys) Object.defineProperty(o, k, { get: () => t(`${area}.${k}`), enumerable: true })
  return o
}
export const TR_NAME: Record<string, string> = labels('edit.tr', ['cut', 'fade', 'black', 'flash'])
export const FLASH_S = 4 / 24   // a flash: the cut with a white flash fading out over 4 frames (app/edit.py FLASH)
export const SND = 's:'   // ED.sel of a sound: 's:<id>'
export const OVL = 'o:'   // ED.sel of an overlay: 'o:<id>'
export const SEAM = 'j:'  // ED.sel of a seam - the join before a clip: 'j:<clip id>'

export const ED = reactive({
  id: '',
  node: '' as string,                  // a graph's «Монтаж» node, or '' for a storyboard
  base: '',                            // the montage's API: /api/projects/<id>/edit or …/nodes/<node>/edit
  view: null as EditView | null,
  clips: [] as Clip[],
  sounds: [] as Sound[],
  overlays: [] as Overlay[],
  off: [] as string[],
  sceneColors: {} as Record<string, ClipColor>,
  colorScope: 'video' as 'clip' | 'scene' | 'video',
  colorSceneId: null as string | null,
  duck: 0,
  // the video's colour (app/edit.py GRADES and look_of): its look, how much of a LUT, the adjustment, the vignette and grain
  look: { grade: '', lut: '', lutMix: 1, match: false, color: undefined as ClipColor | undefined, vignette: 0, grain: 0 } as Look,
  bare: false,                         // «До / после» held: the preview as shot, without any colour
  duration: 0,
  sel: null as string | null,          // a clip's id, 's:<sound id>', 'o:<overlay id>', 'j:<clip id>' (the seam before it), or 'music'
  t: 0,                                // the playhead, seconds
  playing: false,
  seekRev: 0,                           // timeline seek gesture; distinct from the playhead's playback clock
  cue: null as number | null,          // play from here (the panel's «Проиграть стык»; the screen starts the player)
  px: 40,                              // pixels a second
  saving: false,
  undo: 0, redo: 0,                    // how many steps there are (the buttons)
  // «Магнит» (phase 11): the track's beats and bar lines in the video's time (GET …/beats); with it on, a dragged cut
  // or sound lands on the nearest beat
  magnet: (() => { try { return localStorage.getItem('h3-magnet') !== '0' } catch { return true } })(),
  beats: [] as number[],
  bars: [] as number[],
  bpm: null as number | null,
  taps: [] as number[],                // «Удар» (B): where the user heard a beat; the server moves the found beats onto them
  fixed: 0,                            // how many taps the track's beats are fixed by now
})

const frame = (x: number) => Math.round(Math.round(x * FPS) / FPS * 10000) / 10000
export const uid = () => Math.random().toString(16).slice(2, 10)

// the server's layout (app/edit.py resolve), for a change being made: frames at speed, starts, dissolves, joins
export function layout(clips: Clip[]) {
  let t = 0
  clips.forEach((c, k) => {
    const prev = clips[k - 1]
    if (!k) c.tr = 'cut'
    c.frames = Math.max(1, Math.round(Math.round((c.out - c.in) * FPS) / c.speed))
    let td = 0
    if (c.tr !== 'cut' && c.tr !== 'flash' && prev) td = Math.max(1, Math.min(Math.round(Math.min(Math.max(0.2, c.td || TD), 2) * FPS), Math.floor(prev.frames / 2), Math.floor(c.frames / 2)))
    c.td = td / FPS
    const sameScene = !!prev && prev.scene === c.scene, same = sameScene && prev.take === c.take
    const link = !!prev && !!c.from && prev.scene === c.from, cont = link && prev.take === null
    const joined = !!prev && ((same && Math.abs(prev.out - c.in) < FRAME / 2) || (cont && Math.abs(prev.out - prev.length) < FRAME / 2 && Math.abs(c.in - FRAME) < FRAME / 2))
    c.seamless = (same || cont) && c.tr === 'cut' && c.speed === 1 && prev?.speed === 1 && joined
    c.jump = (sameScene || link) && !c.seamless && c.tr === 'cut'
    c.start = (t - td) / FPS
    c.dur = c.frames / FPS
    t = t - td + c.frames
  })
  ED.duration = t / FPS
  // the overlays inside the video (the server's lay does the same)
  for (const o of ED.overlays) {
    o.start = frame(Math.min(Math.max(0, o.start), Math.max(0, ED.duration - MIN_CLIP)))
    o.out = frame(Math.min(o.out, o.in + (ED.duration - o.start)))
    o.dur = o.out - o.in
    o.frames = Math.round(o.dur * FPS)
  }
}

export async function loadEdit(id: string, node = '') {
  ED.id = id
  ED.node = node
  ED.base = node ? `/api/projects/${id}/nodes/${node}/edit` : `/api/projects/${id}/edit`
  undos.length = 0
  redos.length = 0
  take(await api<EditView>(ED.base))
  last = snap()
  counts()
}
function take(v: EditView) {
  ED.view = v
  // a server of stage A has no ids, speeds, levels, sounds: the clips get what they lack
  ED.clips = v.clips.map((c) => {
    const o = c as Partial<Clip> & Clip
    return { ...o, speed: o.speed ?? 1, vol: o.vol ?? 1, take: o.take ?? null, takes: o.takes ?? 1, dur: o.dur ?? o.out - o.in, frames: o.frames ?? Math.round((o.out - o.in) * FPS), id: o.id || o.scene }
  })
  ED.sounds = (v.sounds || []).map((x) => ({ ...x }))
  ED.overlays = (v.overlays || []).map((x) => ({ ...x }))
  ED.off = [...(v.off || [])]
  ED.sceneColors = Object.fromEntries(Object.entries(v.scene_colors || {}).map(([id, color]) => [id, { ...color }]))
  ED.duck = v.duck || 0
  ED.look = { grade: v.grade || '', lut: v.lut || '', lutMix: v.lut_mix ?? 1, match: !!v.match, color: v.color ? { ...v.color } : undefined, vignette: v.vignette || 0, grain: v.grain || 0 }
  ED.duration = v.duration
  keepSel()
}
// the selection is gone (undone, removed, a seam that is now the first clip's start): nothing selected
function keepSel() {
  const s = ED.sel
  if (!s || s === 'music') return
  const ok = s.startsWith(SND) ? ED.sounds.some((x) => SND + x.id === s) : s.startsWith(OVL) ? ED.overlays.some((x) => OVL + x.id === s) : s.startsWith(SEAM) ? ED.clips.findIndex((c) => SEAM + c.id === s) > 0 : ED.clips.some((c) => c.id === s)
  if (!ok) ED.sel = null
}

// ---- undo / redo: a step is the montage as saved; quick changes in a row (a slider) are one step ----
type Snap = string
const undos: Snap[] = [], redos: Snap[] = []
let last: Snap = '', lastAt = 0
const body = () => ({
  clips: ED.clips.map(({ id, scene, in: a, out, tr, td, speed, vol, take, color }) => ({ id, scene, in: a, out, tr, td, speed, vol, take, ...(color ? { color } : {}) })),
  off: ED.off, sounds: ED.sounds, duck: ED.duck,
  overlays: ED.overlays.map(({ id, scene, take, start, in: a, out }) => ({ id, scene, take, start, in: a, out })),
  ...(ED.look.grade ? { grade: ED.look.grade, lut: ED.look.lut || null } : {}), match: ED.look.match,
  lut_mix: ED.look.lutMix, vignette: ED.look.vignette, grain: ED.look.grain,
  ...(ED.look.color ? { color: ED.look.color } : {}),
  scene_colors: ED.sceneColors,
})
const snap = (): Snap => JSON.stringify({ ...body(), clips: ED.clips, overlays: ED.overlays })
function counts() { ED.undo = undos.length; ED.redo = redos.length }
function step() {
  const now = snap()
  if (now === last) return
  if (Date.now() - lastAt > 700 || !undos.length) undos.push(last)
  if (undos.length > 80) undos.shift()
  redos.length = 0
  last = now
  lastAt = Date.now()
  counts()
}
function restore(s: Snap) {
  const d = JSON.parse(s)
  ED.clips = d.clips; ED.off = d.off; ED.sounds = d.sounds; ED.overlays = d.overlays || []; ED.duck = d.duck; ED.sceneColors = d.scene_colors || {}
  ED.look = { grade: d.grade || '', lut: d.lut || '', lutMix: d.lut_mix ?? 1, match: !!d.match, color: d.color ? { ...d.color } : undefined, vignette: d.vignette || 0, grain: d.grain || 0 }
  layout(ED.clips)
  last = s
  lastAt = 0
  keepSel()
  counts()
  queue(50)
}
export function undo() { const s = undos.pop(); if (!s) return false; redos.push(snap()); restore(s); return true }
export function redo() { const s = redos.pop(); if (!s) return false; undos.push(snap()); restore(s); return true }

let timer: ReturnType<typeof setTimeout> | undefined
let revision = 0
let savePromise: Promise<void> | null = null
function queue(ms: number) { ED.saving = true; clearTimeout(timer); timer = setTimeout(save, ms) }
export function touch(ms = 400) {
  revision++
  layout(ED.clips)
  step()
  queue(ms)
}
async function save(): Promise<void> {
  if (savePromise) return savePromise
  savePromise = (async () => {
    let sent = -1
    try {
      do {
        sent = revision
        const result = await api<EditView>(ED.base, { method: 'PUT', body: body() })
        // A response for an older slider position must never replace newer local edits.
        if (sent === revision) { take(result); last = snap() }
      } while (sent !== revision)
    } catch (e) { banner(t('edit.notSaved', { e: (e as Error).message })) }
    finally {
      clearTimeout(timer); timer = undefined
      ED.saving = false
    }
  })()
  try { await savePromise } finally { savePromise = null }
}
export async function flushEdit() {
  if (timer && ED.saving) { clearTimeout(timer); timer = undefined; await save() }
  else if (savePromise) await savePromise
}
export async function resetEdit() {
  clearTimeout(timer)
  undos.push(snap())
  try { take(await api<EditView>(ED.base, { method: 'DELETE' })); ED.saving = false; last = snap(); counts() } catch (e) { banner((e as Error).message) }
}

// ---- the magnet: the track's beats ----
export async function loadBeats() {
  ED.beats = []; ED.bars = []; ED.bpm = null
  if (ED.node || !ED.view?.track) return   // a graph's montage has no track of its own (its «Музыка» comes after)
  try { takeBeats(await api<Beats>(`/api/projects/${ED.id}/beats`)) }
  catch { /* no beats: the magnet just does nothing */ }
}
type Beats = { bpm: number | null; beats: number[]; bars: number[]; fixed?: number }
function takeBeats(b: Beats) { ED.beats = b.beats; ED.bars = b.bars; ED.bpm = b.bpm; ED.fixed = b.fixed || 0; if (!ED.fixed) ED.taps = [] }
// «Удар» (B, while the track plays): a beat heard at the playhead; a moment after the last tap the server fits the found
// beats to all the taps of this session (one: an offset, two and more: the drift too). `reset`: the found beats as they are
let tapTimer: ReturnType<typeof setTimeout> | undefined
export function tapBeat(reset = false) {
  if (reset) ED.taps = []; else ED.taps.push(Math.round(ED.t * 1000) / 1000)
  clearTimeout(tapTimer)
  tapTimer = setTimeout(async () => {
    try { takeBeats(await api<Beats>(`/api/projects/${ED.id}/beats/fix`, { method: 'PUT', body: { taps: ED.taps } })) }
    catch (e) { banner((e as Error).message) }
  }, reset ? 0 : 600)
}
export function setMagnet(on: boolean) { ED.magnet = on; try { localStorage.setItem('h3-magnet', on ? '1' : '0') } catch { /* private window */ } }
// the beat nearest to t within `px` pixels of the timeline, or t itself
export function snapT(t: number, px = 8): number {
  if (!ED.magnet || !ED.beats.length) return t
  let best = t, d = px / ED.px
  for (const b of ED.beats) { const x = Math.abs(b - t); if (x < d) { d = x; best = b } }
  return best
}
// «Склейки на доли»: every cut (not a seam without one: a continuation stays whole) moves back to the last beat
// before it, the clip shortened by less than a beat; the clips after it follow
export function cutsOnBeats(): number {
  if (!ED.beats.length) return 0
  let n = 0
  ED.clips.forEach((c, k) => {
    const next = ED.clips[k + 1]
    if (!next || next.seamless) return
    const end = c.start + c.dur, beat = 60 / (ED.bpm || 120)
    const b = [...ED.beats].reverse().find((x) => x <= end + FRAME / 2 && x - c.start >= MIN_CLIP / c.speed)
    if (b === undefined || end - b > beat || Math.abs(end - b) < FRAME / 2) return
    c.out = frame(c.in + (b - c.start) * c.speed)
    layout(ED.clips)
    n++
  })
  if (n) touch(50)
  return n
}

// ---- changes ----
export const clipOf = (id: string | null) => ED.clips.find((c) => c.id === id) || null
export const soundOf = (sel: string | null) => (sel && sel.startsWith(SND) ? ED.sounds.find((x) => SND + x.id === sel) || null : null)
export const overlayOf = (sel: string | null) => (sel && sel.startsWith(OVL) ? ED.overlays.find((x) => OVL + x.id === sel) || null : null)
// the overlay on screen at t (the last one wins where they overlap, as the render lays them in their order)
export const overlayAt = (t: number) => [...ED.overlays].reverse().find((o) => o.file && t >= o.start - 1e-6 && t < o.start + o.dur - 1e-6) || null
// «+ Поверх»: the scene under the playhead, another take of it when there is a shot one (else the same), from where
// the playhead is in it, 2 s - the panel picks another scene, take or piece
export function addOverlay() {
  const { k, local } = at(ED.t), c = ED.clips[k]
  if (!c) return
  const other = c.take_list.find((x) => x.cached && x.seed !== (c.take ?? c.chosen))
  const take = other ? (other.seed === c.chosen ? null : other.seed) : c.take
  const len = c.length   // the server corrects it to the take's own length
  const a = frame(Math.min(local, Math.max(0, len - 2)))
  const o: Overlay = { id: uid(), scene: c.scene, index: c.index, name: c.name, take, chosen: c.chosen, file: null, png: null, length: len,
    in: a, out: frame(Math.min(len, a + 2)), start: frame(ED.t), dur: 2, frames: 48, take_list: c.take_list }
  ED.overlays.push(o)
  ED.sel = OVL + o.id
  touch(50)
}
export function trimOverlay(o: Overlay, side: 'in' | 'out', v: number) {
  if (side === 'in') { const a = frame(Math.min(Math.max(0, v), o.out - MIN_CLIP)); o.start = frame(Math.max(0, o.start + (a - o.in))); o.in = a }
  else o.out = frame(Math.max(Math.min(o.length, v), o.in + MIN_CLIP))
  layout(ED.clips)
}
// the scenes an overlay can take its picture from: those of the clips, each once
export const overlayScenes = () => ED.clips.filter((c, i) => ED.clips.findIndex((x) => x.scene === c.scene) === i)
export function setOverlayScene(o: Overlay, scene: string) {
  const c = ED.clips.find((x) => x.scene === scene)
  if (!c) return
  Object.assign(o, { scene, index: c.index, name: c.name, take: null, chosen: c.chosen, take_list: c.take_list, file: null, png: null })
  touch(50)
}
export function trim(c: Clip, side: 'in' | 'out', v: number) {
  if (side === 'in') c.in = frame(Math.min(Math.max(0, v), c.out - MIN_CLIP))
  else c.out = frame(Math.max(Math.min(c.length, v), c.in + MIN_CLIP))
  layout(ED.clips)
}
// the chains move as one: `chain` goes before the chain `before` (null: to the end)
export function chainsOf(clips: Clip[]): number[] { return clips.reduce<number[]>((a, c) => (a.includes(c.chain) ? a : [...a, c.chain]), []) }
export function moveChain(chain: number, before: number | null) {
  const order = chainsOf(ED.clips).filter((x) => x !== chain)
  const at = before === null ? order.length : order.indexOf(before)
  order.splice(at < 0 ? order.length : at, 0, chain)
  ED.clips = order.flatMap((ch) => ED.clips.filter((c) => c.chain === ch))
  touch(50)
}
export function setTr(c: Clip, tr: Clip['tr'], td?: number) { c.tr = tr; if (td) c.td = td; touch(150) }

// ---- the seams: the join before each clip but the first ----
export type SeamKind = 'flow' | 'jump' | 'cut' | 'fade' | 'black' | 'flash'
export const SEAM_NAME: Record<SeamKind, string> = labels('edit.seam', ['flow', 'jump', 'cut', 'fade', 'black', 'flash'])
export const SEAM_ICON: Record<SeamKind, string> = { flow: 'link', jump: 'warn', cut: 'splice', fade: 'dissolve', black: 'dot', flash: 'spark' }
export const seamOf = (sel: string | null) => { const k = sel && sel.startsWith(SEAM) ? ED.clips.findIndex((c) => SEAM + c.id === sel) : -1; return k > 0 ? ED.clips[k] : null }
export const seamKind = (c: Clip): SeamKind => (c.tr !== 'cut' ? c.tr : c.seamless ? 'flow' : c.jump ? 'jump' : 'cut')
// why a seam jumps: another take before a continuation (or the pieces of one shot from two takes), a speed, a trim
export function seamWhy(c: Clip): 'take' | 'speed' | 'trim' | null {
  const prev = ED.clips[ED.clips.indexOf(c) - 1]
  if (!prev || !c.jump) return null
  if (prev.scene === c.scene ? prev.take !== c.take : prev.take !== null) return 'take'
  return c.speed !== 1 || prev.speed !== 1 ? 'speed' : 'trim'
}
// «Вернуть стык»: the join as shot - the next piece of the same take goes on where the last one ends, a continuation
// follows its scene's chosen take, whole at the join; both at their own speed
export function mendSeam(c: Clip) {
  const prev = ED.clips[ED.clips.indexOf(c) - 1]
  if (!prev) return
  if (prev.scene === c.scene) { c.take = prev.take; c.in = Math.min(prev.out, c.out - MIN_CLIP) }
  else { prev.take = null; prev.out = prev.length; c.in = FRAME }
  prev.speed = 1
  c.speed = 1
  c.tr = 'cut'
  touch(100)
}
// a clip's take: another shot of its scene (the server finds its file and its length; trims stay inside it)
export function setTake(c: Clip, seed: number | null) { c.take = seed; touch(50) }
export function resetClip(c: Clip) { c.in = c.kind === 'continue' ? FRAME : 0; c.out = c.length; c.tr = 'cut'; c.td = TD; c.speed = 1; c.vol = 1; c.take = null; delete c.color; touch(150) }

// where the playhead is: the clip on screen (the later one in a dissolve) and the time in its shot
export function at(t: number): { k: number; local: number } {
  const cs = ED.clips
  let k = 0
  for (let i = 0; i < cs.length; i++) if (cs[i].start <= t + 1e-6) k = i
  const c = cs[k]
  return { k, local: c ? Math.min(c.out, c.in + Math.max(0, t - c.start) * c.speed) : 0 }
}

// S: the clip under the playhead in two, at the playhead (both halves at least MIN_CLIP long)
export function split(): boolean {
  const { k, local } = at(ED.t)
  const c = ED.clips[k]
  const cut = frame(local)
  if (!c || cut - c.in < MIN_CLIP - 1e-6 || c.out - cut < MIN_CLIP - 1e-6) return false
  const b: Clip = { ...c, id: uid(), ...(c.color ? { color: { ...c.color } } : {}), in: cut, tr: 'cut', td: TD }
  c.out = cut
  ED.clips.splice(k + 1, 0, b)
  ED.sel = b.id
  touch(100)
  return true
}
// Ctrl+D: a copy of the selected clip right after it (a sound: after it on its lane)
export function duplicate(): boolean {
  const c = clipOf(ED.sel)
  if (c) {
    const d: Clip = { ...c, id: uid(), ...(c.color ? { color: { ...c.color } } : {}), tr: 'cut', td: TD }
    ED.clips.splice(ED.clips.indexOf(c) + 1, 0, d)
    ED.sel = d.id
    touch(100)
    return true
  }
  const x = soundOf(ED.sel)
  if (x) {
    const d: Sound = { ...x, id: uid(), start: x.start + (x.out - x.in) }
    ED.sounds.push(d)
    ED.sel = SND + d.id
    touch(100)
    return true
  }
  const o = overlayOf(ED.sel)
  if (o) {
    const d: Overlay = { ...o, id: uid(), start: o.start + o.dur }
    ED.overlays.push(d)
    ED.sel = OVL + d.id
    touch(100)
    return true
  }
  return false
}
// Delete: the selected clip goes; a scene left without clips is taken out of the video (it stays in the storyboard)
export function remove(): boolean {
  const c = clipOf(ED.sel)
  if (c) {
    if (ED.clips.length === 1) { banner(t('edit.lastClip'), 'info'); return false }
    ED.clips.splice(ED.clips.indexOf(c), 1)
    if (!ED.clips.some((x) => x.scene === c.scene) && !ED.off.includes(c.scene)) ED.off.push(c.scene)
    ED.sel = null
    touch(100)
    return true
  }
  const x = soundOf(ED.sel)
  if (x) { ED.sounds.splice(ED.sounds.indexOf(x), 1); ED.sel = null; touch(100); return true }
  const o = overlayOf(ED.sel)
  if (o) { ED.overlays.splice(ED.overlays.indexOf(o), 1); ED.sel = null; touch(100); return true }
  const j = seamOf(ED.sel)   // a seam: its dissolve goes, a plain cut stays
  if (j && j.tr !== 'cut') { setTr(j, 'cut'); return true }
  return false
}
// a scene taken out comes back (the server puts it after the scene before it)
export function restoreScene(scene: string) { ED.off = ED.off.filter((x) => x !== scene); touch(50) }

export function addSound(s: { file: string; name: string; length: number }) {
  const x: Sound = { id: uid(), file: s.file, name: s.name, length: s.length, start: Math.round(ED.t * 100) / 100, in: 0, out: s.length, vol: 1, fade_in: 0, fade_out: 0 }
  ED.sounds.push(x)
  ED.sel = SND + x.id
  touch(50)
}

// a file of the project, or "@<project>/…" - a shot in the cache of the storyboard a graph was made from
export const fileUrl = (f: string | null | undefined) => (!f ? '' : f.startsWith('@') ? `/api/projects/${f.slice(1).replace('/', '/files/')}` : `/api/projects/${ED.id}/files/${f}`)
export const tc = (s: number) => { const m = Math.floor(s / 60), r = s - m * 60; return `${m}:${dec(r.toFixed(1).padStart(4, '0'))}` }
export const xn = (x: number) => `${dec(x)}×`
