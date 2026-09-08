<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft,
  Download,
  FullScreen,
  Headset,
  Loading,
  Reading,
  Search,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import EmptyState from '../components/EmptyState.vue'
import StudyAudioPlayer from '../components/materials/StudyAudioPlayer.vue'
import { errorMessage } from '../services/http'
import {
  formatBytes,
  formatDuration,
  materialUrl,
  openMaterialUrl,
  requestMaterialAsset,
  requestMaterialBundle,
} from '../services/materials'
import { useMaterialsStore } from '../stores/materials'

const route = useRoute()
const router = useRouter()
const materials = useMaterialsStore()
const collection = ref(null)
const loading = ref(true)
const failed = ref(false)
const pdfLoading = ref(false)
const pdfUrl = ref('')
const activeMobilePane = ref('book')
const lessonFilter = ref('')
const currentTrack = ref(null)
const audioUrl = ref('')
const audioLoading = ref(false)
const downloading = ref('')
const refreshedTrackAfterError = ref(false)
let loadRequest = 0
let pdfRequest = 0
let audioRequest = 0

const book = computed(() => collection.value?.books.find((item) => String(item.id) === String(route.params.bookId)) || null)
const flatTracks = computed(() => (book.value?.lessons || []).flatMap((lesson) => lesson.tracks))
const currentTrackIndex = computed(() => flatTracks.value.findIndex((track) => track.id === currentTrack.value?.id))
const filteredLessons = computed(() => {
  const query = lessonFilter.value.trim().toLowerCase()
  if (!query) return book.value?.lessons || []
  return (book.value?.lessons || []).filter((lesson) => (
    lesson.title.toLowerCase().includes(query)
    || lesson.tracks.some((track) => track.title.toLowerCase().includes(query))
  ))
})

function progressKey(bookId) {
  return `hsk-study-progress:${bookId}`
}

async function loadPdf() {
  const request = ++pdfRequest
  const selectedBook = book.value
  pdfUrl.value = ''
  if (!selectedBook?.pdfAssetId) {
    pdfLoading.value = false
    return
  }
  pdfLoading.value = true
  try {
    const grant = await requestMaterialAsset(selectedBook.pdfAssetId, 'inline')
    if (request !== pdfRequest || book.value?.id !== selectedBook.id) return
    pdfUrl.value = materialUrl(grant.url)
  } catch (error) {
    if (request !== pdfRequest) return
    ElMessage.error(errorMessage(error, 'The PDF reader could not be opened.'))
  } finally {
    if (request === pdfRequest) pdfLoading.value = false
  }
}

function initialTrack() {
  const lessonNumber = Number(route.query.lesson)
  const trackNumber = Number(route.query.track)
  let selected = flatTracks.value.find((track) => (
    track.lessonNumber === lessonNumber && track.order === trackNumber
  ))
  if (!selected && book.value) {
    try {
      const stored = JSON.parse(localStorage.getItem(progressKey(book.value.id)) || 'null')
      selected = flatTracks.value.find((track) => track.id === stored?.trackId)
    } catch {
      // A malformed local preference is safe to ignore.
    }
  }
  return selected || null
}

async function load() {
  const request = ++loadRequest
  const slug = String(route.params.slug)
  ++pdfRequest
  ++audioRequest
  loading.value = true
  failed.value = false
  collection.value = null
  pdfUrl.value = ''
  pdfLoading.value = false
  currentTrack.value = null
  audioUrl.value = ''
  audioLoading.value = false
  lessonFilter.value = ''
  activeMobilePane.value = route.query.lesson ? 'audio' : 'book'
  try {
    const result = await materials.loadCollection(slug)
    if (request !== loadRequest) return
    collection.value = result
    if (!book.value) throw new Error('This book is not part of the selected collection.')
    if (!book.value.hasAudio) activeMobilePane.value = 'book'
    const selected = initialTrack()
    await Promise.all([
      loadPdf(),
      selected ? selectTrack(selected, { updateRoute: false }) : Promise.resolve(),
    ])
  } catch (error) {
    if (request !== loadRequest) return
    failed.value = true
    ElMessage.error(errorMessage(error, error.message || 'The study workspace could not be loaded.'))
  } finally {
    if (request === loadRequest) loading.value = false
  }
}

