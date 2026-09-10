<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Document, Headset, Reading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import EmptyState from '../components/EmptyState.vue'
import MaterialBookCard from '../components/materials/MaterialBookCard.vue'
import { errorMessage } from '../services/http'
import {
  formatBytes,
  formatDuration,
  openMaterialUrl,
  requestMaterialAsset,
  requestMaterialBundle,
} from '../services/materials'
import { useAuthStore } from '../stores/auth'
import { useMaterialsStore } from '../stores/materials'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const materials = useMaterialsStore()
const collection = ref(null)
const loading = ref(true)
const failed = ref(false)
const activeKind = ref('all')
const activeVolume = ref('all')
const downloading = ref('')
let loadRequest = 0

const kinds = computed(() => [...new Set((collection.value?.books || []).map((book) => book.kind))])
const volumes = computed(() => [...new Set((collection.value?.books || []).map((book) => book.volume).filter(Boolean))])
const visibleBooks = computed(() => (collection.value?.books || []).filter((book) => (
  (activeKind.value === 'all' || book.kind === activeKind.value)
  && (activeVolume.value === 'all' || book.volume === activeVolume.value)
)))
const totalPages = computed(() => (collection.value?.books || []).reduce((sum, book) => sum + book.pageCount, 0))
const totalDuration = computed(() => (collection.value?.books || []).reduce(
  (sum, book) => sum + book.lessons.reduce(
    (lessonSum, lesson) => lessonSum + lesson.tracks.reduce(
      (trackSum, track) => trackSum + Number(track.durationSeconds || 0), 0,
    ), 0,
  ), 0,
))

const kindLabels = {
  all: 'All resources',
  textbook: 'Textbooks',
  workbook: 'Workbooks',
  writing: 'Writing',
  answers: 'Answers',
  vocabulary: 'Vocabulary',
}

async function load() {
  const request = ++loadRequest
  loading.value = true
  failed.value = false
  activeKind.value = 'all'
  activeVolume.value = 'all'
  try {
    const result = await materials.loadCollection(String(route.params.slug))
    if (request !== loadRequest) return
    collection.value = result
  } catch (error) {
    if (request !== loadRequest) return
    failed.value = true
    ElMessage.error(errorMessage(error, 'This material collection could not be loaded.'))
  } finally {
    if (request === loadRequest) loading.value = false
  }
}

function signInForAccess() {
  router.push({ name: 'login', query: { redirect: route.fullPath } })
}

async function download(book, type) {
  if (downloading.value) return
  if (!auth.isAuthenticated) {
    signInForAccess()
    return
  }
  const bundleId = type === 'audio' ? book.audioBundleId : book.completeBundleId
  const estimatedSize = type === 'pdf'
    ? book.sizeBytes
    : type === 'audio'
      ? book.audioSizeBytes || 0
      : Number(book.sizeBytes || 0) + Number(book.audioSizeBytes || 0)
  downloading.value = `${book.id}:${type}`
  if (estimatedSize >= 500 * 1024 * 1024) {
    try {
      await ElMessageBox.confirm(
        `This download is approximately ${formatBytes(estimatedSize)}. Continue?`,
        'Large study download',
        { confirmButtonText: 'Download', cancelButtonText: 'Cancel', type: 'info' },
      )
    } catch {
      downloading.value = ''
      return
    }
  }
  try {
    const grant = type === 'pdf'
      ? await requestMaterialAsset(book.pdfAssetId, 'attachment')
      : await requestMaterialBundle(bundleId)
    openMaterialUrl(grant.url)
  } catch (error) {
    ElMessage.error(errorMessage(error, 'The download could not be prepared.'))
  } finally {
    downloading.value = ''
  }
}

watch(() => route.params.slug, load, { immediate: true })
onBeforeUnmount(() => { ++loadRequest })
</script>

