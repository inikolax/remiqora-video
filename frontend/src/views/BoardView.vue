<script setup lang="ts">
// 2. The storyboard as a cutting table: a bar on top (BoardBar - what is open: the scenes, the cast, the places, the
// song, the video, each saying what is in it; how much is shot; the main button), in the middle the scenes - how they
// are shown chosen above them: a contact sheet of all by episode (BoardGrid, the default), the frame of one
// (BoardFrame) or the script of all (BoardScript) - the selected scene - or the picked ones (GroupPanel) - on the
// right, at the bottom the video's track (BoardTrack; with the sheet only its map, the sheet itself is the overview). A scene opens on the whole page (SceneDetail.vue) by a
// double click, Enter or ⤢; the address keeps it (?scene=N), so «Назад» in the browser closes it. ← → step through
// the scenes, Esc drops the picked ones.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from '../components/Icon.vue'
import SidePanel from '../components/SidePanel.vue'
import GuideButton from '../components/help/GuideButton.vue'
import LookCard from '../components/board/LookCard.vue'
import PlacesCard from '../components/board/PlacesCard.vue'
import BoardBar from '../components/board/BoardBar.vue'
import BoardFrame from '../components/board/BoardFrame.vue'
import BoardGrid from '../components/board/BoardGrid.vue'
import BoardScript from '../components/board/BoardScript.vue'
import ClipSkeleton from '../components/board/ClipSkeleton.vue'
import BoardTrack from '../components/board/BoardTrack.vue'
import GroupPanel from '../components/board/GroupPanel.vue'
import SceneInspector from '../components/board/SceneInspector.vue'
import SceneDetail from '../components/board/SceneDetail.vue'
import ScenePeek from '../components/board/ScenePeek.vue'
import ShootPanel from '../components/board/ShootPanel.vue'
import BoardSong from '../components/board/BoardSong.vue'
import { S, banner, onJobEnd, stageKind } from '../lib/store'
import { api, post } from '../lib/api'
import { P, flushSave, liveWriter, openProject, projectCall, reloadProject, rewrite, scheduleSave, unsaved } from '../lib/project'
import { TL, needsTranslation } from '../lib/textLang'
import { modeName } from '../lib/consts'
import { dec, mins, mmss } from '../lib/format'
import { moodName } from '../lib/moods'
import { lenOf, peek, shotPng } from '../lib/board'

