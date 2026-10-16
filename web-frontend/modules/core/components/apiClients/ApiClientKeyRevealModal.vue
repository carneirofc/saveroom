<template>
  <Modal ref="modal" :full-screen="false" :close-button="false">
    <h2 class="box__title">{{ $t('apiClientKeyRevealModal.title') }}</h2>
    <Alert type="warning">
      <template #title>{{
        $t('apiClientKeyRevealModal.warningTitle')
      }}</template>
      {{ $t('apiClientKeyRevealModal.warning') }}
    </Alert>
    <div class="api-client__key-reveal margin-top-2 margin-bottom-2">
      <div class="api-client__key-box">{{ secret }}</div>
      <a
        v-tooltip="$t('apiClientKeyRevealModal.copy')"
        class="api-client__key-copy"
        @click="copy()"
      >
        <i class="iconoir-copy" />
        <Copied ref="copied"></Copied>
      </a>
    </div>
    <p class="api-client__key-usage">
      {{ $t('apiClientKeyRevealModal.usage') }}
    </p>
    <div class="actions">
      <div class="align-right">
        <Button type="primary" size="large" @click="hide()">
          {{ $t('apiClientKeyRevealModal.confirm') }}
        </Button>
      </div>
    </div>
  </Modal>
</template>

<script>
import modal from '@baserow/modules/core/mixins/modal'
import { copyToClipboard } from '@baserow/modules/database/utils/clipboard'

export default {
  name: 'ApiClientKeyRevealModal',
  mixins: [modal],
  data() {
    return {
      secret: '',
    }
  },
  methods: {
    show(secret, ...args) {
      this.secret = secret
      modal.methods.show.bind(this)(...args)
    },
    hide(...args) {
      // The backend cannot show this again, but that is no reason to keep it in
      // memory once the user has closed the modal.
      this.secret = ''
      modal.methods.hide.bind(this)(...args)
    },
    copy() {
      copyToClipboard(this.secret)
      this.$refs.copied.show()
    },
  },
}
</script>
