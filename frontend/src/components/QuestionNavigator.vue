<script setup>
import { computed } from 'vue'
import { Check } from '@element-plus/icons-vue'

const props = defineProps({
  questions: { type: Array, required: true },
  currentIndex: { type: Number, required: true },
  answers: { type: Object, required: true },
  saveStates: { type: Object, default: () => ({}) },
})

defineEmits(['select'])

const groups = computed(() => {
  const map = new Map()
  props.questions.forEach((question, index) => {
    const key = question.section || 'QUESTIONS'
    if (!map.has(key)) map.set(key, [])
    map.get(key).push({ question, index })
  })
  return [...map.entries()].map(([name, rows]) => ({ name, rows }))
})

function answered(value) {
  return Array.isArray(value) ? value.length > 0 : value !== undefined && value !== null && String(value).trim() !== ''
}
</script>

<template>
  <aside class="flex h-full flex-col bg-[#17211e] text-white">
    <div class="border-b border-white/10 px-5 py-5">
      <p class="text-[10px] font-black uppercase tracking-[0.18em] text-white/40">Question navigator</p>
      <div class="mt-3 flex items-end justify-between">
        <strong class="font-serif text-2xl">{{ currentIndex + 1 }} <small class="text-sm font-medium text-white/35">/ {{ questions.length }}</small></strong>
        <span class="text-xs font-bold text-white/55">{{ Object.values(answers).filter(answered).length }} answered</span>
      </div>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto px-4 py-4">
      <section v-for="group in groups" :key="group.name" class="mb-5">
        <h2 class="mb-2.5 flex items-center gap-2 px-1 text-[10px] font-black uppercase tracking-[0.16em] text-white/40">
          <span class="h-1.5 w-1.5 rounded-full bg-gold" /> {{ group.name }}
        </h2>
        <div class="grid grid-cols-5 gap-2 lg:grid-cols-4 xl:grid-cols-5">
          <button
            v-for="row in group.rows"
            :key="row.question.id"
            type="button"
            class="relative grid aspect-square place-items-center rounded-lg border text-xs font-black transition"
            :class="[
              row.index === currentIndex
                ? 'border-cinnabar bg-cinnabar text-white shadow-lg shadow-black/20'
                : answered(answers[row.question.id])
                  ? 'border-jade/40 bg-jade text-white hover:border-white/40'
                  : 'border-white/10 bg-white/[0.04] text-white/65 hover:bg-white/10',
              saveStates[row.question.id] === 'error' ? '!border-amber-400' : '',
            ]"
            :aria-label="`Go to question ${row.question.number}`"
            :aria-current="row.index === currentIndex ? 'step' : undefined"
            :title="saveStates[row.question.id] === 'error' ? `Question ${row.question.number}: answer not synced` : answered(answers[row.question.id]) ? `Question ${row.question.number}: answered` : `Question ${row.question.number}: open`"
            @click="$emit('select', row.index)"
          >
            {{ row.question.number }}
            <el-icon v-if="answered(answers[row.question.id]) && row.index !== currentIndex" class="absolute -right-1 -top-1 rounded-full bg-white p-0.5 text-jade" :size="12"><Check /></el-icon>
          </button>
        </div>
      </section>
    </div>

    <div class="grid grid-cols-3 gap-2 border-t border-white/10 px-4 py-3 text-[9px] font-bold uppercase tracking-wider text-white/40">
      <span><i class="mr-1 inline-block h-2 w-2 rounded-sm bg-cinnabar" /> Current</span>
      <span><i class="mr-1 inline-block h-2 w-2 rounded-sm bg-jade" /> Answered</span>
      <span><i class="mr-1 inline-block h-2 w-2 rounded-sm border border-white/30" /> Open</span>
    </div>
  </aside>
</template>

<style scoped>
button:focus-visible { outline: 2px solid white; outline-offset: 2px; }
</style>
