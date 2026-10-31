<script setup lang="ts">
// «Места» (app/places.py): a picture of each place of the video - the start frames' second reference, so every scene
// of a place is the same room or street from its own camera. «Собрать места» asks the writer to group the scenes;
// a place's picture is drawn by Krea 2 from its words (empty of people) or is the user's own photo. A scene is put in
// a place in its panel («Место»).
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import PicLoraLine from '../PicLoraLine.vue'
import HelpQ from '../HelpQ.vue'
import { post } from '../../lib/api'
import { S, banner } from '../../lib/store'
import { P, flushSave, projectCall, scheduleSave } from '../../lib/project'
import { vZoom } from '../../lib/zoom'
import type { Plan } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ p: Plan }>()
const proj = computed(() => P.proj!)
const places = computed(() => (props.p.places || []) as Record<string, any>[])
const newScenes = computed(() => props.p.scenes.filter((x) => x.kind === 'new').length)
const scenesOf = (id: string) => props.p.scenes.filter((x) => x.kind === 'new' && x.place === id).map((x) => x.index + 1)
const fileUrl = (f: string) => `/api/projects/${proj.value.id}/files/${encodeURIComponent(f)}`
const busy = computed(() => S.jobs.some((j) => ['places', 'place'].includes(j.kind) && (j.status === 'running' || j.status === 'queued') && j.params?.project === proj.value.id))
const missing = computed(() => places.value.filter((x) => !x.photo && x.en).length)
const edit = ref(false)
const val = (e: Event) => (e.target as HTMLInputElement).value

async function job(path: string, body: unknown = {}) {
  await flushSave()
  try { S.jobs = [...S.jobs, await post(`/api/projects/${proj.value.id}${path}`, body)] } catch (e) { banner((e as Error).message) }
}
function group() {
  if (places.value.length && !confirm(t('board.places.regroupAsk'))) return
  job('/places/group')
}
const draw = (ids?: string[]) => job('/places/draw', ids ? { places: ids } : {})
const setPlace = (id: string, k: 'name_ru' | 'en', v: string) => projectCall('PUT', `/places/${id}`, { [k]: v })
function del(x: Record<string, any>) {
  if (!confirm(t('board.places.delAsk', { name: x.name_ru }))) return
  projectCall('DELETE', `/places/${x.id}`)
}
// off: the frames are drawn from the words as before; the places and their pictures stay for later
function setOn(e: Event) {
  const on = (e.target as HTMLInputElement).checked
  if (on) delete props.p.places_off; else props.p.places_off = true
  scheduleSave()
}
async function photoUp(id: string, f?: File) {
  if (!f) return
  const fd = new FormData()
  fd.append('file', f)
  await projectCall('POST', `/places/${id}/photo`, fd)
}
</script>

<template>
  <section v-if="p.mode !== 'none' && newScenes" class="look noimg places-card"><div>
    <div class="row"><b>{{ t('board.places.title') }}</b><HelpQ id="look" term="Места" />
      <span v-if="places.length" class="muted small">{{ t('board.places.count', { n: places.length }) }}</span>
      <span style="flex:1" />
      <button v-if="places.length" type="button" class="ghost" :aria-pressed="edit" @click="edit = !edit">{{ edit ? t('board.look.done') : t('board.look.edit') }}</button></div>
    <label v-if="places.length" class="check-row" style="margin-top:6px" :title="t('board.places.onTitle')">
      <input type="checkbox" :checked="!p.places_off" @change="setOn">{{ t('board.places.on') }}</label>
    <p v-if="!places.length" class="muted small">{{ t('board.places.empty') }}</p>
    <div v-else class="places-grid" :class="{ off: p.places_off }">
      <div v-for="x in places" :key="x.id" class="place">
        <div class="place-img"><img v-if="x.photo" v-zoom :src="fileUrl(x.photo)" :alt="x.name_ru"><span v-else class="muted small">{{ t('board.places.noPicture') }}</span></div>
        <template v-if="edit">
          <input class="field-in" :value="x.name_ru" :aria-label="t('board.places.name')" @change="setPlace(x.id, 'name_ru', val($event))">
          <textarea class="field-in" rows="3" :value="x.en" :aria-label="t('board.places.words')" :placeholder="t('board.places.wordsHint')" @change="setPlace(x.id, 'en', val($event))" />
        </template>
        <template v-else>
          <b class="place-name">{{ x.name_ru }}</b>
          <span class="muted small">{{ scenesOf(x.id).length ? t('board.places.scenes', { list: scenesOf(x.id).join(', ') }) : t('board.places.noScenes') }}</span>
          <span v-if="P.showEn" class="en small">{{ x.en }}</span>
        </template>
        <div v-if="x.stale" class="warn-line small"><Icon name="warn" :size="13" />{{ t('board.places.stale') }}</div>
        <div class="acts">
          <button v-if="!x.photo || x.drawn" type="button" class="btn" :disabled="busy || !x.en" :title="t('board.places.drawTitle')" @click="draw([x.id])"><Icon name="brush" />{{ x.drawn ? t('board.places.again') : t('board.places.draw') }}</button>
          <label class="btn" style="cursor:pointer"><Icon name="image" />{{ x.photo ? t('board.look.otherPhoto') : t('board.places.own') }}<input type="file" accept="image/png,image/jpeg,image/webp" hidden @change="photoUp(x.id, ($event.target as HTMLInputElement).files?.[0])"></label>
          <button v-if="edit" type="button" class="btn danger" @click="del(x)"><Icon name="trash" />{{ t('board.look.remove') }}</button></div>
      </div>
    </div>
    <div class="acts" style="margin-top:8px">
      <button type="button" class="btn" :disabled="busy" :title="t('board.places.groupTitle')" @click="group"><Icon name="spark" />{{ places.length ? t('board.places.regroup') : t('board.places.group') }}</button>
      <button v-if="missing" type="button" class="btn" :disabled="busy" @click="draw()"><Icon name="brush" />{{ t('board.places.drawAll', { n: missing }) }}</button>
      <button v-if="edit" type="button" class="btn" @click="projectCall('POST', '/places', {})"><Icon name="plus" />{{ t('board.places.add') }}</button></div>
    <PicLoraLine :models="['krea']" :hint="t('loraset.placesHint')" />
    <p v-if="places.some((x) => x.photo)" class="muted small" style="margin-top:6px">{{ t('board.places.hint') }}</p>
  </div></section>
</template>

<style scoped>
.places-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin-top: 8px; }
.place { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.place-img { aspect-ratio: 16 / 9; border-radius: 8px; overflow: hidden; background: var(--field); border: 1px solid var(--rule); display: grid; place-items: center; }
.place-img img { width: 100%; height: 100%; object-fit: cover; display: block; border-radius: 0; }
.place-name { font-size: 14px; }
.places-card .acts { flex-wrap: wrap; }
.places-grid.off { opacity: .55; }
</style>
