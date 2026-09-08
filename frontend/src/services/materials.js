import { http, mediaUrl, unwrap } from './http'

const KIND_LABELS = {
  textbook: 'Textbook',
  workbook: 'Workbook',
  writing: 'Writing practice',
  answers: 'Answer key',
  vocabulary: 'Vocabulary',
}

function number(value, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function list(value) {
  return Array.isArray(value) ? value : []
}

function normalizeTrack(track, lesson, index) {
  const lessonNumber = number(
    track.lesson_number ?? track.lesson ?? lesson.lesson_number ?? lesson.number,
    0,
  )
  const order = number(track.order ?? track.track_number ?? track.number, index + 1)
  return {
    ...track,
    id: String(track.id ?? track.asset_id ?? `${lesson.id || lessonNumber}-track-${order}`),
    assetId: track.asset_id ?? track.assetId ?? track.id,
    title: track.title || track.label || `Track ${String(order).padStart(2, '0')}`,
    filename: track.filename || '',
    lessonNumber,
    order,
    durationSeconds: track.duration_seconds == null ? null : number(track.duration_seconds),
    sizeBytes: number(track.size_bytes),
  }
}

function normalizeLesson(lesson, index) {
  const lessonNumber = number(lesson.lesson_number ?? lesson.number, index + 1)
  const kind = lesson.kind || lesson.type || 'lesson'
  const order = number(lesson.order, index + 1)
  const normalized = {
    ...lesson,
    id: String(lesson.id ?? `lesson-${lessonNumber}`),
    number: lessonNumber,
    kind,
    order,
    title: lesson.title || lesson.label || (
      kind === 'supplemental'
        ? 'Supplementary audio'
        : `Lesson ${String(lessonNumber).padStart(2, '0')}`
    ),
  }
  normalized.tracks = list(lesson.tracks)
    .map((track, trackIndex) => normalizeTrack(track, normalized, trackIndex))
    .sort((a, b) => a.order - b.order)
  return normalized
}

function normalizeBook(book, collectionLessons = [], index = 0) {
  const kind = String(book.kind || book.type || 'textbook').toLowerCase()
  const volume = book.volume ? String(book.volume).toUpperCase() : null
  const id = String(book.id ?? book.slug ?? `book-${index + 1}`)
  const nestedLessons = list(book.lessons)
  const matchingLessons = collectionLessons.filter((lesson) => (
    String(lesson.book_id ?? lesson.bookId ?? '') === String(id)
    || (Boolean(book.slug) && String(lesson.book_slug ?? '') === String(book.slug))
  ))
  const lessons = (nestedLessons.length ? nestedLessons : matchingLessons)
    .map(normalizeLesson)
    .sort((a, b) => a.order - b.order)
  const trackCount = lessons.reduce((sum, lesson) => sum + lesson.tracks.length, 0)

  return {
    ...book,
    id,
    slug: book.slug || String(id),
    kind,
    kindLabel: KIND_LABELS[kind] || 'Study book',
    volume,
    title: book.title || `${KIND_LABELS[kind] || 'Study book'}${volume ? ` ${volume}` : ''}`,
    description: book.description || '',
    coverUrl: materialUrl(book.cover_url || book.coverUrl),
    pdfAssetId: book.pdf_asset_id ?? book.document_asset_id ?? book.pdfAssetId,
    audioBundleId: book.audio_bundle_id ?? book.audioBundleId ?? null,
    completeBundleId: book.complete_bundle_id ?? book.completeBundleId ?? null,
    pageCount: number(book.page_count ?? book.pages),
    sizeBytes: number(book.size_bytes),
    audioSizeBytes: number(book.audio_size_bytes ?? book.audioSizeBytes),
    viewable: book.viewable !== false && Boolean(
      book.pdf_asset_id ?? book.document_asset_id ?? book.pdfAssetId,
    ),
    downloadable: book.downloadable !== false,
    hasAudio: book.has_audio ?? trackCount > 0,
    lessonCount: lessons.length,
    trackCount: number(book.audio_track_count ?? book.track_count, trackCount),
    lessons,
  }
}

function normalizeCollectionSummary(collection, edition = {}) {
  const level = number(collection.level ?? collection.hsk_level)
  const standard = String(
    collection.standard ?? collection.edition ?? edition.id ?? edition.standard ?? '',
  ).replace(/^HSK\s*/i, '')
  const slug = collection.slug || collection.id || `hsk-${standard.replace('.', '-')}-level-${level}`
  const status = collection.status || (collection.available === false ? 'unavailable' : 'available')
  return {
    ...collection,
    id: collection.id ?? slug,
    slug: String(slug),
    standard,
    level,
    levelLabel: String(collection.level_label || level),
    curriculumLabel: standard === 'vocabulary' ? 'New HSK vocabulary' : `HSK ${standard}`,
    title: collection.title || `HSK ${level}`,
    description: collection.description || '',
    coverUrl: materialUrl(collection.cover_url || collection.coverUrl),
    bookCount: number(collection.book_count),
    lessonCount: number(collection.lesson_count),
    trackCount: number(collection.audio_track_count ?? collection.track_count),
    totalSizeBytes: number(collection.total_size_bytes ?? collection.size_bytes),
    status,
    available: collection.available !== false && status !== 'unavailable',
    note: collection.note || collection.availability_note || '',
  }
}

function normalizeEdition(edition, index) {
  const id = String(edition.id ?? edition.standard ?? index + 1).replace(/^HSK\s*/i, '')
  const levels = list(edition.levels || edition.collections)
    .map((collection) => normalizeCollectionSummary(collection, { ...edition, id }))
    .sort((a, b) => a.level - b.level)
  const availableLevels = list(edition.available_levels || edition.availableLevels)
    .map((level) => number(level))
    .filter(Boolean)
  return {
    ...edition,
    id,
    label: edition.label || edition.title || `HSK ${id}`,
    description: edition.description || '',
    references: list(edition.references).map((reference) => ({
      ...reference,
      assetId: reference.asset_id,
      sizeBytes: number(reference.size_bytes),
    })),
    availableLevels: availableLevels.length
      ? availableLevels
      : levels.filter((level) => level.available).map((level) => level.level),
    levels,
  }
}

export function normalizeCatalog(payload) {
  const value = unwrap(payload, ['catalog']) || {}
  let editions = list(value.editions)

  // Compatibility for a flat scanner response. The public UI still consumes
  // the edition-oriented shape exposed by the current API contract.
  if (!editions.length && Array.isArray(value.collections)) {
    const groups = new Map()
    for (const collection of value.collections) {
      const standard = String(collection.standard || collection.edition || '')
      if (!groups.has(standard)) groups.set(standard, [])
      groups.get(standard).push(collection)
    }
    editions = [...groups.entries()].map(([id, levels]) => ({ id, levels }))
  }

  const normalizedEditions = editions.map(normalizeEdition)
  const allLevels = normalizedEditions.flatMap((edition) => edition.levels)
  const calculated = {
    edition_count: normalizedEditions.length,
    collection_count: allLevels.filter((level) => level.available).length,
    book_count: allLevels.reduce((sum, level) => sum + level.bookCount, 0),
    audio_track_count: allLevels.reduce((sum, level) => sum + level.trackCount, 0),
    total_size_bytes: allLevels.reduce((sum, level) => sum + level.totalSizeBytes, 0),
  }
  return {
    editions: normalizedEditions,
    totals: { ...calculated, ...(value.totals || {}) },
  }
}

export function normalizeCollection(payload, fallbackSlug = '') {
  const value = unwrap(payload, ['collection']) || {}
  const summary = normalizeCollectionSummary({ ...value, slug: value.slug || fallbackSlug })
  const collectionLessons = list(value.lessons)
  const books = list(value.books).map((book, index) => (
    normalizeBook(book, collectionLessons, index)
  ))
  const bookTrackCount = books.reduce((sum, book) => sum + book.trackCount, 0)
  const bookLessonCount = books.reduce((sum, book) => sum + book.lessonCount, 0)
  return {
    ...summary,
    books,
    bookCount: number(value.book_count, books.length),
    lessonCount: number(value.lesson_count, bookLessonCount),
    trackCount: number(value.audio_track_count ?? value.track_count, bookTrackCount),
  }
}

export async function fetchMaterialsCatalog() {
  const { data } = await http.get('/materials/catalog')
  return normalizeCatalog(data)
}

export async function fetchMaterialCollection(slug) {
  const { data } = await http.get(`/materials/collections/${encodeURIComponent(slug)}`)
  return normalizeCollection(data, slug)
}

export async function requestMaterialAsset(assetId, disposition = 'inline') {
  if (!assetId) throw new Error('This material does not have an available file.')
  const { data } = await http.post(
    `/materials/assets/${encodeURIComponent(assetId)}/access`,
    { disposition },
  )
  return unwrap(data, ['access']) || data
}

export async function requestMaterialBundle(bundleId) {
  if (!bundleId) throw new Error('This download bundle is not available.')
  const { data } = await http.post(
    `/materials/bundles/${encodeURIComponent(bundleId)}/access`,
  )
  return unwrap(data, ['access']) || data
}

export function materialUrl(path) {
  return mediaUrl(path)
}

export function openMaterialUrl(path, { newTab = false } = {}) {
  const url = materialUrl(path)
  if (!url) return false
  if (newTab) {
    window.open(url, '_blank', 'noopener,noreferrer')
    return true
  }
  const link = document.createElement('a')
  link.href = url
  link.download = ''
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
  return true
}

export function formatBytes(bytes) {
  const value = number(bytes)
  if (!value) return 'Size unavailable'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  const amount = value / (1024 ** index)
  return `${amount >= 10 || index === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[index]}`
}

export function formatDuration(seconds) {
  const value = number(seconds)
  if (!value) return ''
  const hours = Math.floor(value / 3600)
  const minutes = Math.floor((value % 3600) / 60)
  const remainingSeconds = Math.floor(value % 60).toString().padStart(2, '0')
  return hours
    ? `${hours}:${minutes.toString().padStart(2, '0')}:${remainingSeconds}`
    : `${minutes}:${remainingSeconds}`
}
