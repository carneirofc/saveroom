import baseService, {
  serializeSorts,
} from '@baserow/modules/core/crudTable/baseService'

/**
 * Drops every filter the user left blank. The backend applies an exact lookup for
 * each filter it receives, so sending `?user_id=` would filter on an empty string
 * instead of meaning "no filter".
 */
export const omitEmptyFilters = (filters) =>
  Object.fromEntries(
    Object.entries(filters || {}).filter(
      ([, value]) => value !== null && value !== undefined && value !== ''
    )
  )

export default (client) => {
  return Object.assign(baseService(client, '/admin/audit-log/'), {
    fetchFilterOptions() {
      return client.get('/admin/audit-log/filter-options/')
    },
    export(searchQuery, sorts, filters) {
      const params = omitEmptyFilters(filters)
      if (searchQuery) {
        params.search = searchQuery
      }
      const serializedSorts = serializeSorts(sorts)
      if (serializedSorts) {
        params.sorts = serializedSorts
      }
      return client.get('/admin/audit-log/export/', {
        params,
        responseType: 'blob',
      })
    },
  })
}
