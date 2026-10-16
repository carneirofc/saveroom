<template>
  <Modal
    ref="modal"
    :right-sidebar="true"
    :right-sidebar-scrollable="true"
    :close-button="false"
    :can-close="!uploadingBeforeJobCreated"
    @show="onShow"
  >
    <template #content>
      <div class="import-modal__header">
        <h2 class="import-modal__title">
          {{
            $t('importFileModal.additionalImportTitle', {
              table: table.name,
            })
          }}
        </h2>
        <div class="modal__actions"></div>
      </div>

      <div class="control margin-bottom-2">
        <FormGroup
          :label="$t('importFileModal.importLabel')"
          small-label
          required
        >
          <ul class="choice-items margin-top-1">
            <li v-for="importerType in importerTypes" :key="importerType.type">
              <a
                class="choice-items__link"
                :class="{
                  active: importer === importerType.type,
                  disabled: importInProgress || restoredFromStore,
                }"
                @click="onImporterClick(importerType.type)"
              >
                <i
                  class="choice-items__icon"
                  :class="importerType.iconClass"
                ></i>
                <span> {{ importerType.getName() }}</span>
                <i
                  v-if="importer === importerType.type"
                  class="choice-items__icon-active iconoir-check-circle"
                ></i>
              </a>
            </li>
          </ul>
        </FormGroup>
      </div>

      <div
        v-if="restoredFromStore && job?.original_file_name"
        class="margin-bottom-2"
      >
        <p>
          {{
            $t('importFileModal.restoredFile', { name: job.original_file_name })
          }}
        </p>
      </div>

      <div v-if="!restoredFromStore" class="margin-bottom-2">
        <component
          :is="importerComponent"
          ref="importerRef"
          :disabled="importInProgress"
          @changed="reset()"
          @header="onHeader($event)"
          @data="onData($event)"
          @get-data="onGetData($event)"
        >
          <template #upsertMapping>
            <FormGroup
              :label="$t('importFileModal.modeLabel')"
              small-label
              class="margin-top-1"
            >
              <RadioGroup
                v-model="mode"
                :options="modeOptions"
                vertical-layout
              ></RadioGroup>
              <p class="control__description margin-top-1">
                {{ modeDescription }}
              </p>
              <p
                v-if="!canReplaceRows"
                class="control__description margin-top-1"
              >
                {{ $t('importFileModal.replaceNotAllowed') }}
              </p>
            </FormGroup>

            <FormGroup
              v-if="isMatchingMode"
              :label="$t('importFileModal.matchFieldsLabel')"
              :helper-text="$t('importFileModal.matchFieldsHelp')"
              small-label
              required
              class="margin-top-2"
            >
              <p v-if="availableUpsertFields.length === 0">
                {{ $t('importFileModal.matchFieldsEmpty') }}
              </p>
              <div v-else class="import-modal__match-fields">
                <Checkbox
                  v-for="field in availableUpsertFields"
                  :key="field.id"
                  :checked="matchFieldIds.includes(field.id)"
                  :disabled="importInProgress"
                  @input="toggleMatchField(field.id, $event)"
                  >{{ field.name }}</Checkbox
                >
              </div>
              <Checkbox
                v-model="deleteUnmatched"
                :disabled="importInProgress || !canReplaceRows"
                class="margin-top-2"
                >{{ $t('importFileModal.deleteUnmatched') }}</Checkbox
              >
            </FormGroup>

            <Alert v-if="isDestructive" type="warning" class="margin-top-2">
              {{ $t('importFileModal.replaceWarning') }}
            </Alert>
          </template>
        </component>
      </div>

      <ImportErrorReport :job="job" :error="error"></ImportErrorReport>

      <Alert
        v-if="preview && preview.ambiguous.length > 0"
        type="warning"
        class="margin-bottom-2"
      >
        <template #title>{{ $t('importFileModal.ambiguousTitle') }}</template>
        <p>{{ $t('importFileModal.ambiguousMessage') }}</p>
        <ul>
          <li v-for="(key, index) in preview.ambiguous" :key="index">
            {{
              $t('importFileModal.ambiguousKey', {
                values: key.values.join(' / '),
                fileCount: key.file_count,
                tableCount: key.table_count,
              })
            }}
          </li>
        </ul>
        <Checkbox
          v-model="allowAmbiguousMatches"
          :disabled="importInProgress"
          >{{ $t('importFileModal.allowAmbiguous') }}</Checkbox
        >
      </Alert>

      <Alert v-if="previewStale" type="info" class="margin-bottom-2">
        {{ $t('importFileModal.previewStale') }}
      </Alert>

      <Tabs
        v-if="dataLoaded"
        :key="preview ? 'with-changes' : 'without-changes'"
        header-no-padding
        content-no-x-padding
      >
        <Tab v-if="preview" :title="$t('importFileModal.changesTab')">
          <ImportDiffPreview
            :preview="preview"
            :fields="mappedFields"
            :all-fields="sortedFields"
            :get-imported-row="getImportedRow"
          />
        </Tab>
        <Tab :title="$t('importFileModal.importPreview')">
          <SimpleGrid
            class="import-modal__preview"
            :rows="previewImportData"
            :fields="sortedFields"
            :field-options="importFieldOptions"
          />
        </Tab>
        <Tab :title="$t('importFileModal.filePreview')">
          <SimpleGrid
            class="import-modal__preview"
            :rows="previewFileData"
            :fields="fileFields"
            :field-options="fileFieldOptions"
          />
        </Tab>
      </Tabs>

      <Alert
        v-if="pendingChangeCount > 0"
        type="warning"
        class="margin-bottom-2"
      >
        {{
          $t('importFileModal.pendingChanges', { count: pendingChangeCount })
        }}
      </Alert>

      <div v-if="!hasErrors" class="modal-progress__actions">
        <ProgressBar
          v-if="importInProgress && showProgressBar"
          :value="progressPercentage"
          :status="humanReadableState"
        />
        <ButtonText
          v-if="jobIsRunning || cancelLoading"
          tag="a"
          type="secondary"
          class="modal-progress__cancel-button"
          :loading="cancelLoading"
          @click="cancelJob"
        >
          {{ $t('action.cancel') }}
        </ButtonText>
        <p
          v-if="isDestructive && !hasFreshPreview && canBePreviewed"
          class="control__description margin-bottom-1"
        >
          {{ $t('importFileModal.previewRequired') }}
        </p>
        <Button
          v-if="!importInProgress"
          type="secondary"
          size="large"
          full-width
          class="margin-bottom-1"
          :loading="previewLoading"
          :disabled="previewLoading || !canBePreviewed"
          @click="previewChanges"
        >
          {{ $t('importFileModal.previewChanges') }}
        </Button>
        <Button
          type="primary"
          size="large"
          full-width
          class="modal-progress__primary-button"
          :loading="importInProgress || (jobIsFinished && !isTableCreated)"
          :disabled="
            importInProgress ||
            previewLoading ||
            !canBeSubmitted ||
            (jobIsFinished && !isTableCreated)
          "
          @click="submitted"
        >
          {{ $t('importFileModal.importButton') }}
        </Button>
      </div>
      <div v-else class="align-right">
        <Button
          type="primary"
          size="large"
          :loading="!isTableCreated"
          @click="openTable()"
        >
          {{ $t('importFileModal.showTable') }}
        </Button>
      </div>
    </template>
    <template #sidebar>
      <div class="import-modal__field-mapping">
        <div v-if="header.length > 0" class="import-modal__field-mapping-body">
          <h3>{{ $t('importFileModal.fieldMappingTitle') }}</h3>
          <p>
            {{ $t('importFileModal.fieldMappingDescription') }}
          </p>
          <FormGroup
            v-for="(head, index) in header"
            :key="head"
            :label="head"
            small-label
            required
            class="margin-bottom-2"
          >
            <Dropdown v-model="mapping[index]">
              <DropdownItem name="Skip" :value="0" icon="ban" />
              <DropdownItem
                v-for="field in availableFields"
                :key="field.id"
                :name="field.name"
                :value="field.id"
                :icon="field._.type.iconClass"
                :disabled="
                  selectedFields.includes(field.id) &&
                  field.id !== mapping[index]
                "
              />
            </Dropdown>
          </FormGroup>
        </div>
        <div v-else class="import-modal__field-mapping--empty">
          <i class="import-modal__field-mapping-empty-icon iconoir-shuffle" />
          <div class="import-modal__field-mapping-empty-text">
            {{ $t('importFileModal.selectImportMessage') }}
          </div>
        </div>
      </div>
      <div v-if="!uploadingBeforeJobCreated" class="modal__actions">
        <a class="modal__close" @click="hide()">
          <i class="iconoir-xmark"></i>
        </a>
      </div>

      <ConfirmImportModal
        ref="confirmImportModal"
        :table="table"
        :summary="preview && preview.summary"
        :destructive="isDestructive"
        :protected-table="tableIsProtected"
        @confirmed="runImport"
      />
    </template>
  </Modal>
