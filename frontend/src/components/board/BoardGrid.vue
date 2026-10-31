<script setup lang="ts">
// The board's «Сетка», a contact sheet: every episode (a chain - the scenes shot as one piece) a row - in its margin
// its number big, what it is about, its time and how many of its scenes are shot (a click picks all of it); beside
// it the scenes as cards: the shot's frame (hatched while not shot), its number, its length, what happens in it. A
// click selects (Ctrl / Shift pick several), a double click opens the scene on the whole page; the selected card
// stays in sight when the selection moves (the arrows, the map). ▶ on a shot card plays its chosen take right there,
// with sound, one card at a time; ⤢ opens the scene big in a window (ScenePeek). A short video (16 scenes or fewer) has its cards bigger.
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import { P } from '../../lib/project'
import { authorOf, calmOf, episodes, foundLabel, foundLines, foundOf, hasNotes, isPicked, isRaw, lenOf, peek, pickScene, playKey, problemsOf, rawTake, shotPng, staleShot, type Episode } from '../../lib/board'
import { mmss } from '../../lib/format'
import type { Plan, Scene } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ p: Plan }>()
const emit = defineEmits<{ open: [i: number]; add: [after: number, kind: 'continue' | 'new'] }>()
const eps = computed(() => episodes(props.p))
const tall = computed(() => ['9:16', '4:5', '3:4'].includes(P.proj?.settings.aspect || ''))
const ar = computed(() => (P.proj?.settings.aspect || '16:9').replace(':', ' / '))
const fileUrl = (f: string) => `/api/projects/${P.proj?.id}/files/${encodeURIComponent(f)}`
// the notes of a scene in one tip: the writer's «проверь», then what the clip's check found
// (a calm shot - «почти не движется» - only in its own grey dot's tip: it is not among the notes)
const notesTip = (s: { index?: number } & Record<string, any>) => [problemsOf(s as any), ...foundLines(foundOf(s.index!))].filter(Boolean).join('\n')
const calmTip = (s: { index?: number }) => `${t('board.card.calm', { x: calmOf(s.index!).map(foundLabel).join('; ') })}\n${t('board.card.calmTitle')}`
const notesIn = (e: Episode) => e.scenes.filter((s) => hasNotes(s)).length
const shotIn = (e: Episode) => e.scenes.filter((s) => shotPng(s.index!)).length
const pickEpisode = (n: number) => { const e = eps.value.find((x) => x.n === n)!; P.picked = e.scenes.length > 1 ? e.scenes.map((s) => s.index) : []; P.sel = e.scenes[0].index }
const secs = (x: number) => t('board.grid.secs', { s: String(Math.round(x * 10) / 10).replace('.', ',') })

// the chosen take, played on its card: a click on ▶ (or on the playing video) starts or pauses it, the end puts the
// frame back; another card's ▶ stops this one
const takeOf = playKey
const playing = ref<number | null>(null)
const paused = ref(false)
const progress = ref(0)
function play(s: Scene, e: Event) {
  const v = (e.currentTarget as HTMLElement).closest('.bg-pic')?.querySelector('video')
  if (playing.value === s.index && v) { if (v.paused) v.play().catch(() => {}); else v.pause(); return }
  playing.value = s.index; paused.value = false; progress.value = 0; P.sel = s.index; P.picked = []
}
const stop = () => { playing.value = null }
const zoom = (s: Scene) => { stop(); P.sel = s.index; P.picked = []; peek.value = s.index }

// the selected card in sight
const root = ref<HTMLElement | null>(null)
watch(() => P.sel, (i) => nextTick(() => root.value?.querySelector<HTMLElement>(`[data-i="${i}"]`)?.scrollIntoView({ block: 'nearest' })))
</script>

