<script setup>
import { computed, onMounted, ref } from 'vue'
import { ArrowRight, Calendar, Check, Headset, Medal, Reading, TrendCharts } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import EmptyState from '../components/EmptyState.vue'
import ScoreTrendChart from '../components/ScoreTrendChart.vue'
import StatCard from '../components/StatCard.vue'
import { errorMessage, http, unwrap } from '../services/http'
import { formatLevel, LEVEL_META, numericLevel } from '../services/normalizers'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const loading = ref(true)
const failed = ref(false)
const dashboard = ref({})

const summary = computed(() => dashboard.value.summary || dashboard.value.stats || dashboard.value.overview || dashboard.value)
const attempts = computed(() => dashboard.value.recent_attempts || dashboard.value.attempts || dashboard.value.history || [])

function clamp(value, minimum = 0, maximum = 100) {
  return Math.min(maximum, Math.max(minimum, Number(value) || 0))
}

function percentageForAttempt(attempt) {
  const score = Number(attempt.total_score ?? attempt.score)
  const maximum = Number(attempt.max_score ?? attempt.test?.max_score)
  return maximum > 0 ? clamp((score / maximum) * 100) : 0
}

const readiness = computed(() => clamp(
  summary.value.average_percentage
  ?? summary.value.accuracy
  ?? (attempts.value.length
    ? attempts.value.reduce((sum, attempt) => sum + percentageForAttempt(attempt), 0) / attempts.value.length
    : 0),
))

const progress = computed(() => {
  const value = dashboard.value.progress || dashboard.value.level_progress || dashboard.value.by_level || []
  const rows = Array.isArray(value)
    ? value
    : Object.entries(value || {}).map(([level, data]) => ({
      level,
      ...(typeof data === 'object' ? data : { average_score: data }),
    }))
  return rows.map((row) => {
    const level = numericLevel(row.level)
    const maximum = LEVEL_META.find((item) => item.level === level)?.maxScore || 300
    return {
      ...row,
      level,
      percentage: clamp(row.accuracy ?? row.average_percentage ?? ((row.average_score || 0) / maximum) * 100),
    }
  })
})

const sectionBreakdown = computed(() => {
  const direct = dashboard.value.section_averages || dashboard.value.skills || {}
  if (Array.isArray(direct)) {
    return direct.map((item) => ({
      label: item.section || item.label || item.name,
      value: clamp(item.accuracy ?? item.percentage ?? item.value),
    })).filter((item) => item.label)
  }
  return Object.entries(direct || {}).map(([label, value]) => ({ label, value: clamp(value) }))
})

const weakestSection = computed(() => {
  if (sectionBreakdown.value.length) {
    return [...sectionBreakdown.value].sort((left, right) => left.value - right.value)[0]
  }
  const fallback = dashboard.value.weak_section
  return fallback ? { label: fallback, value: null } : null
})

const scoreTrend = computed(() => attempts.value
  .filter((attempt) => (attempt.total_score ?? attempt.score) != null)
  .slice(0, 7)
  .reverse()
  .map((attempt) => ({
    label: attempt.test_code || attempt.test?.test_code || `HSK${numericLevel(attempt.level ?? attempt.test?.level)}`,
    value: percentageForAttempt(attempt),
  })))

const roadmap = computed(() => {
  const byLevel = new Map(progress.value.map((row) => [row.level, row]))
  const attemptedLevels = [...byLevel.keys()].filter(Boolean)
  const currentLevel = attemptedLevels.length ? Math.max(...attemptedLevels) : 1
  return Array.from({ length: 6 }, (_, index) => {
    const level = index + 1
    const row = byLevel.get(level)
    const percentage = row?.percentage || 0
    return {
      level,
      percentage,
      attempts: Number(row?.attempts || 0),
      state: percentage >= 60 ? 'ready' : level === currentLevel ? 'current' : row ? 'started' : 'locked',
    }
  })
})

