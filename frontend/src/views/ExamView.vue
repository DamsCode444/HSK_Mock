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
import { ElMessage } from 'element-plus/es/components/message/index'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
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
const questionRegion = ref(null)
const allowLeave = ref(false)
const initialising = ref(true)
const pageError = ref('')
const syncInProgress = ref(false)
const automaticSubmission = ref(false)
const confirmingSubmit = ref(false)
const isOnline = ref(typeof navigator === 'undefined' ? true : navigator.onLine)
const isFullscreen = ref(false)
const autoRetryTimer = ref(null)
const warnedAt = new Set()
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
const criticalTime = computed(() => remainingSeconds.value <= 60)
const currentSectionQuestions = computed(() => {
  const section = currentQuestion.value?.section
  return exam.questions.filter((question) => question.section === section)
})
const currentSectionIndex = computed(() => {
  const id = currentQuestion.value?.id
  const index = currentSectionQuestions.value.findIndex((question) => String(question.id) === String(id))
  return Math.max(0, index)
})
const currentSectionAnswered = computed(() =>
  currentSectionQuestions.value.filter((question) => exam.hasAnswer(exam.answers[question.id])).length,
)
const sectionProgress = computed(() => currentSectionQuestions.value.length
  ? ((currentSectionIndex.value + 1) / currentSectionQuestions.value.length) * 100
  : 0)
const keyboardOptions = computed(() => {
  const question = currentQuestion.value
  if (!question) return []
  const type = String(question.type || '').toLowerCase()
  if (['multiple_choice', 'single_choice', 'choice'].includes(type)) return question.options || []
  if (['true_false', 'boolean', 'judgement', 'judgment'].includes(type)) {
    return question.options?.length
      ? question.options
      : [{ label: 'TRUE' }, { label: 'FALSE' }]
  }
  return []
})
const autosaveLabel = computed(() => {
  if (!isOnline.value) return 'Offline · draft kept on this device'
  if (exam.failedSaveCount) return `${exam.failedSaveCount} answer${exam.failedSaveCount === 1 ? '' : 's'} not synced`
  if (exam.pendingSaveCount) return `Saving ${exam.pendingSaveCount} answer${exam.pendingSaveCount === 1 ? '' : 's'}…`
  if (exam.saveSummary === 'saved') return 'All answers saved'
  return 'Autosave ready'
})
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
  const previous = remainingSeconds.value
  remainingSeconds.value = Math.max(0, Math.ceil((deadlineMs.value - Date.now()) / 1000))
  for (const threshold of [300, 60]) {
    if (previous > threshold && remainingSeconds.value <= threshold && !warnedAt.has(threshold)) {
      warnedAt.add(threshold)
      ElMessage.warning({
        message: threshold === 60 ? 'One minute remaining.' : 'Five minutes remaining.',
        duration: 4500,
      })
    }
  }
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

async function handleOnline() {
  isOnline.value = true
  if (!exam.failedSaveCount || exam.submitting) return
  try {
    await exam.retryFailedAnswers()
    ElMessage.success('Connection restored. Your answers are synced.')
  } catch {
    // The visible autosave status continues to offer a manual retry.
  }
}

function handleOffline() {
  isOnline.value = false
}

