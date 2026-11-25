<script setup lang="ts">
// A node of a graph project: its ports from the server's types (inputs left, outputs right, coloured by type), the
// header in the colour of who does the work, what it holds, and its state - the live job's, else the server's.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Handle, Position } from '@vue-flow/core'
import Icon from '../Icon.vue'
import { ENGINE_NAME, GE, ICON, PORT_COLOR, PORT_LABEL, PORT_Y, WHO_COLOR, expand, fileUrl, inputsOf, live, nodeOf, portsOf, graphPics, refLoraOf, runLlm, secondsOf, tOf, typeTitle } from '../../lib/graphDoc'
import { openZoom } from '../../lib/zoom'
import { outLabel } from '../../lib/project'
import { KIND_ICON } from '../../lib/consts'
import { nextStep } from '../../lib/nodeHelp'
import { dec, mins, mmss } from '../../lib/format'
import { S } from '../../lib/store'
import { lookName } from '../../lib/looks'
import { screenplayStats } from '../../lib/screenplay'
import { useResize } from './resize'
import WriterThinking from '../WriterThinking.vue'
import RoleSelect from './RoleSelect.vue'

const props = defineProps<{ id: string; data: Record<string, any>; selected?: boolean }>()
const { t: tx } = useI18n()
const t = computed(() => props.data.t as string)
const rsz = useResize(() => props.id)
// the tile's own size (dragged by its corner): with a height the body fills it instead of its usual few lines
const sized = computed(() => ({ width: props.data.w ? `${props.data.w}px` : undefined, height: props.data.h ? `${props.data.h}px` : undefined }))
const spec = computed(() => GE.types[t.value])
// its ports in rows (graphDoc.portsOf: «Упорядочить» lines the links up by the same rows)
const ports = computed(() => portsOf(t.value, props.data))
const ins = computed(() => ports.value.ins)
const outs = computed(() => ports.value.outs)
const st = computed(() => GE.state?.nodes[props.id])
const job = computed(() => live())
const row = computed(() => job.value?.progress?.nodes?.[props.id] as Record<string, any> | undefined)
const top = (k: number) => `${PORT_Y(k)}px`
const title = computed(() => props.data.title || typeTitle(t.value))
const img = computed(() => {
  const s = st.value
  if (t.value === 'hero' && props.data.actor) {   // an actor's picture: the one the server says it has (face, else look reference, else photo); ?v= changes when it is redrawn
    const a = s?.actor
    return a?.image ? `/api/actors/${props.data.actor}/image/${a.image}?v=${a.v || 0}` : null
  }
  if (t.value === 'photo' || t.value === 'hero') return fileUrl(props.data.file || props.data.photo)
  if (t.value === 'scene' || t.value === 'v2v' || t.value === 'facefix') return s?.state === 'ready' ? fileUrl(s.png) : null
  if (t.value === 'frame' || t.value === 'picture') return s?.state === 'ready' ? fileUrl(s.file) : null
  return null
})

