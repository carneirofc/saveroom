<template>
  <Modal ref="modal" :full-screen="false" :close-button="true">
    <h2 class="box__title">
      {{ $t('dataExportModal.title', { name: database.name }) }}
    </h2>
    <p>{{ $t('dataExportModal.description') }}</p>
    <Error :error="error"></Error>
    <div v-if="loading" class="loading margin-top-2 margin-bottom-2"></div>
    <template v-else-if="loaded">
      <DataExportScheduleForm
        v-if="editing"
        :schedule="editingSchedule"
        :database="database"
        :destinations="destinations"
        :loading="saving"
        @submit="save"
        @cancel="editing = false"
      />
      <template v-else>
        <!-- Existing schedules stay listed without any storage, so they can still
        be inspected, edited or deleted after their storage was removed. -->
        <p v-if="destinations.length === 0">
          {{
            isStaff
              ? $t('dataExportModal.noDestinationsStaff')
              : $t('dataExportModal.noDestinations')
          }}
        </p>
        <Button v-else icon="iconoir-plus" @click="edit(null)">
          {{ $t('dataExportModal.newSchedule') }}
        </Button>
        <BackupList
          :empty="schedules.length === 0"
          :empty-text="$t('dataExportModal.noSchedules')"
        >
          <BackupListItem
            v-for="schedule in schedules"
            :key="schedule.id"
            :title="schedule.name"
          >
            <template #title-extra>
              <template v-if="!schedule.is_active">
                ({{ $t('dataExportModal.inactive') }})
              </template>
            </template>
            <template #detail>
              <code>{{ schedule.cron }}</code> {{ schedule.timezone }} ·
              {{ schedule.destination }} ·
              {{ tablesLabel(schedule) }}
              <template v-if="schedule.is_active">
                ·
                {{
                  $t('dataExportModal.nextRunOn', {
                    date: formatDate(schedule.next_run_on),
                  })
                }}
              </template>
              <template v-if="schedule.last_run_on">
                ·
                {{
                  $t('dataExportModal.lastRunOn', {
                    date: formatDate(schedule.last_run_on),
                  })
                }}
              </template>
            </template>
            <template #badges>
              <Badge color="neutral" size="small">
                {{
                  schedule.table_ids === null
                    ? $t('dataExportModal.allTables')
                    : $t(
                        'dataExportModal.tableCount',
                        schedule.table_ids.length
                      )
                }}
              </Badge>
              <Badge color="cyan" size="small">
                {{
                  $t('dataExportModal.columnNamingBadge', {
                    naming:
                      schedule.column_naming === 'field_name'
                        ? $t('dataExportModal.columnNamingFieldName')
                        : $t('dataExportModal.columnNamingFieldId'),
                  })
                }}
              </Badge>
            </template>
            <template #error>
              <div
                v-for="warning in schedule.warnings"
                :key="warning"
                class="backups__detail color-warning"
              >
                {{ warning }}
              </div>
              <div v-if="schedule.last_error" class="backups__error">
                {{ schedule.last_error }}
              </div>
            </template>
            <template #actions>
              <Button
                v-if="canRun(schedule)"
                type="secondary"
                size="small"
                :loading="busyId === schedule.id"
                :disabled="busyId !== null"
                @click="run(schedule, 'auto')"
              >
                {{ $t('dataExportModal.runNow') }}
              </Button>
              <Button
                type="secondary"
                size="small"
                icon="iconoir-list"
                :title="$t('dataExportModal.runs')"
                :aria-label="$t('dataExportModal.runs')"
                @click="toggleRuns(schedule)"
              ></Button>
              <Button
                :ref="`more-${schedule.id}`"
                type="secondary"
                size="small"
                icon="iconoir-more-horiz"
                :title="$t('dataExportModal.more')"
                :aria-label="$t('dataExportModal.more')"
                @click="toggleMore(schedule)"
              ></Button>
              <Context
                :ref="`moreContext-${schedule.id}`"
                overflow-scroll
                max-height-if-outside-viewport
              >
                <ul class="context__menu">
                  <li v-if="canRun(schedule)" class="context__menu-item">
                    <a
                      class="context__menu-item-link"
                      @click.prevent="runFromMenu(schedule)"
                    >
                      <i class="context__menu-item-icon iconoir-refresh"></i>
                      {{ $t('dataExportModal.runFull') }}
                    </a>
                  </li>
                  <li class="context__menu-item">
                    <a
                      class="context__menu-item-link"
                      @click.prevent="editFromMenu(schedule)"
                    >
                      <i
                        class="context__menu-item-icon iconoir-edit-pencil"
                      ></i>
                      {{ $t('dataExportModal.edit') }}
                    </a>
                  </li>
                  <li class="context__menu-item">
                    <a
                      class="context__menu-item-link context__menu-item-link--delete"
                      @click.prevent="removeFromMenu(schedule)"
                    >
                      <i class="context__menu-item-icon iconoir-bin"></i>
                      {{ $t('dataExportModal.delete') }}
                    </a>
                  </li>
                </ul>
              </Context>
            </template>
            <div v-if="openRunsId === schedule.id" class="margin-top-2">
              <div v-if="runsLoading" class="loading"></div>
              <p v-else-if="runs.length === 0">
                {{ $t('dataExportModal.noRuns') }}
              </p>
              <table v-else class="data-export__runs">
                <thead>
                  <tr>
                    <th>{{ $t('dataExportModal.started') }}</th>
                    <th>{{ $t('dataExportModal.duration') }}</th>
                    <th>{{ $t('dataExportModal.table') }}</th>
                    <th>{{ $t('dataExportModal.mode') }}</th>
                    <th>{{ $t('dataExportModal.state') }}</th>
                    <th>{{ $t('dataExportModal.rows') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="exportRun in runs" :key="exportRun.id">
                    <tr>
                      <td>{{ formatDate(exportRun.started_on) }}</td>
                      <td>
                        <span v-if="exportRun.finished_on">{{
                          runDuration(exportRun)
                        }}</span>
                        <span v-else class="job-duration">{{
                          $t('dataExportModal.runInProgress')
                        }}</span>
                      </td>
                      <td>{{ tableName(exportRun.table_id) }}</td>
                      <td>
                        <Badge color="neutral" size="small">
                          {{ runModeLabel(exportRun.mode) }}
                        </Badge>
                      </td>
                      <td>
                        <Badge
                          :color="runStateColor(exportRun.state)"
                          size="small"
                        >
                          {{ runStateLabel(exportRun.state) }}
                        </Badge>
                      </td>
                      <td>{{ exportRun.row_count }}</td>
                    </tr>
                    <tr v-if="exportRun.error">
                      <td colspan="6" class="data-export__runs-error">
                        {{ exportRun.error }}
                      </td>
                    </tr>
                  </template>
                </tbody>
              </table>
              <Button
                type="secondary"
                size="small"
                :loading="resetting"
                @click="resetState(schedule)"
              >
                {{ $t('dataExportModal.resetState') }}
              </Button>
            </div>
          </BackupListItem>
        </BackupList>
      </template>
    </template>
    <ConfirmModal ref="confirmModal" />
  </Modal>
</template>

<script>
import modal from '@baserow/modules/core/mixins/modal'
import error from '@baserow/modules/core/mixins/error'
import { elapsedMs, formatElapsedMs } from '@baserow/modules/core/utils/job'
import BackupService from '@baserow/modules/core/services/backup'
import DataExportService from '@baserow/modules/database/services/dataExport'
import DataExportScheduleForm from '@baserow/modules/database/components/dataExport/DataExportScheduleForm'
import BackupList from '@baserow/modules/core/components/backups/BackupList'
import BackupListItem from '@baserow/modules/core/components/backups/BackupListItem'
import { formatDate } from '@baserow/modules/core/utils/backups'
import ConfirmModal from '@baserow/modules/core/components/modals/ConfirmModal'

export default {
  name: 'DataExportModal',
  components: {
    DataExportScheduleForm,
    ConfirmModal,
    BackupList,
    BackupListItem,
  },
  mixins: [modal, error],
  props: {
    database: {
      type: Object,
      required: true,
    },
    workspace: {
      type: Object,
      required: true,
    },
  },
  data() {
    return {
      loading: false,
      loaded: false,
      saving: false,
      editing: false,
      editingSchedule: null,
      busyId: null,
      resetting: false,
      openRunsId: null,
      runsLoading: false,
      runsRequest: 0,
      runs: [],
      destinations: [],
      schedules: [],
    }
  },
  computed: {
    isStaff() {
      return this.$store.getters['auth/isStaff']
    },
  },
  methods: {
    show(...args) {
      modal.methods.show.bind(this)(...args)
      // Start from a clean slate: a previous open can leave an editing form, an
      // open runs panel, its rows or an error behind.
      this.editing = false
      this.openRunsId = null
      this.runs = []
      this.runsLoading = false
      this.runsRequest++
      this.loaded = false
      this.hideError()
      this.load()
    },
    formatDate,
    toggleMore(schedule) {
      const button = this.$refs[`more-${schedule.id}`]
      const context = this.$refs[`moreContext-${schedule.id}`]
      const target = (Array.isArray(button) ? button[0] : button)?.$el
      const menu = Array.isArray(context) ? context[0] : context
      menu?.toggle(target, 'bottom', 'right', 4)
    },
    hideMore(schedule) {
      const context = this.$refs[`moreContext-${schedule.id}`]
      ;(Array.isArray(context) ? context[0] : context)?.hide()
    },
    runFromMenu(schedule) {
      this.hideMore(schedule)
      return this.run(schedule, 'full')
    },
    editFromMenu(schedule) {
      this.hideMore(schedule)
      this.edit(schedule)
    },
    removeFromMenu(schedule) {
      this.hideMore(schedule)
      this.remove(schedule)
    },
    runModeLabel(mode) {
      return ['auto', 'full', 'incremental'].includes(mode)
        ? this.$t(`dataExportModal.runModes.${mode}`)
        : mode
    },
    runStateLabel(state) {
      return ['running', 'finished', 'failed'].includes(state)
        ? this.$t(`dataExportModal.runStates.${state}`)
        : state
    },
    runStateColor(state) {
      return { running: 'yellow', finished: 'green', failed: 'red' }[state]
    },
    /**
     * Only the owner of a schedule or a workspace admin (staff included) may run
     * it, which is what the backend enforces with a 403.
     */
    canRun(schedule) {
      return (
        this.workspace.permissions === 'ADMIN' ||
        this.isStaff ||
        schedule.user_id === this.$store.getters['auth/getUserId']
      )
    },
    runDuration(exportRun) {
      return formatElapsedMs(
        elapsedMs(exportRun.started_on, exportRun.finished_on)
      )
    },
    tableName(tableId) {
      const table = (this.database.tables || []).find(
        (item) => item.id === tableId
      )
      return table ? table.name : tableId
    },
    tablesLabel(schedule) {
      if (schedule.table_ids === null) {
        return this.$t('dataExportModal.allTables')
      }
      return schedule.table_ids.map((id) => this.tableName(id)).join(', ')
    },
    async load({ quiet = false } = {}) {
      if (!quiet) {
        this.loading = true
      }
      this.hideError()
      try {
        const [{ data: destinations }, { data: schedules }] = await Promise.all(
          [
            BackupService(this.$client).listDestinations(),
            DataExportService(this.$client).listSchedules(this.workspace.id),
          ]
        )
        this.destinations = destinations.filter((destination) =>
          destination.purposes.includes('datalake')
        )
        this.schedules = schedules.filter(
          (schedule) => schedule.database === this.database.id
        )
        this.loaded = true
      } catch (error) {
        this.handleError(error)
      } finally {
        this.loading = false
      }
    },
    edit(schedule) {
      this.hideError()
      this.editingSchedule = schedule
      this.editing = true
    },
    async save(values) {
      this.saving = true
      this.hideError()
      const service = DataExportService(this.$client)
      try {
        if (this.editingSchedule) {
          await service.updateSchedule(this.editingSchedule.id, values)
        } else {
          await service.createSchedule(this.workspace.id, {
            ...values,
            database_id: this.database.id,
          })
        }
        this.editing = false
        await this.load()
      } catch (error) {
        this.handleError(error)
      } finally {
        this.saving = false
      }
    },
    async run(schedule, mode) {
      this.busyId = schedule.id
      this.hideError()
      try {
        await DataExportService(this.$client).runSchedule(schedule.id, mode)
        this.$store.dispatch('toast/info', {
          title: this.$t('dataExportModal.runQueuedTitle'),
          message: this.$t('dataExportModal.runQueuedMessage'),
        })
        // The schedule's last and next run changed.
        await this.load({ quiet: true })
      } catch (error) {
        this.handleError(error)
      } finally {
        this.busyId = null
      }
    },
    async toggleRuns(schedule) {
      if (this.openRunsId === schedule.id) {
        this.openRunsId = null
        this.runsRequest++
        this.runsLoading = false
        return
      }
      this.openRunsId = schedule.id
      this.runs = []
      this.runsLoading = true
      // Only the answer for the schedule that is still open may fill the table,
      // a slow one for a previously opened schedule would show the wrong runs.
      const request = ++this.runsRequest
      try {
        const { data } = await DataExportService(this.$client).listRuns(
          schedule.id
        )
        if (request !== this.runsRequest) {
          return
        }
        this.runs = data
      } catch (error) {
        if (request !== this.runsRequest) {
          return
        }
        this.handleError(error)
      } finally {
        if (request === this.runsRequest) {
          this.runsLoading = false
        }
      }
    },
    resetState(schedule) {
      this.$refs.confirmModal.ask({
        title: this.$t('dataExportModal.confirmResetStateTitle'),
        message: this.$t('dataExportModal.confirmResetStateMessage', {
          name: schedule.name,
        }),
        confirmLabel: this.$t('dataExportModal.resetState'),
        onConfirm: () => this.doResetState(schedule),
      })
    },
    async doResetState(schedule) {
      this.resetting = true
      this.hideError()
      try {
        await DataExportService(this.$client).resetState(schedule.id)
        this.$store.dispatch('toast/info', {
          title: this.$t('dataExportModal.resetStateTitle'),
          message: this.$t('dataExportModal.resetStateMessage'),
        })
      } catch (error) {
        this.handleError(error)
      } finally {
        this.resetting = false
      }
    },
    remove(schedule) {
      this.$refs.confirmModal.ask({
        title: this.$t('dataExportModal.confirmDeleteTitle'),
        message: this.$t('dataExportModal.confirmDeleteMessage', {
          name: schedule.name,
        }),
        confirmLabel: this.$t('dataExportModal.delete'),
        onConfirm: () => this.doRemove(schedule),
      })
    },
    async doRemove(schedule) {
      this.hideError()
      try {
        await DataExportService(this.$client).deleteSchedule(schedule.id)
        this.schedules = this.schedules.filter(
          (item) => item.id !== schedule.id
        )
      } catch (error) {
        this.handleError(error)
      }
    },
  },
}
</script>
