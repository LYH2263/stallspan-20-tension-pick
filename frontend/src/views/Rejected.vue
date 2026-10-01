<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const loading = ref(false)
async function refresh() {
  loading.value = true
  try {
    // 与主图、运行抽屉同源：/allocate/state，保证结论对齐
    const data = await api('/allocate/state?segment_id=1')
    rows.value = data.rejected || []
  } finally {
    loading.value = false
  }
}
onMounted(refresh)
</script>
<template>
  <div>
    <div style="display:flex;align-items:center;gap:0.75rem">
      <h1 style="margin:0">放不下</h1>
      <button class="btn" style="background:var(--ss-curb)" :disabled="loading" @click="refresh">
        {{ loading ? '读取中…' : '刷新（只读）' }}
      </button>
    </div>
    <p class="sub">提交瞬间仍无法在任何柱间剩余空档内安置、且不跨越挡柱的摊位（只读预估，与主图同源）</p>
    <div class="card">
      <table>
        <thead><tr><th>摊主</th><th>需求宽度</th><th>原因</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.vendor_id">
            <td>{{ r.vendor_name }}</td><td>{{ r.width_m }}</td><td>{{ r.reason }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!rows.length" class="muted">全部放下</p>
    </div>
  </div>
</template>
