import {
  JOB_TERMINAL_STATES,
  elapsedMs,
  formatElapsedMs,
  formatJobElapsed,
  jobElapsedMs,
  jobIsTerminal,
} from '@baserow/modules/core/utils/job'

const MS_IN_SEC = 1000
const MS_IN_MIN = 60 * MS_IN_SEC
const MS_IN_HOUR = 60 * MS_IN_MIN
const MS_IN_DAY = 24 * MS_IN_HOUR

const START = '2026-09-17T10:00:00Z'
const startMs = Date.parse(START)

describe('jobIsTerminal', () => {
  test.each(JOB_TERMINAL_STATES)('%s is terminal', (state) => {
    expect(jobIsTerminal({ state })).toBe(true)
  })

  test.each(['pending', 'started', 'exporting', undefined])(
    '%s is not terminal',
    (state) => {
      expect(jobIsTerminal({ state })).toBe(false)
    }
  )

  test('a missing job is not terminal', () => {
    expect(jobIsTerminal(null)).toBe(false)
    expect(jobIsTerminal(undefined)).toBe(false)
  })
})

describe('elapsedMs', () => {
  test('measures up to the end when the work has finished', () => {
    expect(elapsedMs(START, '2026-09-17T10:02:30Z')).toBe(
      2 * MS_IN_MIN + 30 * MS_IN_SEC
    )
  })

  test('measures up to now while the work is still going', () => {
    expect(elapsedMs(START, null, startMs + 45 * MS_IN_SEC)).toBe(
      45 * MS_IN_SEC
    )
  })

  test('treats a timestamp without a zone as UTC, like the backend sends it', () => {
    expect(elapsedMs('2026-09-17T10:00:00', '2026-09-17T10:00:10Z')).toBe(
      10 * MS_IN_SEC
    )
  })

  test('clamps to zero when the browser clock lags behind the backend', () => {
    expect(elapsedMs(START, null, startMs - 30 * MS_IN_SEC)).toBe(0)
  })

  test('returns null without a usable start', () => {
    expect(elapsedMs(null, START)).toBeNull()
    expect(elapsedMs('', START)).toBeNull()
    expect(elapsedMs('not a date', START)).toBeNull()
  })

  test('returns null when the end is set but unparseable', () => {
    expect(elapsedMs(START, 'not a date')).toBeNull()
  })
})

describe('jobElapsedMs', () => {
  test('a running job measures up to now, ignoring updated_on', () => {
    const job = {
      state: 'started',
      created_on: START,
      updated_on: '2026-09-17T10:00:05Z',
    }
    expect(jobElapsedMs(job, startMs + 20 * MS_IN_SEC)).toBe(20 * MS_IN_SEC)
  })

  test('a finished job freezes on updated_on', () => {
    const job = {
      state: 'finished',
      created_on: START,
      updated_on: '2026-09-17T10:01:00Z',
    }
    // Later wall-clock time must not move a finished job's duration.
    expect(jobElapsedMs(job, startMs + MS_IN_HOUR)).toBe(MS_IN_MIN)
  })

  test.each(['failed', 'cancelled'])(
    'a %s job also freezes on updated_on',
    (state) => {
      const job = {
        state,
        created_on: START,
        updated_on: '2026-09-17T10:00:30Z',
      }
      expect(jobElapsedMs(job, startMs + MS_IN_HOUR)).toBe(30 * MS_IN_SEC)
    }
  )

  test('returns null for a missing job or a job without timestamps', () => {
    expect(jobElapsedMs(null)).toBeNull()
    expect(jobElapsedMs({ state: 'started' })).toBeNull()
  })
})

describe('formatElapsedMs', () => {
  test.each([
    [0, '0:00:00'],
    [4 * MS_IN_SEC, '0:00:04'],
    [90 * MS_IN_SEC, '0:01:30'],
    [MS_IN_HOUR + 2 * MS_IN_MIN + 3 * MS_IN_SEC, '1:02:03'],
    [25 * MS_IN_HOUR, '1 1:00:00'],
  ])('%i ms formats as %s', (ms, expected) => {
    expect(formatElapsedMs(ms)).toBe(expected)
  })

  test('sub-second durations round down to zero seconds rather than disappearing', () => {
    expect(formatElapsedMs(400)).toBe('0:00:00')
  })

  test('returns an empty string when there is nothing to show', () => {
    expect(formatElapsedMs(null)).toBe('')
    expect(formatElapsedMs(undefined)).toBe('')
  })
})

describe('formatJobElapsed', () => {
  test('formats a running job straight from the job object', () => {
    const job = { state: 'started', created_on: START }
    expect(formatJobElapsed(job, startMs + 65 * MS_IN_SEC)).toBe('0:01:05')
  })

  test('is empty for a job it cannot measure', () => {
    expect(formatJobElapsed(null)).toBe('')
  })
})

describe('day boundary', () => {
  test('a duration of exactly one day switches to the day format', () => {
    expect(formatElapsedMs(MS_IN_DAY)).toBe('1 0:00:00')
  })

  test('just under a day stays in hours', () => {
    expect(formatElapsedMs(MS_IN_DAY - MS_IN_SEC)).toBe('23:59:59')
  })
})
