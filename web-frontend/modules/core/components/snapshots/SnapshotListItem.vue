<template>
  <div class="snapshots-modal__snapshot">
    <div class="snapshots-modal__info">
      <div v-if="!jobIsRunning && !jobIsFinished">
        <div class="snapshots-modal__name">
          {{ snapshot.name }}
        </div>
        <div class="snapshots-modal__detail">
          {{ snapshot.created_by ? `${snapshot.created_by.username} - ` : '' }}
          {{ $t('snapshotListItem.created') }} {{ timeAgo }}
          <template v-if="expiresInDays !== null">
            - {{ $t('snapshotListItem.expiresIn', expiresInDays) }}
          </template>
        </div>
      </div>
      <template v-else>
        <ProgressBar
          :value="job.progress_percentage"
          :status="jobHumanReadableState"
        />
        <JobDuration :job="job" />
      </template>
    </div>
    <div class="snapshots-modal__actions">
      <a
        :class="{ 'snapshots-modal__restore--loading': jobIsRunning }"
        @click="restore"
        >{{ $t('snapshotListItem.restore') }}</a
      >
      <a
        v-if="jobIsRunning || cancelLoading"
        class="snapshots-modal__delete"
        @click="cancelJob(job.id)"
      >
        {{ $filters.lowercase($t('snapshotsModal.cancel')) }}
      </a>
      <a v-else class="snapshots-modal__delete" @click="showDelete">{{
        $t('snapshotListItem.delete')
      }}</a>
      <DeleteSnapshotModal
        ref="deleteSnapshotModal"
        :snapshot="snapshot"
        @snapshot-deleted="$emit('snapshot-deleted', $event)"
      ></DeleteSnapshotModal>
    </div>
  </div>
</template>

<script>
import moment from '@baserow/modules/core/moment'
import SnapshotsService from '@baserow/modules/core/services/snapshots'
import DeleteSnapshotModal from '@baserow/modules/core/components/snapshots/DeleteSnapshotModal'
import JobDuration from '@baserow/modules/core/components/job/JobDuration'
import { notifyIf } from '@baserow/modules/core/utils/error'
import job from '@baserow/modules/core/mixins/job'
import timeAgo from '@baserow/modules/core/mixins/timeAgo'
import { RestoreSnapshotJobType } from '@baserow/modules/core/jobTypes'

export default {
  components: {
    DeleteSnapshotModal,
    JobDuration,
  },
  mixins: [job, timeAgo],
  props: {
    snapshot: {
      type: Object,
      required: true,
    },
  },
  emits: ['snapshot-deleted'],
  computed: {
    /**
     * Whole days left before `SnapshotHandler.delete_expired` picks this snapshot
     * up. The backend expires on `created_at` plus
     * BASEROW_SNAPSHOT_EXPIRATION_TIME_DAYS, mirrored into the runtime config.
     * A non-positive configured value means expiry is switched off.
     */
    expiresInDays() {
      const days = parseInt(
        this.$config.public.baserowSnapshotExpirationTimeDays
      )
      if (!Number.isInteger(days) || days <= 0 || !this.snapshot.created_at) {
        return null
      }
      const expiresAt = moment.utc(this.snapshot.created_at).add(days, 'days')
      if (!expiresAt.isValid()) {
        return null
      }
      return Math.max(0, expiresAt.diff(moment.utc(), 'days'))
    },
  },
  mounted() {
    if (!this.job) {
      this.restoreRunningState()
    }
  },
  methods: {
    restoreRunningState() {
      const runningJob = this.$store.getters['job/getUnfinishedJobs'].find(
        (job) => {
          return (
            job.type === RestoreSnapshotJobType.getType() &&
            job.snapshot.id === this.snapshot.id
          )
        }
      )
      if (runningJob) {
        this.job = runningJob
      }
    },
    showError(error, message) {
      if (error.message && !message) {
        message = error.message
      }
      if (message) {
        this.$store.dispatch('toast/error', error, message)
      } else {
        notifyIf(error)
      }
    },
    async restore() {
      try {
        const { data: job } = await SnapshotsService(this.$client).restore(
          this.snapshot.id
        )
        await this.createAndMonitorJob(job)
      } catch (error) {
        notifyIf(error)
      }
    },
    showDelete() {
      this.$refs.deleteSnapshotModal.show()
    },
    onJobFailed() {
      this.showError(
        this.$t('clientHandler.notCompletedTitle'),
        this.$t('clientHandler.notCompletedDescription')
      )
    },
    getCustomHumanReadableJobState(jobState) {
      if (jobState.startsWith('importing')) {
        return this.$t('snapshotsModal.importingState')
      }
      return ''
    },
  },
}
</script>
