import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  fetchMaterialCollection,
  fetchMaterialsCatalog,
} from '../services/materials'

const CATALOG_TTL_MS = 5 * 60 * 1000
const COLLECTION_TTL_MS = 10 * 60 * 1000

export const useMaterialsStore = defineStore('materials', () => {
  const catalog = ref(null)
  const collections = reactive({})
  const collectionFetchedAt = reactive({})
  const catalogFetchedAt = ref(0)
  const catalogLoading = ref(false)
  let catalogPromise = null
  const collectionPromises = new Map()

  const totals = computed(() => catalog.value?.totals || {})
  const editions = computed(() => catalog.value?.editions || [])

  async function loadCatalog(force = false) {
    const fresh = Date.now() - catalogFetchedAt.value < CATALOG_TTL_MS
    if (!force && catalog.value && fresh) return catalog.value
    if (catalogPromise) return catalogPromise
    catalogLoading.value = true
    catalogPromise = fetchMaterialsCatalog()
      .then((value) => {
        catalog.value = value
        catalogFetchedAt.value = Date.now()
        return value
      })
      .finally(() => {
        catalogLoading.value = false
        catalogPromise = null
      })
    return catalogPromise
  }

  async function loadCollection(slug, force = false) {
    const fresh = Date.now() - Number(collectionFetchedAt[slug] || 0) < COLLECTION_TTL_MS
    if (!force && collections[slug] && fresh) return collections[slug]
    if (collectionPromises.has(slug)) return collectionPromises.get(slug)
    const promise = fetchMaterialCollection(slug)
      .then((value) => {
        collections[slug] = value
        collectionFetchedAt[slug] = Date.now()
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
    catalogFetchedAt,
    totals,
    editions,
    loadCatalog,
    loadCollection,
  }
})
