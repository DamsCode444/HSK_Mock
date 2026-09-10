import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { http } from '../services/http'
import {
  answerMap,
  normalizeAttempt,
  normalizeQuestions,
  normalizeTest,
} from '../services/normalizers'

const ACTIVE_ATTEMPT_PREFIX = 'hsk_active_attempt_'
const DRAFT_PREFIX = 'hsk_attempt_draft_'

export const useExamStore = defineStore('exam', () => {
  const test = ref(null)
  const questions = ref([])
  const attempt = ref(null)
  const answers = reactive({})
  const saveStates = reactive({})
  const loading = ref(false)
  const submitting = ref(false)
  const loadError = ref('')
  const lastSavedAt = ref(null)
  const chains = new Map()
  const versions = new Map()

  const attemptId = computed(() => attempt.value?.id)
  const answeredCount = computed(() =>
    questions.value.filter((question) => hasAnswer(answers[question.id])).length,
  )
  const pendingSaveCount = computed(() =>
    Object.values(saveStates).filter((state) => state === 'saving' || state === 'queued').length,
  )
  const failedSaveCount = computed(() =>
    Object.values(saveStates).filter((state) => state === 'error').length,
  )
  const saveSummary = computed(() => {
    if (failedSaveCount.value) return 'error'
    if (pendingSaveCount.value) return 'saving'
    if (lastSavedAt.value) return 'saved'
    return 'idle'
  })

  function hasAnswer(value) {
    if (Array.isArray(value)) return value.length > 0
    return value !== undefined && value !== null && String(value).trim() !== ''
  }

  function resetState() {
    test.value = null
    questions.value = []
    attempt.value = null
    loadError.value = ''
    lastSavedAt.value = null
    chains.clear()
    versions.clear()
    Object.keys(answers).forEach((key) => delete answers[key])
    Object.keys(saveStates).forEach((key) => delete saveStates[key])
  }

  function draftKey(id = attemptId.value) {
    return `${DRAFT_PREFIX}${id}`
  }

  function readStorage(key) {
    try {
      return localStorage.getItem(key)
    } catch {
      return null
    }
  }

  function writeStorage(key, value) {
    try {
      localStorage.setItem(key, value)
    } catch {
      // The API remains authoritative when storage is unavailable or full.
    }
  }

  function removeStorage(key) {
    try {
      localStorage.removeItem(key)
    } catch {
      // Storage can be unavailable in hardened/private browsing contexts.
    }
  }

  function persistDraft() {
    if (!attemptId.value) return
    const validIds = new Set(questions.value.map((question) => String(question.id)))
    const draft = Object.fromEntries(
      Object.entries(answers).filter(([id]) => validIds.has(String(id))),
    )
    writeStorage(draftKey(), JSON.stringify(draft))
  }

  function mergeAnswers(serverAnswers) {
    const validIds = new Set(questions.value.map((question) => String(question.id)))
    const server = answerMap(serverAnswers)
    let local = {}
    try {
      const parsed = JSON.parse(readStorage(draftKey(attempt.value?.id)) || '{}')
      local = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
    } catch {
      local = {}
    }

    const pendingDrafts = []
    for (const [id, value] of Object.entries(server)) {
      if (!validIds.has(String(id))) continue
      answers[id] = value
      saveStates[id] = 'saved'
    }
    // A local draft can contain final keystrokes made immediately before a refresh.
    // Only known question IDs are restored, then any server difference is re-saved.
    for (const [id, value] of Object.entries(local)) {
      if (!validIds.has(String(id))) continue
      answers[id] = value
      if (JSON.stringify(server[id]) !== JSON.stringify(value)) {
        saveStates[id] = 'queued'
        pendingDrafts.push([id, value])
      }
    }
    return pendingDrafts
  }

  function mergeAudioUsage(audioPlays = []) {
    for (const row of audioPlays || []) {
      const questionId = row.question_id ?? row.questionId
      const used = Number(row.play_count ?? row.plays_used ?? 0)
      updateAudioUsage(questionId, used)
    }
  }

  async function recoverOrStart(testId) {
    const storageKey = `${ACTIVE_ATTEMPT_PREFIX}${testId}`
    const savedId = readStorage(storageKey)
    if (savedId) {
      try {
        const { data } = await http.get(`/attempts/${savedId}`)
        const recovered = normalizeAttempt(data)
        if (['in_progress', 'active', 'started'].includes(recovered.status)) {
          attempt.value = recovered
          const pendingDrafts = mergeAnswers(recovered.answers)
          mergeAudioUsage(recovered.audioPlays)
          await Promise.allSettled(
            pendingDrafts.map(([questionId, value]) => saveAnswer(questionId, value)),
          )
          return recovered
        }
      } catch {
        // A missing, expired, or submitted attempt is replaced below.
      }
      removeStorage(storageKey)
    }

    const { data } = await http.post(`/tests/${testId}/start`)
    attempt.value = normalizeAttempt(data)
    if (!attempt.value.id) throw new Error('The server did not return an attempt ID.')
    writeStorage(storageKey, String(attempt.value.id))
    const pendingDrafts = mergeAnswers(attempt.value.answers)
    mergeAudioUsage(attempt.value.audioPlays)
    await Promise.allSettled(
      pendingDrafts.map(([questionId, value]) => saveAnswer(questionId, value)),
    )
    return attempt.value
  }

  async function loadExam(testId) {
    resetState()
    loading.value = true
    try {
      const [testResponse, questionsResponse] = await Promise.all([
        http.get(`/tests/${testId}`),
        http.get(`/tests/${testId}/questions`),
      ])
      test.value = normalizeTest(testResponse.data?.test ?? testResponse.data)
      questions.value = normalizeQuestions(questionsResponse.data)
      if (!questions.value.length) throw new Error('This test has no imported questions yet.')
      await recoverOrStart(testId)
      return attempt.value
    } catch (error) {
      loadError.value = error?.response?.data?.detail || error.message || 'Could not load this exam.'
      throw error
    } finally {
      loading.value = false
    }
  }

  async function syncAttempt() {
    if (!attemptId.value || submitting.value) return attempt.value
    const { data } = await http.get(`/attempts/${attemptId.value}`)
    const latest = normalizeAttempt(data)
    attempt.value = { ...attempt.value, ...latest }
    mergeAudioUsage(latest.audioPlays)
    return attempt.value
  }

  function saveAnswer(questionId, userAnswer) {
    if (!attemptId.value || questionId === undefined || questionId === null) return Promise.resolve()
    const currentAttemptId = attemptId.value
    answers[questionId] = userAnswer
    saveStates[questionId] = 'saving'
    persistDraft()

    const version = (versions.get(questionId) || 0) + 1
    versions.set(questionId, version)
    const previous = chains.get(questionId) || Promise.resolve()
    const request = previous
      .catch(() => undefined)
      .then(() =>
        http.put(`/attempts/${currentAttemptId}/answers/${questionId}`, {
          user_answer: userAnswer,
        }),
      )
      .then(({ data }) => {
        if (attemptId.value === currentAttemptId && versions.get(questionId) === version) {
          saveStates[questionId] = 'saved'
          lastSavedAt.value = data?.saved_at || new Date().toISOString()
        }
      })
      .catch((error) => {
        if (attemptId.value === currentAttemptId && versions.get(questionId) === version) {
          saveStates[questionId] = 'error'
        }
        throw error
      })
      .finally(() => {
        if (chains.get(questionId) === request) chains.delete(questionId)
      })
    chains.set(questionId, request)
    return request
  }

  function stageAnswer(questionId, userAnswer) {
    answers[questionId] = userAnswer
    persistDraft()
  }

  async function retryAnswer(questionId) {
    return saveAnswer(questionId, answers[questionId])
  }

  async function retryFailedAnswers() {
    const failedIds = Object.entries(saveStates)
      .filter(([, state]) => state === 'error')
      .map(([id]) => id)
    await Promise.all(failedIds.map((id) => retryAnswer(id)))
  }

  async function flushAnswers({ allowErrors = false } = {}) {
    await Promise.allSettled([...chains.values()])
    const failed = Object.values(saveStates).some((state) => state === 'error')
    if (failed && !allowErrors) throw new Error('One or more answers have not reached the server.')
  }

  async function submitExam({ allowUnsaved = false } = {}) {
    if (!attemptId.value || submitting.value) return null
    submitting.value = true
    try {
      await flushAnswers({ allowErrors: allowUnsaved })
      const currentAttemptId = attemptId.value
      const { data } = await http.post(`/attempts/${currentAttemptId}/submit`)
      if (test.value?.id) removeStorage(`${ACTIVE_ATTEMPT_PREFIX}${test.value.id}`)
      removeStorage(draftKey(currentAttemptId))
      attempt.value = { ...attempt.value, status: 'submitted' }
      return data
    } finally {
      submitting.value = false
    }
  }

  function updateAudioUsage(questionId, used) {
    const question = questions.value.find((item) => String(item.id) === String(questionId))
    if (question) question.audioPlaysUsed = Number(used)
  }

  return {
    test,
    questions,
    attempt,
    answers,
    saveStates,
    loading,
    submitting,
    loadError,
    lastSavedAt,
    attemptId,
    answeredCount,
    pendingSaveCount,
    failedSaveCount,
    saveSummary,
    hasAnswer,
    loadExam,
    syncAttempt,
    saveAnswer,
    stageAnswer,
    retryAnswer,
    retryFailedAnswers,
    flushAnswers,
    submitExam,
    updateAudioUsage,
    resetState,
  }
})
