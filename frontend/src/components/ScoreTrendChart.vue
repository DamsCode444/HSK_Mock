<script setup>
import { computed } from 'vue'

const props = defineProps({
  points: { type: Array, default: () => [] },
  height: { type: Number, default: 190 },
})

const width = 640
const padding = { top: 20, right: 22, bottom: 36, left: 38 }
const chartWidth = width - padding.left - padding.right
const chartHeight = computed(() => props.height - padding.top - padding.bottom)
const normalized = computed(() => props.points.map((point, index) => ({
  label: point.label || `Attempt ${index + 1}`,
  value: Math.max(0, Math.min(100, Number(point.value) || 0)),
})))
const coordinates = computed(() => normalized.value.map((point, index) => {
  const divisor = Math.max(normalized.value.length - 1, 1)
  return {
    ...point,
    x: padding.left + (index / divisor) * chartWidth,
    y: padding.top + ((100 - point.value) / 100) * chartHeight.value,
  }
}))
const polyline = computed(() => coordinates.value.map((point) => `${point.x},${point.y}`).join(' '))
const area = computed(() => {
  if (!coordinates.value.length) return ''
  const bottom = padding.top + chartHeight.value
  return `${padding.left},${bottom} ${polyline.value} ${coordinates.value.at(-1).x},${bottom}`
})
const ariaLabel = computed(() => normalized.value.length
  ? `Score trend. ${normalized.value.map((point) => `${point.label}: ${Math.round(point.value)} percent`).join(', ')}.`
  : 'No score trend is available yet.')
</script>

<template>
  <div class="score-trend" role="img" :aria-label="ariaLabel">
    <svg :viewBox="`0 0 ${width} ${height}`" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id="score-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#e5533d" stop-opacity=".26" />
          <stop offset="100%" stop-color="#e5533d" stop-opacity="0" />
        </linearGradient>
      </defs>
      <g class="score-grid">
        <line v-for="tick in [0, 25, 50, 75, 100]" :key="tick" :x1="padding.left" :x2="width - padding.right" :y1="padding.top + ((100 - tick) / 100) * chartHeight" :y2="padding.top + ((100 - tick) / 100) * chartHeight" />
      </g>
      <polygon v-if="coordinates.length > 1" :points="area" fill="url(#score-area)" class="score-area" />
      <polyline v-if="coordinates.length > 1" :points="polyline" class="score-line" />
      <g v-for="point in coordinates" :key="`${point.label}-${point.x}`" class="score-point">
        <circle :cx="point.x" :cy="point.y" r="5" />
        <text :x="point.x" :y="height - 12" text-anchor="middle">{{ point.label }}</text>
      </g>
      <g class="score-y-labels">
        <text v-for="tick in [0, 50, 100]" :key="tick" :x="padding.left - 9" :y="padding.top + ((100 - tick) / 100) * chartHeight + 4" text-anchor="end">{{ tick }}</text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.score-trend { width: 100%; overflow: hidden; }
.score-trend svg { display: block; width: 100%; min-height: 11rem; }
.score-grid line { stroke: rgba(22, 35, 31, .09); stroke-width: 1; stroke-dasharray: 5 7; vector-effect: non-scaling-stroke; }
.score-line { fill: none; stroke: #e5533d; stroke-width: 3.5; stroke-linecap: round; stroke-linejoin: round; vector-effect: non-scaling-stroke; stroke-dasharray: 1400; animation: draw-line 1s cubic-bezier(.2,.8,.2,1) both; }
.score-area { animation: reveal-area .8s .15s ease both; transform-origin: bottom; }
.score-point circle { fill: #fff; stroke: #e5533d; stroke-width: 3; vector-effect: non-scaling-stroke; animation: reveal-point .35s ease both; }
.score-point text, .score-y-labels text { fill: rgba(22, 35, 31, .48); font-size: 10px; font-weight: 800; }
@keyframes draw-line { from { stroke-dashoffset: 1400; } to { stroke-dashoffset: 0; } }
@keyframes reveal-area { from { opacity: 0; transform: scaleY(.4); } to { opacity: 1; transform: scaleY(1); } }
@keyframes reveal-point { from { opacity: 0; transform: scale(.6); transform-origin: center; } to { opacity: 1; transform: scale(1); } }
@media (prefers-reduced-motion: reduce) { .score-line, .score-area, .score-point circle { animation: none; } }
</style>