const { t } = useI18n()
const props = defineProps<{ id: string }>()
const router = useRouter()
const route = useRoute()
const loaded = ref(false)
const p = computed(() => P.proj?.plan || null)
const job = computed(() => (P.proj ? liveWriter(P.proj.id) : undefined))
const scene = computed(() => p.value && p.value.scenes[Math.min(P.sel, p.value.scenes.length - 1)])
const unlocked = computed(() => (p.value ? p.value.scenes.filter((s) => !s.locked).length : 0))
// the slate: the facts of the video, each in its cell with its name (a bare «Несколько» said nothing)
const PEOPLE = ['one', 'several', 'none']
const facts = computed(() => {
  const pl = p.value!, st = P.proj!.settings, w = pl.writer
  const vm = (S.cfg?.video_models || []).find((m) => m.id === (st.video_model || 'h3'))
  return [[t('board.fact.model'), vm?.name || 'MiniMax H3'], ...(pl.clip ? [[t('board.fact.clip'), `${pl.clip.name || t('board.fact.song')}`]] : []), [t('board.fact.scenes'), String(pl.scenes.length)],
    [t('board.fact.length'), mmss(pl.seconds)], [t('board.fact.frame'), st.aspect || ''],
    [t('board.fact.mood'), pl.manual ? '' : moodName(st.mood || '')], [t('board.fact.people'), pl.manual ? '' : PEOPLE.includes(pl.mode) ? t(`board.people.${pl.mode}`) : modeName(pl.mode)],
    [t('board.fact.prompts'), pl.manual ? t('board.fact.ownPrompts') : ''], [t('board.fact.script'), w?.model ? t('board.fact.in', { t: mins(w.seconds) }) : '']].filter(([, v]) => v)
})
const locked = computed(() => (p.value ? p.value.scenes.length - unlocked.value : 0))
// scenes still in English (clips brought from Remiqora): the writer puts them in Russian, for reading only
// scenes in another language than the texts' (app/i18n.py): «Перевести на …» has work
const english = computed(() => (p.value ? p.value.scenes.filter((s) => needsTranslation(s)).length : 0))
// the writer rewrites every scene without a lock: more than three - it asks first
function rewriteUnlocked() {
  const n = unlocked.value
  if (n > 3 && !confirm(t('board.rewriteAsk', { scenes: t('board.scenesAcc', n), locked: locked.value }))) return
  rewrite('unlocked')
}
const busyText = computed(() => {
  const j = job.value
  if (!j) return ''
  if (j.params?.how === 'ru') return t('board.busy.ru', { step: j.step || 0, steps: j.steps || english.value, lang: TL.name })
  const k = stageKind(j)   // a clip's job goes on after the storyboard: the places, the singer, the frames
  if (k !== 'write' && j.kind === 'write') return `${t(`board.busy.${k}`, { done: j.progress?.done || 0, all: j.progress?.total || '…' })}… ${Math.round(j.elapsed || 0)} ${t('common.s')}`
  return `${j.kind === 'write' ? t('board.busy.write') : j.params?.how === 'looks' ? t('board.busy.looks')
    : j.params?.how === 'describe' ? t('board.busy.describe') : t('board.busy.rewrite')}… ${Math.round(j.elapsed || 0)} ${t('common.s')}`
})

// no storyboard and no writer at work: the writer failed - its error, and «Расписать ещё раз» with the same idea and
// settings (POST /write; a clip starts again from the home screen)
const failed = computed(() => (P.proj ? S.jobs.filter((j) => j.kind === 'write' && j.params?.project === P.proj!.id && j.status === 'error')
  .sort((a, b) => (b.created || 0) - (a.created || 0))[0] : undefined))
const canRewrite = computed(() => !!P.proj && !P.proj.settings.clip && !!(P.proj.settings.idea || '').trim())
const retrying = ref(false)
async function writeAgain() {
  retrying.value = true
  try { const r = await post(`/api/projects/${P.proj!.id}/write`, { model: S.llm }); S.jobs = [...S.jobs, r.job] }
  catch (e) { banner((e as Error).message) } finally { retrying.value = false }
}

// the writer's share as a bar: its elapsed time against its estimate (the job knows this machine's speed)
const busyPct = computed(() => (job.value?.estimate ? Math.min(99, Math.round((100 * (job.value.elapsed || 0)) / job.value.estimate)) : null))
const busyLeft = computed(() => (job.value?.estimate ? t('board.busy.left', { t: mins(Math.max(0, job.value.estimate - (job.value.elapsed || 0))) }) : ''))

