<template>
  <div v-if="loading" class="loading margin-top-3"></div>
  <p v-else-if="empty" class="margin-top-3">{{ emptyText }}</p>
  <div v-else class="backups__list margin-top-3">
    <slot></slot>
  </div>
</template>

<script>
/**
 * The loading, empty and filled states shared by every list of the backup and
 * datalake export screens. Fill the default slot with `BackupListItem`s.
 */
export default {
  name: 'BackupList',
  props: {
    loading: {
      type: Boolean,
      default: false,
    },
    empty: {
      type: Boolean,
      default: false,
    },
    emptyText: {
      type: String,
      default: '',
    },
  },
}
</script>
