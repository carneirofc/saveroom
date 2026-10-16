<template>
  <div class="margin-bottom-3">
    <h2 class="admin-settings__group-title">
      {{ $t('backupsAdminPanel.destinationsTitle') }}
    </h2>
    <p class="admin-settings__group-description">
      {{ $t('backupsAdminPanel.destinationsDescription') }}
    </p>
    <div v-if="loading" class="loading"></div>
    <p v-else-if="destinations.length === 0">
      {{ $t('backupsAdminPanel.noDestinations') }}
    </p>
    <div v-else class="backups__list">
      <BackupListItem
        v-for="destination in destinations"
        :key="destination.name"
        :title="destination.name"
      >
        <template #detail>{{ destination.type }}</template>
        <template #badges>
          <Badge
            v-for="purpose in destination.purposes"
            :key="purpose"
            color="cyan"
            size="small"
          >
            {{ $t(`backupsAdminPanel.purposes.${purpose}`) }}
          </Badge>
        </template>
      </BackupListItem>
    </div>
  </div>
</template>

<script>
import BackupsAdminService from '@baserow/modules/core/services/admin/backups'
import BackupListItem from '@baserow/modules/core/components/backups/BackupListItem'
import { notifyIf } from '@baserow/modules/core/utils/error'

/**
 * Read-only overview of the data destinations the instance is configured with.
 * They come from the environment, so there is nothing to edit here.
 */
export default {
  name: 'BackupDestinationsCard',
  components: { BackupListItem },
  data() {
    return { loading: true, destinations: [] }
  },
  async mounted() {
    try {
      const { data } = await BackupsAdminService(
        this.$client
      ).listDestinations()
      this.destinations = data
    } catch (error) {
      notifyIf(error)
    } finally {
      this.loading = false
    }
  },
}
</script>
