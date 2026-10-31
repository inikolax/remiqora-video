<script setup lang="ts">
// Phase 9: a graph project (#/g/<id>). The canvas: nodes from «Добавить» or a template, links dragged from an output
// to an input of the same type, Delete removes what is selected, a group drags the nodes inside it. The right panel:
// the selected node (NodeInspector), else the project - quality, «Снять всё», the LLM nodes to rewrite, cleaning,
// «Собрать раскадровку». The server says what each node is; a running job's progress lies on top.
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { VueFlow, useVueFlow, type Connection, type NodeDragEvent, type NodeMouseEvent } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '../styles/graph.css'
import Icon from '../components/Icon.vue'
import ModelPick from '../components/ModelPick.vue'
import SidePanel from '../components/SidePanel.vue'
import GuideButton from '../components/help/GuideButton.vue'
import EditNode from '../components/graph/EditNode.vue'
import GroupNode from '../components/graph/GroupNode.vue'
import NodeInspector from '../components/graph/NodeInspector.vue'
import TemplatesModal from '../components/graph/TemplatesModal.vue'
import { download, portable, type Tpl } from '../lib/templates'
import { api, post } from '../lib/api'
import { S, banner, onJobEnd, pollJobs } from '../lib/store'
import { fitLink, nodeWhat, whoName } from '../lib/nodeHelp'
import { arrange } from '../lib/graphArrange'
import { ADD_MENU, GE, ICON, PORT_COLOR, PORT_NAME, WHO_COLOR, WHO_NAME, addNode, canLink, copy, fileUrl, flush, insert, insideGroup, link, live, loadState, nodeOf, openGraph,
  paste, redo, reloadDoc, removeNodes, runLlm, runTo, tOf, touch, typeTitle, undo, withGroups } from '../lib/graphDoc'
import { QL } from '../lib/consts'
import { mins, mmss } from '../lib/format'

const props = defineProps<{ id: string }>()
const router = useRouter()
const { t } = useI18n()
// the add menu offers only the types this server has (a page newer than the server it talks to)
const known = (ty: string) => !!GE.types[ty]
const loaded = ref(false)
const menu = ref<'' | 'add'>('')
const tplOpen = ref(false)
const tplWin = ref<InstanceType<typeof TemplatesModal> | null>(null)
const { setViewport, zoomIn, zoomOut, viewport, dimensions, getSelectedNodes, getSelectedEdges, getNodes, getEdges, addSelectedNodes, addSelectedElements,
  removeSelectedElements, findNode } = useVueFlow('h3-graph-edit')
let fitted = false
function fitOnce() { if (!fitted) { fitted = true; fitAll(0) } }
// «Весь граф»: the whole graph below the tool bar that floats over the canvas's top (Vue Flow's fitView pads every
// side alike, and the top row went under the bar); a node not measured yet counts as 240 x 200
const TOP = 64, PAD = 24
function fitAll(duration = 300) {
  const ns = getNodes.value
  if (!ns.length) return
  // from the positions themselves: a big graph draws only what is on screen, and the others' computed positions are
  // the old ones until drawn (after «Упорядочить» the box was the old layout's)
  const box = ns.map((n) => ({ x: n.position.x, y: n.position.y, w: n.dimensions.width || 240, h: n.dimensions.height || 200 }))
  const x0 = Math.min(...box.map((r) => r.x)), y0 = Math.min(...box.map((r) => r.y))
  const b = { x: x0, y: y0, width: Math.max(...box.map((r) => r.x + r.w)) - x0, height: Math.max(...box.map((r) => r.y + r.h)) - y0 }
  const W = dimensions.value.width, H = dimensions.value.height
  const zoom = Math.max(0.05, Math.min(1, (W - 2 * PAD) / b.width, (H - TOP - PAD) / b.height))
  setViewport({ x: (W - b.width * zoom) / 2 - b.x * zoom, y: TOP + (H - TOP - PAD - b.height * zoom) / 2 - b.y * zoom, zoom }, { duration })
}