const recommendation = computed(() => {
  if (!attempts.value.length) {
    return {
      eyebrow: 'Recommended next step',
      title: 'Take a diagnostic mock test',
      description: 'Your first completed test establishes a baseline and unlocks personal skill recommendations.',
      to: '/#levels',
      action: 'Choose a level',
    }
  }
  if (weakestSection.value) {
    const label = String(weakestSection.value.label)
    const listening = label.toLowerCase().includes('listen')
    return {
      eyebrow: 'Focus area',
      title: `Strengthen ${label}`,
      description: listening
        ? 'Use lesson audio for a short focused session, then retake a listening section under timed conditions.'
        : 'Review the related course material before your next timed mock exam.',
      to: '/materials',
      action: listening ? 'Open lesson audio' : 'Review study material',
    }
  }
  return {
    eyebrow: 'Keep momentum',
    title: 'Complete another timed test',
    description: 'A second result will reveal useful trends and make your recommendations more precise.',
    to: '/#levels',
    action: 'Continue practice',
  }
})

function scoreText(attempt) {
  const score = attempt.total_score ?? attempt.score
  const max = attempt.max_score ?? attempt.test?.max_score
  return score == null ? '—' : max ? `${score}/${max}` : score
}

function isFinished(attempt) {
  return ['submitted', 'completed', 'graded'].includes(String(attempt.status || '').toLowerCase())
    || attempt.total_score != null
    || attempt.score != null
}

function attemptId(attempt) {
  return attempt.attempt_id ?? attempt.id
}

function testId(attempt) {
  return attempt.test_id ?? attempt.test?.id
}

function formatDate(value) {
  if (!value) return 'Date unavailable'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Date unavailable'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date)
}

async function loadDashboard() {
  loading.value = true
  failed.value = false
  try {
    const { data } = await http.get('/dashboard')
    dashboard.value = unwrap(data, ['dashboard']) || {}
  } catch (error) {
    failed.value = true
    ElMessage.error(errorMessage(error, 'Your dashboard could not be loaded.'))
  } finally {
    loading.value = false
  }
}

onMounted(loadDashboard)
</script>

