<template>
  <Expandable card class="margin-top-2">
    <template #header="{ toggle, expanded }">
      <div class="api-client__head">
        <div class="api-client__name">
          <Editable
            ref="rename"
            :value="client.name"
            @change="update({ name: $event.value }, { name: $event.oldValue })"
          ></Editable>
        </div>
        <a
          ref="contextLink"
          class="api-client__more"
          @click.prevent="
            $refs.context.toggle($refs.contextLink, 'bottom', 'right', 4)
          "
        >
          <i class="baserow-icon-more-horizontal"></i>
        </a>
        <Context ref="context" overflow-scroll max-height-if-outside-viewport>
          <ul class="context__menu">
            <li class="context__menu-item">
              <a class="context__menu-item-link" @click="enableRename()">
                <i class="context__menu-item-icon iconoir-edit-pencil"></i>
                {{ $t('action.rename') }}
              </a>
            </li>
            <li class="context__menu-item">
              <a
                class="context__menu-item-link"
                @click.prevent="startEditScopes"
              >
                <i class="context__menu-item-icon iconoir-lock"></i>
                {{ $t('apiClient.editScopes') }}
              </a>
            </li>
            <li class="context__menu-item">
              <a
                class="context__menu-item-link context__menu-item-link--delete"
                :class="{ 'context__menu-item-link--loading': deleteLoading }"
                @click.prevent="remove()"
              >
                <i class="context__menu-item-icon iconoir-bin"></i>
                {{ $t('action.delete') }}
              </a>
            </li>
          </ul>
        </Context>
      </div>
      <div v-if="editingScopes" class="api-client__scopes-editor">
        <ApiClientScopes v-model="scopeDraft" />
        <p v-if="scopeDraft.length === 0" class="color-error">
          {{ $t('apiClientForm.scopeRequired') }}
        </p>
        <div class="flex margin-top-1">
          <Button
            size="small"
            :loading="scopesLoading"
            :disabled="scopeDraft.length === 0"
            @click.prevent="saveScopes"
          >
            {{ $t('apiClient.saveScopes') }}
          </Button>
          <Button
            type="secondary"
            size="small"
            class="margin-left-1"
            :disabled="scopesLoading"
            @click.prevent="editingScopes = false"
          >
            {{ $t('action.cancel') }}
          </Button>
        </div>
      </div>
      <div v-else class="api-client__meta">
        <div class="api-client__scopes">
          <Badge
            v-for="scope in client.scopes"
            :key="scope"
            color="cyan"
            size="small"
          >
            {{ scope }}
          </Badge>
          <span v-if="client.scopes.length === 0">
            {{ $t('apiClient.noScopes') }}
          </span>
        </div>
        <div class="api-client__toggle">
          <a @click="toggle">
            {{ $t('apiClient.keysLabel', { count: client.keys.length })
            }}<i
              :class="
                expanded ? 'iconoir-nav-arrow-down' : 'iconoir-nav-arrow-right'
              "
            />
          </a>
        </div>
      </div>
    </template>

    <FormGroup
      small-label
      :label="$t('apiClient.activeLabel')"
      :helper-text="$t('apiClient.activeHelp')"
      class="margin-bottom-2"
    >
      <SwitchInput
        :model-value="client.is_active"
        @update:model-value="
          update({ is_active: $event }, { is_active: client.is_active })
        "
      >
        {{ $t('apiClient.active') }}
      </SwitchInput>
    </FormGroup>

    <table v-if="client.keys.length > 0" class="api-client__keys">
      <thead>
        <tr>
          <th>{{ $t('apiClient.keyName') }}</th>
          <th>{{ $t('apiClient.keyPrefix') }}</th>
          <th>{{ $t('apiClient.keyCreatedOn') }}</th>
          <th>{{ $t('apiClient.keyLastUsedOn') }}</th>
          <th>{{ $t('apiClient.keyExpiresOn') }}</th>
          <th>{{ $t('apiClient.keyStatus') }}</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="key in client.keys" :key="key.id">
          <td>{{ key.name || '-' }}</td>
          <td class="api-client__key-prefix">{{ key.prefix }}</td>
          <td>{{ formatDate(key.created_on) }}</td>
          <td>{{ formatDate(key.last_used_on) }}</td>
          <td>{{ formatDate(key.expires_on) }}</td>
          <td>
            <Badge :color="statusColor(key)" size="small">
              {{ $t(`apiClient.keyStatuses.${status(key)}`) }}
            </Badge>
          </td>
          <td>
            <a
              v-if="!key.revoked_on"
              class="api-client__key-revoke"
              :class="{
                'api-client__key-revoke--loading': revoking === key.id,
              }"
              @click.prevent="revoke(key)"
            >
              {{ $t('apiClient.revoke') }}
            </a>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="api-client__empty">{{ $t('apiClient.noKeys') }}</p>

    <ApiClientKeyForm
      v-if="creatingKey"
      :loading="keyLoading"
      class="margin-top-2"
      @submit="createKey($event)"
      @cancel="creatingKey = false"
    />
    <Button
      v-else
      type="secondary"
      class="margin-top-2"
      @click="creatingKey = true"
    >
      {{ $t('apiClient.newKey') }}
    </Button>
  </Expandable>