// «Упорядочить»: the selection (two or more nodes, a group with what is in it) or the whole graph, by its flow
function arrangeNodes() {
  const sel = withGroups(selected())
  // a big graph draws only what is on screen: a node not drawn is as big as the biggest drawn one of its kind
  const typical: Record<string, { w: number; h: number }> = {}
  for (const n of getNodes.value) {
    const t = tOf(n as any), d = n.dimensions
    if (d.width) typical[t] = { w: Math.max(typical[t]?.w || 0, d.width), h: Math.max(typical[t]?.h || 0, d.height) }
  }
  const moved = arrange(sel.length >= 2 ? sel : null, (id) => {
    const n = findNode(id), d = n?.dimensions
    return d?.width ? { w: d.width, h: d.height } : typical[n ? tOf(n as any) : ''] || { w: 260, h: 260 }
  })
  if (!moved) return banner(sel.length >= 2 ? t('graph.selArranged') : t('graph.graphArranged'))
  touch(0)   // a save, and so an undo step: Ctrl+Z brings the old layout back
  nextTick(() => fitAll())
}

const job = computed(() => live())
const quality = computed(() => GE.proj?.settings.quality || 'draft')
const outputs = computed(() => GE.nodes.filter((n) => tOf(n) === 'output'))
const staleLlm = computed(() => GE.nodes.filter((n) => ['writer', 'hero'].includes(tOf(n)) && GE.state?.nodes[n.id]?.state === 'stale').map((n) => n.id))
const scenes = computed(() => GE.nodes.filter((n) => tOf(n) === 'scene').length)
const selId = computed(() => (GE.sel && GE.nodes.some((n) => n.id === GE.sel) ? GE.sel : null))

// where a new node goes: the middle of what is on screen
function centre() {
  const v = viewport.value, dm = dimensions.value
  return { x: (-v.x + dm.width / 2) / v.zoom - 120, y: (-v.y + dm.height / 2) / v.zoom - 80 }
}
// a new node: next to the selected one and linked to it when their ports fit (Идея selected + Сценарист = linked),
// else in the middle of the screen
function add(ty: string) {
  menu.value = ''
  const s = GE.sel ? nodeOf(GE.sel) : null
  const fit = s && !['group', 'note'].includes(tOf(s)) && !['group', 'note'].includes(ty) ? fitLink(s.id, ty) : null
  if (!s || !fit) { const c = centre(); addNode(ty, c.x, c.y); return }
  const n = addNode(ty, s.position.x + (fit.after ? 320 : -320), s.position.y)
  link({ source: fit.source || n.id, sourceHandle: fit.sourceHandle, target: fit.target || n.id, targetHandle: fit.targetHandle })
  const name = (x: string) => typeTitle(x)
  banner(fit.after ? t('graph.linked', { a: name(tOf(s)), b: name(ty) }) : t('graph.linked', { a: name(ty), b: name(tOf(s)) }))
}
// templates: a window with the built-in ones and the user's; out to JSON and in from it (lib/templates.ts)
function useTemplate(tpl: Tpl | null) {
  if (!tpl) return
  const c = centre()
  select(insert(tpl, c.x, c.y))
  tplOpen.value = false
}
// the selected nodes (or the whole graph) as a template: their links between them, without the project's files
function picked() {
  const sel = withGroups(selected()), ids = new Set(sel.length ? sel : GE.nodes.map((n) => n.id))
  return { sel: sel.length, ...portable(GE.nodes.filter((n) => ids.has(n.id)).map((n) => { const { t: type, ...data } = n.data as any; return { id: n.id, type, position: n.position, data } }),
    GE.edges.filter((e) => ids.has(e.source) && ids.has(e.target))) }
}
async function saveTemplate() {
  const p = picked()
  const name = prompt(p.sel ? t('graph.tplFromSel', { n: p.sel }) : t('graph.tplFromAll'), GE.proj?.name || '')
  if (!name) return
  const about = prompt(t('graph.tplAbout'), '') || ''
  try { await post('/api/graph/templates', { name, about, nodes: p.nodes, edges: p.edges }); banner(t('graph.tplSaved', { name }), 'info'); tplWin.value?.reload() } catch (e) { banner((e as Error).message) }
}
function exportJson() {
  const p = picked()
  const name = prompt(p.sel ? t('graph.jsonFromSel', { n: p.sel }) : t('graph.jsonFromAll'), GE.proj?.name || t('graph.tplDefault'))
  if (name) download(name, '', p.nodes, p.edges)
}

