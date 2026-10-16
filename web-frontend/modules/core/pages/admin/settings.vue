<template>
  <div class="layout__col-2-scroll">
    <div class="admin-settings">
      <h1>{{ $t('settings.settingsTitle') }}</h1>
      <div class="admin-settings__group">
        <h2 class="admin-settings__group-title">
          {{ $t('settings.versionTitle') }}
        </h2>
        <p class="admin-settings__group-description">
          {{ $t('settings.versionDescription') }}
        </p>
        <BuildInfo :backend="buildInfo" :error="buildInfoFailed"></BuildInfo>
      </div>
      <div class="admin-settings__group">
        <div class="admin-settings__item">
          <div class="admin-settings__label">
            <div class="admin-settings__name">
              {{ $t('settings.baserowInstanceId') }}
            </div>
            <div class="admin-settings__description">
              {{ $t('settings.instanceIdDescription') }}
            </div>
          </div>
          <div class="admin-settings__control admin-settings__control--inline">
            {{ instanceId }}
            <a class="admin-settings__copy" @click.prevent="handleCopy()">
              {{ $t('action.copy') }}
              <Copied ref="instanceIdCopied" />
            </a>
          </div>
        </div>
        <div class="admin-settings__item">
          <div class="admin-settings__label">
            <div class="admin-settings__name">
              {{ $t('settings.settingsVerifyImportSignature') }}
            </div>
            <div class="admin-settings__description">
              {{ $t('settings.settingsVerifyImportSignatureDescription') }}
            </div>
          </div>
          <div class="admin-settings__control">
            <SwitchInput
              :value="settings.verify_import_signature"
              @input="updateSettings({ verify_import_signature: $event })"
              >{{ $t('settings.enabled') }}</SwitchInput
            >
          </div>
        </div>
      </div>
      <div class="admin-settings__group">
        <h2 class="admin-settings__group-title">
          {{ $t('settings.applicationFeatures') }}
        </h2>
        <div class="admin-settings__item">
          <div class="admin-settings__label">
            <div class="admin-settings__name">
              {{ $t('settings.settingEnableDatabaseName') }}
            </div>
            <div class="admin-settings__description">
              {{ $t('settings.settingEnableDatabaseDescription') }}
            </div>
          </div>
          <div class="admin-settings__control">
            <SwitchInput
              :value="settings.enable_database"
              @input="updateSettings({ enable_database: $event })"
              >{{ $t('settings.enabled') }}</SwitchInput
            >
          </div>
        </div>
        <div class="admin-settings__item">
          <div class="admin-settings__label">
            <div class="admin-settings__name">
              {{ $t('settings.settingEnableBuilderName') }}
            </div>
            <div class="admin-settings__description">
              {{ $t('settings.settingEnableBuilderDescription') }}
            </div>
          </div>
          <div class="admin-settings__control">
            <SwitchInput
              :value="settings.enable_builder"
              @input="updateSettings({ enable_builder: $event })"
              >{{ $t('settings.enabled') }}</SwitchInput
            >
          </div>
        </div>
        <div class="admin-settings__item">
          <div class="admin-settings__label">
            <div class="admin-settings__name">
              {{ $t('settings.settingEnableAutomationName') }}
            </div>
            <div class="admin-settings__description">
              {{ $t('settings.settingEnableAutomationDescription') }}
            </div>
          </div>
          <div class="admin-settings__control">
            <SwitchInput
              :value="settings.enable_automation"
              @input="updateSettings({ enable_automation: $event })"
              >{{ $t('settings.enabled') }}</SwitchInput
            >
          </div>
        </div>
        <div class="admin-settings__item">
          <div class="admin-settings__label">
            <div class="admin-settings__name">
              {{ $t('settings.settingEnableDashboardName') }}
            </div>
            <div class="admin-settings__description">
              {{ $t('settings.settingEnableDashboardDescription') }}
            </div>
          </div>
          <div class="admin-settings__control">
            <SwitchInput
              :value="settings.enable_dashboard"
              @input="updateSettings({ enable_dashboard: $event })"
              >{{ $t('settings.enabled') }}</SwitchInput
            >
          </div>
        </div>
      </div>
      <div class="admin-settings__group">
        <h2 class="admin-settings__group-title">
          {{ $t('settings.accountRestrictions') }}
        </h2>
        <div class="admin-settings__item">
          <div class="admin-settings__label">
            <div class="admin-settings__name">
              {{ $t('settings.settingAllowNewAccountsName') }}
            </div>
            <div class="admin-settings__description">
              {{ $t('settings.settingAllowNewAccountsDescription') }}
            </div>
          </div>
          <div class="admin-settings__control">
            <SwitchInput
              :value="settings.allow_new_signups"
              @input="updateSettings({ allow_new_signups: $event })"
              >{{ $t('settings.enabled') }}</SwitchInput
            >
          </div>
        </div>
        <div class="admin-settings__item">
          <div class="admin-settings__label">
            <div class="admin-settings__name">
              {{ $t('settings.settingAllowResetPasswordName') }}
            </div>
            <div class="admin-settings__description">
              {{ $t('settings.settingAllowResetPasswordDescription') }}
            </div>
          </div>
          <div class="admin-settings__control">
            <SwitchInput
              :value="settings.allow_reset_password"
              @input="updateSettings({ allow_reset_password: $event })"
            >
              {{ $t('settings.enabled') }}
            </SwitchInput>
            <div v-show="!settings.allow_reset_password" class="warning">
              {{ $t('settings.settingAllowResetPasswordWarning') }}
            </div>
          </div>
        </div>
        <div class="admin-settings__item">
          <div class="admin-settings__label">
            <div class="admin-settings__name">
              {{ $t('settings.settingAllowNonStaffCreateWorkspaceOperation') }}
            </div>
            <div class="admin-settings__description">
              {{
                $t(
                  'settings.settingAllowNonStaffCreateWorkspaceOperationDescription'
                )
              }}
            </div>
          </div>
          <div class="admin-settings__control">
            <SwitchInput
              :value="settings.allow_global_workspace_creation"
              @input="
                updateSettings({ allow_global_workspace_creation: $event })
              "
              >{{ $t('settings.enabled') }}</SwitchInput
            >
            <div
              v-show="settings.allow_global_workspace_creation"
              class="warning"
            >
              {{
                $t(
                  'settings.settingAllowNonStaffCreateWorkspaceOperationWarning'
                )
              }}
            </div>
          </div>
        </div>
      </div>
      <div class="admin-settings__group">
        <h2 class="admin-settings__group-title">
          {{ $t('settings.userSettings') }}
        </h2>
        <div class="admin-settings__item">
          <div class="admin-settings__label">
            <div class="admin-settings__name">
              {{ $t('settings.emailVerification') }}
            </div>
            <div class="admin-settings__description">
              {{ $t('settings.emailVerificationDescription') }}
            </div>
          </div>
          <div class="admin-settings__control">
            <RadioGroup
              :model-value="settings.email_verification"
              :options="emailVerificationOptions"
              @input="updateSettings({ email_verification: $event })"
            ></RadioGroup>
          </div>
        </div>
        <div class="admin-settings__item">
          <div class="admin-settings__label">
            <div class="admin-settings__name">
              {{ $t('settings.settingUserDeletionGraceDelay') }}
            </div>
            <div class="admin-settings__description">
              {{ $t('settings.settingUserDeletionGraceDelayDescription') }}
            </div>
          </div>
          <div class="admin-settings__control">
            <FormGroup :error="v$.values.account_deletion_grace_delay.$error">
              <FormInput
                :value="v$.values.account_deletion_grace_delay.$model"
                :error="v$.values.account_deletion_grace_delay.$error"
                type="number"
                size="large"
                @input="handleAccountDeletionGraceDelayInput($event)"
              ></FormInput>

              <template #error>
                {{
                  v$.values.account_deletion_grace_delay.$errors[0]?.$message
                }}
              </template>
            </FormGroup>
          </div>
        </div>
      </div>
      <div class="admin-settings__group">
        <h2 class="admin-settings__group-title">
          {{ $t('settings.maintenance') }}
        </h2>
        <div class="admin-settings__item">
          <div class="admin-settings__label">
            <div class="admin-settings__name">
              {{ $t('settings.settingTrackWorkspaceUsage') }}
            </div>
            <div class="admin-settings__description">
              {{ $t('settings.settingTrackWorkspaceUsageDescription') }}
            </div>
          </div>
          <div class="admin-settings__control">
            <SwitchInput
              :value="settings.track_workspace_usage"
              @input="updateSettings({ track_workspace_usage: $event })"
              >{{ $t('settings.enabled') }}</SwitchInput
            >
          </div>
        </div>
      </div>
      <div v-if="operationalLimits.length > 0" class="admin-settings__group">
        <h2 class="admin-settings__group-title">
          {{ $t('settings.operationalLimits') }}
        </h2>
        <p class="admin-settings__group-description">
          {{ $t('settings.operationalLimitsDescription') }}
        </p>
        <div
          v-for="limit in operationalLimits"
          :key="limit.name"
          class="admin-settings__item"
        >
          <div class="admin-settings__label">
            <div class="admin-settings__name">{{ limit.name }}</div>
          </div>
          <div class="admin-settings__control">{{ limit.value }}</div>
        </div>
      </div>
      <component
        :is="component"
        v-for="(component, index) in additionalSettingsComponents"
        :key="index"
      ></component>
    </div>
  </div>
