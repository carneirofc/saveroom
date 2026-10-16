<template>
  <Modal ref="modal" :wide="true">
    <h2 class="box__title">
      {{
        scopeType === 'workspace'
          ? $t('databaseAccessModal.workspaceTitle', { name: scopeName })
          : $t('databaseAccessModal.title', { name: scopeName })
      }}
    </h2>
    <p class="database-access__description">
      {{ $t('databaseAccessModal.description') }}
    </p>
    <Error :error="error"></Error>
    <div v-if="loading" class="loading"></div>
    <table v-else class="database-access__table">
      <thead>
        <tr>
          <th>{{ $t('databaseAccessModal.subject') }}</th>
          <th>{{ $t('databaseAccessModal.level') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="subject in subjects"
          :key="`${subject.subject_type}-${subject.subject_id}`"
        >
          <td>
            <div class="database-access__name">
              <i
                :class="
                  subject.subject_type === 'team'
                    ? 'iconoir-community'
                    : 'iconoir-user'
                "
              ></i>
              {{ subject.name }}
              <span
                v-if="subject.subject_type === 'team'"
                class="database-access__badge"
              >
                {{ $t('databaseAccessModal.team') }}
              </span>
              <span v-if="subject.is_admin" class="database-access__badge">
                {{ $t('databaseAccessModal.admin') }}
              </span>
            </div>
            <div class="database-access__hint">
              {{ inheritedHint(subject) }}
            </div>
          </td>
          <td class="database-access__level">
            <Dropdown
              :value="levelOf(subject)"
              :disabled="subject.is_admin || saving"
              @input="setLevel(subject, $event)"
            >
              <DropdownItem
                :name="$t('databaseAccessModal.inherit')"
                :value="INHERIT"
              ></DropdownItem>
              <DropdownItem
                v-for="level in LEVELS"
                :key="level"
                :name="$t(`databaseAccessModal.levels.${level}`)"
                :description="
                  $t(`databaseAccessModal.levelDescriptions.${level}`)
                "
                :value="level"
              ></DropdownItem>
            </Dropdown>
          </td>
        </tr>
      </tbody>
    </table>
    <div class="actions">
      <div class="align-right">
        <Button
          type="primary"
          size="large"
          :loading="saving"
          :disabled="saving || loading || !hasChanges"
          @click="save"
        >
          {{ $t('databaseAccessModal.save') }}
        </Button>
      </div>
    </div>
  </Modal>
</template>

<script>
import modal from '@baserow/modules/core/mixins/modal'
import error from '@baserow/modules/core/mixins/error'
import AccessService from '@baserow/modules/database/services/access'
import {
  ACCESS_INHERIT,
  ACCESS_LEVELS,
  buildGrantChanges,
  subjectKey,
} from '@baserow/modules/database/utils/access'

export default {
  name: 'DatabaseAccessModal',
  mixins: [modal, error],
  props: {
    workspace: {
      type: Object,
      required: true,
    },
    scopeType: {
      type: String,
      required: true,
      validator: (value) => ['workspace', 'database', 'table'].includes(value),
    },
    scopeId: {
      type: Number,
      required: true,
    },
    scopeName: {
      type: String,
      required: true,
    },
  },
  data() {
    return {
      INHERIT: ACCESS_INHERIT,
      LEVELS: ACCESS_LEVELS,
      loading: false,
      saving: false,
      subjects: [],
      pending: {},
    }
  },
  computed: {
    hasChanges() {
      return buildGrantChanges(this.subjects, this.pending).length > 0
    },
  },
  methods: {
    show(...args) {
      this.getRootModal().show(...args)
      this.fetch()
    },
    async fetch() {
      this.loading = true
      this.pending = {}
      this.hideError()
      try {
        const { data } = await AccessService(this.$client).get(
          this.scopeType,
          this.scopeId
        )
        this.subjects = data.subjects
      } catch (error) {
        this.handleError(error)
      } finally {
        this.loading = false
      }
    },
    levelOf(subject) {
      const key = subjectKey(subject)
      if (Object.prototype.hasOwnProperty.call(this.pending, key)) {
        return this.pending[key]
      }
      return subject.level === null ? ACCESS_INHERIT : subject.level
    },
    setLevel(subject, level) {
      this.pending = { ...this.pending, [subjectKey(subject)]: level }
    },
    inheritedHint(subject) {
      if (subject.is_admin) {
        return ''
      }
      if (subject.inherited_level) {
        return this.$t('databaseAccessModal.inheritedFrom', {
          level: this.$t(
            `databaseAccessModal.levels.${subject.inherited_level}`
          ),
          scope: this.$t(
            `databaseAccessModal.scopes.${subject.inherited_from}`
          ),
        })
      }
      return this.$t('databaseAccessModal.inheritsFullAccess')
    },
    async save() {
      const grants = buildGrantChanges(this.subjects, this.pending)
      if (grants.length === 0) {
        return
      }
      this.saving = true
      this.hideError()
      try {
        const { data } = await AccessService(this.$client).set(
          this.scopeType,
          this.scopeId,
          grants
        )
        this.subjects = data.subjects
        this.pending = {}
        this.$store.dispatch('toast/success', {
          title: this.$t('databaseAccessModal.saved'),
        })
        this.hide()
      } catch (error) {
        this.handleError(error)
      } finally {
        this.saving = false
      }
    },
  },
}
</script>

<style lang="scss" scoped>
.database-access__description,
.database-access__hint {
  color: var(--color-neutral-600, #6b6b6b);
}

.database-access__hint {
  font-size: 12px;
  margin-top: 2px;
}

.database-access__table {
  width: 100%;
  border-collapse: collapse;
  margin: 16px 0;

  th {
    text-align: left;
    font-weight: 600;
    padding: 8px 0;
  }

  td {
    padding: 8px 0;
    border-top: 1px solid var(--color-neutral-200, #ededed);
    vertical-align: top;
  }
}

.database-access__name {
  display: flex;
  align-items: center;
  gap: 6px;
}

.database-access__badge {
  font-size: 11px;
  padding: 0 6px;
  border-radius: 4px;
  background: var(--color-neutral-100, #f5f5f5);
}

.database-access__level {
  width: 220px;
}
</style>
