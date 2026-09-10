<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from './components/AppHeader.vue'

const route = useRoute()
const fullScreen = computed(() => Boolean(route.meta.fullScreen))
</script>

<template>
  <div class="app-frame">
    <a v-if="!fullScreen" class="skip-link" href="#main-content">Skip to main content</a>
    <AppHeader v-if="!fullScreen" />
    <main
      id="main-content"
      :class="fullScreen ? 'min-h-screen' : 'app-main'"
      tabindex="-1"
    >
      <RouterView v-slot="{ Component }">
        <Transition name="page" mode="out-in">
          <component :is="Component" :key="route.name" />
        </Transition>
      </RouterView>
    </main>
  </div>
</template>
