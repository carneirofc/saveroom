<template>
  <div class="audit-log-filters">
    <FormGroup
      small-label
      :label="$t('auditLogFilters.user')"
      class="audit-log-filters__field"
    >
      <PaginatedDropdown
        :model-value="values.user_id"
        :fetch-page="fetchUsers"
        id-name="id"
        value-name="username"
        :empty-item-display-name="$t('auditLogFilters.all')"
        @input="setValue('user_id', $event)"
      ></PaginatedDropdown>
    </FormGroup>

    <FormGroup
      small-label
      :label="$t('auditLogFilters.workspace')"
      class="audit-log-filters__field"
    >
      <PaginatedDropdown
        :model-value="values.workspace_id"
        :fetch-page="fetchWorkspaces"
        id-name="id"
        value-name="value"
        :empty-item-display-name="$t('auditLogFilters.all')"
        @input="setValue('workspace_id', $event)"
      ></PaginatedDropdown>
    </FormGroup>

    <FormGroup
      small-label
      :label="$t('auditLogFilters.actionType')"
      class="audit-log-filters__field"
    >
      <Dropdown
        :model-value="values.action_type"
        :show-search="true"
        @update:model-value="setValue('action_type', $event)"
      >
        <DropdownItem
          :name="$t('auditLogFilters.all')"
          :value="null"
        ></DropdownItem>
        <DropdownItem
          v-for="actionType in actionTypes"
          :key="actionType"
          :name="actionType"
          :value="actionType"
        ></DropdownItem>
      </Dropdown>
    </FormGroup>

    <FormGroup
      small-label
      :label="$t('auditLogFilters.commandType')"
      class="audit-log-filters__field"
    >
      <Dropdown
        :model-value="values.command_type"
        @update:model-value="setValue('command_type', $event)"
      >
        <DropdownItem
          :name="$t('auditLogFilters.all')"
          :value="null"
        ></DropdownItem>
        <DropdownItem
          v-for="commandType in commandTypes"
          :key="commandType"
          :name="commandType"
          :value="commandType"
        ></DropdownItem>
      </Dropdown>
    </FormGroup>

    <FormGroup
      small-label
      :label="$t('auditLogFilters.createdAfter')"
      class="audit-log-filters__field"
    >
      <FormInput
        :model-value="values.created_after"
        type="datetime-local"
        @update:model-value="setValue('created_after', $event)"
      />
    </FormGroup>

    <FormGroup
      small-label
      :label="$t('auditLogFilters.createdBefore')"
      class="audit-log-filters__field"
    >
      <FormInput
        :model-value="values.created_before"
        type="datetime-local"
        @update:model-value="setValue('created_before', $event)"
      />
    </FormGroup>

    <div class="audit-log-filters__actions">
      <ButtonText v-if="hasFilters" icon="iconoir-xmark" @click="clear()">
        {{ $t('auditLogFilters.clear') }}
      </ButtonText>
    </div>
  </div>
</template>

<script>
import AuditLogService, {
  omitEmptyFilters,
} from '@baserow/modules/core/services/admin/auditLog'
import UsersAdminService from '@baserow/modules/core/services/admin/users'
import WorkspacesAdminService from '@baserow/modules/core/services/admin/workspaces'
import PaginatedDropdown from '@baserow/modules/core/components/PaginatedDropdown'
import { notifyIf } from '@baserow/modules/core/utils/error'

const EMPTY_FILTERS = {
  user_id: null,
  workspace_id: null,
  action_type: null,
  command_type: null,
  created_after: '',
  created_before: '',
}

export default {
  name: 'AuditLogFilters',
  components: { PaginatedDropdown },
  emits: ['update:filters'],
  data() {
    return {
      values: { ...EMPTY_FILTERS },
      actionTypes: [],
      commandTypes: [],
    }
  },
  computed: {
    hasFilters() {
      return Object.keys(omitEmptyFilters(this.values)).length > 0
    },
  },
  async mounted() {
    try {
      const { data } = await AuditLogService(this.$client).fetchFilterOptions()
      this.actionTypes = data.action_types
      this.commandTypes = data.command_types
    } catch (error) {
      notifyIf(error)
    }
  },
  methods: {
    fetchUsers(page, search) {
      return UsersAdminService(this.$client).fetch(
        '/admin/users/',
        page,
        search,
        []
      )
    },
    fetchWorkspaces(page, search) {
      return WorkspacesAdminService(this.$client).listOptions(page, search)
    },
    setValue(key, value) {
      this.values = { ...this.values, [key]: value }
      this.emitFilters()
    },
    clear() {
      this.values = { ...EMPTY_FILTERS }
      this.emitFilters()
    },
    emitFilters() {
      // Only the filters that actually carry a value are emitted: a blank one has
      // to be absent from the query string, not sent as an empty value.
      this.$emit('update:filters', omitEmptyFilters(this.values))
    },
  },
}
</script>
