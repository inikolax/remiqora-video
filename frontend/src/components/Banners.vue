<script setup lang="ts">
// The banners, bottom right: an error stays until closed (red), news goes by itself (the accent); a failed job's
// banner links to its page.
import { useI18n } from 'vue-i18n'
import { S, closeBanner } from '../lib/store'

const { t } = useI18n()
</script>

<template>
  <div id="banners" aria-live="polite">
    <div v-for="b in S.banners" :key="b.id" class="banner" :class="b.kind" :role="b.kind === 'error' ? 'alert' : undefined"><span>{{ b.text }}</span>
      <router-link v-if="b.to" class="banner-go" :to="b.to" @click="closeBanner(b.id)">{{ t('misc.bannerOpen') }}</router-link>
      <button v-if="b.act" type="button" class="banner-go" @click="b.act.run(); closeBanner(b.id)">{{ b.act.label }}</button>
      <button type="button" :aria-label="t('common.close')" @click="closeBanner(b.id)">×</button></div>
  </div>
</template>
