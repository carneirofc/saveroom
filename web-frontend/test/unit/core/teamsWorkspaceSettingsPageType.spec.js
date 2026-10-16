import { vi, describe, test, expect } from 'vitest'

import { TeamsWorkspaceSettingsPageType } from '@baserow/modules/core/workspaceSettingsPageTypes'

describe('TeamsWorkspaceSettingsPageType', () => {
  const workspace = { id: 4 }

  function pageType(allowed) {
    const app = {
      $hasPermission: vi.fn(() => allowed),
      $i18n: { t: (key) => key },
    }
    return { page: new TeamsWorkspaceSettingsPageType({ app }), app }
  }

  test('is only available to users allowed to list teams', () => {
    const allowed = pageType(true)
    const denied = pageType(false)

    expect(allowed.page.hasPermission(workspace)).toBe(true)
    expect(denied.page.hasPermission(workspace)).toBe(false)
    expect(allowed.app.$hasPermission).toHaveBeenCalledWith(
      'workspace.list_teams',
      workspace,
      4
    )
  })

  test('routes to the teams settings page', () => {
    const { page } = pageType(true)

    expect(page.getType()).toBe('teams')
    expect(page.getName()).toBe('teamsSettings.tabTitle')
    expect(page.getRoute(workspace)).toEqual({
      name: 'settings-teams',
      params: { workspaceId: 4 },
    })
  })
})
