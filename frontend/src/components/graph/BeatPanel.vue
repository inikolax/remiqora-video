<script setup lang="ts">
// The beat montage's panel (beat_montage): GET/PUT /api/projects/{pid}/nodes/{nid}/beat. The genre preset, a slider or
// a switch for every item of the server's `spec` by group (each with its own "?"), the frame rate and the loudness, the
// palette in three colours, the title and the HUD text, the captions (on / off and the table: word, start, end, hide), the
// 540x960 preview and «Собрать». Slider edits go to the server ~400 ms after the last one; nothing is rebuilt on a change,
// and render parameters never re-shoot the scenes (their key is not in the beat montage's).
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import BeatHelp from '../BeatHelp.vue'
import HelpQ from '../HelpQ.vue'
import { GE, adoptSaved, fileUrl, flush, live, runTo } from '../../lib/graphDoc'
import { api, post } from '../../lib/api'
import { S, banner, live as jobLive, onJobEnd } from '../../lib/store'
import { type BeatSpec, type BeatView, type CaptionWord, SPEC_GROUPS, bgrToHex, hexToBgr, nameOf } from '../../lib/beat'
import { dec } from '../../lib/format'

const props = defineProps<{ id: string }>()
const { t, locale } = useI18n()
const url = computed(() => `/api/projects/${GE.id}/nodes/${props.id}/beat`)
const v = ref<BeatView | null>(null)
const failed = ref('')
const busy = computed(() => !!live())

async function load() {
  try { await flush(); v.value = await api<BeatView>(url.value); failed.value = ''; seedEdits() } catch (e) { failed.value = (e as Error).message }
}
// edits are sent together ~400 ms after the last one; the answer is the whole view again. While edits are waiting the
// answer is not shown over them.
let pending: Record<string, any> = {}
let timer = 0
function patch(p: Record<string, any>, now = false) {
  Object.assign(pending, p)
  clearTimeout(timer)
  timer = window.setTimeout(send, now ? 0 : 400)
}
async function send() {
  const body = pending
  pending = {}
  if (!Object.keys(body).length) return
  try {
    const r = await api<BeatView>(url.value, { method: 'PUT', body })
    await adoptSaved(props.id, r.graph_rev, r.node_data)
    if (!Object.keys(pending).length) { v.value = r; seedEdits() }
  } catch (e) { banner((e as Error).message) }
}
onMounted(load)
watch(() => [props.id, GE.id], load)
onBeforeUnmount(() => { clearTimeout(timer); if (Object.keys(pending).length) send() })

// ---- the preset and the sliders
const specOf = (g: string) => (v.value?.spec || []).filter((x) => x.group === g && x.key !== 'captions')
const groups = computed(() => SPEC_GROUPS.filter((g) => specOf(g).length))
const help = (x: BeatSpec) => (locale.value === 'en' ? x.help_en : x.help_ru) || ''
const val = (x: BeatSpec) => (v.value?.params?.[x.key] ?? 0) as number
const isSet = (x: BeatSpec) => !!v.value && x.key in v.value.overrides
const decimals = (x: BeatSpec) => (x.kind === 'int' ? 0 : Math.max(0, (String(x.step ?? 0.01).split('.')[1] || '').length))
const show = (x: BeatSpec) => dec(val(x).toFixed(decimals(x)))
function setParam(key: string, value: number | boolean | undefined) {
  if (!v.value) return
  const o = { ...v.value.overrides }
  if (value === undefined) delete o[key]; else o[key] = value
  v.value.overrides = o
  if (value !== undefined) v.value.params = { ...v.value.params, [key]: value }
  patch({ params: o })
}
// a preset resets the sliders but keeps the captions switch (turned-off captions must not come back)
const setPreset = (id: string) => {
  const keep: Record<string, number | boolean> = {}
  if (v.value && 'captions' in v.value.overrides) keep.captions = v.value.overrides.captions
  if (v.value) { v.value.preset = id; v.value.overrides = { ...keep } }
  patch({ preset: id, params: keep }, true)
}

// ---- the palette: BGR on the wire, #rrggbb in the colour pickers
const PAL = ['a', 'b', 'tint'] as const
function setColour(k: typeof PAL[number], hex: string) {
  if (!v.value) return
  v.value.palette = { ...v.value.palette, [k]: hexToBgr(hex) }
  patch({ palette: v.value.palette })
}

// ---- the title and the HUD: the server cleans them (drug-hint words); its answer says so
const setText = (k: 'title' | 'hud', s: string) => { if (v.value) v.value[k] = s; patch({ [k]: s }) }

