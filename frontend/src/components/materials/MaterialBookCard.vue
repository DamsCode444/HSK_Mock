<script setup>
import { computed } from 'vue'
import { ArrowRight, Document, Download, Headset } from '@element-plus/icons-vue'
import { formatBytes } from '../../services/materials'

const props = defineProps({
  book: { type: Object, required: true },
  collectionSlug: { type: String, required: true },
  downloading: { type: Boolean, default: false },
})

defineEmits(['download'])

const readerTarget = computed(() => ({
  name: 'material-reader',
  params: { slug: props.collectionSlug, bookId: props.book.id },
}))
</script>

<template>
  <article class="surface group overflow-hidden transition duration-200 hover:-translate-y-1 hover:shadow-xl">
    <div class="grid sm:grid-cols-[148px_1fr]">
      <div class="relative min-h-48 overflow-hidden bg-[#e8e0d1] sm:min-h-full">
        <img
          v-if="book.coverUrl"
          :src="book.coverUrl"
          :alt="`${book.title} cover`"
          class="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
        >
        <div class="absolute inset-0 bg-gradient-to-t from-black/30 via-transparent to-transparent" />
        <span v-if="book.volume" class="absolute left-3 top-3 rounded-lg bg-ink px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-white">
          Volume {{ book.volume }}
        </span>
      </div>

      <div class="flex min-w-0 flex-col p-5">
        <div>
          <p class="text-[10px] font-black uppercase tracking-[0.16em] text-cinnabar">{{ book.kindLabel }}</p>
          <h3 class="mt-2 font-serif text-xl font-bold leading-tight">{{ book.title }}</h3>
          <p class="mt-2 line-clamp-2 text-xs leading-5 text-black/48">{{ book.description }}</p>
        </div>

        <div class="mt-5 flex flex-wrap gap-2 text-[11px] font-bold text-black/55">
          <span class="inline-flex items-center gap-1.5 rounded-lg bg-black/[0.045] px-2.5 py-1.5">
            <el-icon><Document /></el-icon>{{ book.pageCount }} pages
          </span>
          <span v-if="book.hasAudio" class="inline-flex items-center gap-1.5 rounded-lg bg-jade/10 px-2.5 py-1.5 text-jade">
            <el-icon><Headset /></el-icon>{{ book.trackCount }} tracks
          </span>
          <span class="rounded-lg bg-black/[0.045] px-2.5 py-1.5">{{ formatBytes(book.sizeBytes) }}</span>
        </div>

        <RouterLink
          :to="readerTarget"
          class="mt-5 inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-ink px-4 text-sm font-extrabold text-white transition hover:bg-cinnabar"
        >
          {{ book.hasAudio ? 'Read & listen' : 'Read book' }}
          <el-icon><ArrowRight /></el-icon>
        </RouterLink>

        <div class="mt-3 flex flex-wrap gap-x-4 gap-y-2 border-t border-black/[0.07] pt-3 text-xs font-bold">
          <button type="button" :disabled="downloading" class="inline-flex items-center gap-1.5 text-black/55 hover:text-cinnabar disabled:opacity-40" @click="$emit('download', book, 'pdf')">
            <el-icon><Download /></el-icon>PDF
          </button>
          <button v-if="book.audioBundleId" type="button" :disabled="downloading" class="inline-flex items-center gap-1.5 text-black/55 hover:text-jade disabled:opacity-40" @click="$emit('download', book, 'audio')">
            <el-icon><Download /></el-icon>Audio
          </button>
          <button v-if="book.completeBundleId" type="button" :disabled="downloading" class="inline-flex items-center gap-1.5 text-black/55 hover:text-cinnabar disabled:opacity-40" @click="$emit('download', book, 'complete')">
            <el-icon><Download /></el-icon>Complete pack
          </button>
        </div>
      </div>
    </div>
  </article>
</template>
