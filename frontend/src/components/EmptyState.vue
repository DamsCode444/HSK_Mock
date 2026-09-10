<script setup>
import { Collection } from '@element-plus/icons-vue'

defineProps({
  title: { type: String, default: 'Nothing here yet' },
  description: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})
</script>

<template>
  <div
    class="empty-state"
    :class="{ 'empty-state--compact': compact }"
    role="status"
    aria-live="polite"
  >
    <div class="relative z-10 max-w-lg">
      <span class="empty-state__icon" aria-hidden="true">
        <slot name="icon"><el-icon :size="24"><Collection /></el-icon></slot>
      </span>
      <h3 class="mt-5 font-serif text-xl font-bold tracking-tight sm:text-2xl">{{ title }}</h3>
      <p v-if="description" class="mx-auto mt-2.5 max-w-md text-sm leading-6 text-black/55">{{ description }}</p>
      <div v-if="$slots.default" class="mt-6 flex flex-wrap justify-center gap-3"><slot /></div>
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  position: relative;
  display: grid;
  min-height: 16rem;
  place-items: center;
  overflow: hidden;
  border: 1px dashed rgba(23, 33, 30, 0.18);
  border-radius: var(--radius-lg);
  background:
    radial-gradient(circle at 50% 0%, rgba(201, 148, 62, 0.1), transparent 12rem),
    rgba(255, 255, 255, 0.48);
  padding: 3rem 1.5rem;
  text-align: center;
}

.empty-state::before,
.empty-state::after {
  position: absolute;
  border: 1px solid rgba(23, 33, 30, 0.045);
  border-radius: 999px;
  content: '';
}

.empty-state::before {
  width: 13rem;
  height: 13rem;
}

.empty-state::after {
  width: 18rem;
  height: 18rem;
}

.empty-state--compact {
  min-height: 12rem;
  padding-block: 2rem;
}

.empty-state__icon {
  display: grid;
  width: 3.5rem;
  height: 3.5rem;
  margin-inline: auto;
  place-items: center;
  border: 1px solid rgba(31, 106, 87, 0.1);
  border-radius: 1rem;
  color: var(--jade);
  background: rgba(31, 106, 87, 0.08);
  box-shadow: 0 8px 24px rgba(31, 106, 87, 0.08);
}
</style>
