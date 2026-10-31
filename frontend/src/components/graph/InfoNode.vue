<script setup lang="ts">
// Every node but a scene: a person or the world, the style, LoRA, a start photo, the assembly, the music, the
// output. The header's colour says who does the work (lib/graph.ts WHO_COLOR); ports carry their type's colour.
import { computed, inject } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import Icon from '../Icon.vue'
import { WHO_COLOR, type InfoData } from '../../lib/graph'
import { GRAPH } from './ctx'

const props = defineProps<{ id: string; data: InfoData }>()
const G = inject(GRAPH)!
const step = computed(() => G.step(props.id))
const dim = computed(() => !!G.lit.value && !G.lit.value.has(props.id))
const top = (k: number) => `${58 + k * 30}px`
</script>

<template>
  <div class="gn ginfo" :class="[{ dim, now: step?.state === 'now' }, `w-${data.who}`]" :style="{ '--h': WHO_COLOR[data.who] }">
    <Handle v-for="(p, k) in data.inputs || []" :id="p.id" :key="'i' + p.id" type="target" :position="Position.Left" :class="`p-${p.type}`" :style="{ top: top(k) }" :connectable="false" />
    <Handle v-for="(p, k) in data.outputs || []" :id="p.id" :key="'o' + p.id" type="source" :position="Position.Right" :class="`p-${p.type}`" :style="{ top: top(k) }" :connectable="false" />
    <header><Icon :name="data.icon" :size="14" /><b>{{ data.title }}</b><span class="grow" /><span v-if="data.note" class="note">{{ data.note }}</span></header>
    <span v-for="(p, k) in data.inputs || []" :key="'li' + p.id" class="pl in" :style="{ top: top(k) }">{{ p.label }}</span>
    <span v-for="(p, k) in data.outputs || []" :key="'lo' + p.id" class="pl out" :style="{ top: top(k) }">{{ p.label }}</span>
    <img v-if="data.img" class="pic" :src="data.img" alt="" draggable="false">
    <span v-if="data.sub" class="sub">{{ data.sub }}</span>
    <p v-if="data.text" class="txt">{{ data.text }}</p>
    <footer v-if="step"><span :class="step.state === 'ok' ? 'ok' : step.state === 'stale' ? 'warn' : step.state === 'now' ? 'accent' : 'muted'">{{ step.text }}</span></footer>
  </div>
</template>
