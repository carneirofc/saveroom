import {
  LocalBaserowListRowsServiceType,
  LocalBaserowGetRowServiceType,
  LocalBaserowTableServiceType,
  LocalBaserowCreateRowWorkflowServiceType,
  LocalBaserowDeleteRowWorkflowServiceType,
  LocalBaserowFieldsUpdatedTriggerServiceType,
} from '@baserow/modules/integrations/localBaserow/serviceTypes'
import { TestApp } from '@baserow/test/helpers/testApp'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// Read rather than imported: the i18n loader turns an imported locale file
// into compiled message ASTs, which the copy below can't be read off of.
const en = JSON.parse(
  readFileSync(
    resolve(process.cwd(), 'modules/integrations/locales/en.json'),
    'utf8'
  )
)

describe('Local baserow service types', () => {
  let testApp = null

  beforeEach(() => {
    testApp = new TestApp()
  })

  afterEach(() => {
    testApp.afterEach()
  })

  test('Get service should prepareValuePath', () => {
    const fakeApp = {}
    const serviceType = new LocalBaserowGetRowServiceType(fakeApp)

    const service = {
      schema: {
        properties: { id: { title: 'Id' }, field_42: { title: 'Field 42' } },
      },
    }

    expect(serviceType.prepareValuePath(service, [])).toEqual([])
    expect(serviceType.prepareValuePath(service, [0])).toEqual([0])
    expect(serviceType.prepareValuePath(service, ['id'])).toEqual(['id'])
    expect(serviceType.prepareValuePath(service, ['field_42'])).toEqual([
      'Field 42',
    ])
    expect(
      serviceType.prepareValuePath(service, ['field_42', 'value'])
    ).toEqual(['Field 42', 'value'])
  })

  test('List service should prepareValuePath', () => {
    const fakeApp = {}
    const serviceType = new LocalBaserowListRowsServiceType(fakeApp)

    const service = {
      schema: {
        items: {
          properties: { id: { title: 'Id' }, field_42: { title: 'Field 42' } },
        },
      },
    }

    expect(serviceType.prepareValuePath(service, [])).toEqual([])
    expect(serviceType.prepareValuePath(service, [0])).toEqual([0])
    expect(serviceType.prepareValuePath(service, ['id'])).toEqual(['id'])
    expect(serviceType.prepareValuePath(service, ['field_42'])).toEqual([
      'Field 42',
    ])
    expect(
      serviceType.prepareValuePath(service, ['field_42', 'value'])
    ).toEqual(['Field 42', 'value'])
  })

  test('List service should resolve correctly in builder data provider', () => {
    const dataProvider = testApp
      .getRegistry()
      .get('builderDataProvider', 'data_source')

    const service = {
      id: 1,
      type: 'local_baserow_list_rows',
      schema: {
        items: {
          properties: { id: { title: 'Id' }, field_42: { title: 'Field 42' } },
        },
      },
    }

    dataProvider.getDataSourceContent = vi.fn(() => [
      { id: 1, 'Field 42': 'Field 42 content row 1' },
      { id: 2, 'Field 42': 'Field 42 content row 2' },
    ])

    const page = { id: 2, dataSources: [service] }

    const applicationContext = {
      builder: {
        pages: [{ id: 1, shared: true, dataSources: [] }, page],
      },
      page,
    }

    expect(dataProvider.getDataChunk(applicationContext, ['1'])).toEqual([
      { id: 1, 'Field 42': 'Field 42 content row 1' },
      { id: 2, 'Field 42': 'Field 42 content row 2' },
    ])
    expect(dataProvider.getDataChunk(applicationContext, ['1', '0'])).toEqual({
      id: 1,
      'Field 42': 'Field 42 content row 1',
    })
    expect(dataProvider.getDataChunk(applicationContext, ['1', '1'])).toEqual({
      id: 2,
      'Field 42': 'Field 42 content row 2',
    })
    expect(
      dataProvider.getDataChunk(applicationContext, ['1', '1', 'id'])
    ).toEqual(2)
    expect(
      dataProvider.getDataChunk(applicationContext, ['1', '1', 'field_42'])
    ).toEqual('Field 42 content row 2')
    expect(
      dataProvider.getDataChunk(applicationContext, ['1', '*', 'field_42'])
    ).toEqual(['Field 42 content row 1', 'Field 42 content row 2'])
  })

  test('Get service should resolve correctly in builder data provider', () => {
    const dataProvider = testApp
      .getRegistry()
      .get('builderDataProvider', 'data_source')

    const service = {
      id: 1,
      type: 'local_baserow_get_row',
      schema: {
        properties: { id: { title: 'Id' }, field_42: { title: 'Field 42' } },
      },
    }

    dataProvider.getDataSourceContent = vi.fn(() => ({
      id: 1,
      'Field 42': 'Field 42 content',
    }))

    const page = { id: 2, dataSources: [service] }

    const applicationContext = {
      builder: {
        pages: [{ id: 1, shared: true, dataSources: [] }, page],
      },
      page,
    }

    expect(dataProvider.getDataChunk(applicationContext, ['1'])).toEqual({
      id: 1,
      'Field 42': 'Field 42 content',
    })
    expect(dataProvider.getDataChunk(applicationContext, ['1', 'id'])).toEqual(
      1
    )
    expect(
      dataProvider.getDataChunk(applicationContext, ['1', 'field_42'])
    ).toEqual('Field 42 content')
  })

  test('LocalBaserowTableServiceType supportedTables returns all tables it is given.', () => {
    const fakeApp = {}
    const serviceType = new LocalBaserowTableServiceType(fakeApp)

    const tables = [
      {
        id: 1,
        name: 'Table 1',
        is_data_sync: false,
        is_two_way_data_sync: false,
      },
      {
        id: 2,
        name: 'Table 2',
        is_data_sync: true,
        is_two_way_data_sync: false,
      },
      {
        id: 3,
        name: 'Table 3',
        is_data_sync: true,
        is_two_way_data_sync: true,
      },
    ]

    const result = serviceType.supportedTables(tables)
    expect(result).toEqual(tables)
    expect(result.length).toBe(3)
  })

  test('LocalBaserowCreateRowWorkflowServiceType supportedTables returns non data-synced tables or two-way data-synced tables.', () => {
    const fakeApp = {}
    const serviceType = new LocalBaserowCreateRowWorkflowServiceType(fakeApp)

    const tables = [
      {
        id: 1,
        name: 'Table 1',
        is_data_sync: false,
        is_two_way_data_sync: false,
      },
      {
        id: 2,
        name: 'Table 2',
        is_data_sync: true,
        is_two_way_data_sync: false,
      },
      {
        id: 3,
        name: 'Table 3',
        is_data_sync: true,
        is_two_way_data_sync: true,
      },
    ]

    const result = serviceType.supportedTables(tables)
    expect(result).toEqual([
      {
        id: 1,
        name: 'Table 1',
        is_data_sync: false,
        is_two_way_data_sync: false,
      },
      {
        id: 3,
        name: 'Table 3',
        is_data_sync: true,
        is_two_way_data_sync: true,
      },
    ])
    expect(result.length).toBe(2)
  })

  test('LocalBaserowDeleteRowWorkflowServiceType supportedTables returns non data-synced tables or two-way data-synced tables', () => {
    const fakeApp = {}
    const serviceType = new LocalBaserowDeleteRowWorkflowServiceType(fakeApp)

    const tables = [
      {
        id: 1,
        name: 'Table 1',
        is_data_sync: false,
        is_two_way_data_sync: false,
      },
      {
        id: 2,
        name: 'Table 2',
        is_data_sync: true,
        is_two_way_data_sync: false,
      },
      {
        id: 3,
        name: 'Table 3',
        is_data_sync: true,
        is_two_way_data_sync: true,
      },
    ]

    const result = serviceType.supportedTables(tables)
    expect(result).toEqual([
      {
        id: 1,
        name: 'Table 1',
        is_data_sync: false,
        is_two_way_data_sync: false,
      },
      {
        id: 3,
        name: 'Table 3',
        is_data_sync: true,
        is_two_way_data_sync: true,
      },
    ])
    expect(result.length).toBe(2)
  })

  test('LocalBaserowFieldsUpdatedTriggerServiceType is in error unless a table and at least one field are selected', () => {
    const serviceType = new LocalBaserowFieldsUpdatedTriggerServiceType({
      app: { $i18n: { t: (key) => key } },
    })

    expect(
      serviceType.isInError({ service: { table_id: null, field_ids: [] } })
    ).toBe(true)
    expect(
      serviceType.isInError({ service: { table_id: 1, field_ids: [] } })
    ).toBe(true)
    expect(
      serviceType.isInError({ service: { table_id: null, field_ids: [1] } })
    ).toBe(true)
    expect(
      serviceType.isInError({ service: { table_id: 1, field_ids: [1, 2] } })
    ).toBe(false)
  })

  test('the update row service is in error without a row ID, the create row service is not', () => {
    const registry = testApp.getRegistry()
    const updateRow = registry.get('service', 'local_baserow_update_row')
    const createRow = registry.get('service', 'local_baserow_create_row')
    const emptyRowId = { formula: '', mode: 'simple', version: '0.1' }
    const rowId = { formula: "get('row.id')", mode: 'simple', version: '0.1' }

    expect(
      updateRow.getErrorMessage({
        service: { table_id: 1, row_id: emptyRowId },
      })
    ).toBe('serviceType.errorNoRowIdSelected')
    expect(
      updateRow.getErrorMessage({
        service: { table_id: 1, row_id: { ...emptyRowId, formula: '  ' } },
      })
    ).toBe('serviceType.errorNoRowIdSelected')
    expect(
      updateRow.getErrorMessage({ service: { table_id: 1, row_id: rowId } })
    ).toBe(null)
    // A public page's service carries no formulas, so nothing to check.
    expect(updateRow.getErrorMessage({ service: { table_id: 1 } })).toBe(null)
    // The table comes first: the row ID input is disabled until one is chosen.
    expect(
      updateRow.getErrorMessage({
        service: { table_id: null, row_id: emptyRowId },
      })
    ).toBe('serviceType.errorNoTableSelected')
    expect(
      createRow.getErrorMessage({
        service: { table_id: 1, row_id: emptyRowId },
      })
    ).toBe(null)
    expect(en.serviceType.errorNoRowIdSelected).toBe('No row ID selected')
  })

  test('the create rows service reports a missing table before missing rows', () => {
    const createRows = testApp
      .getRegistry()
      .get('service', 'local_baserow_create_rows')
    const emptyRows = { formula: '', mode: 'simple', version: '0.1' }

    expect(
      createRows.getErrorMessage({
        service: { table_id: null, rows: emptyRows },
      })
    ).toBe('serviceType.errorNoTableSelected')
    expect(
      createRows.getErrorMessage({ service: { table_id: 1, rows: emptyRows } })
    ).toBe('serviceType.errorNoRowsSelected')
  })
})