// the state in words, the job's first
const status = computed(() => {
  const r = row.value, s = st.value, j = job.value
  if (r) {
    if (r.status === 'running') {
      const step = j && j.phase === 'sampling' && j.steps ? tx('nodes.card.step', { a: j.step, b: j.steps }) : j?.phase === 'loading' ? tx('nodes.card.loading') : ''
      return { cls: 'now', text: (t.value === 'writer' || t.value === 'clip_writer' || t.value === 'pool_writer' || t.value === 'screenplay' ? tx('nodes.card.writing') : t.value === 'hero' ? tx('nodes.card.describing') : tx('nodes.card.going')) + step }
    }
    if (r.status === 'done') return { cls: 'ok', text: r.seconds ? tx('nodes.card.doneS', { s: Math.round(r.seconds) }) : tx('nodes.card.done') }
    if (r.status === 'cached') return { cls: 'ok', text: tx('nodes.card.cached') }
    if (r.status === 'error') return { cls: 'bad', text: r.error || tx('nodes.card.error') }
    if (r.status === 'blocked') return { cls: 'warn', text: tx('nodes.card.blocked') }
    if (r.status === 'skipped') return { cls: 'muted', text: tx('nodes.card.skipped') }
    if (r.status === 'queued') return { cls: 'muted', text: r.estimate ? tx('nodes.card.queuedEst', { t: mins(r.estimate) }) : tx('nodes.card.queued') }
  }
  if (!s) return { cls: 'muted', text: '' }
  const make = tx(t.value === 'scene' ? 'nodes.card.toShoot' : t.value === 'picture' ? 'nodes.card.draw' : t.value === 'v2v' || t.value === 'facefix' ? 'nodes.card.rebuild' : 'nodes.card.build')
  switch (s.state) {
    case 'ready': return { cls: 'ok', text: ['scene', 'v2v', 'facefix', 'sound', 'picture', 'frame', 'join', 'montage', 'beat_montage', 'music', 'output'].includes(t.value) ? tx('nodes.card.done') : t.value === 'writer' || t.value === 'clip_writer' || t.value === 'pool_writer' || t.value === 'screenplay' ? tx('nodes.card.written') : '' }
    case 'todo': return { cls: 'todo', text: make }
    case 'wait': return { cls: 'muted', text: t.value === 'scene' ? tx('nodes.card.waitStart') : tx('nodes.card.waitInputs') }
    case 'blocked': return { cls: 'warn', text: tx('nodes.card.inputError') }
    case 'error': return { cls: 'bad', text: s.error || tx('nodes.card.error') }
    case 'stale': return { cls: 'warn', text: t.value === 'writer' || t.value === 'clip_writer' || t.value === 'pool_writer' ? tx('nodes.card.writerStale') : tx('nodes.card.heroStale') }
    case 'empty': return { cls: 'muted', text: t.value === 'writer' || t.value === 'clip_writer' || t.value === 'pool_writer' ? tx('nodes.card.writerEmpty') : tx('nodes.card.heroEmpty') }
    default: return { cls: 'muted', text: '' }
  }
})

