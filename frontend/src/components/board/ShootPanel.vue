<script setup lang="ts">
// How the video is shot: the model (phase 10: H3, LTX 2.5, LTX 2.3, WAN 2.2 5B - and what it won't do with this
// storyboard), the quality, the LoRA, your own track over it (LTX 2.3: the scenes shot to it), the output (RTX,
// HDR10, 48 fps), and the button that shoots, mixes or re-finishes - whichever is left to do, with the time it takes.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import ShootConfirm from './ShootConfirm.vue'
import LoraSet from '../LoraSet.vue'
import HelpQ from '../HelpQ.vue'
import ModelPick from '../ModelPick.vue'
import { S, lorasFor } from '../../lib/store'
import { P, output, projectCall, scheduleSave, startRender } from '../../lib/project'
import { useShoot } from '../../lib/shoot'
import { dec, mins, mmss } from '../../lib/format'
import type { Plan } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ p: Plan }>()
const { st, q, cur, eta, done, mainLabel, mainIcon, note, model, modelWarn, foreign, quick } = useShoot(() => props.p)
// a long shoot asks first («Перед съёмкой»); only the assembly left - straight away
const ask = ref(false)
const shoot = () => { if (quick.value) startRender(); else ask.value = true }
const waiting = computed(() => P.after?.pid === P.proj?.id)
const used = computed(() => (st.value.loras || []) as { id: string; name: string; strength: number }[])
const rest = computed(() => lorasFor(st.value.video_model || 'h3').filter((l) => l.verdict !== 'blocked' && !used.value.some((u) => u.id === l.id)))
const setQuality = (id: string) => { st.value.quality = id; scheduleSave('settings') }

// the model: another one shoots every scene anew (its shots have keys of their own); the old ones stay in the cache.
// That is minutes to half an hour: asked first, with the scenes and the time
function setModel(id: string) {
  const to = (S.cfg?.video_models || []).find((m) => m.id === id), n = props.p.scenes.length, secs = mins(cur.value.per_scene * n + 40)
  if (id === (st.value.video_model || 'h3') || !to) return
  const shot = !!P.est?.[cur.value.id]?.cached
  if (!confirm(shot ? t('board.shoot.modelAsk', { m: to.name, x: t('board.scenesAcc', n), t: secs, old: model.value?.name || 'H3' })
    : t('board.shoot.modelAskNew', { m: to.name, x: t('board.scenesAcc', n), t: secs }))) return
  st.value.video_model = id
  if (!to.track) st.value.track_sync = false
  scheduleSave('settings')
}
const sizeOf = (id: string) => model.value?.sizes[id]?.w || q.value.find((x) => x.id === id)?.w
const synced = computed(() => !!st.value.track_sync && !!model.value?.track)
function setSync(e: Event) { st.value.track_sync = (e.target as HTMLInputElement).checked; scheduleSave('settings') }
function addLora(e: Event) {
  const l = S.loras.find((x) => x.id === (e.target as HTMLSelectElement).value)
  if (l) { st.value.loras = [...used.value, { id: l.id, name: l.name, strength: l.strength ?? 0.8 }]; scheduleSave('settings') }
}
const delLora = (i: number) => { st.value.loras.splice(i, 1); scheduleSave('settings') }

// the output
const o = computed(() => output(st.value))
const w = computed(() => sizeOf(cur.value.id) || cur.value.w || 960)
function setOut(patch: Record<string, unknown>) {
  st.value.output = { ...o.value, ...patch }
  if (st.value.output.size === 'off') st.value.output.hdr = false
  st.value.rtx = st.value.output.size !== 'off'
  scheduleSave('settings')
}