// ---- the captions: the table holds the edits; every change sends the whole list of them («replace»)
type Edit = { i: number; word?: string; start?: number; end?: number; hide?: boolean }
const edits = ref<Record<number, Edit>>({})
// The table shows only the words of the clip's window, but the node keeps the edits of every word: start from the node's
// list, then take the window's words from the server (an edit outside the window stays, and is sent again with the rest).
function seedEdits() {
  const o: typeof edits.value = {}
  const node = GE.nodes.find((n) => n.id === props.id)
  for (const e of ((node?.data as any)?.caption_edits || []) as Edit[]) if (e && typeof e.i === 'number') o[e.i] = { ...e }
  for (const w of v.value?.captions.words || []) {
    if (w.edited || w.hidden) o[w.i] = { ...(o[w.i] || {}), i: w.i, word: w.word, start: w.start, end: w.end, hide: !!w.hidden }
    else delete o[w.i]
  }
  edits.value = o
}
function editWord(w: CaptionWord, k: 'word' | 'start' | 'end' | 'hide', value: string | number | boolean) {
  const cur = edits.value[w.i] || { i: w.i, word: w.word, start: w.start, end: w.end, hide: !!w.hidden }
  const next: Edit = { ...cur }
  // an emptied «from» / «to» is «no change»: its override goes (a blank number is not 0 s)
  if ((k === 'start' || k === 'end') && (value === '' || Number.isNaN(value))) delete next[k]
  else (next as any)[k] = value
  edits.value = { ...edits.value, [w.i]: next }
  Object.assign(w, { word: next.word ?? w.word, start: next.start ?? w.start, end: next.end ?? w.end, hidden: !!next.hide, edited: true })
  patch({ caption_edits: Object.values(edits.value) })
}
function resetCaptions() { edits.value = {}; patch({ caption_edits: [] }, true) }
const hasEdits = computed(() => Object.keys(edits.value).length > 0)
const capsOn = computed(() => !!v.value?.captions.on)
const setCaps = (on: boolean) => { if (v.value) v.value.captions = { ...v.value.captions, on }; setParam('captions', on) }

// ---- the preview (a job of the GPU-less renderer) and «Собрать»
const previewJob = ref('')
const running = computed(() => { const j = S.jobs.find((x) => x.id === previewJob.value); return !!j && jobLive(j) })
async function preview() {
  try { await flush(); clearTimeout(timer); await send(); const j = await post(`${url.value}/preview`); S.jobs = [...S.jobs, j]; previewJob.value = j.id } catch (e) { banner((e as Error).message) }
}
const off = onJobEnd((j) => { if (j.id === previewJob.value || (j.kind === 'graph' && j.params?.project === GE.id)) load() })
onBeforeUnmount(off)
const build = async () => { await send(); await runTo([props.id]) }
const stamp = computed(() => `?v=${encodeURIComponent((v.value?.state || '') + (v.value?.preview || ''))}`)
</script>

