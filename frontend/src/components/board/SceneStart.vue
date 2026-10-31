<script setup lang="ts">
// How a scene starts: a new scene (text, its own place), or a continuation - from the last frame of the scene before
// it or of any earlier one (`from`). The storyboard's panel and its graph view share it; a change is saved at once.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import HelpQ from '../HelpQ.vue'
import { scheduleSave } from '../../lib/project'
import { isRaw } from '../../lib/board'
import type { Plan, Scene } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ p: Plan; s: Scene }>()
const startVal = computed(() => (props.s.kind === 'new' ? 'new' : props.s.from ? `from:${props.s.from}` : 'continue'))
const earlier = computed(() => props.p.scenes.slice(0, Math.max(0, props.s.index - 1)).filter((x) => x.id))
const fromIndex = computed(() => (props.p.scenes.find((x) => x.id === props.s.from)?.index ?? 0) + 1)
function setStart(v: string) {
  if (v === 'new') { props.s.kind = 'new'; delete props.s.from }
  else if (v === 'continue') { props.s.kind = 'continue'; delete props.s.from }
  else { props.s.kind = 'continue'; props.s.from = v.slice(5) }
  scheduleSave()
}
</script>

<template>
  <label><span class="lbl">{{ t('board.start.label') }} <HelpQ id="inspector" term="Начало" /></span><select class="field-in" :value="startVal" :disabled="s.index === 0" @change="setStart(($event.target as HTMLSelectElement).value)">
    <option value="new">{{ isRaw(s) ? t('board.start.newRaw') : t('board.start.new') }}</option>
    <option value="continue">{{ t('board.start.cont') }}</option>
    <option v-for="x in earlier" :key="x.id" :value="`from:${x.id}`">{{ t('board.start.contFrom', { n: x.index + 1 }) }}</option></select></label>
  <p v-if="s.from" class="muted" style="margin:-6px 0 0;font-size:12.5px">{{ t('board.start.back', { n: fromIndex }) }}</p>
</template>
