<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowRight,
  Check,
  Clock,
  Document,
  Headset,
  Reading,
  TrendCharts,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import TestCard from '../components/TestCard.vue'
import EmptyState from '../components/EmptyState.vue'
import { http, errorMessage } from '../services/http'
import { LEVEL_META, normalizeTests } from '../services/normalizers'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const tests = ref([])
const loading = ref(true)
const visibleLimit = ref(6)

const requestedLevel = Number(route.query.level || 0)
const selectedLevel = ref(LEVEL_META.some((item) => item.level === requestedLevel) ? requestedLevel : 0)

const publishedTests = computed(() => tests.value.filter((test) => !['draft', 'archived'].includes(test.status)))
const filteredTests = computed(() => (
  selectedLevel.value
    ? publishedTests.value.filter((test) => test.level === selectedLevel.value)
    : publishedTests.value
))
const visibleTests = computed(() => filteredTests.value.slice(0, visibleLimit.value))
const availableLevels = computed(() => new Set(publishedTests.value.map((test) => test.level)).size)
const currentYear = new Date().getFullYear()

function countForLevel(level) {
  return publishedTests.value.filter((test) => test.level === level).length
}

function scrollToTests() {
  requestAnimationFrame(() => {
    document.querySelector('#available-tests')?.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      block: 'start',
    })
  })
}

function chooseLevel(level) {
  selectedLevel.value = selectedLevel.value === level ? 0 : level
  visibleLimit.value = 6
  router.replace({ query: selectedLevel.value ? { level: selectedLevel.value } : {} })
  scrollToTests()
}

function clearLevel() {
  selectedLevel.value = 0
  visibleLimit.value = 6
  router.replace({ query: {} })
}

function startTest(test) {
  const destination = `/exam/${test.id}`
  if (!auth.isAuthenticated) {
    router.push({ name: 'login', query: { redirect: destination } })
    return
  }
  router.push(destination)
}

