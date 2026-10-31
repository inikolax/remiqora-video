<script setup lang="ts">
// Phase 9, G1: «Показать как граф» - the storyboard on a canvas: the scenes are the storyboard's, the states the
// video screen's (lib/shots.ts), the links the server's (/graph). A click on a node lights up what it is linked with
// and shows it on the right. What the storyboard has links for is edited here and saved into it at once: a scene's
// start - a «кадр» drawn to a later scene's «старт» (the scene goes on from that frame), or «Начало» in the panel -
// its takes and its own LoRA. The rest (the text, the people, the camera) is the cards' («Открыть в раскадровке»);
// a graph of its own to branch and rewire - «Копия — проект-граф» in the panel (a new project; this one stays).
import { computed, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { VueFlow, useVueFlow, type Connection, type EdgeMouseEvent, type NodeMouseEvent } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '../styles/graph.css'
import Icon from '../components/Icon.vue'
import SidePanel from '../components/SidePanel.vue'
import GuideButton from '../components/help/GuideButton.vue'
import SceneNode from '../components/graph/SceneNode.vue'
import InfoNode from '../components/graph/InfoNode.vue'
import SceneStart from '../components/board/SceneStart.vue'
import SceneTakes from '../components/board/SceneTakes.vue'
import { GRAPH, type StepState } from '../components/graph/ctx'
import { api, post } from '../lib/api'
import { banner, onJobEnd } from '../lib/store'
import { P, file, openProject, outLabel, reloadProject, scheduleSave } from '../lib/project'
import { useShots } from '../lib/shots'
import { PORT_COLOR, WHO_COLOR, WHO_NAME, build, neighbours, type InfoData, type SceneLink } from '../lib/graph'
import { CAMERAS, FRAMINGS, QL } from '../lib/consts'
import { mmss } from '../lib/format'

const props = defineProps<{ id: string }>()
const router = useRouter()
const { t } = useI18n()
const loaded = ref(false)
const links = ref<SceneLink[] | null>(null)
const shots = useShots(() => props.id)
const est = computed(() => (P.est && P.est[shots.q.value]) || null)
const sel = ref<string | null>(null)

const built = computed(() => (P.proj?.plan && links.value ? build(P.proj, links.value) : null))
const lit = computed(() => (sel.value && built.value ? neighbours(built.value.edges, sel.value) : null))
const nodes = computed(() => built.value?.nodes || [])
// the links: lit around the selected node, running into the scene being shot
const edges = computed(() => {
  const b = built.value
  if (!b) return []
  const L = lit.value, cur = shots.curIdx.value
  return b.edges.map((e) => {
    const hot = !!L && sel.value !== null && (e.source === sel.value || e.target === sel.value)
    return { ...e, class: `${e.class}${hot ? ' hot' : L ? ' dim' : ''}`, animated: cur >= 0 && e.target === `scene-${cur}` }
  })
})

// the assembly, the music and the output: done, going, or to be made again (the video screen's stages)
function step(id: string): StepState | null {
  const sv = shots.saved.value, j = shots.run.value, stage = j?.progress?.stage, e = est.value
  if (id === 'join') return stage === 'assembling' ? { state: 'now', text: t('graph.joining') } : !j && sv?.video ? { state: 'ok', text: t('graph.ready') } : { state: '', text: t('graph.afterScenes') }
  if (id === 'music') return stage === 'mixing' ? { state: 'now', text: t('graph.mixing') } : e?.remix && !j ? { state: 'stale', text: t('graph.trackChanged') }
    : !j && sv?.track_sig ? { state: 'ok', text: t('graph.mixed') } : { state: '', text: t('graph.afterJoin') }
  if (id === 'out') {
    const label = P.proj ? outLabel(P.proj.settings) : ''
    if (stage === 'upscaling' || stage === 'interpolating') return { state: 'now', text: t('graph.outGoing', { label }) }
    if (e?.refinish && !j) return { state: 'stale', text: t('graph.outChanged', { label }) }
    if (!j && sv?.complete) return { state: 'ok', text: sv.up_size ? `${sv.up_size}${sv.fps === 48 ? ' · 48 fps' : ''}${sv.hdr ? ' · HDR10' : ''}` : label }
    return { state: '', text: label }
  }
  return null
}
provide(GRAPH, { shots, est, step, lit })

const { fitBounds, setViewport, dimensions, zoomIn, zoomOut, setCenter, findNode } = useVueFlow('h3-graph')
const fit = () => built.value && fitBounds(built.value.all, { padding: 0.04, duration: 300 })
// a short video opens whole; a long one on its first rows. The wheel zooms and a drag moves, as in ComfyUI
function opened() {
  const b = built.value
  if (b && b.rows > 4) {   // the first rows across the canvas, from its top
    const r = b.top, { width, height } = dimensions.value, zoom = Math.min(1, (width - 32) / r.width, (height - 32) / r.height)
    setViewport({ x: 16 - r.x * zoom + Math.max(0, (width - 32 - r.width * zoom) / 2), y: 64 - r.y * zoom, zoom })
  }
  else if (b) fitBounds(b.all, { padding: 0.04 })
}
function onNode(e: NodeMouseEvent) { sel.value = sel.value === e.node.id ? null : e.node.id }
// a start drawn by hand: a scene's «кадр» to the «старт» of a later scene - it goes on from that frame
const sceneNo = (id: string | null | undefined) => (id && id.startsWith('scene-') ? Number(id.slice(6)) : -1)
function canLink(c: Connection) {
  const a = sceneNo(c.source), b = sceneNo(c.target)
  return c.sourceHandle === 'frame' && c.targetHandle === 'start' && a >= 0 && b > a
}
function onConnect(c: Connection) {
  if (!canLink(c) || !P.proj?.plan) return
  const a = sceneNo(c.source), b = sceneNo(c.target), sc = P.proj.plan.scenes
  const s = sc[b]
  s.kind = 'continue'
  if (a === b - 1) delete s.from
  else s.from = sc[a].id
  sel.value = `scene-${b}`
  scheduleSave()
  banner(t('graph.startsFrom', { b: b + 1, a: a + 1 }), 'info')
}
// a click on a link: the scene it leads into (its «Начало» is in the panel)
function onEdge(e: EdgeMouseEvent) { if (e.edge.target.startsWith('scene-')) sel.value = e.edge.target }
function focusScene(i: number) {
  const n = findNode(`scene-${i}`)
  if (!n) return
  sel.value = n.id
  setCenter(n.position.x + 118, n.position.y + 114, { zoom: 1, duration: 400 })
}

// what the right panel shows for the selected node
const selScene = computed(() => (sel.value?.startsWith('scene-') ? Number(sel.value.slice(6)) : null))
const scene = computed(() => (selScene.value !== null ? P.proj!.plan!.scenes[selScene.value] : null))
const sceneRow = computed(() => (selScene.value !== null ? shots.rows.value[selScene.value] : null))
const sceneKey = computed(() => (selScene.value !== null ? est.value?.keys?.[selScene.value] || sceneRow.value?.key || null : null))
const sceneLink = computed(() => (selScene.value !== null ? links.value?.[selScene.value] : null))
const info = computed(() => (sel.value && !sel.value.startsWith('scene-') ? (nodes.value.find((n) => n.id === sel.value)?.data as InfoData) : null))
const startText = (l: SceneLink | null | undefined) => (!l ? '' : l.start === 'prev' ? t('graph.startPrev', { n: (l.from ?? l.index - 1) + 1 }) : l.start === 'photo' ? t('graph.startPhoto') : t('graph.startText'))
const finalVideo = computed(() => { const sv = shots.saved.value; return sv && sv.complete ? sv.video_up || sv.video : null })
const counts = computed(() => {
  const r = shots.rows.value, e = est.value
  return { n: r.length, ready: shots.ready.value, shoot: e && !shots.job.value ? e.to_shoot : null }
})
function openInBoard(i: number) { P.sel = i; router.push(`/p/${props.id}`) }
// «Копия — проект-граф»: a new graph project with the same keys (the storyboard stays as it is)
const opening = ref(false)
async function toGraph() {
  opening.value = true
  try { const r = await post(`/api/projects/${props.id}/to-graph`); router.push(`/g/${r.project}`) }
  catch (e) { banner((e as Error).message); opening.value = false }
}

async function loadLinks() {
  try { links.value = (await api<{ scenes: SceneLink[] }>(`/api/projects/${props.id}/graph`)).scenes }
  catch (e) { banner(t('graph.linksFailed', { e: (e as Error).message })) }
}
let off: () => void
onMounted(async () => {
  try { await openProject(props.id) } catch (e) { banner((e as Error).message); router.push('/'); return }
  if (!P.proj!.plan) { router.replace(`/p/${props.id}`); return }
  await loadLinks()
  loaded.value = true
  off = onJobEnd((j) => { if (j.params?.project === props.id) reloadProject() })
})
onUnmounted(() => off?.())
// a new plan (the writer finished, another project): the links again
watch(() => P.proj?.updated, (a, b) => { if (loaded.value && a !== b) loadLinks() })
</script>

<template>
  <div v-if="loaded && P.proj && P.proj.plan" class="graph-screen">
    <div class="graph-canvas">
      <VueFlow id="h3-graph" :nodes="nodes" :edges="edges" :min-zoom="0.05" :max-zoom="2" :nodes-draggable="false" :nodes-connectable="true"
        :is-valid-connection="canLink" :elements-selectable="false" :only-render-visible-elements="true" :zoom-on-double-click="false"
        @init="opened" @node-click="onNode" @edge-click="onEdge" @connect="onConnect" @pane-click="sel = null">
        <template #node-scene="n"><SceneNode :id="n.id" :data="n.data" /></template>
        <template #node-info="n"><InfoNode :id="n.id" :data="n.data" /></template>
      </VueFlow>
      <div class="graph-tools">
        <nav class="seg bh-view" :aria-label="t('graph.boardView')"><router-link :to="`/p/${id}`" :title="t('graph.cardsTitle')"><Icon name="film" />{{ t('graph.cards') }}</router-link>
          <span class="on" aria-current="page"><Icon name="layers" />{{ t('graph.graph') }}</span></nav>
        <span class="sep" />
        <button type="button" class="ghost" :title="t('graph.wholeGraph')" @click="fit"><Icon name="expand" />{{ t('graph.wholeGraph') }}</button>
        <button type="button" class="ghost" :aria-label="t('graph.zoomIn')" @click="zoomIn({ duration: 200 })"><Icon name="plus" /></button>
        <button type="button" class="ghost" :aria-label="t('graph.zoomOut')" @click="zoomOut({ duration: 200 })"><Icon name="minus" /></button>
        <span class="sep" />
        <span class="view-only" :title="t('graph.dragTitle')">{{ t('graph.dragHint') }}</span>
        <GuideButton guide="graph-view" />
      </div>
    </div>

    <SidePanel id="graph-view" class="graph-side" :label="t('graph.scene')" :width="360">
      <template v-if="scene && selScene !== null">
        <div class="gs-head"><span class="lbl">{{ t('graph.sceneN', { n: selScene + 1 }) }} · {{ mmss(scene.start) }}–{{ mmss(scene.end) }}</span>
          <button type="button" class="ghost" :aria-label="t('graph.close')" @click="sel = null"><Icon name="close" /></button></div>
        <video v-if="sceneRow?.mp4" class="gs-video" :src="file(sceneRow.mp4)" controls playsinline :poster="sceneRow.png ? file(sceneRow.png) : undefined" />
        <img v-else-if="sceneRow?.png" class="gs-video" :src="file(sceneRow.png)" alt="">
        <p class="gs-ru">{{ scene.ru || t('graph.notWritten') }}</p>
        <dl class="gs-dl">
          <dt>{{ t('graph.state') }}</dt><dd>{{ !shots.job.value && est?.scenes?.[selScene] === 'shoot' ? t('graph.willShoot')
            : sceneRow ? [shots.shot(sceneRow, selScene).cap, shots.shot(sceneRow, selScene).st].filter(Boolean).join(' · ') : '' }}</dd>
          <dt>{{ t('graph.start') }}</dt><dd>{{ startText(sceneLink) }}</dd>
          <template v-if="P.proj.plan.mode !== 'none'"><dt>{{ t('graph.who') }}</dt><dd>{{ sceneLink?.who.map((k) => k + 1).join(', ') || t('graph.all') }}{{ sceneLink?.refs.length ? t('graph.facesRef') : '' }}</dd></template>
          <dt>{{ t('graph.camera') }}</dt><dd>{{ FRAMINGS[scene.framing] || scene.framing }}, {{ (CAMERAS[scene.camera] || scene.camera || '').toLowerCase() }}</dd>
          <dt>{{ t('graph.seed') }}</dt><dd>{{ scene.seed }}</dd>
          <dt>{{ t('graph.frameKey') }}</dt><dd><code>{{ sceneKey || t('graph.keyLater') }}</code></dd>
        </dl>
        <SceneStart :p="P.proj.plan" :s="scene" />
        <SceneTakes :s="scene" />
        <details class="gs-prompt"><summary>{{ t('graph.modelPrompt') }}</summary><pre>{{ scene.prompt }}</pre></details>
        <button type="button" class="btn" @click="openInBoard(selScene)"><Icon name="pen" />{{ t('graph.openInBoard') }}</button>
      </template>

      <template v-else-if="info">
        <div class="gs-head"><span class="lbl">{{ info.title }}</span>
          <button type="button" class="ghost" :aria-label="t('graph.close')" @click="sel = null"><Icon name="close" /></button></div>
        <video v-if="sel === 'out' && finalVideo" class="gs-video" :src="file(finalVideo)" controls playsinline />
        <img v-else-if="info.img" class="gs-photo" :src="info.img" alt="">
        <span v-if="info.sub" class="muted">{{ info.sub }}</span>
        <p v-if="info.text" class="gs-ru pre">{{ info.text }}</p>
        <span class="who-line"><i :style="{ background: WHO_COLOR[info.who] }" />{{ WHO_NAME[info.who] }}</span>
        <span v-if="step(sel!)" class="muted">{{ step(sel!)!.text }}</span>
      </template>

      <template v-else>
        <span class="lbl">{{ t('graph.videoGraph') }}</span>
        <h2 class="gs-title">{{ P.proj.name || P.proj.plan.title_ru || t('graph.video') }}</h2>
        <span class="muted">{{ t('graph.scenes', counts.n) }} · {{ QL[shots.q.value] }}{{ t('graph.shotOf', { a: counts.ready, b: counts.n }) }}{{ counts.shoot ? t('graph.toShootN', { n: counts.shoot }) : '' }}</span>
        <div class="gv-copy">
          <b><Icon name="layers" :size="16" />{{ t('graph.branchesQ') }}</b>
          <p>{{ t('graph.branchesText') }}</p>
          <button type="button" class="btn" :disabled="opening" @click="toGraph"><Icon name="layers" />{{ opening ? t('graph.copying') : t('graph.copyGraph') }}</button>
        </div>
        <p class="gs-ru">{{ t('graph.about') }}</p>
        <div class="legend">
          <span class="lbl">{{ t('graph.legendWho') }}</span>
          <span v-for="(c, k) in WHO_COLOR" :key="k" class="who-line"><i :style="{ background: c }" />{{ WHO_NAME[k] }}</span>
          <span class="lbl" style="margin-top:8px">{{ t('graph.links') }}</span>
          <span class="who-line"><i class="ln" :style="{ background: 'var(--accent)' }" />{{ t('graph.lnChain') }}</span>
          <span class="who-line"><i class="ln" :style="{ background: PORT_COLOR.look }" />{{ t('graph.lnLook') }}</span>
          <span class="who-line"><i class="ln" :style="{ background: PORT_COLOR.face }" />{{ t('graph.lnFace') }}</span>
          <span class="who-line"><i class="ln" :style="{ background: PORT_COLOR.image }" />{{ t('graph.lnPhoto') }}</span>
          <span class="who-line"><i class="ln" :style="{ background: PORT_COLOR.clip }" />{{ t('graph.lnClip') }}</span>
        </div>
        <label class="lbl" for="g-find" style="margin-top:6px">{{ t('graph.goScene') }}</label>
        <select id="g-find" class="field-in" @change="focusScene(Number(($event.target as HTMLSelectElement).value)); ($event.target as HTMLSelectElement).value = ''">
          <option value="">{{ t('graph.sceneNo') }}</option>
          <option v-for="s in P.proj.plan.scenes" :key="s.index" :value="s.index">{{ s.index + 1 }} · {{ mmss(s.start) }} · {{ (s.ru || '').slice(0, 48) }}</option>
        </select>
        <router-link class="btn" :to="`/p/${id}/video`"><Icon name="film" />{{ t('graph.videoScreen') }}</router-link>
      </template>
    </SidePanel>
  </div>
</template>