<template>
  <div class="bp">
    <p v-if="failed" class="warn-line"><Icon name="warn" :size="14" /><span>{{ failed }}</span></p>
    <template v-if="v">
      <div v-if="v.error && v.state === 'error'" class="warn-line"><Icon name="warn" :size="14" /><span>{{ v.error }}</span></div>

      <div class="bp-prev">
        <video v-if="v.preview" class="bp-video" :src="fileUrl(v.preview)! + stamp" controls playsinline loop />
        <div v-else class="bp-video none"><span>{{ t('beat.bp.noPreview') }}</span></div>
        <video v-if="v.file" class="bp-final" :src="fileUrl(v.file)! + stamp" controls playsinline />
      </div>
      <div class="ni-row">
        <button type="button" class="btn" :disabled="busy || running || !v.scenes_ready" :title="v.scenes_ready ? t('beat.bp.previewTitle') : t('beat.bp.needScenes')" @click="preview">
          <Icon name="film" />{{ running ? t('beat.bp.previewing') : t('beat.bp.preview') }}</button>
        <button type="button" class="primary bp-go" :disabled="busy" :title="t('beat.bp.buildTitle')" @click="build"><Icon name="clapper" :size="18" />{{ t('beat.bp.build') }}</button>
      </div>
      <p class="muted small">{{ t('beat.bp.noReshoot') }} <BeatHelp k="noReshoot" /></p>
      <p v-if="!v.scenes_ready" class="muted small">{{ t('beat.bp.scenesNotReady') }}</p>

      <div class="stack"><span class="lbl">{{ t('beat.bp.preset') }} <BeatHelp k="preset" /></span>
        <div class="chips"><button v-for="p in v.presets" :key="p.id" type="button" class="chip" :class="{ on: v.preset === p.id }" @click="setPreset(p.id)">{{ nameOf(p) }}</button></div></div>

      <div class="ni-row">
        <label class="stack grow"><span class="lbl">{{ t('beat.bp.drop') }} <BeatHelp k="drop" /></span>
          <input class="field-in" type="number" step="0.05" min="0" :value="v.drop" @change="v.drop = +($event.target as HTMLInputElement).value; patch({ drop: v.drop })"></label>
        <label class="stack grow"><span class="lbl">BPM <BeatHelp k="bpm" /></span>
          <input class="field-in" type="number" step="0.1" min="40" max="260" :value="v.bpm" @change="v.bpm = +($event.target as HTMLInputElement).value; patch({ bpm: v.bpm })"></label></div>

      <fieldset v-for="g in groups" :key="g" class="bp-group">
        <legend>{{ t(`beat.group.${g}`) }}</legend>
        <div v-for="x in specOf(g)" :key="x.key" class="bp-row">
          <template v-if="x.kind === 'bool'">
            <label class="check-row"><input type="checkbox" :checked="!!v.params[x.key]" @change="setParam(x.key, ($event.target as HTMLInputElement).checked)">{{ nameOf(x) }}</label>
          </template>
          <template v-else>
            <div class="bp-head"><span class="lbl">{{ nameOf(x) }}</span><output>{{ show(x) }}</output></div>
            <input type="range" :min="x.min" :max="x.max" :step="x.step ?? (x.kind === 'int' ? 1 : 0.01)" :value="val(x)" :aria-label="nameOf(x)"
              @input="setParam(x.key, +($event.target as HTMLInputElement).value)">
          </template>
          <span class="bp-end"><HelpQ v-if="help(x)" id="beat" :title="nameOf(x)" :text="help(x)" />
            <button v-if="isSet(x)" type="button" class="ghost bp-reset" :title="t('beat.bp.reset')" :aria-label="`${t('beat.bp.reset')}: ${nameOf(x)}`" @click="setParam(x.key, undefined)"><Icon name="reset" :size="13" /></button></span>
        </div>
      </fieldset>

      <fieldset class="bp-group">
        <legend>{{ t('beat.bp.output') }}</legend>
        <div class="bp-row"><div class="bp-head"><span class="lbl">{{ t('beat.bp.fps') }}</span><BeatHelp k="fps" /></div>
          <div class="seg"><button v-for="n in [30, 60]" :key="n" type="button" :class="{ on: v.fps === n }" @click="v.fps = n; patch({ fps: n })">{{ n }}</button></div></div>
        <div class="bp-row"><div class="bp-head"><span class="lbl">{{ t('beat.bp.loudness') }} <BeatHelp k="loudness" /></span><output>{{ dec(v.loudness.toFixed(1)) }} LUFS</output></div>
          <input type="range" min="-16" max="-6" step="0.5" :value="v.loudness" :aria-label="t('beat.bp.loudness')" @input="v.loudness = +($event.target as HTMLInputElement).value; patch({ loudness: v.loudness })"></div>
      </fieldset>

      <fieldset class="bp-group">
        <legend>{{ t('beat.bp.palette') }} <BeatHelp k="palette" /></legend>
        <div class="bp-pal"><label v-for="k in PAL" :key="k" class="bp-col"><input type="color" :value="bgrToHex(v.palette[k])" :aria-label="t(`beat.bp.pal.${k}`)" @input="setColour(k, ($event.target as HTMLInputElement).value)"><span>{{ t(`beat.bp.pal.${k}`) }}</span></label></div>
      </fieldset>

      <fieldset class="bp-group">
        <legend>{{ t('beat.bp.texts') }}</legend>
        <label class="stack"><span class="lbl">{{ t('beat.bp.title') }} <BeatHelp k="title" /></span>
          <input class="field-in" maxlength="80" :value="v.title" :placeholder="t('beat.bp.titlePh')" @input="setText('title', ($event.target as HTMLInputElement).value)"></label>
        <p v-if="v.cleaned?.title" class="muted small">{{ t('beat.cleaned') }}</p>
        <label class="stack"><span class="lbl">{{ t('beat.bp.hud') }} <BeatHelp k="hud" /></span>
          <input class="field-in" maxlength="80" :value="v.hud" :placeholder="t('beat.bp.hudPh')" @input="setText('hud', ($event.target as HTMLInputElement).value)"></label>
        <p v-if="v.cleaned?.hud" class="muted small">{{ t('beat.cleaned') }}</p>
      </fieldset>

      <fieldset class="bp-group">
        <legend>{{ t('beat.bp.captions') }} <BeatHelp k="captions" /></legend>
        <label class="check-row"><input type="checkbox" :checked="capsOn" @change="setCaps(($event.target as HTMLInputElement).checked)">{{ t('beat.bp.captionsOn') }}</label>
        <template v-if="capsOn">
          <p v-if="!v.captions.words.length" class="muted small">{{ t('beat.bp.noWords') }}</p>
          <div v-else class="bp-caps">
            <div class="bp-cap bp-cap-h"><span>{{ t('beat.bp.word') }}</span><span>{{ t('beat.bp.from') }}</span><span>{{ t('beat.bp.to') }}</span><span>{{ t('beat.bp.hide') }}</span></div>
            <div v-for="w in v.captions.words" :key="w.i" class="bp-cap" :class="{ off: w.hidden }">
              <input class="field-in" :value="w.word" :aria-label="t('beat.bp.word')" spellcheck="false" @change="editWord(w, 'word', ($event.target as HTMLInputElement).value)">
              <input class="field-in" type="number" step="0.01" min="0" :value="w.start" :aria-label="t('beat.bp.from')" @change="editWord(w, 'start', ($event.target as HTMLInputElement).value === '' ? '' : +($event.target as HTMLInputElement).value)">
              <input class="field-in" type="number" step="0.01" min="0" :value="w.end" :aria-label="t('beat.bp.to')" @change="editWord(w, 'end', ($event.target as HTMLInputElement).value === '' ? '' : +($event.target as HTMLInputElement).value)">
              <input type="checkbox" :checked="!!w.hidden" :aria-label="t('beat.bp.hide')" @change="editWord(w, 'hide', ($event.target as HTMLInputElement).checked)"></div>
          </div>
          <button v-if="hasEdits" type="button" class="link-btn" @click="resetCaptions">{{ t('beat.bp.resetCaps') }}</button>
        </template>
      </fieldset>
    </template>
    <p v-else-if="!failed" class="muted small">{{ t('beat.bp.loading') }}</p>
  </div>