const setName = (e: Event) => { P.proj!.name = (e.target as HTMLInputElement).value; scheduleSave('name') }
// «Ветка»: a copy with its shots that remembers this one (app/projects.py branch); a branch says what differs
const branching = ref(false)
async function makeBranch() {
  branching.value = true
  try { await flushSave(); const r = await post(`/api/projects/${P.proj!.id}/branch`); router.push(`/p/${r.project}`) }
  catch (e) { banner((e as Error).message) } finally { branching.value = false }
}
type Diff = { id?: string; name?: string; gone?: boolean; changed?: number[]; added?: number[]; removed?: number; settings?: string[]; edit?: boolean }
const diff = ref<Diff | null>(null)
async function loadDiff() { try { diff.value = P.proj?.branch_of ? await api<Diff>(`/api/projects/${P.proj.id}/branch`) : null } catch { diff.value = null } }
watch(() => [P.proj?.id, P.proj?.updated], loadDiff, { immediate: true })
const diffSay = computed(() => {
  const d = diff.value
  if (!d) return ''
  const out = [
    ...(d.changed?.length ? [t('board.branchScenes', { list: d.changed.join(', ') }, d.changed.length)] : []),
    ...(d.added?.length ? [t('board.branchAdded', { list: d.added.join(', ') })] : []),
    ...(d.removed ? [t('board.branchRemoved', d.removed)] : []),
    ...(d.settings?.length ? [t('board.branchSettings')] : []),
    ...(d.edit ? [t('board.branchEdit')] : []),
  ]
  return out.join(', ') || t('board.branchSame')
})
// «+ Сцена» / «+ Эпизод» (the grid's end of an episode, «Добавить сцену» in the script): an empty scene after scene
// `after` - a continuation in its episode or a new episode; in a clip it takes the second half of that scene's time,
// so the song stays under the others (POST /scenes/{i}/insert). The writer fills it.
async function addScene(after = P.sel, kind: 'continue' | 'new' = 'continue') {
  const pl = p.value!, s = pl.scenes[after]
  if (pl.clip && s) {   // the numbers first: the scene before gives half its time, and a shot one is shot again
    const len = lenOf(s), num = (x: number) => dec((Math.round(x * 10) / 10).toFixed(1))
    const ask = [t('board.grid.clipAsk', { n: after + 1, a: num(len / 2), b: num(len / 2) }), shotPng(after) ? t('board.grid.clipAskShot', { n: after + 1 }) : '', t('board.grid.clipAskGo')]
    if (!confirm(ask.filter(Boolean).join('\n\n'))) return
  }
  if (!(await projectCall('POST', `/scenes/${after}/insert`, { kind }))) return
  P.picked = []
  P.sel = after + 1
  if (!p.value!.manual) rewrite('fill', [after + 1])
}

// a scene moved in the script (a line dragged onto another)
function move(f: number, to: number) {
  const pl = p.value!
  const [moved] = pl.scenes.splice(f, 1)
  pl.scenes.splice(f < to ? to - 1 : to, 0, moved)
  P.picked = []
  P.sel = pl.scenes.indexOf(moved)
  scheduleSave()
}
// the centre: all the scenes in a grid (by default), the frame of the selected one, the script, or a clip's skeleton
// (ClipSkeleton) - where a clip with scenes nobody wrote yet opens
const unwritten = computed(() => (p.value?.scenes || []).filter((s) => !(s.beats_en || []).some((b: string) => (b || '').trim())).length)
const view = computed<'grid' | 'frame' | 'script' | 'clip'>(() => (P.view === 'clip' && !p.value?.clip ? 'grid' : P.view || (p.value?.clip && unwritten.value ? 'clip' : 'grid')))

// the scene on the whole page: ?scene=N in the address; stepping to another scene there rewrites N in place
const detail = computed(() => route.query.scene !== undefined)
const openDetail = (i = P.sel) => { P.sel = i; router.push({ query: { ...route.query, scene: String(i + 1) } }) }
const closeDetail = () => { const { scene: _, ...q } = route.query; router.push({ query: q }) }
watch(() => route.query.scene, (n) => { const i = Number(n) - 1; if (n !== undefined && p.value && i >= 0 && i < p.value.scenes.length) P.sel = i })
watch(() => P.sel, (i) => { if (loaded.value && detail.value && route.query.scene !== String(i + 1)) router.replace({ query: { ...route.query, scene: String(i + 1) } }) })
// Enter on the storyboard (not in a field) opens the selected scene, Space shows it big in a window
function onKey(e: KeyboardEvent) {
  if (detail.value || e.altKey || e.ctrlKey || e.metaKey || !p.value) return
  if ((e.target as HTMLElement).closest?.('input, textarea, select, button, a, video, [contenteditable]')) return
  const n = p.value.scenes.length
  if (e.key === 'Enter') openDetail()
  else if (e.key === ' ') peek.value = P.sel
  else if (e.key === 'ArrowLeft' && P.sel > 0) { P.picked = []; P.sel-- }
  else if (e.key === 'ArrowRight' && P.sel < n - 1) { P.picked = []; P.sel++ }
  else if (e.key === 'Escape' && P.picked.length) P.picked = []
  else return
  e.preventDefault()
}

