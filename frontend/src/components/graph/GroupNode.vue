<script setup lang="ts">
// A group: a titled frame behind nodes. Dragging it by its title moves the nodes inside (GraphEditView does that);
// its size is set in the panel.
import { useI18n } from 'vue-i18n'
import { useResize } from './resize'
const props = defineProps<{ id: string; data: Record<string, any>; selected?: boolean }>()
const { t } = useI18n()
const rsz = useResize(() => props.id, { w: 240, h: 120 }, { w: 4000, h: 4000 })
</script>

<template>
  <div class="ge-group" :class="{ sel: selected }" :style="{ width: `${data.w || 720}px`, height: `${data.h || 420}px`, '--g': data.color || '#2a2a38' }">
    <b>{{ data.title || t('nodes.title.group') }}</b>
    <i class="ge-rsz nodrag nopan" :title="t('nodes.card.resize')" @pointerdown="rsz.start" @dblclick="rsz.reset" />
  </div>
</template>
