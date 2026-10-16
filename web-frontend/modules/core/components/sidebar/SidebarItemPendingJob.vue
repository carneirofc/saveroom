<template>
  <li class="tree__sub">
    <a class="tree__sub-link tree__sub-link--disabled" :title="jobTitle">
      {{ jobSidebarText }}
      <div class="tree__progress-percentage">
        {{ job.progress_percentage }} %
      </div>
    </a>
    <div class="tree__sub-link--loading"></div>
  </li>
</template>

<script>
import jobElapsed from '@baserow/modules/core/mixins/jobElapsed'

export default {
  name: 'SidebarItemPendingJob',
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