// the canvas
function onConnect(c: Connection) { link(c) }
function onNode(e: NodeMouseEvent) { GE.sel = e.node.id }
const typing = (e: KeyboardEvent) => e.target instanceof Element && !!e.target.closest('input, textarea, select, [contenteditable]')
// the keys (by the key's place, not its letter: Ctrl+A is Ctrl+Ф on the Russian layout): Ctrl+A all, Esc none,
// Delete / Backspace the selected, Ctrl+C / Ctrl+V / Ctrl+D copy, paste, duplicate, Ctrl+Z / Ctrl+Shift+Z (Ctrl+Y)
// undo, redo. In a text field the keys are the field's.
const selected = () => getSelectedNodes.value.map((n) => n.id)
function select(ids: string[]) {
  removeSelectedElements()
  nextTick(() => {
    const nodes = ids.map((id) => findNode(id)).filter((n): n is NonNullable<typeof n> => !!n)
    addSelectedNodes(nodes)
    GE.sel = ids.length === 1 ? ids[0] : null
  })
}
function onKey(e: KeyboardEvent) {
  if (typing(e) || !loaded.value) return
  const mod = e.ctrlKey || e.metaKey
  if (e.key === 'Delete' || e.key === 'Backspace') {
    const nodes = selected(), edges = new Set(getSelectedEdges.value.map((x) => x.id))
    if (!nodes.length && !edges.size) return
    e.preventDefault()
    if (edges.size) { GE.edges = GE.edges.filter((x) => !edges.has(x.id)); touch(150) }
    if (nodes.length) removeNodes(nodes)
    return
  }
  if (e.key === 'Escape') { removeSelectedElements(); GE.sel = null; menu.value = ''; return }
  if (e.key === '?' && !mod) { e.preventDefault(); S.keys = true; return }   // the keys sheet, as in Remiqora's editor
  if (!mod) return
  switch (e.code) {
    // one call: Vue Flow's addSelectedEdges alone unselects the nodes
    case 'KeyA': e.preventDefault(); addSelectedElements([...getNodes.value, ...getEdges.value]); GE.sel = null; break
    case 'KeyC': if (copy(withGroups(selected()))) e.preventDefault(); break
    case 'KeyV': { e.preventDefault(); const ids = paste(); if (ids.length) select(ids); break }
    case 'KeyD': { e.preventDefault(); if (copy(withGroups(selected()))) select(paste()); break }
    case 'KeyZ': e.preventDefault(); (e.shiftKey ? redo() : undo()).then((ok) => { if (!ok) banner(e.shiftKey ? t('graph.nothingRedo') : t('graph.nothingUndo'), 'info') }); break
    case 'KeyY': e.preventDefault(); redo().then((ok) => { if (!ok) banner(t('graph.nothingRedo'), 'info') }); break
  }
}
// a group carries what lies inside it
let inside: { id: string; x: number; y: number }[] = [], from = { x: 0, y: 0 }
function dragStart(e: NodeDragEvent) {
  const g = e.node
  if (tOf(g) !== 'group') { inside = []; return }
  from = { x: g.position.x, y: g.position.y }
  inside = insideGroup(g).map((n) => ({ id: n.id, x: n.position.x, y: n.position.y }))
}
function drag(e: NodeDragEvent) {
  if (!inside.length) return
  const dx = e.node.position.x - from.x, dy = e.node.position.y - from.y
  for (const p of inside) { const n = GE.nodes.find((x) => x.id === p.id); if (n) n.position = { x: p.x + dx, y: p.y + dy } }
}
function dragStop() { inside = []; touch(300) }

