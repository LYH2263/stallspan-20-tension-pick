<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '../api'
const rows = ref<any[]>([])
const drafts = ref<Record<number, string>>({})
const saving = ref<number | null>(null)
const msg = ref<{ kind: 'ok' | 'err'; text: string } | null>(null)

async function load() { rows.value = await api('/vendors') }
onMounted(load)

async function save(id: number) {
  const w = parseFloat(drafts.value[id])
  if (!Number.isFinite(w) || w <= 0) {
    msg.value = { kind: 'err', text: '摊位宽度必须为正数' }
    return
  }
  saving.value = id
  msg.value = null
  try {
    const row = await api(`/vendors/${id}`, { method: 'PATCH', body: JSON.stringify({ stall_width_m: w }) })
    const i = rows.value.findIndex(r => r.id === id)
    if (i >= 0) rows.value[i] = row
    msg.value = { kind: 'ok', text: `已按新宽 ${w} m 保存；下一次紧张度与确认都按提交瞬间的新宽重算，不吃旧预估。` }
  } catch (e) {
    msg.value = { kind: 'err', text: (e as ApiError).message }
  } finally {
    saving.value = null
  }
}
</script>
<template>
  <h1>摊主队列</h1>
  <p class="sub">底部排队条 · 宽度与优先级；改宽后确认落库跟新宽</p>
  <div v-if="msg" :class="['card', msg.kind === 'ok' ? 'ss-note-ok' : 'ss-note-err']" style="margin-bottom:0.75rem">
    {{ msg.text }}
  </div>
  <div class="ss-vendor-queue" style="border-top:none; background:transparent; margin:0; padding:0.5rem 0 1rem">
    <div v-for="r in rows" :key="r.id ?? JSON.stringify(r)" class="ss-vendor-chip">
      <strong>{{ r.name }}</strong>
      <span>需 {{ r.stall_width_m }} m · 优先 {{ r.priority }}</span>
    </div>
  </div>
  <div class="card">
    <table>
      <thead><tr><th>摊主</th><th>宽度(m)</th><th>优先级</th><th>改摊宽</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)">
          <td>{{ r.name }}</td><td>{{ r.stall_width_m }}</td><td>{{ r.priority }}</td>
          <td style="display:flex;gap:0.4rem;align-items:center">
            <input v-model="drafts[r.id]" type="number" step="0.1" min="0.1"
                   :placeholder="String(r.stall_width_m)"
                   style="width:90px;padding:0.25rem 0.4rem" />
            <button class="btn" style="padding:0.25rem 0.6rem" :disabled="saving === r.id" @click="save(r.id)">
              {{ saving === r.id ? '保存中…' : '保存新宽' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
