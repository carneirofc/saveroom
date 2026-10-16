<template>
  <Modal ref="modal" :full-screen="false" :close-button="true">
    <h2 class="box__title">
      {{ $t('backupsModal.title', { name: workspace.name }) }}
    </h2>
    <p>{{ $t('backupsModal.description') }}</p>
    <Error :error="error"></Error>
    <div v-if="loading" class="loading margin-top-2 margin-bottom-2"></div>
    <Tabs v-else-if="loaded" header-no-padding content-no-x-padding>
      <Tab :title="$t('backupsModal.tabBackups')">
        <BackupsTab :workspace="workspace" :destinations="destinations" />
      </Tab>
      <Tab v-if="canListSchedules" :title="$t('backupsModal.tabSchedules')">
        <BackupSchedulesTab
          :workspace="workspace"
          :destinations="destinations"
        />
      </Tab>
      <Tab :title="$t('backupsModal.tabRemote')">
        <RemoteBackupsTab :workspace="workspace" :destinations="destinations" />
      </Tab>
    </Tabs>
  </Modal>
</template>

<script>
import modal from '@baserow/modules/core/mixins/modal'
import error from '@baserow/modules/core/mixins/error'
import BackupService from '@baserow/modules/core/services/backup'
import BackupsTab from '@baserow/modules/core/components/backups/BackupsTab'
import BackupSchedulesTab from '@baserow/modules/core/components/backups/BackupSchedulesTab'
import RemoteBackupsTab from '@baserow/modules/core/components/backups/RemoteBackupsTab'

export default {
  name: 'BackupsModal',
  components: { BackupsTab, BackupSchedulesTab, RemoteBackupsTab },
  mixins: [modal, error],
  provide() {
    return { backupJobs: this.backupJobs }
  },
  props: {
    workspace: {
      type: Object,
      required: true,
    },
  },
  data() {
    return {
      loading: false,
      loaded: false,
      destinations: [],
      // The tabs are unmounted when the modal closes or another tab is selected, so
      // the jobs they started are remembered here and re-attached on remount.
      backupJobs: {},
    }
  },
  computed: {
    canListSchedules() {
      return this.$hasPermission(
        'workspace.list_backup_schedules',
        this.workspace,
        this.workspace.id
      )
    },
  },
  methods: {
    show(...args) {
      modal.methods.show.bind(this)(...args)
      // The tabs reload their own data when they mount. Reloading the
      // destinations on every open would toggle `loaded` and unmount them.
      if (!this.loaded) {
        this.load()
      }
    },
    async load() {
      this.loaded = false
      this.loading = true
      this.hideError()
      try {
        const { data } = await BackupService(this.$client).listDestinations()
        this.destinations = data.filter((destination) =>
          destination.purposes.includes('backup')
        )
        this.loaded = true
      } catch (error) {
        this.handleError(error)
      } finally {
        this.loading = false
      }
    },
  },
}
</script>
