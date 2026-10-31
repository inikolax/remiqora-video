<script setup lang="ts">
// Who is in the frame, word for word in every scene: the hero's (or heroes') look, or the world without people;
// «Изменить» edits each character's gender, age, look and outfit in Russian (the English follows by «Обновить промт
// по тексту», or edit it under EN); with several people a character can be added (up to 3) or removed. A character's
// voice by sample (render.voice_ref): LTX 2.3 scenes where only they speak are shot with ID-LoRA in that voice.
// With people in the video and the form closed, the tab is a casting (CastingCard): portraits, Krea's tries, the face
// in the shot scenes; the video's style, sound, «Держать лицо по фото» and «Нарисовать кадры всем сценам» under it.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import HelpQ from '../HelpQ.vue'
import VoiceRecorder from '../VoiceRecorder.vue'
import CastingCard from './CastingCard.vue'
import { post } from '../../lib/api'
import { S, banner } from '../../lib/store'
import { P, flushSave, projectCall, scheduleSave } from '../../lib/project'
import { redrawUnlike, unlikeOf } from '../../lib/shoot'
import { vZoom } from '../../lib/zoom'
import { GENDERS } from '../../lib/consts'
import type { Plan } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ p: Plan }>()
const proj = computed(() => P.proj!)

// a character's photo: their own, or the project's photo for the hero described from it
const castPhoto = (c: Record<string, any>) => (c.photo ? `/api/projects/${proj.value.id}/files/${encodeURIComponent(c.photo)}`
  : c.from_photo && proj.value.settings.photo ? `/api/projects/${proj.value.id}/photo` : null)
const photos = computed(() => (props.p.mode === 'none' ? [] : (props.p.cast || []).map(castPhoto).filter(Boolean) as string[]))
const photo = computed(() => photos.value[0] || (proj.value.settings.photo ? `/api/projects/${proj.value.id}/photo` : null))
const look = computed(() => {
  const p = props.p
  if (p.mode === 'none') return { label: t('board.look.world'), ru: p.world?.ru || '', en: p.world?.en || '' }
  const cast = p.cast || []
  const one = (c: Record<string, any>, i: number) => `${cast.length > 1 ? `${i + 1}. ` : ''}${/\d/.test((c.ru || '').slice(0, 14)) ? '' : t('board.look.age', { n: c.age }) + ' '}${c.ru || ''}${c.outfit_ru && !(c.ru || '').includes(c.outfit_ru.slice(0, 20)) ? ' ' + c.outfit_ru : ''}`
  return { label: cast.length > 1 ? t('board.look.heroes') : cast[0]?.gender === 'female' ? t('board.look.heroine') : t('board.look.hero'),
    ru: cast.map(one).join('\n'), en: cast.map((c: Record<string, any>) => `${c.en} Wearing ${c.outfit_en}`).join('\n') }
})
const several = computed(() => props.p.mode === 'several')
const dirty = computed(() => (props.p.mode === 'none' ? !!props.p.world?.ru_dirty : (props.p.cast || []).some((c: Record<string, any>) => c.ru_dirty)))
const save = () => { scheduleSave(); flushSave() }