// the project
async function setSetting(k: string, v: unknown) {
  try { GE.proj = await api(`/api/projects/${props.id}`, { method: 'PUT', body: { settings: { [k]: v } } }); await loadState() } catch (e) { banner((e as Error).message) }
}
// the frame by hand: one side typed, the other stays as it is (the auto size until both are set); an emptied field
// returns the frame to the format's size; the server snaps to the model's step, the field then shows what it kept
async function setSize(k: 'w' | 'h', e: Event) {
  const el = e.target as HTMLInputElement, st = GE.state
  if (!st) return
  const v = parseInt(el.value, 10)
  if (!v || v < 0) { if (st.own_size) await setSetting('size', null); el.value = ''; return }
  await setSetting('size', { w: k === 'w' ? v : st.width, h: k === 'h' ? v : st.height })
  if (GE.state) el.value = String(k === 'w' ? GE.state.width : GE.state.height)
}
async function setName(e: Event) {
  try { GE.proj = await api(`/api/projects/${props.id}`, { method: 'PUT', body: { name: (e.target as HTMLInputElement).value } }) } catch (err) { banner((err as Error).message) }
}
const stopAfter = () => post(`/api/jobs/${job.value!.id}/stop-after`).then(pollJobs).catch((e) => banner(e.message))
function stopNow() { if (confirm(t('graph.stopNow'))) post(`/api/jobs/${job.value!.id}/cancel`).then(pollJobs) }
async function clean() {
  try {
    const r = await api(`/api/projects/${props.id}/nodes/cleanup`)
    if (!r.files) { banner(r.all_known ? t('graph.nothingClean') : t('graph.noExtraTakes')); return }
    const mb = (r.bytes / 2 ** 20).toFixed(0)
    if (!confirm(t('graph.cleanAsk', { files: r.files, what: t('graph.files', r.files), mb, takes: r.takes, rest: r.all_known ? t('graph.cleanRest') : '' }))) return
    await post(`/api/projects/${props.id}/nodes/cleanup`)
    await reloadDoc()
    banner(t('graph.cleaned', { mb }), 'info')
  } catch (e) { banner((e as Error).message) }
}
async function toStoryboard() {
  await flush()
  try { const r = await post(`/api/projects/${props.id}/to-storyboard`); router.push(`/p/${r.project}`) } catch (e) { banner((e as Error).message) }
}

let off: () => void
const away = () => { menu.value = '' }
onMounted(async () => {
  try { await openGraph(props.id) } catch (e) { banner((e as Error).message); router.push('/'); return }
  if (GE.proj?.type !== 'graph') { router.replace(`/p/${props.id}`); return }
  loaded.value = true
  off = onJobEnd((j) => { if (j.params?.project === props.id) (j.kind === 'graph-llm' ? reloadDoc() : loadState()) })
  addEventListener('keydown', onKey)
  addEventListener('beforeunload', flush)
  document.addEventListener('click', away)
})
onUnmounted(() => { off?.(); flush(); removeEventListener('keydown', onKey); removeEventListener('beforeunload', flush); document.removeEventListener('click', away) })
</script>

