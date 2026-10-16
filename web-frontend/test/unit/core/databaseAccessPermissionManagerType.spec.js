import { DatabaseAccessPermissionManagerType } from '@baserow/modules/core/permissionManagerTypes'

const LEVEL_OPERATIONS = {
  viewer: ['application.read', 'database.list_tables', 'database.table.read'],
  editor: [
    'application.read',
    'database.list_tables',
    'database.table.read',
    'database.table.create_row',
  ],
  builder: [
    'application.read',
    'application.update',
    'database.list_tables',
    'database.create_table',
    'database.table.read',
    'database.table.create_row',
    'database.table.create_field',
  ],
}

function permissions(overrides = {}) {
  return {
    workspace: null,
    databases: {},
    tables: {},
    databases_with_accessible_tables: [],
    family_operations: LEVEL_OPERATIONS.builder,
    level_operations: LEVEL_OPERATIONS,
    database_passthrough_operations: [
      'application.read',
      'database.list_tables',
    ],
    ...overrides,
  }
}

const database = { id: 1, type: 'database', tables: [{ id: 10 }, { id: 11 }] }
const otherDatabase = { id: 2, type: 'database', tables: [{ id: 20 }] }
const table = { id: 10, database_id: 1 }
const otherTable = { id: 11, database_id: 1 }
const otherDatabaseTable = { id: 20, database_id: 2 }
const field = { id: 100, table_id: 10 }

function createManager() {
  const store = {
    getters: { 'application/getAll': [database, otherDatabase] },
  }
  return new DatabaseAccessPermissionManagerType({ app: { $store: store } })
}

describe('DatabaseAccessPermissionManagerType', () => {
  const manager = createManager()

  test('defers without a permission object or grant', () => {
    expect(
      manager.hasPermission(null, 'database.table.read', table, 1)
    ).toBeNull()
    expect(
      manager.hasPermission(permissions(), 'database.table.read', table, 1)
    ).toBeNull()
  })

  test('defers operations outside the database family and unknown contexts', () => {
    const perms = permissions({ workspace: 'none' })

    expect(manager.hasPermission(perms, 'workspace.read', {}, 1)).toBeNull()
    expect(
      manager.hasPermission(perms, 'database.table.read', { id: 5 }, 1)
    ).toBeNull()
  })

  test('most specific scope wins', () => {
    const perms = permissions({
      workspace: 'none',
      databases: { 1: 'viewer' },
      tables: { 10: 'editor' },
    })

    expect(
      manager.hasPermission(perms, 'database.table.create_row', table, 1)
    ).toBe(true)
    expect(
      manager.hasPermission(perms, 'database.table.create_field', table, 1)
    ).toBe(false)
    expect(
      manager.hasPermission(perms, 'database.table.read', otherTable, 1)
    ).toBe(true)
    expect(
      manager.hasPermission(perms, 'database.table.create_row', otherTable, 1)
    ).toBe(false)
    expect(
      manager.hasPermission(perms, 'database.table.read', otherDatabaseTable, 1)
    ).toBe(false)
  })

  test('contexts with a table_id resolve through their table', () => {
    const perms = permissions({ databases: { 1: 'builder' } })

    expect(
      manager.hasPermission(perms, 'database.table.create_field', field, 1)
    ).toBe(true)
  })

  test('database stays reachable when one of its tables is accessible', () => {
    const perms = permissions({
      databases: { 1: 'none' },
      tables: { 10: 'viewer' },
      databases_with_accessible_tables: [1],
    })

    expect(manager.hasPermission(perms, 'application.read', database, 1)).toBe(
      true
    )
    expect(
      manager.hasPermission(perms, 'database.create_table', database, 1)
    ).toBe(false)
    expect(
      manager.hasPermission(perms, 'database.table.read', otherTable, 1)
    ).toBe(false)
  })

  test('builder on a database allows database operations', () => {
    const perms = permissions({ databases: { 2: 'builder' } })

    expect(
      manager.hasPermission(perms, 'database.create_table', otherDatabase, 1)
    ).toBe(true)
    expect(
      manager.hasPermission(perms, 'application.update', database, 1)
    ).toBeNull()
  })
})