// a clip's job saves the storyboard, then each place and frame, before it ends: the board shows them as they come
// (edits not saved yet stay on top of what comes - lib/project.ts adopt)
watch(() => (job.value?.kind === 'write' ? `${job.value.progress?.stage}:${job.value.progress?.done}` : ''),
  (v, was) => { if (v && was && v !== was) reloadProject() })

// a job of this project ended: show what it did - a shoot too, it writes the scenes' seeds, takes and camera
let off: () => void
const leave = () => { if (unsaved()) flushSave() }
onMounted(async () => {
  try { await openProject(props.id) } catch (e) { banner((e as Error).message); router.push('/'); return }
  loaded.value = true
  if (route.query.scene !== undefined && p.value) P.sel = Math.min(Math.max(Number(route.query.scene) - 1 || 0, 0), p.value.scenes.length - 1)
  addEventListener('keydown', onKey)
  off = onJobEnd((j) => { if (j.params?.project === props.id) reloadProject() })
  addEventListener('beforeunload', leave)
})
onUnmounted(() => { off?.(); removeEventListener('beforeunload', leave); removeEventListener('keydown', onKey) })
onBeforeRouteLeave(() => flushSave())
</script>

<template>
  <!-- the project being read: a spinner, not a blank black screen -->
  <div v-if="!loaded" class="screen"><main class="main"><div class="empty-state" role="status"><span class="busy-note"><i class="spin" />{{ t('board.loading') }}</span></div></main></div>
  <div v-else-if="loaded && P.proj && !p" class="screen"><main class="main"><div class="empty-state">
    <template v-if="job"><div class="busy-note"><i class="spin" />{{ busyText }}<template v-if="busyPct != null"><span class="bar busy-bar" role="progressbar" :aria-valuenow="busyPct" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: `${busyPct}%` }" /></span><small>{{ busyLeft }}</small></template></div>
      <span>{{ t('board.canClose') }}</span></template>
    <template v-else><span>{{ t('board.noBoard') }}</span>
      <div v-if="failed?.error" class="warn-line board-err"><Icon name="warn" :size="14" /><span>{{ failed.error }}</span></div>
      <div class="acts"><button v-if="canRewrite" type="button" class="primary" :disabled="retrying" @click="writeAgain"><Icon name="spark" :size="16" />{{ t('board.writeAgain') }}</button>
        <router-link class="btn" to="/">{{ t('board.backToIdea') }}</router-link></div></template>
  </div></main></div>

  <SceneDetail v-else-if="loaded && p && scene && detail" :p="p" :s="scene" @close="closeDetail" />

  <div v-else-if="loaded && p && scene" class="bv">
    <BoardBar :p="p" />
    <div v-if="job" class="busy-note bv-note"><i class="spin" />{{ busyText }}<template v-if="busyPct != null"><span class="bar busy-bar" role="progressbar" :aria-valuenow="busyPct" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: `${busyPct}%` }" /></span><small>{{ busyLeft }}</small></template></div>
    <div class="screen bv-body">
      <SidePanel id="board" class="side right" :label="t('board.sidePanel')" :width="380">
        <GroupPanel v-if="P.picked.length > 1" :p="p" />
        <SceneInspector v-else :key="`${P.sel}-${scene.kind}-${'raw' in scene}`" :p="p" :s="scene" @expand="openDetail()" />
      </SidePanel>
      <main class="main bv-center">
        <template v-if="P.tab === 'scenes'">
          <!-- how the scenes are shown: their own choice, above them -->
          <div class="bv-tools"><span>{{ view === 'grid' ? t('board.bar.viewAll') : view === 'frame' ? t('board.bar.viewFrame') : view === 'clip' ? t('board.skel.title') : t('board.bar.viewScript') }}</span>
            <span class="grow" /><span class="bv-show">{{ t('board.bar.show') }}</span>
            <nav class="seg bb-view" :aria-label="t('board.bar.show')">
              <button type="button" :class="{ on: view === 'grid' }" :aria-pressed="view === 'grid'" :title="t('board.bar.gridTitle')" @click="P.view = 'grid'"><Icon name="grid" :size="14" />{{ t('board.bar.grid') }}</button>
              <button type="button" :class="{ on: view === 'frame' }" :aria-pressed="view === 'frame'" :title="t('board.bar.frameTitle')" @click="P.view = 'frame'"><Icon name="play" :size="13" />{{ t('board.bar.frame') }}</button>
              <button type="button" :class="{ on: view === 'script' }" :aria-pressed="view === 'script'" :title="t('board.bar.scriptTitle')" @click="P.view = 'script'"><Icon name="text" :size="15" />{{ t('board.bar.script') }}</button>
              <button v-if="p.clip" type="button" :class="{ on: view === 'clip' }" :aria-pressed="view === 'clip'" :title="t('board.skel.viewTitle')" @click="P.view = 'clip'"><Icon name="music" :size="14" />{{ t('board.skel.view') }}</button>
              <router-link :to="`/p/${P.proj!.id}/graph`" :title="t('board.bar.graphTitle')"><Icon name="arrange" :size="15" />{{ t('board.bar.graph') }}</router-link>
            </nav></div>
          <BoardGrid v-if="view === 'grid'" :p="p" @open="openDetail" @add="addScene" />
          <BoardFrame v-else-if="view === 'frame'" :p="p" :s="scene" @open="openDetail()" />
          <ClipSkeleton v-else-if="view === 'clip'" :p="p" />
          <BoardScript v-else :p="p" :busy="!!job" :english="english" :unlocked="unlocked"
            @open="openDetail" @add="addScene" @rewrite="rewriteUnlocked" @translate="rewrite('ru')" @move="move" />
        </template>
        <LookCard v-else-if="P.tab === 'cast' && !p.manual" :p="p" />
        <PlacesCard v-else-if="P.tab === 'places' && !p.manual" :p="p" />
        <BoardSong v-else-if="P.tab === 'song' && p.clip" :p="p" />
        <div v-else class="bv-video">
          <header class="bh">
            <div class="bh-top">
              <label class="bh-name" :title="t('board.nameTitle')"><input :value="P.proj!.name" :aria-label="t('board.name')" @change="setName"><Icon name="pen" :size="16" /></label>
              <button type="button" class="btn" :disabled="branching || !!job" :title="t('board.branchTitle')" @click="makeBranch"><Icon name="layers" />{{ branching ? t('board.branching') : t('board.branch') }}</button>
              <GuideButton guide="board" /></div>
            <dl class="bh-slate"><div v-for="[k, v] in facts" :key="k"><dt>{{ k }}</dt><dd>{{ v }}</dd></div></dl>
            <p v-if="diff?.id" class="muted small bh-branch"><Icon name="layers" :size="13" />
              <template v-if="diff.gone">{{ t('board.branchGone', { name: diff.name }) }}</template>
              <template v-else>{{ t('board.branchOf') }} <router-link :to="`/p/${diff.id}`">«{{ diff.name }}»</router-link>: {{ diffSay }}</template></p>
          </header>
          <ShootPanel :p="p" />
        </div>
      </main>
    </div>
    <BoardTrack :p="p" :mini="P.tab === 'scenes' && view === 'grid'" @open="openDetail" />
  </div>

  <!-- a scene big in a window over the board: ⤢ on a card, Space -->
  <ScenePeek v-if="loaded && p && !detail" @open="openDetail" />
</template>