</template>

<script>
import modal from '@baserow/modules/core/mixins/modal'
import error from '@baserow/modules/core/mixins/error'
import job from '@baserow/modules/core/mixins/job'
import TableService from '@baserow/modules/database/services/table'
import {
  uuid,
  getNextAvailableNameInSequence,
} from '@baserow/modules/core/utils/string'
import SimpleGrid from '@baserow/modules/database/components/view/grid/SimpleGrid'
import {
  IMPORT_MATCHING_MODES,
  IMPORT_MODES,
  IMPORT_MODE_INSERT,
  IMPORT_MODE_REPLACE,
  buildImportConfiguration,
  buildImportPayload,
  getFieldMapping,
} from '@baserow/modules/database/utils/import'

import { ResponseErrorMessage } from '@baserow/modules/core/plugins/clientHandler'
import ImportErrorReport from '@baserow/modules/database/components/table/ImportErrorReport.vue'
import ImportDiffPreview from '@baserow/modules/database/components/table/ImportDiffPreview.vue'
import ConfirmImportModal from '@baserow/modules/database/components/table/ConfirmImportModal.vue'
import { isProtected } from '@baserow/modules/database/utils/editConfirmation'
import { FileImportJobType } from '@baserow/modules/database/jobTypes'
import { pageFinished } from '@baserow/modules/core/utils/routing'
import { nextTick, useNuxtApp } from '#imports'