async function selectTrack(track, { updateRoute = true } = {}) {
  if (!track?.assetId || !book.value) return
  const request = ++audioRequest
  const selectedBookId = book.value.id
  currentTrack.value = track
  audioLoading.value = true
  audioUrl.value = ''
  refreshedTrackAfterError.value = false
  try {
    const grant = await requestMaterialAsset(track.assetId, 'inline')
    if (request !== audioRequest || book.value?.id !== selectedBookId) return
    audioUrl.value = materialUrl(grant.url)
    try {
      localStorage.setItem(progressKey(selectedBookId), JSON.stringify({
        trackId: track.id,
        lesson: track.lessonNumber,
        track: track.order,
      }))
    } catch {
      // Browser storage can be unavailable; listening still works.
    }
    if (updateRoute) {
      await router.replace({
        query: { ...route.query, lesson: track.lessonNumber, track: track.order },
      })
    }
  } catch (error) {
    if (request !== audioRequest) return
    audioUrl.value = ''
    ElMessage.error(errorMessage(error, 'This audio track could not be opened.'))
  } finally {
    if (request === audioRequest) audioLoading.value = false
  }
}

function moveTrack(offset) {
  const index = currentTrackIndex.value
  const target = flatTracks.value[index < 0 ? 0 : index + offset]
  if (target) selectTrack(target)
}

async function playbackError(message, source) {
  if (source !== audioUrl.value || audioLoading.value) return
  if (currentTrack.value && !refreshedTrackAfterError.value) {
    const request = ++audioRequest
    const trackId = currentTrack.value.id
    refreshedTrackAfterError.value = true
    audioLoading.value = true
    audioUrl.value = ''
    try {
      const grant = await requestMaterialAsset(currentTrack.value.assetId, 'inline')
      if (request !== audioRequest || currentTrack.value?.id !== trackId) return
      audioUrl.value = materialUrl(grant.url)
      return
    } catch {
      if (request !== audioRequest) return
      // Fall through to the visible error message.
    } finally {
      if (request === audioRequest) audioLoading.value = false
    }
  }
  ElMessage.error(message)
}

async function downloadTrack() {
  if (!currentTrack.value || downloading.value) return
  downloading.value = 'track'
  try {
    const grant = await requestMaterialAsset(currentTrack.value.assetId, 'attachment')
    openMaterialUrl(grant.url)
  } catch (error) {
    ElMessage.error(errorMessage(error, 'The track download could not be prepared.'))
  } finally {
    downloading.value = ''
  }
}

async function download(type) {
  const selectedBook = book.value
  if (!selectedBook || downloading.value) return
  const id = type === 'audio' ? selectedBook.audioBundleId : selectedBook.completeBundleId
  const estimatedSize = type === 'pdf'
    ? selectedBook.sizeBytes
    : type === 'audio'
      ? selectedBook.audioSizeBytes
      : Number(selectedBook.sizeBytes || 0) + Number(selectedBook.audioSizeBytes || 0)
  downloading.value = type
  if (estimatedSize >= 500 * 1024 * 1024) {
    try {
      await ElMessageBox.confirm(
        `This study pack is approximately ${formatBytes(estimatedSize)}. Continue?`,
        'Large download',
        { confirmButtonText: 'Download', cancelButtonText: 'Cancel', type: 'info' },
      )
    } catch {
      downloading.value = ''
      return
    }
  }
  try {
    const grant = type === 'pdf'
      ? await requestMaterialAsset(selectedBook.pdfAssetId, 'attachment')
      : await requestMaterialBundle(id)
    openMaterialUrl(grant.url)
  } catch (error) {
    ElMessage.error(errorMessage(error, 'The download could not be prepared.'))
  } finally {
    downloading.value = ''
  }
}