// your own track over the whole video (music.py mixes it over the assembled scenes)
const trk = computed(() => st.value.track)
function trackUp(f?: File) {
  if (!f) return
  const fd = new FormData()
  fd.append('file', f)
  projectCall('POST', '/track', fd)
}
const pct = (v: number) => `${Math.round(v * 100)}%`, sec = (v: number) => `${dec((+v).toFixed(1))} ${t('common.s')}`
const sliders = computed(() => [
  { key: 'volume', label: t('board.shoot.volume'), min: 0, max: 1.5, step: 0.05, fmt: pct },
  { key: 'scene_volume', label: t('board.shoot.sceneVolume'), min: 0, max: 1, step: 0.05, fmt: pct },
  { key: 'offset', label: t('board.shoot.offset'), min: 0, max: Math.max(0, Math.floor((trk.value?.duration || 0) - 5)), step: 0.5, fmt: sec },
  { key: 'fade_out', label: t('board.shoot.fadeOut'), min: 0, max: 6, step: 0.5, fmt: sec },
])
function noMusic(e: Event) {
  const box = e.target as HTMLInputElement, on = box.checked
  if (on && !confirm(t('board.shoot.noMusicAsk'))) { box.checked = false; return }
  props.p.no_music = on
  scheduleSave()
}
</script>

