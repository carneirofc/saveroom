import { vi, describe, test, expect } from 'vitest'

import TeamsService from '@baserow/modules/core/services/teams'
import WorkspaceService from '@baserow/modules/core/services/workspace'
import AccessService from '@baserow/modules/database/services/access'

function fakeClient() {
  return {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  }
}

describe('TeamsService', () => {
  test('calls the team endpoints', () => {
    const client = fakeClient()
    const service = TeamsService(client)

    service.fetchAll(3)
    service.create(3, { name: 'Finance' })
    service.update(5, { name: 'Ops' })
    service.delete(5)
    service.addMembers(5, [1, 2])
    service.removeMembers(5, [2])

    expect(client.get).toHaveBeenCalledWith('/workspaces/teams/workspace/3/')
    expect(client.post).toHaveBeenCalledWith('/workspaces/teams/workspace/3/', {
      name: 'Finance',
    })
    expect(client.patch).toHaveBeenCalledWith('/workspaces/teams/5/', {
      name: 'Ops',
    })
    expect(client.delete).toHaveBeenCalledWith('/workspaces/teams/5/')
    expect(client.post).toHaveBeenCalledWith('/workspaces/teams/5/members/', {
      user_ids: [1, 2],
    })
    // Axios only sends a DELETE body through the `data` option.
    expect(client.delete).toHaveBeenCalledWith('/workspaces/teams/5/members/', {
      data: { user_ids: [2] },
    })
  })
})

describe('WorkspaceService members', () => {
  test('searches candidates and adds users', () => {
    const client = fakeClient()
    const service = WorkspaceService(client)

    service.searchUserCandidates(3, 'ali')
    service.addUsers(3, [4, 5], 'ADMIN')

    expect(client.get).toHaveBeenCalledWith(
      '/workspaces/users/workspace/3/candidates/',
      { params: { search: 'ali' } }
    )
    expect(client.post).toHaveBeenCalledWith('/workspaces/users/workspace/3/', {
      user_ids: [4, 5],
      permissions: 'ADMIN',
      team_ids: [],
      access_level: null,
    })
  })

  test('adds users into teams with a default access level', () => {
    const client = fakeClient()

    WorkspaceService(client).addUsers(3, [4], 'MEMBER', {
      teamIds: [7],
      accessLevel: 'viewer',
    })

    expect(client.post).toHaveBeenCalledWith('/workspaces/users/workspace/3/', {
      user_ids: [4],
      permissions: 'MEMBER',
      team_ids: [7],
      access_level: 'viewer',
    })
  })
})

describe('AccessService', () => {
  test('reads and sets grants on a scope', () => {
    const client = fakeClient()
    const service = AccessService(client)
    const grants = [{ subject_type: 'team', subject_id: 1, level: null }]

    service.get('table', 9)
    service.set('database', 2, grants)

    expect(client.get).toHaveBeenCalledWith('/database/access/table/9/')
    expect(client.put).toHaveBeenCalledWith('/database/access/database/2/', {
      grants,
    })
  })
})