const body = computed(() => {
  const d = props.data
  switch (t.value) {
    case 'prompt': case 'idea': return d.text || ''
    case 'picture': return inputsOf(props.id, 'text').length ? '' : d.prompt || ''
    case 'hero': { const a = d.actor ? st.value?.actor : null; return a ? [a.name, a.look_ru || a.look_en].filter(Boolean).join(String.fromCharCode(10)) : d.ru || d.en || '' }   // an actor's name and look, not the template's old text
    case 'note': return d.text || ''
    case 'track': return d.name || tx('nodes.card.noFile')
    case 'lora': return (d.items || []).map((x: any) => `${x.name || x.id} · ${x.strength}`).join('\n') || tx('nodes.card.empty')
    case 'music': return tx('nodes.card.music', { a: Math.round((d.volume ?? 0.9) * 100), b: Math.round((d.scene_volume ?? 0.3) * 100) })
    case 'output': return outLabel({ output: d.output })
    case 'v2v': { const l = S.loras.find((x) => x.id === d.lora); return l ? `${l.name}${l.v2v?.out === 'matte' ? tx('nodes.card.noBg') : ''}` : tx('nodes.card.noLora') }
    case 'sound': return d.voice === false ? tx('nodes.card.allSound') : tx('nodes.card.voiceOnly')
    case 'facefix': { const n = st.value?.note; return tx(`nodesPanel.ffModes.${d.mode || 'far'}`) + (n ? (n.faces ? tx('nodes.card.ffFixed', { n: n.fixed }) : tx('nodes.card.ffNone')) : '') }
    case 'frame': return d.at === 'last' || d.at == null || d.at === '' ? tx('nodes.card.lastFrame') : tx('nodes.card.frameAt', { s: dec(d.at) })
    case 'join': return tx('nodes.card.joinN', inputsOf(props.id, 'clips').length)
    case 'montage': { const e = d.edit, n = inputsOf(props.id, 'clips').length; return `${tx('nodes.card.montageN', n)}${d.beats ? tx('nodes.card.beats') : ''}${e ? tx('nodes.card.ownEdit') : tx('nodes.card.asInput')}${st.value?.seconds ? tx('nodes.card.secs', { s: Math.round(st.value.seconds) }) : ''}` }
    case 'song': { const pc = st.value?.piece; return !d.file ? tx('nodes.card.songNone') : `${d.name || ''}${pc ? '\n' + tx('nodes.card.songPiece', { a: mmss(pc[0]), b: mmss(pc[1]), s: Math.round(pc[1] - pc[0]) }) : ''}` }
    case 'series': return d.look && d.look !== 'auto' ? [d.title, tx('screenplay.series.card', { look: lookName(d.look) })].filter(Boolean).join('\n') : d.title || ''
    case 'screenplay': {
      const sp = screenplayStats(String(d.text ?? ''))   // read from the node's current text on every change
      return sp.shots ? tx('screenplay.play.card', { s: sp.scenes, n: sp.shots }) : tx('screenplay.play.cardNew')
    }
    case 'pool_writer': return (d.pool || []).length ? tx('beat.card.pool', { n: d.pool.length }, d.pool.length) : tx('beat.card.poolNew')
    case 'clip_writer': { const p = d.plan; return p ? tx('nodes.card.clipPlan', { title: p.title_ru || tx('nodes.card.storyboard') }, p.scenes.length) : tx('nodes.card.clipNew') }
    case 'writer': { const p = d.plan; return p ? tx('nodes.card.writerPlan', { title: p.title_ru || tx('nodes.card.storyboard') }, p.scenes.length) : tx('nodes.card.writerNew', { s: d.seconds || 15, mood: d.mood || '' }) }
    default: return ''
  }
})
const lines = computed(() => (t.value === 'prompt' ? (props.data.lines || []).filter((l: any) => l.text?.trim()) : []))
// something missing: the card says what (the panel says more)
const need = computed(() => { const x = nextStep(props.id); return x && x.setup && !row.value ? x.text : '' })
const badges = computed(() => {
  if (t.value !== 'scene') return []
  const d = props.data, out: string[] = []
  const takes = d.takes || [], secs = secondsOf(nodeOf(props.id))
  if (secs !== 5) out.push(tx('nodes.card.badgeS', { s: dec(secs) }))
  if (takes.length > 1) out.push(tx('nodes.card.badgeTake', { a: (d.take || 0) + 1, b: takes.length }))
  const start = inputsOf(props.id, 'start')[0], from = start ? nodeOf(start.source) : null
  if (from) out.push(tx(['scene', 'frame'].includes(tOf(from)) ? 'nodes.card.fromFrame' : tOf(from) === 'picture' ? 'nodes.card.fromPicture' : 'nodes.card.fromPhoto'))
  if (inputsOf(props.id, 'end').length) out.push(tx('nodes.card.toFrame'))
  const ref = refLoraOf(props.id)
  if (ref?.v2v) out.push(tx(ref.v2v.reads === 'voice' ? 'nodes.card.byVoice' : 'nodes.card.byClip', { e: ENGINE_NAME[ref.v2v.engine] }))
  else if (inputsOf(props.id, 'faces').length) out.push('Ref2VA')
  if (inputsOf(props.id, 'lora').length && !ref) out.push('LoRA')
  if (d.model) out.push(S.cfg?.video_models?.find((m) => m.id === d.model)?.short || d.model)   // a scene of its own model
  if (d.look && d.look !== 'auto') out.push(`◆ ${tx('looks.lookChip', { name: lookName(d.look) })}`)   // the scene's own look (app/graph.look_text)
  return out
})
</script>