</template>
<script setup>
import {
  ref,
  reactive,
  computed,
  watch,
  getCurrentInstance,
  onMounted,
} from 'vue'
import { useAsyncData, useNuxtApp, useHead } from '#app'
import { useStore } from 'vuex'
import { useVuelidate } from '@vuelidate/core'
import { required, integer, between, helpers } from '@vuelidate/validators'

import { notifyIf } from '@baserow/modules/core/utils/error'
import SettingsService from '@baserow/modules/core/services/settings'
import LimitsService from '@baserow/modules/core/services/admin/limits'
import BuildService from '@baserow/modules/core/services/admin/build'
import BuildInfo from '@baserow/modules/core/components/version/BuildInfo.vue'
import { copyToClipboard } from '@baserow/modules/database/utils/clipboard'
import { EMAIL_VERIFICATION_OPTIONS } from '@baserow/modules/core/enums'

const { $registry, $client, $i18n } = useNuxtApp()
const { t: $t } = useI18n()
const store = useStore()

useHead({ title: $i18n.t('settings.settingsTitle') })

const instanceIdCopied = ref(null)

const values = reactive({
  account_deletion_grace_delay: null,
})

const settings = computed(() => store.getters['settings/get'])

const emailVerificationOptions = computed(() => [
  {
    label: $t('settings.emailVerificationNoVerification'),
    value: EMAIL_VERIFICATION_OPTIONS.NO_VERIFICATION,
  },
  {
    label: $t('settings.emailVerificationRecommended'),
    value: EMAIL_VERIFICATION_OPTIONS.RECOMMENDED,
  },
  {
    label: $t('settings.emailVerificationEnforced'),
    value: EMAIL_VERIFICATION_OPTIONS.ENFORCED,
  },
])