onMounted(async () => {
  try {
    const { data } = await http.get('/tests')
    tests.value = normalizeTests(data)
  } catch (error) {
    ElMessage.error(errorMessage(error, 'Available mock tests could not be loaded.'))
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="home-view">
    <section class="hero soft-grid" aria-labelledby="home-title">
      <div class="hero-orb hero-orb--one" aria-hidden="true" />
      <div class="hero-orb hero-orb--two" aria-hidden="true" />

      <div class="page-shell hero-grid">
        <div class="hero-copy">
          <div class="availability-badge">
            <span class="status-pulse" aria-hidden="true" />
            Exam-ready practice for HSK 1–6
          </div>
          <p class="eyebrow mt-6">Practise with purpose</p>
          <h1 id="home-title" class="display-title mt-5 text-[2.75rem] font-bold leading-[1.03] sm:text-6xl lg:text-[4.55rem]">
            Build the calm to do your <span class="gradient-text">best work.</span>
          </h1>
          <p class="section-copy mt-6 text-base sm:text-lg">
            Train with timed HSK papers, focused study materials, and clear score feedback—all in one distraction-free workspace.
          </p>

          <div class="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
            <a href="#levels" class="btn-primary min-h-12 px-6">
              Choose your HSK level <el-icon><ArrowRight /></el-icon>
            </a>
            <RouterLink to="/materials" class="btn-secondary min-h-12 px-6">
              <el-icon><Reading /></el-icon> Explore study library
            </RouterLink>
            <RouterLink
              :to="auth.isAuthenticated ? (auth.isAdmin ? '/admin' : '/dashboard') : '/register'"
              class="btn-quiet min-h-12 px-6"
            >
              {{ auth.isAuthenticated ? 'Open dashboard' : 'Create free account' }}
            </RouterLink>
          </div>

          <ul class="mt-8 flex flex-wrap gap-x-6 gap-y-3 text-xs font-bold text-black/50" aria-label="Platform benefits">
            <li class="flex items-center gap-2"><span class="benefit-check"><el-icon><Check /></el-icon></span>Answers auto-save</li>
            <li class="flex items-center gap-2"><span class="benefit-check"><el-icon><Check /></el-icon></span>Resume safely</li>
            <li class="flex items-center gap-2"><span class="benefit-check"><el-icon><Check /></el-icon></span>Review every score</li>
          </ul>
        </div>

        <div class="exam-stage" aria-label="Example of the computer-based exam interface">
          <div class="exam-glow" aria-hidden="true" />
          <div class="exam-preview">
            <div class="exam-preview__topbar">
              <div class="flex min-w-0 items-center gap-3">
                <span class="grid h-9 w-9 flex-none place-items-center rounded-xl bg-cinnabar font-serif font-bold">4</span>
                <span class="min-w-0">
                  <small class="block truncate text-[9px] font-extrabold uppercase tracking-[0.18em] text-white/35">HSK practice exam</small>
                  <strong class="mt-1 block truncate text-sm">Listening · Part 1</strong>
                </span>
              </div>
              <span class="timer-chip"><el-icon><Clock /></el-icon>32:18</span>
            </div>

            <div class="exam-progress" role="progressbar" aria-label="Exam progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="48">
              <span style="width: 48%" />
            </div>

            <div class="exam-preview__body">
              <div class="question-map" aria-hidden="true">
                <span
                  v-for="n in 12"
                  :key="n"
                  :class="{ answered: n < 6, current: n === 6 }"
                >{{ n }}</span>
              </div>

              <div class="min-w-0">
                <div class="flex items-center justify-between gap-3">
                  <p class="text-[9px] font-black uppercase tracking-[0.18em] text-gold">Question 6 of 40</p>
                  <span class="inline-flex items-center gap-1.5 text-[9px] font-bold text-white/40">
                    <el-icon><Headset /></el-icon> Audio ready
                  </span>
                </div>
                <p class="mt-5 font-serif text-lg font-semibold leading-8 sm:text-xl">男的为什么要去图书馆？</p>
                <div class="mt-5 space-y-2.5">
                  <span
                    v-for="(answer, index) in ['借一本书', '见一位朋友', '准备考试']"
                    :key="answer"
                    class="answer-preview"
                    :class="{ selected: index === 2 }"
                  >
                    <b>{{ String.fromCharCode(65 + index) }}</b>{{ answer }}
                    <el-icon v-if="index === 2" class="ml-auto"><Check /></el-icon>
                  </span>
                </div>
              </div>
            </div>

            <div class="exam-preview__footer">
              <span class="inline-flex items-center gap-2"><i class="status-pulse" /> Answer saved</span>
              <span class="rounded-lg bg-white/10 px-4 py-2 text-white">Next →</span>
            </div>
          </div>

          <div class="score-float">
            <span class="grid h-10 w-10 place-items-center rounded-xl bg-jade/10 text-jade">
              <el-icon :size="20"><TrendCharts /></el-icon>
            </span>
            <span><b class="block text-lg leading-none">6 levels</b><small>one clear roadmap</small></span>
          </div>
        </div>
      </div>

      <div class="page-shell pb-8 sm:pb-10">
        <dl class="trust-strip">
          <div><dt>{{ loading ? '—' : publishedTests.length }}</dt><dd>Published mock papers</dd></div>
          <div><dt>{{ loading ? '—' : availableLevels || 6 }}</dt><dd>HSK levels represented</dd></div>
          <div><dt>24/7</dt><dd>Self-paced preparation</dd></div>
          <div><dt>100%</dt><dd>Server-validated scores</dd></div>
        </dl>
      </div>
    </section>

    <section id="levels" class="scroll-mt-24 py-16 sm:py-24" aria-labelledby="level-heading">
      <div class="page-shell">
        <div class="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div class="max-w-2xl">
            <p class="eyebrow">Six levels, one clear path</p>
            <h2 id="level-heading" class="display-title mt-4 text-4xl font-bold sm:text-5xl">Meet your next challenge.</h2>
            <p class="section-copy mt-4">Pick your current level to see the complete, timed papers ready for practice.</p>
          </div>
          <RouterLink to="/materials" class="group inline-flex items-center gap-2 self-start text-sm font-extrabold text-jade lg:self-auto">
            Not test-ready yet? Study first
            <el-icon class="transition-transform group-hover:translate-x-1"><ArrowRight /></el-icon>
          </RouterLink>
        </div>

        <div class="level-grid mt-9" role="group" aria-label="Filter tests by HSK level">
          <button
            v-for="level in LEVEL_META"
            :key="level.level"
            type="button"
            class="level-card"
            :class="{ 'level-card--selected': selectedLevel === level.level }"
            :aria-pressed="selectedLevel === level.level"
            aria-controls="available-tests"
            @click="chooseLevel(level.level)"
          >
            <span class="level-card__number">{{ level.level }}</span>
            <span class="min-w-0">
              <strong class="block text-sm">HSK {{ level.level }}</strong>
              <small>{{ level.duration }} min · {{ level.questions }} questions</small>
            </span>
            <span class="level-card__count">{{ countForLevel(level.level) }}</span>
          </button>
        </div>

        <div id="available-tests" class="mt-14 scroll-mt-28 sm:mt-16">
          <div class="flex flex-col gap-4 border-b border-black/10 pb-5 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p class="text-[10px] font-extrabold uppercase tracking-[0.15em] text-cinnabar">Practice catalog</p>
              <h2 class="mt-2 font-serif text-2xl font-bold sm:text-3xl">
                {{ selectedLevel ? `HSK ${selectedLevel} mock tests` : 'All available mock tests' }}
              </h2>
              <p class="mt-1.5 text-sm text-black/45" aria-live="polite">
                <span v-if="loading">Loading published papers…</span>
                <span v-else>{{ filteredTests.length }} {{ filteredTests.length === 1 ? 'paper' : 'papers' }} ready to take</span>
              </p>
            </div>
            <button v-if="selectedLevel" type="button" class="btn-quiet !min-h-10 self-start !px-4 sm:self-auto" @click="clearLevel">
              Show every level
            </button>
          </div>

          <div v-if="loading" class="mt-7 grid gap-5 md:grid-cols-2 xl:grid-cols-3" role="status" aria-label="Loading mock tests">
            <article v-for="n in 3" :key="n" class="surface min-h-[26rem] p-5">
              <div class="flex items-center justify-between"><span class="skeleton-block h-7 w-20" /><span class="skeleton-block h-11 w-11" /></div>
              <span class="skeleton-block mt-6 block h-6 w-4/5" />
              <span class="skeleton-block mt-3 block h-4 w-1/3" />
              <span class="skeleton-block mt-7 block h-20 w-full" />
              <span class="skeleton-block mt-7 block h-16 w-full" />
              <span class="skeleton-block mt-7 block h-12 w-full" />
            </article>
          </div>

          <TransitionGroup v-else-if="filteredTests.length" name="card-grid" tag="div" class="mt-7 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            <TestCard v-for="test in visibleTests" :key="test.id" :test="test" @start="startTest" />
          </TransitionGroup>

          <div v-if="!loading && visibleTests.length < filteredTests.length" class="mt-8 flex flex-col items-center gap-3">
            <p class="text-xs font-semibold text-black/45">
              Showing {{ visibleTests.length }} of {{ filteredTests.length }} available papers
            </p>
            <button type="button" class="btn-secondary min-h-11 px-6" @click="visibleLimit += 6">
              Show more mock tests
            </button>
          </div>

          <EmptyState
            v-else
            class="mt-7"
            title="No published tests at this level"
            description="This level does not have a published paper yet. Explore another level or use the study library while new papers are prepared."
          >
            <RouterLink to="/materials" class="btn-secondary">Open study library</RouterLink>
            <button v-if="selectedLevel" type="button" class="btn-quiet" @click="clearLevel">View all levels</button>
          </EmptyState>
        </div>
      </div>
    </section>

    <section class="learning-section" aria-labelledby="learning-heading">
      <div class="page-shell py-16 sm:py-20">
        <div class="max-w-2xl">
          <p class="eyebrow">A smarter practice loop</p>
          <h2 id="learning-heading" class="display-title mt-4 text-4xl font-bold sm:text-5xl">Prepare. Perform. Improve.</h2>
        </div>

        <div class="mt-10 grid gap-4 lg:grid-cols-3">
          <article
            v-for="item in [
              { icon: Clock, number: '01', title: 'Sit a true timed paper', text: 'The server keeps the official deadline, so a refresh or reconnect never restarts your clock.' },
              { icon: Headset, number: '02', title: 'Build listening discipline', text: 'Exam-aware playback limits help you practise careful, focused listening without losing accessible controls.' },
              { icon: TrendCharts, number: '03', title: 'Review what matters', text: 'See section scores and missed answers, then turn those patterns into your next focused study session.' },
            ]"
            :key="item.number"
            class="feature-card"
          >
            <div class="flex items-center justify-between">
              <span class="feature-card__icon"><el-icon :size="22"><component :is="item.icon" /></el-icon></span>
              <span class="text-xs font-black tracking-[0.17em] text-cinnabar">{{ item.number }}</span>
            </div>
            <h3 class="mt-6 font-serif text-2xl font-bold">{{ item.title }}</h3>
            <p class="mt-3 text-sm leading-7 text-black/55">{{ item.text }}</p>
          </article>
        </div>

        <div class="cta-panel mt-12">
          <div class="relative z-10 max-w-2xl">
            <span class="inline-flex items-center gap-2 text-xs font-extrabold uppercase tracking-[0.15em] text-gold">
              <el-icon><Document /></el-icon> Your next paper is waiting
            </span>
            <h2 class="display-title mt-4 text-3xl font-bold text-white sm:text-4xl">Make exam day feel familiar.</h2>
            <p class="mt-3 max-w-xl text-sm leading-7 text-white/55">Start with your level, learn the interface, and replace uncertainty with a repeatable routine.</p>
          </div>
          <a href="#levels" class="btn-primary relative z-10 flex-none !border-white !bg-white !text-ink hover:!bg-[#f2eee5]">
            Find a mock test <el-icon><ArrowRight /></el-icon>
          </a>
        </div>
      </div>
    </section>

    <footer class="site-footer">
      <div class="page-shell flex flex-col gap-7 py-10 sm:flex-row sm:items-center sm:justify-between">
        <RouterLink to="/" class="brand-footer" aria-label="Mòkǎo home">
          <span>墨</span>
          <span><b>Mòkǎo</b><small>Focused HSK preparation</small></span>
        </RouterLink>
        <nav class="flex flex-wrap gap-x-6 gap-y-2 text-xs font-bold text-white/70" aria-label="Footer navigation">
          <a href="#levels" class="hover:text-white">Mock tests</a>
          <RouterLink to="/materials" class="hover:text-white">Study library</RouterLink>
          <RouterLink :to="auth.isAuthenticated ? '/dashboard' : '/login'" class="hover:text-white">Account</RouterLink>
        </nav>
        <p class="text-xs text-white/70">© {{ currentYear }} Mòkǎo</p>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.hero {
  position: relative;
  overflow: hidden;
  border-bottom: 1px solid var(--line);
  background-color: rgba(247, 244, 237, 0.76);
}

#levels,
.learning-section,
.site-footer {
  content-visibility: auto;
}

#levels {
  contain-intrinsic-size: auto 2200px;
}

.learning-section {
  contain-intrinsic-size: auto 1050px;
}

.site-footer {
  contain-intrinsic-size: auto 210px;
}

.hero-orb {
  position: absolute;
  border-radius: 999px;
  pointer-events: none;
  filter: blur(2px);
}

.hero-orb--one {
  top: -13rem;
  right: -10rem;
  width: 36rem;
  height: 36rem;
  border: 1px solid rgba(183, 59, 46, 0.08);
  box-shadow: 0 0 0 5rem rgba(183, 59, 46, 0.025), 0 0 0 10rem rgba(183, 59, 46, 0.02);
}

.hero-orb--two {
  bottom: 2rem;
  left: -8rem;
  width: 17rem;
  height: 17rem;
  background: rgba(201, 148, 62, 0.075);
  filter: blur(45px);
}

.hero-grid {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  min-height: 39rem;
  align-items: center;
  gap: 4rem;
  padding-block: 4.5rem 3.5rem;
}

.hero-copy {
  position: relative;
  z-index: 2;
  min-width: 0;
}

.availability-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.65rem;
  border: 1px solid rgba(22, 128, 93, 0.14);
  border-radius: 999px;
  padding: 0.45rem 0.75rem;
  color: rgba(23, 33, 30, 0.65);
  background: rgba(255, 255, 255, 0.62);
  font-size: 0.68rem;
  font-weight: 800;
  box-shadow: var(--shadow-xs);
}

