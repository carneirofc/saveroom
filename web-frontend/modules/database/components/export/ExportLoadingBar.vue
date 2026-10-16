<template>
  <div>
    <div class="modal-progress__actions">
      <template v-if="job !== null">
        <ProgressBar :value="job.progress_percentage" :status="job.state" />
        <JobDuration :job="job" class="modal-progress__duration" />
      </template>

      <Button
        v-if="job === null || job.state !== 'finished'"
        type="primary"
        size="large"
        :loading="loading"
        :disabled="disabled || loading"
        full-width
        class="modal-progress__export-button"
      >
        {{ $t('exportTableLoadingBar.export') }}
      </Button>
      <DownloadLink
        v-else
        class="button button--large button--full-width modal-progress__export-button"
        :url="job.download_url"
        :filename="filename"
        :loading-class="'button--loading'"
      >
        <template #default="{ loading: downloadLoading }">
          <template v-if="!downloadLoading">{{
            $t('exportTableLoadingBar.download')
          }}</template>
        </template>
      </DownloadLink>
    </div>
    <p
      v-if="job !== null && job.state === 'finished'"
      class="modal-progress__hint"
    >
      {{ $t('exportTableLoadingBar.expires', { minutes: expireMinutes }) }}
    </p>
  </div>
</template>

<script>
import JobDuration from '@baserow/modules/core/components/job/JobDuration'

export default {
  name: 'ExportLoadingBar',
  components: { JobDuration },
  props: {
    filename: {
      type: String,
      required: false,
      default: 'export',
    },
    exportType: {
      type: String,
      required: false,
      default: 'export',
    },
    job: {
      type: Object,
      required: false,
      default: null,
    },
    loading: {
      type: Boolean,
      required: true,
    },
    disabled: {
      type: Boolean,
      required: true,
    },
  },
  computed: {
    expireMinutes() {
      return parseInt(this.$config.public.exportFileExpireMinutes)
    },
  },
}
</script>
