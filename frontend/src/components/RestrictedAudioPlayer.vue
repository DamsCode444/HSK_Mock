<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { VideoPlay, VideoPause, Headset, Mute, Microphone } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import { http, errorMessage } from '../services/http'

const props = defineProps({
  url: { type: String, required: true },
  attemptId: { type: [String, Number], required: true },
  questionId: { type: [String, Number], required: true },
  playLimit: { type: Number, default: 1 },
  playsUsed: { type: Number, default: 0 },
})

const emit = defineEmits(['usage'])
const audio = ref(null)
const playing = ref(false)
const startedSession = ref(false)
const ended = ref(false)
const registering = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const volume = ref(0.85)
const localUsed = ref(props.playsUsed)

const remaining = computed(() => Math.max(0, props.playLimit - localUsed.value))
const progress = computed(() => (duration.value ? Math.min(100, (currentTime.value / duration.value) * 100) : 0))
const locked = computed(() => ended.value && remaining.value <= 0)

watch(() => props.playsUsed, (value) => { localUsed.value = Number(value || 0) })
watch(volume, (value) => { if (audio.value) audio.value.volume = value })

function formatTime(seconds) {
  if (!Number.isFinite(seconds)) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60).toString().padStart(2, '0')
  return `${mins}:${secs}`
}

async function registerPlay() {
  registering.value = true
  try {
    const { data } = await http.post(`/attempts/${props.attemptId}/audio-plays`, {
      question_id: props.questionId,
    })
    if (data?.allowed === false) throw new Error(data.message || 'The play limit has been reached.')
    const used = Number(data?.plays_used ?? data?.play_count ?? localUsed.value + 1)
    localUsed.value = used
    emit('usage', used)
    return true
  } catch (error) {
    ElMessage.error(errorMessage(error, 'Audio playback could not be authorised.'))
    return false
  } finally {
    registering.value = false
  }
}

async function togglePlayback() {
  if (!audio.value || registering.value) return
  if (playing.value) {
    audio.value.pause()
    return
  }

  if (!startedSession.value || ended.value) {
    if (remaining.value <= 0) {
      ElMessage.warning('This recording has reached its replay limit.')
      return
    }
    const authorised = await registerPlay()
    if (!authorised) return
    audio.value.currentTime = 0
    currentTime.value = 0
    ended.value = false
    startedSession.value = true
  }

  try {
    await audio.value.play()
  } catch {
    ElMessage.error('Your browser prevented audio playback. Please press play again.')
  }
}

function onLoaded() {
  duration.value = Number(audio.value?.duration || 0)
  if (audio.value) audio.value.volume = volume.value
}

function onTimeUpdate() {
  currentTime.value = Number(audio.value?.currentTime || 0)
}

function onEnded() {
  playing.value = false
  ended.value = true
  currentTime.value = duration.value
}

onBeforeUnmount(() => audio.value?.pause())
</script>

<template>
  <section class="overflow-hidden rounded-2xl border border-jade/15 bg-jade/[0.055]">
    <audio
      ref="audio"
      :src="url"
      preload="metadata"
      controlslist="nodownload noplaybackrate"
      @loadedmetadata="onLoaded"
      @timeupdate="onTimeUpdate"
      @play="playing = true"
      @pause="playing = false"
      @ended="onEnded"
    />
    <div class="flex items-center gap-4 p-4">
      <button
        type="button"
        class="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-jade text-white shadow-lg shadow-jade/20 transition hover:scale-105 disabled:cursor-not-allowed disabled:opacity-45"
        :disabled="registering || locked"
        :aria-label="playing ? 'Pause audio' : 'Play audio'"
        @click="togglePlayback"
      >
        <el-icon :size="22"><VideoPause v-if="playing" /><VideoPlay v-else /></el-icon>
      </button>

      <div class="min-w-0 flex-1">
        <div class="mb-2 flex items-center justify-between gap-3">
          <span class="flex items-center gap-2 text-xs font-black uppercase tracking-wider text-jade">
            <el-icon><Headset /></el-icon> Listening recording
          </span>
          <span class="text-[11px] font-bold text-black/45">
            {{ remaining }} {{ remaining === 1 ? 'play' : 'plays' }} remaining
          </span>
        </div>
        <div class="h-1.5 overflow-hidden rounded-full bg-black/10" aria-label="Audio progress">
          <div class="h-full rounded-full bg-jade transition-[width] duration-200" :style="{ width: `${progress}%` }" />
        </div>
        <div class="mt-1.5 flex justify-between text-[10px] font-bold tabular-nums text-black/35">
          <span>{{ formatTime(currentTime) }}</span><span>{{ formatTime(duration) }}</span>
        </div>
      </div>

      <div class="hidden w-24 items-center gap-2 sm:flex">
        <el-icon class="text-black/35"><Mute v-if="volume === 0" /><Microphone v-else /></el-icon>
        <el-slider v-model="volume" :min="0" :max="1" :step="0.05" :show-tooltip="false" />
      </div>
    </div>
    <p class="border-t border-jade/10 px-4 py-2 text-[11px] leading-5 text-black/45">
      Playback is recorded. Pausing does not use another play; finished recordings cannot be rewound.
    </p>
  </section>
</template>

<style scoped>
audio { display: none; }
:deep(.el-slider) { --el-slider-main-bg-color: #226957; --el-slider-runway-bg-color: rgba(29, 38, 35, 0.1); }
</style>
