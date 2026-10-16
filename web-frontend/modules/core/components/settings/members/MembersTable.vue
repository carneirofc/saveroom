<template>
  <div>
    <CrudTable
      ref="crudTable"
      :service="service"
      :columns="columns"
      row-id-key="id"
      @row-context="onRowContext"
      @edit-role-context="onEditRoleContext"
      @edit-teams-context="onEditTeamsContext"
    >
      <template #title>
        {{
          $t('membersSettings.membersTable.title', {
            userAmount: workspace.users.length || 0,
            workspaceName: workspace.name,
          })
        }}
      </template>
      <template #header-right-side>
        <Button
          v-if="
            $hasPermission(
              'workspace.add_workspace_users',
              workspace,
              workspace.id
            )
          "
          type="primary"
          size="large"
          class="margin-left-2"
          @click="$refs.addMembersModal.show()"
        >
          {{ $t('membersSettings.membersTable.addMembers') }}
        </Button>
      </template>
      <template #menus="slotProps">
        <EditMemberContext
          ref="editMemberContext"
          :workspace="workspace"
          :member="editMember"
          @remove-user="slotProps.deleteRow"
        ></EditMemberContext>
        <EditRoleContext
          ref="editRoleContext"
          :subject="editRoleMember"
          :roles="roles"
          :workspace="workspace"
          @update-role="roleUpdate($event)"
        ></EditRoleContext>
        <EditTeamsContext
          ref="editTeamsContext"
          :member="editTeamsMember"
          :teams="teams"
          :loading="savingTeams"
          @toggle-team="teamToggle($event)"
        ></EditTeamsContext>
      </template>
    </CrudTable>
    <AddWorkspaceMembersModal
      ref="addMembersModal"
      :workspace="workspace"
      :teams="teams"
      @added="$refs.crudTable.refresh()"
    />
  </div>
</template>

<script>
import { mapGetters } from 'vuex'
import { clone } from '@baserow/modules/core/utils/object'
import { notifyIf } from '@baserow/modules/core/utils/error'

import CrudTable from '@baserow/modules/core/components/crudTable/CrudTable'
import WorkspaceService from '@baserow/modules/core/services/workspace'
import TeamsService from '@baserow/modules/core/services/teams'
import CrudTableColumn from '@baserow/modules/core/crudTable/crudTableColumn'
import SimpleField from '@baserow/modules/core/components/crudTable/fields/SimpleField'
import TwoFactorAuthField from '@baserow/modules/core/components/crudTable/fields/TwoFactorAuthField'
import MoreField from '@baserow/modules/core/components/crudTable/fields/MoreField'
import MemberRoleField from '@baserow/modules/core/components/settings/members/MemberRoleField'
import MemberTeamsField from '@baserow/modules/core/components/settings/members/MemberTeamsField'
import AddWorkspaceMembersModal from '@baserow/modules/core/components/workspace/AddWorkspaceMembersModal'
import EditMemberContext from '@baserow/modules/core/components/settings/members/EditMemberContext'
import EditRoleContext from '@baserow/modules/core/components/settings/members/EditRoleContext'
import EditTeamsContext from '@baserow/modules/core/components/settings/members/EditTeamsContext'

