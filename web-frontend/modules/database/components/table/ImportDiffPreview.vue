<template>
  <div class="import-diff">
    <div class="import-diff__summary">
      <span
        v-for="kind in summaryKinds"
        :key="kind"
        class="import-diff__badge"
        :class="`import-diff__badge--${kind}`"
      >
        {{ $t(`importDiffPreview.${kind}`) }}: {{ preview.summary[kind] || 0 }}
      </span>
    </div>

    <p v-if="!hasChanges">{{ $t('importDiffPreview.noChanges') }}</p>

    <Tabs v-else header-no-padding content-no-x-padding>
      <Tab
        v-for="tab in tabs"
        :key="tab.kind"
        :title="`${$t(`importDiffPreview.${tab.kind}`)} (${
          preview.summary[tab.kind] || 0
        })`"
      >
        <p v-if="tab.rows.length === 0">{{ $t('importDiffPreview.empty') }}</p>
        <template v-else>
          <div class="import-diff__table-wrapper">
            <table class="import-diff__table">
              <thead>
                <tr>
                  <th v-if="tab.kind !== 'delete'" class="import-diff__index">
                    {{ $t('importDiffPreview.index') }}
                  </th>
                  <th v-for="field in tab.fields" :key="field.id">
                    <i :class="fieldTypes[field.type].iconClass"></i>
                    {{ field.name }}
                  </th>
                  <th v-if="tab.kind === 'errors'">
                    {{ $t('importDiffPreview.errors') }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in tab.rows"
                  :key="row.key"
                  :class="{ 'import-diff__row--delete': tab.kind === 'delete' }"
                >
                  <td v-if="tab.kind !== 'delete'" class="import-diff__index">
                    {{ row.importIndex + 1 }}
                  </td>
                  <td
                    v-for="field in tab.fields"
                    :key="field.id"
                    :class="{
                      'import-diff__cell--changed': row.changed.includes(
                        field.id
                      ),
                    }"
                  >
                    <template v-if="row.changed.includes(field.id)">
                      <div class="import-diff__old">
                        <SimpleGridField :field="field" :row="row.old" />
                      </div>
                      <div class="import-diff__new">
                        <SimpleGridField :field="field" :row="row.new" />
                      </div>
                    </template>
                    <SimpleGridField v-else :field="field" :row="row.new" />
                  </td>
                  <td v-if="tab.kind === 'errors'">{{ row.message }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div
            v-if="(preview.summary[tab.kind] || 0) > tab.rows.length"
            class="import-diff__notice"
          >
            {{
              $t('importDiffPreview.sampleNotice', { count: tab.rows.length })
            }}
          </div>
        </template>
      </Tab>
    </Tabs>
  </div>
</template>

<script>
import SimpleGridField from '@baserow/modules/database/components/view/grid/SimpleGridField'

export default {
  name: 'ImportDiffPreview',
  components: { SimpleGridField },
  props: {
    /**
     * The response of the import preview endpoint.
     */
    preview: {
      type: Object,
      required: true,
    },
    /**
     * The table fields mapped to a file column, shown for imported rows.
     */
    fields: {
      type: Array,
      required: true,
    },
    /**
     * All the table fields, shown for trashed rows.
     */
    allFields: {
      type: Array,
      required: true,
    },
    /**
     * Returns the imported values of the row at the provided file index, keyed by
     * `field_{id}` in the same format as a row.
     */
    getImportedRow: {
      type: Function,
      required: true,
    },
  },
  computed: {
    fieldTypes() {
      return this.$registry.getAll('field')
    },
    summaryKinds() {
      return ['create', 'update', 'unchanged', 'delete', 'skipped', 'errors']
    },
    hasChanges() {
      const summary = this.preview.summary
      return ['create', 'update', 'delete', 'skipped', 'errors'].some(
        (kind) => (summary[kind] || 0) > 0
      )
    },
    tabs() {
      return [
        {
          kind: 'create',
          fields: this.fields,
          rows: this.preview.create.map((importIndex) =>
            this.importedRow(importIndex)
          ),
        },
        {
          kind: 'update',
          fields: this.fields,
          rows: this.preview.update.map((update) => ({
            ...this.importedRow(update.import_index),
            old: update.row,
            changed: update.changed_field_ids,
          })),
        },
        {
          kind: 'delete',
          fields: this.allFields,
          rows: this.preview.delete.map((row) => ({
            key: `delete-${row.id}`,
            new: row,
            changed: [],
          })),
        },
        {
          kind: 'skipped',
          fields: this.fields,
          rows: this.preview.skipped.map((importIndex) =>
            this.importedRow(importIndex)
          ),
        },
        {
          kind: 'errors',
          fields: this.fields,
          rows: Object.entries(this.preview.errors).map(
            ([importIndex, error]) => ({
              ...this.importedRow(parseInt(importIndex, 10)),
              message: this.errorMessage(error),
            })
          ),
        },
      ].filter((tab) => (this.preview.summary[tab.kind] || 0) > 0)
    },
  },
  methods: {
    importedRow(importIndex) {
      return {
        key: `import-${importIndex}`,
        importIndex,
        new: {
          id: `import-${importIndex}`,
          ...this.getImportedRow(importIndex),
        },
        changed: [],
      }
    },
    errorMessage(error) {
      return Object.values(error)
        .flat()
        .map((item) => (item && item.error ? item.error : String(item)))
        .join(', ')
    },
  },
}
</script>
