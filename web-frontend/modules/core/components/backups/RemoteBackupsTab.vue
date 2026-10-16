<template>
  <div>
    <Error :error="error"></Error>
    <p v-if="destinations.length === 0">
      {{
        isStaff
          ? $t('backupsModal.noBackupDestinationsStaff')
          : $t('backupsModal.noBackupDestinations')
      }}
    </p>
    <template v-else>
      <div class="row">
        <div class="col col-6">
          <FormGroup
            small-label
            :label="$t('backupsModal.destination')"
            class="margin-bottom-2"
          >
            <Dropdown
              :model-value="destination"
              :disabled="busy"
              @update:model-value="selectDestination"
            >
              <DropdownItem
                v-for="item in destinations"
                :key="item.name"
                :name="`${item.name} (${item.type})`"
                :value="item.name"
              ></DropdownItem>
            </Dropdown>
          </FormGroup>
        </div>
        <div v-if="canTrustPublicKey" class="col col-6">
          <FormGroup
            small-label
            :label="$t('backupsModal.signingKey')"
            :helper-text="$t('backupsModal.trustPublicKeyHelp')"
            class="margin-bottom-2"
          >
            <Checkbox v-model="trustPublicKey" :disabled="busy">
              {{ $t('backupsModal.trustPublicKey') }}
            </Checkbox>
          </FormGroup>
        </div>
      </div>
      <template v-if="jobIsRunning">
        <ProgressBar
          :value="job.progress_percentage || 0"
          :status="jobHumanReadableState"
        />
        <JobDuration :job="job" class="margin-bottom-2" />
      </template>
      <BackupList
        :loading="loading"
        :empty="backups.length === 0"
        :empty-text="$t('backupsModal.noRemoteBackups')"
      >
        <BackupListItem
          v-for="backup in backups"
          :key="backup.key"
          :title="`${formatDate(backup.created_on)} · ${applicationNames(backup)}`"
        >
          <template #detail>
            {{ formatSize(backup.size) }}
            <template v-if="backup.baserow_version">
              ·
              {{
                $t('backupsModal.version', { version: backup.baserow_version })
              }}
            </template>
            <template v-if="backup.sha256">
              ·
              <code :title="backup.sha256">{{
                backup.sha256.slice(0, 8)
              }}</code>
            </template>
            <template v-if="backup.created_by">
              · {{ $t('backupsModal.createdBy', { name: backup.created_by }) }}
            </template>
            <template v-if="scheduleName(backup)">
              ·
              {{
                $t('backupsModal.fromSchedule', { name: scheduleName(backup) })
              }}
            </template>
            <template v-if="backup.is_this_instance === false">
              · {{ $t('backupsModal.instance', { id: backup.instance_id }) }}
            </template>
          </template>
          <template #badges>
            <Badge v-if="backup.only_structure" color="purple" size="small">
              {{ $t('backupsModal.structureOnly') }}
            </Badge>
            <Badge v-if="backup.schedule_id" color="cyan" size="small">
              {{ $t('backupsModal.scheduled') }}
            </Badge>
            <Badge
              v-if="backup.is_this_instance === false"
              color="yellow"
              size="small"
            >
              {{ $t('backupsModal.otherInstance') }}
            </Badge>
          </template>
          <template #actions>
            <Button
              v-if="canRestore"
              type="secondary"
              size="small"
              :loading="busy && restoringKey === backup.key"
              :disabled="busy"
              @click="restore(backup)"
            >
              {{ $t('backupsModal.restore') }}
            </Button>
          </template>
        </BackupListItem>
      </BackupList>
    </template>
    <ConfirmModal ref="confirmModal" />
  </div>
</template>

<script>
import error from '@baserow/modules/core/mixins/error'
import job from '@baserow/modules/core/mixins/job'
import backupJobMemory from '@baserow/modules/core/mixins/backupJobMemory'
import BackupService from '@baserow/modules/core/services/backup'
import BackupList from '@baserow/modules/core/components/backups/BackupList'
import BackupListItem from '@baserow/modules/core/components/backups/BackupListItem'
import {
  formatDate,
  restoredApplicationsFinished,
} from '@baserow/modules/core/utils/backups'
import { formatFileSize } from '@baserow/modules/core/utils/file'
import JobDuration from '@baserow/modules/core/components/job/JobDuration'
import ConfirmModal from '@baserow/modules/core/components/modals/ConfirmModal'
import { ResponseErrorMessage } from '@baserow/modules/core/plugins/clientHandler'

