<script setup lang="ts">
// The board's «Каркас» of a clip: every scene along the song - its time, its part, the words sung in it - with its own
// text, its type and who wrote it. A scene the user writes is theirs and pinned: the writer puts it into English and
// leaves the words as they are; a type picked here stays (shot_user). «Написать остальные» (POST /clip/write,
// writer.write_clip) writes the empty scenes, the first time also the story, the cast and the style. A clip made with
// «Тексты сцен: только пустые / никакие» opens here; any clip can come back to it.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import { post } from '../../lib/api'
import { S, banner } from '../../lib/store'
import { P, flushSave, liveWriter, scheduleSave } from '../../lib/project'
import { authorOf, pickScene } from '../../lib/board'
import { mmss } from '../../lib/format'
import type { Plan, Scene } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ p: Plan }>()
const job = computed(() => (P.proj ? liveWriter(P.proj.id) : undefined))
const PARTS = ['intro', 'groove', 'break', 'drop', 'outro', 'chorus']
const partName = (s: Scene) => (s.chorus ? t('idea.part.chorus') : PARTS.includes(s.part) ? t(`idea.part.${s.part}`) : s.part || '')
const words = (s: Scene) => (s.sung || []).map((x: any) => x.text).join(' ').trim()
const written = (s: Scene) => (s.beats_en || []).some((b: string) => (b || '').trim())
const mine = (s: Scene) => s.source === 'user' && !!(s.ru || '').trim()
const whoOf = authorOf
const left = computed(() => props.p.scenes.filter((s) => !written(s) || (mine(s) && s.ru_dirty)).length)
const types = computed(() => (props.p.mode === 'none' ? ['perform', 'insert'] : ['sing', 'perform', 'insert']))

// the user's own words: theirs and pinned; cleared, the scene goes back to the writer
function setText(s: Scene, v: string) {
  s.ru = v
  if (v.trim()) Object.assign(s, { source: 'user', locked: true, ru_dirty: true })
  else Object.assign(s, { source: '', locked: false, ru_dirty: false })
  scheduleSave()
}
// the type, as writer.clip_shot gives it: a singing scene sings the words of its seconds, on the singing model, from
// the singer's photo; a picked type stays the user's
function setShot(s: Scene, shot: string) {
  const c = props.p.clip || {}
  s.shot = shot
  s.shot_user = true
  s.lines = shot === 'sing' && words(s) ? [{ who: 1, text: words(s), how: 'sing' }] : []
  if (s.kind === 'new' && c.sing_model) { if (shot === 'sing') s.model = c.sing_model; else if (s.model === c.sing_model) delete s.model }
  if (s.kind === 'new' && c.photo) {
    if (shot === 'sing' && !s.start_photo) s.start_photo = c.photo
    else if (shot !== 'sing' && s.start_photo === c.photo) { delete s.start_photo; delete s.start_en }
  }
  scheduleSave()
}
async function writeRest() {
  await flushSave()
  try { S.jobs = [...S.jobs, await post(`/api/projects/${P.proj!.id}/clip/write`)] } catch (e) { banner((e as Error).message) }
}
const val = (e: Event) => (e.target as HTMLInputElement).value
</script>

<template>
  <section class="cs">
    <div class="cs-head"><b>{{ t('board.skel.title') }}</b><span>{{ t('board.skel.sub', { n: p.scenes.length }) }}</span><span class="grow" />
      <span v-if="job" class="cs-busy"><i class="spin" />{{ t('status.writing') }}</span>
      <button v-else-if="left" type="button" class="btn cs-go" :title="t('board.skel.writeTitle')" @click="writeRest"><Icon name="spark" />{{ t('board.skel.write', { n: left }) }}</button>
      <span v-else class="cs-done"><Icon name="check" :size="14" />{{ t('board.skel.allDone') }}</span></div>
    <p class="cs-hint">{{ t('board.skel.hint') }}</p>
    <div class="cs-cols" aria-hidden="true"><span /><span /><span>{{ t('board.skel.col.what') }}</span><span>{{ t('board.skel.col.type') }}</span><span>{{ t('board.skel.col.who') }}</span></div>
    <div v-for="s in p.scenes" :key="s.id || s.index" class="cs-row" :class="{ on: s.index === P.sel }" @click="pickScene(s.index, $event)">
      <b class="cs-n">{{ s.index + 1 }}</b>
      <span class="cs-t">{{ mmss(s.start || 0) }}<small>{{ partName(s) }}, {{ Math.round((Number(s.seconds) || 5) * 10) / 10 }} {{ t('common.s') }}</small></span>
      <div class="cs-what">
        <textarea rows="2" :value="s.ru || ''" :placeholder="t('board.skel.empty')" :disabled="!!job" :aria-label="t('board.skel.col.what')"
          @click.stop @change="setText(s, val($event))" />
        <small v-if="words(s)">{{ t('board.skel.sings') }}: «{{ words(s) }}»</small><small v-else>{{ t('board.skel.instrumental') }}</small>
      </div>
      <select class="field-in cs-type" :value="s.shot" :disabled="!!job" :aria-label="t('board.skel.col.type')" @click.stop @change="setShot(s, val($event))">
        <option v-for="k in types" :key="k" :value="k">{{ t(`board.shot.${k}`) }}</option></select>
      <span class="cs-who" :class="whoOf(s)">{{ t(`board.skel.who.${whoOf(s)}`) }}</span>
    </div>
  </section>
</template>
