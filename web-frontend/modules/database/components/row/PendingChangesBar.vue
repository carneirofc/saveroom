<template>
  <div
    v-if="count > 0"
    class="pending-changes-bar"
    :class="{ 'pending-changes-bar--inline': inline }"
  >
    <i class="pending-changes-bar__icon iconoir-warning-circle"></i>
    <span class="pending-changes-bar__count">
      {{ $t('pendingChanges.count', { count }, count) }}
    </span>
    <div class="pending-changes-bar__actions">
      <ButtonText tag="a" :disabled="saving" @click="discard">
        {{ $t('pendingChanges.discard') }}
      </ButtonText>
      <Button type="primary" :loading="saving" :disabled="saving" @click="save">
        {{ $t('pendingChanges.save') }}
      </Button>
    </div>
  </div>
</template>

<script>
import { notifyIf } from '@baserow/modules/core/utils/error'

/**
 * Shows the number of staged row changes of a table with protected editing enabled
 * and lets the user save or discard them. `Ctrl/Cmd + S` saves as well.
 */
export default {
  name: 'PendingChangesBar',
  props: {
    table: {
      type: Object,
      required: true,
    },
    fields: {
      type: Array,
      required: true,
    },
    storePrefix: {
      type: String,
      required: false,
      default: 'page/',
    },
    inline: {
      type: Boolean,
      required: false,
      default: false,
    },
  },
  computed: {
    count() {
      return this.$store.getters['pendingRowChanges/count'](this.table.id)
    },
    saving() {
      return this.$store.getters['pendingRowChanges/isSaving']
    },
  },
  mounted() {
    // The inline variant lives inside the row edit modal, next to a page level bar,
    // so only the page level bar listens to the keyboard shortcut.
    if (!this.inline) {
      this.keydownEvent = (event) => this.keydown(event)
      document.body.addEventListener('keydown', this.keydownEvent)
    }
  },
  beforeUnmount() {
    if (this.keydownEvent) {
      document.body.removeEventListener('keydown', this.keydownEvent)
    }
  },
  methods: {
    keydown(event) {
      if (
        (event.ctrlKey || event.metaKey) &&
        event.key.toLowerCase() === 's' &&
        this.count > 0
      ) {
        event.preventDefault()
        this.save()
      }
    },
    async save() {
      try {
        await this.$store.dispatch('pendingRowChanges/save', {
          table: this.table,
          fields: this.fields,
          storePrefix: this.storePrefix,
        })
        this.$store.dispatch('toast/success', {
          title: this.$t('pendingChanges.saved'),
        })
      } catch (error) {
        notifyIf(error, 'row')
      }
    },
    async discard() {
      try {
        await this.$store.dispatch('pendingRowChanges/discard', {
          table: this.table,
          fields: this.fields,
          storePrefix: this.storePrefix,
        })
      } catch (error) {
        notifyIf(error, 'row')
      }
    },
  },
}
</script>
