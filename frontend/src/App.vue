<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from './components/AppHeader.vue'

const route = useRoute()
const fullScreen = computed(() => Boolean(route.meta.fullScreen))
</script>

<template>
  <div class="min-h-screen bg-paper text-ink">
    <AppHeader v-if="!fullScreen" />
    <main :class="fullScreen ? 'min-h-screen' : ''">
      <RouterView v-slot="{ Component }">
        <Transition name="page" mode="out-in">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </main>
  </div>
</template>
