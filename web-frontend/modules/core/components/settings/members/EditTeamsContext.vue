<template>
  <Context ref="context" overflow-scroll max-height-if-outside-viewport>
    <div class="context__menu-title">
      {{ $t('membersSettings.membersTable.columns.teams') }}
    </div>
    <ul v-if="teams.length > 0" class="context__menu">
      <li v-for="team in teams" :key="team.id" class="context__menu-item">
        <a
          class="context__menu-item-link"
          @click.prevent="toggle(team)"
          @mousedown.prevent
        >
          <Checkbox :checked="isMember(team)" :disabled="loading"></Checkbox>
          {{ team.name }}
        </a>
      </li>
    </ul>
    <div v-else class="context__description">
      {{ $t('membersSettings.membersTable.noTeamsYet') }}
    </div>
  </Context>
</template>

<script>
import context from '@baserow/modules/core/mixins/context'

export default {
  name: 'EditTeamsContext',
  mixins: [context],
  props: {
    member: {
      type: Object,
      required: true,
    },
    teams: {
      type: Array,
      required: true,
    },
    loading: {
      type: Boolean,
      required: false,
      default: false,
    },
  },
  emits: ['toggle-team'],
  methods: {
    isMember(team) {
      return (this.member.teams || []).some((t) => t.id === team.id)
    },
    toggle(team) {
      if (this.loading) {
        return
      }
      this.$emit('toggle-team', {
        member: this.member,
        team,
        member_of: this.isMember(team),
      })
    },
  },
}
</script>
