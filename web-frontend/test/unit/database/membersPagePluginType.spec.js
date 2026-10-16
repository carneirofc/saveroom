import { vi, describe, test, expect } from 'vitest'

import CrudTableColumn from '@baserow/modules/core/crudTable/crudTableColumn'
import SimpleField from '@baserow/modules/core/components/crudTable/fields/SimpleField'
import { DatabaseAccessMembersPagePluginType } from '@baserow/modules/database/membersPagePluginTypes'

describe('DatabaseAccessMembersPagePluginType', () => {
  const workspace = { id: 4 }

  function plugin(allowed) {
    const app = {
      $hasPermission: vi.fn(() => allowed),
      $i18n: { t: (key) => key },
    }
    return { type: new DatabaseAccessMembersPagePluginType({ app }), app }
  }

  function columns() {
    return [
      new CrudTableColumn('name', 'Name', SimpleField),
      new CrudTableColumn('two_factor_auth', '2FA', SimpleField),
    ]
  }

  test('adds the access column right before the 2FA column', () => {
    const { type, app } = plugin(true)

    const result = type.mutateMembersTableColumns(columns(), { workspace })

    expect(result.map((column) => column.key)).toEqual([
      'name',
      'access_level',
      'two_factor_auth',
    ])
    expect(app.$hasPermission).toHaveBeenCalledWith(
      'workspace.manage_database_access',
      workspace,
      4
    )
  })

  test('appends the column when there is no 2FA column', () => {
    const { type } = plugin(true)

    const result = type.mutateMembersTableColumns(
      [new CrudTableColumn('name', 'Name', SimpleField)],
      { workspace }
    )

    expect(result.map((column) => column.key)).toEqual(['name', 'access_level'])
  })

  test('adds nothing for a user who cannot manage access', () => {
    const { type } = plugin(false)

    const result = type.mutateMembersTableColumns(columns(), { workspace })

    expect(result.map((column) => column.key)).toEqual([
      'name',
      'two_factor_auth',
    ])
  })
})
