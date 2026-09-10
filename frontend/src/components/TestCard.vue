<script setup>
import { computed } from 'vue'
import { ArrowRight, Clock, Document, Headset } from '@element-plus/icons-vue'

const props = defineProps({
  test: { type: Object, required: true },
  busy: { type: Boolean, default: false },
})

defineEmits(['start'])

const titleId = computed(() => `test-card-${props.test.id ?? props.test.testCode}`)
const sectionLabel = computed(() => {
  const sections = Array.isArray(props.test.sections) ? props.test.sections : []
  return sections.length ? sections.join(' · ') : 'Complete paper'
})
</script>

<template>
  <article
    class="test-card surface"
    :aria-labelledby="titleId"
    :aria-busy="busy"
  >
    <div class="test-card__wash" aria-hidden="true" />

    <div class="relative flex items-start justify-between gap-4">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <span class="level-pill">{{ test.levelLabel }}</span>
          <span class="inline-flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-[0.13em] text-black/40">
            <i class="status-dot" aria-hidden="true" /> Ready
          </span>
        </div>
        <h3 :id="titleId" class="mt-4 font-serif text-xl font-bold leading-snug tracking-tight sm:text-[1.35rem]">
          {{ test.title }}
        </h3>
        <p class="mt-1.5 truncate text-[10px] font-extrabold uppercase tracking-[0.14em] text-black/35">
          {{ test.testCode }}
        </p>
      </div>
      <span class="level-number" aria-hidden="true">{{ test.level }}</span>
    </div>

    <p class="relative mt-4 line-clamp-2 min-h-12 text-sm leading-6 text-black/55">
      {{ test.description }}
    </p>

    <p class="relative mt-4 truncate text-[11px] font-bold text-jade/80">{{ sectionLabel }}</p>

    <dl class="test-card__facts relative mt-5">
      <div>
        <dt><el-icon><Clock /></el-icon><span>Time</span></dt>
        <dd>{{ test.duration }} min</dd>
      </div>
      <div>
        <dt><el-icon><Document /></el-icon><span>Questions</span></dt>
        <dd>{{ test.totalQuestions }}</dd>
      </div>
      <div>
        <dt><el-icon><Headset /></el-icon><span>Mode</span></dt>
        <dd>Timed</dd>
      </div>
    </dl>

    <div class="relative mt-auto pt-5">
      <el-button
        class="!h-12 !w-full"
        type="primary"
        :loading="busy"
        :disabled="busy"
        :aria-label="`Start ${test.title}`"
        @click="$emit('start', test)"
      >
        Start mock test <el-icon class="ml-1"><ArrowRight /></el-icon>
      </el-button>
      <p class="mt-2.5 text-center text-[10px] font-semibold text-black/35">Progress is saved to your account</p>
    </div>
  </article>
</template>

<style scoped>
.test-card {
  position: relative;
  display: flex;
  height: 100%;
  min-height: 26.5rem;
  flex-direction: column;
  overflow: hidden;
  padding: 1.25rem;
  isolation: isolate;
  transition: transform 220ms ease, box-shadow 220ms ease, border-color 220ms ease;
}

.test-card:hover {
  transform: translateY(-4px);
  border-color: rgba(183, 59, 46, 0.2);
  box-shadow: var(--shadow-md);
}

.test-card__wash {
  position: absolute;
  z-index: -1;
  top: -6rem;
  right: -6rem;
  width: 12rem;
  height: 12rem;
  border-radius: 999px;
  background: radial-gradient(circle, rgba(201, 148, 62, 0.13), transparent 68%);
  transition: transform 300ms ease;
}

.test-card:hover .test-card__wash {
  transform: scale(1.12);
}

.level-pill {
  display: inline-flex;
  align-items: center;
  border: 1px solid rgba(183, 59, 46, 0.12);
  border-radius: 0.65rem;
  padding: 0.3rem 0.55rem;
  color: var(--cinnabar);
  background: rgba(183, 59, 46, 0.075);
  font-size: 0.65rem;
  font-weight: 850;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.status-dot {
  width: 0.38rem;
  height: 0.38rem;
  border-radius: 999px;
  background: var(--success);
  box-shadow: 0 0 0 3px rgba(22, 128, 93, 0.1);
}

.level-number {
  display: grid;
  width: 2.75rem;
  height: 2.75rem;
  flex: none;
  place-items: center;
  border-radius: 0.9rem;
  color: white;
  background: linear-gradient(145deg, #287964, #185241);
  box-shadow: 0 9px 20px rgba(31, 106, 87, 0.18);
  font-family: Georgia, serif;
  font-size: 1.15rem;
  font-weight: 800;
}

.test-card__facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  border-block: 1px solid var(--line);
  padding-block: 0.9rem;
}

.test-card__facts > div {
  min-width: 0;
  padding-inline: 0.6rem;
  text-align: center;
}

.test-card__facts > div + div {
  border-left: 1px solid var(--line);
}

.test-card__facts dt {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.3rem;
  color: rgba(23, 33, 30, 0.42);
  font-size: 0.62rem;
  font-weight: 750;
  text-transform: uppercase;
}

.test-card__facts dd {
  margin: 0.35rem 0 0;
  overflow: hidden;
  font-size: 0.75rem;
  font-weight: 850;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 420px) {
  .test-card {
    min-height: 25.5rem;
  }

  .test-card__facts dt span {
    display: none;
  }
}
</style>
