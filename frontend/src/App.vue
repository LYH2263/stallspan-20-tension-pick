<script setup lang="ts">
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { computed } from 'vue'

const route = useRoute()
const title = computed(() => {
  const map: Record<string, string> = {
    '/days': '集日', '/segments': '街段', '/vendors': '摊主队列',
    '/tension': '柱间紧张度', '/map': '街段分配带', '/rejected': '放不下', '/pillars': '挡柱',
  }
  return map[route.path] || 'StallSpan'
})
</script>
<template>
  <div class="ss-shell">
    <header class="ss-market-bar">
      <div class="ss-market-brand">StallSpan · 摊档开间</div>
      <nav class="ss-market-nav">
        <RouterLink to="/days">集日</RouterLink>
        <RouterLink to="/segments">街段</RouterLink>
        <RouterLink to="/tension">紧张度</RouterLink>
        <RouterLink to="/map">分配带</RouterLink>
        <RouterLink to="/pillars">挡柱</RouterLink>
        <RouterLink to="/rejected">放不下</RouterLink>
        <RouterLink to="/vendors">摊主</RouterLink>
      </nav>
      <div class="ss-market-day">今日开市 · {{ title }}</div>
    </header>
    <main class="ss-stage">
      <RouterView />
    </main>
  </div>
</template>
