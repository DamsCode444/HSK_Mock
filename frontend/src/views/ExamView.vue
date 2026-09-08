<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Clock,
  Close,
  FullScreen,
  Grid,
  Loading,
  RefreshRight,
  Warning,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import QuestionNavigator from '../components/QuestionNavigator.vue'
import QuestionRenderer from '../components/QuestionRenderer.vue'
import RestrictedAudioPlayer from '../components/RestrictedAudioPlayer.vue'
import { useExamStore } from '../stores/exam'
import { errorMessage } from '../services/http'

const route = useRoute()
const router = useRouter()
const exam = useExamStore()
const currentIndex = ref(0)
const remainingSeconds = ref(0)
const deadlineMs = ref(0)
const mobileNavigator = ref(false)
const contentPane = ref(null)
const allowLeave = ref(false)
const initialising = ref(true)
const pageError = ref('')
const syncInProgress = ref(false)
const automaticSubmission = ref(false)
const autoRetryTimer = ref(null)
const pendingText = new Map()
let tickTimer = null
let syncTimer = null

const currentQuestion = computed(() => exam.questions[currentIndex.value])
const sharedAudioQuestion = computed(() => {
  const listening = exam.questions.filter(
    (question) => question.section === 'LISTENING' && question.audioUrl,
  )
  if (listening.length < 2) return null
  const urls = new Set(listening.map((question) => question.audioUrl))
  return urls.size === 1 ? listening[0] : null
})
const currentAnswer = computed(() => currentQuestion.value ? exam.answers[currentQuestion.value.id] ?? '' : '')
const saveState = computed(() => currentQuestion.value ? exam.saveStates[currentQuestion.value.id] : '')
const unansweredCount = computed(() => Math.max(0, exam.questions.length - exam.answeredCount))
const progress = computed(() => exam.questions.length ? ((currentIndex.value + 1) / exam.questions.length) * 100 : 0)
const urgentTime = computed(() => remainingSeconds.value <= 300)
const timeText = computed(() => {
  const seconds = Math.max(0, remainingSeconds.value)
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
})

function updateDeadline(attempt, fallback = false) {
  if (!attempt) return
  if (attempt.remainingSeconds !== null && attempt.remainingSeconds !== undefined) {
    remainingSeconds.value = Math.max(0, Math.ceil(attempt.remainingSeconds))
    deadlineMs.value = Date.now() + remainingSeconds.value * 1000
    return
  }
  if (attempt.expiresAt) {
    const parsed = new Date(attempt.expiresAt).getTime()
    if (Number.isFinite(parsed)) {
      deadlineMs.value = parsed
      remainingSeconds.value = Math.max(0, Math.ceil((parsed - Date.now()) / 1000))
      return
    }
  }
  if (fallback) {
    remainingSeconds.value = Number(exam.test?.duration || 40) * 60
    deadlineMs.value = Date.now() + remainingSeconds.value * 1000
  }
}

function tick() {
  if (!deadlineMs.value || automaticSubmission.value) return
  remainingSeconds.value = Math.max(0, Math.ceil((deadlineMs.value - Date.now()) / 1000))
  if (remainingSeconds.value <= 0) performSubmit(true)
}

async function syncClock() {
  if (syncInProgress.value || automaticSubmission.value || initialising.value) return
  syncInProgress.value = true
  try {
    const latest = await exam.syncAttempt()
    if (['submitted', 'completed', 'graded'].includes(latest?.status)) {
      allowLeave.value = true
      router.replace(`/results/${exam.attemptId}`)
      return
    }
    updateDeadline(latest)
  } catch {
    // Continue using the last authoritative deadline while temporarily offline.
  } finally {
    syncInProgress.value = false
  }
}

function handleVisibility() {
  if (document.visibilityState === 'visible') syncClock()
}

function beforeUnload(event) {
  if (allowLeave.value || exam.attempt?.status === 'submitted') return
  event.preventDefault()
  event.returnValue = ''
}

function stageAnswer({ value, immediate }) {
  const questionId = currentQuestion.value?.id
  if (questionId === undefined) return
  exam.stageAnswer(questionId, value)
  const pending = pendingText.get(questionId)
  if (pending) clearTimeout(pending.timer)

  if (immediate) {
    pendingText.delete(questionId)
    exam.saveAnswer(questionId, value).catch(() => undefined)
    return
  }

  const timer = setTimeout(() => {
    pendingText.delete(questionId)
    exam.saveAnswer(questionId, value).catch(() => undefined)
  }, 450)
  pendingText.set(questionId, { value, timer })
}

