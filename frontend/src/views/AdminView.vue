<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import {
  Collection,
  Delete,
  DocumentAdd,
  Refresh,
  Setting,
  UploadFilled,
  User,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import StatCard from '../components/StatCard.vue'
import EmptyState from '../components/EmptyState.vue'
import { asList, errorMessage, http, unwrap } from '../services/http'
import { normalizeTests } from '../services/normalizers'

const activeTab = ref('overview')
const loading = ref(true)
const refreshing = ref(false)
const overview = ref({})
const tests = ref([])
const users = ref([])
const importForm = reactive({ testCode: '', importAll: false })
const importing = ref(false)
const uploadFile = ref(null)
const uploading = ref(false)

const stats = computed(() => overview.value.stats || overview.value.summary || overview.value)
const recentAttempts = computed(() => overview.value.recent_attempts || overview.value.attempts || [])
const recentUsers = computed(() => overview.value.recent_users || overview.value.recent_registrations || users.value.slice(0, 10))

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

function statusType(status) {
  return status === 'published' || status === 'active' ? 'success' : status === 'archived' || status === 'disabled' ? 'danger' : 'info'
}

async function loadAll(showToast = false) {
  refreshing.value = true
  try {
    const [overviewResponse, testsResponse, usersResponse] = await Promise.all([
      http.get('/admin/overview'),
      http.get('/admin/tests'),
      http.get('/admin/users'),
    ])
    overview.value = unwrap(overviewResponse.data, ['overview']) || {}
    tests.value = normalizeTests(testsResponse.data)
    users.value = asList(usersResponse.data, ['users', 'items', 'results'])
    if (showToast) ElMessage.success('Dashboard refreshed.')
  } catch (error) {
    ElMessage.error(errorMessage(error, 'Admin data could not be loaded.'))
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

async function runImport() {
  if (!importForm.importAll && !importForm.testCode.trim()) {
    ElMessage.warning('Enter a test code or choose “Import all bundles”.')
    return
  }
  importing.value = true
  try {
    const payload = { import_all: importForm.importAll }
    if (!importForm.importAll) payload.test_code = importForm.testCode.trim()
    const { data } = await http.post('/admin/import', payload)
    const count = data?.imported_count ?? data?.count ?? data?.imported?.length
    ElMessage.success(count != null ? `Import complete: ${count} bundle${count === 1 ? '' : 's'} processed.` : 'Import completed.')
    importForm.testCode = ''
    await loadAll()
    activeTab.value = 'tests'
  } catch (error) {
    ElMessage.error(errorMessage(error, 'The bundle import failed.'))
  } finally {
    importing.value = false
  }
}

function handleUploadChange(file) {
  uploadFile.value = file.raw
}

async function uploadZip() {
  if (!uploadFile.value) {
    ElMessage.warning('Choose a ZIP archive first.')
    return
  }
  uploading.value = true
  try {
    const body = new FormData()
    body.append('file', uploadFile.value)
    await http.post('/admin/import/upload', body, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 })
    ElMessage.success('ZIP uploaded and imported successfully.')
    uploadFile.value = null
    await loadAll()
    activeTab.value = 'tests'
  } catch (error) {
    ElMessage.error(errorMessage(error, 'The ZIP upload failed.'))
  } finally {
    uploading.value = false
  }
}

async function saveTest(test) {
  test._saving = true
  try {
    await http.patch(`/admin/tests/${test.id}`, {
      audio_play_limit: Number(test.audioPlayLimit || 1),
      status: test.status,
    })
    ElMessage.success(`${test.testCode} settings saved.`)
  } catch (error) {
    ElMessage.error(errorMessage(error, 'Test settings could not be saved.'))
  } finally {
    test._saving = false
  }
}

async function archiveTest(test) {
  try {
    await ElMessageBox.confirm(
      `${test.testCode} will be removed from the student catalog. Existing result records are kept by the server where supported.`,
      'Archive this test?',
      { type: 'warning', confirmButtonText: 'Archive test', cancelButtonText: 'Cancel' },
    )
    await http.delete(`/admin/tests/${test.id}`)
    tests.value = tests.value.filter((item) => item.id !== test.id)
    ElMessage.success(`${test.testCode} archived.`)
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error, 'The test could not be archived.'))
  }
}

async function toggleUser(user, isActive) {
  user._updating = true
  try {
    await http.patch(`/admin/users/${user.id}`, { is_active: isActive })
    ElMessage.success(`${user.username} is now ${isActive ? 'active' : 'disabled'}.`)
  } catch (error) {
    user.is_active = !isActive
    ElMessage.error(errorMessage(error, 'The account status could not be changed.'))
  } finally {
    user._updating = false
  }
}

onMounted(() => loadAll())
</script>

