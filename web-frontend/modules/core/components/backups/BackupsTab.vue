<template>
  <div>
    <Error :error="error"></Error>
    <div class="row">
      <div class="col col-6">
        <FormGroup
          small-label
          :label="$t('backupsModal.destination')"
          class="margin-bottom-2"
        >
          <Dropdown v-model="destination" :disabled="busy">
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
          </Dropdown>
        </FormGroup>
      </div>
      <div class="col col-6">
        <FormGroup
          small-label
          :label="$t('backupsModal.content')"
          class="margin-bottom-2"
        >
          <Checkbox v-model="onlyStructure" :disabled="busy">
            {{ $t('backupsModal.onlyStructure') }}
          </Checkbox>
        </FormGroup>
      </div>
    </div>
    <FormGroup
      v-if="applications.length > 0"
      small-label
      :label="$t('backupsModal.scope')"
      class="margin-bottom-2"
    >
      <Checkbox v-model="onlySelectedApplications" :disabled="busy">
        {{ $t('backupsModal.onlySelectedApplications') }}
      </Checkbox>
      <ApplicationSelector
        v-if="onlySelectedApplications"
        class="margin-top-1"
        :workspace="workspace"
        :selected-application-ids="selectedApplicationIds"
        :disabled="busy"
        @update="selectedApplicationIds = $event"
      />
    </FormGroup>

    <template v-if="jobIsRunning">
      <ProgressBar
        :value="job.progress_percentage || 0"
        :status="jobHumanReadableState"
      />
      <JobDuration :job="job" class="margin-bottom-2" />
    </template>
    <Button :loading="busy" :disabled="busy" @click="startBackup">
      {{ $t('backupsModal.backupNow') }}
    </Button>

    <BackupList
      :loading="loading"
      :empty="backups.length === 0"
      :empty-text="$t('backupsModal.noBackups')"
    >
      <BackupListItem
        v-for="backup in backups"
        :key="backup.id"
        :title="formatDate(backup.created_on)"
      >
        <template #detail>
          {{ backup.exported_file_name }}
          <template v-if="backup.destination">
            ·
            {{ $t('backupsModal.uploadedTo', { name: backup.destination }) }}
          </template>
        </template>
        <template #actions>
          <DownloadLink
            :url="backup.download_url"
            :filename="backup.exported_file_name"
            class="button button--small button--secondary"
            :loading-class="'button--loading'"
          >
            {{ $t('backupsModal.download') }}
          </DownloadLink>
          <Button
            v-if="canRestore"
            type="secondary"
            size="small"
            :disabled="busy"
            @click="restore(backup)"
          >
            {{ $t('backupsModal.restore') }}
          </Button>
          <Button
            type="danger"
            size="small"
            icon="iconoir-bin"
            :disabled="busy"
            :title="$t('backupsModal.delete')"
            :aria-label="$t('backupsModal.delete')"
            @click="remove(backup)"
          ></Button>
        </template>
      </BackupListItem>
    </BackupList>
    <ConfirmModal ref="confirmModal" />
  </div>
</template>

<script>
import error from '@baserow/modules/core/mixins/error'
import job from '@baserow/modules/core/mixins/job'
import backupJobMemory from '@baserow/modules/core/mixins/backupJobMemory'
import BackupService from '@baserow/modules/core/services/backup'
import ApplicationSelector from '@baserow/modules/core/components/export/ApplicationSelector'
import JobDuration from '@baserow/modules/core/components/job/JobDuration'
import ConfirmModal from '@baserow/modules/core/components/modals/ConfirmModal'
import BackupList from '@baserow/modules/core/components/backups/BackupList'
import BackupListItem from '@baserow/modules/core/components/backups/BackupListItem'
import {
  formatDate,
  restoredApplicationsFinished,
} from '@baserow/modules/core/utils/backups'

export default {
  name: 'BackupsTab',
  components: {
    ApplicationSelector,
    JobDuration,
    ConfirmModal,
    BackupList,
    BackupListItem,
  },
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
      jobKind: null,
      destination: '',
      onlyStructure: false,
      onlySelectedApplications: false,
      selectedApplicationIds: [],
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
    /**
     * `ApplicationSelector` reads the applications out of the store, which only
     * holds those of the workspace the user has open. The staff admin panel targets
     * an arbitrary workspace, so there the list is empty and the picker is hidden
     * rather than showing the wrong applications.
     */
    applications() {
      return this.$store.getters['application/getAllOfWorkspace'](
        this.workspace
      )
    },
  },
  mounted() {
    const remembered = this.resumeJob('backups')
    if (remembered) {
      this.jobKind = remembered.kind
    }
    this.load()
  },
  methods: {
    formatDate,
    async load() {
      this.loading = true
      try {
        const { data } = await this.resolvedService.listBackups(
          this.workspace.id
        )
        this.backups = data.results || []
      } catch (error) {
        this.handleError(error)
      } finally {
        this.loading = false
      }
    },
    async run(kind, request) {
      this.starting = true
      this.hideError()
      try {
        const { data } = await request()
        this.jobKind = kind
        await this.createAndMonitorJob(data)
        this.rememberJob('backups', { kind })
      } catch (error) {
        this.handleError(error)
      } finally {
        this.starting = false
      }
    },
    startBackup() {
      const values = { only_structure: this.onlyStructure }
      if (this.destination) {
        values.destination = this.destination
      }
      if (this.onlySelectedApplications && this.selectedApplicationIds.length) {
        values.application_ids = this.selectedApplicationIds
      }
      return this.run('backup', () =>
        this.resolvedService.startBackup(this.workspace.id, values)
      )
    },
    restore(backup) {
      this.$refs.confirmModal.ask({
        title: this.$t('backupsModal.confirmRestoreTitle'),
        message: this.$t('backupsModal.confirmRestoreMessage', {
          date: this.formatDate(backup.created_on),
        }),
        confirmLabel: this.$t('backupsModal.restore'),
        onConfirm: () => this.doRestore(backup),
      })
    },
    doRestore(backup) {
      return this.run('restore', () =>
        this.resolvedService.restoreBackup(
          this.workspace.id,
          backup.resource_id
        )
      )
    },
    remove(backup) {
      this.$refs.confirmModal.ask({
        title: this.$t('backupsModal.confirmDeleteTitle'),
        message: this.$t('backupsModal.confirmDeleteMessage', {
          date: this.formatDate(backup.created_on),
        }),
        confirmLabel: this.$t('backupsModal.delete'),
        onConfirm: () => this.doRemove(backup),
      })
    },
    async doRemove(backup) {
      this.hideError()
      try {
        await this.resolvedService.deleteBackup(
          this.workspace.id,
          backup.resource_id
        )
        this.backups = this.backups.filter((item) => item.id !== backup.id)
      } catch (error) {
        this.handleError(error)
      }
    },
    async onJobFinished() {
      this.forgetJob('backups')
      if (this.jobKind === 'restore') {
        await restoredApplicationsFinished(this, this.job, this.workspace.id)
      } else {
        this.$store.dispatch('toast/info', {
          title: this.$t('backupsModal.backupFinishedTitle'),
          message: this.$t('backupsModal.backupFinishedMessage'),
        })
        await this.load()
      }
    },
    onJobFailed() {
      this.forgetJob('backups')
      this.showError(
        this.$t('clientHandler.notCompletedTitle'),
        this.job.human_readable_error
      )
    },
  },
}
</script>
