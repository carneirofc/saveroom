import { Registerable } from '@baserow/modules/core/registry'

export class WorkspaceSettingsPageType extends Registerable {
  /**
   * The name of the page in the tabs navigation at the top of the page.
   */
  getName() {
    return null
  }

  constructor(...args) {
    super(...args)
    this.type = this.getType()

    if (this.type === null) {
      throw new Error('The type name of a workspace settings page must be set.')
    }
  }

  serialize() {
    return {
      type: this.type,
      name: this.getName(),
    }
  }

  /**
   * Responsible for returning whether the user has access
   * to this workspace settings page type. By default, they do.
   */
  hasPermission(workspace) {
    return true
  }

  getRoute() {
    throw new Error('The `getRoute` method must be set.')
  }
}

export class MembersWorkspaceSettingsPageType extends WorkspaceSettingsPageType {
  static getType() {
    return 'members'
  }

  getName() {
    const { $i18n: i18n } = this.app
    return i18n.t('membersSettings.membersTabTitle')
  }

  getRoute(workspace) {
    return {
      name: 'settings-members',
      params: {
        workspaceId: workspace.id,
      },
    }
  }
}

export class TeamsWorkspaceSettingsPageType extends WorkspaceSettingsPageType {
  static getType() {
    return 'teams'
  }

  getName() {
    const { $i18n: i18n } = this.app
    return i18n.t('teamsSettings.tabTitle')
  }

  hasPermission(workspace) {
    return this.app.$hasPermission(
      'workspace.list_teams',
      workspace,
      workspace.id
    )
  }

  getRoute(workspace) {
    return {
      name: 'settings-teams',
      params: {
        workspaceId: workspace.id,
      },
    }
  }
}
