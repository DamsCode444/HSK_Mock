import { asList, mediaUrl, unwrap } from './http'

export const LEVEL_META = [
  { level: 1, questions: 40, duration: 40, maxScore: 200, passScore: 120, sections: ['Listening', 'Reading'] },
  { level: 2, questions: 60, duration: 55, maxScore: 200, passScore: 120, sections: ['Listening', 'Reading'] },
  { level: 3, questions: 80, duration: 90, maxScore: 300, passScore: 180, sections: ['Listening', 'Reading', 'Writing'] },
  { level: 4, questions: 100, duration: 105, maxScore: 300, passScore: 180, sections: ['Listening', 'Reading', 'Writing'] },
  { level: 5, questions: 100, duration: 125, maxScore: 300, passScore: 180, sections: ['Listening', 'Reading', 'Writing'] },
  { level: 6, questions: 101, duration: 140, maxScore: 300, passScore: 180, sections: ['Listening', 'Reading', 'Writing'] },
]

export function numericLevel(value) {
  const parsed = Number(String(value ?? '').match(/\d+/)?.[0])
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1
}

export function formatLevel(value) {
  return `HSK ${numericLevel(value)}`
}

export function normalizeTest(raw = {}) {
  const level = numericLevel(raw.level ?? raw.hsk_level ?? raw.level_id)
  const defaults = LEVEL_META.find((item) => item.level === level) || LEVEL_META[0]
  return {
    ...raw,
    id: raw.id ?? raw.test_id,
    level,
    levelLabel: `HSK ${level}`,
    testCode: raw.test_code ?? raw.code ?? `Test ${raw.id ?? ''}`,
    title: raw.title || `${formatLevel(level)} Mock Test`,
    description: raw.description || 'A complete, timed HSK simulation built from an official-style test bundle.',
    duration: Number(raw.duration ?? raw.duration_minutes ?? defaults.duration),
    totalQuestions: Number(raw.total_questions ?? raw.question_count ?? defaults.questions),
    maxScore: Number(raw.max_score ?? defaults.maxScore),
    passScore: Number(raw.passing_score ?? raw.pass_score ?? defaults.passScore),
    status: String(raw.status || 'published').toLowerCase(),
    audioPlayLimit: Number(raw.audio_play_limit ?? raw.allow_replay ?? 1) || 1,
    fullAudioUrl: mediaUrl(raw.full_audio_url ?? raw.full_audio_file),
    sections: raw.sections || defaults.sections,
  }
}

export function normalizeTests(payload) {
  return asList(payload, ['tests', 'items', 'results']).map(normalizeTest)
}

function normalizeOptions(options = []) {
  if (!Array.isArray(options) && options && typeof options === 'object') {
    return Object.entries(options).map(([label, text]) => ({ label, text }))
  }
  return (options || []).map((option, index) => {
    if (typeof option === 'string') {
      return { id: `${index}`, label: String.fromCharCode(65 + index), text: option }
    }
    return {
      ...option,
      id: option.id ?? `${index}`,
      label: option.label ?? option.option_label ?? String.fromCharCode(65 + index),
      text: option.text ?? option.option_text ?? option.content ?? '',
      imageUrl: mediaUrl(option.image_url ?? option.imageUrl),
    }
  })
}

export function normalizeQuestion(raw = {}, index = 0) {
  const questionType = String(raw.question_type ?? raw.type ?? 'multiple_choice').toLowerCase()
  return {
    ...raw,
    id: raw.id ?? raw.question_id,
    number: Number(raw.number ?? raw.question_number ?? index + 1),
    section: String(raw.section ?? raw.section_type ?? 'READING').toUpperCase(),
    type: questionType,
    text: raw.question_text ?? raw.content ?? raw.prompt ?? '',
    instruction: raw.instruction ?? raw.instructions ?? '',
    pageText: raw.page_text ?? raw.extracted_text ?? '',
    pageNumber: raw.page_number ?? raw.pdf_page,
    imageUrl: mediaUrl(raw.page_image_url ?? raw.image_url ?? raw.content_image_url),
    audioUrl: mediaUrl(raw.audio_url ?? raw.audio_file),
    options: normalizeOptions(raw.options),
    audioPlayLimit: Number(raw.audio_play_limit ?? 0) || null,
    audioPlaysUsed: Number(raw.audio_plays_used ?? raw.play_count ?? 0),
    maxLength: Number(raw.max_length ?? raw.character_limit ?? 1000),
  }
}

