<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, SEGMENT_ID } from '../api'
const rows = ref<any[]>([])
const err = ref('')
onMounted(async () => {
  try {
    const data = await api(`/allocate/state?segment_id=${SEGMENT_ID}`)
    // 与主图、运行抽屉同源：只列仍待安置、且所有柱间空档都放不下的摊主。
    rows.value = data.rejected || []
  } catch (e: any) { err.value = e?.message || String(e) }
})
</script>
<template>
  <h1>放不下</h1>
  <p class="sub">仍待安置、且在任何柱间空档都无法放下（不跨越挡柱）的摊位；与分配带同源只读</p>
  <p v-if="err" class="ss-msg ss-msg-err">{{ err }}</p>
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
</template>
