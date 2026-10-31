<script setup lang="ts">
// The keys sheet (S.keys) of the graph or of the montage - whichever screen is open, after Remiqora's editor
// shortcut sheet: the title in the accent gradient, groups of cards, each an action on the left and its keys in
// accent chips on the right.
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import HelpModal from './HelpModal.vue'
import { editKeys, graphKeys } from '../../lib/content'
import { S } from '../../lib/store'

const route = useRoute()
const { t } = useI18n()
const edit = computed(() => route.name === 'edit' || route.name === 'gmontage')

const chips = (k: string) => k.split(' + ')
const isKey = (k: string) => /^(Ctrl|Shift|Esc|Delete|[A-ZА-Я?]|Backspace|Alt|Пробел|Space|Home|End|← \/ →|Home \/ End)$/.test(k)
</script>

<template>
  <HelpModal :open="S.keys" :title="edit ? t('helpui.keysEdit') : t('helpui.keysGraph')" gradient @close="S.keys = false">
    <div class="km">
      <section v-for="g in edit ? editKeys() : graphKeys()" :key="g.title">
        <h3><Icon :name="g.icon" :size="15" />{{ g.title }}</h3>
        <div class="km-grid">
          <div v-for="[act, keys] in g.rows" :key="act" class="km-row">
            <span>{{ act }}</span>
            <span class="km-keys"><template v-for="(k, i) in chips(keys)" :key="i"><span v-if="i" class="km-plus">+</span><kbd v-if="isKey(k)">{{ k }}</kbd><span v-else class="km-mouse">{{ k }}</span></template></span>
          </div>
        </div>
      </section>
      <p class="km-hint">{{ edit ? t('helpui.keysHintEdit') : t('helpui.keysHintGraph') }}</p>
    </div>
  </HelpModal>
</template>
