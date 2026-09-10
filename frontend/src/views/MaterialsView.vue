<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowRight,
  Collection,
  Document,
  Download,
  Headset,
  Reading,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import EmptyState from '../components/EmptyState.vue'
import { errorMessage } from '../services/http'
import { formatBytes, formatDuration, materialUrl, openMaterialUrl, requestMaterialAsset } from '../services/materials'
import { useAuthStore } from '../stores/auth'
import { useMaterialsStore } from '../stores/materials'

const route = useRoute()
const router = useRouter()
const materials = useMaterialsStore()
const auth = useAuthStore()
const openingReference = ref('')
const loading = ref(true)
const failed = ref(false)
const selectedEditionId = computed({
  get: () => String(route.query.edition || '2.0'),
  set: (edition) => router.replace({ query: { ...route.query, edition } }),
})

const selectedEdition = computed(() => (
  materials.editions.find((edition) => edition.id === selectedEditionId.value)
  || materials.editions[0]
  || null
))

const levelSlots = computed(() => selectedEdition.value?.id === 'vocabulary'
  ? selectedEdition.value.levels
  : Array.from({ length: 6 }, (_, index) => {
  const level = index + 1
  const available = selectedEdition.value?.levels.find((item) => item.level === level)
  return available || {
    id: `${selectedEdition.value?.id || 'edition'}-${level}-unavailable`,
    level,
    levelLabel: String(level),
    available: false,
    title: `HSK ${level}`,
    note: selectedEdition.value?.id === '3.0'
      ? 'This level is not included in the supplied HSK 3.0 library.'
      : 'This level is not currently available.',
  }
}))

async function openReference(reference, disposition) {
  if (openingReference.value) return
  if (!auth.isAuthenticated) {
    router.push({ name: 'login', query: { redirect: route.fullPath } })
    return
  }
  const tab = disposition === 'inline' ? window.open('about:blank', '_blank') : null
  if (disposition === 'inline' && !tab) {
    ElMessage.info('Allow pop-ups for this site to view the chart in a new tab.')
    return
  }
  if (tab) tab.opener = null
  openingReference.value = reference.id
  try {
    const grant = await requestMaterialAsset(reference.assetId, disposition)
    if (tab) tab.location.replace(materialUrl(grant.url))
    else openMaterialUrl(grant.url)
  } catch (error) {
    if (tab) tab.close()
    ElMessage.error(errorMessage(error, 'The reference chart could not be opened.'))
  } finally {
    openingReference.value = ''
  }
}

