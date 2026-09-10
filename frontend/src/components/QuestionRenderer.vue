<script setup>
import { computed, ref, watch } from 'vue'
import { FullScreen, Picture, RefreshLeft, ZoomIn, ZoomOut } from '@element-plus/icons-vue'

const props = defineProps({
  question: { type: Object, required: true },
  modelValue: { type: [String, Number, Boolean, Array, Object], default: '' },
})

const emit = defineEmits(['answer'])
const orderedTokens = ref([])
const sourceZoom = ref(100)
const sourceFrame = ref(null)

const isChoice = computed(() => ['multiple_choice', 'single_choice', 'choice'].includes(props.question.type))
const isTrueFalse = computed(() => ['true_false', 'boolean', 'judgement', 'judgment'].includes(props.question.type))
const isFill = computed(() => ['fill_blank', 'fill_in_blank', 'short_answer'].includes(props.question.type))
const isOrder = computed(() => ['sentence_order', 'ordering', 'reorder'].includes(props.question.type))
const isWriting = computed(() => ['writing', 'essay', 'summary'].includes(props.question.type))
const answerText = computed(() => String(props.modelValue ?? ''))
const isSourcePage = computed(() => Boolean(props.question.pageNumber || props.question.pageText))
const compactOrder = computed(() =>
  isOrder.value &&
  Boolean(props.question.options?.length) &&
  props.question.options.every((option) => /^[A-F]$/.test(String(option.text ?? option.label ?? ''))),
)
const choiceOptions = computed(() => {
  if (props.question.options?.length) return props.question.options
  if (isTrueFalse.value) return [
    { label: 'TRUE', text: '正确 / True' },
    { label: 'FALSE', text: '错误 / False' },
  ]
  return []
})

watch(
  () => [props.question.id, props.modelValue],
  () => {
    if (!isOrder.value) return
    const value = props.modelValue
    const rawTokens = Array.isArray(value)
      ? value
      : compactOrder.value
        ? String(value || '').replaceAll(' ', '').split('').filter(Boolean)
        : String(value || '').split(' ').filter(Boolean)
    orderedTokens.value = rawTokens.map((token) => {
      if (token && typeof token === 'object') return { ...token }
      const text = String(token)
      const sourceIndex = props.question.options.findIndex(
        (option) => String(option.text ?? option.label ?? '') === text,
      )
      const source = props.question.options[sourceIndex]
      return source
        ? { ...source, text: source.text ?? source.label, _sourceIndex: sourceIndex }
        : { text, _sourceIndex: -1 }
    })
  },
  { immediate: true },
)

watch(
  () => props.question.id,
  () => {
    sourceZoom.value = isSourcePage.value ? 150 : 100
    if (sourceFrame.value) {
      sourceFrame.value.scrollTop = 0
      sourceFrame.value.scrollLeft = 0
    }
  },
  { immediate: true },
)

function serializedOrder() {
  return orderedTokens.value
    .map((item) => String(item.text ?? item.label ?? ''))
    .join(compactOrder.value ? '' : ' ')
}

function selectToken(token, index) {
  orderedTokens.value.push({ ...token, text: token.text ?? token.label, _sourceIndex: index })
  emit('answer', { value: serializedOrder(), immediate: true })
}

function removeToken(index) {
  orderedTokens.value.splice(index, 1)
  emit('answer', { value: serializedOrder(), immediate: true })
}

function usedCount(sourceIndex) {
  return orderedTokens.value.filter((item) => {
    if (item._sourceIndex >= 0) return item._sourceIndex === sourceIndex
    return item.text === props.question.options[sourceIndex]?.text
  }).length
}

function resetOrder() {
  orderedTokens.value = []
  emit('answer', { value: '', immediate: true })
}

function changeZoom(delta) {
  sourceZoom.value = Math.max(75, Math.min(250, sourceZoom.value + delta))
}

function fitSource() {
  sourceZoom.value = 100
  if (sourceFrame.value) sourceFrame.value.scrollLeft = 0
}
</script>