function changeBook(event) {
  const bookId = event.target.value
  router.push({ name: 'material-reader', params: { slug: route.params.slug, bookId } })
}

async function openPdfInNewTab() {
  if (!book.value?.pdfAssetId) return
  const selectedBook = book.value
  const tab = window.open('about:blank', '_blank')
  if (!tab) {
    ElMessage.info('Allow pop-ups for this site to open the PDF in another tab.')
    return
  }
  tab.opener = null
  try {
    const grant = await requestMaterialAsset(selectedBook.pdfAssetId, 'inline')
    tab.location.replace(materialUrl(grant.url))
  } catch (error) {
    tab.close()
    ElMessage.error(errorMessage(error, 'The PDF could not be opened.'))
  }
}

function lessonHasCurrent(lesson) {
  return lesson.tracks.some((track) => track.id === currentTrack.value?.id)
}

watch(
  () => `${route.params.slug}:${route.params.bookId}`,
  load,
  { immediate: true },
)

watch(() => [route.query.lesson, route.query.track], () => {
  if (loading.value) return
  const selected = initialTrack()
  if (selected && selected.id !== currentTrack.value?.id) {
    selectTrack(selected, { updateRoute: false })
  }
})

onBeforeUnmount(() => {
  ++loadRequest
  ++pdfRequest
  ++audioRequest
  audioUrl.value = ''
  pdfUrl.value = ''
})
</script>

