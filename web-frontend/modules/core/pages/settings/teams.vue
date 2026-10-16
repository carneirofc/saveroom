<template>
  <TeamsSettings :workspace="workspace" />
</template>

<script>
import TeamsSettings from '@baserow/modules/core/components/settings/teams/TeamsSettings'

export default {
  name: 'Teams',
  components: { TeamsSettings },
  props: {
    workspace: {
      type: Object,
      required: true,
    },
  },
}
</script>
