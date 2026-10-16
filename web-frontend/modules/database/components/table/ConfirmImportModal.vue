<template>
  <Modal ref="modal" small @show="resolved = false" @hidden="onHidden">
    <h2 class="box__title">{{ $t('importFileModal.confirmTitle') }}</h2>
    <p>
      {{ $t('importFileModal.confirmMessage', { table: tableName }) }}
    </p>
    <ul class="import-modal__confirm-summary">
      <li
        v-for="entry in entries"
        :key="entry.key"
        class="import-modal__confirm-summary-item"
      >
        <span class="import-modal__confirm-summary-label">
          {{ entry.label }}
        </span>
        <span class="import-modal__confirm-summary-count">
          {{ entry.count }}
        </span>
      </li>
    </ul>
    <Alert v-if="destructive" type="error" class="margin-top-2">
      {{ $t('importFileModal.confirmDestructive') }}
    </Alert>
    <Alert v-else-if="protectedTable" type="warning" class="margin-top-2">
      {{ $t('importFileModal.confirmProtected') }}
    </Alert>
    <div class="actions">
      <ul class="action__links">
        <li>
          <a @click.prevent="resolve(false)">
            {{ $t('action.cancel') }}
          </a>
        </li>
      </ul>
      <Button
        :type="destructive ? 'danger' : 'primary'"
        @click.prevent="resolve(true)"
      >
        {{ $t('importFileModal.importButton') }}
      </Button>
    </div>
  </Modal>
</template>

<script>
import modal from '@baserow/modules/core/mixins/modal'

/**
 * Asks the user to accept an import before it is sent to the backend. The counts
 * come from the import preview endpoint, which computes them over the whole file,
 * so they say exactly what the import is going to do.
 *
 * It is rendered inside the `ImportFileModal` instead of going through the
 * `pendingRowChanges/confirm` action because that one needs a mounted
 * `ConfirmDataChangeModal` host, which only the table page has, while an import can
 * be started from the sidebar of a table that isn't open.
 */
export default {
  name: 'ConfirmImportModal',
  mixins: [modal],
  props: {
    table: {
      type: Object,
      required: false,
      default: null,
    },
    /**
     * The `summary` of the import preview response.
     */
    summary: {
      type: Object,
      required: false,
      default: null,
    },
    destructive: {
      type: Boolean,
      required: false,
      default: false,
    },
    protectedTable: {
      type: Boolean,
      required: false,
      default: false,
    },
  },
  emits: ['confirmed', 'cancelled'],
  data() {
    return {
      // Makes sure that closing the modal after a choice doesn't emit again.
      resolved: false,
    }
  },
  computed: {
    tableName() {
      return this.table?.name || ''
    },
    entries() {
      const summary = this.summary || {}
      return ['create', 'update', 'unchanged', 'delete', 'skip', 'errors'].map(
        (key) => ({
          key,
          label: this.$t(`importFileModal.confirmCount.${key}`),
          count: summary[key] || 0,
        })
      )
    },
  },
  methods: {
    resolve(confirmed) {
      if (this.resolved) {
        return
      }
      this.resolved = true
      this.hide()
      this.$emit(confirmed ? 'confirmed' : 'cancelled')
    },
    onHidden() {
      // Closing in any other way, like escape or clicking outside, cancels.
      this.resolve(false)
    },
  },
}
</script>