</template>

<style scoped>
.bp { display: flex; flex-direction: column; gap: 12px; }
.bp-prev { display: flex; gap: 8px; align-items: flex-start; }
.bp-video, .bp-final { width: 100%; max-width: 270px; aspect-ratio: 9 / 16; border-radius: 10px; background: #000; object-fit: contain; }
.bp-prev:has(.bp-final) .bp-video, .bp-prev:has(.bp-final) .bp-final { max-width: 50%; }
.bp-video.none { display: grid; place-items: center; border: 1px dashed var(--rule-3); background: none; color: var(--muted); font-size: 12px; text-align: center; padding: 8px; }
.bp-go { flex: 1; width: auto; }
.bp-group { display: flex; flex-direction: column; gap: 10px; margin: 0; padding: 10px 12px 12px; border-radius: 10px; border: 1px solid var(--rule-2); min-width: 0; }
.bp-group legend { padding: 0 6px; color: var(--soft); font-size: 12.5px; font-weight: 600; }
.bp-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 2px 6px; align-items: center; }
.bp-row > input[type=range], .bp-row > .seg { grid-column: 1; }
.bp-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; grid-column: 1; }
.bp-head output { color: var(--muted); font-variant-numeric: tabular-nums; font-size: 12px; }
.bp-end { grid-column: 2; grid-row: 1 / span 2; display: inline-flex; align-items: center; gap: 2px; }
.bp-reset { padding: 2px; }
.bp-pal { display: flex; gap: 14px; flex-wrap: wrap; }
.bp-col { display: flex; flex-direction: column; align-items: center; gap: 4px; font-size: 12px; color: var(--soft); }
.bp-col input { width: 52px; height: 36px; padding: 0; border: 1px solid var(--rule-input); border-radius: 8px; background: var(--field); cursor: pointer; }
.bp-caps { display: flex; flex-direction: column; gap: 4px; max-height: 280px; overflow: auto; padding-right: 2px; }
.bp-cap { display: grid; grid-template-columns: minmax(0, 1.5fr) 68px 68px 28px; gap: 4px; align-items: center; }
.bp-cap.off input.field-in { opacity: .45; text-decoration: line-through; }
.bp-cap-h { color: var(--muted); font-size: 11.5px; position: sticky; top: 0; background: var(--panel); }
.bp-cap .field-in { min-width: 0; padding: 4px 6px; font-size: 12.5px; }
</style>
