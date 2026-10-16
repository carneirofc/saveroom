<template>
  <Modal ref="modal" :full-screen="false" :close-button="true">
    <h2 class="box__title">
      {{ $t('apiClientsModal.title') }} {{ workspace.name }}
    </h2>
    <p>{{ $t('apiClientsModal.description') }}</p>
    <Error :error="error"></Error>
    <div v-if="loading" class="loading margin-top-2 margin-bottom-2"></div>
    <template v-else>
      <ApiClientForm
        v-if="creating"
        class="margin-top-2"
        @submitted="create($event)"
      >
        <div class="flex justify-content-end">
          <Button
            type="secondary"
            class="margin-right-1"
            @click.prevent="creating = false"
          >
            {{ $t('action.cancel') }}
          </Button>
          <Button
            :loading="createLoading"
            :disabled="createLoading"
            type="primary"
          >
            {{ $t('apiClientsModal.create') }}
          </Button>
        </div>
      </ApiClientForm>
      <Button
        v-else
        type="primary"
        class="margin-top-2"
        @click="creating = true"
      >
        {{ $t('apiClientsModal.newClient') }}
      </Button>

      <ApiClient
        v-for="client in clients"
        :key="client.id"
        :client="client"
        @deleted="removeClient($event)"
        @key-created="$refs.revealModal.show($event)"
      />
      <p v-if="clients.length === 0" class="margin-top-2">
        {{ $t('apiClientsModal.noClients') }}
      </p>
    </template>
    <ApiClientKeyRevealModal ref="revealModal"></ApiClientKeyRevealModal>
  </Modal>
</template>

<script>
import modal from '@baserow/modules/core/mixins/modal'
import error from '@baserow/modules/core/mixins/error'
import ApiClientsService from '@baserow/modules/core/services/apiClients'
import ApiClient from '@baserow/modules/core/components/apiClients/ApiClient'
import ApiClientForm from '@baserow/modules/core/components/apiClients/ApiClientForm'
import ApiClientKeyRevealModal from '@baserow/modules/core/components/apiClients/ApiClientKeyRevealModal'

export default {
  name: 'ApiClientsModal',
  components: { ApiClient, ApiClientForm, ApiClientKeyRevealModal },
  mixins: [modal, error],
  props: {
    workspace: {
      type: Object,
      required: true,
    },
  },
  data() {
    return {
      loading: false,
      creating: false,
      createLoading: false,
      clients: [],
    }
  },
  methods: {
    show(...args) {
      modal.methods.show.bind(this)(...args)
      this.load()
    },
    async load() {
      this.loading = true
      this.creating = false
      this.hideError()

      try {
        const { data } = await ApiClientsService(this.$client).fetchAll(
          this.workspace.id
        )
        this.clients = data
      } catch (error) {
        this.handleError(error)
      } finally {
        this.loading = false
      }
    },
    async create(values) {
      this.createLoading = true
      this.hideError()

      try {
        const { data } = await ApiClientsService(this.$client).create(
          this.workspace.id,
          values
        )
        this.clients.unshift(data)
        this.creating = false
      } catch (error) {
        this.handleError(error)
      } finally {
        this.createLoading = false
      }
    },
    removeClient(client) {
      this.clients = this.clients.filter((c) => c.id !== client.id)
    },
  },
}
</script>
