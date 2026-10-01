<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

interface Gap {
  index: number
  start_m: number
  end_m: number
  width_m: number
  fit_count: number
  cant_fit_count: number
  widest_cant_fit_m: number | null
}

const data = ref<any>(null)
const selected = ref<number | null>(null) // 勾选粒度锁在柱间空档，至多一个
const loading = ref(false)
const confirming = ref(false)
const banner = ref<{ kind: 'ok' | 'err'; text: string } | null>(null)

async function refresh() {
  // 纯只读：连刷任意次都不增行
  loading.value = true
  try {
    data.value = await api('/allocate/tension?segment_id=1')
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

const gaps = computed<Gap[]>(() => data.value?.gaps ?? [])
const selectedGap = computed(() => gaps.value.find(g => g.index === selected.value) || null)

async function confirm_() {
  // 点确认直接落库：只有这一次 POST，服务端在提交瞬间重算，无"先发再交"两段令牌
  if (selected.value === null) {
    // 零选：直接让服务端拦下并回差异化文案（前端不伪造结果）
    banner.value = null
  }
  confirming.value = true
  try {
    const body = await api('/allocate/confirm', {
      method: 'POST',
      body: JSON.stringify({ segment_id: 1, gap_indexes: selected.value === null ? [] : [selected.value] }),
    })
    const p = body.placements[body.placements.length - 1]
    banner.value = {
      kind: 'ok',
      text: `已落库：${p.vendor_name} 落于 ${p.start_m}–${p.end_m} m（运行 #${body.run_id}）。主图/放不下/运行抽屉已按同一结果对齐。`,
    }
    selected.value = null
    await refresh()
  } catch (e: any) {
    // 400 零选/多选、409 拒空跑/空档失效：文案由服务端区分，且都不增行
    banner.value = { kind: 'err', text: String(e.message || e) }
  } finally {
    confirming.value = false
  }
}
</script>
<template>
  <div>
    <h1>柱间紧张度</h1>
    <p class="sub">
      只读预估：挡柱切出的每个柱间空档，给出可落数 / 放不下数 / 放不下最宽摊宽。
      打开此页不产生任何放置；确认时按提交瞬间的摊主与挡柱重算，不采用本页旧预估。
    </p>

    <div v-if="banner" :class="['card', banner.kind === 'ok' ? 'ss-note-ok' : 'ss-note-err']"
         style="margin-bottom:0.75rem">
      <strong>{{ banner.kind === 'ok' ? '✔ 确认成功' : '✖ 确认被拦下（未增行）' }}</strong>
      <div style="white-space:pre-wrap">{{ banner.text }}</div>
    </div>

    <div class="card">
      <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem">
        <strong>东街段 · 柱间空档</strong>
        <button class="btn" style="background:var(--ss-curb)" :disabled="loading" @click="refresh">
          {{ loading ? '读取中…' : '刷新（只读，不增行）' }}
        </button>
        <span class="muted" style="font-size:0.78rem">勾选粒度＝单个柱间空档，一次只能选一个</span>
      </div>
      <table>
        <thead>
          <tr>
            <th style="width:48px">勾选</th>
            <th>柱间空档</th><th>空档宽(m)</th>
            <th>可落数</th><th>放不下数</th><th>放不下最宽摊宽(m)</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="g in gaps" :key="g.index"
              :class="{ 'ss-row-pick': selected === g.index }">
            <td>
              <input type="radio" name="gap" :value="g.index" v-model.number="selected"
                     :aria-label="`勾选空档 ${g.index + 1}`" />
            </td>
            <td>#{{ g.index + 1 }} · {{ g.start_m }}–{{ g.end_m }} m</td>
            <td>{{ g.width_m }}</td>
            <td><span class="badge badge-ok">{{ g.fit_count }}</span></td>
            <td><span :class="['badge', g.cant_fit_count ? 'badge-bad' : 'badge-ok']">{{ g.cant_fit_count }}</span></td>
            <td>{{ g.widest_cant_fit_m ?? '—' }}</td>
          </tr>
          <tr v-if="!gaps.length"><td colspan="6" class="muted">暂无柱间空档</td></tr>
        </tbody>
      </table>

      <div style="display:flex;align-items:center;gap:0.75rem;margin-top:0.75rem">
        <button class="btn" :disabled="confirming" @click="confirm_">
          {{ confirming ? '提交中…' : '确认落库（直接提交）' }}
        </button>
        <span class="muted" style="font-size:0.8rem">
          <template v-if="selectedGap">
            已选空档 #{{ selectedGap.index + 1 }}（{{ selectedGap.start_m }}–{{ selectedGap.end_m }} m）；
            提交瞬间若该空档放不下任何摊主，将被拒绝且不增行。
          </template>
          <template v-else>尚未勾选空档 —— 直接点确认会被服务端按"未选中"拦下，不增行。</template>
        </span>
      </div>
    </div>

    <p class="muted" style="font-size:0.78rem">
      改摊宽请去「摊主」页保存；回本页数字按新宽重算，确认也跟新宽，不吃旧缓存。
    </p>
  </div>
</template>
