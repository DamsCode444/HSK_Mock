<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Check, Close, Clock, Medal, Warning } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import EmptyState from '../components/EmptyState.vue'
import { http, errorMessage } from '../services/http'
import { formatLevel, normalizeResult } from '../services/normalizers'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const loadError = ref('')
const result = ref(null)
const reviewFilter = ref('all')

const scorePercent = computed(() => result.value?.maxScore ? Math.min(100, Math.round((result.value.score / result.value.maxScore) * 100)) : 0)
const filteredReview = computed(() => {
  if (!result.value) return []
  if (reviewFilter.value === 'incorrect') return result.value.review.filter((item) => item.isCorrect === false)
  if (reviewFilter.value === 'correct') return result.value.review.filter((item) => item.isCorrect === true)
  return result.value.review
})
const correctCount = computed(() => result.value?.review.filter((item) => item.isCorrect === true).length || 0)
const incorrectCount = computed(() => result.value?.review.filter((item) => item.isCorrect === false).length || 0)
const ungradedCount = computed(() => result.value?.review.filter((item) => item.isCorrect === null).length || 0)

function displayAnswer(value) {
  if (Array.isArray(value)) return value.join(' → ')
  if (value === null || value === undefined || String(value).trim() === '') return 'No answer'
  return String(value)
}

