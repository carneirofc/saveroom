import { vi, describe, test, expect } from 'vitest'

import { RealTimeHandler } from '@baserow/modules/core/plugins/realTimeHandler'

vi.mock('#imports', () => ({
  useRuntimeConfig: () => ({
    public: { publicBackendUrl: 'http://localhost' },
  }),
}))

function makeHandler(workspaces = {}) {
  const dispatched = []
  const store = {
    getters: {
      'auth/token': 'token',
      'auth/webSocketId': 'ws-id',
      'workspace/get': (id) => workspaces[id],
    },
    dispatch(name, value) {
      dispatched.push([name, value])
      return Promise.resolve()
    },
    subscribe() {},
  }
  const context = { store, app: { router: {} } }
  const handler = new RealTimeHandler(context)
  return { handler, context, dispatched }
}

async function fire(handler, context, type, data) {
  for (const callback of handler.events[type] || []) {
    await callback(context, data)
  }
}

describe('RealTimeHandler permissions_updated', () => {
  test('refetches permissions and applications, then notifies the user', async () => {
    const workspace = { id: 7 }
    const { handler, context, dispatched } = makeHandler({ 7: workspace })

    await fire(handler, context, 'permissions_updated', { workspace_id: 7 })

    expect(dispatched).toEqual([
      ['workspace/forceFetchPermissions', workspace],
      ['application/fetchAll', undefined],
      ['toast/setPermissionsUpdated', true],
    ])
  })

  test('ignores workspaces that are not loaded', async () => {
    const { handler, context, dispatched } = makeHandler({})

    await fire(handler, context, 'permissions_updated', { workspace_id: 99 })

    expect(dispatched).toEqual([])
  })
})
