<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const data = ref<any>(null)
const loading = ref(false)
const drawerOpen = ref(false)

async function refresh() {
  // 只读视图：与「放不下」「运行抽屉」同源 /allocate/state
  loading.value = true
  try {
    data.value = await api('/allocate/state?segment_id=1')
  } finally {
    loading.value = false
  }
}
onMounted(refresh)

const colors = ['#e8a87c','#85dcb8','#e27d60','#c38d9e','#41b3a3','#f4a261','#e76f51']
const cells = computed(() => {
  if (!data.value) return []
  const width = data.value.segment.width_m
  const out: any[] = []
  for (const p of data.value.pillars || []) {
    out.push({ type: 'pillar', start: p.position_m - p.thickness_m/2, w: p.thickness_m, label: p.label || '挡柱' })
  }
  for (const [i, p] of (data.value.placements || []).entries()) {
    out.push({ type: 'stall', start: p.start_m, w: p.width_m, label: p.vendor_name, color: colors[i % colors.length] })
  }
  return out.sort((a,b) => a.start - b.start).map(c => ({ ...c, pct: Math.max((c.w / width) * 100, 2) }))
})

const runById = computed(() => {
  const m = new Map<number, any>()
  for (const r of data.value?.runs || []) m.set(r.placement_id, r)
  return m
})
function fmtTime(iso: string) {
  return iso.replace('T', ' ').slice(0, 19)
}
</script>
<template>
  <div class="ss-street-wrap">
    <div style="display:flex;align-items:center;gap:0.75rem">
      <h1 style="margin:0">街段分配带</h1>
      <button class="btn" style="background:var(--ss-curb)" :disabled="loading" @click="refresh">
        {{ loading ? '读取中…' : '刷新（只读）' }}
      </button>
      <button class="btn" @click="drawerOpen = !drawerOpen">
        运行抽屉（{{ data?.runs?.length ?? 0 }} 条成功运行）
      </button>
    </div>
    <p class="sub">只读：仅展示已确认落库的放置；预估与放置请到「柱间紧张度」勾选空档后确认</p>

    <template v-if="data">
      <div class="ss-band-ruler">
        <span>0 m</span>
        <span>{{ data.segment.name }} · {{ data.segment.width_m }} m</span>
        <span>{{ data.segment.width_m }} m</span>
      </div>
      <div class="ss-street-band">
        <div class="ss-street-inner">
          <div
            v-for="(c,i) in cells" :key="i"
            class="ss-band-cell"
            :class="{ 'ss-pillar': c.type === 'pillar' }"
            :style="{ width: c.pct + '%', background: c.type === 'pillar' ? undefined : c.color, flex: '0 0 ' + c.pct + '%' }"
          >{{ c.label }}</div>
        </div>
      </div>

      <div class="card">
        <strong>已落库放置（{{ data.placements.length }}）</strong>
        <table style="margin-top:0.4rem">
          <thead><tr><th>运行</th><th>摊主</th><th>起点</th><th>终点</th><th>宽度</th></tr></thead>
          <tbody>
            <tr v-for="p in data.placements" :key="p.id">
              <td><span class="badge badge-ok">#{{ runById.get(p.id)?.id ?? '—' }}</span></td>
              <td>{{ p.vendor_name }}</td><td>{{ p.start_m }}</td><td>{{ p.end_m }}</td><td>{{ p.width_m }}</td>
            </tr>
            <tr v-if="!data.placements.length"><td colspan="5" class="muted">尚无落库放置（紧张度表数字不是放置）</td></tr>
          </tbody>
        </table>
      </div>

      <div class="card" v-if="drawerOpen">
        <strong>运行抽屉</strong>
        <p class="muted" style="font-size:0.78rem;margin:0.2rem 0 0.5rem">
          只有确认成功才会出现一行；被拦下（未选中 / 多选 / 拒空跑）不会进此抽屉，也不会清掉既有运行。
        </p>
        <table>
          <thead><tr><th>运行#</th><th>关联放置</th><th>落库时间</th></tr></thead>
          <tbody>
            <tr v-for="r in data.runs" :key="r.id">
              <td>#{{ r.id }}</td>
              <td>placement #{{ r.placement_id }}</td>
              <td>{{ fmtTime(r.created_at) }}</td>
            </tr>
            <tr v-if="!data.runs.length"><td colspan="3" class="muted">暂无成功运行</td></tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
