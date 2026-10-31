<script setup lang="ts">
// The scene as fields (lib/sceneForm.ts), one language: style, place, camera (the studio's lists plus an addition),
// what happens by seconds (the beats share the length), sound, the tail. The fields are edited in place.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import HelpQ from '../HelpQ.vue'
import Icon from '../Icon.vue'
import { type Fields, MAX_BEATS, MOVES, SHOTS, cuts, fmtS } from '../../lib/sceneForm'
import { type Lang, labelSide } from '../../lib/promptParts'

const { t } = useI18n()
const props = defineProps<{ lang: Lang; seconds: number }>()
// the examples' language: Russian only on a Russian sheet (labelSide)
const side = computed(() => labelSide(props.lang))
const f = defineModel<Fields>({ required: true })
const times = computed(() => cuts(f.value.beats, props.seconds))
// the placeholders are examples in the prompt's own language (the tab's), not the interface's
const PH: Record<string, Record<Lang, string>> = {
  style: { ru: 'реалистичное кино, тёплый свет лампы, плёночное зерно', en: 'Realistic live-action cinematic look, warm lamp light, film grain' },
  place: { ru: 'кухня ночью; взрослый мужчина около 40 лет, седой, в тёмном свитере, сидит за столом', en: 'a small kitchen at night; an adult man, about 40, with short grey hair, in a dark sweater, sits at the table' },
  camera: { ru: 'уточнение: лицо хорошо видно', en: 'an addition: his face clearly visible' },
  beat: { ru: 'одно действие; реплика — в кавычках', en: 'one action; a spoken line in quotes' },
  audio: { ru: 'тиканье часов, тишина кухни, без музыки', en: 'a clock ticking, quiet room tone, no music' },
}
const QUOTE = /["«“]/
function addBeat() { if (f.value.beats.length < MAX_BEATS) f.value.beats.push({ text: '', secs: null }) }
function delBeat(i: number) { f.value.beats.splice(i, 1); if (!f.value.beats.length) addBeat() }
function setSecs(i: number, v: string) { const n = +v; f.value.beats[i].secs = v === '' || !(n > 0) ? null : Math.min(15, Math.round(n * 2) / 2) }
</script>

<template>
  <div class="scene-form" :lang="lang">
    <label class="stack"><span class="lbl">{{ t('lab.part.style') }}<HelpQ id="lab" term="Стиль" /></span>
      <input v-model="f.style" class="field-in" :placeholder="PH.style[side]" spellcheck="false"></label>
    <label class="stack"><span class="lbl">{{ t('lab.form.place') }} <small>{{ t('lab.form.placeSub') }}</small><HelpQ id="lab" term="Место" /></span>
      <textarea v-model="f.place" class="field-in" rows="2" :placeholder="PH.place[side]" spellcheck="false" /></label>
    <div class="stack"><span class="lbl">{{ t('lab.form.camera') }}<HelpQ id="lab" term="Камера" /></span>
      <div class="cam-row">
        <select v-model="f.shot" class="field-in" :aria-label="t('lab.form.shotAria')"><option value="">{{ t('lab.form.noShot') }}</option><option v-for="(_, id) in SHOTS" :key="id" :value="id">{{ t(`lab.shot.${id}`) }}</option></select>
        <select v-model="f.move" class="field-in" :aria-label="t('lab.form.moveAria')"><option value="">{{ t('lab.form.noMove') }}</option><option v-for="(_, id) in MOVES" :key="id" :value="id">{{ t(`lab.move.${id}`) }}</option></select>
      </div>
      <input v-model="f.cameraText" class="field-in" :placeholder="PH.camera[side]" :aria-label="t('lab.form.camAddAria')" spellcheck="false"></div>
    <div class="stack"><span class="lbl">{{ t('lab.form.what') }} <small>{{ t('lab.form.whatSub') }}</small><HelpQ id="lab" term="Что происходит" /></span>
      <div v-for="(b, i) in f.beats" :key="i" class="beat" :class="{ say: QUOTE.test(b.text) }">
        <span class="beat-t" :title="t('lab.form.beatRange', { a: fmtS(times[i][0]), b: fmtS(times[i][1]) })">{{ t('lab.form.beatShort', { a: fmtS(times[i][0]), b: fmtS(times[i][1]) }) }}</span>
        <input v-model="b.text" class="field-in" :placeholder="PH.beat[side]" :aria-label="t('lab.form.beatAria', { n: i + 1 })" spellcheck="false">
        <input class="field-in beat-s" type="number" min="0.5" max="15" step="0.5" :value="b.secs ?? ''" :placeholder="t('lab.form.auto')" :aria-label="t('lab.form.beatSecsAria', { n: i + 1 })"
          :title="t('lab.form.beatSecsTitle')" @change="setSecs(i, ($event.target as HTMLInputElement).value)">
        <button type="button" class="ghost" :aria-label="t('lab.form.removeBeatAria', { n: i + 1 })" :title="t('lab.form.remove')" @click="delBeat(i)"><Icon name="close" /></button>
      </div>
      <button v-if="f.beats.length < MAX_BEATS" type="button" class="ghost add-beat" @click="addBeat"><Icon name="plus" />{{ t('lab.form.addBeat') }}</button></div>
    <label class="stack"><span class="lbl">{{ t('lab.form.audio') }} <small>{{ t('lab.form.audioSub') }}</small><HelpQ id="lab" term="Звук" /></span>
      <input v-model="f.audio" class="field-in" :placeholder="PH.audio[side]" spellcheck="false"></label>
    <div class="tail-row">
      <label class="check-row" :title="t('lab.form.keepTitle')"><input v-model="f.keep" type="checkbox">{{ t('lab.form.keep') }}</label>
      <label class="check-row" :title="t('lab.form.noTextTitle')"><input v-model="f.noText" type="checkbox">{{ t('lab.form.noText') }}</label>
    </div>
  </div>
</template>
