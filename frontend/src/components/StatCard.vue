<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], default: '—' },
  hint: { type: String, default: '' },
  tone: {
    type: String,
    default: 'jade',
    validator: (value) => ['jade', 'gold', 'red'].includes(value),
  },
})

const toneClass = computed(() => `stat-card--${props.tone}`)
</script>

<template>
  <article class="stat-card surface" :class="toneClass" :aria-label="`${label}: ${value}`">
    <span class="stat-card__accent" aria-hidden="true" />
    <div class="flex items-start justify-between gap-4">
      <div class="min-w-0">
        <p class="text-[11px] font-extrabold uppercase tracking-[0.145em] text-black/45">{{ label }}</p>
        <p class="mt-3 text-3xl font-black tracking-[-0.045em] sm:text-[2rem]">{{ value }}</p>
      </div>
      <span v-if="$slots.icon" class="stat-card__icon" aria-hidden="true"><slot name="icon" /></span>
    </div>
    <p v-if="hint" class="mt-1.5 text-sm leading-5 text-black/50">{{ hint }}</p>
  </article>
</template>

<style scoped>
.stat-card {
  --stat-color: var(--jade);
  position: relative;
  min-height: 8.7rem;
  overflow: hidden;
  padding: 1.25rem;
  transition: transform 200ms ease, box-shadow 200ms ease, border-color 200ms ease;
}

.stat-card::after {
  position: absolute;
  right: -2.5rem;
  bottom: -3.4rem;
  width: 7rem;
  height: 7rem;
  border-radius: 999px;
  content: '';
  background: color-mix(in srgb, var(--stat-color) 8%, transparent);
}

.stat-card:hover {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--stat-color) 25%, transparent);
  box-shadow: var(--shadow-md);
}

.stat-card--gold { --stat-color: var(--gold); }
.stat-card--red { --stat-color: var(--cinnabar); }

.stat-card__accent {
  position: absolute;
  top: 1.2rem;
  right: 1.2rem;
  width: 0.6rem;
  height: 0.6rem;
  border: 2px solid color-mix(in srgb, var(--stat-color) 20%, transparent);
  border-radius: 999px;
  background: var(--stat-color);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--stat-color) 10%, transparent);
}

.stat-card__icon {
  display: grid;
  width: 2.6rem;
  height: 2.6rem;
  flex: none;
  place-items: center;
  border-radius: 0.8rem;
  color: var(--stat-color);
  background: color-mix(in srgb, var(--stat-color) 10%, transparent);
}
</style>