<template>
  <section class="pb-20 pt-10 sm:pt-14">
    <div class="page-shell">
      <div class="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div><span class="eyebrow">Administration</span><h1 class="display-title mt-3 text-4xl font-bold sm:text-5xl">Content control room.</h1><p class="mt-3 text-black/50">Import HSK bundles, publish tests, and monitor student activity.</p></div>
        <el-button :loading="refreshing" :icon="Refresh" class="!h-11" @click="loadAll(true)">Refresh data</el-button>
      </div>

      <div v-if="loading" class="mt-9 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"><el-skeleton v-for="n in 4" :key="n" animated class="surface p-5"><template #template><el-skeleton-item variant="h3" class="!h-24" /></template></el-skeleton></div>

      <template v-else>
        <div class="mt-9 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Registered users" :value="stats.total_users ?? users.length" hint="All accounts" />
          <StatCard label="Imported tests" :value="stats.total_tests ?? tests.length" hint="Drafts and published" tone="gold" />
          <StatCard label="Total attempts" :value="stats.total_attempts ?? 0" hint="Started mock exams" tone="red" />
          <StatCard label="Average score" :value="stats.average_score ?? stats.avg_score ?? '—'" hint="Submitted attempts" />
        </div>

        <div class="mt-8 rounded-[1.3rem] border border-black/10 bg-white/70 px-4 shadow-soft sm:px-6">
          <el-tabs v-model="activeTab" class="admin-tabs">
            <el-tab-pane name="overview">
              <template #label><span class="inline-flex items-center gap-2"><el-icon><Collection /></el-icon> Overview</span></template>
              <div class="grid gap-7 py-6 lg:grid-cols-2">
                <section>
                  <h2 class="font-serif text-2xl font-bold">Recent attempts</h2>
                  <div v-if="recentAttempts.length" class="mt-4 divide-y divide-black/[0.07] rounded-2xl border border-black/[0.07] bg-white px-4">
                    <div v-for="attempt in recentAttempts" :key="attempt.id ?? attempt.attempt_id" class="flex items-center gap-3 py-4">
                      <span class="grid h-9 w-9 place-items-center rounded-lg bg-jade/10 text-xs font-black text-jade">H{{ attempt.level ?? attempt.test?.level ?? '?' }}</span>
                      <span class="min-w-0 flex-1"><b class="block truncate text-sm">{{ attempt.username ?? attempt.user?.username ?? 'Student' }}</b><small class="text-black/40">{{ attempt.test_code ?? attempt.test?.test_code ?? 'Mock test' }} · {{ formatDate(attempt.end_time ?? attempt.start_time) }}</small></span>
                      <b>{{ attempt.total_score ?? attempt.score ?? '—' }}</b>
                    </div>
                  </div>
                  <EmptyState v-else class="mt-4" title="No attempts yet" description="Student test activity will appear here." />
                </section>
                <section>
                  <h2 class="font-serif text-2xl font-bold">Recent registrations</h2>
                  <div v-if="recentUsers.length" class="mt-4 divide-y divide-black/[0.07] rounded-2xl border border-black/[0.07] bg-white px-4">
                    <div v-for="person in recentUsers" :key="person.id" class="flex items-center gap-3 py-4"><span class="grid h-9 w-9 place-items-center rounded-lg bg-cinnabar/10 font-bold text-cinnabar">{{ String(person.username ?? '?').slice(0, 1).toUpperCase() }}</span><span class="min-w-0 flex-1"><b class="block truncate text-sm">{{ person.username }}</b><small class="text-black/40">{{ person.email }}</small></span><small class="text-black/35">{{ formatDate(person.created_at) }}</small></div>
                  </div>
                  <EmptyState v-else class="mt-4" title="No registrations yet" description="New student accounts will appear here." />
                </section>
              </div>
            </el-tab-pane>

            <el-tab-pane name="import">
              <template #label><span class="inline-flex items-center gap-2"><el-icon><DocumentAdd /></el-icon> Import</span></template>
              <div class="grid gap-7 py-6 lg:grid-cols-2">
                <section class="rounded-2xl border border-black/[0.08] bg-[#f8f6f0] p-5 sm:p-7">
                  <span class="grid h-11 w-11 place-items-center rounded-xl bg-jade/10 text-jade"><el-icon :size="22"><Refresh /></el-icon></span>
                  <h2 class="mt-5 font-serif text-2xl font-bold">Scan local bundles</h2>
                  <p class="mt-2 text-sm leading-6 text-black/50">Import one known test code, or scan every HSK1–6 bundle in the configured source directory.</p>
                  <el-form class="mt-6" label-position="top" @submit.prevent="runImport">
                    <el-form-item label="Test code"><el-input v-model="importForm.testCode" size="large" placeholder="e.g. H11329" :disabled="importForm.importAll" /></el-form-item>
                    <el-checkbox v-model="importForm.importAll">Import all bundles found on disk</el-checkbox>
                    <el-button native-type="submit" type="primary" size="large" class="mt-6 !w-full" :loading="importing">Run importer</el-button>
                  </el-form>
                </section>

                <section class="rounded-2xl border border-black/[0.08] bg-[#f8f6f0] p-5 sm:p-7">
                  <span class="grid h-11 w-11 place-items-center rounded-xl bg-cinnabar/10 text-cinnabar"><el-icon :size="22"><UploadFilled /></el-icon></span>
                  <h2 class="mt-5 font-serif text-2xl font-bold">Upload a ZIP bundle</h2>
                  <p class="mt-2 text-sm leading-6 text-black/50">The archive should contain the exam PDF, answer PDF, and listening audio directory. HSK6 may include a writing PDF.</p>
                  <el-upload class="mt-6" drag action="#" accept=".zip,application/zip" :auto-upload="false" :limit="1" :on-change="handleUploadChange">
                    <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
                    <div class="el-upload__text">Drop a ZIP here or <em>browse</em></div>
                    <template #tip><div class="el-upload__tip">ZIP archives only. Server validation controls the maximum size.</div></template>
                  </el-upload>
                  <el-button type="primary" size="large" class="mt-5 !w-full" :loading="uploading" :disabled="!uploadFile" @click="uploadZip">Upload and import</el-button>
                </section>
              </div>
            </el-tab-pane>

            <el-tab-pane name="tests">
              <template #label><span class="inline-flex items-center gap-2"><el-icon><Setting /></el-icon> Tests <small class="rounded bg-black/5 px-1.5 py-0.5">{{ tests.length }}</small></span></template>
              <div class="py-6">
                <div class="mb-5 flex items-center justify-between"><div><h2 class="font-serif text-2xl font-bold">Test catalog & settings</h2><p class="mt-1 text-sm text-black/45">Control publishing and the listening replay limit.</p></div><el-button type="primary" @click="activeTab = 'import'">Import test</el-button></div>
                <div v-if="tests.length" class="overflow-hidden rounded-2xl border border-black/[0.08]">
                  <el-table :data="tests" stripe class="w-full">
                    <el-table-column label="Test" min-width="230"><template #default="{ row }"><div class="flex items-center gap-3"><span class="grid h-10 w-10 place-items-center rounded-xl bg-jade/10 font-serif font-bold text-jade">{{ row.level }}</span><span><b class="block">{{ row.title }}</b><small class="text-black/40">{{ row.testCode }}</small></span></div></template></el-table-column>
                    <el-table-column prop="totalQuestions" label="Questions" width="100" align="center" />
                    <el-table-column prop="duration" label="Minutes" width="90" align="center" />
                    <el-table-column label="Audio plays" width="150"><template #default="{ row }"><el-input-number v-model="row.audioPlayLimit" :min="1" :max="10" size="small" /></template></el-table-column>
                    <el-table-column label="Status" width="145"><template #default="{ row }"><el-select v-model="row.status" size="small"><el-option label="Published" value="published" /><el-option label="Draft" value="draft" /><el-option label="Archived" value="archived" /></el-select></template></el-table-column>
                    <el-table-column label="Actions" width="190" fixed="right"><template #default="{ row }"><el-button size="small" :loading="row._saving" @click="saveTest(row)">Save</el-button><el-button size="small" type="danger" plain :icon="Delete" @click="archiveTest(row)">Archive</el-button></template></el-table-column>
                  </el-table>
                </div>
                <EmptyState v-else title="No tests imported" description="Run the local bundle importer or upload a ZIP archive to create the catalog."><el-button type="primary" @click="activeTab = 'import'">Open importer</el-button></EmptyState>
              </div>
            </el-tab-pane>

            <el-tab-pane name="users">
              <template #label><span class="inline-flex items-center gap-2"><el-icon><User /></el-icon> Users <small class="rounded bg-black/5 px-1.5 py-0.5">{{ users.length }}</small></span></template>
              <div class="py-6">
                <div class="mb-5"><h2 class="font-serif text-2xl font-bold">Registered users</h2><p class="mt-1 text-sm text-black/45">Student and administrator accounts from the local database.</p></div>
                <div v-if="users.length" class="overflow-hidden rounded-2xl border border-black/[0.08]"><el-table :data="users" stripe class="w-full"><el-table-column label="User" min-width="220"><template #default="{ row }"><div class="flex items-center gap-3"><span class="grid h-9 w-9 place-items-center rounded-lg bg-cinnabar/10 font-bold text-cinnabar">{{ String(row.username || '?').slice(0, 1).toUpperCase() }}</span><span><b class="block">{{ row.username }}</b><small class="text-black/40">ID {{ row.id }} · {{ row.attempt_count || 0 }} attempts</small></span></div></template></el-table-column><el-table-column prop="email" label="Email" min-width="230" /><el-table-column label="Role" width="110"><template #default="{ row }"><el-tag :type="row.role === 'admin' ? 'danger' : 'info'" effect="light">{{ row.role }}</el-tag></template></el-table-column><el-table-column label="Active" width="130"><template #default="{ row }"><el-switch v-model="row.is_active" :loading="row._updating" inline-prompt active-text="Yes" inactive-text="No" @change="toggleUser(row, $event)" /></template></el-table-column><el-table-column label="Joined" width="190"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column></el-table></div>
                <EmptyState v-else title="No user accounts" description="Registered students will appear in this table." />
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
:deep(.admin-tabs > .el-tabs__header) { margin: 0; }
:deep(.admin-tabs > .el-tabs__header .el-tabs__nav-wrap::after) { background: rgba(29, 38, 35, .08); }
:deep(.admin-tabs > .el-tabs__header .el-tabs__item) { height: 56px; font-weight: 700; }
</style>
