<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import {
  ArrowLeftBold,
  ArrowRightBold,
  Download,
  VideoPause,
  VideoPlay,
} from '@element-plus/icons-vue'
import { formatDuration } from '../../services/materials'

const props = defineProps({
  track: { type: Object, default: null },
  src: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  downloading: { type: Boolean, default: false },
  hasPrevious: { type: Boolean, default: false },
  hasNext: { type: Boolean, default: false },
})

const emit = defineEmits(['previous', 'next', 'download', 'playback-error', 'playback-blocked'])
const audio = ref(null)
const playing = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const volume = ref(0.9)
const speed = ref(1)
const continuous = ref(true)
const resumeAfterAdvance = ref(false)
const seekable = ref(false)
let sourceRequest = 0

const durationLabel = computed(() => formatDuration(duration.value || props.track?.durationSeconds))
const currentLabel = computed(() => formatDuration(currentTime.value) || '0:00')

watch(() => props.src, async (value) => {
  const request = ++sourceRequest
  resumeAfterAdvance.value ||= playing.value
  playing.value = false
  seekable.value = false
  currentTime.value = 0
  duration.value = Number(props.track?.durationSeconds || 0)
  if (!value) return
  await nextTick()
  if (request !== sourceRequest) return
  audio.value?.load()
  if (resumeAfterAdvance.value && audio.value) {
    resumeAfterAdvance.value = false
    play()
  }
})

watch(volume, (value) => {
  if (audio.value) audio.value.volume = Number(value)
})

watch(speed, (value) => {
  if (audio.value) audio.value.playbackRate = Number(value)
})

async function togglePlayback() {
  if (!audio.value || !props.src) return
  if (audio.value.paused) {
    await play()
  } else {
    audio.value.pause()
  }
}

async function play() {
  const source = props.src
  try {
    await audio.value?.play()
  } catch (error) {
    if (source !== props.src || error.name === 'AbortError') return
    if (error.name === 'NotAllowedError') {
      emit('playback-blocked', 'The track is ready. Press play to continue.')
    } else {
      emit('playback-error', 'This audio track could not be played.', source)
    }
  }
}

function mediaError() {
  if (props.src && !props.loading && audio.value?.error) {
    emit('playback-error', 'This audio track could not be loaded.', props.src)
  }
}

function seek(event) {
  if (!audio.value || !seekable.value) return
  const value = Number(event.target.value)
  audio.value.currentTime = value
  currentTime.value = value
}

function metadataLoaded() {
  duration.value = Number.isFinite(audio.value?.duration)
    ? audio.value.duration
    : Number(props.track?.durationSeconds || 0)
  if (audio.value) {
    seekable.value = audio.value.readyState > 0
    audio.value.volume = Number(volume.value)
    audio.value.playbackRate = Number(speed.value)
  }
}

function ended() {
  playing.value = false
  if (continuous.value && props.hasNext) {
    resumeAfterAdvance.value = true
    emit('next')
  }
}
</script>

<template>
  <section class="border-t border-white/10 bg-[#111a17] px-4 py-3 text-white sm:px-6" aria-label="Study audio player">
    <audio
      ref="audio"
      :src="src || undefined"
      preload="metadata"
      @play="playing = true"
      @pause="playing = false"
      @timeupdate="currentTime = audio?.currentTime || 0"
      @loadedmetadata="metadataLoaded"
      @durationchange="metadataLoaded"
      @ended="ended"
      @error="mediaError"
    />

    <div class="mx-auto grid max-w-[1500px] gap-3 lg:grid-cols-[minmax(180px,300px)_1fr_auto] lg:items-center">
      <div class="min-w-0" aria-live="polite">
        <p class="truncate text-[10px] font-black uppercase tracking-[0.16em] text-white/35">
          {{ track ? `Lesson ${String(track.lessonNumber).padStart(2, '0')}` : 'Study audio' }}
        </p>
        <p class="mt-0.5 truncate text-sm font-bold">{{ track?.title || 'Choose a track from the lesson list' }}</p>
      </div>

      <div class="flex min-w-0 items-center gap-2 sm:gap-3">
        <button type="button" class="player-icon" :disabled="!hasPrevious || loading" aria-label="Previous track" @click="$emit('previous')">
          <el-icon><ArrowLeftBold /></el-icon>
        </button>
        <button type="button" class="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-cinnabar text-white disabled:cursor-not-allowed disabled:opacity-40" :disabled="!src || loading" :aria-label="playing ? 'Pause' : 'Play'" @click="togglePlayback">
          <el-icon :size="20"><VideoPause v-if="playing" /><VideoPlay v-else /></el-icon>
        </button>
        <button type="button" class="player-icon" :disabled="!hasNext || loading" aria-label="Next track" @click="$emit('next')">
          <el-icon><ArrowRightBold /></el-icon>
        </button>
        <span class="hidden w-10 shrink-0 text-right font-mono text-[10px] text-white/50 sm:block">{{ currentLabel }}</span>
        <input
          class="audio-range min-w-0 flex-1"
          type="range"
          min="0"
          :max="Math.max(duration || track?.durationSeconds || 0, 0.01)"
          step="0.1"
          :value="currentTime"
          :disabled="!src || !seekable"
          aria-label="Audio position"
          @input="seek"
        >
        <span class="w-10 shrink-0 font-mono text-[10px] text-white/50">{{ durationLabel || '0:00' }}</span>
      </div>

      <div class="flex items-center justify-end gap-3 text-[11px] font-bold text-white/55">
        <label class="flex items-center gap-2">
          Speed
          <select v-model="speed" class="rounded-lg border border-white/10 bg-white/10 px-2 py-1.5 text-white" aria-label="Playback speed">
            <option class="text-ink" :value="0.75">0.75×</option>
            <option class="text-ink" :value="1">1×</option>
            <option class="text-ink" :value="1.25">1.25×</option>
            <option class="text-ink" :value="1.5">1.5×</option>
            <option class="text-ink" :value="2">2×</option>
          </select>
        </label>
        <label class="hidden items-center gap-2 xl:flex">
          Volume
          <input v-model="volume" class="audio-range w-20" type="range" min="0" max="1" step="0.05" aria-label="Volume">
        </label>
        <label class="flex items-center gap-1.5">
          <input v-model="continuous" type="checkbox" class="accent-[#ba3b2d]"> Auto-next
        </label>
        <button type="button" class="player-icon" :disabled="!track || downloading" aria-label="Download current track" @click="$emit('download')">
          <el-icon><Download /></el-icon>
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.player-icon {
  display: grid;
  width: 2.25rem;
  height: 2.25rem;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 0.65rem;
  color: rgba(255, 255, 255, 0.72);
  transition: color 150ms ease, background-color 150ms ease;
}
.player-icon:hover:not(:disabled) { color: white; background: rgba(255, 255, 255, 0.1); }
.player-icon:disabled { opacity: 0.28; cursor: not-allowed; }
.audio-range { accent-color: #ba3b2d; }
</style>