<template>
  <div>
    <div class="mb-6 flex flex-wrap items-center gap-2 text-xs font-black uppercase tracking-[0.13em]">
      <span class="rounded-lg bg-ink px-2.5 py-1.5 text-white">Question {{ question.number }}</span>
      <span class="rounded-lg bg-black/5 px-2.5 py-1.5 text-black/45">{{ question.section }}</span>
      <span class="rounded-lg bg-gold/15 px-2.5 py-1.5 text-[#956817]">{{ question.type.replaceAll('_', ' ') }}</span>
      <span v-if="choiceOptions.length" class="ml-auto hidden text-[10px] normal-case tracking-normal text-black/35 sm:inline">Press A–F or 1–6 to choose</span>
    </div>

    <p v-if="question.instruction" class="mb-4 rounded-xl border-l-4 border-gold bg-gold/[0.08] px-4 py-3 text-sm leading-6 text-black/65">
      {{ question.instruction }}
    </p>

    <div v-if="question.text" class="whitespace-pre-wrap font-serif text-xl font-semibold leading-9 text-ink sm:text-2xl">
      {{ question.text }}
    </div>

    <div v-if="question.imageUrl" class="source-viewer mt-5 overflow-hidden rounded-2xl border border-black/10 bg-white">
      <div class="flex flex-wrap items-center gap-2 border-b border-black/[0.07] bg-[#f7f5f0] px-3 py-2.5 sm:px-4">
        <span class="mr-auto inline-flex items-center gap-2 text-xs font-extrabold text-ink">
          <el-icon class="text-cinnabar"><Picture /></el-icon>
          Source page <span v-if="question.pageNumber" class="font-semibold text-black/40">· page {{ question.pageNumber }}</span>
        </span>
        <button type="button" class="source-tool" :disabled="sourceZoom <= 75" aria-label="Zoom source page out" @click="changeZoom(-25)"><el-icon><ZoomOut /></el-icon></button>
        <output class="min-w-[46px] text-center text-[11px] font-black tabular-nums text-black/50" aria-live="polite">{{ sourceZoom }}%</output>
        <button type="button" class="source-tool" :disabled="sourceZoom >= 250" aria-label="Zoom source page in" @click="changeZoom(25)"><el-icon><ZoomIn /></el-icon></button>
        <button type="button" class="source-tool source-tool--text" @click="fitSource">Fit page</button>
        <a :href="question.imageUrl" target="_blank" rel="noopener noreferrer" class="source-tool source-tool--text" title="Open the original page in a new tab">
          <el-icon><FullScreen /></el-icon><span class="hidden sm:inline">Full size</span>
        </a>
      </div>
      <div
        ref="sourceFrame"
        tabindex="0"
        data-exam-shortcuts="off"
        class="source-frame max-h-[min(68dvh,760px)] overflow-auto bg-[#dedbd4] p-2 shadow-inner sm:p-4"
        aria-label="Scrollable source page. Use the zoom controls above to enlarge the text."
      >
        <img
          :src="question.imageUrl"
          :alt="`Question ${question.number} source page`"
          class="mx-auto block h-auto max-w-none rounded-lg bg-white shadow-md transition-[width] duration-200"
          :style="{ width: `${sourceZoom}%` }"
          decoding="async"
        />
      </div>
      <p v-if="isSourcePage" class="border-t border-black/[0.07] px-4 py-2 text-[10px] font-semibold leading-5 text-black/40">
        Source pages open at 150% for easier reading. Scroll inside the frame or choose “Fit page” to see the whole sheet.
      </p>
    </div>

    <details v-if="question.pageText && question.pageText !== question.text" :open="!question.text" class="mt-4 rounded-xl border border-jade/15 bg-jade/[0.035] px-4 py-3 text-sm">
      <summary class="cursor-pointer font-bold text-jade">Readable text version</summary>
      <p class="mt-3 whitespace-pre-wrap font-serif text-base leading-8 text-black/70">{{ question.pageText }}</p>
      <p class="mt-3 text-[10px] font-semibold text-black/35">Automatically extracted text may contain recognition errors; use the source page as the reference.</p>
    </details>

    <div class="mt-7">
      <el-radio-group
        v-if="isChoice || isTrueFalse || (!isFill && !isOrder && !isWriting && choiceOptions.length)"
        :model-value="modelValue"
          class="!grid w-full gap-3"
          :aria-label="`Answer choices for question ${question.number}`"
        @change="emit('answer', { value: $event, immediate: true })"
      >
        <el-radio
          v-for="option in choiceOptions"
          :key="option.id ?? option.label"
          :value="option.label"
          class="option-radio !m-0 !h-auto !w-full rounded-2xl border border-black/10 bg-white/65 !px-4 !py-3.5 transition duration-150 hover:!border-jade/40 hover:!bg-jade/[0.035]"
        >
          <span class="flex items-center gap-3 whitespace-normal">
            <b class="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-black/5 text-sm">{{ option.label }}</b>
            <span class="text-base leading-7 text-ink">{{ option.text || option.label }}</span>
            <img v-if="option.imageUrl" :src="option.imageUrl" :alt="`Illustration for option ${option.label}`" loading="lazy" decoding="async" class="ml-auto max-h-24 max-w-32 rounded-lg object-contain" />
          </span>
        </el-radio>
      </el-radio-group>

      <el-input
        v-else-if="isFill"
        :model-value="answerText"
        size="large"
        clearable
        placeholder="Type your answer here…"
        @input="emit('answer', { value: $event, immediate: false })"
      />

      <div v-else-if="isOrder">
        <template v-if="question.options?.length">
          <p class="mb-3 text-sm font-semibold text-black/50">Select the parts in the correct order.</p>
          <div class="min-h-16 rounded-2xl border-2 border-dashed border-jade/20 bg-jade/[0.035] p-3">
            <div v-if="orderedTokens.length" class="flex flex-wrap gap-2">
              <button
                v-for="(token, index) in orderedTokens"
                :key="`${token.text}-${index}`"
                type="button"
                class="rounded-xl bg-jade px-3 py-2 font-serif text-base font-bold text-white shadow-sm"
                title="Remove"
                @click="removeToken(index)"
              >{{ token.text }}</button>
            </div>
            <p v-else class="py-2 text-center text-sm text-black/35">Your sentence will appear here</p>
          </div>
          <div class="mt-3 flex flex-wrap gap-2">
            <button
              v-for="(token, index) in question.options"
              :key="token.id ?? index"
              type="button"
              class="rounded-xl border border-black/10 bg-white px-3 py-2 font-serif text-base font-semibold transition hover:border-jade/30 hover:bg-jade/5 disabled:opacity-35"
              :disabled="usedCount(index) > 0"
              @click="selectToken(token, index)"
            >{{ token.text ?? token.label }}</button>
            <button v-if="orderedTokens.length" type="button" class="ml-auto inline-flex items-center gap-1 text-xs font-bold text-cinnabar" @click="resetOrder">
              <el-icon><RefreshLeft /></el-icon> Reset
            </button>
          </div>
        </template>
        <div v-else>
          <p class="mb-3 text-sm font-semibold text-black/50">Enter the label order shown on the source page (for example, CBA).</p>
          <el-input
            :model-value="answerText"
            size="large"
            clearable
            maxlength="12"
            placeholder="Enter the order"
            @input="emit('answer', { value: String($event).toUpperCase(), immediate: false })"
          />
        </div>
      </div>

      <div v-else>
        <el-input
          :model-value="answerText"
          type="textarea"
          :rows="isWriting ? 9 : 5"
          :maxlength="question.maxLength"
          show-word-limit
          resize="vertical"
          placeholder="Write your answer in Chinese…"
          @input="emit('answer', { value: $event, immediate: false })"
        />
        <p class="mt-2 text-xs leading-5 text-black/40">Chinese input methods are supported. Your response saves automatically while you write.</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