const rules = computed(() => {
  return {
    values: {
      account_deletion_grace_delay: {
        required: helpers.withMessage($t('error.requiredField'), required),
        between: helpers.withMessage(
          $t('settings.invalidAccountDeletionGraceDelay'),
          between(0, 32000)
        ),
        integer: helpers.withMessage(
          $t('settings.invalidAccountDeletionGraceDelay'),
          integer
        ),
      },
    },
  }
})

const v$ = useVuelidate(rules, { values }, { $lazy: true })

const { data: instanceData } = await useAsyncData('instance-id', async () => {
  const { data } = await SettingsService($client).getInstanceID()
  return data
})

// The limits below are read from the environment by the backend, so they are
// shown but cannot be edited here: changing one means changing the environment
// and restarting the instance.
const { data: limitsData } = await useAsyncData(
  'operational-limits',
  async () => {
    const { data } = await LimitsService($client).get()
    return data
  }
)

const operationalLimits = computed(() => {
  const limits = limitsData.value
  if (!limits) {
    return []
  }
  return [
    {
      name: $t('settings.limitTrash'),
      value: $t('settings.limitHours', {
        count: limits.hours_until_trash_permanently_deleted,
      }),
    },
    {
      name: $t('settings.limitExportFile'),
      value: $t('settings.limitMinutes', {
        count: limits.export_file_expire_minutes,
      }),
    },
    {
      name: $t('settings.limitSnapshotExpiration'),
      value: $t('settings.limitDays', {
        count: limits.snapshot_expiration_time_days,
      }),
    },
    {
      name: $t('settings.limitMaxSnapshots'),
      value: limits.max_snapshots_per_workspace,
    },
    {
      name: $t('settings.limitAuditLogRetention'),
      value: $t('settings.limitDays', {
        count: limits.user_log_entry_retention_days,
      }),
    },
    {
      name: $t('settings.limitRowHistoryRetention'),
      value: $t('settings.limitDays', {
        count: limits.row_history_retention_days,
      }),
    },
    {
      name: $t('settings.limitJobSoftTimeLimit'),
      value: $t('settings.limitMinutes', {
        count: Math.round(limits.job_soft_time_limit_seconds / 60),
      }),
    },
    {
      name: $t('settings.limitJobExpiration'),
      value: $t('settings.limitMinutes', {
        count: limits.job_expiration_time_limit_minutes,
      }),
    },
    {
      name: $t('settings.limitImportExportRemoval'),
      value: $t('settings.limitDays', {
        count: limits.import_export_resource_removal_after_days,
      }),
    },
  ]
})