async function flushPendingText(questionId = null) {
  const selected = [...pendingText.entries()].filter(([id]) => questionId === null || String(id) === String(questionId))
  const saves = selected.map(([id, pending]) => {
    clearTimeout(pending.timer)
    pendingText.delete(id)
    return exam.saveAnswer(id, pending.value)
  })
  await Promise.allSettled(saves)
}

async function selectQuestion(index) {
  await flushPendingText(currentQuestion.value?.id)
  currentIndex.value = Math.max(0, Math.min(index, exam.questions.length - 1))
  mobileNavigator.value = false
  await nextTick()
  contentPane.value?.scrollTo({ top: 0, behavior: 'smooth' })
}

function move(delta) {
  selectQuestion(currentIndex.value + delta)
}

async function retryCurrent() {
  try {
    await exam.retryAnswer(currentQuestion.value.id)
    ElMessage.success('Answer saved.')
  } catch (error) {
    ElMessage.error(errorMessage(error, 'The answer still could not be saved.'))
  }
}

async function performSubmit(isAutomatic = false) {
  if (exam.submitting || automaticSubmission.value) return
  if (!isAutomatic) {
    try {
      await ElMessageBox.confirm(
        unansweredCount.value
          ? `You still have ${unansweredCount.value} unanswered question${unansweredCount.value === 1 ? '' : 's'}. You cannot change answers after submission.`
          : 'You have answered every question. You cannot change answers after submission.',
        'Submit this exam?',
        { confirmButtonText: 'Submit exam', cancelButtonText: 'Keep working', type: unansweredCount.value ? 'warning' : 'info' },
      )
    } catch {
      return
    }
  }

  automaticSubmission.value = isAutomatic
  try {
    await flushPendingText()
    const failedIds = Object.entries(exam.saveStates).filter(([, state]) => state === 'error').map(([id]) => id)
    if (failedIds.length) await Promise.all(failedIds.map((id) => exam.retryAnswer(id)))
    await exam.submitExam()
    allowLeave.value = true
    ElMessage.success(isAutomatic ? 'Time is up. Your answers were submitted.' : 'Exam submitted successfully.')
    router.replace(`/results/${exam.attemptId}`)
  } catch (error) {
    automaticSubmission.value = false
    if (isAutomatic || remainingSeconds.value <= 0) {
      ElMessage.error({ message: 'Time is up. Reconnecting to submit your answers…', duration: 4500 })
      clearTimeout(autoRetryTimer.value)
      autoRetryTimer.value = setTimeout(() => performSubmit(true), 5000)
    } else {
      ElMessageBox.alert(
        errorMessage(error, 'Some answers have not reached the server. Check your connection and retry.'),
        'Submission paused',
        { type: 'error', confirmButtonText: 'Continue exam' },
      )
    }
  }
}

async function requestExit() {
  try {
    await ElMessageBox.confirm(
      'Your saved attempt will remain active and the timer will continue running.',
      'Leave the exam?',
      { confirmButtonText: 'Leave exam', cancelButtonText: 'Stay here', type: 'warning' },
    )
    await flushPendingText()
    allowLeave.value = true
    router.push('/dashboard')
  } catch {
    // Staying in the exam is the safe default.
  }
}

function enterFullScreen() {
  if (!document.fullscreenElement) document.documentElement.requestFullscreen?.()
  else document.exitFullscreen?.()
}

onBeforeRouteLeave(async () => {
  if (allowLeave.value || exam.attempt?.status === 'submitted') return true
  try {
    await ElMessageBox.confirm('The exam timer will keep running. Your latest saved answers will be available when you return.', 'Leave active exam?', {
      confirmButtonText: 'Leave', cancelButtonText: 'Stay', type: 'warning',
    })
    await flushPendingText()
    return true
  } catch {
    return false
  }
})

onMounted(async () => {
  try {
    await exam.loadExam(route.params.testId)
    if (['submitted', 'completed', 'graded'].includes(exam.attempt?.status)) {
      allowLeave.value = true
      router.replace(`/results/${exam.attemptId}`)
      return
    }
    updateDeadline(exam.attempt, true)
    tickTimer = setInterval(tick, 250)
    syncTimer = setInterval(syncClock, 15000)
    document.addEventListener('visibilitychange', handleVisibility)
    window.addEventListener('beforeunload', beforeUnload)
  } catch (error) {
    pageError.value = errorMessage(error, exam.loadError || 'This exam could not be opened.')
  } finally {
    initialising.value = false
  }
})

