<template>
  <CrudTable
    ref="crudTable"
    :columns="columns"
    :service="service"
    :filters="filters"
    row-id-key="id"
  >
    <template #title>
      {{ $t('auditLogAdminTable.title') }}
    </template>
    <template #header-right-side>
      <span v-if="retentionDays" class="audit-log__retention">
        {{ $t('auditLogAdminTable.retention', retentionDays) }}
      </span>
      <a class="button button--ghost" @click="exportCsv">
        {{ $t('auditLogAdminTable.export') }}
      </a>
    </template>
    <template #header-filters>
      <AuditLogFilters @update:filters="filters = $event" />
    </template>
  </CrudTable>
</template>

<script>
import AuditLogService from '@baserow/modules/core/services/admin/auditLog'
import AuditLogFilters from '@baserow/modules/core/components/admin/auditLog/AuditLogFilters'
import CrudTable from '@baserow/modules/core/components/crudTable/CrudTable'
import SimpleField from '@baserow/modules/core/components/crudTable/fields/SimpleField'
import LocalDateField from '@baserow/modules/core/components/crudTable/fields/LocalDateField'
import CrudTableColumn from '@baserow/modules/core/crudTable/crudTableColumn'
import { notifyIf } from '@baserow/modules/core/utils/error'

export default {
  name: 'AuditLogAdminTable',
  components: {
    AuditLogFilters,
    CrudTable,
  },
  data() {
    this.columns = [
      new CrudTableColumn(
        'created_on',
        () => this.$t('auditLogAdminTable.createdOn'),
        LocalDateField,
        true
      ),
      new CrudTableColumn(
        'user_email',
        () => this.$t('auditLogAdminTable.user'),
        SimpleField,
        true
      ),
      new CrudTableColumn(
        'workspace_id',
        () => this.$t('auditLogAdminTable.workspace'),
        SimpleField
      ),
      new CrudTableColumn(
        'action_type',
        () => this.$t('auditLogAdminTable.actionType'),
        SimpleField,
        true
      ),
      new CrudTableColumn(
        'command_type',
        () => this.$t('auditLogAdminTable.commandType'),
        SimpleField
      ),
      new CrudTableColumn(
        'description',
        () => this.$t('auditLogAdminTable.description'),
        SimpleField
      ),
      new CrudTableColumn(
        'ip_address',
        () => this.$t('auditLogAdminTable.ipAddress'),
        SimpleField,
        false,
        false,
        false,
        {},
        '',
        // Only the synthetic auth events carry an IP: the `action_done` signal the
        // rest of the entries come from has no request to read one from.
        this.$t('auditLogAdminTable.ipAddressHelp')
      ),
    ]
    this.service = AuditLogService(this.$client)
    return { filters: {} }
  },
  computed: {
    /**
     * How far back the log reaches. Entries older than
     * BASEROW_USER_LOG_ENTRY_RETENTION_DAYS are cleaned up, which also bounds
     * what an export can contain, so it is stated next to the export action. A
     * non-positive value means the cleanup is switched off.
     */
    retentionDays() {
      const days = parseInt(
        this.$config.public.baserowUserLogEntryRetentionDays
      )
      return Number.isInteger(days) && days > 0 ? days : null
    },
  },
  methods: {
    async exportCsv() {
      try {
        // The export must match what the table is showing, so it is given the same
        // search, sorts and filters the table last fetched with.
        const crudTable = this.$refs.crudTable
        const { data } = await this.service.export(
          crudTable.searchQuery || null,
          crudTable.columnSorts,
          this.filters
        )
        const url = window.URL.createObjectURL(new Blob([data]))
        const link = document.createElement('a')
        link.href = url
        link.setAttribute('download', 'audit-log.csv')
        document.body.appendChild(link)
        link.click()
        link.remove()
        window.URL.revokeObjectURL(url)
      } catch (error) {
        notifyIf(error)
      }
    },
  },
}
</script>
