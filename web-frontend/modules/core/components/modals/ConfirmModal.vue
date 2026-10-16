<template>
  <Modal ref="modal" small :close-button="false" @hidden="reset">
    <h2 class="box__title">{{ title }}</h2>
    <p>{{ message }}</p>
    <div class="actions">
      <div class="flex justify-content-end">
        <Button
          type="secondary"
          class="margin-right-1"
          :disabled="loading"
          @click.prevent="cancel"
        >
          {{ $t('action.cancel') }}
        </Button>
        <Button type="danger" :loading="loading" @click.prevent="confirm">
          {{ confirmLabel }}
        </Button>
      </div>
    </div>
  </Modal>
</template>

<script>
import modal from '@baserow/modules/core/mixins/modal'

/**
 * Generic "are you sure" modal for a destructive action. The caller opens it with
 * `ask({ title, message, confirmLabel, onConfirm })`; `onConfirm` only runs when
 * the user confirms, so a single misclick never deletes, restores or resets
 * anything.
 */
export default {
  name: 'ConfirmModal',
  mixins: [modal],
  emits: ['confirm', 'cancel'],
  data() {
    return {
      title: '',
      message: '',
      confirmLabel: '',
      pending: null,
      loading: false,
    }
  },
  methods: {
    reset() {
      this.pending = null
      this.loading = false
    },
    ask({ title, message, confirmLabel, onConfirm }) {
      this.title = title
      this.message = message
      this.confirmLabel = confirmLabel || this.$t('action.delete')
      this.pending = onConfirm || null
      this.show()
    },
    cancel() {
      if (this.loading) {
        return
      }
      this.pending = null
      this.$emit('cancel')
      this.hide()
    },
    /**
     * The modal stays open, with the confirm button loading, until `onConfirm`
     * settles, so the action cannot be triggered twice and its outcome is not
     * hidden behind an already closed dialog.
     */
    async confirm() {
      if (this.loading) {
        return
      }
      const onConfirm = this.pending
      this.pending = null
      this.$emit('confirm')
      this.loading = true
      try {
        if (onConfirm) {
          await onConfirm()
        }
      } finally {
        this.loading = false
        this.hide()
      }
    },
  },
}
</script>
