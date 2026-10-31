<script setup lang="ts">
// Several scenes picked at once (Ctrl / Shift, an episode's number): what they are about when they are one episode,
// their frames, and what can be set for all of them - the camera, the shot, the length - where they differ it says
// «разное»; the writer's «Улучшить» / «Другой вариант» for them all, pin or unpin them, delete them.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import { S } from '../../lib/store'
import { P, liveWriter, rewrite, scheduleSave } from '../../lib/project'
import { episodes, isRaw, removeScenes, shotPng } from '../../lib/board'
import { CAMERAS, FRAMINGS } from '../../lib/consts'
import { mmss } from '../../lib/format'
import type { Plan } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ p: Plan }>()
const list = computed(() => P.picked.map((i) => props.p.scenes[i]).filter(Boolean))
const idx = computed(() => list.value.map((s) => s.index))
const writer = computed(() => (P.proj ? liveWriter(P.proj.id) : undefined))
const ep = computed(() => { const e = episodes(props.p).find((x) => x.scenes.length === list.value.length && x.scenes.every((s) => P.picked.includes(s.index))); return e || null })
const range = computed(() => {   // 3, 4, 5, 9 -> «3–5, 9»
  const out: string[] = []
  for (let k = 0; k < idx.value.length; k++) {
    const a = idx.value[k]; let b = a
    while (idx.value[k + 1] === b + 1) { b++; k++ }
    out.push(a === b ? String(a + 1) : `${a + 1}–${b + 1}`)
  }
  return out.join(', ')
})
const same = (k: string) => { const v = new Set(list.value.map((s) => s[k])); return v.size === 1 ? [...v][0] : '' }
function setAll(k: string, v: unknown) { if (v === '') return; for (const s of list.value) s[k] = v; scheduleSave() }
const model = computed(() => (S.cfg?.video_models || []).find((m) => m.id === (P.proj!.settings.video_model || 'h3')))
const lens = computed(() => (props.p.clip ? [] : [5, 10, 15].filter((x) => x <= (model.value?.max_seconds || 5))))
const lenNow = computed(() => { const v = new Set(list.value.map((s) => Number(s.seconds) || 5)); return v.size === 1 ? [...v][0] : 0 })
function setLen(x: number) { for (const s of list.value) { if (x === 5 && !props.p.scene_seconds) delete s.seconds; else s.seconds = x } scheduleSave() }
const writable = computed(() => list.value.filter((s) => !isRaw(s) && !s.locked).map((s) => s.index))
const allLocked = computed(() => list.value.every((s) => s.locked))
function pin() { const on = !allLocked.value; for (const s of list.value) s.locked = on; scheduleSave() }
function del() {
  if (props.p.scenes.length - list.value.length < 1 || !confirm(t('board.group.delAsk', { n: list.value.length }))) return
  removeScenes(props.p, new Set(idx.value))   // in a clip, the others stay on their bars
  P.picked = []
  P.sel = Math.max(0, Math.min(idx.value[0], props.p.scenes.length - 1))
  scheduleSave()
}
const val = (e: Event) => (e.target as HTMLSelectElement).value
</script>

<template>
  <div class="insp-head"><h2>{{ t('board.group.title', list.length) }}</h2>
    <span>{{ t('board.group.range', { list: range }) }} · {{ mmss(list[0]?.start || 0) }}–{{ mmss(list[list.length - 1]?.end || 0) }}</span></div>
  <div class="insp stack gp" style="gap:14px">
    <button type="button" class="link-btn" style="align-self:flex-start;margin:0" @click="P.picked = []">{{ t('board.group.clear') }}</button>
    <div class="gp-thumbs"><button v-for="s in list.slice(0, 12)" :key="s.index" type="button" :title="s.ru" @click="P.picked = []; P.sel = s.index">
      <img v-if="shotPng(s.index)" :src="shotPng(s.index)!" alt=""><b>{{ s.index + 1 }}</b></button></div>
    <div v-if="ep" class="stack" style="gap:6px"><span class="lbl">{{ t('board.group.episode') }} <small>{{ t('board.group.episodeSub') }}</small></span>
      <p class="gp-about">{{ ep.about }}</p></div>
    <div class="row2">
      <label><span class="lbl">{{ t('board.insp.camera') }} <small>{{ t('board.group.forAll') }}</small></span>
        <select class="field-in" :value="same('camera')" @change="setAll('camera', val($event))"><option v-if="!same('camera')" value="">{{ t('board.group.mixed') }}</option>
          <option v-for="(v, k) in CAMERAS" :key="k" :value="k">{{ v }}</option></select></label>
      <label><span class="lbl">{{ t('board.insp.framing') }} <small>{{ t('board.group.forAll') }}</small></span>
        <select class="field-in" :value="same('framing')" @change="setAll('framing', val($event))"><option v-if="!same('framing')" value="">{{ t('board.group.mixed') }}</option>
          <option v-for="(v, k) in FRAMINGS" :key="k" :value="k">{{ v }}</option></select></label>
    </div>
    <div v-if="lens.length > 1" class="stack" style="gap:6px"><span class="lbl">{{ t('board.group.lenEach') }} <small v-if="!lenNow">{{ t('board.group.mixed') }}</small></span>
      <div class="seg"><button v-for="x in lens" :key="x" type="button" :class="{ on: lenNow === x }" @click="setLen(x)">{{ x }} {{ t('common.s') }}</button></div></div>
    <div v-if="!p.manual" class="acts">
      <button type="button" class="btn" :disabled="!writable.length || !!writer" @click="rewrite('improve', writable)"><Icon name="spark" />{{ t('board.group.improve', { n: writable.length }) }}</button>
      <button type="button" class="btn" :disabled="!writable.length || !!writer" @click="rewrite('variant', writable)"><Icon name="shuffle" />{{ t('board.group.variant', { n: writable.length }) }}</button></div>
    <div class="acts">
      <button v-if="!p.manual" type="button" class="btn" @click="pin"><Icon name="lock" :size="14" />{{ allLocked ? t('board.group.unpin') : t('board.group.pin') }}</button>
      <button type="button" class="btn danger" :disabled="p.scenes.length - list.length < 1" @click="del"><Icon name="trash" />{{ t('board.group.del', { n: list.length }) }}</button></div>
  </div>
</template>
