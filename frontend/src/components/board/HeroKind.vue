<script setup lang="ts">
// Who a hero is: a person, an animal, a robot or a creature (cast[i].kind, rules_v 4 plans; no kind = a person). Chips with an
// icon each; `compact` is one select with the icon before it (the hero card's name row). v-model: the kind.
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import { KINDS, KIND_ICON } from '../../lib/consts'

const { t } = useI18n()
// `faceless` adds «Без лица» (a beat clip's hero, graph projects only)
const props = defineProps<{ modelValue?: string; compact?: boolean; faceless?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [kind: string] }>()
const cur = () => props.modelValue || 'person'
</script>

<template>
  <label v-if="compact" class="hk-sel" :title="t('board.cast.kindHelp')"><Icon :name="KIND_ICON[cur()]" :size="16" />
    <select class="cc-inl" :aria-label="t('board.cast.kind')" :value="cur()" @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)">
      <option v-for="[k, v] in KINDS" :key="k" :value="k">{{ v }}</option></select></label>
  <span v-else class="chips" role="radiogroup" :aria-label="t('board.cast.kind')">
    <button v-for="[k, v] in KINDS" :key="k" type="button" role="radio" class="chip" :class="{ on: cur() === k }" :aria-checked="cur() === k" @click="emit('update:modelValue', k)">
      <Icon :name="KIND_ICON[k]" :size="16" />{{ v }}</button>
    <button v-if="faceless" type="button" role="radio" class="chip" :class="{ on: cur() === 'faceless' }" :aria-checked="cur() === 'faceless'" @click="emit('update:modelValue', 'faceless')">
      <Icon :name="KIND_ICON.faceless" :size="16" />{{ t('beat.hero.faceless') }}</button></span>
</template>

<style scoped>
.hk-sel { display: inline-flex; align-items: center; gap: 6px; color: var(--accent, currentColor); }
.hk-sel select { color: var(--text); }
</style>