<template>
  <div class="flex h-dvh flex-col overflow-hidden bg-[#edf0ec] text-ink">
    <header class="z-20 flex h-16 shrink-0 items-center gap-3 border-b border-black/10 bg-paper px-3 sm:px-5">
      <RouterLink
        :to="{ name: 'material-level', params: { slug: route.params.slug } }"
        class="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-black/10 hover:border-cinnabar/30 hover:text-cinnabar"
        aria-label="Back to level library"
      >
        <el-icon><ArrowLeft /></el-icon>
      </RouterLink>

      <div class="min-w-0 flex-1">
        <p class="hidden truncate text-[9px] font-black uppercase tracking-[0.16em] text-black/35 sm:block">{{ collection ? `${collection.curriculumLabel} · ${collection.title}` : 'Study library' }}</p>
        <h1 class="truncate text-sm font-extrabold sm:mt-0.5">{{ book?.title || 'Opening study workspace…' }}</h1>
      </div>

      <label v-if="collection?.books?.length > 1" class="hidden lg:block">
        <span class="sr-only">Choose book</span>
        <select :value="book?.id" class="h-10 max-w-60 rounded-xl border border-black/10 bg-white px-3 text-xs font-bold" @change="changeBook">
          <option v-for="item in collection.books" :key="item.id" :value="item.id">{{ item.title }}</option>
        </select>
      </label>

      <button type="button" class="reader-toolbar-button" :disabled="!book?.pdfAssetId" aria-label="Open PDF in a new tab" @click="openPdfInNewTab">
        <el-icon><FullScreen /></el-icon><span class="hidden sm:inline">Open PDF</span>
      </button>
      <button type="button" class="reader-toolbar-button" :disabled="!book || Boolean(downloading)" aria-label="Download PDF" @click="download('pdf')">
        <el-icon><Download /></el-icon><span class="hidden sm:inline">PDF</span>
      </button>
      <el-dropdown v-if="book?.audioBundleId" trigger="click">
        <button type="button" class="reader-toolbar-button" :disabled="Boolean(downloading)" aria-label="Download study pack">
          <el-icon><Download /></el-icon><span class="hidden sm:inline">Study pack</span>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="download('audio')">Audio ZIP · {{ formatBytes(book.audioSizeBytes) }}</el-dropdown-item>
            <el-dropdown-item @click="download('complete')">Book + audio · {{ formatBytes(book.sizeBytes + book.audioSizeBytes) }}</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </header>

    <label v-if="collection?.books?.length > 1" class="flex shrink-0 items-center gap-3 border-b border-black/10 bg-paper px-3 py-2 lg:hidden">
      <span class="shrink-0 text-xs font-bold text-black/50">Book</span>
      <select :value="book?.id" class="h-8 min-w-0 flex-1 rounded-lg border border-black/10 bg-white px-2 text-xs font-bold" aria-label="Choose book" @change="changeBook">
        <option v-for="item in collection.books" :key="item.id" :value="item.id">{{ item.title }}</option>
      </select>
    </label>

    <div v-if="book?.hasAudio" class="flex shrink-0 border-b border-black/10 bg-white p-1 md:hidden">
      <button type="button" class="mobile-pane-button" :class="activeMobilePane === 'book' && 'is-active'" @click="activeMobilePane = 'book'"><el-icon><Reading /></el-icon>Book</button>
      <button type="button" class="mobile-pane-button" :class="activeMobilePane === 'audio' && 'is-active'" @click="activeMobilePane = 'audio'"><el-icon><Headset /></el-icon>Lessons</button>
    </div>

    <div v-if="loading" class="grid min-h-0 flex-1 place-items-center">
      <div class="text-center"><el-icon class="is-loading text-cinnabar" :size="30"><Loading /></el-icon><p class="mt-3 text-sm font-bold text-black/45">Preparing your study space…</p></div>
    </div>

    <div v-else-if="failed" class="min-h-0 flex-1 overflow-auto p-5">
      <EmptyState title="This study workspace could not be opened" description="Return to the collection and choose another book.">
        <RouterLink :to="{ name: 'material-level', params: { slug: route.params.slug } }" class="font-bold text-cinnabar">Back to collection →</RouterLink>
      </EmptyState>
    </div>

    <div v-else class="grid min-h-0 flex-1" :class="book?.hasAudio && 'md:grid-cols-[minmax(0,1fr)_390px]'">
      <section class="relative min-h-0 bg-[#c8ccc8]" :class="activeMobilePane !== 'book' ? 'hidden md:block' : 'block'" aria-label="PDF reader">
        <div v-if="pdfLoading" class="absolute inset-0 z-10 grid place-items-center bg-white/70 backdrop-blur-sm"><span class="text-sm font-bold text-black/45">Loading PDF…</span></div>
        <iframe v-if="pdfUrl" :src="pdfUrl" :title="`${book.title} PDF reader`" referrerpolicy="no-referrer" class="h-full min-h-0 w-full border-0 bg-white" />
        <div v-else class="grid h-full min-h-0 place-items-center p-6 text-center">
          <div><p class="font-serif text-xl font-bold">The embedded reader is unavailable</p><button type="button" class="mt-3 text-sm font-bold text-cinnabar" @click="loadPdf">Try opening it again →</button></div>
        </div>
      </section>

      <aside v-if="book?.hasAudio" class="min-h-0 overflow-y-auto border-l border-black/10 bg-paper" :class="activeMobilePane !== 'audio' ? 'hidden md:block' : 'block'" aria-label="Lesson audio">
        <div class="sticky top-0 z-10 border-b border-black/[0.07] bg-paper/95 p-4 backdrop-blur">
          <div class="flex items-end justify-between gap-3">
            <div><p class="text-[9px] font-black uppercase tracking-[0.16em] text-cinnabar">Lesson audio</p><h2 class="mt-1 font-serif text-xl font-bold">{{ book.hasAudio ? `${book.trackCount} tracks` : 'Not supplied' }}</h2></div>
            <span v-if="book.hasAudio" class="text-[10px] font-bold text-black/38">{{ book.lessonCount }} groups</span>
          </div>
          <label v-if="book.hasAudio" class="relative mt-4 block">
            <el-icon class="absolute left-3 top-1/2 -translate-y-1/2 text-black/35"><Search /></el-icon>
            <input v-model="lessonFilter" type="search" class="h-10 w-full rounded-xl border border-black/10 bg-white pl-9 pr-3 text-xs outline-none focus:border-cinnabar/40" placeholder="Find a lesson or track" aria-label="Filter lessons and tracks">
          </label>
        </div>

        <div v-if="book.hasAudio" class="space-y-2 p-3 pb-8">
          <details
            v-for="lesson in filteredLessons"
            :key="lesson.id"
            class="lesson-group overflow-hidden rounded-xl border border-black/[0.08] bg-white/60"
            :open="lessonHasCurrent(lesson)"
          >
            <summary class="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
              <div class="min-w-0"><b class="block truncate text-sm">{{ lesson.title }}</b><span class="text-[10px] font-bold text-black/38">{{ lesson.tracks.length }} {{ lesson.tracks.length === 1 ? 'track' : 'tracks' }}</span></div>
              <span v-if="lesson.kind === 'supplemental'" class="rounded-md bg-gold/12 px-2 py-1 text-[9px] font-black uppercase tracking-wide text-[#9a6a20]">Supplement</span>
            </summary>
            <div class="border-t border-black/[0.06] p-1.5">
              <button
                v-for="track in lesson.tracks"
                :key="track.id"
                type="button"
                class="flex min-h-11 w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition"
                :class="currentTrack?.id === track.id ? 'bg-jade text-white' : 'hover:bg-black/[0.045]'"
                @click="selectTrack(track)"
              >
                <span class="grid h-7 w-7 shrink-0 place-items-center rounded-full text-[10px] font-black" :class="currentTrack?.id === track.id ? 'bg-white/15' : 'bg-jade/10 text-jade'">{{ track.order }}</span>
                <span class="min-w-0 flex-1 truncate text-xs font-bold">{{ track.title }}</span>
                <span class="font-mono text-[10px] opacity-45">{{ formatDuration(track.durationSeconds) }}</span>
              </button>
            </div>
          </details>
          <p v-if="!filteredLessons.length" class="px-3 py-10 text-center text-sm text-black/40">No lesson matches that search.</p>
        </div>
        <div v-else class="grid min-h-72 place-items-center px-7 text-center">
          <div><span class="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-black/[0.05] text-black/30"><el-icon><Headset /></el-icon></span><h3 class="mt-4 font-serif text-lg font-bold">No audio included</h3><p class="mt-2 text-xs leading-5 text-black/43">This PDF remains available to read and download, but its matching audio was not present in the supplied library.</p></div>
        </div>
      </aside>
    </div>

    <StudyAudioPlayer
      v-if="!failed && !loading && book?.hasAudio"
      class="shrink-0"
      :track="currentTrack"
      :src="audioUrl"
      :loading="audioLoading"
      :downloading="Boolean(downloading)"
      :has-previous="currentTrackIndex > 0"
      :has-next="currentTrackIndex >= 0 && currentTrackIndex < flatTracks.length - 1"
      @previous="moveTrack(-1)"
      @next="moveTrack(1)"
      @download="downloadTrack"
      @playback-error="playbackError"
      @playback-blocked="ElMessage.info"
    />
  </div>
</template>

<style scoped>
.reader-toolbar-button {
  display: inline-flex;
  height: 2.5rem;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  border: 1px solid rgba(29, 38, 35, 0.1);
  border-radius: 0.75rem;
  background: rgba(255, 255, 255, 0.62);
  padding: 0 0.75rem;
  color: rgba(29, 38, 35, 0.68);
  font-size: 0.72rem;
  font-weight: 800;
}
.reader-toolbar-button:hover:not(:disabled) { border-color: rgba(186, 59, 45, 0.35); color: #ba3b2d; }
.reader-toolbar-button:disabled { cursor: not-allowed; opacity: 0.35; }
.mobile-pane-button { display: inline-flex; height: 2.6rem; flex: 1; align-items: center; justify-content: center; gap: 0.45rem; border-radius: 0.7rem; color: rgba(29, 38, 35, 0.48); font-size: 0.75rem; font-weight: 800; }
.mobile-pane-button.is-active { background: #1d2623; color: white; }
.lesson-group summary::-webkit-details-marker { display: none; }
</style>
