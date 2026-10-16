<template>
  <form @submit.prevent="submit">
    <div class="row">
      <div class="col col-6">
        <FormGroup
          small-label
          required
          :label="$t('backupsModal.name')"
          :error="showErrors && !nameValid"
          class="margin-bottom-2"
        >
          <FormInput v-model="values.name" :error="showErrors && !nameValid" />
          <template #error>{{ nameError }}</template>
        </FormGroup>
      </div>
      <div class="col col-6">
        <FormGroup
          small-label
          :label="$t('backupsModal.destination')"
          :error="destinationUnavailable"
          class="margin-bottom-2"
        >
          <Dropdown v-model="values.destination">
            <DropdownItem
              :name="$t('backupsModal.noDestination')"
              value=""
            ></DropdownItem>
            <DropdownItem
              v-for="item in destinations"
              :key="item.name"
              :name="`${item.name} (${item.type})`"
              :value="item.name"
            ></DropdownItem>
            <DropdownItem
              v-if="destinationUnavailable"
              :name="
                $t('backupsModal.unavailableDestination', {
                  name: values.destination,
                })
              "
              :value="values.destination"
              disabled
            ></DropdownItem>
          </Dropdown>
          <template #error>
            {{ $t('backupsModal.unavailableDestinationError') }}
          </template>
        </FormGroup>
      </div>
      <div class="col col-6">
        <FormGroup
          small-label
          required
          :label="$t('backupsModal.cron')"
          :helper-text="$t('backupsModal.cronHelp')"
          :error="showErrors && !values.cron.trim()"
          class="margin-bottom-2"
        >
          <FormInput
            v-model="values.cron"
            placeholder="0 3 * * *"
            :error="showErrors && !values.cron.trim()"
          />
          <template #error>{{ $t('error.requiredField') }}</template>
        </FormGroup>
      </div>
      <div class="col col-6">
        <FormGroup
          small-label
          :label="$t('backupsModal.timezone')"
          class="margin-bottom-2"
        >
          <PaginatedDropdown
            :value="values.timezone"
            :fetch-page="fetchTimezonePage"
            :add-empty-item="false"
            :initial-display-name="values.timezone"
            :fetch-on-open="true"
            :debounce-time="20"
            :page-size="timezonePageSize"
            :fixed-items="true"
            @input="(timezone) => (values.timezone = timezone)"
          ></PaginatedDropdown>
        </FormGroup>
      </div>
      <div class="col col-6">
        <FormGroup
          small-label
          :label="$t('backupsModal.keepLast')"
          :helper-text="$t('backupsModal.retentionHelp')"
          :error="showErrors && !isValidRetention(values.keep_last)"
          class="margin-bottom-2"
        >
          <FormInput
            v-model="values.keep_last"
            type="number"
            :min="1"
            :step="1"
            :error="showErrors && !isValidRetention(values.keep_last)"
          />
          <template #error>{{ $t('backupsModal.retentionInvalid') }}</template>
        </FormGroup>
      </div>
      <div class="col col-6">
        <FormGroup
          small-label
          :label="$t('backupsModal.keepDays')"
          :error="showErrors && !isValidRetention(values.keep_days)"
          class="margin-bottom-2"
        >
          <FormInput
            v-model="values.keep_days"
            type="number"
            :min="1"
            :step="1"
            :error="showErrors && !isValidRetention(values.keep_days)"
          />
          <template #error>{{ $t('backupsModal.retentionInvalid') }}</template>
        </FormGroup>
      </div>
      <div v-if="applications.length > 0" class="col col-12">
        <FormGroup
          small-label
          :label="$t('backupsModal.scope')"
          class="margin-bottom-2"
        >
          <Checkbox v-model="onlySelectedApplications">
            {{ $t('backupsModal.onlySelectedApplications') }}
          </Checkbox>
          <ApplicationSelector
            v-if="onlySelectedApplications"
            class="margin-top-1"
            :workspace="workspace"
            :selected-application-ids="selectedApplicationIds"
            @update="selectedApplicationIds = $event"
          />
        </FormGroup>
      </div>
      <div class="col col-12">
        <FormGroup
          small-label
          :label="$t('backupsModal.content')"
          class="margin-bottom-2"
        >
          <Checkbox v-model="values.only_structure">
            {{ $t('backupsModal.onlyStructure') }}
          </Checkbox>
          <Checkbox v-model="values.is_active">
            {{ $t('backupsModal.active') }}
          </Checkbox>
        </FormGroup>
      </div>
    </div>
    <div class="flex justify-content-end">
      <Button
        type="secondary"
        class="margin-right-1"
        @click.prevent="$emit('cancel')"
      >
        {{ $t('backupsModal.cancel') }}
      </Button>
      <Button :loading="loading" :disabled="loading">
        {{ $t('backupsModal.save') }}
      </Button>
    </div>
  </form>
