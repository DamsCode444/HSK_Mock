<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, Check, Clock, Headset, Reading, TrendCharts } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
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
const selectedLevel = ref(Number(route.query.level || 0))

const publishedTests = computed(() => tests.value.filter((test) => !['draft', 'archived'].includes(test.status)))
const filteredTests = computed(() =>
  selectedLevel.value
    ? publishedTests.value.filter((test) => test.level === selectedLevel.value)
    : publishedTests.value,
)

function countForLevel(level) {
  return publishedTests.value.filter((test) => test.level === level).length
}

function chooseLevel(level) {
  selectedLevel.value = selectedLevel.value === level ? 0 : level
  router.replace({ query: selectedLevel.value ? { level: selectedLevel.value } : {} })
  requestAnimationFrame(() => document.querySelector('#available-tests')?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
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
  <div>
    <section class="soft-grid relative overflow-hidden border-b border-black/[0.06]">
      <div class="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-cinnabar/[0.06] blur-3xl" />
      <div class="page-shell grid min-h-[630px] items-center gap-14 py-20 lg:grid-cols-[1.08fr_.92fr] lg:py-24">
        <div class="relative z-10">
          <span class="eyebrow">Practise with purpose</span>
          <h1 class="display-title mt-5 max-w-3xl text-5xl font-bold leading-[1.02] sm:text-6xl lg:text-7xl">
            Walk into your HSK exam <span class="text-cinnabar">ready.</span>
          </h1>
          <p class="mt-7 max-w-xl text-base leading-8 text-black/60 sm:text-lg">
            Real test papers. Official timing. Focused review. Build the calm, rhythm, and accuracy you need before exam day.
          </p>
          <div class="mt-9 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
            <a href="#levels" class="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-cinnabar px-6 text-sm font-extrabold text-white shadow-lg shadow-red-900/15 transition hover:bg-[#9f3025]">
              Choose your HSK level <el-icon><ArrowRight /></el-icon>
            </a>
            <RouterLink to="/materials" class="inline-flex h-12 items-center justify-center gap-2 rounded-xl border border-jade/20 bg-jade px-6 text-sm font-extrabold text-white transition hover:bg-[#194f42]">
              <el-icon><Reading /></el-icon>Open study library
            </RouterLink>
            <RouterLink v-if="auth.isAuthenticated" :to="auth.isAdmin ? '/admin' : '/dashboard'" class="inline-flex h-12 items-center justify-center rounded-xl border border-black/10 bg-white/60 px-6 text-sm font-extrabold hover:bg-white">
              Open dashboard
            </RouterLink>
            <RouterLink v-else to="/register" class="inline-flex h-12 items-center justify-center rounded-xl border border-black/10 bg-white/60 px-6 text-sm font-extrabold hover:bg-white">
              Create a free account
            </RouterLink>
          </div>
          <div class="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-xs font-bold text-black/45">
            <span class="flex items-center gap-2"><el-icon class="text-jade"><Check /></el-icon> Answers save automatically</span>
            <span class="flex items-center gap-2"><el-icon class="text-jade"><Check /></el-icon> Resume after refresh</span>
            <span class="flex items-center gap-2"><el-icon class="text-jade"><Check /></el-icon> Detailed score review</span>
          </div>
        </div>

        <div class="relative mx-auto w-full max-w-[500px] lg:mx-0">
          <div class="absolute -left-6 -top-7 h-32 w-32 rounded-full border border-gold/25" />
          <div class="surface relative overflow-hidden !bg-[#17211e] p-5 text-white sm:p-7">
            <div class="flex items-center justify-between border-b border-white/10 pb-5">
              <div>
                <p class="text-[10px] font-black uppercase tracking-[0.2em] text-white/35">Live exam preview</p>
                <h2 class="mt-2 font-serif text-xl font-bold">HSK 4 · Listening</h2>
              </div>
              <span class="rounded-xl bg-cinnabar px-3 py-2 font-mono text-sm font-bold">32:18</span>
            </div>
            <div class="mt-6 grid grid-cols-[64px_1fr] gap-5">
              <div class="grid content-start grid-cols-2 gap-2">
                <span v-for="n in 10" :key="n" class="grid aspect-square place-items-center rounded-md text-[10px] font-black" :class="n === 6 ? 'bg-cinnabar' : n < 6 ? 'bg-jade' : 'bg-white/10 text-white/50'">{{ n }}</span>
              </div>
              <div>
                <p class="text-[10px] font-black uppercase tracking-widest text-gold">Question 6</p>
                <p class="mt-4 font-serif text-lg leading-8">男的为什么要去图书馆？</p>
                <div class="mt-5 space-y-2">
                  <span v-for="(answer, index) in ['借一本书', '见一位朋友', '准备考试']" :key="answer" class="flex items-center gap-3 rounded-xl border px-3 py-2.5 text-sm" :class="index === 2 ? 'border-jade bg-jade/30' : 'border-white/10 bg-white/5 text-white/60'">
                    <b class="grid h-6 w-6 place-items-center rounded-md bg-white/10 text-[10px]">{{ String.fromCharCode(65 + index) }}</b>{{ answer }}
                  </span>
                </div>
              </div>
            </div>
            <div class="mt-7 flex items-center justify-between border-t border-white/10 pt-5 text-xs font-bold text-white/45">
              <span>Answer saved</span><span class="rounded-lg bg-white/10 px-4 py-2 text-white">Next →</span>
            </div>
          </div>
          <div class="absolute -bottom-5 -right-3 flex items-center gap-3 rounded-2xl border border-black/5 bg-white px-4 py-3 shadow-soft sm:-right-8">
            <span class="grid h-10 w-10 place-items-center rounded-xl bg-jade/10 text-jade"><el-icon :size="20"><TrendCharts /></el-icon></span>
            <span><b class="block text-lg leading-none">+18%</b><small class="text-[10px] font-bold uppercase tracking-wider text-black/40">average gain</small></span>
          </div>
        </div>
      </div>
    </section>

    <section id="levels" class="scroll-mt-24 py-20 sm:py-24">
      <div class="page-shell">
        <div class="max-w-2xl">
          <span class="eyebrow">Six levels, one clear path</span>
          <h2 class="display-title mt-4 text-4xl font-bold sm:text-5xl">Find your next challenge.</h2>
          <p class="mt-4 leading-7 text-black/55">Select a level to see the imported mock papers available for practice.</p>
        </div>

        <div class="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <button
            v-for="level in LEVEL_META"
            :key="level.level"
            type="button"
            class="group rounded-2xl border p-4 text-left transition duration-200"
            :class="selectedLevel === level.level ? 'border-cinnabar bg-cinnabar text-white shadow-lg shadow-red-900/10' : 'border-black/10 bg-white/60 hover:-translate-y-0.5 hover:border-cinnabar/30 hover:bg-white'"
            @click="chooseLevel(level.level)"
          >
            <span class="text-[10px] font-black uppercase tracking-[0.16em] opacity-55">Level</span>
            <span class="mt-1 block font-serif text-3xl font-bold">{{ level.level }}</span>
            <span class="mt-4 block text-[11px] font-bold opacity-60">{{ level.duration }} min · {{ level.questions }} Qs</span>
            <span class="mt-1 block text-[10px] font-semibold opacity-50">{{ countForLevel(level.level) }} {{ countForLevel(level.level) === 1 ? 'test' : 'tests' }}</span>
          </button>
        </div>

        <div id="available-tests" class="scroll-mt-24 mt-16 flex flex-col gap-3 border-b border-black/10 pb-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 class="font-serif text-2xl font-bold">{{ selectedLevel ? `HSK ${selectedLevel} mock tests` : 'All available tests' }}</h2>
            <p class="mt-1 text-sm text-black/45">{{ filteredTests.length }} imported {{ filteredTests.length === 1 ? 'paper' : 'papers' }} ready to take</p>
          </div>
          <button v-if="selectedLevel" class="text-sm font-bold text-cinnabar" @click="selectedLevel = 0; router.replace({ query: {} })">Show every level</button>
        </div>

        <div v-if="loading" class="mt-7 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          <el-skeleton v-for="n in 3" :key="n" animated class="surface p-5">
            <template #template><el-skeleton-item variant="h3" class="!h-52 !rounded-xl" /></template>
          </el-skeleton>
        </div>
        <div v-else-if="filteredTests.length" class="mt-7 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          <TestCard v-for="test in filteredTests" :key="test.id" :test="test" @start="startTest" />
        </div>
        <EmptyState v-else class="mt-7" title="No published tests at this level" description="Ask an administrator to import a test bundle, then refresh this page." />
      </div>
    </section>

    <section class="border-y border-black/[0.06] bg-[#eee9dd] py-20">
      <div class="page-shell grid gap-8 lg:grid-cols-3">
        <article v-for="item in [
          { icon: Clock, n: '01', title: 'Sit a true timed paper', text: 'The server keeps the official deadline. Refresh or reconnect without restarting your clock.' },
          { icon: Headset, n: '02', title: 'Practise listening discipline', text: 'Playback limits mirror exam conditions, while pause and volume remain accessible.' },
          { icon: TrendCharts, n: '03', title: 'Review what matters', text: 'See section scores, missed answers, and the patterns that deserve your next study session.' },
        ]" :key="item.n" class="relative border-l border-black/10 pl-6">
          <span class="text-xs font-black tracking-widest text-cinnabar">{{ item.n }}</span>
          <el-icon class="absolute right-2 top-0 text-black/10" :size="42"><component :is="item.icon" /></el-icon>
          <h3 class="mt-5 font-serif text-2xl font-bold">{{ item.title }}</h3>
          <p class="mt-3 text-sm leading-7 text-black/55">{{ item.text }}</p>
        </article>
      </div>
    </section>

    <footer class="bg-ink py-12 text-white">
      <div class="page-shell flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div class="flex items-center gap-3"><span class="grid h-10 w-10 place-items-center rounded-xl bg-cinnabar font-serif text-xl font-bold">墨</span><span><b class="block font-serif text-lg">Mòkǎo</b><small class="text-white/40">Focused HSK practice</small></span></div>
        <p class="text-xs text-white/35">Local MVP · Content from your imported HSK test bundles</p>
      </div>
    </footer>
  </div>
</template>