function handleFullscreenChange() {
  isFullscreen.value = Boolean(document.fullscreenElement)
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
  questionRegion.value?.focus({ preventScroll: true })
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

async function retryAllFailed() {
  try {
    await exam.retryFailedAnswers()
    ElMessage.success('All answers are synced.')
  } catch (error) {
    ElMessage.error(errorMessage(error, 'Some answers still could not be synced.'))
  }
}

function handleKeyboard(event) {
  if (initialising.value || pageError.value || exam.submitting || automaticSubmission.value) return
  if (event.defaultPrevented || event.isComposing || event.repeat || event.ctrlKey || event.metaKey || event.altKey) return
  if (document.querySelector('[role="dialog"]')) return

  const target = event.target instanceof Element ? event.target : null
  if (target?.closest('input, textarea, select, button, a, [contenteditable="true"], [role="slider"], [role="radio"], [data-exam-shortcuts="off"]')) return

  if (event.key === 'ArrowLeft' && currentIndex.value > 0) {
    event.preventDefault()
    move(-1)
    return
  }
  if (event.key === 'ArrowRight' && currentIndex.value < exam.questions.length - 1) {
    event.preventDefault()
    move(1)
    return
  }

  const key = event.key.toUpperCase()
  const numberedIndex = /^\d$/.test(key) ? Number(key) - 1 : -1
  const option = keyboardOptions.value.find(
    (item) => String(item.label ?? '').toUpperCase() === key,
  ) || (numberedIndex >= 0 ? keyboardOptions.value[numberedIndex] : null)
  if (!option) return
  event.preventDefault()
  stageAnswer({ value: option.label, immediate: true })
}

async function performSubmit(isAutomatic = false) {
  if (exam.submitting || automaticSubmission.value) return
  if (!isAutomatic) {
    if (confirmingSubmit.value) return
    confirmingSubmit.value = true
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
    } finally {
      confirmingSubmit.value = false
    }
    if (exam.submitting || automaticSubmission.value) return
  } else if (confirmingSubmit.value) {
    ElMessageBox.close()
  }

  automaticSubmission.value = isAutomatic
  try {
    await flushPendingText()
    if (exam.failedSaveCount) {
      if (isAutomatic) await Promise.allSettled([exam.retryFailedAnswers()])
      else await exam.retryFailedAnswers()
    }
    await exam.submitExam({ allowUnsaved: isAutomatic })
    allowLeave.value = true
    clearTimeout(autoRetryTimer.value)
    ElMessage.success(isAutomatic ? 'Time is up. Your answers were submitted.' : 'Exam submitted successfully.')
    router.replace(`/results/${exam.attemptId}`)
  } catch (error) {
    if (isAutomatic || remainingSeconds.value <= 0) {
      ElMessage.error({ message: 'Time is up. Reconnecting to submit your answers…', duration: 4500 })
      clearTimeout(autoRetryTimer.value)
      automaticSubmission.value = true
      autoRetryTimer.value = setTimeout(() => {
        automaticSubmission.value = false
        performSubmit(true)
      }, 5000)
    } else {
      automaticSubmission.value = false
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

async function enterFullScreen() {
  try {
    if (!document.fullscreenElement) await document.documentElement.requestFullscreen?.()
    else await document.exitFullscreen?.()
  } catch {
    ElMessage.info('Full screen is unavailable in this browser window.')
  }
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
    document.addEventListener('fullscreenchange', handleFullscreenChange)
    window.addEventListener('beforeunload', beforeUnload)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    window.addEventListener('keydown', handleKeyboard)
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
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
  window.removeEventListener('beforeunload', beforeUnload)
  window.removeEventListener('online', handleOnline)
  window.removeEventListener('offline', handleOffline)
  window.removeEventListener('keydown', handleKeyboard)
  if (document.fullscreenElement) document.exitFullscreen?.().catch(() => undefined)
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
      <header class="relative z-30 border-b border-black/10 bg-white shadow-sm">
        <div class="flex min-h-[68px] items-center px-3 sm:px-5">
          <button type="button" class="mr-2 grid h-10 w-10 shrink-0 place-items-center rounded-xl text-black/55 transition hover:bg-black/5 hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cinnabar" aria-label="Leave exam" @click="requestExit">
            <el-icon :size="20"><Close /></el-icon>
          </button>
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <span class="rounded-md bg-cinnabar px-2 py-1 text-[10px] font-black uppercase tracking-wider text-white">{{ exam.test.levelLabel }}</span>
              <span class="hidden text-[10px] font-black uppercase tracking-wider text-black/35 sm:inline">{{ exam.test.testCode }}</span>
            </div>
            <h1 class="mt-1 max-w-[34vw] truncate text-sm font-extrabold sm:max-w-md xl:max-w-xl">{{ exam.test.title }}</h1>
          </div>

          <div class="ml-auto flex items-center gap-2 sm:gap-3">
            <button
              v-if="exam.failedSaveCount"
              type="button"
              class="hidden items-center gap-1.5 rounded-lg bg-red-50 px-2.5 py-2 text-[11px] font-bold text-cinnabar transition hover:bg-red-100 md:flex"
              @click="retryAllFailed"
            ><el-icon><Warning /></el-icon>{{ autosaveLabel }} · retry</button>
            <span v-else class="hidden items-center gap-1.5 text-[11px] font-bold md:flex" :class="isOnline ? 'text-black/40' : 'text-[#9a6a20]'" role="status">
              <el-icon v-if="exam.pendingSaveCount || syncInProgress" class="is-loading"><RefreshRight /></el-icon>
              <el-icon v-else><Check /></el-icon>
              {{ autosaveLabel }}
            </span>
            <button
              type="button"
              class="hidden h-10 w-10 place-items-center rounded-xl border border-black/10 text-black/50 transition hover:border-jade/30 hover:bg-jade/5 hover:text-jade sm:grid"
              :class="isFullscreen ? 'border-jade/30 bg-jade/5 text-jade' : ''"
              :aria-label="isFullscreen ? 'Exit full screen' : 'Enter full screen'"
              :aria-pressed="isFullscreen"
              @click="enterFullScreen"
            ><el-icon><FullScreen /></el-icon></button>
            <button
              type="button"
              class="relative grid h-10 w-10 place-items-center rounded-xl border border-black/10 text-black/50 lg:hidden"
              aria-label="Open question navigator"
              :aria-expanded="mobileNavigator"
              @click="mobileNavigator = true"
            >
              <el-icon><Grid /></el-icon>
              <span v-if="unansweredCount" class="absolute -right-1.5 -top-1.5 min-w-5 rounded-full bg-gold px-1 text-center text-[9px] font-black leading-5 text-ink">{{ unansweredCount }}</span>
            </button>
            <div
              class="exam-timer flex min-w-[100px] items-center justify-center gap-2 rounded-xl px-2.5 py-2 font-mono text-base font-black tabular-nums text-white sm:min-w-[122px] sm:px-3 sm:text-lg"
              :class="criticalTime ? 'exam-timer--critical bg-cinnabar' : urgentTime ? 'bg-[#9f3025]' : 'bg-ink'"
              role="timer"
              :aria-label="`${timeText} remaining`"
            ><el-icon><Clock /></el-icon>{{ timeText }}</div>
          </div>
        </div>
        <div class="h-1 bg-black/[0.06]" role="progressbar" aria-label="Overall exam position" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="Math.round(progress)">
          <div class="h-full bg-cinnabar transition-[width] duration-300" :style="{ width: `${progress}%` }" />
        </div>
      </header>

      <div class="flex min-h-0">
        <div class="hidden w-[300px] shrink-0 lg:block">
          <QuestionNavigator :questions="exam.questions" :current-index="currentIndex" :answers="exam.answers" :save-states="exam.saveStates" @select="selectQuestion" />
        </div>
        <main ref="contentPane" class="min-w-0 flex-1 overflow-y-auto bg-[#efede7]">
          <div class="sticky top-0 z-20 border-b border-black/[0.07] bg-[#f8f6f1]/95 backdrop-blur-md">
            <div class="mx-auto flex min-h-12 w-full max-w-[1180px] items-center gap-3 px-4 sm:px-8">
              <span class="rounded-md bg-jade/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.13em] text-jade">{{ currentQuestion.section }}</span>
              <div class="hidden min-w-[150px] max-w-xs flex-1 sm:block">
                <div class="mb-1 flex justify-between text-[9px] font-bold uppercase tracking-wider text-black/35">
                  <span>Section progress</span><span>{{ currentSectionIndex + 1 }}/{{ currentSectionQuestions.length }}</span>
                </div>
                <div class="h-1 overflow-hidden rounded-full bg-black/10" role="progressbar" :aria-label="`${currentQuestion.section} progress`" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="Math.round(sectionProgress)">
                  <div class="h-full rounded-full bg-jade transition-[width] duration-300" :style="{ width: `${sectionProgress}%` }" />
                </div>
              </div>
              <span class="ml-auto text-[11px] font-bold text-black/45">{{ currentSectionAnswered }}/{{ currentSectionQuestions.length }} answered in section</span>
            </div>
          </div>

          <div class="mx-auto w-full max-w-[1180px] px-3 py-5 sm:px-8 sm:py-8 lg:px-10">
            <div class="mb-3 flex min-h-6 items-center justify-between gap-3 text-[11px] font-bold">
              <span class="hidden text-black/35 xl:inline">Keyboard: A–F or 1–6 to answer · ← → to navigate</span>
              <span class="xl:hidden" />
              <span v-if="saveState === 'saving' || saveState === 'queued'" class="flex items-center gap-1.5 text-black/40" role="status"><el-icon class="is-loading"><Loading /></el-icon> Saving this answer…</span>
              <span v-else-if="saveState === 'saved'" class="flex items-center gap-1.5 text-jade" role="status"><el-icon><Check /></el-icon> This answer is saved</span>
              <button v-else-if="saveState === 'error'" type="button" class="flex items-center gap-1.5 text-cinnabar underline-offset-2 hover:underline" @click="retryCurrent"><el-icon><Warning /></el-icon> Not synced · retry</button>
              <span v-else class="text-black/35" role="status">{{ autosaveLabel }}</span>
            </div>

            <Transition name="question" mode="out-in">
              <section
                :key="currentQuestion.id"
                ref="questionRegion"
                tabindex="-1"
                class="rounded-[1.35rem] border border-black/10 bg-[#fbfaf7] p-4 shadow-[0_16px_50px_rgba(29,38,35,.07)] outline-none sm:p-7 lg:p-9"
                :aria-label="`Question ${currentQuestion.number}`"
              >
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
                <QuestionRenderer :question="currentQuestion" :model-value="currentAnswer" @answer="stageAnswer" />
              </section>
            </Transition>
          </div>
        </main>
      </div>

      <footer class="exam-footer relative z-30 border-t border-black/10 bg-white px-3 py-3 shadow-[0_-5px_20px_rgba(29,38,35,.05)] sm:px-5 lg:pl-[320px]">
        <div class="mx-auto flex w-full max-w-[1100px] items-center gap-2 sm:gap-4">
          <el-button :disabled="currentIndex === 0 || exam.submitting || automaticSubmission" class="!h-11" aria-label="Previous question" @click="move(-1)"><el-icon class="sm:mr-1"><ArrowLeft /></el-icon><span class="hidden sm:inline">Previous</span></el-button>
          <div class="min-w-0 flex-1 text-center">
            <b class="block text-xs text-ink">Question {{ currentIndex + 1 }} of {{ exam.questions.length }}</b>
            <span class="text-[10px] font-semibold text-black/40">{{ exam.answeredCount }} answered · {{ unansweredCount }} open</span>
          </div>
          <el-button
            v-if="currentIndex < exam.questions.length - 1"
            type="primary"
            class="!h-11"
            :disabled="exam.submitting || automaticSubmission"
            @click="move(1)"
          >Next <el-icon class="ml-1"><ArrowRight /></el-icon></el-button>
          <el-button v-else type="primary" class="!h-11" :loading="exam.submitting || automaticSubmission" @click="performSubmit(false)">Review & submit <el-icon class="ml-1"><Check /></el-icon></el-button>
          <el-button v-if="currentIndex < exam.questions.length - 1" class="!hidden !h-11 !border-cinnabar/20 !text-cinnabar sm:!inline-flex" :disabled="exam.submitting || automaticSubmission" @click="performSubmit(false)">Finish exam</el-button>
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

.question-enter-active,
.question-leave-active {
  transition: opacity 160ms ease, transform 160ms ease;
}

.question-enter-from {
  opacity: 0;
  transform: translateX(8px);
}

.question-leave-to {
  opacity: 0;
  transform: translateX(-5px);
}

.exam-timer--critical {
  animation: timer-attention 1.8s ease-in-out infinite;
}

.exam-footer {
  padding-bottom: max(0.75rem, env(safe-area-inset-bottom));
}

@keyframes timer-attention {
  0%, 100% { box-shadow: 0 0 0 0 rgba(186, 59, 45, 0); }
  50% { box-shadow: 0 0 0 5px rgba(186, 59, 45, 0.14); }
}

@media (max-width: 639px) {
  :deep(.el-button) { padding-inline: 12px; }
}

@media (prefers-reduced-motion: reduce) {
  .exam-timer--critical { animation: none; }
}
</style>
