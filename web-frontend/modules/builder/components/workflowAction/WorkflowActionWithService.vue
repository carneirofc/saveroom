<template>
  <component
    :is="serviceType.formComponent"
    :application="builder"
    :service="defaultValues.service"
    :service-type="serviceType"
    :loading="workflowActionLoading"
    :default-values="defaultValues.service"
    @values-changed="bufferServiceChange($event)"
  >
  </component>
</template>

<script>
import form from '@baserow/modules/core/mixins/form'

export default {
  name: 'WorkflowActionWithService',
  mixins: [form],
  inject: ['builder'],
  props: {
    workflowAction: {
      type: Object,
      required: false,
      default: null,
    },
  },
  data() {
    return {
      allowedValues: ['service'],
      values: {
        service: {},
      },
      // The service changes the user has made but not yet had saved,
      // accumulated from the wrapped form's `values-changed` events. The form
      // only emits editable fields, so this never carries the read-only,
      // backend-computed ones (`schema`, sample data, …); those always come
      // fresh from `workflowAction.service` when we rebuild `values.service`.
      pendingServiceChanges: {},
    }
  },
  computed: {
    workflowActionLoading() {
      return this.$store.getters['builderWorkflowAction/getLoading'](
        this.workflowAction
      )
    },
    workflowActionType() {
      return this.$registry.get('workflowAction', this.workflowAction.type)
    },
    serviceType() {
      return this.workflowActionType.serviceType
    },
  },
  methods: {
    /**
     * Records an editable service change and rebuilds `values.service` from the
     * latest server service plus the accumulated changes. Buffering the changes
     * keeps a follow-up edit (or a freshly picked integration) that lands before
     * the debounced save completes, while the read-only fields are always taken
     * fresh from `workflowAction.service` instead of a stale buffered copy.
     */
    bufferServiceChange(changes) {
      this.pendingServiceChanges = {
        ...this.pendingServiceChanges,
        ...changes,
      }
      this.values.service = {
        ...this.workflowAction?.service,
        ...this.pendingServiceChanges,
      }
    },
  },
}
</script>
