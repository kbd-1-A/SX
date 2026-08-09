import { describe, expect, it } from 'vitest'
import { parseSqliteUtcTimestamp } from './time'

describe('parseSqliteUtcTimestamp', () => {
  it('treats SQLite CURRENT_TIMESTAMP as UTC', () => {
    const date = parseSqliteUtcTimestamp('2026-08-08 09:08:13')
    expect(date?.toISOString()).toBe('2026-08-08T09:08:13.000Z')
  })

  it('returns null for empty or invalid timestamps', () => {
    expect(parseSqliteUtcTimestamp('')).toBeNull()
    expect(parseSqliteUtcTimestamp('not-a-date')).toBeNull()
  })
})