<template>
  <div ref="root" class="bg" :class="{ tall, few: p.scenes.length <= 16 }" :style="{ '--ar': ar }">
    <section v-for="e in eps" :key="e.n" class="bg-ep">
      <button type="button" class="bg-margin" :title="t('board.grid.pickEp')" @click="pickEpisode(e.n)">
        <span class="bg-n">{{ e.n }}</span><span class="bg-about">{{ e.about }}</span>
        <span class="bg-meta"><span>{{ mmss(e.start) }}–{{ mmss(e.end) }}</span><span :class="{ ok: shotIn(e) === e.scenes.length }">{{ t('board.grid.shot', { k: shotIn(e), n: e.scenes.length }) }}</span>
          <span v-if="notesIn(e)" class="warn">{{ t('board.grid.notes', notesIn(e)) }}</span></span></button>
      <div class="bg-cards">
        <button v-for="s in e.scenes" :key="s.index" type="button" class="bg-card" :data-i="s.index"
          :class="{ on: s.index === P.sel, pick: isPicked(s.index), raw: !shotPng(s.index) && !s.start_photo }"
          :title="`${s.index + 1}, ${mmss(Number(s.start) || 0)}: ${s.ru || ''}`" @click="pickScene(s.index, $event)" @dblclick="emit('open', s.index)" @keydown.space.prevent.stop="zoom(s)">
          <!-- the shot; not shot yet - the scene's start (its first frame), so the card shows what the scene begins with -->
          <span class="bg-pic" :class="{ playing: playing === s.index }"><video v-if="playing === s.index && takeOf(s)" :src="fileUrl(`scenes/${takeOf(s)}.mp4`)"
              autoplay playsinline @click.stop="play(s, $event)" @dblclick.stop @play="paused = false" @pause="paused = true" @ended="stop"
              @timeupdate="progress = ($event.target as HTMLVideoElement).currentTime / (($event.target as HTMLVideoElement).duration || 1)" />
            <img v-else-if="shotPng(s.index)" :src="shotPng(s.index)!" alt="" loading="lazy">
            <template v-else-if="s.start_photo"><img :src="fileUrl(s.start_photo)" alt="" loading="lazy"><span class="bg-tag">{{ t('board.grid.start') }}</span></template>
            <span v-if="s.ru_dirty && !isRaw(s)" class="bg-tag warn" :title="t('board.grid.dirtyTitle')">{{ t('board.grid.dirty') }}</span>
            <span v-else-if="staleShot(s.index)" class="bg-tag warn" :title="t('board.grid.reshootTitle')">{{ t('board.grid.reshoot') }}</span>
            <span v-else-if="rawTake(s)" class="bg-tag warn" :title="t('board.grid.facesTitle')">{{ t('board.grid.faces') }}</span>
            <span v-if="takeOf(s) && !staleShot(s.index)" class="bg-play" :class="{ on: playing === s.index && !paused }" role="button" tabindex="-1"
              :title="playing === s.index && !paused ? t('board.grid.pause') : t('board.grid.play')" @click.stop="play(s, $event)" @dblclick.stop>
              <Icon :name="playing === s.index && !paused ? 'pause' : 'play'" :size="18" /></span>
            <span v-if="shotPng(s.index) || s.start_photo" class="bg-zoom" role="button" tabindex="-1" :title="t('board.peek.open')" @click.stop="zoom(s)" @dblclick.stop>
              <Icon name="expand" :size="13" /></span>
            <i v-if="playing === s.index" class="bg-prog" :style="{ width: `${progress * 100}%` }" />
            <b>{{ s.index + 1 }}</b><small>{{ secs(lenOf(s)) }}</small>
            <Icon v-if="s.locked" class="bg-lock" name="lock" :size="13" /><span v-if="hasNotes(s)" class="bg-note" :title="notesTip(s)"><Icon name="warn" :size="12" /></span>
            <span v-else-if="calmOf(s.index).length" class="bg-note calm" role="img" :title="calmTip(s)" :aria-label="calmTip(s)" /></span>
          <span class="bg-text"><span class="cs-who bg-who" :class="authorOf(s)">{{ t(`board.skel.who.${authorOf(s)}`) }}</span>{{ s.ru || '' }}</span>
        </button>
        <!-- the episode's end, a slim strip beside its last card (its words on hover or focus): one more scene in it (a
             continuation), or a new episode after it -->
        <div class="bg-add">
          <button type="button" class="bg-add-scene" :aria-label="`${t('board.grid.addScene')}: ${t('board.grid.addSceneSub')}`" :title="t(p.clip ? 'board.grid.addSceneClipTitle' : 'board.grid.addSceneTitle')" @click="emit('add', e.scenes[e.scenes.length - 1].index, 'continue')">
            <Icon name="plus" :size="16" /><span><b>{{ t('board.grid.addScene') }}</b><small>{{ t('board.grid.addSceneSub') }}</small></span></button>
          <button type="button" class="bg-add-ep" :aria-label="t('board.grid.addEp')" :title="t(p.clip ? 'board.grid.addEpClipTitle' : 'board.grid.addEpTitle')" @click="emit('add', e.scenes[e.scenes.length - 1].index, 'new')">
            <Icon name="plus" :size="12" /><span>{{ t('board.grid.addEpShort') }}</span></button>
        </div>
      </div>
    </section>
  </div>
</template>