export default {
  name: 'MembersTable',
  components: {
    AddWorkspaceMembersModal,
    EditMemberContext,
    EditRoleContext,
    EditTeamsContext,
    CrudTable,
  },
  props: {
    workspace: {
      type: Object,
      required: true,
    },
  },
  data() {
    return {
      editMember: {},
      editRoleMember: {},
      editTeamsMember: {},
      teams: [],
      savingTeams: false,
    }
  },
  computed: {
    ...mapGetters({ userId: 'auth/getUserId' }),
    roles() {
      return this.workspace._.roles
    },
    canListTeams() {
      return this.$hasPermission(
        'workspace.list_teams',
        this.workspace,
        this.workspace.id
      )
    },
    canManageTeamMembers() {
      return this.$hasPermission(
        'workspace.manage_team_members',
        this.workspace,
        this.workspace.id
      )
    },
    service() {
      const service = WorkspaceService(this.$client)
      const options = {
        ...service.options,
        urlParams: { workspaceId: this.workspace.id },
      }
      return {
        ...service,
        options,
      }
    },
    membersPagePlugins() {
      return Object.values(this.$registry.getAll('membersPagePlugins'))
    },
    columns() {
      let columns = [
        new CrudTableColumn(
          'name',
          this.$t('membersSettings.membersTable.columns.name'),
          SimpleField,
          true,
          true
        ),
        new CrudTableColumn(
          'email',
          this.$t('membersSettings.membersTable.columns.email'),
          SimpleField,
          true
        ),
        new CrudTableColumn(
          'permissions',
          this.$t('membersSettings.membersTable.columns.role'),
          MemberRoleField,
          false,
          false,
          false,
          {
            roles: this.roles,
            userId: this.userId,
            workspaceId: this.workspace.id,
          }
        ),
      ]

      if (this.canListTeams) {
        columns.push(
          new CrudTableColumn(
            'teams',
            this.$t('membersSettings.membersTable.columns.teams'),
            MemberTeamsField,
            false,
            false,
            false,
            { canManage: this.canManageTeamMembers }
          )
        )
      }

      columns.push(
        new CrudTableColumn(
          'two_factor_auth',
          this.$t('membersSettings.membersTable.columns.2fa'),
          TwoFactorAuthField,
          false
        ),
        new CrudTableColumn(null, null, MoreField, false, false, true)
      )

      for (const plugin of this.membersPagePlugins) {
        columns = plugin.mutateMembersTableColumns(columns, {
          workspace: this.workspace,
          client: this.$client,
        })
      }
      return columns
    },
  },
  async mounted() {
    if (this.canListTeams) {
      try {
        const { data } = await TeamsService(this.$client).fetchAll(
          this.workspace.id
        )
        this.teams = data
      } catch (error) {
        notifyIf(error)
      }
    }
  },
  methods: {
    onRowContext({ row, event, target }) {
      event.preventDefault()
      if (target === undefined) {
        target = {
          left: event.clientX,
          top: event.clientY,
        }
      }

      const action = row.id === this.editMember.id ? 'toggle' : 'show'
      this.editMember = row
      this.$refs.editMemberContext[action](target, 'bottom', 'left', 4)
    },
    onEditRoleContext({ row, target }) {
      const action = row.id === this.editRoleMember.id ? 'toggle' : 'show'
      this.editRoleMember = row
      this.$refs.editRoleContext[action](target, 'bottom', 'left', 4)
    },
    onEditTeamsContext({ row, target }) {
      const action = row.id === this.editTeamsMember.id ? 'toggle' : 'show'
      this.editTeamsMember = row
      this.$refs.editTeamsContext[action](target, 'bottom', 'left', 4)
    },
    async roleUpdate({ uid: permissionsNew, subject: member }) {
      const oldMember = clone(member)
      const newMember = clone(member)
      newMember.permissions = permissionsNew
      this.$refs.crudTable.updateRow(newMember)

      try {
        await WorkspaceService(this.$client).updateUser(oldMember.id, {
          permissions: newMember.permissions,
        })
        await this.$store.dispatch('workspace/forceUpdateWorkspaceUser', {
          workspaceId: this.workspace.id,
          id: oldMember.id,
          values: { permissions: newMember.permissions },
        })
      } catch (error) {
        this.$refs.crudTable.updateRow(oldMember)
        notifyIf(error, 'workspace')
      }
    },
    /**
     * Adds the member to the team, or removes them from it when they are already a
     * member of it. The row is updated right away and reverted if the call fails.
     */
    async teamToggle({ member, team, member_of: memberOf }) {
      const oldMember = clone(member)
      const teams = memberOf
        ? (member.teams || []).filter((t) => t.id !== team.id)
        : [...(member.teams || []), { id: team.id, name: team.name }]
      const newMember = { ...clone(member), teams }
      this.$refs.crudTable.updateRow(newMember)
      this.editTeamsMember = newMember

      this.savingTeams = true
      try {
        const service = TeamsService(this.$client)
        if (memberOf) {
          await service.removeMembers(team.id, [member.user_id])
        } else {
          await service.addMembers(team.id, [member.user_id])
        }
      } catch (error) {
        this.$refs.crudTable.updateRow(oldMember)
        this.editTeamsMember = oldMember
        notifyIf(error)
      } finally {
        this.savingTeams = false
      }
    },
  },
}
</script>
