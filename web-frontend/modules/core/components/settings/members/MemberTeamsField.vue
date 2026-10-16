<template>
  <span v-if="isReadOnly" class="member-teams-field__names">{{ names }}</span>
  <a v-else class="member-teams-field__link" @click.prevent="onClick">
    <span class="member-teams-field__names">{{ names }}</span>
    <i class="iconoir-nav-arrow-down"></i>
  </a>
</template>

<script>
export default {
  name: 'MemberTeamsField',
  props: {
    row: {
      type: Object,
      required: true,
    },
    column: {
      type: Object,
      required: true,
    },
  },
  emits: ['edit-teams-context'],
  computed: {
    isReadOnly() {
      return !this.column.additionalProps.canManage
    },
    names() {
      const teams = this.row.teams || []
      return teams.length === 0
        ? this.$t('membersSettings.membersTable.noTeams')
        : teams.map((team) => team.name).join(', ')
    },
  },
  methods: {
    onClick(event) {
      this.$emit('edit-teams-context', {
        row: this.row,
        target: event.currentTarget,
      })
    },
  },
}
</script>

<style lang="scss" scoped>
.member-teams-field__link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
}

.member-teams-field__names {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
