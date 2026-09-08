<script setup>
import { Clock, Headset, Document, ArrowRight } from '@element-plus/icons-vue'

defineProps({
  test: { type: Object, required: true },
  busy: { type: Boolean, default: false },
})

defineEmits(['start'])
</script>

<template>
  <article class="group surface flex h-full flex-col p-5 transition duration-300 hover:-translate-y-1 hover:shadow-soft">
    <div class="flex items-start justify-between gap-4">
      <div>
        <span class="inline-flex rounded-lg bg-cinnabar/10 px-2.5 py-1 text-xs font-black uppercase tracking-wider text-cinnabar">
          {{ test.levelLabel }}
        </span>
        <h3 class="mt-3 font-serif text-xl font-bold leading-tight">{{ test.title }}</h3>
        <p class="mt-1 text-xs font-bold uppercase tracking-wider text-black/35">{{ test.testCode }}</p>
      </div>
      <span class="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-jade text-lg font-black text-white">{{ test.level }}</span>
    </div>

    <p class="mt-4 line-clamp-2 text-sm leading-6 text-black/55">{{ test.description }}</p>

    <div class="mt-5 grid grid-cols-3 gap-2 border-y border-black/[0.07] py-4 text-center text-xs">
      <span class="flex flex-col items-center gap-1 text-black/45">
        <el-icon><Clock /></el-icon><b class="text-ink">{{ test.duration }} min</b>
      </span>
      <span class="flex flex-col items-center gap-1 text-black/45">
        <el-icon><Document /></el-icon><b class="text-ink">{{ test.totalQuestions }} Qs</b>
      </span>
      <span class="flex flex-col items-center gap-1 text-black/45">
        <el-icon><Headset /></el-icon><b class="text-ink">Timed</b>
      </span>
    </div>

    <el-button class="mt-5 !h-11 !w-full" type="primary" :loading="busy" @click="$emit('start', test)">
      Start mock test <el-icon class="ml-1"><ArrowRight /></el-icon>
    </el-button>
  </article>
</template>