export default {
  name: 'RemoteBackupsTab',
  components: { JobDuration, ConfirmModal, BackupList, BackupListItem },
  mixins: [error, job, backupJobMemory],
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
    // The staff admin panel passes `admin`: the backend lets staff restore into any
    // workspace, so the restore action is not gated there.
    admin: {
      type: Boolean,
      required: false,
      default: false,
    },
  },
  data() {
    return {
      loading: false,
      starting: false,
      destination: this.destinations[0]?.name || '',
      loadedDestination: null,
      loadRequest: 0,
      trustPublicKey: false,
      scheduleNames: {},
      restoringKey: null,
      backups: [],
    }
  },
  computed: {
    resolvedService() {
      return (this.service || BackupService)(this.$client)
    },
    busy() {
      return this.starting || this.jobIsRunning
    },
    // Restoring creates applications, which the backend checks separately from
    // exporting the workspace, which is what opens the backups modal.
    canRestore() {
      return (
        this.admin ||
        this.$hasPermission(
          'workspace.create_application',
          this.workspace,
          this.workspace.id
        )
      )
    },
    isStaff() {
      return this.$store.getters['auth/isStaff']
    },
    selectedDestination() {
      return this.destinations.find((item) => item.name === this.destination)
    },
    // Trusting a foreign signing key is for staff, and only when the storage allows
    // it, otherwise the backend would refuse it anyway.
    canTrustPublicKey() {
      return !!(
        this.isStaff && this.selectedDestination?.allow_trust_public_key
      )
    },
  },
  mounted() {
    const remembered = this.resumeJob('remote')
    if (remembered) {
      this.restoringKey = remembered.restoringKey
    }
    this.load()
    this.loadScheduleNames()
  },
  methods: {
    formatDate,
    scheduleName(backup) {
      return backup.schedule_id ? this.scheduleNames[backup.schedule_id] : null
    },
    formatSize(bytes) {
      return formatFileSize(this.$t, this.$i18n.locale, bytes || 0)
    },
    applicationNames(backup) {
      return (backup.applications || [])
        .map((application) => application.name)
        .join(', ')
    },
    // Names the schedules the backups came from. A user who cannot list the
    // schedules gets none, the row then only says it was scheduled.
    async loadScheduleNames() {
      try {
        const { data } = await this.resolvedService.listSchedules(
          this.workspace.id
        )
        const names = {}
        for (const schedule of data || []) {
          names[schedule.id] = schedule.name
        }
        this.scheduleNames = names
      } catch (error) {
        this.scheduleNames = {}
        // Without the permission the names are simply left out, anything else is a
        // real failure the user should hear about.
        const status = error.response?.status
        const denied =
          status === 401 ||
          status === 403 ||
          error.handler?.code === 'ERROR_PERMISSION_DENIED'
        if (!denied && error.handler) {
          error.handler.notifyIf()
        }
      }
    },
    selectDestination(value) {
      this.destination = value
      // The trust is given to the signing key of one storage, not carried over.
      this.trustPublicKey = false
      this.load()
    },
    async load() {
      if (!this.destination || this.loadedDestination === this.destination) {
        return
      }
      // Only the response for the destination that is still selected may fill
      // the list, otherwise a slow answer for a previous destination would show
      // its backups, and restore their keys, under the current one.
      const destination = this.destination
      const request = ++this.loadRequest
      this.loadedDestination = destination
      this.loading = true
      this.hideError()
      try {
        const { data } = await this.resolvedService.listRemoteBackups(
          destination,
          this.workspace.id
        )
        if (request !== this.loadRequest) {
          return
        }
        this.backups = data.results || []
      } catch (error) {
        if (request !== this.loadRequest) {
          return
        }
        this.backups = []
        // Selecting the same destination again must retry.
        this.loadedDestination = null
        this.handleError(error)
      } finally {
        if (request === this.loadRequest) {
          this.loading = false
        }
      }
    },
    restore(backup) {
      const destination = this.destination
      this.$refs.confirmModal.ask({
        title: this.$t('backupsModal.confirmRestoreTitle'),
        message: this.$t('backupsModal.confirmRestoreMessage', {
          date: this.formatDate(backup.created_on),
        }),
        confirmLabel: this.$t('backupsModal.restore'),
        onConfirm: () => this.doRestore(backup, destination),
      })
    },
    async doRestore(backup, destination) {
      // The backup's key only exists on the destination it was listed from.
      if (destination !== this.destination) {
        return
      }
      this.starting = true
      this.restoringKey = backup.key
      this.hideError()
      try {
        const values = { key: backup.key }
        if (this.canTrustPublicKey && this.trustPublicKey) {
          values.trust_public_key = true
        }
        const { data } = await this.resolvedService.restoreRemoteBackup(
          destination,
          this.workspace.id,
          values
        )
        await this.createAndMonitorJob(data)
        this.rememberJob('remote', { restoringKey: backup.key })
      } catch (error) {
        this.restoringKey = null
        this.handleError(error, 'backup', {
          ERROR_UNTRUSTED_PUBLIC_KEY: new ResponseErrorMessage(
            this.$t('backupsModal.untrustedKeyTitle'),
            this.$t('backupsModal.untrustedKeyMessage')
          ),
        })
      } finally {
        this.starting = false
      }
    },
    async onJobFinished() {
      this.restoringKey = null
      this.forgetJob('remote')
      await restoredApplicationsFinished(this, this.job, this.workspace.id)
    },
    onJobFailed() {
      this.restoringKey = null
      this.forgetJob('remote')
      this.showError(
        this.$t('clientHandler.notCompletedTitle'),
        this.job.human_readable_error
      )
    },
  },
}
</script>