<template>
  <section class="dashboard-page pb-20 pt-8 sm:pt-12">
    <div class="page-shell">
      <header class="dashboard-hero surface relative overflow-hidden p-6 sm:p-8 lg:p-10">
        <div class="hero-orb hero-orb-one" />
        <div class="hero-orb hero-orb-two" />
        <div class="relative grid items-end gap-8 lg:grid-cols-[1fr_auto]">
          <div class="max-w-3xl">
            <span class="eyebrow">Student dashboard</span>
            <h1 class="display-title mt-4 text-4xl font-bold leading-tight sm:text-5xl">
              Welcome back, <span class="text-cinnabar">{{ auth.displayName }}</span>
            </h1>
            <p class="mt-4 max-w-xl text-sm leading-7 text-black/55 sm:text-base">
              Build exam confidence one focused session at a time. Your results, study priorities, and next milestone are all here.
            </p>
          </div>
          <div class="flex flex-col gap-3 sm:flex-row lg:flex-col xl:flex-row">
            <RouterLink to="/materials" class="secondary-action"><el-icon><Reading /></el-icon>Study library</RouterLink>
            <RouterLink to="/#levels" class="primary-action">Take a mock test <el-icon><ArrowRight /></el-icon></RouterLink>
          </div>
        </div>
      </header>

      <div v-if="loading" class="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Loading dashboard">
        <el-skeleton v-for="number in 4" :key="number" animated class="surface p-5"><template #template><el-skeleton-item variant="h3" class="!h-24" /></template></el-skeleton>
      </div>

      <EmptyState v-else-if="failed" class="mt-6" title="Your dashboard is temporarily unavailable" description="Your results are safe. Check your connection and try loading them again.">
        <button type="button" class="primary-action mx-auto" @click="loadDashboard">Try again</button>
      </EmptyState>

      <template v-else>
        <section class="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Performance summary">
          <StatCard label="Tests completed" :value="summary.completed_attempts ?? summary.total_attempts ?? attempts.length" hint="Submitted mock exams" />
          <StatCard label="Average score" :value="summary.average_score ?? summary.avg_score ?? '—'" hint="Across completed tests" tone="gold" />
          <StatCard label="Personal best" :value="summary.highest_score ?? summary.best_score ?? '—'" hint="Your highest total" tone="red" />
          <StatCard label="Pass rate" :value="summary.pass_rate != null ? `${Math.round(summary.pass_rate <= 1 ? summary.pass_rate * 100 : summary.pass_rate)}%` : '—'" hint="Completed attempts" />
        </section>

        <div class="mt-6 grid gap-6 xl:grid-cols-[1.55fr_.8fr]">
          <section class="surface overflow-hidden p-5 sm:p-7" aria-labelledby="score-trend-title">
            <div class="flex flex-col gap-3 border-b border-black/[0.07] pb-5 sm:flex-row sm:items-center sm:justify-between">
              <div><p class="section-kicker">Performance trend</p><h2 id="score-trend-title" class="mt-1 font-serif text-2xl font-bold">Score consistency</h2></div>
              <span class="inline-flex items-center gap-2 text-xs font-bold text-black/45"><el-icon class="text-jade"><TrendCharts /></el-icon>Percentage of total score</span>
            </div>
            <ScoreTrendChart v-if="scoreTrend.length" class="mt-5" :points="scoreTrend" />
            <div v-else class="grid min-h-52 place-items-center text-center"><div><p class="font-bold">Your trend starts after test one</p><p class="mt-2 text-sm text-black/45">Complete a mock test to plot your first score.</p></div></div>
          </section>

          <section class="surface flex flex-col p-6 sm:p-7" aria-labelledby="readiness-title">
            <div class="flex items-start justify-between gap-4"><div><p class="section-kicker">Overall readiness</p><h2 id="readiness-title" class="mt-1 font-serif text-2xl font-bold">Exam confidence</h2></div><el-icon class="text-gold" :size="25"><Medal /></el-icon></div>
            <div class="mx-auto my-7 grid h-40 w-40 place-items-center rounded-full p-3" :style="{ background: `conic-gradient(#247461 ${readiness * 3.6}deg, rgba(36,116,97,.1) 0deg)` }">
              <div class="grid h-full w-full place-items-center rounded-full bg-white text-center shadow-inner"><span><b class="block font-serif text-4xl">{{ Math.round(readiness) }}%</b><small class="font-bold uppercase tracking-wider text-black/35">average</small></span></div>
            </div>
            <p class="mt-auto text-center text-sm leading-6 text-black/50">{{ readiness >= 75 ? 'Strong work. Keep your timing and accuracy consistent.' : readiness >= 60 ? 'You are building a passing foundation. Focus on the weakest section next.' : 'Keep practicing—each completed test makes this guidance more useful.' }}</p>
          </section>
        </div>

        <div class="mt-6 grid gap-6 lg:grid-cols-[.92fr_1.08fr]">
          <section class="surface p-5 sm:p-7" aria-labelledby="skills-title">
            <div class="flex items-center justify-between"><div><p class="section-kicker">Skill analysis</p><h2 id="skills-title" class="mt-1 font-serif text-2xl font-bold">Section accuracy</h2></div><el-icon class="text-cinnabar" :size="23"><Headset /></el-icon></div>
            <div v-if="sectionBreakdown.length" class="mt-7 space-y-5">
              <div v-for="section in sectionBreakdown" :key="section.label">
                <div class="mb-2 flex items-center justify-between gap-4 text-sm"><b class="capitalize">{{ section.label }}</b><span class="font-mono text-xs font-bold text-black/45">{{ Math.round(section.value) }}%</span></div>
                <div class="h-2.5 overflow-hidden rounded-full bg-black/[0.06]" role="progressbar" :aria-label="`${section.label} accuracy`" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="Math.round(section.value)">
                  <div class="metric-fill h-full rounded-full" :class="section.value < 60 ? 'bg-cinnabar' : 'bg-jade'" :style="{ '--metric-width': `${section.value}%` }" />
                </div>
              </div>
            </div>
            <p v-else class="mt-7 rounded-2xl bg-black/[0.035] p-5 text-sm leading-6 text-black/48">Section insights appear after a completed mock exam.</p>
          </section>

          <section class="relative overflow-hidden rounded-[1.4rem] bg-ink p-6 text-white shadow-soft sm:p-8" aria-labelledby="recommendation-title">
            <div class="absolute -right-16 -top-16 h-48 w-48 rounded-full bg-cinnabar/25 blur-3xl" />
            <div class="relative">
              <span class="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-white/10 text-gold"><el-icon :size="22"><TrendCharts /></el-icon></span>
              <p class="mt-6 text-[10px] font-black uppercase tracking-[.18em] text-white/40">{{ recommendation.eyebrow }}</p>
              <h2 id="recommendation-title" class="mt-2 font-serif text-3xl font-bold">{{ recommendation.title }}</h2>
              <p class="mt-4 max-w-xl text-sm leading-7 text-white/60">{{ recommendation.description }}</p>
              <RouterLink :to="recommendation.to" class="mt-7 inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-white px-5 text-sm font-extrabold text-ink transition hover:-translate-y-0.5 hover:bg-gold">{{ recommendation.action }} <el-icon><ArrowRight /></el-icon></RouterLink>
            </div>
          </section>
        </div>

        <section class="surface mt-6 p-5 sm:p-7" aria-labelledby="roadmap-title">
          <div class="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between"><div><p class="section-kicker">HSK roadmap</p><h2 id="roadmap-title" class="mt-1 font-serif text-2xl font-bold">Your path from HSK 1 to 6</h2></div><p class="text-xs font-bold text-black/40">60%+ average marks a level as exam-ready</p></div>
          <div class="mt-7 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <article v-for="item in roadmap" :key="item.level" class="roadmap-step" :class="`is-${item.state}`">
              <div class="flex items-center justify-between"><span class="roadmap-number">{{ item.level }}</span><el-icon v-if="item.state === 'ready'" class="text-jade"><Check /></el-icon></div>
              <b class="mt-4 block">HSK {{ item.level }}</b><span class="mt-1 block text-xs text-black/42">{{ item.attempts ? `${Math.round(item.percentage)}% average` : 'Not started' }}</span>
            </article>
          </div>
        </section>

        <section class="surface mt-6 overflow-hidden" aria-labelledby="history-title">
          <div class="flex items-center justify-between border-b border-black/[0.07] px-5 py-5 sm:px-7"><div><p class="section-kicker">Recent activity</p><h2 id="history-title" class="mt-1 font-serif text-2xl font-bold">Mock-test history</h2></div><el-icon class="text-cinnabar" :size="23"><Calendar /></el-icon></div>
          <div v-if="attempts.length" class="divide-y divide-black/[0.07] px-5 sm:px-7">
            <article v-for="attempt in attempts" :key="attemptId(attempt)" class="grid gap-4 py-5 sm:grid-cols-[auto_1fr_auto] sm:items-center">
              <span class="grid h-12 w-12 place-items-center rounded-2xl bg-jade/10 font-serif text-lg font-black text-jade">{{ numericLevel(attempt.level ?? attempt.test?.level) }}</span>
              <div class="min-w-0"><h3 class="truncate font-bold">{{ attempt.title ?? attempt.test_title ?? attempt.test?.title ?? formatLevel(attempt.level ?? attempt.test?.level) }}</h3><p class="mt-1 text-xs text-black/40">{{ attempt.test_code ?? attempt.test?.test_code ?? 'Mock test' }} · {{ formatDate(attempt.submitted_at ?? attempt.end_time ?? attempt.start_time) }}</p></div>
              <div class="flex items-center justify-between gap-5 sm:justify-end"><span><b class="block text-xl">{{ scoreText(attempt) }}</b><small class="text-[10px] font-bold uppercase tracking-wider text-black/35">score</small></span><RouterLink v-if="isFinished(attempt)" :to="`/results/${attemptId(attempt)}`" class="compact-action">Review</RouterLink><RouterLink v-else-if="testId(attempt)" :to="`/exam/${testId(attempt)}`" class="compact-action is-primary">Resume</RouterLink></div>
            </article>
          </div>
          <EmptyState v-else class="m-5 sm:m-7" title="Your first score starts here" description="Complete a mock test and this space will become your progress history."><RouterLink to="/#levels" class="font-bold text-cinnabar">Browse available tests →</RouterLink></EmptyState>
        </section>
      </template>
    </div>
  </section>
