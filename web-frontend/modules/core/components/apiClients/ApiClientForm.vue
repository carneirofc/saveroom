<template>
  <form @submit.prevent="submit">
    <FormGroup
      :label="$t('apiClientForm.nameLabel')"
      small-label
      required
      :error="fieldHasErrors('name')"
      class="margin-bottom-2"
    >
      <FormInput
        ref="name"
        v-model="v$.values.name.$model"
        size="large"
        :error="fieldHasErrors('name')"
        @blur="v$.values.name.$touch()"
      ></FormInput>
      <template #error>{{ getFirstErrorMessage('name') }}</template>
    </FormGroup>

    <FormGroup
      :label="$t('apiClientForm.scopesLabel')"
      :helper-text="$t('apiClientForm.scopesHelp')"
      small-label
      required
      :error="fieldHasErrors('scopes')"
      class="margin-bottom-2"
    >
      <ApiClientScopes
        :model-value="values.scopes"
        @update:model-value="setScopes"
      />
      <template #error>{{ getFirstErrorMessage('scopes') }}</template>
    </FormGroup>

    <slot></slot>
  </form>
</template>

<script>
import { useVuelidate } from '@vuelidate/core'
import { helpers, required } from '@vuelidate/validators'

import form from '@baserow/modules/core/mixins/form'
import ApiClientScopes from '@baserow/modules/core/components/apiClients/ApiClientScopes'
import { toggleScopeSelection } from '@baserow/modules/core/apiClients/scopes'

export default {
  name: 'ApiClientForm',
  components: { ApiClientScopes },
  mixins: [form],
  setup() {
    return { v$: useVuelidate({ $lazy: true }) }
  },
  data() {
    return {
      values: {
        name: '',
        scopes: [],
      },
    }
  },
  mounted() {
    this.$refs.name.focus()
  },
  methods: {
    toggleScope(scope, selected) {
      this.setScopes(toggleScopeSelection(this.values.scopes, scope, selected))
    },
    setScopes(scopes) {
      this.values.scopes = scopes
      this.v$.values.scopes.$touch()
    },
  },
  validations() {
    return {
      values: {
        name: {
          required: helpers.withMessage(
            this.$t('error.requiredField'),
            required
          ),
        },
        scopes: {
          // `minLength` skips values it considers empty, so an empty array would
          // pass it. `required` is the one that rejects a zero length array.
          required: helpers.withMessage(
            this.$t('apiClientForm.scopeRequired'),
            required
          ),
        },
      },
    }
  },
}
</script>
