import moment from '@baserow/modules/core/moment'
import { notifyIf } from '@baserow/modules/core/utils/error'

/**
 * Locale-aware date and time, the same format everywhere in the backup and datalake
 * export screens. Empty for a missing value.
 */
export function formatDate(value) {
  return value ? moment(value).format('L LT') : ''
}

/**
 * Adds the applications installed by a finished restore job to the sidebar and tells
 * the user. Shared by the local and remote restore tabs.
 *
 * The sidebar store only knows the workspaces of the user, so an application
 * restored into another workspace (the staff admin panel can target any) is not
 * added to it, which would otherwise leave an application of a foreign workspace in
 * the store.
 */
export async function restoredApplicationsFinished(
  component,
  finishedJob,
  workspaceId
) {
  const installed = finishedJob.installed_applications || []
  const workspaceInStore =
    component.$store.getters['workspace/get'](workspaceId) !== undefined
  try {
    if (workspaceInStore) {
      for (const application of installed) {
        await component.$store.dispatch('application/forceCreate', application)
      }
    }
    component.$store.dispatch('toast/info', {
      title: component.$t('backupsModal.restoreFinishedTitle'),
      message: component.$t('backupsModal.restoreFinishedMessage', {
        count: installed.length,
      }),
    })
  } catch (error) {
    notifyIf(error, 'application')
  }
}
