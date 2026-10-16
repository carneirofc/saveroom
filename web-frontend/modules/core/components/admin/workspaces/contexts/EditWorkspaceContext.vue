<template>
  <Context ref="context" overflow-scroll max-height-if-outside-viewport>
    <template v-if="Object.keys(workspace).length > 0">
      <div class="context__menu-title">
        {{ workspace.name }} ({{ workspace.id }})
      </div>
      <ul class="context__menu">
        <li class="context__menu-item">
          <a class="context__menu-item-link" @click.prevent="showAccessModal">
            <i class="context__menu-item-icon iconoir-lock"></i>
            {{ $t('editWorkspaceContext.manageAccess') }}
          </a>
        </li>
        <li class="context__menu-item context__menu-item--with-separator">
          <a
            class="context__menu-item-link context__menu-item-link--delete"
            @click.prevent="showDeleteModal"
          >
            <i class="context__menu-item-icon iconoir-bin"></i>
            {{ $t('editWorkspaceContext.delete') }}
          </a>
        </li>
      </ul>
      <DeleteWorkspaceModal
        ref="deleteWorkspaceModal"
        :workspace="workspace"
        @workspace-deleted="$emit('workspace-deleted', $event)"
      ></DeleteWorkspaceModal>
      <DatabaseAccessModal
        ref="accessModal"
        :workspace="workspace"
        scope-type="workspace"
        :scope-id="workspace.id"
        :scope-name="workspace.name"
      ></DatabaseAccessModal>
    </template>
  </Context>
</template>

<script>
import context from '@baserow/modules/core/mixins/context'
import DeleteWorkspaceModal from '@baserow/modules/core/components/admin/workspaces/modals/DeleteWorkspaceModal'
import DatabaseAccessModal from '@baserow/modules/database/components/access/DatabaseAccessModal'

export default {
  name: 'EditWorkspaceContext',
  components: { DeleteWorkspaceModal, DatabaseAccessModal },
  mixins: [context],
  props: {
    workspace: {
      required: true,
      type: Object,
    },
  },
  emits: ['workspace-deleted'],
  methods: {
    showDeleteModal() {
      this.hide()
      this.$refs.deleteWorkspaceModal.show()
    },
    showAccessModal() {
      this.hide()
      this.$refs.accessModal.show()
    },
  },
}
</script>