.benefit-check {
  display: grid;
  width: 1.25rem;
  height: 1.25rem;
  place-items: center;
  border-radius: 999px;
  color: var(--jade);
  background: rgba(31, 106, 87, 0.1);
}

.exam-stage {
  position: relative;
  z-index: 1;
  width: 100%;
  min-width: 0;
  max-width: 34rem;
  margin-inline: auto;
  padding: 1rem;
}

.exam-glow {
  position: absolute;
  inset: 12% 5% 2%;
  border-radius: 4rem;
  background: rgba(31, 106, 87, 0.21);
  filter: blur(45px);
}

.exam-preview {
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 1.5rem;
  color: white;
  background: linear-gradient(145deg, #192723 0%, #111b18 100%);
  box-shadow: 0 32px 80px rgba(15, 29, 24, 0.25);
  transform: perspective(1100px) rotateY(-2deg) rotateX(1deg);
}

.exam-preview__topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding: 1.15rem;
}

.timer-chip {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 0.4rem;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 0.75rem;
  padding: 0.55rem 0.7rem;
  color: white;
  background: rgba(255, 255, 255, 0.07);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.75rem;
  font-weight: 800;
}

.exam-progress {
  height: 3px;
  background: rgba(255, 255, 255, 0.07);
}

.exam-progress span {
  display: block;
  height: 100%;
  border-radius: 0 99px 99px 0;
  background: linear-gradient(90deg, var(--cinnabar), #e17749);
  animation: progress-arrive 900ms ease-out both;
}

.exam-preview__body {
  display: grid;
  grid-template-columns: 4.6rem minmax(0, 1fr);
  gap: 1.25rem;
  padding: 1.5rem 1.15rem;
}

.question-map {
  display: grid;
  align-content: start;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.4rem;
}

.question-map span {
  display: grid;
  aspect-ratio: 1;
  place-items: center;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 0.45rem;
  color: rgba(255, 255, 255, 0.38);
  background: rgba(255, 255, 255, 0.045);
  font-size: 0.6rem;
  font-weight: 800;
}

.question-map span.answered {
  color: white;
  background: rgba(31, 106, 87, 0.75);
}

.question-map span.current {
  border-color: var(--cinnabar);
  color: white;
  background: var(--cinnabar);
  box-shadow: 0 0 0 3px rgba(183, 59, 46, 0.18);
}

.answer-preview {
  display: flex;
  min-height: 2.65rem;
  align-items: center;
  gap: 0.7rem;
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 0.75rem;
  padding: 0.5rem 0.65rem;
  color: rgba(255, 255, 255, 0.6);
  background: rgba(255, 255, 255, 0.04);
  font-size: 0.78rem;
}

.answer-preview b {
  display: grid;
  width: 1.65rem;
  height: 1.65rem;
  flex: none;
  place-items: center;
  border-radius: 0.45rem;
  background: rgba(255, 255, 255, 0.07);
  font-size: 0.65rem;
}

.answer-preview.selected {
  border-color: rgba(76, 179, 147, 0.5);
  color: white;
  background: rgba(31, 106, 87, 0.32);
}

.exam-preview__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  padding: 0.9rem 1.15rem;
  color: rgba(255, 255, 255, 0.45);
  font-size: 0.65rem;
  font-weight: 750;
}

