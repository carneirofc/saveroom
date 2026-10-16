<template>
  <div class="teams-settings">
    <div class="teams-settings__header">
      <h2 class="teams-settings__title">
        {{
          $t('teamsSettings.title', {
            count: teams.length,
            workspaceName: workspace.name,
          })
        }}
      </h2>
      <Button
        v-if="
          $hasPermission(
            'workspace.manage_database_access',
            workspace,
            workspace.id
          )
        "
        type="secondary"
        @click="$refs.defaultAccessModal.show()"
      >
        {{ $t('teamsSettings.defaultAccess') }}
      </Button>
    </div>
    <p class="teams-settings__description">
      {{ $t('teamsSettings.description') }}
    </p>

    <Error :error="error"></Error>

    <form
      v-if="$hasPermission('workspace.create_team', workspace, workspace.id)"
      class="teams-settings__create"
      @submit.prevent="createTeam"
    >
      <FormInput
        v-model="newTeamName"
        :placeholder="$t('teamsSettings.newTeamPlaceholder')"
      />
      <Button
        type="primary"
        :loading="creating"
        :disabled="creating || !newTeamName.trim()"
      >
        {{ $t('teamsSettings.createTeam') }}
      </Button>
    </form>

    <div v-if="loading" class="loading"></div>
    <p v-else-if="teams.length === 0" class="teams-settings__empty">
      {{ $t('teamsSettings.empty') }}
    </p>
    <div
      v-for="team in teams"
      v-else
      :key="team.id"
      class="teams-settings__team"
    >
      <div class="teams-settings__team-header">
        <FormInput
          v-if="renamingId === team.id"
          v-model="renameValue"
          @keydown.enter="renameTeam(team)"
        />
        <h3 v-else class="teams-settings__team-name">{{ team.name }}</h3>
        <div class="teams-settings__team-actions">
          <template
            v-if="
              $hasPermission('workspace.update_team', workspace, workspace.id)
            "
          >
            <Button
              v-if="renamingId === team.id"
              type="primary"
              size="small"
              @click="renameTeam(team)"
            >
              {{ $t('teamsSettings.save') }}
            </Button>
            <Button
              v-else
              type="secondary"
              size="small"
              @click="startRename(team)"
            >
              {{ $t('teamsSettings.rename') }}
            </Button>
          </template>
          <Button
            v-if="
              $hasPermission('workspace.delete_team', workspace, workspace.id)
            "
            type="danger"
            size="small"
            @click="deleteTeam(team)"
          >
            {{ $t('teamsSettings.delete') }}
          </Button>
        </div>
      </div>

      <ul class="teams-settings__members">
        <li v-if="team.members.length === 0" class="teams-settings__empty">
          {{ $t('teamsSettings.noMembers') }}
        </li>
        <li
          v-for="member in team.members"
          :key="member.id"
          class="teams-settings__member"
        >
          <span>{{ member.name || member.email }}</span>
          <span class="teams-settings__member-email">{{ member.email }}</span>
          <span
            v-if="member.source !== 'manual'"
            class="teams-settings__member-badge"
          >
            {{ $t('teamsSettings.ssoManaged') }}
          </span>
          <a
            v-if="canManageMembers"
            class="teams-settings__member-remove"
            @click="removeMember(team, member)"
          >
            {{ $t('teamsSettings.removeMember') }}
          </a>
        </li>
      </ul>

      <Dropdown
        v-if="canManageMembers && candidates(team).length > 0"
        :value="null"
        :show-search="true"
        :placeholder="$t('teamsSettings.addMember')"
        class="teams-settings__add-member"
        @input="addMember(team, $event)"
      >
        <DropdownItem
          v-for="user in candidates(team)"
          :key="user.user_id"
          :name="user.name || user.email"
          :value="user.user_id"
        ></DropdownItem>
      </Dropdown>
    </div>

    <DatabaseAccessModal
      ref="defaultAccessModal"
      :workspace="workspace"
      scope-type="workspace"
      :scope-id="workspace.id"
      :scope-name="workspace.name"
    ></DatabaseAccessModal>
  </div>
</template>