function setWorld(k: 'ru' | 'en', v: string) {
  const p = props.p
  p.world = { ...(p.world || {}) }
  if (k === 'ru') { p.world.ru = v; p.world.ru_dirty = true } else p.world.en = v
  save()
}
function setCast(i: number, k: string, v: string) {
  const c = props.p.cast![i]
  if (k === 'age') c.age = Math.max(21, +v || 21)
  else c[k] = v
  if (['ru', 'outfit_ru', 'gender', 'age'].includes(k)) {
    c.ru_dirty = true
    if (castPhoto(c)) c.photo_stale = true   // the portrait shows the look before the edit (CastingCard)
  }
  save()
}
async function castPhotoUp(i: number, f?: File) {
  if (!f) return
  const fd = new FormData()
  fd.append('file', f)
  await projectCall('POST', `/cast/${i}/photo`, fd)   // the description is the user's call: «Описать по фото»
}
// «Нарисовать по описанию»: Krea 2 paints the character from the look; the picture becomes their photo (app/hero.py)
async function draw(i: number) {
  await flushSave()
  try { S.jobs = [...S.jobs, await post(`/api/projects/${proj.value.id}/cast/${i}/draw`)] } catch (e) { banner((e as Error).message) }
}
async function describe(i: number) {
  await flushSave()
  try { S.jobs = [...S.jobs, await post(`/api/projects/${proj.value.id}/cast/${i}/describe`)] } catch (e) { banner((e as Error).message) }
}
function addHero() {
  props.p.cast!.push({ gender: 'female', age: 30, ru: '', outfit_ru: '', en: '', outfit_en: '', ru_dirty: true })
  save()
  banner(t('board.look.added', { n: props.p.cast!.length }), 'info')
}
function delHero(i: number) {
  const n = i + 1
  if (!confirm(t('board.look.delAsk', { n }))) return
  props.p.cast!.splice(i, 1)
  for (const sc of props.p.scenes) if (sc.who) sc.who = sc.who.filter((x: number) => x !== n).map((x: number) => (x > n ? x - 1 : x))
  save()
}
async function translate() {
  await flushSave()
  const idx = props.p.mode === 'none' ? [] : (props.p.cast || []).map((c: Record<string, any>, i: number) => (c.ru_dirty ? i : -1)).filter((i: number) => i >= 0)
  try { S.jobs = [...S.jobs, await post(`/api/projects/${proj.value.id}/rewrite`, { how: 'looks', scenes: idx })] } catch (e) { banner((e as Error).message) }
}
// «Нарисовать кадры всем сценам» (app/frames.py): every new scene with a hero who has a photo starts from a frame
// drawn by FLUX.2 Klein - the face from the photo in the scene's place
const frameScenes = computed(() => props.p.mode === 'none' ? 0 : props.p.scenes.filter((x) => x.kind === 'new' && x.raw == null).length)
const framing = computed(() => S.jobs.some((j) => j.kind === 'frame' && (j.status === 'running' || j.status === 'queued') && j.params?.project === proj.value.id))
const unlike = computed(() => (props.p.mode === 'none' ? [] : unlikeOf(props.p)))
async function framesAll() {
  if (!confirm(t('board.look.framesAsk', { n: frameScenes.value }))) return
  await flushSave()
  try { S.jobs = [...S.jobs, await post(`/api/projects/${proj.value.id}/frames`, {})] } catch (e) { banner((e as Error).message) }
}
function refPhoto(e: Event) {
  const box = e.target as HTMLInputElement, on = box.checked, n = props.p.scenes.filter((x) => x.kind === 'new').length
  if (!confirm(t(on ? 'board.look.refOn' : 'board.look.refOff', { n }))) { box.checked = !on; return }
  props.p.ref_photo = on; scheduleSave()
}
function refAll(e: Event) {
  const box = e.target as HTMLInputElement, on = box.checked
  if (!confirm(t(on ? 'board.look.refAllOn' : 'board.look.refAllOff'))) { box.checked = !on; return }
  props.p.ref_all = on; scheduleSave()
}
const val = (e: Event) => (e.target as HTMLInputElement).value
const casting = computed(() => props.p.mode !== 'none' && !P.editLook)
const openScene = (i: number) => { P.picked = []; P.sel = i; P.tab = 'scenes' }

// ---- a character's voice by sample ----
const fileUrl = (f: string) => `/api/projects/${proj.value.id}/files/${encodeURIComponent(f)}`
const q = computed(() => proj.value.settings.quality || 'draft')
const shotScenes = computed(() => props.p.scenes.filter((x) => P.est?.[q.value]?.scenes?.[x.index] === 'cached'))
// the scenes that will take this voice: shot by LTX 2.3, all their lines this character's
const voiced = (i: number) => props.p.scenes.filter((x) => (x.model || proj.value.settings.video_model || 'h3') === 'ltx23'
  && (x.lines || []).some((l: any) => (l.text || '').trim()) && (x.lines || []).every((l: any) => !(l.text || '').trim() || (l.who || 1) === i + 1)).length
