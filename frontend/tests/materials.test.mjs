import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { createServer } from 'vite'

let server
let materials
before(async () => {
  server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  materials = await server.ssrLoadModule('/src/services/materials.js')
})
after(async () => { await server?.close() })

test('vocabulary catalog preserves seven groups, the advanced range, and private reference IDs', () => {
  const catalog = materials.normalizeCatalog({ editions: [
    { id: '2.0', levels: [{ level: 1, standard: '2.0', book_count: 3 }] },
    { id: '3.0', levels: [{ level: 1, standard: '3.0', book_count: 3 }] },
    { id: 'vocabulary', label: 'Vocabulary', available_levels: [1, 2, 3, 4, 5, 6, 7],
      levels: Array.from({ length: 7 }, (_, index) => ({
        level: index + 1, level_label: index === 6 ? '7–9' : String(index + 1),
        slug: `hsk-vocabulary-level-${index === 6 ? '7-9' : index + 1}`,
        standard: 'vocabulary', book_count: 1,
      })),
      references: [{ id: 'comparison', asset_id: 'comparison-image', size_bytes: 32526 }],
    },
  ] })
  assert.equal(catalog.editions.length, 3)
  const vocabulary = catalog.editions[2]
  assert.equal(vocabulary.levels.length, 7)
  assert.equal(vocabulary.levels[6].levelLabel, '7–9')
  assert.equal(vocabulary.levels[6].slug, 'hsk-vocabulary-level-7-9')
  assert.equal(vocabulary.references[0].assetId, 'comparison-image')
  assert.equal(vocabulary.references[0].sizeBytes, 32526)
  assert.deepEqual(catalog.editions[0].references, [])
  assert.equal(catalog.editions[0].levels[0].levelLabel, '1')
})

test('vocabulary books stay readable and downloadable without invented audio', () => {
  const collection = materials.normalizeCollection({ standard: 'vocabulary', level: 7,
    level_label: '7–9', slug: 'hsk-vocabulary-level-7-9', books: [{
      id: 'new-hsk-vocabulary-l7-9', kind: 'vocabulary', page_count: 235,
      pdf_asset_id: 'new-hsk-vocabulary-l7-9-pdf', has_audio: false,
      lessons: [], audio_bundle_id: null, complete_bundle_id: null,
    }],
  })
  assert.equal(collection.curriculumLabel, 'New HSK vocabulary')
  const book = collection.books[0]
  assert.equal(book.kindLabel, 'Vocabulary')
  assert.equal(book.pageCount, 235)
  assert.equal(book.viewable, true)
  assert.equal(book.downloadable, true)
  assert.equal(book.hasAudio, false)
  assert.equal(book.trackCount, 0)
  assert.equal(book.audioBundleId, null)
  assert.equal(book.completeBundleId, null)
})

test('existing course books keep their lesson audio and curriculum label', () => {
  const collection = materials.normalizeCollection({ standard: '2.0', level: 1,
    books: [{ id: 'course', kind: 'textbook', pdf_asset_id: 'course-pdf',
      audio_bundle_id: 'course-audio', lessons: [{ lesson_number: 1,
        tracks: [{ asset_id: 'track-1', order: 1, duration_seconds: 120 }],
      }],
    }],
  })
  assert.equal(collection.curriculumLabel, 'HSK 2.0')
  assert.equal(collection.books[0].hasAudio, true)
  assert.equal(collection.books[0].trackCount, 1)
  assert.equal(collection.books[0].audioBundleId, 'course-audio')
})
