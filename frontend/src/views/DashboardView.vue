<script setup>
import { computed, onMounted, ref } from 'vue'
import { ArrowRight, Calendar, Medal, Reading, TrendCharts } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import StatCard from '../components/StatCard.vue'
import EmptyState from '../components/EmptyState.vue'
import { http, errorMessage, unwrap } from '../services/http'
import { formatLevel, LEVEL_META, numericLevel } from '../services/normalizers'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const loading = ref(true)
const dashboard = ref({})

const summary = computed(() => dashboard.value.summary || dashboard.value.stats || dashboard.value.overview || dashboard.value)
const attempts = computed(() => dashboard.value.recent_attempts || dashboard.value.attempts || dashboard.value.history || [])
const progress = computed(() => {
  const value = dashboard.value.progress || dashboard.value.level_progress || dashboard.value.by_level || []
  const rows = Array.isArray(value)
    ? value
    : Object.entries(value || {}).map(([level, data]) => ({ level, ...(typeof data === 'object' ? data : { average_score: data }) }))
  return rows.map((row) => {
    const level = numericLevel(row.level)
    const maximum = LEVEL_META.find((item) => item.level === level)?.maxScore || 300
    return {
      ...row,
      level,
      percentage: Number(row.accuracy ?? row.average_percentage ?? ((row.average_score || 0) / maximum) * 100),
    }
  })
})
const weakSections = computed(() => {
  const rows = dashboard.value.weak_sections || dashboard.value.weak_areas
  if (Array.isArray(rows)) return rows
  if (!dashboard.value.weak_section) return []
  return [{
    section: dashboard.value.weak_section,
    accuracy: dashboard.value.section_averages?.[dashboard.value.weak_section],
  }]
})

function scoreText(attempt) {
  const score = attempt.total_score ?? attempt.score
  const max = attempt.max_score ?? attempt.test?.max_score
  return score === null || score === undefined ? '—' : max ? `${score}/${max}` : score
}

function isFinished(attempt) {
  return ['submitted', 'completed', 'graded'].includes(String(attempt.status || '').toLowerCase()) || attempt.total_score != null || attempt.score != null
}

function attemptId(attempt) {
  return attempt.attempt_id ?? attempt.id
}

function testId(attempt) {
  return attempt.test_id ?? attempt.test?.id
}

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value))
}