async function voiceUp(i: number, f?: File) {
  if (!f) return
  const fd = new FormData()
  fd.append('file', f)
  await projectCall('POST', `/cast/${i}/voice`, fd)
}
async function voiceFromScene(i: number, ev: Event) {
  const sel = ev.target as HTMLSelectElement, raw = sel.value
  sel.value = ''
  if (raw === '') return
  const n = +raw
  await flushSave()
  try { S.jobs = [...S.jobs, await post(`/api/projects/${proj.value.id}/cast/${i}/voice/scene`, { scene: n })] } catch (e) { banner((e as Error).message) }
}
const setVoice = (i: number, k: 'from' | 'secs', v: string) => projectCall('PUT', `/cast/${i}/voice`, { [k]: +v })
</script>

<template>
  <template v-if="casting">
    <CastingCard :p="p" @edit="P.editLook = true" @open="openScene" />
    <div class="cc-foot">
      <div class="facts"><span><span>{{ t('board.look.style') }} · </span>{{ p.style_en }}</span><span><span>{{ t('board.look.sound') }} · </span>{{ p.audio_en }}</span></div>
      <template v-if="photo">
        <label class="check-row" :title="t('board.look.refTitle')">
          <input type="checkbox" :checked="!!p.ref_photo" @change="refPhoto">{{ t('board.look.ref') }} <HelpQ id="look" term="Держать лицо по фото" /></label>
        <label v-if="p.ref_photo" class="check-row sub-check" :title="t('board.look.refAllTitle')">
          <input type="checkbox" :checked="!!p.ref_all" @change="refAll">{{ t('board.look.refAll') }} <HelpQ id="look" term="На всех сценах" /></label>
        <div v-if="frameScenes" class="acts"><button type="button" class="btn" :disabled="framing" :title="t('board.look.framesTitle')" @click="framesAll"><Icon name="spark" />{{ t('board.look.frames') }}</button>
          <button v-if="unlike.length" type="button" class="btn" :disabled="framing" :title="t('board.look.unlikeTitle', { list: unlike.map((i) => i + 1).join(', ') })" @click="redrawUnlike"><Icon name="retake" />{{ t('board.look.unlike', { n: unlike.length }) }}</button>
          <HelpQ id="look" term="Нарисовать кадры всем сценам" /></div>
      </template>
      <div v-for="x in (p.cast_problems_ru || p.cast_problems || [])" :key="x" class="warn-line"><Icon name="warn" :size="14" />{{ x }}</div>
    </div>
  </template>
  <section v-else class="look" :class="{ noimg: !photo }">
    <div v-if="photo" class="look-photos"><img v-for="u in (photos.length ? photos : [photo])" :key="u" v-zoom :src="u" :alt="t('board.look.photoAlt')"></div>
    <div><div class="row"><b>{{ look.label }}</b><HelpQ id="look" term="Кастинг" /><span class="pill"><Icon name="lock" :size="14" />{{ t('board.look.verbatim') }}</span>
        <span v-if="p.mode === 'none'">{{ t('board.look.noPeople') }}</span>
        <span v-if="(p.cast || []).some((c: any) => c.from_photo)">{{ t('board.look.fromPhoto') }}</span>
        <span style="flex:1" />
        <button type="button" class="ghost" :aria-pressed="P.editLook" @click="P.editLook = !P.editLook">{{ P.editLook ? t('board.look.done') : t('board.look.edit') }}</button>
        <button v-if="!P.editLook" type="button" class="ghost" :aria-pressed="P.showEn" :title="t('board.look.enTitle')" @click="P.showEn = !P.showEn">EN</button></div>

      <template v-if="!P.editLook">
        <p style="white-space:pre-line">{{ look.ru }}</p><p v-if="P.showEn" class="en" style="white-space:pre-line">{{ look.en }}</p>
      </template>
      <div v-else-if="p.mode === 'none'" class="look-form">
        <label><span class="lbl">{{ t('board.look.worldText') }}</span><textarea class="field-in" rows="3" :value="p.world?.ru || ''" @change="setWorld('ru', val($event))" /></label>
        <details><summary class="lbl">{{ t('board.look.enAsSent') }}</summary><textarea class="field-in" rows="3" :value="p.world?.en || ''" @change="setWorld('en', val($event))" /></details>
        <button v-if="dirty" type="button" class="btn" @click="translate"><Icon name="spark" />{{ t('board.look.updatePrompt') }}</button>
      </div>
      <div v-else class="look-form">
        <fieldset v-for="(c, i) in p.cast" :key="i" class="look-person">
          <legend>{{ several ? t('board.look.heroN', { n: i + 1 }) : t('board.look.hero') }}{{ c.from_photo ? ' · ' + t('board.look.fromPhoto') : '' }}</legend>
          <div class="row3">
            <label><span class="lbl">{{ t('board.look.gender') }}</span><select class="field-in" :value="c.gender" @change="setCast(i, 'gender', val($event))"><option v-for="[k, v] in GENDERS" :key="k" :value="k">{{ v }}</option></select></label>
            <label><span class="lbl">{{ t('board.look.ageLbl') }}</span><input class="field-in" type="number" min="21" max="99" :value="c.age || 30" @change="setCast(i, 'age', val($event))"></label>
            <button v-if="several && p.cast!.length > 1" type="button" class="btn danger" :title="t('board.look.removeHeroTitle')" @click="delHero(i)"><Icon name="trash" />{{ t('board.look.remove') }}</button><span v-else />
          </div>
          <div class="person-photo"><img v-if="castPhoto(c)" v-zoom :src="castPhoto(c)!" :alt="t('board.look.photoAltN', { n: i + 1 })"><span v-else class="muted">{{ t('board.look.noPhoto') }}</span>
            <div class="acts"><label class="btn" style="cursor:pointer"><Icon name="image" />{{ castPhoto(c) ? t('board.look.otherPhoto') : t('board.look.photo') }}<input type="file" accept="image/png,image/jpeg,image/webp" hidden @change="castPhotoUp(i, ($event.target as HTMLInputElement).files?.[0])"></label>
              <button v-if="castPhoto(c)" type="button" class="btn" :title="t('board.look.describeTitle')" @click="describe(i)"><Icon name="spark" />{{ t('board.look.describe') }}</button>
              <button v-if="!castPhoto(c) || c.drawn" type="button" class="btn" :disabled="!c.en" :title="t('board.look.drawTitle')"
                @click="draw(i)"><Icon name="brush" />{{ c.drawn ? t('board.look.redraw') : t('board.look.draw') }}</button>
              <button v-if="c.photo" type="button" class="btn" @click="projectCall('DELETE', `/cast/${i}/photo`)">{{ t('board.look.removePhoto') }}</button></div></div>
          <div class="person-voice">
            <span class="lbl">{{ t('board.look.voice') }} <small>{{ several ? t('board.look.voiceSubSeveral') : t('board.look.voiceSub') }}</small></span>
            <template v-if="c.voice">
              <audio :src="fileUrl(c.voice.file)" controls style="width:100%" />
              <div class="row3">
                <label><span class="lbl">{{ t('board.look.sampleFrom') }}</span><input class="field-in" type="number" step="0.5" min="0" :value="c.voice.from ?? 0" @change="setVoice(i, 'from', val($event))"></label>
                <label><span class="lbl">{{ t('board.look.sampleLen') }}</span><input class="field-in" type="number" step="0.5" min="1" max="20" :value="c.voice.secs ?? 5" @change="setVoice(i, 'secs', val($event))"></label>
                <button type="button" class="btn" @click="projectCall('DELETE', `/cast/${i}/voice`)">{{ t('board.look.removeVoice') }}</button></div>
              <span class="muted small">{{ voiced(i) ? t('board.look.voicedN', { n: voiced(i) }) : t('board.look.voicedNone') }}</span>
            </template>
            <div class="acts"><label class="btn" style="cursor:pointer"><Icon name="music" />{{ c.voice ? t('board.look.otherFile') : t('board.look.file') }}<input type="file" accept="audio/*" hidden @change="voiceUp(i, ($event.target as HTMLInputElement).files?.[0])"></label>
              <VoiceRecorder @done="voiceUp(i, $event)" />
              <select v-if="shotScenes.length" class="field-in" style="width:auto" :title="t('board.look.fromSceneTitle')" @change="voiceFromScene(i, $event)">
                <option value="">{{ t('board.look.fromScene') }}</option><option v-for="x in shotScenes" :key="x.index" :value="x.index">{{ t('idea.sceneN', { n: x.index + 1 }) }}</option></select></div>
          </div>
          <label><span class="lbl">{{ t('board.look.lookLbl') }}</span><textarea class="field-in" rows="3" :value="c.ru || ''" @change="setCast(i, 'ru', val($event))" /></label>
          <label><span class="lbl">{{ t('board.look.outfitLbl') }}</span><textarea class="field-in" rows="2" :value="c.outfit_ru || ''" @change="setCast(i, 'outfit_ru', val($event))" /></label>
          <details><summary class="lbl">{{ t('board.look.enAsSent') }}</summary>
            <textarea class="field-in" rows="3" :value="c.en || ''" @change="setCast(i, 'en', val($event))" />
            <textarea class="field-in" rows="2" :value="c.outfit_en || ''" @change="setCast(i, 'outfit_en', val($event))" /></details>
        </fieldset>
        <div class="acts"><button v-if="several && p.cast!.length < 3" type="button" class="btn" @click="addHero"><Icon name="plus" />{{ t('board.look.addHero') }}</button>
          <button v-if="dirty" type="button" class="btn" @click="translate"><Icon name="spark" />{{ t('board.look.updatePrompt') }}</button></div>
        <div class="warn-line"><Icon name="warn" :size="14" />{{ t('board.look.reshootWarn') }}</div>
      </div>

      <div class="facts"><span><span>{{ t('board.look.style') }} · </span>{{ p.style_en }}</span><span><span>{{ t('board.look.sound') }} · </span>{{ p.audio_en }}</span></div>
      <template v-if="photo && p.mode !== 'none'">
        <label class="check-row" style="margin-top:10px" :title="t('board.look.refTitle')">
          <input type="checkbox" :checked="!!p.ref_photo" @change="refPhoto">{{ t('board.look.ref') }} <HelpQ id="look" term="Держать лицо по фото" /></label>
        <label v-if="p.ref_photo" class="check-row sub-check" :title="t('board.look.refAllTitle')">
          <input type="checkbox" :checked="!!p.ref_all" @change="refAll">{{ t('board.look.refAll') }} <HelpQ id="look" term="На всех сценах" /></label>
        <div v-if="frameScenes" class="acts" style="margin-top:8px"><button type="button" class="btn" :disabled="framing" :title="t('board.look.framesTitle')" @click="framesAll"><Icon name="spark" />{{ t('board.look.frames') }}</button>
          <button v-if="unlike.length" type="button" class="btn" :disabled="framing" :title="t('board.look.unlikeTitle', { list: unlike.map((i) => i + 1).join(', ') })" @click="redrawUnlike"><Icon name="retake" />{{ t('board.look.unlike', { n: unlike.length }) }}</button>
          <HelpQ id="look" term="Нарисовать кадры всем сценам" /></div>
      </template>
      <div v-for="x in (p.cast_problems_ru || p.cast_problems || [])" :key="x" class="warn-line" style="margin-top:8px"><Icon name="warn" :size="14" />{{ x }}</div>
    </div>
  </section>
</template>
