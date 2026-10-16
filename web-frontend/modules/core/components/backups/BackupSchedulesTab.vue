<template>
  <div>
    <Error :error="error"></Error>
    <BackupScheduleForm
      v-if="editing"
      :schedule="editingSchedule"
      :destinations="destinations"
      :workspace="workspace"
      :loading="saving"
      @submit="save"
      @cancel="editing = false"
    />
    <template v-else>
      <Button v-if="canCreate" icon="iconoir-plus" @click="edit(null)">
        {{ $t('backupsModal.newSchedule') }}
      </Button>
      <BackupList
        :loading="loading"
        :empty="schedules.length === 0"
        :empty-text="$t('backupsModal.noSchedules')"
      >
        <BackupListItem
          v-for="schedule in schedules"
          :key="schedule.id"
          :title="schedule.name"
        >
          <template #title-extra>
            <template v-if="!schedule.is_active">
              ({{ $t('backupsModal.inactive') }})
            </template>
          </template>
          <template #detail>
            <code>{{ schedule.cron }}</code> {{ schedule.timezone }}
            <template v-if="schedule.destination">
              ·
              {{
                $t('backupsModal.uploadedTo', { name: schedule.destination })
              }}
            </template>
            <template v-if="schedule.is_active">
              ·
              {{
                $t('backupsModal.nextRunOn', {
                  date: formatDate(schedule.next_run_on),
                })
              }}
            </template>
            <template v-if="schedule.last_run_on">
              ·
              {{
                $t('backupsModal.lastRunOn', {
                  date: formatDate(schedule.last_run_on),
                })
              }}
            </template>
          </template>
          <template #badges>
            <Badge v-if="schedule.only_structure" color="purple" size="small">
              {{ $t('backupsModal.structureOnly') }}
            </Badge>
            <Badge color="neutral" size="small">
              {{
                schedule.application_ids === null ||
                schedule.application_ids === undefined
                  ? $t('backupsModal.allApplications')
                  : $t(
                      'backupsModal.applicationCount',
                      schedule.application_ids.length
                    )
              }}
            </Badge>
            <Badge v-if="schedule.keep_last" color="cyan" size="small">
              {{ $t('backupsModal.keepLastBadge', schedule.keep_last) }}
            </Badge>
            <Badge v-if="schedule.keep_days" color="cyan" size="small">
              {{ $t('backupsModal.keepDaysBadge', schedule.keep_days) }}
            </Badge>
          </template>
          <template v-if="schedule.last_error" #error>
            <div class="backups__error">{{ schedule.last_error }}</div>
          </template>
          <template #actions>
            <Button
              v-if="canManage(schedule)"
              type="secondary"
              size="small"
              :loading="runningId === schedule.id"
              :disabled="runningId !== null"
              @click="runNow(schedule)"
            >
              {{ $t('backupsModal.runNow') }}
            </Button>
            <Button
              v-if="canManage(schedule)"
              type="secondary"
              size="small"
              icon="iconoir-edit-pencil"
              :title="$t('backupsModal.edit')"
              :aria-label="$t('backupsModal.edit')"
              @click="edit(schedule)"
            ></Button>
            <Button
              v-if="canManage(schedule) && canDelete"
              type="danger"
              size="small"
              icon="iconoir-bin"
              :title="$t('backupsModal.delete')"
              :aria-label="$t('backupsModal.delete')"
              @click="remove(schedule)"
            ></Button>
          </template>
        </BackupListItem>
      </BackupList>
    </template>
    <ConfirmModal ref="confirmModal" />
  </div>
</template>

<script>
import error from '@baserow/modules/core/mixins/error'
import BackupService from '@baserow/modules/core/services/backup'
import BackupScheduleForm from '@baserow/modules/core/components/backups/BackupScheduleForm'
import BackupList from '@baserow/modules/core/components/backups/BackupList'
import BackupListItem from '@baserow/modules/core/components/backups/BackupListItem'
import { formatDate } from '@baserow/modules/core/utils/backups'
import ConfirmModal from '@baserow/modules/core/components/modals/ConfirmModal'

