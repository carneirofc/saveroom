<template>
  <Modal ref="modal" small @hidden="onHidden">
    <template v-if="confirmation">
      <h2 class="box__title">{{ confirmation.title }}</h2>
      <p>{{ confirmation.message }}</p>
      <div class="actions">
        <ul class="action__links">
          <li>
            <a @click.prevent="resolve(false)">
              {{ $t('confirmDataChange.cancel') }}
            </a>
          </li>
        </ul>
        <Button
          :type="confirmation.danger ? 'danger' : 'primary'"
          @click.prevent="resolve(true)"
        >
          {{ confirmation.confirmLabel || $t('confirmDataChange.confirm') }}
        </Button>
      </div>
    </template>
  </Modal>
</template>

<script>
import modal from '@baserow/modules/core/mixins/modal'

/**
 * Renders the data change confirmation requested via the `pendingRowChanges/confirm`
 * store action. Mount it once per page that can change data of a table with
 * protected editing enabled.
 */
export default {
  name: 'ConfirmDataChangeModal',
  mixins: [modal],
  computed: {
    confirmation() {
      return this.$store.getters['pendingRowChanges/getConfirmation']
    },
  },
  watch: {
    confirmation(value) {
      if (value) {
        this.show()
      } else {
        this.hide()
      }
    },
  },
  mounted() {
    this.$store.dispatch('pendingRowChanges/registerConfirmationHost')
  },
  beforeUnmount() {
    this.$store.dispatch('pendingRowChanges/unregisterConfirmationHost')
  },
  methods: {
    resolve(value) {
      this.$store.dispatch('pendingRowChanges/resolveConfirmation', value)
    },
    onHidden() {
      // Closing the modal in any other way (escape, clicking outside) cancels.
      if (this.confirmation) {
        this.resolve(false)
      }
    },
  },
}
</script>
