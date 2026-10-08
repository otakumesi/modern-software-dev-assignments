import moment from 'moment'
import dayjs from '../../src'

it('#3003 daysInMonth 1981-12', () => {
  const d = dayjs('1981-12-01')
  console.log(process.env.TZ, 'dayjs', d.daysInMonth(), 'endOf', d.endOf('M').format(), 'moment', moment('1981-12-01').daysInMonth())
  expect(d.daysInMonth()).toBe(31)
})
