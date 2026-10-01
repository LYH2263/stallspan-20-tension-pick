<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, ApiError, SEGMENT_ID } from '../api'

interface SpanRow {
  index: number
  key: string
  start_m: number
  end_m: number
  width_m: number
  fit_count: number
  fit_vendor_ids: number[]
  rejected_count: number
  widest_rejected_m: number | null
  rejected: { vendor_id: number; vendor_name: string; width_m: number }[]
}

const router = useRouter()
const loading = ref(false)
const confirming = ref(false)
const data = ref<any>(null)
const errorMsg = ref('')
const okMsg = ref('')
const selected = ref<Set<string>>(new Set())

const spans = computed<SpanRow[]>(() => data.value?.spans || [])
const vendorName = computed(() => {
  const m = new Map<number, any>((data.value?.vendors || []).map((v: any) => [v.id, v]))
  return (id: number) => m.get(id)?.name || `#${id}`
})

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    // 纯读：每次打开/刷新都拿提交瞬间的最新数据，不缓存旧预估。
    data.value = await api(`/allocate/tension?segment_id=${SEGMENT_ID}`)
    // 空档身份可能因挡柱/落库变化；清掉已不存在的勾选。
    const keys = new Set(spans.value.map(s => s.key))
    selected.value = new Set([...selected.value].filter(k => keys.has(k)))
  } catch (e: any) {
    errorMsg.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

function toggle(key: string, ev: Event) {
  const checked = (ev.target as HTMLInputElement).checked
  const next = new Set(selected.value)
  if (checked) next.add(key)
  else next.delete(key)
  selected.value = next
}

// 零选 / 多选各自的文案，与后端 400 文案保持可区分。
const ZERO_MSG = '未选中任何柱间空档：请勾选一个柱间空档后再确认。'
const MANY_MSG = (n: number) => `只能选中一个柱间空档，请取消多余勾选后再确认（当前选中 ${n} 个）。`

async function confirmOne() {
  errorMsg.value = ''
  okMsg.value = ''
  const keys = [...selected.value]
  if (keys.length === 0) { errorMsg.value = ZERO_MSG; return }
  if (keys.length > 1) { errorMsg.value = MANY_MSG(keys.length); return }

  confirming.value = true
  try {
    // 单段提交、直接落库：没有“先发预估、再交确认”的两段令牌。
    const res = await api('/allocate/confirm', {
      method: 'POST',
      body: JSON.stringify({ segment_id: SEGMENT_ID, span_keys: keys }),
    })
    const names = res.placements.map((p: any) => p.vendor_name).join('、')
    okMsg.value = `已落库：空档 ${res.span_start_m}–${res.span_end_m} m 安置 ${res.placements.length} 摊（${names}）。`
    selected.value = new Set()
    await load()
    setTimeout(() => router.push('/map'), 600)
  } catch (e: any) {
    errorMsg.value = e instanceof ApiError ? e.message : (e?.message || String(e))
  } finally {
    confirming.value = false
  }
}

onMounted(load)
</script>
<template>
  <div class="ss-street-wrap">
    <h1>柱间紧张度</h1>
    <p class="sub">
      只读预估：按当前摊主宽度、挡柱与已入库放置实时计算 ·
      勾选粒度锁在「柱间空档」，恰好勾选一个后点确认才落库
    </p>
    <div class="ss-row-actions">
      <button class="btn" :disabled="loading" @click="load">{{ loading ? '计算中…' : '刷新紧张度' }}</button>
      <button class="btn btn-primary" :disabled="confirming || !spans.length" @click="confirmOne">
        {{ confirming ? '确认中…' : '确认所选空档并落库' }}
      </button>
    </div>
    <p v-if="okMsg" class="ss-msg ss-msg-ok">{{ okMsg }}</p>
    <p v-if="errorMsg" class="ss-msg ss-msg-err">{{ errorMsg }}</p>

    <div class="card" v-if="data">
      <table>
        <thead>
          <tr>
            <th>勾选</th><th>柱间空档 (m)</th><th>空档宽 (m)</th>
            <th>可落数</th><th>放不下数</th><th>放不下最宽摊宽 (m)</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in spans" :key="s.key">
            <td>
              <input
                type="checkbox"
                :checked="selected.has(s.key)"
                :aria-label="`勾选空档 ${s.start_m}-${s.end_m}`"
                @change="toggle(s.key, $event)"
              />
            </td>
            <td>{{ s.start_m }} – {{ s.end_m }}</td>
            <td>{{ s.width_m }}</td>
            <td>
              <span class="badge badge-ok">{{ s.fit_count }}</span>
              <span class="ss-fit-names">{{ s.fit_vendor_ids.map(vendorName).join('、') || '—' }}</span>
            </td>
            <td>
              <span class="badge" :class="s.rejected_count ? 'badge-bad' : 'badge-ok'">{{ s.rejected_count }}</span>
            </td>
            <td>
              <template v-if="s.widest_rejected_m !== null">
                <strong>{{ s.widest_rejected_m }}</strong>
                <span class="ss-fit-names">
                  （{{ s.rejected.filter(r => r.width_m === s.widest_rejected_m).map(r => r.vendor_name).join('、') }}）
                </span>
              </template>
              <span v-else class="muted">—</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!spans.length" class="muted">当前没有柱间空档（街段已占满或宽度为 0）。</p>
    </div>

    <h2 class="ss-sub-head">待安置摊主（提交瞬间按此重算）</h2>
    <div class="ss-vendor-queue">
      <div v-for="v in data?.vendors || []" :key="v.id" class="ss-vendor-chip">
        <strong>{{ v.name }}</strong>
        <span>需 {{ v.stall_width_m }} m · 优先 {{ v.priority }}</span>
      </div>
      <p v-if="data && !data.vendors.length" class="muted">摊主均已落位。</p>
    </div>
  </div>
</template>