</template>

<script>
import ApiClientsService from '@baserow/modules/core/services/apiClients'
import ApiClientScopes from '@baserow/modules/core/components/apiClients/ApiClientScopes'
import ApiClientKeyForm from '@baserow/modules/core/components/apiClients/ApiClientKeyForm'
import { notifyIf } from '@baserow/modules/core/utils/error'

export default {
  name: 'ApiClient',
  components: { ApiClientKeyForm, ApiClientScopes },
  props: {
    client: {
      type: Object,
      required: true,
    },
  },
  emits: ['deleted', 'key-created'],
  data() {
    return {
      deleteLoading: false,
      editingScopes: false,
      scopeDraft: [],
      scopesLoading: false,
      creatingKey: false,
      keyLoading: false,
      revoking: null,
    }
  },
  methods: {
    enableRename() {
      this.$refs.context.hide()
      this.$refs.rename.edit()
    },
    startEditScopes() {
      this.$refs.context.hide()
      this.scopeDraft = [...this.client.scopes]
      this.editingScopes = true
    },
    async saveScopes() {
      if (this.scopeDraft.length === 0) {
        return
      }
      this.scopesLoading = true
      try {
        const scopes = [...this.scopeDraft]
        const { data } = await ApiClientsService(this.$client).update(
          this.client.id,
          { scopes }
        )
        this.client.scopes = data?.scopes || scopes
        this.editingScopes = false
      } catch (error) {
        notifyIf(error)
      } finally {
        this.scopesLoading = false
      }
    },
    formatDate(value) {
      return value ? new Date(value).toLocaleString() : '-'
    },
    status(key) {
      if (key.revoked_on) {
        return 'revoked'
      }
      return key.is_usable ? 'active' : 'expired'
    },
    statusColor(key) {
      return { revoked: 'red', expired: 'yellow', active: 'green' }[
        this.status(key)
      ]
    },
    async update(values, old) {
      Object.assign(this.client, values)

      try {
        await ApiClientsService(this.$client).update(this.client.id, values)
      } catch (error) {
        Object.assign(this.client, old)
        notifyIf(error)
      }
    },
    async remove() {
      if (this.deleteLoading) {
        return
      }
      this.deleteLoading = true

      try {
        await ApiClientsService(this.$client).delete(this.client.id)
        this.$emit('deleted', this.client)
      } catch (error) {
        notifyIf(error)
      } finally {
        this.deleteLoading = false
      }
    },
    async createKey(values) {
      this.keyLoading = true

      try {
        const { data } = await ApiClientsService(this.$client).createKey(
          this.client.id,
          values
        )
        const { key, ...stored } = data
        this.client.keys.push(stored)
        this.creatingKey = false
        // The secret is handed straight to the reveal modal and deliberately not
        // kept on the key we just stored: the backend can never return it again.
        this.$emit('key-created', key)
      } catch (error) {
        notifyIf(error)
      } finally {
        this.keyLoading = false
      }
    },
    async revoke(key) {
      if (this.revoking !== null) {
        return
      }
      this.revoking = key.id

      try {
        const { data } = await ApiClientsService(this.$client).revokeKey(key.id)
        // Revoking keeps the record so the revocation stays visible, so the row is
        // updated in place rather than removed.
        Object.assign(key, data)
      } catch (error) {
        notifyIf(error)
      } finally {
        this.revoking = null
      }
    },
  },
}
</script>
