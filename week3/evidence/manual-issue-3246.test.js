import MockDate from 'mockdate'
import dayjs from '../../src'
import calendar from '../../src/plugin/calendar'

dayjs.extend(calendar)

afterEach(() => MockDate.reset())

it('#3246 callback receives explicit reference', () => {
  MockDate.set('2026-10-05T12:00:00Z')
  const reference = dayjs('2020-01-15T12:00:00')
  let received
  reference.calendar(reference, { sameDay(now) { received = now.valueOf(); return '[Today]' } })
  expect(dayjs(received).format()).toBe(reference.format())
})

it('#3246 control: no reference -> callback gets now', () => {
  MockDate.set('2026-10-05T12:00:00Z')
  let received
  dayjs().calendar(null, { sameDay(now) { received = now.valueOf(); return '[Today]' } })
  expect(received).toBe(Date.now())
})