:deep(.option-radio .el-radio__label) { width: 100%; padding-left: 10px; }
:deep(.option-radio.is-checked) { border-color: rgba(34, 105, 87, 0.55) !important; background: rgba(34, 105, 87, 0.07) !important; }
:deep(.option-radio .el-radio__input.is-checked .el-radio__inner) { border-color: #226957; background: #226957; }
:deep(.option-radio:focus-within) { outline: 2px solid rgba(34, 105, 87, 0.45); outline-offset: 2px; }
:deep(.el-textarea__inner) { font-size: 1rem; line-height: 1.8; padding: 16px; }

.source-tool {
  display: inline-flex;
  min-width: 2rem;
  height: 2rem;
  align-items: center;
  justify-content: center;
  gap: 0.3rem;
  border: 1px solid rgba(29, 38, 35, 0.12);
  border-radius: 0.55rem;
  background: white;
  color: rgba(29, 38, 35, 0.68);
  transition: border-color 150ms ease, color 150ms ease, background 150ms ease;
}

.source-tool:hover:not(:disabled) {
  border-color: rgba(34, 105, 87, 0.35);
  background: rgba(34, 105, 87, 0.05);
  color: #226957;
}

.source-tool:focus-visible {
  outline: 2px solid rgba(34, 105, 87, 0.5);
  outline-offset: 2px;
}

.source-tool:disabled {
  cursor: not-allowed;
  opacity: 0.35;
}

.source-tool--text {
  padding-inline: 0.6rem;
  font-size: 0.68rem;
  font-weight: 800;
}

.source-frame:focus-visible {
  outline: 3px solid rgba(34, 105, 87, 0.48);
  outline-offset: -3px;
}

@media (max-width: 480px) {
  .source-tool--text { padding-inline: 0.45rem; }
}
</style>