function formatDuration(seconds) {
  if (!seconds) return '—'
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m ${Math.floor(seconds % 60)}s`
}

onMounted(async () => {
  try {
    const { data } = await http.get(`/results/${route.params.attemptId}`)
    result.value = normalizeResult(data)
  } catch (error) {
    loadError.value = errorMessage(error, 'Your score report could not be loaded.')
    ElMessage.error(loadError.value)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="pb-20 pt-10 sm:pt-14">
    <div class="page-shell">
      <button type="button" class="mb-6 inline-flex items-center gap-2 text-sm font-bold text-black/50 hover:text-cinnabar" @click="router.push('/dashboard')"><el-icon><ArrowLeft /></el-icon> Back to dashboard</button>

      <div v-if="loading" class="space-y-6">
        <el-skeleton animated class="surface p-8"><template #template><el-skeleton-item variant="h1" class="!h-72 !rounded-2xl" /></template></el-skeleton>
      </div>
      <div v-else-if="loadError" class="surface mx-auto max-w-lg p-8 text-center">
        <span class="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-red-50 text-cinnabar"><el-icon :size="24"><Warning /></el-icon></span>
        <h1 class="mt-4 font-serif text-2xl font-bold">Score report unavailable</h1><p class="mt-3 text-sm leading-6 text-black/50">{{ loadError }}</p><el-button type="primary" class="mt-6" @click="router.go(0)">Try again</el-button>
      </div>

      <template v-else-if="result">
        <section class="relative overflow-hidden rounded-[1.6rem] bg-[#17211e] p-6 text-white shadow-soft sm:p-10">
          <div class="absolute -right-28 -top-28 h-96 w-96 rounded-full border-[70px] border-white/[0.025]" />
          <div class="relative grid items-center gap-10 md:grid-cols-[1fr_auto]">
            <div>
              <span class="inline-flex rounded-lg bg-gold/15 px-3 py-1.5 text-xs font-black uppercase tracking-widest text-gold">{{ formatLevel(result.level) }} · {{ result.testCode || 'Score report' }}</span>
              <h1 class="display-title mt-5 text-4xl font-bold sm:text-5xl">{{ result.passed ? 'Well done — you passed.' : 'Keep going — this is useful data.' }}</h1>
              <p class="mt-4 max-w-2xl leading-7 text-white/50">{{ result.passed ? 'You reached the passing standard for this mock paper. Review each section to make the result repeatable.' : `The passing score is ${result.passScore}. Review the missed questions, focus your next study block, and try again.` }}</p>
              <div class="mt-7 flex flex-wrap gap-5 text-sm">
                <span class="flex items-center gap-2 text-white/60"><el-icon class="text-gold"><Medal /></el-icon> {{ result.title }}</span>
                <span v-if="result.durationSeconds" class="flex items-center gap-2 text-white/60"><el-icon class="text-gold"><Clock /></el-icon> {{ formatDuration(result.durationSeconds) }}</span>
              </div>
            </div>
            <div class="relative mx-auto h-48 w-48 shrink-0 sm:h-56 sm:w-56">
              <svg class="h-full w-full -rotate-90" viewBox="0 0 120 120" role="img" :aria-label="`${scorePercent}% of maximum score`">
                <circle cx="60" cy="60" r="52" fill="none" stroke="rgba(255,255,255,.1)" stroke-width="7" />
                <circle cx="60" cy="60" r="52" fill="none" :stroke="result.passed ? '#5ca48f' : '#c99643'" stroke-linecap="round" stroke-width="7" :stroke-dasharray="`${scorePercent * 3.267} 326.7`" />
              </svg>
              <div class="absolute inset-0 grid place-items-center text-center"><span><b class="block font-serif text-5xl">{{ result.score }}</b><small class="font-bold text-white/40">out of {{ result.maxScore }}</small><span class="mx-auto mt-2 block w-fit rounded-md px-2 py-1 text-[10px] font-black uppercase tracking-widest" :class="result.passed ? 'bg-jade text-white' : 'bg-gold text-ink'">{{ result.passed ? 'Pass' : 'Not yet' }}</span></span></div>
            </div>
          </div>
        </section>

        <section class="mt-8">
          <div class="mb-5"><span class="eyebrow">Section analysis</span><h2 class="display-title mt-2 text-3xl font-bold">Where your score came from.</h2></div>
          <div v-if="result.sections.length" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <article v-for="section in result.sections" :key="section.name" class="surface p-5">
              <div class="flex items-start justify-between"><span class="text-xs font-black uppercase tracking-[0.15em] text-black/40">{{ section.name }}</span><b class="font-serif text-3xl">{{ section.score }}<small class="text-sm text-black/35">/{{ section.maxScore }}</small></b></div>
              <div class="mt-5 h-2 overflow-hidden rounded-full bg-black/[0.07]"><div class="h-full rounded-full bg-jade" :style="{ width: `${Math.min(100, section.maxScore ? (section.score / section.maxScore) * 100 : 0)}%` }" /></div>
              <p v-if="section.correct != null" class="mt-3 text-xs font-semibold text-black/40">{{ section.correct }} correct out of {{ section.total }}</p>
            </article>
          </div>
          <EmptyState v-else title="Section scores are still being prepared" description="The total score is available, but this result does not include a section breakdown." />
        </section>

        <section class="mt-12">
          <div class="flex flex-col gap-4 border-b border-black/10 pb-5 sm:flex-row sm:items-end sm:justify-between">
            <div><span class="eyebrow">Question review</span><h2 class="display-title mt-2 text-3xl font-bold">Learn from every answer.</h2><p v-if="result.review.length" class="mt-2 text-sm text-black/45">{{ correctCount }} correct · {{ incorrectCount }} to review <span v-if="ungradedCount">· {{ ungradedCount }} ungraded</span></p></div>
            <el-segmented v-model="reviewFilter" :options="[{ label: 'All', value: 'all' }, { label: 'To review', value: 'incorrect' }, { label: 'Correct', value: 'correct' }]" />
          </div>

          <div v-if="filteredReview.length" class="mt-6 space-y-4">
            <article v-for="question in filteredReview" :key="question.id" class="surface overflow-hidden">
              <div class="flex items-center gap-3 border-b border-black/[0.07] px-5 py-4 sm:px-6">
                <span class="grid h-8 w-8 place-items-center rounded-lg" :class="question.isCorrect === null ? 'bg-gold text-ink' : question.isCorrect ? 'bg-jade text-white' : 'bg-cinnabar text-white'"><el-icon><Warning v-if="question.isCorrect === null" /><Check v-else-if="question.isCorrect" /><Close v-else /></el-icon></span>
                <div><b>Question {{ question.number }}</b><span class="ml-2 text-[10px] font-black uppercase tracking-wider text-black/35">{{ question.section }}</span></div>
                <span v-if="question.earnedScore != null" class="ml-auto text-xs font-bold text-black/40">{{ question.earnedScore }} pts</span>
              </div>
              <div class="p-5 sm:p-6">
                <p v-if="question.text" class="whitespace-pre-wrap font-serif text-lg font-semibold leading-8">{{ question.text }}</p>
                <img v-if="question.imageUrl" :src="question.imageUrl" :alt="`Question ${question.number}`" class="mt-4 max-h-96 rounded-xl border border-black/10 bg-white object-contain" />
                <div class="mt-5 grid gap-3 sm:grid-cols-2">
                  <div class="rounded-xl border p-4" :class="question.isCorrect === null ? 'border-gold/30 bg-gold/[0.06]' : question.isCorrect ? 'border-jade/20 bg-jade/[0.045]' : 'border-cinnabar/20 bg-cinnabar/[0.04]'"><span class="text-[10px] font-black uppercase tracking-wider text-black/40">Your answer</span><p class="mt-2 whitespace-pre-wrap font-semibold" :class="question.userAnswer ? '' : 'italic text-black/35'">{{ displayAnswer(question.userAnswer) }}</p></div>
                  <div class="rounded-xl border p-4" :class="question.isCorrect === null ? 'border-gold/30 bg-gold/[0.06]' : 'border-jade/20 bg-jade/[0.045]'"><span class="text-[10px] font-black uppercase tracking-wider" :class="question.isCorrect === null ? 'text-[#956817]' : 'text-jade'">{{ question.isCorrect === null ? 'Grading status' : 'Correct answer' }}</span><p class="mt-2 whitespace-pre-wrap font-semibold">{{ question.isCorrect === null ? 'Not graded automatically in Phase 1' : displayAnswer(question.correctAnswer) }}</p></div>
                </div>
                <div v-if="question.explanation" class="mt-4 rounded-xl bg-gold/[0.09] px-4 py-3 text-sm leading-6 text-black/60"><b class="text-ink">Why:</b> {{ question.explanation }}</div>
              </div>
            </article>
          </div>
          <EmptyState v-else-if="result.review.length" class="mt-6" title="No questions match this filter" description="Choose another review filter to see more answers." />
          <EmptyState v-else class="mt-6" title="Detailed review is unavailable" description="This result contains the score summary but no question-level answer data." />
        </section>

        <div class="mt-10 flex flex-col justify-center gap-3 sm:flex-row"><RouterLink to="/dashboard" class="inline-flex h-11 items-center justify-center rounded-xl border border-black/10 bg-white px-5 text-sm font-bold">Back to dashboard</RouterLink><RouterLink to="/#levels" class="inline-flex h-11 items-center justify-center rounded-xl bg-cinnabar px-5 text-sm font-bold text-white">Take another mock test</RouterLink></div>
      </template>
    </div>
  </section>
</template>
