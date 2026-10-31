<script setup lang="ts">
// A node of a graph project: its ports from the server's types (inputs left, outputs right, coloured by type), the
// header in the colour of who does the work, what it holds, and its state - the live job's, else the server's.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Handle, Position } from '@vue-flow/core'
import Icon from '../Icon.vue'
import { ENGINE_NAME, GE, ICON, PORT_COLOR, PORT_LABEL, WHO_COLOR, fileUrl, inputsOf, live, nodeOf, refLoraOf, secondsOf, tOf, typeTitle } from '../../lib/graphDoc'
import { outLabel } from '../../lib/project'
import { nextStep } from '../../lib/nodeHelp'
import { dec, mins } from '../../lib/format'
import { S } from '../../lib/store'
import { useResize } from './resize'

const props = defineProps<{ id: string; data: Record<string, any>; selected?: boolean }>()
const { t: tx } = useI18n()
const t = computed(() => props.data.t as string)
const rsz = useResize(() => props.id)
// the tile's own size (dragged by its corner): with a height the body fills it instead of its usual few lines
const sized = computed(() => ({ width: props.data.w ? `${props.data.w}px` : undefined, height: props.data.h ? `${props.data.h}px` : undefined }))
const spec = computed(() => GE.types[t.value])
// a «Картинка» by Krea 2 reads its text alone: no «образцы» port (FLUX.2 Klein has it)
const ins = computed(() => Object.entries(spec.value?.in || {}).filter(([p]) => !(p === 'ref' && t.value === 'picture' && props.data.model !== 'flux2')))
const outs = computed(() => Object.entries(spec.value?.out || {}))
const st = computed(() => GE.state?.nodes[props.id])
const job = computed(() => live())
const row = computed(() => job.value?.progress?.nodes?.[props.id] as Record<string, any> | undefined)
const top = (k: number) => `${50 + k * 24}px`
const title = computed(() => props.data.title || typeTitle(t.value))
const img = computed(() => {
  const s = st.value
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
      return { cls: 'now', text: (t.value === 'writer' ? tx('nodes.card.writing') : t.value === 'hero' ? tx('nodes.card.describing') : tx('nodes.card.going')) + step }
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
    case 'ready': return { cls: 'ok', text: ['scene', 'v2v', 'facefix', 'sound', 'picture', 'frame', 'join', 'montage', 'music', 'output'].includes(t.value) ? tx('nodes.card.done') : t.value === 'writer' ? tx('nodes.card.written') : '' }
    case 'todo': return { cls: 'todo', text: make }
    case 'wait': return { cls: 'muted', text: t.value === 'scene' ? tx('nodes.card.waitStart') : tx('nodes.card.waitInputs') }
    case 'blocked': return { cls: 'warn', text: tx('nodes.card.inputError') }
    case 'error': return { cls: 'bad', text: s.error || tx('nodes.card.error') }
    case 'stale': return { cls: 'warn', text: t.value === 'writer' ? tx('nodes.card.writerStale') : tx('nodes.card.heroStale') }
    case 'empty': return { cls: 'muted', text: t.value === 'writer' ? tx('nodes.card.writerEmpty') : tx('nodes.card.heroEmpty') }
    default: return { cls: 'muted', text: '' }
  }
})

const body = computed(() => {
  const d = props.data
  switch (t.value) {
    case 'prompt': case 'idea': return d.text || ''
    case 'picture': return inputsOf(props.id, 'text').length ? '' : d.prompt || ''
    case 'hero': return d.ru || d.en || ''
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
    case 'montage': { const e = d.edit, n = inputsOf(props.id, 'clips').length; return `${tx('nodes.card.montageN', n)}${e ? tx('nodes.card.ownEdit') : tx('nodes.card.asInput')}${st.value?.seconds ? tx('nodes.card.secs', { s: Math.round(st.value.seconds) }) : ''}` }
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
  if (secs !== 5) out.push(tx('nodes.card.badgeS', { s: secs }))
  if (takes.length > 1) out.push(tx('nodes.card.badgeTake', { a: (d.take || 0) + 1, b: takes.length }))
  const start = inputsOf(props.id, 'start')[0], from = start ? nodeOf(start.source) : null
  if (from) out.push(tx(['scene', 'frame'].includes(tOf(from)) ? 'nodes.card.fromFrame' : tOf(from) === 'picture' ? 'nodes.card.fromPicture' : 'nodes.card.fromPhoto'))
  if (inputsOf(props.id, 'end').length) out.push(tx('nodes.card.toFrame'))
  const ref = refLoraOf(props.id)
  if (ref?.v2v) out.push(tx(ref.v2v.reads === 'voice' ? 'nodes.card.byVoice' : 'nodes.card.byClip', { e: ENGINE_NAME[ref.v2v.engine] }))
  else if (inputsOf(props.id, 'faces').length) out.push('Ref2VA')
  if (inputsOf(props.id, 'lora').length && !ref) out.push('LoRA')
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
    <header><Icon :name="ICON[t] || 'layers'" :size="14" /><b>{{ title }}</b><span class="grow" />
      <span v-if="t === 'scene' && data.takes?.length" class="seed" :title="tx('nodes.card.seed')">#{{ data.takes[data.take || 0] }}</span></header>
    <div v-if="img || ['scene', 'v2v', 'facefix', 'picture', 'frame'].includes(t)" class="ge-thumb" :class="{ alpha: t === 'v2v' && st?.alpha }">
      <img v-if="img" :src="img" alt="" draggable="false">
      <span v-else class="none">{{ tx(t === 'scene' ? 'nodes.card.notShot' : t === 'v2v' || t === 'facefix' ? 'nodes.card.notBuilt' : t === 'picture' ? 'nodes.card.notDrawn' : 'nodes.card.noFrame') }}</span>
    </div>
    <p v-if="body" class="ge-body">{{ body }}</p>
    <p v-for="(l, i) in lines.slice(0, 2)" :key="i" class="ge-line"><b>{{ l.who }}:</b> «{{ l.text }}»</p>
    <p v-if="t === 'scene' && st?.warn" class="ge-warn" :title="st.warn"><Icon name="warn" :size="12" />{{ tx('nodes.card.faceDrift') }}</p>
    <p v-if="t === 'scene' && st?.checks?.length" class="ge-warn" :title="st.checks.map((x) => tx('nodes.card.checkAt', { name: x.name, at: dec(x.at) })).join('; ')"><Icon name="warn" :size="12" />{{ st.checks[0].name }}{{ st.checks.length > 1 ? tx('nodes.card.andMore', { n: st.checks.length - 1 }) : '' }}</p>
    <div v-if="badges.length" class="ge-badges"><span v-for="b in badges" :key="b">{{ b }}</span></div>
    <p v-if="need" class="ge-need" :title="need"><Icon name="forward" :size="12" />{{ need }}</p>
    <footer v-if="status.text" :class="status.cls" :title="status.text">{{ status.text }}</footer>
    </div>
    <i class="ge-rsz nodrag nopan" :title="tx('nodes.card.resize')" @pointerdown="rsz.start" @dblclick="rsz.reset" />
  </div>
</template>
