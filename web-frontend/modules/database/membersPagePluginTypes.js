import { Registerable } from '@baserow/modules/core/registry'
import CrudTableColumn from '@baserow/modules/core/crudTable/crudTableColumn'
import MemberAccessField from '@baserow/modules/database/components/access/MemberAccessField'

export class MembersPagePluginType extends Registerable {
  /**
   * Lets you manipulate the columns of the members table to either add, remove or
   * modify columns.
   *
   * You could always make sure to not make this function fail hard if it can't update
   * or remove something, since other plugins might have also altered the columns.
   */
  mutateMembersTableColumns(columns, context) {
    return columns
  }

  /**
   * A hook that lets you manipulate the columns of the admin users listing page.
   */
  mutateAdminUsersTableColumns(columns, context) {
    return columns
  }
}

/**
 * Adds the workspace default access level of every member to the members table, so an
 * admin sets the role, the teams and the access of a member in one place. The level
 * itself is owned by the database module (`contrib/database/access`), which is why it
 * is injected here instead of living in the core table.
 */
export class DatabaseAccessMembersPagePluginType extends MembersPagePluginType {
  static getType() {
    return 'database_access'
  }

  mutateMembersTableColumns(columns, { workspace }) {
    if (
      !this.app.$hasPermission(
        'workspace.manage_database_access',
        workspace,
        workspace.id
      )
    ) {
      return columns
    }

    const column = new CrudTableColumn(
      'access_level',
      this.app.$i18n.t('membersSettings.membersTable.columns.access'),
      MemberAccessField,
      false,
      false,
      false,
      { workspaceId: workspace.id }
    )
    // Right before the 2FA column, so the identity and permission columns stay
    // together; appended when that column is absent.
    const index = columns.findIndex((c) => c.key === 'two_factor_auth')
    if (index === -1) {
      return [...columns, column]
    }
    return [...columns.slice(0, index), column, ...columns.slice(index)]
  }
}