<template>
  <section class="pb-20">
    <div v-if="loading" class="page-shell py-14">
      <el-skeleton animated class="surface p-6"><template #template><el-skeleton-item variant="image" class="!h-[430px] !w-full !rounded-xl" /></template></el-skeleton>
    </div>

    <div v-else-if="failed" class="page-shell py-14">
      <EmptyState title="This collection is unavailable" description="The source may have moved or the materials index may need to be rebuilt.">
        <button type="button" class="font-bold text-cinnabar" @click="load">Try again →</button>
      </EmptyState>
    </div>

    <template v-else-if="collection">
      <header class="relative overflow-hidden border-b border-black/[0.06] bg-[#e9e3d7]">
        <div class="soft-grid absolute inset-0 opacity-60" />
        <div class="page-shell relative grid gap-8 py-10 md:grid-cols-[220px_1fr] md:items-center md:py-14">
          <div class="mx-auto w-44 overflow-hidden rounded-2xl border border-black/10 bg-white shadow-xl shadow-black/10 md:mx-0 md:w-[210px]">
            <img :src="collection.coverUrl" :alt="`${collection.title} book cover`" decoding="async" fetchpriority="high" width="420" height="560" class="aspect-[3/4] w-full object-cover">
          </div>
          <div>
            <RouterLink :to="{ name: 'materials', query: { edition: collection.standard } }" class="inline-flex items-center gap-2 text-xs font-extrabold text-black/45 hover:text-cinnabar">
              <el-icon><ArrowLeft /></el-icon>All study materials
            </RouterLink>
            <p class="mt-7 text-xs font-black uppercase tracking-[0.18em] text-cinnabar">{{ collection.curriculumLabel }}</p>
            <h1 class="display-title mt-3 text-5xl font-bold sm:text-6xl">{{ collection.title }}</h1>
            <p class="mt-4 max-w-2xl text-base leading-7 text-black/56">{{ collection.description }}</p>
            <div class="mt-7 grid max-w-2xl grid-cols-2 gap-3" :class="collection.trackCount ? 'sm:grid-cols-4' : 'sm:max-w-sm'">
              <div class="rounded-xl border border-black/[0.08] bg-white/60 p-3"><b class="block text-xl">{{ collection.bookCount }}</b><span class="text-[10px] font-black uppercase tracking-wider text-black/38">Books</span></div>
              <div class="rounded-xl border border-black/[0.08] bg-white/60 p-3"><b class="block text-xl">{{ totalPages.toLocaleString() }}</b><span class="text-[10px] font-black uppercase tracking-wider text-black/38">Pages</span></div>
              <div v-if="collection.trackCount" class="rounded-xl border border-black/[0.08] bg-white/60 p-3"><b class="block text-xl">{{ collection.trackCount }}</b><span class="text-[10px] font-black uppercase tracking-wider text-black/38">Tracks</span></div>
              <div v-if="collection.trackCount" class="rounded-xl border border-black/[0.08] bg-white/60 p-3"><b class="block text-xl">{{ formatDuration(totalDuration) || '—' }}</b><span class="text-[10px] font-black uppercase tracking-wider text-black/38">Audio</span></div>
            </div>
          </div>
        </div>
      </header>

      <div class="page-shell pt-10">
        <div v-if="collection.note" class="flex items-start gap-3 rounded-2xl border border-gold/20 bg-gold/[0.07] px-5 py-4 text-sm leading-6 text-black/58">
          <el-icon class="mt-0.5 shrink-0 text-gold" :size="18"><Reading /></el-icon>
          <p>{{ collection.note }}</p>
        </div>

        <div class="mt-10 flex flex-col gap-5 border-b border-black/10 pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p class="text-xs font-black uppercase tracking-wider text-black/38">In this collection</p>
            <h2 class="mt-1 font-serif text-3xl font-bold">Choose a study book</h2>
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="kind in ['all', ...kinds]"
              :key="kind"
              type="button"
              class="rounded-xl border px-3.5 py-2 text-xs font-extrabold transition"
              :class="activeKind === kind ? 'border-cinnabar bg-cinnabar text-white' : 'border-black/10 bg-white/60 text-black/50 hover:border-cinnabar/30'"
              @click="activeKind = kind"
            >
              {{ kindLabels[kind] || kind }}
            </button>
            <span v-if="volumes.length" class="mx-1 hidden w-px bg-black/10 sm:block" />
            <button
              v-for="volume in ['all', ...volumes]"
              v-show="volumes.length"
              :key="volume"
              type="button"
              class="rounded-xl border px-3.5 py-2 text-xs font-extrabold transition"
              :class="activeVolume === volume ? 'border-jade bg-jade text-white' : 'border-black/10 bg-white/60 text-black/50 hover:border-jade/30'"
              @click="activeVolume = volume"
            >
              {{ volume === 'all' ? 'All volumes' : `Volume ${volume}` }}
            </button>
          </div>
        </div>

        <div v-if="visibleBooks.length" class="mt-7 grid gap-6 xl:grid-cols-2">
          <MaterialBookCard
            v-for="book in visibleBooks"
            :key="book.id"
            :book="book"
            :collection-slug="collection.slug"
            :downloading="Boolean(downloading)"
            @download="download"
          />
        </div>
        <EmptyState v-else class="mt-7" title="No books match these filters" description="Choose a different resource type or volume." />

        <div class="mt-10 grid gap-4 sm:grid-cols-2">
          <div class="rounded-2xl border border-black/[0.07] bg-white/50 p-5">
            <div class="flex items-center gap-3"><span class="grid h-10 w-10 place-items-center rounded-xl bg-cinnabar/10 text-cinnabar"><el-icon><Document /></el-icon></span><b>Browser-ready books</b></div>
            <p class="mt-3 text-sm leading-6 text-black/48">Every supplied PDF is available to read without downloading. You can still save an individual PDF for offline study.</p>
          </div>
          <div v-if="collection.trackCount" class="rounded-2xl border border-black/[0.07] bg-white/50 p-5">
            <div class="flex items-center gap-3"><span class="grid h-10 w-10 place-items-center rounded-xl bg-jade/10 text-jade"><el-icon><Headset /></el-icon></span><b>Lesson-matched listening</b></div>
            <p class="mt-3 text-sm leading-6 text-black/48">Audio is grouped by its supplied book and lesson. Supplementary final-review tracks are labeled separately.</p>
          </div>
          <div v-else class="rounded-2xl border border-black/[0.07] bg-white/50 p-5">
            <div class="flex items-center gap-3"><span class="grid h-10 w-10 place-items-center rounded-xl bg-jade/10 text-jade"><el-icon><Reading /></el-icon></span><b>Focused reading</b></div>
            <p class="mt-3 text-sm leading-6 text-black/48">Use the full-width reader or save the PDF for offline review. No audio was supplied with these resources.</p>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>