<script>
import error from '@baserow/modules/core/mixins/error'
import TeamsService from '@baserow/modules/core/services/teams'
import WorkspaceService from '@baserow/modules/core/services/workspace'
import DatabaseAccessModal from '@baserow/modules/database/components/access/DatabaseAccessModal'

export default {
  name: 'TeamsSettings',
  components: { DatabaseAccessModal },
  mixins: [error],
  props: {
    workspace: {
      type: Object,
      required: true,
    },
  },
  data() {
    return {
      loading: true,
      creating: false,
      teams: [],
      workspaceUsers: [],
      newTeamName: '',
      renamingId: null,
      renameValue: '',
    }
  },
  computed: {
    canManageMembers() {
      return this.$hasPermission(
        'workspace.manage_team_members',
        this.workspace,
        this.workspace.id
      )
    },
  },
  async mounted() {
    await this.fetch()
  },
  methods: {
    async fetch() {
      this.loading = true
      try {
        const [teams, users] = await Promise.all([
          TeamsService(this.$client).fetchAll(this.workspace.id),
          WorkspaceService(this.$client).fetchAllUsers(this.workspace.id),
        ])
        this.teams = teams.data
        this.workspaceUsers = users.data
      } catch (error) {
        this.handleError(error)
      } finally {
        this.loading = false
      }
    },
    candidates(team) {
      const memberIds = new Set(team.members.map((member) => member.user_id))
      return this.workspaceUsers.filter((user) => !memberIds.has(user.user_id))
    },
    replaceTeam(team) {
      const index = this.teams.findIndex((t) => t.id === team.id)
      if (index === -1) {
        this.teams.push(team)
      } else {
        this.teams.splice(index, 1, team)
      }
    },
    async run(callback) {
      this.hideError()
      try {
        await callback()
      } catch (error) {
        this.handleError(error)
      }
    },
    async createTeam() {
      this.creating = true
      await this.run(async () => {
        const { data } = await TeamsService(this.$client).create(
          this.workspace.id,
          { name: this.newTeamName.trim() }
        )
        this.replaceTeam(data)
        this.newTeamName = ''
      })
      this.creating = false
    },
    startRename(team) {
      this.renamingId = team.id
      this.renameValue = team.name
    },
    async renameTeam(team) {
      await this.run(async () => {
        const { data } = await TeamsService(this.$client).update(team.id, {
          name: this.renameValue.trim(),
        })
        this.replaceTeam(data)
        this.renamingId = null
      })
    },
    async deleteTeam(team) {
      await this.run(async () => {
        await TeamsService(this.$client).delete(team.id)
        this.teams = this.teams.filter((t) => t.id !== team.id)
      })
    },
    async addMember(team, userId) {
      if (userId === null) {
        return
      }
      await this.run(async () => {
        const { data } = await TeamsService(this.$client).addMembers(team.id, [
          userId,
        ])
        this.replaceTeam(data)
      })
    },
    async removeMember(team, member) {
      await this.run(async () => {
        const { data } = await TeamsService(this.$client).removeMembers(
          team.id,
          [member.user_id]
        )
        this.replaceTeam(data)
      })
    },
  },
}
</script>

<style lang="scss" scoped>
.teams-settings {
  padding: 24px;
}

.teams-settings__header,
.teams-settings__team-header,
.teams-settings__create {
  display: flex;
  align-items: center;
  gap: 12px;
}

.teams-settings__header {
  justify-content: space-between;
}

.teams-settings__create {
  margin: 16px 0 24px;
  max-width: 480px;
}

.teams-settings__team {
  border-top: 1px solid var(--color-neutral-200, #ededed);
  padding: 16px 0;
}

.teams-settings__team-header {
  justify-content: space-between;
}

.teams-settings__team-actions {
  display: flex;
  gap: 8px;
}

.teams-settings__members {
  margin: 12px 0;
  padding: 0;
  list-style: none;
}

.teams-settings__member {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 0;
}

.teams-settings__member-email,
.teams-settings__description,
.teams-settings__empty {
  color: var(--color-neutral-600, #6b6b6b);
}

.teams-settings__member-badge {
  font-size: 12px;
}

.teams-settings__member-remove {
  margin-left: auto;
  cursor: pointer;
}

.teams-settings__add-member {
  max-width: 320px;
}
</style>