.score-float {
  position: absolute;
  right: -0.25rem;
  bottom: -0.3rem;
  display: flex;
  align-items: center;
  gap: 0.7rem;
  border: 1px solid var(--line);
  border-radius: 1rem;
  background: rgba(255, 255, 255, 0.96);
  padding: 0.65rem 0.85rem;
  box-shadow: var(--shadow-md);
  animation: gentle-float 4s ease-in-out infinite;
}

.score-float small {
  display: block;
  margin-top: 0.2rem;
  color: rgba(23, 33, 30, 0.42);
  font-size: 0.55rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.trust-strip {
  position: relative;
  display: grid;
  overflow: hidden;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border: 1px solid var(--line);
  border-radius: 1.2rem;
  background: rgba(255, 255, 255, 0.58);
  box-shadow: var(--shadow-xs);
  backdrop-filter: blur(12px);
}

.trust-strip div {
  padding: 1.1rem 1.25rem;
  text-align: center;
}

.trust-strip div + div {
  border-left: 1px solid var(--line);
}

.trust-strip dt {
  font-family: Georgia, serif;
  font-size: 1.35rem;
  font-weight: 800;
}

.trust-strip dd {
  margin: 0.2rem 0 0;
  color: rgba(23, 33, 30, 0.45);
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0.07em;
  text-transform: uppercase;
}

.level-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
}

