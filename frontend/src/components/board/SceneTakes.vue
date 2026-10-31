<script setup lang="ts">
// A scene's takes and its own LoRA: every take shot stays in the cache, the chosen one (seed) goes into the video and
// the continuations; «Ещё дубль» shoots one more now, this scene alone. LoRA: as the video, its own set, or none.
// The storyboard's panel and its graph view share it; a change is saved at once. The scene's full page shows the takes
// itself (loraOnly); the panel's tabs show the takes (takesOnly) and the LoRA (loraOnly) apart.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import HelpQ from '../HelpQ.vue'
import { S, lorasFor } from '../../lib/store'
import { P, scheduleSave } from '../../lib/project'
import { moreTake, openerOf, pickTake, takesOf, taking } from '../../lib/board'
import type { Scene } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ s: Scene; loraOnly?: boolean; takesOnly?: boolean }>()
const proj = computed(() => P.proj!)
const fileUrl = (path: string) => `/api/projects/${proj.value.id}/files/${path}`

const takes = computed(() => takesOf(props.s))
const busy = computed(taking)
function dropTake(seed: number) {
  const left = takes.value.map((x) => x.seed).filter((x) => x !== seed)
  if (!left.length) return
  props.s.takes = left
  if (props.s.seed === seed) props.s.seed = left[left.length - 1]
  scheduleSave()
}

const ownOpen = ref(false)
const loraMode = computed(() => (!Array.isArray(props.s.loras) ? 'video' : props.s.loras.length || ownOpen.value ? 'own' : 'none'))
function setLoraMode(m: string) {
  ownOpen.value = m === 'own'
  if (m === 'video') delete props.s.loras
  else props.s.loras = m === 'own' ? JSON.parse(JSON.stringify(proj.value.settings.loras || [])) : []
  scheduleSave()
}
const sceneModel = computed(() => (P.proj?.plan && openerOf(P.proj.plan, props.s) || props.s).model || proj.value.settings.video_model || 'h3')
const loraRest = computed(() => lorasFor(sceneModel.value).filter((l) => l.verdict !== 'blocked' && !(props.s.loras || []).some((u: any) => u.id === l.id)))
const loraName = (id: string) => S.loras.find((l) => l.id === id)?.name || id.split(/[\\/]/).pop()
function addLora(e: Event) {
  const l = S.loras.find((x) => x.id === (e.target as HTMLSelectElement).value)
  if (l) { props.s.loras = [...(props.s.loras || []), { id: l.id, strength: l.strength ?? 0.8 }]; scheduleSave() }
  ;(e.target as HTMLSelectElement).value = ''
}
const projLoras = computed(() => (proj.value.settings.loras || []).map((x: any) => loraName(x.id)).join(', ') || t('common.none'))
</script>

<template>
  <div v-if="!loraOnly" class="stack takes-box" style="gap:8px"><span class="lbl">{{ t('board.takes.label') }} <HelpQ id="inspector" term="Дубли" /> <small>{{ t('board.takes.sub') }}</small></span>
    <div class="takes"><button v-for="(tk, i) in takes" :key="tk.seed" type="button" class="take" :class="{ on: tk.seed === s.seed }" :title="t('board.takes.seed', { seed: tk.seed }) + (tk.cached ? '' : ' · ' + t('board.takes.notShot'))" @click="pickTake(s, tk.seed)">
      <img v-if="tk.cached && tk.key" :src="fileUrl(`scenes/${tk.key}.png`)" alt=""><span v-else>{{ tk.cached ? t('board.takes.shot') : t('board.takes.notShot') }}</span><b>{{ i + 1 }}</b>
      <i v-if="takes.length > 1" role="button" :aria-label="t('board.takes.drop')" :title="t('board.takes.dropTitle')" @click.stop="dropTake(tk.seed)">×</i></button></div>
    <button v-if="!takesOnly" type="button" class="btn" :disabled="busy" :title="t('board.takes.moreTitle')" @click="moreTake(s)"><Icon name="clapper" />{{ busy ? t('board.takes.taking') : t('board.takes.more') }}</button>
  </div>

  <div v-if="!takesOnly" class="stack" style="gap:8px"><span class="lbl">{{ t('board.takes.lora') }} <HelpQ id="inspector" term="LoRA сцены" /></span>
    <div class="seg"><button v-for="m in ['video', 'own', 'none']" :key="m" type="button" :class="{ on: loraMode === m }" @click="setLoraMode(m)">{{ t(`board.takes.loraMode.${m}`) }}</button></div>
    <span v-if="loraMode === 'video'" class="muted" style="font-size:12.5px">{{ t('board.takes.videoLoras', { x: projLoras }) }}</span>
    <template v-else-if="loraMode === 'own'">
      <div v-for="(u, i) in s.loras" :key="u.id" class="lora-row"><span class="grow" :title="u.id">{{ loraName(u.id) }}</span>
        <input class="field-in" type="number" step="0.05" min="-2" max="2" style="width:84px" :value="u.strength" :aria-label="t('board.takes.strength')" @change="u.strength = +($event.target as HTMLInputElement).value; scheduleSave()">
        <button type="button" class="ghost" :aria-label="t('board.look.remove')" @click="s.loras.splice(i, 1); scheduleSave()"><Icon name="close" /></button></div>
      <select class="field-in" @change="addLora"><option value="">{{ t('board.takes.addLora') }}</option><option v-for="l in loraRest" :key="l.id" :value="l.id">{{ l.name }}</option></select>
    </template>
  </div>
</template>
