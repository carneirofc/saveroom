import {
  formatJobElapsed,
  jobIsTerminal,
} from '@baserow/modules/core/utils/job'

/**
 * Keeps a formatted "time elapsed" for `this.job` up to date.
 *
 * The component must expose a `job` prop or data property. While the job is
 * unfinished the value advances on its own clock rather than on job updates:
 * the job poller backs off up to `baserowFrontendJobsPollingTimeoutMs` between
 * requests, so a counter driven by those updates would visibly stutter and then
 * jump. The interval is stopped as soon as the job reaches a terminal state, so
 * a finished job costs nothing.
 */
export default {
  data() {
    return {
      jobElapsedNow: Date.now(),
      jobElapsedIntervalId: null,
    }
  },
  computed: {
    jobElapsed() {
      return formatJobElapsed(this.job, this.jobElapsedNow)
    },
    jobElapsedIsRunning() {
      return !!this.job && !jobIsTerminal(this.job)
    },
  },
  watch: {
    jobElapsedIsRunning: {
      immediate: true,
      handler(value) {
        if (value) {
          this.startJobElapsedTicker()
        } else {
          this.stopJobElapsedTicker()
        }
      },
    },
  },
  beforeUnmount() {
    this.stopJobElapsedTicker()
  },
  methods: {
    startJobElapsedTicker() {
      if (this.jobElapsedIntervalId !== null) {
        return
      }
      this.jobElapsedNow = Date.now()
      this.jobElapsedIntervalId = setInterval(() => {
        this.jobElapsedNow = Date.now()
      }, 1000)
    },
    stopJobElapsedTicker() {
      if (this.jobElapsedIntervalId !== null) {
        clearInterval(this.jobElapsedIntervalId)
        this.jobElapsedIntervalId = null
      }
      // A job that just finished must settle on its final duration, not on the
      // last value the ticker happened to write.
      this.jobElapsedNow = Date.now()
    },
  },
}
