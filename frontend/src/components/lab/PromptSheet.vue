<script setup lang="ts">
// The lab's prompt field. With the markup on, the textarea's own text is transparent and a layer under it shows the
// same text coloured (lib/promptParts.ts), every paragraph with a Russian tag above it; the two scroll together.
import { computed, nextTick, ref, watch } from 'vue'
import { type Lang, markup as paint } from '../../lib/promptParts'

const model = defineModel<string>({ required: true })
// whole: the prompt is one paragraph without H3's parts (LTX, WAN) - the tag over it
const props = withDefaults(defineProps<{ markup: boolean; lang?: Lang; label: string; placeholder?: string; whole?: string }>(), { lang: 'en', placeholder: '', whole: undefined })
const el = ref<HTMLTextAreaElement | null>(null)
const layer = ref<HTMLElement | null>(null)
const html = computed(() => (props.markup ? paint(model.value, props.lang, props.whole) : ''))

const sync = () => { if (layer.value && el.value) layer.value.scrollTop = el.value.scrollTop }
watch(html, () => nextTick(sync))
defineExpose({ el })
</script>

<template>
  <div class="sheet" :class="{ markup }">
    <pre v-if="markup" ref="layer" class="hl" aria-hidden="true" v-html="html" />
    <textarea :id="`prompt-${lang}`" ref="el" v-model="model" spellcheck="false" :lang="lang" :aria-label="label" :placeholder="placeholder" @scroll="sync" />
  </div>
</template>
