<template>
  <div class="backups__item">
    <div class="backups__row">
      <div class="backups__info">
        <div class="backups__title">
          {{ title }}
          <slot name="title-extra"></slot>
        </div>
        <div v-if="detail || $slots.detail" class="backups__detail">
          <slot name="detail">{{ detail }}</slot>
        </div>
        <div v-if="$slots.badges" class="backups__badges">
          <slot name="badges"></slot>
        </div>
        <slot name="error"></slot>
      </div>
      <div v-if="$slots.actions" class="backups__actions">
        <slot name="actions"></slot>
      </div>
    </div>
    <slot></slot>
  </div>
</template>

<script>
/**
 * One row of a backup or datalake export list: a title, an optional detail line and
 * badges, and the actions on the right. The `error` slot holds the visible error
 * text, the default slot content that belongs under the row (e.g. a runs table).
 */
export default {
  name: 'BackupListItem',
  props: {
    title: {
      type: String,
      required: true,
    },
    detail: {
      type: String,
      default: '',
    },
  },
}
</script>
