<template>
  <a class="create-widget-card" @click="widgetVariationSelected">
    <div class="create-widget-card__img-container">
      <img :src="variation.createWidgetImage" />
    </div>
    <div class="create-widget-card__name">
      <span>{{ variation.name }}</span>
    </div>
  </a>
</template>

<script>
export default {
  name: 'CreateWidgetCard',
  props: {
    dashboard: {
      type: Object,
      required: true,
    },
    widgetType: {
      type: Object,
      required: true,
    },
    variation: {
      type: Object,
      required: true,
    },
  },
  emits: ['widget-variation-selected'],
  methods: {
    widgetVariationSelected() {
      this.$emit('widget-variation-selected', this.variation)
    },
  },
}
</script>