</template>

<script>
import ApplicationSelector from '@baserow/modules/core/components/export/ApplicationSelector'
import PaginatedDropdown from '@baserow/modules/core/components/PaginatedDropdown'
import {
  fetchTimezonePage,
  TIMEZONE_PAGE_SIZE,
} from '@baserow/modules/core/utils/date'

// Mirrors `BackupSchedule.name` on the backend.
const NAME_MAX_LENGTH = 100

function isBlank(value) {
  return value === null || value === undefined || String(value).trim() === ''
}

/**
 * Empty means "keep every backup" and is sent as null. Anything else must be a
 * positive whole number, which is what the backend accepts.
 */
function isValidRetention(value) {
  return isBlank(value) || /^[1-9][0-9]*$/.test(String(value).trim())
}

function toRetention(value) {
  return isBlank(value) ? null : parseInt(String(value).trim(), 10)
}

export default {
  name: 'BackupScheduleForm',
  components: { ApplicationSelector, PaginatedDropdown },
  props: {
    schedule: {
      type: Object,
      required: false,
      default: null,
    },
    destinations: {
      type: Array,
      required: true,
    },
    // Only needed to scope the schedule to some applications. Without it the
    // schedule covers the whole workspace and the picker is not offered.
    workspace: {
      type: Object,
      required: false,
      default: null,
    },
    loading: {
      type: Boolean,
      default: false,
    },
  },
  emits: ['submit', 'cancel'],
  data() {
    const schedule = this.schedule || {}
    const applicationIds = schedule.application_ids ?? null
    return {
      showErrors: false,
      timezonePageSize: TIMEZONE_PAGE_SIZE,
      onlySelectedApplications: applicationIds !== null,
      selectedApplicationIds: applicationIds || [],
      values: {
        name: schedule.name || '',
        cron: schedule.cron || '0 3 * * *',
        timezone: schedule.timezone || 'UTC',
        destination: schedule.destination || '',
        keep_last: schedule.keep_last ?? '',
        keep_days: schedule.keep_days ?? '',
        only_structure: schedule.only_structure || false,
        is_active: schedule.is_active ?? true,
      },
    }
  },
  computed: {
    nameValid() {
      const name = this.values.name.trim()
      return name !== '' && name.length <= NAME_MAX_LENGTH
    },
    nameError() {
      return this.values.name.trim()
        ? this.$t('backupsModal.nameTooLong', { max: NAME_MAX_LENGTH })
        : this.$t('error.requiredField')
    },
    // An existing schedule can name a destination that has since been removed
    // from the configuration. It is shown as unavailable and must be replaced
    // before saving, rather than silently sent back.
    destinationUnavailable() {
      const name = this.values.destination
      return (
        !!name &&
        !this.destinations.some((destination) => destination.name === name)
      )
    },
    // The store only holds the applications of the workspace the user has open, so
    // the picker stays hidden on surfaces that target another workspace.
    applications() {
      return this.workspace
        ? this.$store.getters['application/getAllOfWorkspace'](this.workspace)
        : []
    },
  },
  methods: {
    isValidRetention,
    fetchTimezonePage,
    submit() {
      this.showErrors = true
      if (
        !this.nameValid ||
        !this.values.cron.trim() ||
        this.destinationUnavailable ||
        !isValidRetention(this.values.keep_last) ||
        !isValidRetention(this.values.keep_days)
      ) {
        return
      }
      const applicationIds =
        this.onlySelectedApplications && this.selectedApplicationIds.length
          ? this.selectedApplicationIds
          : null
      this.$emit('submit', {
        ...this.values,
        name: this.values.name.trim(),
        cron: this.values.cron.trim(),
        timezone: this.values.timezone.trim() || 'UTC',
        keep_last: toRetention(this.values.keep_last),
        keep_days: toRetention(this.values.keep_days),
        // Sent even when null, so editing a schedule back to covering the whole
        // workspace actually clears the previous selection.
        application_ids: applicationIds,
      })
    },
  },
}
</script>
