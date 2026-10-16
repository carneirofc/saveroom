<template>
  <div class="layout__col-2-scroll">
    <div class="admin-settings">
      <h1>{{ $t('adminType.backups') }}</h1>
      <BackupDestinationsCard />
      <FormGroup :label="$t('backupsAdminPanel.workspace')" small-label>
        <PaginatedDropdown
          :model-value="workspaceId"
          :fetch-page="fetchWorkspaces"
          id-name="id"
          value-name="value"
          size="large"
          :include-display-name-in-selected-event="true"
          @input="workspaceSelected"
        ></PaginatedDropdown>
      </FormGroup>

      <div v-if="loading" class="loading margin-top-2"></div>
      <div v-else-if="workspace && destinationsError" class="margin-top-2">
        <Alert type="error">
          <template #title>{{
            $t('backupsAdminPanel.loadErrorTitle')
          }}</template>
          <p>{{ $t('backupsAdminPanel.loadErrorMessage') }}</p>
        </Alert>
        <Button type="secondary" class="margin-top-2" @click="loadDestinations">
          {{ $t('backupsAdminPanel.retry') }}
        </Button>
      </div>
      <Tabs
        v-else-if="workspace"
        :key="workspaceId"
        header-no-padding
        content-no-x-padding
        class="margin-top-2"
      >
        <Tab :title="$t('backupsModal.tabBackups')">
          <BackupsTab
            :workspace="workspace"
            :destinations="destinations"
            :service="adminBackupService"
            admin
          />
        </Tab>
        <Tab :title="$t('backupsModal.tabSchedules')">
          <BackupSchedulesTab
            :workspace="workspace"
            :destinations="destinations"
            :service="adminBackupService"
            admin
          />
        </Tab>
        <Tab :title="$t('backupsModal.tabRemote')">
          <RemoteBackupsTab
            :workspace="workspace"
            :destinations="destinations"
            :service="adminBackupService"
            admin
          />
        </Tab>
      </Tabs>
    </div>
  </div>
</template>

<script>
import BackupsAdminService from '@baserow/modules/core/services/admin/backups'
import PaginatedDropdown from '@baserow/modules/core/components/PaginatedDropdown'
import BackupDestinationsCard from '@baserow/modules/core/components/admin/backups/BackupDestinationsCard'
import BackupsTab from '@baserow/modules/core/components/backups/BackupsTab'
import BackupSchedulesTab from '@baserow/modules/core/components/backups/BackupSchedulesTab'
import RemoteBackupsTab from '@baserow/modules/core/components/backups/RemoteBackupsTab'
import { notifyIf } from '@baserow/modules/core/utils/error'

export default {
  name: 'BackupsAdminPanel',
  components: {
    PaginatedDropdown,
    BackupDestinationsCard,
    BackupsTab,
    BackupSchedulesTab,
    RemoteBackupsTab,
  },
  provide() {
    return { backupJobs: this.backupJobs }
  },
  data() {
    return {
      // Remembers the jobs started from the tabs across tab switches, keyed by
      // tab and workspace.
      backupJobs: {},
      workspaceId: null,
      workspaceName: null,
      loading: false,
      destinationsError: false,
      destinationsRequest: 0,
      destinations: [],
    }
  },
  computed: {
    workspace() {
      return this.workspaceId
        ? { id: this.workspaceId, name: this.workspaceName }
        : null
    },
  },
  methods: {
    // `service` is passed as a factory function (matching the `(client) => {...}`
    // shape `BackupsTab`/`BackupSchedulesTab`/`RemoteBackupsTab` expect), so the
    // same tab components work here and in the member-facing `BackupsModal`.
    adminBackupService(client) {
      return BackupsAdminService(client)
    },
    fetchWorkspaces(page, search) {
      return BackupsAdminService(this.$client).listWorkspaces(page, search)
    },
    async workspaceSelected({ value, displayName }) {
      this.workspaceId = value
      this.workspaceName = displayName
      await this.loadDestinations()
    },
    async loadDestinations() {
      // Switching workspaces quickly can leave an older request in flight; only
      // the latest one may decide what the panel shows.
      const request = ++this.destinationsRequest
      this.loading = true
      this.destinationsError = false
      try {
        const { data } = await BackupsAdminService(
          this.$client
        ).listDestinations()
        if (request !== this.destinationsRequest) {
          return
        }
        this.destinations = data.filter((destination) =>
          destination.purposes.includes('backup')
        )
      } catch (error) {
        if (request !== this.destinationsRequest) {
          return
        }
        // Rendering the tabs with an empty list would claim no external storage
        // is configured, so show the failure instead.
        this.destinations = []
        this.destinationsError = true
        notifyIf(error)
      } finally {
        if (request === this.destinationsRequest) {
          this.loading = false
        }
      }
    },
  },
}
</script>
