<template>
  <ApplicationContext
    ref="context"
    :application="application"
    :workspace="workspace"
  >
    <template #additional-context-items>
      <li class="context__menu-item">
        <nuxt-link
          :to="{
            name: 'database-api-docs-detail',
            params: {
              databaseId: application.id,
            },
          }"
          class="context__menu-item-link"
        >
          <i class="context__menu-item-icon iconoir-book"></i>
          {{ $t('sidebar.viewAPI') }}
        </nuxt-link>
      </li>
      <li
        v-if="
          $hasPermission(
            'workspace.list_table_export_schedules',
            workspace,
            workspace.id
          )
        "
        class="context__menu-item"
      >
        <a class="context__menu-item-link" @click="openDataExport">
          <i class="context__menu-item-icon iconoir-cloud-upload"></i>
          {{ $t('sidebar.datalakeExports') }}
        </a>
        <DataExportModal
          ref="dataExportModal"
          :database="application"
          :workspace="workspace"
        ></DataExportModal>
      </li>
      <li
        v-if="
          $hasPermission(
            'workspace.manage_database_access',
            workspace,
            workspace.id
          )
        "
        class="context__menu-item"
      >
        <a class="context__menu-item-link" @click="openAccess">
          <i class="context__menu-item-icon iconoir-lock"></i>
          {{ $t('sidebar.manageAccess') }}
        </a>
        <DatabaseAccessModal
          ref="accessModal"
          :workspace="workspace"
          scope-type="database"
          :scope-id="application.id"
          :scope-name="application.name"
        ></DatabaseAccessModal>
      </li>
    </template>
  </ApplicationContext>
</template>

<script>
import ApplicationContext from '@baserow/modules/core/components/application/ApplicationContext.vue'
import applicationContext from '@baserow/modules/core/mixins/applicationContext'
import DataExportModal from '@baserow/modules/database/components/dataExport/DataExportModal'
import DatabaseAccessModal from '@baserow/modules/database/components/access/DatabaseAccessModal'

export default {
  components: {
    ApplicationContext,
    DataExportModal,
    DatabaseAccessModal,
  },
  mixins: [applicationContext],
  props: {
    application: {
      type: Object,
      required: true,
    },
    workspace: {
      type: Object,
      required: true,
    },
  },
  methods: {
    openDataExport() {
      this.hide()
      this.$refs.dataExportModal.show()
    },
    openAccess() {
      this.hide()
      this.$refs.accessModal.show()
    },
  },
}
</script>
