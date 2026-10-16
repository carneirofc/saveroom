<template>
  <span v-if="member.permissions === 'ADMIN'" class="member-access-field__full">
    {{ $t('memberAccessField.fullAccess') }}
  </span>
  <Dropdown
    v-else
    :value="level"
    :disabled="saving"
    class="member-access-field__dropdown"
    @input="setLevel($event)"
  >
    <DropdownItem
      :name="$t('databaseAccessModal.inherit')"
      :value="INHERIT"
    ></DropdownItem>
    <DropdownItem
      v-for="option in LEVELS"
      :key="option"
      :name="$t(`databaseAccessModal.levels.${option}`)"
      :value="option"
    ></DropdownItem>
  </Dropdown>
</template>

<script>
import { notifyIf } from '@baserow/modules/core/utils/error'
import AccessService from '@baserow/modules/database/services/access'
import {
  ACCESS_INHERIT,
  ACCESS_LEVELS,
} from '@baserow/modules/database/utils/access'

export default {
  name: 'MemberAccessField',
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
  emits: ['row-update'],
  data() {
    return {
      INHERIT: ACCESS_INHERIT,
      LEVELS: ACCESS_LEVELS,
      saving: false,
    }
  },
  computed: {
    member() {
      return this.row
    },
    level() {
      return this.member.access_level === null ||
        this.member.access_level === undefined
        ? ACCESS_INHERIT
        : this.member.access_level
    },
  },
  methods: {
    async setLevel(value) {
      const level = value === ACCESS_INHERIT ? null : value
      if (level === (this.member.access_level ?? null)) {
        return
      }

      this.saving = true
      try {
        await AccessService(this.$client).set(
          'workspace',
          this.column.additionalProps.workspaceId,
          [
            {
              subject_type: 'user',
              subject_id: this.member.user_id,
              level,
            },
          ]
        )
        this.$emit('row-update', { ...this.member, access_level: level })
      } catch (error) {
        notifyIf(error)
      } finally {
        this.saving = false
      }
    },
  },
}
</script>

<style lang="scss" scoped>
.member-access-field__dropdown {
  min-width: 140px;
}
</style>