export default {
  name: 'ImportFileModal',
  components: {
    ImportErrorReport,
    ImportDiffPreview,
    ConfirmImportModal,
    SimpleGrid,
  },
  mixins: [modal, error, job],
  props: {
    database: {
      type: Object,
      required: true,
    },
    table: {
      type: Object,
      required: false,
      default: null,
    },
    fields: {
      type: Array,
      required: false,
      default: () => [],
    },
  },
  emits: ['table-refresh'],
  setup() {
    const nuxtApp = useNuxtApp()
    return { nuxtApp }
  },
  data() {
    return {
      importer: '',
      restoredFromStore: false,
      uploadProgressPercentage: 0,
      importState: null,
      showProgressBar: false,
      header: [],
      mapping: {},
      getData: null,
      previewData: [],
      dataLoaded: false,
      // Incremented every time the file data changes, to invalidate the caches.
      dataVersion: 0,
      mode: IMPORT_MODE_INSERT,
      matchFieldIds: [],
      deleteUnmatched: false,
      allowAmbiguousMatches: false,
      preview: null,
      previewSettingsKey: null,
      previewLoading: false,
      // The raw and prepared file data, reused between the preview and the import.
      prepared: null,
    }
  },
  computed: {
    sortedFields() {
      // The sort needs to follow the same sort logic as
      // RowHandler.import_rows(...) in the backend
      return [...this.fields].sort((a, b) => {
        const aPrimary = !!a.primary
        const bPrimary = !!b.primary
        if (aPrimary !== bPrimary) return aPrimary ? -1 : 1
        const orderDiff = (a.order ?? 0) - (b.order ?? 0)
        if (orderDiff !== 0) return orderDiff
        return a.id - b.id
      })
    },
    isTableCreated() {
      if (!this.job?.table_id) {
        return false
      }
      return this.database.tables.some(({ id }) => id === this.job.table_id)
    },
    mappingNotEmpty() {
      return Object.values(this.mapping).some(
        (value) => this.fieldIndexMap[value] !== undefined
      )
    },
    tableIsProtected() {
      return isProtected(this.table)
    },
    /**
     * The number of staged, not yet saved cell changes of the table. An import
     * would race with them, so it's blocked while there are any.
     */
    pendingChangeCount() {
      if (!this.table) {
        return 0
      }
      return this.$store.getters['pendingRowChanges/count'](this.table.id)
    },
    /**
     * Trashing the existing rows of a table needs more than the permission to
     * import into it.
     */
    canReplaceRows() {
      return (
        !!this.table &&
        this.$hasPermission(
          'database.table.replace_rows',
          this.table,
          this.database.workspace.id
        )
      )
    },
    modeOptions() {
      const labels = {
        insert: this.$t('importFileModal.modeInsert'),
        upsert: this.$t('importFileModal.modeUpsert'),
        update: this.$t('importFileModal.modeUpdate'),
        replace: this.$t('importFileModal.modeReplace'),
      }
      return IMPORT_MODES.map((value) => ({
        value,
        label: labels[value],
        disabled:
          this.importInProgress ||
          (value === IMPORT_MODE_REPLACE && !this.canReplaceRows),
      }))
    },
    modeDescription() {
      const descriptions = {
        insert: this.$t('importFileModal.modeInsertDescription'),
        upsert: this.$t('importFileModal.modeUpsertDescription'),
        update: this.$t('importFileModal.modeUpdateDescription'),
        replace: this.$t('importFileModal.modeReplaceDescription'),
      }
      return descriptions[this.mode]
    },
    isMatchingMode() {
      return IMPORT_MATCHING_MODES.includes(this.mode)
    },
    /**
     * The selected match fields that are still mapped, in the field order.
     */
    activeMatchFieldIds() {
      if (!this.isMatchingMode) {
        return []
      }
      return this.availableUpsertFields
        .map((field) => field.id)
        .filter((id) => this.matchFieldIds.includes(id))
    },
    isDestructive() {
      return (
        this.mode === IMPORT_MODE_REPLACE ||
        (this.isMatchingMode && this.deleteUnmatched)
      )
    },
    /**
     * Identifies everything the preview depends on. When it changes, the current
     * preview doesn't reflect what would be imported anymore.
     */
    settingsKey() {
      return JSON.stringify({
        dataVersion: this.dataVersion,
        mapping: this.mapping,
        mode: this.mode,
        matchFieldIds: this.activeMatchFieldIds,
        deleteUnmatched: this.isMatchingMode && this.deleteUnmatched,
        allowAmbiguousMatches:
          this.isMatchingMode && this.allowAmbiguousMatches,
      })
    },
    hasFreshPreview() {
      return !!this.preview && this.previewSettingsKey === this.settingsKey
    },
    previewStale() {
      return !!this.preview && !this.hasFreshPreview
    },
    canBePreviewed() {
      return (
        !!this.importer &&
        typeof this.getData === 'function' &&
        this.mappingNotEmpty &&
        (!this.isMatchingMode || this.activeMatchFieldIds.length > 0)
      )
    },
    canBeSubmitted() {
      if (!this.canBePreviewed) {
        return false
      }
      // Saving the staged changes afterwards would overwrite what was imported.
      if (this.pendingChangeCount > 0) {
        return false
      }
      if (this.isDestructive && !this.canReplaceRows) {
        return false
      }
      // Rows are trashed, the user must see what is going to happen first.
      if (this.isDestructive && !this.hasFreshPreview) {
        return false
      }
      if (this.hasFreshPreview && this.preview.ambiguous_blocked) {
        return false
      }
      return true
    },
    fieldTypes() {
      return this.$registry.getAll('field')
    },
    fileFields() {
      return this.header.map((header, index) => ({
        type: 'text',
        name: header,
        id: uuid(),
        order: index,
      }))
    },
    importFieldOptions() {
      return Object.fromEntries(
        this.sortedFields.map((field) => [field.id, { hidden: false }])
      )
    },
    fileFieldOptions() {
      return Object.fromEntries(
        this.fileFields.map((field) => [field.id, { hidden: false }])
      )
    },
    /**
     * All writable fields.
     */
    writableFields() {
      return this.sortedFields.filter((field) =>
        this.fieldTypes[field.type].canWriteFieldValues(field)
      )
    },
    /**
     * Map beetween the field id and its index in the array.
     */
    fieldIndexMap() {
      return Object.fromEntries(
        this.writableFields.map((field, index) => [field.id, index])
      )
    },
    /**
     * All writable fields that can be imported into
     */
    availableFields() {
      return this.writableFields.filter(({ type }) =>
        this.fieldTypes[type].getCanImport()
      )
    },
    fieldMapping() {
      return getFieldMapping(this.mapping, this.fieldIndexMap)
    },
    /**
     * The fields mapped to a file column, in the field order.
     */
    mappedFields() {
      const mappedIndexes = new Set(
        this.fieldMapping.map(([, fieldIndex]) => fieldIndex)
      )
      return this.writableFields.filter((field, index) =>
        mappedIndexes.has(index)
      )
    },
    previewFileData() {
      return this.previewData.map((row) => {
        const newRow = Object.fromEntries(
          this.fileFields.map((field, index) => [
            `field_${field.id}`,
            `${row[index]}`,
          ])
        )
        newRow.id = uuid()
        return newRow
      })
    },
    previewImportData() {
      return this.previewData.map((row) => {
        const newRow = this.toImportedRow(row)
        newRow.id = uuid()
        return newRow
      })
    },

    /**
     * Fields that are mapped to a column
     */
    selectedFields() {
      return Object.values(this.mapping)
    },
    availableUpsertFields() {
      const selected = Object.values(this.mapping)
      return this.sortedFields.filter((field) => {
        return (
          selected.includes(field.id) && this.fieldTypes[field.type].canUpsert()
        )
      })
    },
    progressPercentage() {
      switch (this.state) {
        case null:
          return 0
        case 'preparingData':
          return 1
        case 'uploading':
          // 10% -> 50%
          return (this.uploadProgressPercentage / 100) * 40 + 10
        default:
          // 50% -> 100%
          return 50 + this.job.progress_percentage / 2
      }
    },
    state() {
      if (this.job === null) {
        return this.importState
      } else {
        return this.job.state
      }
    },
    importInProgress() {
      return (
        this.state !== null &&
        !this.jobIsFinished &&
        !this.jobHasFailed &&
        !this.error.visible
      )
    },
    // True only while uploading the file before the backend job exists.
    // Once the job is created the user can close the modal — the running job
    // is in the store and will be restored on reopen.
    uploadingBeforeJobCreated() {
      return this.job === null && this.importInProgress
    },
    importerTypes() {
      return this.$registry.getAll('importer')
    },
    importerComponent() {
      return this.importer === ''
        ? null
        : this.$registry.get('importer', this.importer).getFormComponent()
    },
    humanReadableState() {
      switch (this.state) {
        case null:
          return ''
        case 'preparingData':
          return this.$t('importFileModal.preparing')
        case 'uploading':
          if (this.uploadProgressPercentage === 100) {
            return this.$t('job.statePending')
          } else {
            return this.$t('importFileModal.uploading')
          }
        default:
          return this.jobHumanReadableState
      }
    },
    hasErrors() {
      return this.job && Object.keys(this.job.report.failing_rows).length > 0
    },
  },
  methods: {
    getDefaultName() {
      const excludeNames = this.database.tables.map((table) => table.name)
      const baseName = this.$t('importFileModal.defaultName')
      return getNextAvailableNameInSequence(baseName, excludeNames)
    },
    reset(full = true) {
      this.job = null
      this.restoredFromStore = false
      this.uploadProgressPercentage = 0
      if (full) {
        this.header = []
        this.importState = null
        this.mapping = {}
        this.getData = null
        this.previewData = []
        this.dataLoaded = false
        this.invalidateData()
      }
      this.hideError()
    },
    invalidateData() {
      this.dataVersion += 1
      this.prepared = null
      this.preview = null
      this.previewSettingsKey = null
    },
    onImporterClick(type) {
      // Don't let the user change the importer while a job is in progress
      // or a running job is being restored.
      if (this.importInProgress || this.restoredFromStore) {
        return
      }
      this.importer = type
      this.reset()
    },
    getAutoMapping(header) {
      return Object.fromEntries(
        header.map((name, index) => {
          const foundField = this.availableFields.find(
            ({ name: fieldName }) => fieldName === name
          )
          return [index, foundField ? foundField.id : 0]
        })
      )
    },
    onData({ header, previewData }) {
      this.header = header
      this.previewData = previewData
      this.mapping = this.getAutoMapping(header)
      this.dataLoaded = header.length > 0 || previewData.length > 0
      this.invalidateData()
    },
    onGetData(getData) {
      this.getData = getData
      this.invalidateData()
    },
    onHeader(header) {
      this.header = header
      this.mapping = this.getAutoMapping(header)
      this.invalidateData()
    },
    toggleMatchField(fieldId, checked) {
      const others = this.matchFieldIds.filter((id) => id !== fieldId)
      this.matchFieldIds = checked ? [...others, fieldId] : others
    },
    /**
     * Converts a raw file row into a row object as displayed in the grid.
     */
    toImportedRow(row) {
      return Object.fromEntries(
        this.fieldMapping.map(([importIndex, fieldIndex]) => {
          const field = this.writableFields[fieldIndex]
          return [
            `field_${field.id}`,
            this.fieldTypes[field.type].prepareValueForPaste(
              field,
              `${row[importIndex]}`,
              row[importIndex]
            ),
          ]
        })
      )
    },
    getImportedRow(importIndex) {
      const row = this.prepared?.rawData[importIndex]
      return row ? this.toImportedRow(row) : {}
    },
    getSkippedFieldIds() {
      const mappedFieldIds = Object.values(this.mapping).filter(
        (id) => id !== 0
      )
      return this.writableFields
        .filter((field) => !mappedFieldIds.includes(field.id))
        .map((field) => field.id)
    },
    /**
     * Reads and prepares the whole file once for the current mapping and match
     * fields, so that the preview and the import send exactly the same data.
     */
    async prepareData() {
      const key = JSON.stringify({
        dataVersion: this.dataVersion,
        mapping: this.mapping,
        matchFieldIds: this.activeMatchFieldIds,
      })
      if (this.prepared?.key === key) {
        return this.prepared
      }
      const rawData = await this.getData()
      const { data, upsertValues } = await buildImportPayload(rawData, {
        mapping: this.mapping,
        writableFields: this.writableFields,
        fieldTypes: this.fieldTypes,
        fieldIndexMap: this.fieldIndexMap,
        upsertFieldIds: this.activeMatchFieldIds,
        onChunk: () => this.$ensureRender(),
      })
      this.prepared = { key, rawData, data, upsertValues }
      return this.prepared
    },
    getImportConfiguration(upsertValues) {
      return buildImportConfiguration({
        mode: this.mode,
        upsertFieldIds: this.activeMatchFieldIds,
        upsertValues,
        skippedFieldIds: this.getSkippedFieldIds(),
        deleteUnmatched: this.deleteUnmatched,
        allowAmbiguousMatches: this.allowAmbiguousMatches,
      })
    },
    async previewChanges() {
      this.hideError()
      this.previewLoading = true
      const settingsKey = this.settingsKey
      try {
        const { data, upsertValues } = await this.prepareData()
        const { data: preview } = await TableService(
          this.$client
        ).previewImport(
          this.table.id,
          data,
          this.getImportConfiguration(upsertValues)
        )
        this.preview = preview
        this.previewSettingsKey = settingsKey
        return true
      } catch (error) {
        this.handleError(error, 'application')
        return false
      } finally {
        this.previewLoading = false
      }
    },
    /**
     * An import changes a whole set of rows at once, so it is never sent straight
     * away: the preview is refreshed if needed and the user has to accept the
     * changes it reports first.
     */
    async submitted() {
      this.hideError()

      if (!this.hasFreshPreview && !(await this.previewChanges())) {
        return
      }
      if (this.preview?.ambiguous_blocked) {
        return
      }

      this.$refs.confirmImportModal.show()
    },
    /**
     * When the form is submitted we try to extract the initial data and first row
     * header setting from the values. An importer could have added those, but they
     * need to be removed from the values.
     */
    async runImport() {
      this.showProgressBar = false
      this.reset(false)
      let data = null
      let configuration = null

      if (typeof this.getData === 'function') {
        try {
          this.showProgressBar = true
          this.importState = 'preparingData'
          await this.$ensureRender()

          const prepared = await this.prepareData()
          data = prepared.data
          configuration = this.getImportConfiguration(prepared.upsertValues)
        } catch (error) {
          this.importState = null
          this.handleError(error, 'application')
          return
        }
      }

      this.importState = 'uploading'

      const onUploadProgress = ({ loaded, total }) =>
        (this.uploadProgressPercentage = (loaded / total) * 100)

      try {
        if (data && data.length > 0) {
          this.showProgressBar = true
        }

        const { data: job } = await TableService(this.$client).importData(
          this.table.id,
          data,
          {
            onUploadProgress,
          },
          configuration,
          {
            importer_type: this.importer,
            original_file_name: this.$refs.importerRef?.values?.filename || '',
          }
        )
        await this.createAndMonitorJob(job)
      } catch (error) {
        this.handleError(error, 'application', {
          ERROR_MAX_JOB_COUNT_EXCEEDED: new ResponseErrorMessage(
            this.$t('job.errorJobAlreadyRunningTitle'),
            this.$t('job.errorJobAlreadyRunningDescription')
          ),
        })
      }
    },
    getCustomHumanReadableJobState(jobState) {
      const translations = {
        'row-import-creation': this.$t('importFileModal.stateRowCreation'),
        'row-import-validation': this.$t('importFileModal.statePreValidation'),
        'import-create-table': this.$t('importFileModal.stateCreateTable'),
      }
      return translations[jobState]
    },
    async openTable() {
      // Redirect to the newly created table.
      await this.$router.push({
        name: 'database-table',
        params: {
          databaseId: this.database.id,
          tableId: this.job.table_id,
        },
      })
      await pageFinished(this.nuxtApp)
      await nextTick()
      this.hide()
    },
    onJobFinished() {
      this.$bus.$emit('table-refresh', {
        tableId: this.job.table_id,
      })
      if (!this.hasErrors) {
        this.hide()
      }
    },
    onJobFailed() {
      this.showError(
        new ResponseErrorMessage(
          this.$t('importFileModal.importError'),
          this.job.human_readable_error
        )
      )
    },
    onJobCancelled() {
      this.importer = ''
      this.reset()
    },
    onShow() {
      this.importer = ''
      this.mode = IMPORT_MODE_INSERT
      this.matchFieldIds = []
      this.deleteUnmatched = false
      this.allowAmbiguousMatches = false
      this.reset()
      this.loadRunningJob()
    },
    loadRunningJob() {
      const runningJob = this.$store.getters['job/getUnfinishedJobs'].find(
        (j) =>
          j.type === FileImportJobType.getType() &&
          j.table_id === this.table?.id
      )
      if (runningJob) {
        this.job = runningJob
        this.restoredFromStore = true
        this.showProgressBar = true
        // Restore the importer type if it's still registered; otherwise the
        // modal shows just the progress bar + file name.
        if (
          runningJob.importer_type &&
          this.$registry.exists('importer', runningJob.importer_type)
        ) {
          this.importer = runningJob.importer_type
        }
      }
    },
  },
}
</script>
