<script setup lang="ts">
// The board's top bar, big enough to read at a glance: on the left what can be opened - the scenes, the cast, the
// places, a clip's song, the video's own settings - each a tab with its icon, its name and what is in it (120 scenes
// in 30 episodes, 3 heroes; the video: its length, frame and model); on the right how much is shot, as a bar, and the
// one main button: shoot what is left, or open the finished video. How the scenes are shown (grid, frame, script,
// graph) is the scenes' own, above them (BoardView).
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import ShootConfirm from './ShootConfirm.vue'
import { S } from '../../lib/store'
import { P, flushSave, startRender } from '../../lib/project'
import { episodes, shotPng } from '../../lib/board'
import { useShoot } from '../../lib/shoot'
import { mins, mmss } from '../../lib/format'
import type { Plan } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ p: Plan }>()
const { cur, eta, done, mainLabel, mainIcon, quick } = useShoot(() => props.p)
// a long shoot asks first («Перед съёмкой»); only the assembly left - straight away
const ask = ref(false)
const shoot = () => { if (quick.value) startRender(); else ask.value = true }
const waiting = computed(() => P.after?.pid === P.proj?.id)

const n = computed(() => props.p.scenes.length)
const cast = computed(() => (props.p.cast || []).length)
const places = computed(() => (props.p.places || []).length)
const model = computed(() => (S.cfg?.video_models || []).find((m) => m.id === (P.proj!.settings.video_model || 'h3')))
// the hero's tab by who it is: «Героиня», «Герой», several - «Герои»
const heroTab = computed(() => (cast.value > 1 ? t('board.bar.cast') : (props.p.cast || [])[0]?.gender === 'female' ? t('board.bar.hero') : t('board.bar.heroM')))
const tabs = computed(() => [
  ['scenes', 'film', t('board.bar.scenes'), t('board.bar.scenesSub', n.value) + (episodes(props.p).length > 1 ? t('board.bar.epsSub', episodes(props.p).length) : '')],
  ...(props.p.manual ? [] : [['cast', cast.value > 1 ? 'users' : 'user', heroTab.value, cast.value ? t('board.bar.castSub', cast.value) : t('board.bar.none')]]),
  ...(props.p.manual ? [] : [['places', 'pin', t('board.bar.places'), places.value ? t('board.bar.placesSub', places.value) : t('board.bar.none')]]),
  ...(props.p.clip ? [['song', 'music', t('board.bar.song'), t('board.bar.songSub')]] : []),
  ['video', 'clapper', t('board.bar.video'), `${mmss(props.p.seconds)}, ${P.proj!.settings.aspect}, ${model.value?.short || model.value?.name || 'H3'}`],
] as [typeof P.tab, string, string, string][])
const shot = computed(() => props.p.scenes.filter((s) => shotPng(s.index)).length)
</script>

<template>
  <div class="bb">
    <nav class="bb-tabs" :aria-label="t('board.bar.tabs')">
      <button v-for="[id, ic, name, sub] in tabs" :key="id" type="button" :class="{ on: P.tab === id }" :aria-current="P.tab === id ? 'page' : undefined" @click="P.tab = id">
        <i><Icon :name="ic" :size="20" /></i><span><b>{{ name }}</b><small>{{ sub }}</small></span></button>
    </nav>
    <span class="grow" />
    <!-- the save, quietly: an edit is saved 350 ms after it; a failed one stays and can be sent again -->
    <span v-if="P.saveState" class="bb-save" :class="P.saveState" role="status">
      <template v-if="P.saveState === 'error'"><Icon name="warn" :size="13" />{{ t('board.saveFailed') }} <button type="button" class="link-btn" @click="flushSave()">{{ t('board.saveRetry') }}</button></template>
      <template v-else-if="P.saveState === 'saving'">{{ t('board.saving') }}</template>
      <template v-else><Icon name="check" :size="13" />{{ t('board.saved') }}</template></span>
    <div class="bb-prog" :title="t('board.bar.facts')">
      <div><b>{{ t('board.bar.shotOf', { k: shot, n }) }}</b><small>{{ shot === n ? t('board.bar.allShot') : t('board.bar.left', n - shot) }}</small></div>
      <span class="bb-pbar"><i :style="{ width: `${(shot / Math.max(1, n)) * 100}%` }" /></span>
    </div>
    <router-link v-if="done" class="primary bb-go" :to="`/p/${P.proj!.id}/video`"><Icon name="play" :size="16" />{{ t('board.shoot.openVideo') }}, {{ done.video_up ? '1080p' : done.width }}</router-link>
    <button v-else-if="waiting" type="button" class="primary bb-go" disabled><i class="spin" />{{ t('board.pre.waiting') }}</button>
    <button v-else type="button" class="primary bb-go" @click="shoot"><Icon :name="mainIcon" :size="16" />{{ mainLabel }}, ~{{ mins(eta(cur)) }}</button>
    <ShootConfirm :p="p" :open="ask" @close="ask = false" />
  </div>
</template>
