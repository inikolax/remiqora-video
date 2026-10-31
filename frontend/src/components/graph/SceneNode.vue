<script setup lang="ts">
// A scene on the graph: its number and time, how it starts, the last frame of its shot, what happens, and the
// state of the shot in the words of the video screen. Ports: start (a last frame or a photo), who (the looks),
// faces (Ref2VA's photos) in; frame (its last frame) and clip (the shot) out.
import { computed, inject } from 'vue'
import { useI18n } from 'vue-i18n'
import { Handle, Position } from '@vue-flow/core'
import Icon from '../Icon.vue'
import { P, file } from '../../lib/project'
import { chainColor } from '../../lib/consts'
import { mmss } from '../../lib/format'
import { isRaw, startsFromPhoto } from '../../lib/board'
import { GRAPH } from './ctx'

const props = defineProps<{ id: string; data: { index: number } }>()
const G = inject(GRAPH)!
const { t: tx } = useI18n()
const i = computed(() => props.data.index)
const s = computed(() => P.proj!.plan!.scenes[i.value])
const row = computed(() => G.shots.rows.value[i.value])
const t = computed(() => (row.value ? G.shots.shot(row.value, i.value) : null))
const plan = computed(() => G.est.value?.scenes?.[i.value] as string | undefined)
const shotNow = computed(() => !!G.shots.job.value)
// the text changed since the shot: «Снять ролик» will shoot it again (the estimate knows the keys)
const stale = computed(() => !shotNow.value && plan.value === 'shoot' && (row.value?.status === 'done' || row.value?.status === 'cached'))
const inCache = computed(() => !shotNow.value && plan.value === 'cached' && row.value?.status === 'none')
const dim = computed(() => !!G.lit.value && !G.lit.value.has(props.id))
</script>

<template>
  <div class="gn gscene" :class="{ now: row?.status === 'running', dim }" :style="{ '--c': chainColor(s.chain) }">
    <Handle id="start" type="target" :position="Position.Left" class="p-image" style="top:58px" :title="tx('graph.sn.start')" />
    <Handle id="who" type="target" :position="Position.Left" class="p-look" style="top:110px" :connectable="false" />
    <Handle id="faces" type="target" :position="Position.Left" class="p-face" style="top:162px" :connectable="false" />
    <Handle id="frame" type="source" :position="Position.Right" class="p-image" style="top:58px" :title="tx('graph.sn.frame')" />
    <Handle id="clip" type="source" :position="Position.Right" class="p-clip" style="top:162px" :connectable="false" />
    <span class="pl in" style="top:58px">{{ tx('graph.sn.pStart') }}</span><span class="pl in" style="top:110px">{{ tx('graph.sn.pWho') }}</span><span class="pl in" style="top:162px">{{ tx('graph.sn.pFaces') }}</span>
    <span class="pl out" style="top:58px">{{ tx('graph.sn.pFrame') }}</span><span class="pl out" style="top:162px">{{ tx('graph.sn.pClip') }}</span>
    <header>
      <Icon :name="s.kind === 'new' ? 'clapper' : 'link'" :size="14" /><b>{{ i + 1 }}</b><span class="t">{{ mmss(s.start) }}–{{ mmss(s.end) }}</span>
      <span class="grow" />
      <span v-if="startsFromPhoto(s)" class="tag" :title="tx('graph.sn.fromPhoto')"><Icon name="image" :size="12" /></span>
      <span v-if="isRaw(s) && !P.proj!.plan!.manual" class="tag" :title="tx('graph.sn.ownPrompt')"><Icon name="pen" :size="12" /></span>
    </header>
    <div class="thumb">
      <img v-if="row?.png" :src="file(row.png)" :alt="tx('graph.sn.lastFrame', { n: i + 1 })" draggable="false">
      <span v-if="t && t.pct !== null" class="pct">{{ t.pct }}%</span>
      <span v-else-if="!row?.png" class="none">{{ s.kind === 'new' ? tx('graph.sn.newScene') : tx('graph.sn.continuation') }}</span>
    </div>
    <p class="ru">{{ s.ru || (isRaw(s) ? s.raw : '') || tx('graph.notWritten') }}</p>
    <footer>
      <span>{{ t?.cap }}</span>
      <span v-if="stale" class="warn" :title="tx('graph.sn.staleTitle')">{{ tx('graph.sn.stale') }}</span>
      <span v-else-if="inCache" class="ok" :title="tx('graph.sn.cacheTitle')">{{ tx('graph.sn.inCache') }}</span>
      <span v-else :class="t?.tone">{{ t?.st }}</span>
    </footer>
  </div>
</template>
