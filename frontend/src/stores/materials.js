import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  fetchMaterialCollection,
  fetchMaterialsCatalog,
} from '../services/materials'


export const useMaterialsStore = defineStore('materials', () => {
  const catalog = ref(null)
  const collections = reactive({})
  const catalogLoading = ref(false)
  let catalogPromise = null
  const collectionPromises = new Map()

  const totals = computed(() => catalog.value?.totals || {})
  const editions = computed(() => catalog.value?.editions || [])

  async function loadCatalog(force = false) {
    if (!force && catalog.value) return catalog.value
    if (catalogPromise) return catalogPromise
    catalogLoading.value = true
    catalogPromise = fetchMaterialsCatalog()
      .then((value) => {
        catalog.value = value
        return value
      })
      .finally(() => {
        catalogLoading.value = false
        catalogPromise = null
      })
    return catalogPromise
  }

  async function loadCollection(slug, force = false) {
    if (!force && collections[slug]) return collections[slug]
    if (collectionPromises.has(slug)) return collectionPromises.get(slug)
    const promise = fetchMaterialCollection(slug)
      .then((value) => {
        collections[slug] = value
        return value
      })
      .finally(() => collectionPromises.delete(slug))
    collectionPromises.set(slug, promise)
    return promise
  }

  return {
    catalog,
    collections,
    catalogLoading,
    totals,
    editions,
    loadCatalog,
    loadCollection,
  }
})
