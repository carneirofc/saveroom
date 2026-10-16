<template>
  <div class="layout__col-2-scroll">
    <div class="admin-health">
      <h1>
        {{ $t('health.title') }}
      </h1>
      <div class="admin-health__group">
        <h2 class="admin-health__group-title">{{ $t('buildInfo.title') }}</h2>
        <BuildInfo :backend="buildInfo" :error="buildInfoFailed"></BuildInfo>
      </div>
      <div class="admin-health__group">
        <h2 class="admin-health__group-title">
          {{ $t('health.checksTitle') }}
        </h2>
        <div class="admin-health__description">
          {{ $t('health.description') }}
        </div>
        <div>
          <div
            v-for="(status, checkName) in healthChecks"
            :key="checkName"
            class="admin-health__check-item"
          >
            <div class="admin-health__check-item-label">
              <div class="admin-health__check-item-name">
                {{ camelCaseToSpaceSeparated(checkName) }}
              </div>
            </div>
            <div
              class="admin-health__icon"
              :class="status !== 'working' ? 'warning' : ''"
            >
              <i
                :class="
                  status === 'working'
                    ? 'iconoir-check admin-health__icon--success'
                    : 'iconoir-xmark admin-health__icon--fail'
                "
              ></i>
              <div
                v-if="status !== 'working'"
                class="admin-health__check-item-description"
              >
                {{ status }}
              </div>
            </div>
          </div>
          <div class="admin-health__check-item">
            <div class="admin-health__check-item-label">
              <div class="admin-health__check-item-name">Celery queue size</div>
            </div>
            {{ celeryQueueSize }}
          </div>
          <div class="admin-health__check-item">
            <div class="admin-health__check-item-label">
              <div class="admin-health__check-item-name">
                Celery export queue size
              </div>
            </div>
            {{ celeryExportQueueSize }}
          </div>
        </div>
      </div>
      <div class="admin-health__group">
        <EmailTester></EmailTester>
      </div>
      <div class="admin-health__group">
        <h2 class="admin-health__group-title">Error tester</h2>
        <Button @click="error()">Click to throw error</Button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useHead } from '#imports'
import HealthService from '@baserow/modules/core/services/health'
import BuildService from '@baserow/modules/core/services/admin/build'
import EmailTester from '@baserow/modules/core/components/health/EmailTester.vue'
import BuildInfo from '@baserow/modules/core/components/version/BuildInfo.vue'

// Page meta
definePageMeta({
  layout: 'app',
  middleware: 'staff',
})

// Access Baserow client from Nuxt app
const { $client, $i18n } = useNuxtApp()

useHead({ title: $i18n.t('health.title') })

// Fetch data (equivalent to asyncData)
const { data } = await useAsyncData('health', async () => {
  const res = await HealthService($client).getAll()
  return res.data
})

// The build the backend is running, so the page that answers "is this instance
// healthy" also answers "which instance is this".
const { data: buildData, error: buildDataError } = await useAsyncData(
  'health-build-info',
  async () => {
    const res = await BuildService($client).get()
    return res.data
  }
)

const buildInfo = computed(() => buildData.value ?? null)

// A failing request is itself a finding: a backend older than this web-frontend
// has no endpoint to answer it, so the panel says that instead of showing an
// empty version block.
const buildInfoFailed = computed(() => Boolean(buildDataError.value))

const healthChecks = computed(() => data.value?.checks ?? [])
const celeryQueueSize = computed(() => data.value?.celery_queue_size ?? 0)
const celeryExportQueueSize = computed(
  () => data.value?.celery_export_queue_size ?? 0
)

// Methods
function camelCaseToSpaceSeparated(str) {
  if (!str) return 'unknown'
  return str.toString().replace(/([A-Z])/g, ' $1')
}

function error() {
  setTimeout(() => {
    throw new Error('Health check error')
  }, 1)
}
</script>