</template>

<style scoped>
.dashboard-page { background: radial-gradient(circle at 12% 8%, rgba(229,83,61,.055), transparent 24rem); }
.dashboard-hero { background: linear-gradient(135deg, rgba(255,255,255,.94), rgba(248,244,235,.8)); }
.hero-orb { position: absolute; border-radius: 999px; filter: blur(45px); pointer-events: none; }
.hero-orb-one { width: 15rem; height: 15rem; right: 8%; top: -7rem; background: rgba(36,116,97,.13); }
.hero-orb-two { width: 10rem; height: 10rem; right: 28%; bottom: -7rem; background: rgba(217,163,60,.12); }
.primary-action, .secondary-action { display: inline-flex; min-height: 2.8rem; align-items: center; justify-content: center; gap: .5rem; border-radius: .85rem; padding: 0 1.15rem; font-size: .82rem; font-weight: 800; transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease; }
.primary-action { background: #e5533d; color: white; box-shadow: 0 12px 28px rgba(177,54,41,.18); }
.secondary-action { border: 1px solid rgba(22,35,31,.11); background: rgba(255,255,255,.75); color: #16231f; }
.primary-action:hover, .secondary-action:hover { transform: translateY(-2px); }
.section-kicker { font-size: .68rem; font-weight: 900; letter-spacing: .15em; text-transform: uppercase; color: rgba(22,35,31,.4); }
.metric-fill { width: var(--metric-width); animation: grow-metric .8s cubic-bezier(.2,.8,.2,1) both; transform-origin: left; }
.roadmap-step { min-height: 8.5rem; border: 1px solid rgba(22,35,31,.08); border-radius: 1rem; background: rgba(255,255,255,.55); padding: 1rem; transition: transform .18s ease, border-color .18s ease; }
.roadmap-step:hover { transform: translateY(-2px); }
.roadmap-step.is-current { border-color: rgba(229,83,61,.35); background: rgba(229,83,61,.055); }
.roadmap-step.is-ready { border-color: rgba(36,116,97,.25); background: rgba(36,116,97,.055); }
.roadmap-step.is-locked { opacity: .62; }
.roadmap-number { display: grid; width: 2rem; height: 2rem; place-items: center; border-radius: .7rem; background: rgba(22,35,31,.06); font-family: ui-serif, Georgia, serif; font-weight: 900; }
.is-current .roadmap-number { background: #e5533d; color: white; }
.is-ready .roadmap-number { background: #247461; color: white; }
.compact-action { display: inline-flex; min-height: 2.4rem; align-items: center; border: 1px solid rgba(22,35,31,.11); border-radius: .7rem; padding: 0 .9rem; font-size: .72rem; font-weight: 800; }
.compact-action:hover { border-color: rgba(229,83,61,.4); color: #c44232; }
.compact-action.is-primary { border-color: transparent; background: #247461; color: white; }
@keyframes grow-metric { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@media (prefers-reduced-motion: reduce) { .metric-fill { animation: none; } .primary-action, .secondary-action, .roadmap-step { transition: none; } }
</style>