export function normalizeQuestions(payload) {
  const value = unwrap(payload, ['questions', 'items'])
  let rows = Array.isArray(value) ? value : []
  if (!rows.length && Array.isArray(value?.sections)) {
    rows = value.sections.flatMap((section) =>
      (section.questions || []).map((question) => ({
        ...question,
        section: question.section || section.section_type || section.type || section.name,
      })),
    )
  }
  return rows
    .map(normalizeQuestion)
    .sort((a, b) => a.number - b.number)
}

export function normalizeAttempt(payload) {
  const raw = unwrap(payload, ['attempt']) || {}
  return {
    ...raw,
    id: raw.id ?? raw.attempt_id,
    status: String(raw.status || 'in_progress').toLowerCase(),
    remainingSeconds: numberOrNull(raw.remaining_seconds ?? raw.time_remaining_seconds),
    expiresAt: raw.expires_at ?? raw.deadline ?? raw.scheduled_end_time,
    startedAt: raw.started_at ?? raw.start_time ?? raw.created_at,
    answers: raw.answers || raw.saved_answers || [],
    audioPlays: raw.audio_plays || raw.audio_play_state || [],
  }
}

export function numberOrNull(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function answerMap(answerRows = []) {
  if (!Array.isArray(answerRows) && answerRows && typeof answerRows === 'object') return answerRows
  return (answerRows || []).reduce((acc, row) => {
    const id = row.question_id ?? row.questionId ?? row.id
    if (id !== undefined) acc[id] = row.user_answer ?? row.answer ?? ''
    return acc
  }, {})
}

export function normalizeResult(payload) {
  const raw = unwrap(payload, ['result']) || {}
  const sectionSource = raw.sections ?? raw.section_scores ?? raw.section_analysis ?? []
  const sections = Array.isArray(sectionSource)
    ? sectionSource.map((section) => ({
        name: String(section.name ?? section.section ?? section.section_type ?? '').toUpperCase(),
        score: Number(section.score ?? section.earned_score ?? 0),
        maxScore: Number(section.max_score ?? section.maximum ?? 100),
        correct: section.correct ?? section.correct_count,
        total: section.total ?? section.question_count,
      }))
    : Object.entries(sectionSource || {}).map(([name, section]) => ({
        name: name.toUpperCase(),
        score: Number(section?.score ?? section ?? 0),
        maxScore: Number(section?.max_score ?? 100),
        correct: section?.correct ?? section?.correct_count,
        total: section?.total ?? section?.question_count,
      }))

  const reviewRows = raw.questions ?? raw.question_review ?? raw.answers ?? []
  return {
    ...raw,
    attemptId: raw.attempt_id ?? raw.id,
    level: numericLevel(raw.level ?? raw.hsk_level ?? raw.test?.level),
    title: raw.title ?? raw.test_title ?? raw.test?.title ?? 'HSK Mock Test',
    testCode: raw.test_code ?? raw.test?.test_code,
    score: Number(raw.total_score ?? raw.score ?? 0),
    maxScore: Number(raw.max_score ?? raw.maximum_score ?? 300),
    passScore: Number(raw.passing_score ?? raw.pass_score ?? 180),
    passed: raw.passed ?? raw.is_passed ?? String(raw.result || raw.status).toLowerCase() === 'pass',
    submittedAt: raw.submitted_at ?? raw.end_time,
    durationSeconds: raw.duration_seconds ?? raw.time_spent_seconds,
    sections,
    review: Array.isArray(reviewRows)
      ? reviewRows.map((row, index) => ({
          ...normalizeQuestion(row.question || row, index),
          userAnswer: row.user_answer ?? row.answer ?? '',
          correctAnswer: row.correct_answer ?? row.question?.correct_answer ?? '',
          isCorrect: row.is_correct !== undefined
            ? row.is_correct
            : row.correct !== undefined
              ? row.correct
              : null,
          explanation: row.explanation ?? row.question?.explanation ?? '',
          earnedScore: row.score ?? row.earned_score,
        }))
      : [],
  }
}