.level-card {
  position: relative;
  display: flex;
  min-height: 5rem;
  align-items: center;
  gap: 0.85rem;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 1rem;
  color: var(--ink);
  background: rgba(255, 255, 255, 0.64);
  padding: 0.75rem;
  text-align: left;
  transition: transform 180ms ease, border-color 180ms ease, background-color 180ms ease, box-shadow 180ms ease;
}

.level-card:hover {
  transform: translateY(-2px);
  border-color: rgba(183, 59, 46, 0.25);
  background: white;
  box-shadow: var(--shadow-sm);
}

.level-card--selected {
  border-color: var(--cinnabar);
  color: white;
  background: linear-gradient(135deg, var(--cinnabar), #a33127);
  box-shadow: 0 12px 28px rgba(183, 59, 46, 0.2);
}

.level-card__number {
  display: grid;
  width: 2.8rem;
  height: 2.8rem;
  flex: none;
  place-items: center;
  border-radius: 0.8rem;
  color: var(--jade);
  background: rgba(31, 106, 87, 0.08);
  font-family: Georgia, serif;
  font-size: 1.2rem;
  font-weight: 800;
}

.level-card--selected .level-card__number {
  color: white;
  background: rgba(255, 255, 255, 0.13);
}

.level-card small {
  display: block;
  margin-top: 0.25rem;
  overflow: hidden;
  color: rgba(23, 33, 30, 0.42);
  font-size: 0.61rem;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.level-card--selected small {
  color: rgba(255, 255, 255, 0.65);
}

.level-card__count {
  display: grid;
  width: 1.6rem;
  height: 1.6rem;
  flex: none;
  place-items: center;
  margin-left: auto;
  border-radius: 999px;
  color: rgba(23, 33, 30, 0.42);
  background: rgba(23, 33, 30, 0.05);
  font-size: 0.65rem;
  font-weight: 850;
}

.level-card--selected .level-card__count {
  color: white;
  background: rgba(255, 255, 255, 0.15);
}

.learning-section {
  border-top: 1px solid var(--line);
  background: #eee9de;
}

.feature-card {
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(23, 33, 30, 0.08);
  border-radius: 1.25rem;
  background: rgba(255, 255, 255, 0.55);
  padding: 1.5rem;
  transition: transform 200ms ease, background-color 200ms ease, box-shadow 200ms ease;
}

.feature-card:hover {
  transform: translateY(-3px);
  background: rgba(255, 255, 255, 0.78);
  box-shadow: var(--shadow-sm);
}

.feature-card__icon {
  display: grid;
  width: 3rem;
  height: 3rem;
  place-items: center;
  border-radius: 0.9rem;
  color: var(--jade);
  background: rgba(31, 106, 87, 0.09);
}

.cta-panel {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2rem;
  overflow: hidden;
  border-radius: 1.5rem;
  background: linear-gradient(130deg, #17241f 0%, #1d302a 65%, #29483e 100%);
  padding: 2rem;
  box-shadow: var(--shadow-md);
}

.cta-panel::after {
  position: absolute;
  top: -7rem;
  right: -5rem;
  width: 18rem;
  height: 18rem;
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 999px;
  content: '';
  box-shadow: 0 0 0 3rem rgba(255, 255, 255, 0.02), 0 0 0 6rem rgba(255, 255, 255, 0.015);
}

.site-footer {
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  color: white;
  background: #111a17;
}

.brand-footer {
  display: inline-flex;
  align-items: center;
  gap: 0.7rem;
}

.brand-footer > span:first-child {
  display: grid;
  width: 2.5rem;
  height: 2.5rem;
  place-items: center;
  border-radius: 0.75rem;
  background: var(--cinnabar);
  font-family: Georgia, serif;
  font-size: 1.1rem;
  font-weight: 800;
}

.brand-footer b {
  display: block;
  font-family: Georgia, serif;
  font-size: 1rem;
}

.brand-footer small {
  display: block;
  color: rgba(255, 255, 255, 0.68);
  font-size: 0.65rem;
}

@keyframes progress-arrive {
  from { width: 0; }
}

@keyframes gentle-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-5px); }
}

