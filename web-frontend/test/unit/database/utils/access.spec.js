import {
  ACCESS_INHERIT,
  buildGrantChanges,
  subjectKey,
} from '@baserow/modules/database/utils/access'

const member = {
  subject_type: 'user',
  subject_id: 1,
  is_admin: false,
  level: 'viewer',
}
const team = {
  subject_type: 'team',
  subject_id: 1,
  is_admin: false,
  level: null,
}
const admin = {
  subject_type: 'user',
  subject_id: 2,
  is_admin: true,
  level: null,
}

describe('buildGrantChanges', () => {
  test('keys users and teams separately', () => {
    expect(subjectKey(member)).not.toBe(subjectKey(team))
  })

  test('returns nothing without pending changes', () => {
    expect(buildGrantChanges([member, team], {})).toEqual([])
  })

  test('ignores selections equal to the saved level', () => {
    const pending = {
      [subjectKey(member)]: 'viewer',
      [subjectKey(team)]: ACCESS_INHERIT,
    }

    expect(buildGrantChanges([member, team], pending)).toEqual([])
  })

  test('sets levels and turns inherit into a removal', () => {
    const pending = {
      [subjectKey(member)]: ACCESS_INHERIT,
      [subjectKey(team)]: 'none',
    }

    expect(buildGrantChanges([member, team], pending)).toEqual([
      { subject_type: 'user', subject_id: 1, level: null },
      { subject_type: 'team', subject_id: 1, level: 'none' },
    ])
  })

  test('never changes admins', () => {
    expect(buildGrantChanges([admin], { [subjectKey(admin)]: 'none' })).toEqual(
      []
    )
  })
})