onMounted(async () => {
  try {
    const { data } = await http.get('/dashboard')
    dashboard.value = unwrap(data, ['dashboard']) || {}
  } catch (error) {
    ElMessage.error(errorMessage(error, 'Your dashboard could not be loaded.'))
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="py-10 sm:py-14">
    <div class="page-shell">
      <div class="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <span class="eyebrow">Student dashboard</span>
          <h1 class="display-title mt-3 text-4xl font-bold sm:text-5xl">你好, {{ auth.displayName }}.</h1>
          <p class="mt-3 text-black/50">Small, consistent sessions turn into exam-day confidence.</p>
        </div>
        <div class="flex flex-col gap-2 sm:flex-row">
          <RouterLink to="/materials" class="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-black/10 bg-white/60 px-5 text-sm font-extrabold hover:border-jade/30 hover:text-jade">
            <el-icon><Reading /></el-icon>Study library
          </RouterLink>
          <RouterLink to="/#levels" class="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-cinnabar px-5 text-sm font-extrabold text-white shadow-lg shadow-red-900/10">
            Take a mock test <el-icon><ArrowRight /></el-icon>
          </RouterLink>
        </div>
      </div>

      <div v-if="loading" class="mt-9 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <el-skeleton v-for="n in 4" :key="n" animated class="surface p-5"><template #template><el-skeleton-item variant="h3" class="!h-24" /></template></el-skeleton>
      </div>
      <template v-else>
        <div class="mt-9 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Tests completed" :value="summary.completed_attempts ?? summary.total_attempts ?? attempts.length" hint="All mock exams" />
          <StatCard label="Average score" :value="summary.average_score ?? summary.avg_score ?? '—'" hint="Across completed tests" tone="gold" />
          <StatCard label="Personal best" :value="summary.highest_score ?? summary.best_score ?? '—'" hint="Your highest total" tone="red" />
          <StatCard label="Pass rate" :value="summary.pass_rate != null ? `${Math.round(summary.pass_rate <= 1 ? summary.pass_rate * 100 : summary.pass_rate)}%` : '—'" hint="Completed attempts" />
        </div>

        <div class="mt-8 grid gap-7 lg:grid-cols-[1.55fr_.85fr]">
          <section class="surface p-5 sm:p-7">
            <div class="flex items-center justify-between border-b border-black/[0.07] pb-5">
              <div><p class="text-xs font-black uppercase tracking-wider text-black/40">Recent activity</p><h2 class="mt-1 font-serif text-2xl font-bold">Your mock tests</h2></div>
              <el-icon class="text-cinnabar" :size="24"><Calendar /></el-icon>
            </div>
            <div v-if="attempts.length" class="divide-y divide-black/[0.07]">
              <article v-for="attempt in attempts" :key="attemptId(attempt)" class="flex flex-col gap-4 py-5 sm:flex-row sm:items-center">
                <span class="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-jade/10 font-serif text-lg font-black text-jade">{{ numericLevel(attempt.level ?? attempt.test?.level) }}</span>
                <div class="min-w-0 flex-1">
                  <h3 class="truncate font-bold">{{ attempt.title ?? attempt.test_title ?? attempt.test?.title ?? formatLevel(attempt.level ?? attempt.test?.level) }}</h3>
                  <p class="mt-1 text-xs text-black/40">{{ attempt.test_code ?? attempt.test?.test_code ?? '' }} · {{ formatDate(attempt.submitted_at ?? attempt.end_time ?? attempt.start_time) }}</p>
                </div>
                <div class="flex items-center justify-between gap-5 sm:justify-end">
                  <span><b class="block text-xl">{{ scoreText(attempt) }}</b><small class="text-[10px] font-bold uppercase tracking-wider text-black/35">score</small></span>
                  <RouterLink v-if="isFinished(attempt)" :to="`/results/${attemptId(attempt)}`" class="rounded-lg border border-black/10 px-3 py-2 text-xs font-bold hover:border-cinnabar/30 hover:text-cinnabar">Review</RouterLink>
                  <RouterLink v-else-if="testId(attempt)" :to="`/exam/${testId(attempt)}`" class="rounded-lg bg-jade px-3 py-2 text-xs font-bold text-white">Resume</RouterLink>
                </div>
              </article>
            </div>
            <EmptyState v-else class="mt-5" title="Your first score starts here" description="Complete a mock test and this space will become your progress history.">
              <RouterLink to="/#levels" class="font-bold text-cinnabar">Browse available tests →</RouterLink>
            </EmptyState>
          </section>

          <div class="space-y-7">
            <section class="surface p-5 sm:p-6">
              <div class="flex items-center justify-between"><div><p class="text-xs font-black uppercase tracking-wider text-black/40">Level progress</p><h2 class="mt-1 font-serif text-xl font-bold">Keep climbing</h2></div><el-icon class="text-gold" :size="24"><TrendCharts /></el-icon></div>
              <div v-if="progress.length" class="mt-6 space-y-5">
                <div v-for="row in progress" :key="row.level" class="text-sm">
                  <div class="mb-2 flex justify-between"><b>{{ formatLevel(row.level) }}</b><span class="text-black/45">{{ Math.round(row.percentage) }}%</span></div>
                  <div class="h-2 overflow-hidden rounded-full bg-black/[0.07]"><div class="h-full rounded-full bg-jade" :style="{ width: `${Math.min(100, row.percentage)}%` }" /></div>
                </div>
              </div>
              <p v-else class="mt-6 text-sm leading-6 text-black/45">Complete tests at any level to reveal your progress trend.</p>
            </section>

            <section class="surface !bg-[#17211e] p-5 text-white sm:p-6">
              <div class="flex items-center gap-3"><span class="grid h-10 w-10 place-items-center rounded-xl bg-gold/15 text-gold"><el-icon :size="20"><Medal /></el-icon></span><div><p class="text-[10px] font-black uppercase tracking-wider text-white/35">Study focus</p><h2 class="font-serif text-xl font-bold">Weak sections</h2></div></div>
              <div v-if="weakSections.length" class="mt-5 flex flex-wrap gap-2"><span v-for="item in weakSections" :key="item.section ?? item" class="rounded-lg bg-white/10 px-3 py-2 text-xs font-bold">{{ item.section ?? item }}<template v-if="item.accuracy != null"> · {{ Math.round(item.accuracy) }}%</template></span></div>
              <p v-else class="mt-5 text-sm leading-6 text-white/45">After a few attempts, we’ll surface the sections where focused review can make the biggest difference.</p>
            </section>
          </div>
        </div>
      </template>
    </div>
  </section>
</template>
