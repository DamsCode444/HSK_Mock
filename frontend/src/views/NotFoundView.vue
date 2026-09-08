<script setup>
import { ArrowLeft } from '@element-plus/icons-vue'
</script>

<template>
  <section class="soft-grid grid min-h-[calc(100vh-72px)] place-items-center px-5 py-16 text-center">
    <div>
      <span class="font-serif text-[9rem] font-black leading-none text-cinnabar/10">404</span>
      <h1 class="display-title -mt-8 text-4xl font-bold">This page wandered off.</h1>
      <p class="mt-4 text-black/50">Return to the mock test catalog and keep your preparation moving.</p>
      <RouterLink to="/" class="mt-7 inline-flex h-11 items-center gap-2 rounded-xl bg-ink px-5 text-sm font-bold text-white"><el-icon><ArrowLeft /></el-icon> Back home</RouterLink>
    </div>
  </section>
</template>
