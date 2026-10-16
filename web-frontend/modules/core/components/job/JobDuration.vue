<template>
  <span
    v-if="jobElapsed"
    class="job-duration"
    :title="$t('jobDuration.title')"
    >{{ jobElapsed }}</span
  >
</template>

<script>
import jobElapsed from '@baserow/modules/core/mixins/jobElapsed'

/**
 * Shows how long a job has been running, ticking while it is unfinished and
 * settling on the total once it is done.
 */
export default {
  name: 'JobDuration',
  mixins: [jobElapsed],
  props: {
    job: {
      type: Object,
      required: false,
      default: null,
    },
  },
}
</script>
