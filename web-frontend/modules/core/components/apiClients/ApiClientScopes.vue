<template>
  <div>
    <div
      v-for="scope in scopes"
      :key="scope"
      class="api-client__scope margin-bottom-1"
    >
      <Checkbox
        :model-value="modelValue.includes(scope)"
        @update:model-value="toggle(scope, $event)"
      >
        {{ $t(`apiClientScopes.${translationKey(scope)}`) }}
      </Checkbox>
      <div class="api-client__scope-description">
        {{ $t(`apiClientScopes.${translationKey(scope)}Description`) }}
      </div>
    </div>
  </div>
</template>

<script>
import {
  API_CLIENT_SCOPES,
  scopeTranslationKey,
  toggleScopeSelection,
} from '@baserow/modules/core/apiClients/scopes'

/**
 * The checkbox group for the scopes of an API client, shared by the create form and
 * the "Edit scopes" action of an existing client.
 */
export default {
  name: 'ApiClientScopes',
  props: {
    modelValue: {
      type: Array,
      required: true,
    },
  },
  emits: ['update:modelValue'],
  data() {
    return { scopes: API_CLIENT_SCOPES }
  },
  methods: {
    translationKey(scope) {
      return scopeTranslationKey(scope)
    },
    toggle(scope, selected) {
      this.$emit(
        'update:modelValue',
        toggleScopeSelection(this.modelValue, scope, selected)
      )
    },
  },
}
</script>
