<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], default: '—' },
  hint: { type: String, default: '' },
  tone: { type: String, default: 'jade' },
})
</script>

<template>
  <article class="surface relative overflow-hidden p-5">
    <span
      class="absolute right-5 top-5 h-2.5 w-2.5 rounded-full"
      :class="tone === 'red' ? 'bg-cinnabar' : tone === 'gold' ? 'bg-gold' : 'bg-jade'"
    />
    <p class="text-xs font-extrabold uppercase tracking-[0.14em] text-black/45">{{ label }}</p>
    <p class="mt-3 text-3xl font-black tracking-tight">{{ value }}</p>
    <p v-if="hint" class="mt-1 text-sm text-black/50">{{ hint }}</p>
  </article>
</template>
