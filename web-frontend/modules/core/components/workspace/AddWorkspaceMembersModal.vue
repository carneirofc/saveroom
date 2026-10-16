<template>
  <Modal ref="modal">
    <h2 class="box__title">
      {{ $t('addWorkspaceMembersModal.title', { name: workspace.name }) }}
    </h2>
    <p class="add-members__description">
      {{ $t('addWorkspaceMembersModal.description') }}
    </p>
    <Error :error="error"></Error>

    <FormGroup
      small-label
      :label="$t('addWorkspaceMembersModal.search')"
      class="margin-bottom-2"
    >
      <FormInput
        v-model="search"
        :placeholder="$t('addWorkspaceMembersModal.searchPlaceholder')"
        @input="onSearch"
      />
    </FormGroup>

    <div v-if="searching" class="loading"></div>
    <p
      v-else-if="search.trim().length < minSearchLength"
      class="add-members__hint"
    >
      {{ $t('addWorkspaceMembersModal.minSearch', { count: minSearchLength }) }}
    </p>
    <p v-else-if="candidates.length === 0" class="add-members__hint">
      {{ $t('addWorkspaceMembersModal.noResults') }}
    </p>
    <ul v-else class="add-members__list">
      <li
        v-for="candidate in candidates"
        :key="candidate.user_id"
        class="add-members__item"
      >
        <Checkbox
          :checked="isSelected(candidate)"
          @input="toggle(candidate)"
        ></Checkbox>
        <span class="add-members__name">{{
          candidate.name || candidate.email
        }}</span>
        <span class="add-members__email">{{ candidate.email }}</span>
      </li>
    </ul>

    <p v-if="selected.length > 0" class="add-members__selected">
      {{ $t('addWorkspaceMembersModal.selected', { count: selected.length }) }}
      <span
        v-for="user in selected"
        :key="user.user_id"
        class="add-members__chip"
      >
        {{ user.name || user.email }}
        <a @click="toggle(user)"><i class="iconoir-xmark"></i></a>
      </span>
    </p>

    <FormGroup
      v-if="teams.length > 0"
      small-label
      :label="$t('addWorkspaceMembersModal.teams')"
      class="margin-bottom-2"
    >
      <ul class="add-members__list add-members__list--teams">
        <li v-for="team in teams" :key="team.id" class="add-members__item">
          <Checkbox
            :checked="selectedTeamIds.includes(team.id)"
            @input="toggleTeam(team)"
          >
            {{ team.name }}
          </Checkbox>
        </li>
      </ul>
    </FormGroup>

    <div class="actions">
      <FormGroup
        small-label
        :label="$t('addWorkspaceMembersModal.permissions')"
        class="add-members__permissions"
      >
        <Dropdown v-model="permissions">
          <DropdownItem
            :name="$t('permission.member')"
            value="MEMBER"
          ></DropdownItem>
          <DropdownItem
            :name="$t('permission.admin')"
            value="ADMIN"
          ></DropdownItem>
        </Dropdown>
      </FormGroup>
      <FormGroup
        v-if="canManageAccess && permissions === 'MEMBER'"
        small-label
        :label="$t('addWorkspaceMembersModal.access')"
        class="add-members__permissions"
      >
        <Dropdown v-model="accessLevel">
          <DropdownItem
            :name="$t('databaseAccessModal.inherit')"
            :value="INHERIT"
          ></DropdownItem>
          <DropdownItem
            v-for="level in LEVELS"
            :key="level"
            :name="$t(`databaseAccessModal.levels.${level}`)"
            :value="level"
          ></DropdownItem>
        </Dropdown>
      </FormGroup>
      <div class="align-right">
        <Button
          type="primary"
          size="large"
          :loading="saving"
          :disabled="saving || selected.length === 0"
          @click="add"
        >
          {{ $t('addWorkspaceMembersModal.add', { count: selected.length }) }}
        </Button>
      </div>
    </div>
  </Modal>
</template>

<script>
import modal from '@baserow/modules/core/mixins/modal'
import error from '@baserow/modules/core/mixins/error'
import WorkspaceService from '@baserow/modules/core/services/workspace'
import {
  ACCESS_INHERIT,
  ACCESS_LEVELS,
} from '@baserow/modules/database/utils/access'

