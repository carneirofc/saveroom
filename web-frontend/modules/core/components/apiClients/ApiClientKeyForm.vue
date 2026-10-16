<template>
  <form class="api-client__key-form" @submit.prevent="submit">
    <div class="row">
      <div class="col col-6">
        <FormGroup
          small-label
          :label="$t('apiClientKeyForm.nameLabel')"
          :helper-text="$t('apiClientKeyForm.nameHelp')"
          class="margin-bottom-2"
        >
          <FormInput v-model="name" />
        </FormGroup>
      </div>
      <div class="col col-6">
        <FormGroup
          small-label
          :label="$t('apiClientKeyForm.expiresOnLabel')"
          :helper-text="$t('apiClientKeyForm.expiresOnHelp')"
          class="margin-bottom-2"
        >
          <FormInput v-model="expiresOn" type="datetime-local" />
        </FormGroup>
      </div>
    </div>
    <div class="flex justify-content-end">
      <Button
        type="secondary"
        class="margin-right-1"
        @click.prevent="$emit('cancel')"
      >
        {{ $t('action.cancel') }}
      </Button>
      <Button :loading="loading" :disabled="loading" @click.prevent="submit">
        {{ $t('apiClientKeyForm.create') }}
      </Button>
    </div>
  </form>
</template>

<script>
export default {
  name: 'ApiClientKeyForm',
  props: {
    loading: {
      type: Boolean,
      required: false,
      default: false,
    },
  },
  emits: ['submit', 'cancel'],
  data() {
    return {
      name: '',
      expiresOn: '',
    }
  },
  methods: {
    submit() {
      this.$emit('submit', {
        name: this.name.trim(),
        // A blank input means the key never expires, which the backend spells as
        // an explicit null rather than an empty string.
        expires_on: this.expiresOn
          ? new Date(this.expiresOn).toISOString()
          : null,
      })
    },
  },
}
</script>
