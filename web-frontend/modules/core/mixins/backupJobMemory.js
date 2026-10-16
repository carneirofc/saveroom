/**
 * The tabs of the backups modal and of the staff admin panel are unmounted when the
 * modal closes or another tab is selected, which would drop the job they started
 * while it is still running. The parent provides a reactive `backupJobs` object that
 * outlives them; this mixin records the job of a tab in it and re-attaches the
 * remounted tab to the same job from the `job` store, so the progress, the busy state
 * and the finished or failed callbacks keep working.
 *
 * Without a provided `backupJobs` the memory is simply off.
 */
export default {
  inject: {
    backupJobs: { default: null },
  },
  methods: {
    jobMemoryKey(tab) {
      return `${tab}:${this.workspace.id}`
    },
    rememberJob(tab, extra = {}) {
      if (this.backupJobs && this.job) {
        this.backupJobs[this.jobMemoryKey(tab)] = { id: this.job.id, ...extra }
      }
    },
    forgetJob(tab) {
      if (this.backupJobs) {
        delete this.backupJobs[this.jobMemoryKey(tab)]
      }
    },
    /**
     * Re-attaches `this.job` to the remembered job and returns what was remembered,
     * or null. A job that ended while the tab was unmounted still triggers its
     * finished or failed callback once, because the `job.state` watcher fires when
     * the job is assigned.
     */
    resumeJob(tab) {
      const remembered = this.backupJobs?.[this.jobMemoryKey(tab)]
      if (!remembered) {
        return null
      }
      const job = this.$store.getters['job/get'](remembered.id)
      if (!job) {
        this.forgetJob(tab)
        return null
      }
      this.job = job
      return remembered
    },
  },
}