<template>
  <section class="shoot">
    <div class="stack" style="gap:8px"><span class="lbl">{{ t('idea.model') }} <HelpQ id="shoot" term="Модель" /></span>
      <ModelPick :model-value="st.video_model" compact @update:model-value="setModel" />
      <div v-for="x in modelWarn" :key="x" class="warn-line"><Icon name="warn" :size="14" /><span>{{ x }}</span></div>
      <span v-if="model && model.id !== 'h3'" class="muted" style="font-size:12px">{{ t('board.shoot.otherModel', { m: model.name }) }}</span></div>
    <div class="stack" style="gap:8px"><span class="lbl">{{ t('board.shoot.quality') }} <HelpQ id="shoot" term="Качество" /></span>
      <div class="seg"><button v-for="x in q" :key="x.id" type="button" :class="{ on: x.id === cur.id }" @click="setQuality(x.id)">{{ x.id === 'final' ? t('board.quality.final') : t('board.quality.draft') }}<small>{{ sizeOf(x.id) }} · ~{{ mins(eta(x)) }}</small></button></div></div>
    <div class="stack" style="gap:8px"><div class="sec-head"><span class="lbl">LoRA <HelpQ id="shoot" term="LoRA" /></span>
        <select v-if="rest.length" class="ghost" :aria-label="t('board.shoot.addLora')" value="" @change="addLora"><option value="">{{ t('board.shoot.fromLibrary') }}</option><option v-for="l in rest" :key="l.id" :value="l.id">{{ l.name }}</option></select></div>
      <div v-for="(u, i) in used" :key="u.id" class="lora"><span :title="u.name">{{ u.name }}</span>
        <input type="range" min="0" max="1.5" step="0.05" :value="u.strength" :aria-label="t('board.shoot.strengthOf', { x: u.name })" @input="u.strength = +($event.target as HTMLInputElement).value" @change="scheduleSave('settings')">
        <b>{{ (+u.strength).toFixed(2) }}</b><button type="button" :aria-label="t('board.shoot.removeX', { x: u.name })" @click="delLora(i)">×</button></div>
      <span v-if="!used.length" class="muted" style="font-size:13px">{{ t('board.takes.loraMode.none') }}</span>
      <span v-if="model && used.some((u) => foreign(u.id))" class="warn-line"><Icon name="warn" :size="14" />{{ t('board.shoot.foreignLora', { m: model.name }) }}</span></div>
    <div class="stack" style="gap:8px"><span class="lbl">{{ t('loraset.pics') }} <small>{{ t('loraset.picsSub') }}</small></span>
      <LoraSet pics-only :pics="st.pic_loras || {}" @update:pics="st.pic_loras = $event; scheduleSave('settings')" /></div>

    <div v-if="!trk" class="stack" style="gap:8px"><span class="lbl">{{ t('board.shoot.music') }} <HelpQ id="shoot" term="Музыка" /></span>
      <label class="btn" style="cursor:pointer"><Icon name="music" />{{ t('board.shoot.ownTrack') }}<input type="file" accept="audio/*,.mp3,.wav,.m4a,.flac,.ogg" hidden @change="trackUp(($event.target as HTMLInputElement).files?.[0])"></label>
      <span class="muted" style="font-size:12px">{{ model && !model.sound ? t('board.shoot.mutedVideo', { m: model.name }) : t('board.shoot.ownMusic', { m: model?.short || 'H3' }) }}</span>
      <span v-if="model?.track" class="muted" style="font-size:12px">{{ t('board.shoot.canTrack', { m: model.name }) }}</span>
      <label v-if="p.no_music" class="check-row" :title="t('board.shoot.noMusicTitle')">
        <input type="checkbox" :checked="!!p.no_music" @change="noMusic">{{ t('board.shoot.noMusic') }} <HelpQ id="shoot" term="В сценах без музыки" /></label></div>
    <div v-else class="stack" style="gap:8px"><div class="sec-head"><span class="lbl">{{ t('board.shoot.music') }} <HelpQ id="shoot" term="Музыка" /> · {{ trk.name }} · {{ mmss(trk.duration || 0) }}</span>
        <button type="button" class="ghost" :aria-label="t('board.shoot.removeTrack')" @click="projectCall('DELETE', '/track')">×</button></div>
      <audio controls preload="none" :src="`/api/projects/${P.proj!.id}/files/${encodeURIComponent(trk.file)}`" style="width:100%;height:32px" />
      <div v-for="x in sliders.filter((y) => !(synced && y.key === 'scene_volume'))" :key="x.key" class="tk"><span>{{ x.label }}</span>
        <input type="range" :min="x.min" :max="x.max" :step="x.step" :value="trk[x.key]" :aria-label="x.label"
          @input="trk[x.key] = +($event.target as HTMLInputElement).value" @change="projectCall('PUT', '/track', { [x.key]: +($event.target as HTMLInputElement).value })"><b>{{ x.fmt(trk[x.key]) }}</b></div>
      <div v-if="(trk.duration || 0) - trk.offset < p.seconds" class="warn-line"><Icon name="warn" :size="14" />{{ t('board.shoot.trackShort') }}</div>
      <label v-if="model?.track" class="check-row" :title="t('board.shoot.syncTitle')">
        <input type="checkbox" :checked="!!st.track_sync" @change="setSync">{{ t('board.shoot.sync') }} <HelpQ id="shoot" term="Снимать под трек" /></label>
      <span v-if="st.track_sync && model?.track" class="muted" style="font-size:12px">{{ t('board.shoot.syncNote') }}</span>
      <label v-if="!synced" class="check-row" :title="t('board.shoot.noMusicTitle')">
        <input type="checkbox" :checked="!!p.no_music" @change="noMusic">{{ t('board.shoot.noMusic') }} <HelpQ id="shoot" term="В сценах без музыки" /></label></div>

    <div class="stack" style="gap:8px"><span class="lbl">{{ t('board.shoot.output') }} <HelpQ id="shoot" term="Выход" /></span>
      <div class="seg three-col">
        <button type="button" :class="{ on: o.size === 'off' }" @click="setOut({ size: 'off' })">{{ t('board.shoot.asShot') }}<small>{{ w }}</small></button>
        <button type="button" :class="{ on: o.size === '1080p' }" @click="setOut({ size: '1080p' })">1080p<small>RTX</small></button>
        <button type="button" :class="{ on: o.size === '4k' }" @click="setOut({ size: '4k' })">4K<small>RTX</small></button></div>
      <label class="check-row" :title="t('board.shoot.hdrTitle')">
        <input type="checkbox" :checked="o.hdr && o.size !== 'off'" :disabled="o.size === 'off'" @change="setOut({ hdr: ($event.target as HTMLInputElement).checked })">HDR10</label>
      <label class="check-row" :title="t('board.shoot.fpsTitle')">
        <input type="checkbox" :checked="o.fps48" @change="setOut({ fps48: ($event.target as HTMLInputElement).checked })">{{ t('board.shoot.fps48') }}</label></div>

    <router-link v-if="done" class="primary" :to="`/p/${P.proj!.id}/video`"><Icon name="play" :size="18" />{{ t('board.shoot.openVideo') }} · {{ done.video_up ? '1080p' : done.width }}</router-link>
    <button v-else-if="waiting" type="button" class="primary" disabled><i class="spin" />{{ t('board.pre.waiting') }}</button>
    <button v-else type="button" class="primary" @click="shoot"><Icon :name="mainIcon" :size="18" />{{ mainLabel }} · ~{{ mins(eta(cur)) }}</button>
    <ShootConfirm :p="p" :open="ask" @close="ask = false" />
    <span class="foot-note">{{ note }}<br>{{ t('board.shoot.fixNote') }}</span>
  </section>
</template>