@media (min-width: 1024px) {
  .hero-grid {
    grid-template-columns: minmax(0, 1.04fr) minmax(27rem, 0.96fr);
  }
}

@media (min-width: 1280px) {
  .level-grid {
    grid-template-columns: repeat(6, minmax(0, 1fr));
  }

  .level-card {
    min-height: 8.5rem;
    align-items: flex-start;
    flex-direction: column;
  }

  .level-card__count {
    position: absolute;
    top: 0.8rem;
    right: 0.8rem;
  }
}

@media (max-width: 1023px) {
  .hero-grid {
    gap: 3rem;
    padding-top: 3.5rem;
  }

  .hero-copy {
    max-width: 48rem;
  }

  .exam-stage {
    max-width: 38rem;
  }
}

@media (max-width: 767px) {
  .hero-grid {
    gap: 2.5rem;
    padding-block: 2.5rem 3rem;
  }

  .exam-stage {
    padding-inline: 0;
  }

  .exam-preview {
    transform: none;
  }

  .score-float {
    right: -0.25rem;
  }

  .trust-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .trust-strip div:nth-child(3) {
    border-left: 0;
  }

  .trust-strip div:nth-child(n + 3) {
    border-top: 1px solid var(--line);
  }

  .level-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .level-card {
    align-items: flex-start;
    flex-direction: column;
  }

  .level-card__count {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
  }

  .cta-panel {
    align-items: flex-start;
    flex-direction: column;
    padding: 1.5rem;
  }
}

@media (max-width: 480px) {
  .exam-preview__body {
    grid-template-columns: 3.6rem minmax(0, 1fr);
    gap: 0.75rem;
    padding-inline: 0.8rem;
  }

  .exam-preview__topbar,
  .exam-preview__footer {
    padding-inline: 0.8rem;
  }

  .score-float {
    display: none;
  }

  .trust-strip dt {
    font-size: 1.1rem;
  }

  .trust-strip dd {
    font-size: 0.54rem;
  }

  .level-card {
    min-height: 8.2rem;
  }
}
</style>