export default {
  name: 'BackupSchedulesTab',
  components: { BackupScheduleForm, ConfirmModal, BackupList, BackupListItem },
  mixins: [error],
  props: {
    workspace: {
      type: Object,
      required: true,
    },
    destinations: {
      type: Array,
      required: true,
    },
    service: {
      type: Function,
      required: false,
      default: null,
    },
    // The staff admin panel passes `admin`: it manages the schedules of any
    // workspace and the backend lets staff through, so nothing is gated there.
    admin: {
      type: Boolean,
      required: false,
      default: false,
    },
  },
  data() {
    return {
      loading: false,
      saving: false,
      editing: false,
      editingSchedule: null,
      runningId: null,
      schedules: [],
    }
  },
  computed: {
    resolvedService() {
      return (this.service || BackupService)(this.$client)
    },
    workspaceAdmin() {
      return this.admin || this.workspace.permissions === 'ADMIN'
    },
    canCreate() {
      return (
        this.admin ||
        this.$hasPermission(
          'workspace.create_backup_schedule',
          this.workspace,
          this.workspace.id
        )
      )
    },
    canDelete() {
      return (
        this.admin ||
        this.$hasPermission(
          'workspace.backup_schedule.delete',
          this.workspace,
          this.workspace.id
        )
      )
    },
    canUpdate() {
      return (
        this.admin ||
        this.$hasPermission(
          'workspace.backup_schedule.update',
          this.workspace,
          this.workspace.id
        )
      )
    },
  },
  mounted() {
    this.load()
  },
  methods: {
    formatDate,
    /**
     * Only the owner of a schedule or a workspace admin (staff included) may edit,
     * delete or run it, which is what the backend enforces with a 403.
     */
    isOwnerOrAdmin(schedule) {
      return (
        this.workspaceAdmin ||
        this.$store.getters['auth/isStaff'] ||
        schedule.user_id === this.$store.getters['auth/getUserId']
      )
    },
    canManage(schedule) {
      return this.canUpdate && this.isOwnerOrAdmin(schedule)
    },
    async load({ quiet = false } = {}) {
      if (!quiet) {
        this.loading = true
      }
      try {
        const { data } = await this.resolvedService.listSchedules(
          this.workspace.id
        )
        this.schedules = data
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
      const service = this.resolvedService
      try {
        if (this.editingSchedule) {
          await service.updateSchedule(this.editingSchedule.id, values)
        } else {
          await service.createSchedule(this.workspace.id, values)
        }
        this.editing = false
        await this.load()
      } catch (error) {
        this.handleError(error)
      } finally {
        this.saving = false
      }
    },
    async runNow(schedule) {
      this.runningId = schedule.id
      this.hideError()
      try {
        const { data: job } = await this.resolvedService.runSchedule(
          schedule.id
        )
        await this.$store.dispatch('job/create', job)
        this.$store.dispatch('toast/info', {
          title: this.$t('backupsModal.runStartedTitle'),
          message: this.$t('backupsModal.runStartedMessage'),
        })
        // The schedule's last run and next run changed.
        await this.load({ quiet: true })
      } catch (error) {
        this.handleError(error)
      } finally {
        this.runningId = null
      }
    },
    remove(schedule) {
      this.$refs.confirmModal.ask({
        title: this.$t('backupsModal.confirmDeleteScheduleTitle'),
        message: this.$t('backupsModal.confirmDeleteScheduleMessage', {
          name: schedule.name,
        }),
        confirmLabel: this.$t('backupsModal.delete'),
        onConfirm: () => this.doRemove(schedule),
      })
    },
    async doRemove(schedule) {
      this.hideError()
      try {
        await this.resolvedService.deleteSchedule(schedule.id)
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
