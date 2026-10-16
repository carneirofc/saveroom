<template>
  <li class="tree__item tree__item--loading">
    <div class="tree__action tree__action--disabled">
      <a class="tree__link" :title="jobTitle">
        <i class="tree__icon" :class="jobIconClass"></i>
        <span class="tree__link-text">{{ jobSidebarText }}</span>
        <div class="tree__progress-percentage">
          {{ job.progress_percentage }} %
        </div>
      </a>
    </div>
  </li>
</template>

<script>
import jobElapsed from '@baserow/modules/core/mixins/jobElapsed'

export default {
  name: 'SidebarApplicationPendingJob',
  mixins: [jobElapsed],
  props: {
    job: {
      type: Object,
      required: true,
    },
  },
  computed: {
    jobSidebarText() {
      return this.$registry.get('job', this.job.type).getSidebarText(this.job)
    },
    jobIconClass() {
      return this.$registry.get('job', this.job.type).getIconClass(this.job)
    },
    // The sidebar row is too narrow for a second number next to the
    // percentage, so the elapsed time rides along as the row's tooltip.
    jobTitle() {
      return this.jobElapsed
        ? `${this.jobSidebarText} - ${this.jobElapsed}`
        : this.jobSidebarText
    },
  },
}
</script>
