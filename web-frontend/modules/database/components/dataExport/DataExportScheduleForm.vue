<template>
  <form @submit.prevent="submit">
    <div class="row">
      <div class="col col-6">
        <FormGroup
          small-label
          required
          :label="$t('dataExportModal.name')"
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
          required
          :label="$t('dataExportModal.destination')"
          :error="(showErrors && !values.destination) || destinationUnavailable"
          class="margin-bottom-2"
        >
          <Dropdown v-model="values.destination">
            <DropdownItem
              v-for="item in destinations"
              :key="item.name"
              :name="`${item.name} (${item.type})`"
              :value="item.name"
            ></DropdownItem>
            <DropdownItem
              v-if="destinationUnavailable"
              :name="
                $t('dataExportModal.unavailableDestination', {
                  name: values.destination,
                })
              "
              :value="values.destination"
              disabled
            ></DropdownItem>
          </Dropdown>
          <template #error>
            {{
              destinationUnavailable
                ? $t('dataExportModal.unavailableDestinationError')
                : $t('error.requiredField')
            }}
          </template>
        </FormGroup>
      </div>
      <div class="col col-6">
        <FormGroup
          small-label
          required
          :label="$t('dataExportModal.cron')"
          :helper-text="$t('dataExportModal.cronHelp')"
          :error="showErrors && !values.cron.trim()"
          class="margin-bottom-2"
        >
          <FormInput
            v-model="values.cron"
            placeholder="0 * * * *"
            :error="showErrors && !values.cron.trim()"
          />
          <template #error>{{ $t('error.requiredField') }}</template>
        </FormGroup>
      </div>
      <div class="col col-6">
        <FormGroup
          small-label
          :label="$t('dataExportModal.timezone')"
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
          :label="$t('dataExportModal.fullEveryN')"
          :helper-text="$t('dataExportModal.fullEveryNHelp')"
          :error="showErrors && !fullEveryNValid"
          class="margin-bottom-2"
        >
          <FormInput
            v-model="values.full_every_n"
            type="number"
            :min="0"
            :step="1"
            :error="showErrors && !fullEveryNValid"
          />
          <template #error>{{
            $t('dataExportModal.fullEveryNInvalid')
          }}</template>
        </FormGroup>
      </div>
      <div class="col col-6">
        <FormGroup
          small-label
          :label="$t('dataExportModal.columnNaming')"
          :helper-text="$t('dataExportModal.columnNamingHelp')"
          class="margin-bottom-2"
        >
          <Dropdown v-model="values.column_naming">
            <DropdownItem
              :name="$t('dataExportModal.columnNamingFieldId')"
              value="field_id"
            ></DropdownItem>
            <DropdownItem
              :name="$t('dataExportModal.columnNamingFieldName')"
              value="field_name"
            ></DropdownItem>
          </Dropdown>
        </FormGroup>
      </div>
      <div class="col col-12">
        <FormGroup
          small-label
          :label="$t('dataExportModal.tables')"
          :error="showErrors && !allTables && selectedTableIds.length === 0"
          class="margin-bottom-2"
        >
          <Checkbox v-model="allTables">
            {{ $t('dataExportModal.allTables') }}
          </Checkbox>
          <template v-if="!allTables">
            <Checkbox
              v-for="table in database.tables || []"
              :key="table.id"
              v-model="tableSelection[table.id]"
            >
              {{ table.name }}
            </Checkbox>
          </template>
          <template #error>{{ $t('dataExportModal.selectTables') }}</template>
        </FormGroup>
      </div>
      <div class="col col-12">
        <FormGroup
          small-label
          :label="$t('dataExportModal.status')"
          class="margin-bottom-2"
        >
          <Checkbox v-model="values.is_active">
            {{ $t('dataExportModal.active') }}
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
        {{ $t('dataExportModal.cancel') }}
      </Button>
      <Button :loading="loading" :disabled="loading">
        {{ $t('dataExportModal.save') }}
      </Button>
    </div>
  </form>
</template>

<script>
import PaginatedDropdown from '@baserow/modules/core/components/PaginatedDropdown'
import {
  fetchTimezonePage,
  TIMEZONE_PAGE_SIZE,
} from '@baserow/modules/core/utils/date'

// Mirrors the name length of the export schedule on the backend.
const NAME_MAX_LENGTH = 100

// The backend accepts any whole number from zero up (zero only exports fully when
// required) and the field is not nullable.
function isValidFullEveryN(value) {
  return /^(0|[1-9][0-9]*)$/.test(String(value ?? '').trim())
}

export default {
  name: 'DataExportScheduleForm',
  components: { PaginatedDropdown },
  props: {
    schedule: {
      type: Object,
      required: false,
      default: null,
    },
    database: {
      type: Object,
      required: true,
    },
    destinations: {
      type: Array,
      required: true,
    },
    loading: {
      type: Boolean,
      default: false,
    },
  },
  emits: ['submit', 'cancel'],
  data() {
    const schedule = this.schedule || {}
    const tableIds = schedule.table_ids ?? null
    const tableSelection = {}
    for (const table of this.database.tables || []) {
      tableSelection[table.id] =
        tableIds !== null && tableIds.includes(table.id)
    }
    return {
      showErrors: false,
      timezonePageSize: TIMEZONE_PAGE_SIZE,
      allTables: tableIds === null,
      tableSelection,
      values: {
        name: schedule.name || '',
        cron: schedule.cron || '0 * * * *',
        timezone: schedule.timezone || 'UTC',
        destination: schedule.destination || this.destinations[0]?.name || '',
        full_every_n: schedule.full_every_n ?? 24,
        column_naming: schedule.column_naming || 'field_id',
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
        ? this.$t('dataExportModal.nameTooLong', { max: NAME_MAX_LENGTH })
        : this.$t('error.requiredField')
    },
    // An existing schedule can name a storage that has since been removed from
    // the configuration. It is shown as unavailable and must be replaced before
    // saving, rather than silently sent back.
    destinationUnavailable() {
      const name = this.values.destination
      return (
        !!name &&
        !this.destinations.some((destination) => destination.name === name)
      )
    },
    fullEveryNValid() {
      return isValidFullEveryN(this.values.full_every_n)
    },
    selectedTableIds() {
      return Object.entries(this.tableSelection)
        .filter(([, selected]) => selected)
        .map(([id]) => parseInt(id, 10))
    },
  },
  methods: {
    fetchTimezonePage,
    submit() {
      this.showErrors = true
      if (
        !this.nameValid ||
        !this.values.cron.trim() ||
        !this.values.destination ||
        this.destinationUnavailable ||
        !this.fullEveryNValid ||
        (!this.allTables && this.selectedTableIds.length === 0)
      ) {
        return
      }
      this.$emit('submit', {
        ...this.values,
        name: this.values.name.trim(),
        cron: this.values.cron.trim(),
        timezone: this.values.timezone.trim() || 'UTC',
        full_every_n: parseInt(String(this.values.full_every_n).trim(), 10),
        table_ids: this.allTables ? null : this.selectedTableIds,
      })
    },
  },
}
</script>