const instanceId = computed(() => instanceData.value?.instance_id ?? '')

// The build the backend is running. The web-frontend build needs no request,
// BuildInfo reads it from the bundle it is served with.
const { data: buildData, error: buildDataError } = await useAsyncData(
  'build-info',
  async () => {
    const { data } = await BuildService($client).get()
    return data
  }
)

const buildInfo = computed(() => buildData.value ?? null)

// A failing request is itself a finding: a backend older than this web-frontend
// has no endpoint to answer it, so the panel says that instead of showing an
// empty version block.
const buildInfoFailed = computed(() => Boolean(buildDataError.value))

const additionalSettingsComponents = computed(() => {
  return Object.values($registry.getAll('plugin'))
    .reduce(
      (components, plugin) =>
        components.concat(plugin.getSettingsPageComponents()),
      []
    )
    .filter((component) => component !== null)
})

function handleCopy() {
  copyToClipboard(instanceId.value)
  instanceIdCopied.value?.show()
}

async function updateSettings(payload) {
  v$.value.$touch()
  if (v$.value.$invalid) return
  try {
    await store.dispatch('settings/update', payload)
  } catch (error) {
    notifyIf(error, 'settings')
  }
}

function updateAccountDeletionGraceDelay() {
  const existing = settings.value.account_deletion_grace_delay
  const parsed = parseInt(v$.value.values.account_deletion_grace_delay.$model)
  if (
    !v$.value.values.account_deletion_grace_delay.$error &&
    existing !== parsed
  ) {
    updateSettings({ account_deletion_grace_delay: parsed })
  }
}

function handleAccountDeletionGraceDelayInput(event) {
  v$.value.values.account_deletion_grace_delay.$model = event
  updateAccountDeletionGraceDelay()
}

watch(
  () => settings.value.account_deletion_grace_delay,
  (val) => {
    v$.value.values.account_deletion_grace_delay.$model = val
  }
)

onMounted(() => {
  v$.value.values.account_deletion_grace_delay.$model =
    settings.value.account_deletion_grace_delay
})
</script>
