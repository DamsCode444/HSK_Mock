<script setup>
import { Collection } from '@element-plus/icons-vue'

defineProps({
  title: { type: String, default: 'Nothing here yet' },
  description: { type: String, default: '' },
})
</script>

<template>
  <div class="grid min-h-60 place-items-center rounded-2xl border border-dashed border-black/15 bg-white/35 px-6 py-12 text-center">
    <div>
      <span class="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-black/5 text-black/35">
        <el-icon :size="22"><Collection /></el-icon>
      </span>
      <h3 class="mt-4 font-serif text-xl font-bold">{{ title }}</h3>
      <p v-if="description" class="mx-auto mt-2 max-w-md text-sm leading-6 text-black/50">{{ description }}</p>
      <div v-if="$slots.default" class="mt-5"><slot /></div>
    </div>
  </div>
</template>
