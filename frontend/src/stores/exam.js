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
  const chains = new Map()
  const versions = new Map()

  const attemptId = computed(() => attempt.value?.id)
  const answeredCount = computed(() =>
    questions.value.filter((question) => hasAnswer(answers[question.id])).length,
  )

  function hasAnswer(value) {
    if (Array.isArray(value)) return value.length > 0
    return value !== undefined && value !== null && String(value).trim() !== ''
  }

  function resetState() {
    test.value = null
    questions.value = []
    attempt.value = null
    loadError.value = ''
    chains.clear()
    versions.clear()
    Object.keys(answers).forEach((key) => delete answers[key])
    Object.keys(saveStates).forEach((key) => delete saveStates[key])
  }

  function draftKey(id = attemptId.value) {
    return `${DRAFT_PREFIX}${id}`
  }

  function persistDraft() {
    if (!attemptId.value) return
    localStorage.setItem(draftKey(), JSON.stringify({ ...answers }))
  }

  function mergeAnswers(serverAnswers) {
    let local = {}
    try {
      local = JSON.parse(localStorage.getItem(draftKey(attempt.value?.id)) || '{}')
    } catch {
      local = {}
    }
    // The local draft may contain the final keystrokes made just before a refresh.
    Object.assign(answers, answerMap(serverAnswers), local)
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
    const savedId = localStorage.getItem(storageKey)
    if (savedId) {
      try {
        const { data } = await http.get(`/attempts/${savedId}`)
        const recovered = normalizeAttempt(data)
        if (['in_progress', 'active', 'started'].includes(recovered.status)) {
          attempt.value = recovered
          mergeAnswers(recovered.answers)
          mergeAudioUsage(recovered.audioPlays)
          return recovered
        }
      } catch {
        // A missing, expired, or submitted attempt is replaced below.
      }
      localStorage.removeItem(storageKey)
    }

    const { data } = await http.post(`/tests/${testId}/start`)
    attempt.value = normalizeAttempt(data)
    if (!attempt.value.id) throw new Error('The server did not return an attempt ID.')
    localStorage.setItem(storageKey, String(attempt.value.id))
    mergeAnswers(attempt.value.answers)
    mergeAudioUsage(attempt.value.audioPlays)
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
    answers[questionId] = userAnswer
    saveStates[questionId] = 'saving'
    persistDraft()

    const version = (versions.get(questionId) || 0) + 1
    versions.set(questionId, version)
    const previous = chains.get(questionId) || Promise.resolve()
    const request = previous
      .catch(() => undefined)
      .then(() =>
        http.put(`/attempts/${attemptId.value}/answers/${questionId}`, {
          user_answer: userAnswer,
        }),
      )
      .then(() => {
        if (versions.get(questionId) === version) saveStates[questionId] = 'saved'
      })
      .catch((error) => {
        if (versions.get(questionId) === version) saveStates[questionId] = 'error'
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

  async function flushAnswers() {
    await Promise.allSettled([...chains.values()])
    const failed = Object.values(saveStates).some((state) => state === 'error')
    if (failed) throw new Error('One or more answers have not reached the server.')
  }

  async function submitExam() {
    if (!attemptId.value || submitting.value) return null
    submitting.value = true
    try {
      await flushAnswers()
      const currentAttemptId = attemptId.value
      const { data } = await http.post(`/attempts/${currentAttemptId}/submit`)
      if (test.value?.id) localStorage.removeItem(`${ACTIVE_ATTEMPT_PREFIX}${test.value.id}`)
      localStorage.removeItem(draftKey(currentAttemptId))
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
    attemptId,
    answeredCount,
    hasAnswer,
    loadExam,
    syncAttempt,
    saveAnswer,
    stageAnswer,
    retryAnswer,
    flushAnswers,
    submitExam,
    updateAudioUsage,
    resetState,
  }
})