onBeforeUnmount(() => {
  clearInterval(tickTimer)
  clearInterval(syncTimer)
  clearTimeout(autoRetryTimer.value)
  pendingText.forEach((pending) => clearTimeout(pending.timer))
  document.removeEventListener('visibilitychange', handleVisibility)
  window.removeEventListener('beforeunload', beforeUnload)
})
</script>

<template>
  <div class="h-[100dvh] overflow-hidden bg-[#eeece6]">
    <div v-if="initialising" class="grid h-full place-items-center bg-paper">
      <div class="text-center">
        <span class="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-cinnabar text-white shadow-lg shadow-red-900/15"><el-icon class="is-loading" :size="28"><Loading /></el-icon></span>
        <h1 class="mt-5 font-serif text-2xl font-bold">Preparing your exam</h1>
        <p class="mt-2 text-sm text-black/45">Recovering the timer and your saved answers…</p>
      </div>
    </div>

    <div v-else-if="pageError" class="grid h-full place-items-center bg-paper px-5">
      <div class="surface max-w-lg p-8 text-center">
        <span class="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-red-50 text-cinnabar"><el-icon :size="24"><Warning /></el-icon></span>
        <h1 class="mt-4 font-serif text-2xl font-bold">We couldn’t open this exam</h1>
        <p class="mt-3 text-sm leading-6 text-black/50">{{ pageError }}</p>
        <div class="mt-6 flex justify-center gap-3"><el-button @click="router.push('/')">Browse tests</el-button><el-button type="primary" @click="router.go(0)">Try again</el-button></div>
      </div>
    </div>

    <div v-else class="grid h-full grid-rows-[auto_minmax(0,1fr)_auto]">
      <header class="relative z-20 flex h-[72px] items-center border-b border-black/10 bg-white px-3 shadow-sm sm:px-5">
        <button type="button" class="mr-3 grid h-10 w-10 place-items-center rounded-xl hover:bg-black/5" aria-label="Leave exam" @click="requestExit"><el-icon :size="20"><Close /></el-icon></button>
        <div class="min-w-0">
          <div class="flex items-center gap-2"><span class="rounded-md bg-cinnabar px-2 py-1 text-[10px] font-black uppercase tracking-wider text-white">{{ exam.test.levelLabel }}</span><span class="hidden text-[10px] font-black uppercase tracking-wider text-black/35 sm:inline">{{ exam.test.testCode }}</span></div>
          <h1 class="mt-1 max-w-[42vw] truncate text-sm font-extrabold sm:max-w-lg">{{ exam.test.title }}</h1>
        </div>
        <div class="ml-auto flex items-center gap-2 sm:gap-3">
          <span v-if="syncInProgress" class="hidden items-center gap-1 text-[10px] font-bold text-black/35 sm:flex"><el-icon class="is-loading"><RefreshRight /></el-icon> Syncing</span>
          <button type="button" class="hidden h-10 w-10 place-items-center rounded-xl border border-black/10 text-black/50 hover:bg-black/5 sm:grid" aria-label="Toggle full screen" @click="enterFullScreen"><el-icon><FullScreen /></el-icon></button>
          <button type="button" class="grid h-10 w-10 place-items-center rounded-xl border border-black/10 text-black/50 lg:hidden" aria-label="Open question navigator" @click="mobileNavigator = true"><el-icon><Grid /></el-icon></button>
          <div class="flex min-w-[104px] items-center justify-center gap-2 rounded-xl px-3 py-2 font-mono text-lg font-black tabular-nums sm:min-w-[120px]" :class="urgentTime ? 'bg-cinnabar text-white animate-pulse' : 'bg-ink text-white'">
            <el-icon><Clock /></el-icon>{{ timeText }}
          </div>
        </div>
      </header>

      <div class="flex min-h-0">
        <div class="hidden w-[280px] shrink-0 lg:block"><QuestionNavigator :questions="exam.questions" :current-index="currentIndex" :answers="exam.answers" :save-states="exam.saveStates" @select="selectQuestion" /></div>
        <main ref="contentPane" class="min-w-0 flex-1 overflow-y-auto">
          <div class="sticky top-0 z-10 h-1 bg-black/[0.06]"><div class="h-full bg-cinnabar transition-[width] duration-300" :style="{ width: `${progress}%` }" /></div>
          <div class="mx-auto w-full max-w-[940px] px-4 py-7 sm:px-8 sm:py-10 lg:px-12">
            <div class="mb-4 flex min-h-6 items-center justify-end text-[11px] font-bold">
              <span v-if="saveState === 'saving'" class="flex items-center gap-1.5 text-black/40"><el-icon class="is-loading"><Loading /></el-icon> Saving answer…</span>
              <span v-else-if="saveState === 'saved'" class="flex items-center gap-1.5 text-jade"><el-icon><Check /></el-icon> Answer saved</span>
              <button v-else-if="saveState === 'error'" type="button" class="flex items-center gap-1.5 text-cinnabar" @click="retryCurrent"><el-icon><Warning /></el-icon> Not saved · retry</button>
            </div>
            <section class="rounded-[1.4rem] border border-black/10 bg-[#fbfaf7] p-5 shadow-[0_16px_50px_rgba(29,38,35,.06)] sm:p-8 lg:p-10">
              <RestrictedAudioPlayer
                v-if="sharedAudioQuestion"
                v-show="currentQuestion.section === 'LISTENING'"
                key="shared-listening-audio"
                class="mb-7"
                :url="sharedAudioQuestion.audioUrl"
                :attempt-id="exam.attemptId"
                :question-id="sharedAudioQuestion.id"
                :play-limit="sharedAudioQuestion.audioPlayLimit || exam.test.audioPlayLimit"
                :plays-used="sharedAudioQuestion.audioPlaysUsed"
                @usage="exam.updateAudioUsage(sharedAudioQuestion.id, $event)"
              />
              <RestrictedAudioPlayer
                v-else-if="currentQuestion.audioUrl"
                :key="`audio-${currentQuestion.audioUrl}`"
                class="mb-7"
                :url="currentQuestion.audioUrl"
                :attempt-id="exam.attemptId"
                :question-id="currentQuestion.id"
                :play-limit="currentQuestion.audioPlayLimit || exam.test.audioPlayLimit"
                :plays-used="currentQuestion.audioPlaysUsed"
                @usage="exam.updateAudioUsage(currentQuestion.id, $event)"
              />
              <QuestionRenderer :key="currentQuestion.id" :question="currentQuestion" :model-value="currentAnswer" @answer="stageAnswer" />
            </section>
          </div>
        </main>
      </div>

      <footer class="relative z-20 border-t border-black/10 bg-white px-3 py-3 shadow-[0_-5px_20px_rgba(29,38,35,.04)] sm:px-5">
        <div class="ml-auto flex max-w-[940px] items-center justify-between gap-3 lg:mr-[calc((100vw-280px-940px)/2)] lg:w-[calc(100%-280px)] lg:max-w-[940px]">
          <el-button :disabled="currentIndex === 0 || exam.submitting" class="!h-11" @click="move(-1)"><el-icon class="mr-1"><ArrowLeft /></el-icon><span class="hidden sm:inline">Previous</span></el-button>
          <span class="hidden text-xs font-bold text-black/40 sm:block">{{ exam.answeredCount }} of {{ exam.questions.length }} answered</span>
          <div class="ml-auto flex gap-2">
            <el-button v-if="currentIndex < exam.questions.length - 1" type="primary" class="!h-11" :disabled="exam.submitting" @click="move(1)">Next <el-icon class="ml-1"><ArrowRight /></el-icon></el-button>
            <el-button v-else type="primary" class="!h-11" :loading="exam.submitting || automaticSubmission" @click="performSubmit(false)">Submit exam <el-icon class="ml-1"><Check /></el-icon></el-button>
            <el-button v-if="currentIndex < exam.questions.length - 1" class="!h-11 !border-cinnabar/20 !text-cinnabar" :disabled="exam.submitting" @click="performSubmit(false)"><span class="hidden sm:inline">Submit</span><el-icon class="sm:ml-1"><Check /></el-icon></el-button>
          </div>
        </div>
      </footer>

      <el-drawer v-model="mobileNavigator" direction="ltr" size="min(88vw, 340px)" :with-header="false" class="exam-drawer">
        <QuestionNavigator :questions="exam.questions" :current-index="currentIndex" :answers="exam.answers" :save-states="exam.saveStates" @select="selectQuestion" />
      </el-drawer>
    </div>
  </div>
</template>

<style scoped>
:deep(.exam-drawer .el-drawer__body),
:deep(.el-drawer__body) { padding: 0; }
@media (max-width: 639px) {
  :deep(.el-button) { padding-inline: 12px; }
}
</style>