<template>
  <div class="ge-node" :class="[`t-${t}`, { sel: selected, now: status.cls === 'now', bad: status.cls === 'bad', sized: !!data.h }]" :style="{ '--h': WHO_COLOR[spec?.who || 'none'], ...sized }">
    <Handle v-for="([p, s], k) in ins" :id="p" :key="'i' + p" type="target" :position="Position.Left" :style="{ top: top(k), background: PORT_COLOR[s.type] }"
      :class="{ multi: s.multi }" :title="`${PORT_LABEL[p] || p}${s.multi ? tx('nodes.card.multi') : ''}`" />
    <Handle v-for="([p, ty], k) in outs" :id="p" :key="'o' + p" type="source" :position="Position.Right" :style="{ top: top(k), background: PORT_COLOR[ty] }"
      :title="PORT_LABEL[p] || p" />
    <span v-for="([p], k) in ins" :key="'li' + p" class="pl in" :style="{ top: top(k) }">{{ PORT_LABEL[p] || p }}</span>
    <span v-for="([p], k) in outs" :key="'lo' + p" class="pl out" :style="{ top: top(k) }">{{ PORT_LABEL[p] || p }}</span>
    <div class="ge-in"><!-- what the tile holds; the ports and their labels stay outside it, so a sized tile clips only this -->
    <header><Icon :name="(t === 'hero' && data.kind ? KIND_ICON[data.kind] : ICON[t]) || 'layers'" :size="14" /><b>{{ title }}</b><span class="grow" />
      <span v-if="t === 'scene' && data.takes?.length" class="seed" :title="tx('nodes.card.seed')">#{{ data.takes[data.take || 0] }}</span></header>
    <div v-if="img || ['scene', 'v2v', 'facefix', 'picture', 'frame'].includes(t)" class="ge-thumb" :class="{ alpha: t === 'v2v' && st?.alpha }">
      <img v-if="img" :src="img" alt="" draggable="false">
      <button v-if="img" type="button" class="ge-zoom nodrag nopan" :aria-label="tx('zoom.open')" :title="tx('zoom.open')" @click.stop="openZoom(img, title, graphPics())" @dblclick.stop><Icon name="expand" :size="13" /></button>
      <span v-else class="none">{{ tx(t === 'scene' ? 'nodes.card.notShot' : t === 'v2v' || t === 'facefix' ? 'nodes.card.notBuilt' : t === 'picture' ? 'nodes.card.notDrawn' : 'nodes.card.noFrame') }}</span>
    </div>
    <p v-if="body" class="ge-body">{{ body }}</p>
    <p v-for="(l, i) in lines.slice(0, 2)" :key="i" class="ge-line"><b>{{ l.who }}:</b> «{{ l.text }}»</p>
    <p v-if="t === 'scene' && st?.warn" class="ge-warn" :title="st.warn"><Icon name="warn" :size="12" />{{ tx('nodes.card.faceDrift') }}</p>
    <p v-if="t === 'scene' && st?.frame_look" class="ge-warn" :title="tx('looks.needFrame', { name: lookName(st.frame_look) })"><Icon name="warn" :size="12" />{{ tx('looks.needFrameCard', { name: lookName(st.frame_look) }) }}</p>
    <p v-if="t === 'scene' && st?.checks?.length" class="ge-warn" :title="st.checks.map((x) => tx('nodes.card.checkAt', { name: x.name, at: dec(x.at) })).join('; ')"><Icon name="warn" :size="12" />{{ st.checks[0].name }}{{ st.checks.length > 1 ? tx('nodes.card.andMore', { n: st.checks.length - 1 }) : '' }}</p>
    <div v-if="badges.length" class="ge-badges"><span v-for="b in badges" :key="b">{{ b }}</span></div>
    <RoleSelect v-if="t === 'scene' && data.role" :id="id" compact />
    <div v-if="t === 'screenplay'" class="ge-acts nodrag nopan">
      <button type="button" class="btn" :disabled="!!job || !inputsOf(id, 'idea').length" @click.stop="runLlm([id])"><Icon name="spark" :size="13" />{{ tx('screenplay.play.write') }}</button>
      <button type="button" class="btn" :disabled="!!job || !(data.text || '').trim()" @click.stop="expand(id)"><Icon name="layers" :size="13" />{{ tx('screenplay.play.expand') }}</button></div>
    <div v-if="t === 'pool_writer'" class="ge-acts nodrag nopan">
      <button type="button" class="btn" :disabled="!!job || !inputsOf(id, 'song').length" @click.stop="runLlm([id])"><Icon name="spark" :size="13" />{{ tx('nodesPanel.write') }}</button>
      <button type="button" class="btn" :disabled="!!job || !(data.pool || []).length" @click.stop="expand(id)"><Icon name="layers" :size="13" />{{ tx('nodesPanel.expand') }}</button></div>
    <WriterThinking v-if="(t === 'writer' || t === 'clip_writer' || t === 'pool_writer' || t === 'screenplay') && job" class="ge-think" :job="job" :node="id" compact />
    <p v-if="need" class="ge-need" :title="need"><Icon name="forward" :size="12" />{{ need }}</p>
    <footer v-if="status.text" :class="status.cls" :title="status.text">{{ status.text }}</footer>
    </div>
    <i class="ge-rsz nodrag nopan" :title="tx('nodes.card.resize')" @pointerdown="rsz.start" @dblclick="rsz.reset" />
  </div>
</template>