async function load() {
  loading.value = true
  failed.value = false
  try {
    await materials.loadCatalog()
    if (!materials.editions.some((edition) => edition.id === selectedEditionId.value)) {
      selectedEditionId.value = materials.editions[0]?.id || '2.0'
    }
  } catch (error) {
    failed.value = true
    ElMessage.error(errorMessage(error, 'The study library could not be loaded.'))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <section class="soft-grid relative overflow-hidden border-b border-black/[0.06] py-16 sm:py-20">
      <div class="pointer-events-none absolute -right-24 -top-28 h-96 w-96 rounded-full bg-jade/[0.08] blur-3xl" />
      <div class="page-shell relative grid items-end gap-10 lg:grid-cols-[1fr_auto]">
        <div class="max-w-3xl">
          <span class="eyebrow">Learn before you test</span>
          <h1 class="display-title mt-5 text-5xl font-bold leading-[1.04] sm:text-6xl">
            Your complete <span class="text-cinnabar">HSK study library.</span>
          </h1>
          <p class="mt-6 max-w-2xl text-base leading-8 text-black/58 sm:text-lg">
            Read course books and vocabulary guides, study with matching lesson audio, or download resources for offline learning.
          </p>
        </div>

        <div v-if="materials.catalog" class="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:w-[460px] lg:grid-cols-2">
          <div class="rounded-2xl border border-black/[0.08] bg-white/70 p-4">
            <Document class="h-5 w-5 text-cinnabar" />
            <b class="mt-3 block text-2xl">{{ materials.totals.book_count }}</b>
            <span class="text-[10px] font-black uppercase tracking-wider text-black/38">Books</span>
          </div>
          <div class="rounded-2xl border border-black/[0.08] bg-white/70 p-4">
            <Headset class="h-5 w-5 text-jade" />
            <b class="mt-3 block text-2xl">{{ Number(materials.totals.audio_track_count || 0).toLocaleString() }}</b>
            <span class="text-[10px] font-black uppercase tracking-wider text-black/38">Audio tracks</span>
          </div>
          <div class="rounded-2xl border border-black/[0.08] bg-white/70 p-4">
            <Reading class="h-5 w-5 text-gold" />
            <b class="mt-3 block text-2xl">{{ Number(materials.totals.page_count || 0).toLocaleString() }}</b>
            <span class="text-[10px] font-black uppercase tracking-wider text-black/38">Pages</span>
          </div>
          <div class="rounded-2xl border border-black/[0.08] bg-white/70 p-4">
            <Collection class="h-5 w-5 text-ink" />
            <b class="mt-3 block text-2xl">{{ formatDuration(materials.totals.audio_duration_seconds) }}</b>
            <span class="text-[10px] font-black uppercase tracking-wider text-black/38">Listening time</span>
          </div>
        </div>
      </div>
    </section>

    <section class="py-14 sm:py-20">
      <div class="page-shell">
        <div class="flex flex-col gap-5 border-b border-black/10 pb-7 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p class="text-xs font-black uppercase tracking-[0.15em] text-black/38">Choose your study resources</p>
            <h2 class="mt-2 font-serif text-3xl font-bold">Course books & vocabulary</h2>
          </div>
          <div v-if="materials.editions.length" class="inline-flex w-full flex-wrap rounded-2xl bg-black/[0.055] p-1 sm:w-auto" role="tablist" aria-label="Study collection">
            <button
              v-for="edition in materials.editions"
              :key="edition.id"
              type="button"
              role="tab"
              :aria-selected="selectedEditionId === edition.id"
              class="flex-1 rounded-xl px-3 py-3 text-sm font-extrabold transition sm:flex-none sm:px-5"
              :class="selectedEditionId === edition.id ? 'bg-white text-cinnabar shadow-sm' : 'text-black/50 hover:text-ink'"
              @click="selectedEditionId = edition.id"
            >
              {{ edition.label }}
            </button>
          </div>
        </div>

        <div v-if="loading" class="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          <el-skeleton v-for="n in 6" :key="n" animated class="surface p-5">
            <template #template><el-skeleton-item variant="image" class="!h-64 !w-full !rounded-xl" /></template>
          </el-skeleton>
        </div>

        <EmptyState
          v-else-if="failed"
          class="mt-8"
          title="The study library is temporarily unavailable"
          description="Make sure the materials index has been generated, then try again."
        >
          <button type="button" class="font-bold text-cinnabar" @click="load">Try again →</button>
        </EmptyState>

        <template v-else-if="selectedEdition">
          <div class="mt-7 flex flex-col gap-3 rounded-2xl border border-jade/15 bg-jade/[0.055] px-5 py-4 text-sm leading-6 text-black/58 sm:flex-row sm:items-center sm:justify-between">
            <p>{{ selectedEdition.description }}</p>
            <span class="shrink-0 font-bold text-jade">{{ selectedEdition.availableLevels.length }} {{ selectedEdition.id === 'vocabulary' ? 'level groups' : 'levels' }} available</span>
          </div>

          <div v-for="reference in selectedEdition.references" :key="reference.id" class="mt-5 flex flex-col gap-4 rounded-2xl border border-black/10 bg-white/60 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 class="text-sm font-extrabold">{{ reference.title }}</h3>
              <p class="mt-1 max-w-2xl text-xs leading-5 text-black/50">{{ reference.description }}</p>
            </div>
            <div class="flex shrink-0 flex-wrap gap-3 text-xs font-bold">
              <button type="button" :disabled="Boolean(openingReference)" class="rounded-xl border border-black/10 px-4 py-2.5 hover:text-cinnabar disabled:opacity-40" @click="openReference(reference, 'inline')">View chart</button>
              <button type="button" :disabled="Boolean(openingReference)" class="inline-flex items-center gap-1.5 rounded-xl border border-black/10 px-4 py-2.5 hover:text-cinnabar disabled:opacity-40" @click="openReference(reference, 'attachment')"><el-icon><Download /></el-icon>PNG · {{ formatBytes(reference.sizeBytes) }}</button>
            </div>
          </div>

          <div class="mt-7 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            <article
              v-for="level in levelSlots"
              :key="level.id"
              class="group overflow-hidden rounded-[1.25rem] border transition duration-200"
              :class="level.available ? 'border-black/10 bg-white/75 shadow-[0_18px_60px_rgba(25,35,31,.055)] hover:-translate-y-1 hover:shadow-xl' : 'border-dashed border-black/12 bg-black/[0.018]'"
            >
              <template v-if="level.available">
                <RouterLink :to="{ name: 'material-level', params: { slug: level.slug } }" class="block">
                  <div class="relative h-64 overflow-hidden bg-[#e8e0d1]">
                    <img :src="level.coverUrl" :alt="`${selectedEdition.label} Level ${level.levelLabel} cover`" loading="lazy" decoding="async" width="420" height="560" class="h-full w-full object-cover transition duration-500 group-hover:scale-[1.035]">
                    <div class="absolute inset-0 bg-gradient-to-t from-[#151e1b]/75 via-transparent to-transparent" />
                    <div class="absolute bottom-0 left-0 right-0 flex items-end justify-between p-5 text-white">
                      <div>
                        <span class="text-[10px] font-black uppercase tracking-[0.18em] text-white/60">{{ selectedEdition.label }}</span>
                        <h3 class="mt-1 font-serif text-3xl font-bold">{{ level.levelLabel.includes('–') ? 'Levels' : 'Level' }} {{ level.levelLabel }}</h3>
                      </div>
                      <span class="grid h-11 w-11 place-items-center rounded-xl bg-white/15 backdrop-blur transition group-hover:bg-cinnabar"><el-icon><ArrowRight /></el-icon></span>
                    </div>
                  </div>
                  <div class="p-5">
                    <div class="flex flex-wrap gap-2 text-[11px] font-bold text-black/52">
                      <span class="rounded-lg bg-black/[0.045] px-2.5 py-1.5">{{ level.bookCount }} {{ level.bookCount === 1 ? 'book' : 'books' }}</span>
                      <span v-if="level.trackCount" class="rounded-lg bg-jade/10 px-2.5 py-1.5 text-jade">{{ level.trackCount }} tracks</span>
                      <span v-else class="rounded-lg bg-jade/10 px-2.5 py-1.5 text-jade">Read & download</span>
                      <span class="rounded-lg bg-black/[0.045] px-2.5 py-1.5">{{ formatBytes(level.totalSizeBytes) }}</span>
                    </div>
                    <p v-if="level.note" class="mt-4 min-h-10 text-xs leading-5 text-black/45">{{ level.note }}</p>
                    <p v-else class="mt-4 min-h-10 text-xs leading-5 text-black/45">Textbooks, workbooks, and corresponding lesson audio.</p>
                  </div>
                </RouterLink>
              </template>
              <div v-else class="flex min-h-[390px] flex-col items-center justify-center px-7 text-center">
                <span class="grid h-14 w-14 place-items-center rounded-2xl bg-black/[0.045] font-serif text-2xl font-bold text-black/28">{{ level.level }}</span>
                <h3 class="mt-5 font-serif text-xl font-bold text-black/45">Level {{ level.level }} not in library</h3>
                <p class="mt-2 text-xs leading-5 text-black/38">{{ level.note }}</p>
              </div>
            </article>
          </div>
        </template>
      </div>
    </section>

    <section class="border-y border-black/[0.06] bg-[#eee9dd] py-12">
      <div class="page-shell flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 class="font-serif text-2xl font-bold">Study access that respects your library</h2>
          <p class="mt-2 max-w-2xl text-sm leading-6 text-black/50">Catalog details are easy to browse. Reading, listening, and downloads require your signed-in account and use expiring private links.</p>
        </div>
        <RouterLink to="/#levels" class="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-xl border border-black/10 bg-white/60 px-5 text-sm font-extrabold hover:bg-white">
          Ready? Take a mock test <el-icon><ArrowRight /></el-icon>
        </RouterLink>
      </div>
    </section>
  </div>
</template>