<template>
  <div v-if="loaded && GE.proj" class="graph-screen">
    <div class="graph-canvas">
      <VueFlow id="h3-graph-edit" v-model:nodes="GE.nodes" v-model:edges="GE.edges" :min-zoom="0.05" :max-zoom="2" :delete-key-code="null"
        :is-valid-connection="canLink" :zoom-on-double-click="false" :only-render-visible-elements="GE.nodes.length > 80" @nodes-initialized="fitOnce"
        @connect="onConnect" @node-click="onNode" @pane-click="GE.sel = null" @node-drag-start="dragStart" @node-drag="drag" @node-drag-stop="dragStop">
        <template #node-gnode="n"><EditNode :id="n.id" :data="n.data" :selected="n.selected" /></template>
        <template #node-ggroup="n"><GroupNode :id="n.id" :data="n.data" :selected="n.selected" /></template>
      </VueFlow>
      <div class="graph-tools" @click.stop>
        <router-link class="ghost" to="/"><Icon name="back" />{{ t('graph.videos') }}</router-link>
        <span class="sep" />
        <div class="tool-menu"><button type="button" class="ghost" :aria-expanded="menu === 'add'" @click="menu = menu === 'add' ? '' : 'add'"><Icon name="plus" />{{ t('graph.add') }}</button>
          <div v-if="menu === 'add'" class="tm-pop wide add-pop">
            <span class="tm-hint">{{ GE.sel && nodeOf(GE.sel) ? t('graph.addNear', { name: (nodeOf(GE.sel)!.data as any).title || typeTitle(tOf(nodeOf(GE.sel)!)) }) : t('graph.addHint') }}</span>
            <template v-for="[g, ts] in ADD_MENU" :key="g"><span class="tm-group">{{ t(`graph.addGroup.${g}`) }}</span>
              <button v-for="ty in ts.filter(known)" :key="ty" type="button" class="tm-node" @click="add(ty)">
                <span class="tm-ic" :style="{ color: WHO_COLOR[GE.types[ty]?.who || 'none'] }"><Icon :name="ICON[ty] || 'layers'" :size="18" /></span>
                <span class="tm-tx"><b>{{ typeTitle(ty) }}</b><small>{{ nodeWhat(ty) }}</small></span></button></template>
          </div></div>
        <button type="button" class="ghost" @click="tplOpen = true; menu = ''"><Icon name="layers" />{{ t('graph.templates') }}</button>
        <span class="sep" />
        <button type="button" class="ghost" @click="fitAll()"><Icon name="expand" />{{ t('graph.wholeGraph') }}</button>
        <button type="button" class="ghost" :title="t('graph.arrangeTitle', { only: getSelectedNodes.length >= 2 ? t('graph.arrangeOnly') : '' })"
          @click="arrangeNodes"><Icon name="arrange" />{{ t('graph.arrange') }}</button>
        <button type="button" class="ghost" :aria-label="t('graph.zoomIn')" @click="zoomIn({ duration: 200 })"><Icon name="plus" /></button>
        <button type="button" class="ghost" :aria-label="t('graph.zoomOut')" @click="zoomOut({ duration: 200 })"><Icon name="minus" /></button>
        <span class="sep" /><GuideButton guide="graph-edit" />
        <button type="button" class="guide-btn" :title="t('graph.keysTitle')" @click.stop="S.keys = true"><Icon name="grip" :size="16" /><span>{{ t('graph.keys') }}</span></button>
        <span class="sep" /><span class="view-only">{{ GE.saving ? t('graph.saving') : t('graph.saved') }}</span>
      </div>
    </div>

    <TemplatesModal ref="tplWin" :open="tplOpen" mode="insert" :selected="tplOpen ? withGroups(getSelectedNodes.map((n) => n.id)).length : 0" @close="tplOpen = false" @pick="useTemplate"
      @save="saveTemplate" @export="exportJson" />
    <SidePanel id="graph-edit" class="graph-side" :label="t('graph.sideLabel')" :width="360">
      <NodeInspector v-if="selId" :id="selId" :key="selId" />
      <template v-else>
        <span class="lbl">{{ t('graph.graph') }}</span>
        <input class="gs-title-in" :value="GE.proj.name" :aria-label="t('graph.name')" @change="setName">
        <span class="muted">{{ t('graph.scenes', scenes) }} · {{ GE.proj.settings.aspect }} · {{ QL[quality] }}{{ GE.state ? ` · ${GE.state.width}×${GE.state.height}` : '' }}</span>
        <div class="seg"><button v-for="q in ['draft', 'final']" :key="q" type="button" :class="{ on: quality === q }" :disabled="!!job" @click="setSetting('quality', q)">{{ QL[q] }}</button></div>
        <select class="field-in" :value="GE.proj.settings.aspect" :aria-label="t('graph.aspect')" :disabled="!!job" @change="setSetting('aspect', ($event.target as HTMLSelectElement).value)">
          <option v-for="a in ['16:9', '9:16', '1:1']" :key="a" :value="a">{{ a }}</option></select>
        <span class="lbl">{{ t('graph.size') }} <small>{{ GE.state?.own_size ? t('graph.sizeOwn') : t('graph.sizeAuto') }}</small></span>
        <div class="gs-size">
          <input class="field-in" type="number" inputmode="numeric" min="256" max="2048" :value="GE.state?.own_size ? GE.state.width : ''"
            :placeholder="GE.state ? String(GE.state.auto_size[0]) : ''" :aria-label="t('graph.width')" :disabled="!!job" @change="setSize('w', $event)">
          <span class="muted">×</span>
          <input class="field-in" type="number" inputmode="numeric" min="256" max="2048" :value="GE.state?.own_size ? GE.state.height : ''"
            :placeholder="GE.state ? String(GE.state.auto_size[1]) : ''" :aria-label="t('graph.height')" :disabled="!!job" @change="setSize('h', $event)">
          <button v-if="GE.state?.own_size" type="button" class="btn" :disabled="!!job" @click="setSetting('size', null)">{{ t('graph.sizeReset') }}</button>
        </div>
        <span class="lbl">{{ t('graph.model') }} <small>{{ t('graph.modelSub') }}</small></span>
        <ModelPick :model-value="GE.proj.settings.video_model" compact @update:model-value="!job && setSetting('video_model', $event)" />
        <template v-if="job">
          <div class="busy-note"><i class="spin" />{{ job.kind === 'graph-llm' ? t('graph.writerWorks') : t('graph.shooting') }}… {{ Math.round(job.elapsed || 0) }} {{ t('common.s') }}{{ job.estimate ? t('graph.of', { t: mins(job.estimate) }) : '' }}</div>
          <button v-if="job.kind === 'graph'" type="button" class="btn" :disabled="job.stop_after" @click="stopAfter"><Icon name="stop" />{{ job.stop_after ? t('graph.stoppingAfter') : t('graph.stopAfter') }}</button>
          <button type="button" class="btn danger" @click="stopNow"><Icon name="close" />{{ t('graph.stopNowBtn') }}</button>
        </template>
        <button v-else type="button" class="primary" :disabled="!outputs.length" @click="runTo([], quality)"><Icon name="play" :size="18" />
          {{ GE.state && GE.state.to_shoot + GE.state.pictures === 0 ? t('graph.buildOutputs') : t('graph.shootAll') }}{{ GE.state && GE.state.seconds >= 1 ? ` · ~${mins(GE.state.seconds)}` : '' }}</button>
        <span v-if="GE.state && !job" class="muted small">{{ GE.state.to_shoot ? t('graph.toShoot', GE.state.to_shoot) : t('graph.allShot') }}{{ GE.state.pictures ? t('graph.pictures', { n: GE.state.pictures }) : '' }}{{ t('graph.onlyNeeded') }}</span>
        <button v-if="staleLlm.length" type="button" class="btn" :disabled="!!job" @click="runLlm(staleLlm)"><Icon name="spark" />{{ t('graph.rewriteStale', { n: staleLlm.length }) }}</button>
        <div v-if="outputs.length" class="stack" style="gap:6px"><span class="lbl">{{ t('graph.outputs') }}</span>
          <div v-for="o in outputs" :key="o.id" class="out-row"><button type="button" class="ghost grow" @click="GE.sel = o.id">{{ (o.data as any).title || typeTitle('output') }}</button>
            <a v-if="GE.state?.nodes[o.id]?.state === 'ready'" class="ghost" :href="fileUrl(GE.state.nodes[o.id].file)!" target="_blank"><Icon name="play" />{{ mmss(GE.state.nodes[o.id].seconds || 0) }}</a>
            <span v-else class="muted small">{{ t('graph.notBuilt') }}</span></div></div>
        <div class="stack" style="gap:6px">
          <button type="button" class="btn" :disabled="!!job" @click="clean"><Icon name="trash" />{{ t('graph.cleanTakes') }}</button>
          <button type="button" class="btn" @click="toStoryboard"><Icon name="film" />{{ t('graph.toStoryboard') }}</button></div>
        <div class="legend">
          <span class="lbl">{{ t('graph.legendWho') }}</span>
          <span v-for="(_, k) in WHO_NAME" :key="k" class="who-line"><i :style="{ background: WHO_COLOR[k] }" />{{ whoName(k) }}</span>
          <span class="lbl" style="margin-top:8px">{{ t('graph.legendPorts') }}</span>
          <span v-for="(c, k) in PORT_NAME" :key="k" class="who-line"><i class="dot" :style="{ background: PORT_COLOR[k] }" />{{ c }}</span>
          <p class="muted small">{{ t('graph.legendHow') }}</p>
          <button type="button" class="btn" @click.stop="S.keys = true"><Icon name="grip" />{{ t('graph.allKeys') }}</button>
          <span class="lbl" style="margin-top:8px">{{ t('graph.keys') }}</span>
          <dl class="keys">
            <dt>{{ t('graph.key.shiftBox') }}</dt><dd>{{ t('graph.key.selMany') }}</dd>
            <dt>{{ t('graph.key.ctrlClick') }}</dt><dd>{{ t('graph.key.addSel') }}</dd>
            <dt>Ctrl + A</dt><dd>{{ t('graph.key.selAll') }}</dd>
            <dt>Esc</dt><dd>{{ t('graph.key.unsel') }}</dd>
            <dt>Delete</dt><dd>{{ t('graph.key.del') }}</dd>
            <dt>Ctrl + C, Ctrl + V</dt><dd>{{ t('graph.key.copyPaste') }}</dd>
            <dt>Ctrl + D</dt><dd>{{ t('graph.key.dup') }}</dd>
            <dt>Ctrl + Z</dt><dd>{{ t('graph.key.undo') }}</dd>
            <dt>Ctrl + Shift + Z</dt><dd>{{ t('graph.key.redo') }}</dd>
          </dl>
        </div>
      </template>
    </SidePanel>
  </div>
</template>
