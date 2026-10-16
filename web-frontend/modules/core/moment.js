// Moment should always be imported from here. This will enforce that the timezone
// is always included. There were some problems when Baserow is installed as a
// dependency and then moment-timezone does not work. Still will resolve that issue.
import moment from 'moment-timezone'
import 'moment/dist/locale/pt-br'

export default moment
