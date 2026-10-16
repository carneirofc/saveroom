import moment from '@baserow/modules/core/moment'
import {
  Timedelta,
  formatValueWithDurationFormat,
} from '@baserow/modules/core/utils/duration'

/**
 * The states a job can no longer leave. Anything else means the job is still
 * being worked on by a worker.
 */
export const JOB_TERMINAL_STATES = ['finished', 'failed', 'cancelled']

export const jobIsTerminal = (job) => JOB_TERMINAL_STATES.includes(job?.state)

const SECS_IN_DAY = 86400

/**
 * How long a job has been running, in milliseconds.
 *
 * The backend does not send an explicit duration, but `JobSerializer` exposes
 * `created_on` and `updated_on`. A job is touched on every progress update, so
 * once it reaches a terminal state `updated_on` is the moment it stopped. While
 * it is still running there is no end yet, so the caller passes the current
 * time in, which also lets a component re-render the counter without this
 * function depending on the clock.
 *
 * Returns `null` when the job has no usable timestamps.
 */
export const jobElapsedMs = (job, now = Date.now()) => {
  if (!job) {
    return null
  }
  return elapsedMs(
    job.created_on,
    jobIsTerminal(job) ? job.updated_on : null,
    now
  )
}

/**
 * Milliseconds between two backend timestamps. A missing `finishedOn` means the
 * work is still going, so `now` stands in for the end.
 *
 * Returns `null` when either timestamp is missing or unparseable.
 */
export const elapsedMs = (startedOn, finishedOn, now = Date.now()) => {
  if (!startedOn) {
    return null
  }
  const start = moment.utc(startedOn)
  if (!start.isValid()) {
    return null
  }
  let end
  if (finishedOn) {
    end = moment.utc(finishedOn)
    if (!end.isValid()) {
      return null
    }
  } else {
    end = moment.utc(now)
  }
  // The browser clock is not the backend clock. When it lags behind, the end
  // lands before the start and the duration would be negative, which means
  // nothing to a user, so it is clamped to zero instead.
  return Math.max(0, end.valueOf() - start.valueOf())
}

/**
 * Formats a duration in milliseconds for display, reusing the same formatter
 * the duration field type uses so durations read the same everywhere. Days are
 * only shown once there is at least one, to keep the common case short.
 */
export const formatElapsedMs = (ms) => {
  if (ms === null || ms === undefined) {
    return ''
  }
  const format = ms >= SECS_IN_DAY * 1000 ? 'd h:mm:ss' : 'h:mm:ss'
  return formatValueWithDurationFormat(new Timedelta(ms), format)
}

/**
 * Convenience wrapper for the common case of formatting a job straight away.
 */
export const formatJobElapsed = (job, now = Date.now()) =>
  formatElapsedMs(jobElapsedMs(job, now))
