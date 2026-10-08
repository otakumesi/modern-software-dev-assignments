import moment from 'moment'
import dayjs from '../../src'
import utc from '../../src/plugin/utc'
import weekOfYear from '../../src/plugin/weekOfYear'
import advancedFormat from '../../src/plugin/advancedFormat'
import customParseFormat from '../../src/plugin/customParseFormat'

dayjs.extend(utc)
dayjs.extend(weekOfYear)
dayjs.extend(advancedFormat) // needed to *format* 'ww'
dayjs.extend(customParseFormat)

// Triage repro for https://github.com/iamkun/dayjs/issues/3239
// Run: TZ=<zone> npx jest test/__repro__/issue-3239.test.js --coverage=false

it('#3239 reported behavior: dayjs.utc drops parsed week', () => {
  const actual = dayjs.utc('2024-31', 'YYYY-ww')
  const oracle = moment.utc('2024-31', 'YYYY-ww')
  console.log(process.env.TZ, 'dayjs.utc:', actual.format(), 'moment.utc:', oracle.format())
  expect(oracle.week()).toBe(31)
  expect(actual.week()).toBe(31)
})

it('#3239 control: local parse keeps week (fixed in #2705)', () => {
  const actual = dayjs('2024-31', 'YYYY-ww')
  const oracle = moment('2024-31', 'YYYY-ww')
  console.log(process.env.TZ, 'dayjs:', actual.format(), 'moment:', oracle.format())
  expect(actual.format('YYYY-ww')).toBe('2024-31')
  expect(oracle.week()).toBe(31)
})
