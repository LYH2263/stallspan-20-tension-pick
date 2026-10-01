<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, SEGMENT_ID } from '../api'

const data = ref<any>(null)
const err = ref('')
async function load() {
  try { data.value = await api(`/allocate/state?segment_id=${SEGMENT_ID}`) }
  catch (e: any) { err.value = e?.message || String(e) }
}
onMounted(load)

const colors = ['#e8a87c','#85dcb8','#e27d60','#c38d9e','#41b3a3','#f4a261','#e76f51']

// 主图 = 挡柱 + 已入库放置，与下方名单、放不下、运行抽屉同源（/allocate/state）。
const cells = computed(() => {
  if (!data.value) return []
  const width = data.value.segment.width_m
  const out: any[] = []
  for (const p of data.value.pillars || []) {
    out.push({ type: 'pillar', start: p.position_m - p.thickness_m / 2,
               w: p.thickness_m, label: p.label || '挡柱' })
  }
  for (const [i, p] of (data.value.placements || []).entries()) {
    out.push({ type: 'stall', start: p.start_m, w: p.width_m,
               label: p.vendor_name, color: colors[i % colors.length] })
  }
  return out.sort((a, b) => a.start - b.start)
    .map(c => ({ ...c, pct: Math.max((c.w / width) * 100, c.type === 'pillar' ? 1.2 : 2) }))
})
</script>
<template>
  <div class="ss-street-wrap">
    <h1>街段分配带</h1>
    <p class="sub">只读视图：只展示已确认落库的放置与运行记录，打开此页不会产生任何新行</p>
    <p v-if="err" class="ss-msg ss-msg-err">{{ err }}</p>
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

      <div class="ss-two-col">
        <div class="card">
          <h2 class="ss-sub-head">已落库名单（主图即此名单）</h2>
          <table>
            <thead><tr><th>摊主</th><th>起点</th><th>终点</th><th>宽度</th></tr></thead>
            <tbody>
              <tr v-for="p in data.placements" :key="p.vendor_id">
                <td>{{ p.vendor_name }}</td><td>{{ p.start_m }}</td><td>{{ p.end_m }}</td><td>{{ p.width_m }}</td>
              </tr>
            </tbody>
          </table>
          <p v-if="!data.placements.length" class="muted">尚无已确认落库的放置，去「柱间紧张度」勾选空档确认。</p>
        </div>

        <div class="card">
          <h2 class="ss-sub-head">放不下（实时，仍待安置）</h2>
          <table>
            <thead><tr><th>摊主</th><th>需求宽度</th><th>原因</th></tr></thead>
            <tbody>
              <tr v-for="r in data.rejected" :key="r.vendor_id">
                <td>{{ r.vendor_name }}</td><td>{{ r.width_m }}</td><td>{{ r.reason }}</td>
              </tr>
            </tbody>
          </table>
          <p v-if="!data.rejected.length" class="muted">当前待安置摊主都能在某个柱间空档放下。</p>
        </div>
      </div>

      <div class="card">
        <h2 class="ss-sub-head">运行抽屉（每次成功确认一条；空跑不计）</h2>
        <table>
          <thead><tr><th>#</th><th>时间</th><th>选中空档 (m)</th><th>本运行落位</th></tr></thead>
          <tbody>
            <tr v-for="run in data.runs" :key="run.id">
              <td>{{ run.id }}</td>
              <td>{{ run.created_at }}</td>
              <td>{{ run.span_start_m }} – {{ run.span_end_m }}</td>
              <td>{{ run.placements.map((p: any) => `${p.vendor_name}(${p.start_m}-${p.end_m})`).join('、') }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!data.runs.length" class="muted">还没有成功运行。</p>
      </div>
    </template>
  </div>
</template>