const MIN_SEARCH_LENGTH = 3
const SEARCH_DEBOUNCE_MS = 300

export default {
  name: 'AddWorkspaceMembersModal',
  mixins: [modal, error],
  props: {
    workspace: {
      type: Object,
      required: true,
    },
    teams: {
      type: Array,
      required: false,
      default: () => [],
    },
  },
  emits: ['added'],
  data() {
    return {
      minSearchLength: MIN_SEARCH_LENGTH,
      INHERIT: ACCESS_INHERIT,
      LEVELS: ACCESS_LEVELS,
      search: '',
      searching: false,
      candidates: [],
      selected: [],
      selectedTeamIds: [],
      permissions: 'MEMBER',
      accessLevel: ACCESS_INHERIT,
      saving: false,
      searchTimeout: null,
      searchRequest: 0,
    }
  },
  computed: {
    canManageAccess() {
      return this.$hasPermission(
        'workspace.manage_database_access',
        this.workspace,
        this.workspace.id
      )
    },
  },
  beforeUnmount() {
    clearTimeout(this.searchTimeout)
  },
  methods: {
    show(...args) {
      this.search = ''
      this.candidates = []
      this.selected = []
      this.selectedTeamIds = []
      this.permissions = 'MEMBER'
      this.accessLevel = ACCESS_INHERIT
      this.hideError()
      this.getRootModal().show(...args)
    },
    onSearch() {
      clearTimeout(this.searchTimeout)
      if (this.search.trim().length < MIN_SEARCH_LENGTH) {
        this.candidates = []
        this.searching = false
        return
      }
      this.searchTimeout = setTimeout(this.fetchCandidates, SEARCH_DEBOUNCE_MS)
    },
    async fetchCandidates() {
      const request = ++this.searchRequest
      this.searching = true
      try {
        const { data } = await WorkspaceService(
          this.$client
        ).searchUserCandidates(this.workspace.id, this.search.trim())
        // Ignore responses of searches typed over since.
        if (request === this.searchRequest) {
          this.candidates = data
        }
      } catch (error) {
        this.handleError(error)
      } finally {
        if (request === this.searchRequest) {
          this.searching = false
        }
      }
    },
    isSelected(candidate) {
      return this.selected.some((user) => user.user_id === candidate.user_id)
    },
    toggle(candidate) {
      if (this.isSelected(candidate)) {
        this.selected = this.selected.filter(
          (user) => user.user_id !== candidate.user_id
        )
      } else {
        this.selected = [...this.selected, candidate]
      }
    },
    toggleTeam(team) {
      this.selectedTeamIds = this.selectedTeamIds.includes(team.id)
        ? this.selectedTeamIds.filter((id) => id !== team.id)
        : [...this.selectedTeamIds, team.id]
    },
    async add() {
      this.saving = true
      this.hideError()
      try {
        const accessLevel =
          this.canManageAccess &&
          this.permissions === 'MEMBER' &&
          this.accessLevel !== ACCESS_INHERIT
            ? this.accessLevel
            : null
        const { data } = await WorkspaceService(this.$client).addUsers(
          this.workspace.id,
          this.selected.map((user) => user.user_id),
          this.permissions,
          { teamIds: this.selectedTeamIds, accessLevel }
        )
        for (const workspaceUser of data) {
          await this.$store.dispatch('workspace/forceAddWorkspaceUser', {
            workspaceId: this.workspace.id,
            values: workspaceUser,
          })
        }
        this.$emit('added', data)
        this.hide()
      } catch (error) {
        this.handleError(error, 'workspace')
      } finally {
        this.saving = false
      }
    },
  },
}
</script>

<style lang="scss" scoped>
.add-members__description,
.add-members__hint,
.add-members__email {
  color: var(--color-neutral-600, #6b6b6b);
}

.add-members__list {
  list-style: none;
  margin: 0 0 16px;
  padding: 0;
  max-height: 280px;
  overflow-y: auto;
}

.add-members__item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
}

.add-members__email {
  margin-left: auto;
}

.add-members__selected {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.add-members__chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 6px;
  border-radius: 4px;
  background: var(--color-neutral-100, #f5f5f5);

  a {
    cursor: pointer;
  }
}

.add-members__permissions {
  min-width: 160px;
}
</style>
