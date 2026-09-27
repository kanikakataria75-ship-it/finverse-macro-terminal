// Exchanges, sessions and country code tables shared by clocks, map and globe.

export const EXCHANGES = [
  { id: "NYSE", city: "New York", lat: 40.71, lon: -74.01, tz: "America/New_York", open: "09:30", close: "16:00", idx: "^GSPC", clock: true, short: "NY" },
  { id: "TSX", city: "Toronto", lat: 43.65, lon: -79.38, tz: "America/Toronto", open: "09:30", close: "16:00", idx: "^GSPTSE" },
  { id: "B3", city: "São Paulo", lat: -23.55, lon: -46.63, tz: "America/Sao_Paulo", open: "10:00", close: "17:00", idx: "^BVSP" },
  { id: "LSE", city: "London", lat: 51.51, lon: -0.13, tz: "Europe/London", open: "08:00", close: "16:30", idx: "^FTSE", clock: true, short: "LDN" },
  { id: "XETRA", city: "Frankfurt", lat: 50.11, lon: 8.68, tz: "Europe/Berlin", open: "09:00", close: "17:30", idx: "^GDAXI", clock: true, short: "FRA" },
  { id: "SIX", city: "Zürich", lat: 47.37, lon: 8.54, tz: "Europe/Zurich", open: "09:00", close: "17:30", idx: "^SSMI" },
  { id: "TADAWUL", city: "Riyadh", lat: 24.71, lon: 46.68, tz: "Asia/Riyadh", open: "10:00", close: "15:00", days: [0, 1, 2, 3, 4] },
  { id: "DFM", city: "Dubai", lat: 25.2, lon: 55.27, tz: "Asia/Dubai", open: "10:00", close: "15:00" },
  { id: "NSE", city: "Mumbai", lat: 19.07, lon: 72.88, tz: "Asia/Kolkata", open: "09:15", close: "15:30", idx: "^NSEI", clock: true, short: "MUM" },
  { id: "SGX", city: "Singapore", lat: 1.28, lon: 103.85, tz: "Asia/Singapore", open: "09:00", close: "17:00", idx: "^STI" },
  { id: "HKEX", city: "Hong Kong", lat: 22.32, lon: 114.17, tz: "Asia/Hong_Kong", open: "09:30", close: "16:00", idx: "^HSI", clock: true, short: "HK" },
  { id: "SSE", city: "Shanghai", lat: 31.23, lon: 121.47, tz: "Asia/Shanghai", open: "09:30", close: "15:00", idx: "000001.SS" },
  { id: "KRX", city: "Seoul", lat: 37.57, lon: 126.98, tz: "Asia/Seoul", open: "09:00", close: "15:30", idx: "^KS11" },
  { id: "TSE", city: "Tokyo", lat: 35.68, lon: 139.69, tz: "Asia/Tokyo", open: "09:00", close: "15:30", idx: "^N225", clock: true, short: "TKY" },
  { id: "ASX", city: "Sydney", lat: -33.87, lon: 151.21, tz: "Australia/Sydney", open: "10:00", close: "16:00", idx: "^AXJO" },
  { id: "JSE", city: "Johannesburg", lat: -26.2, lon: 28.05, tz: "Africa/Johannesburg", open: "09:00", close: "17:00" },
];

const _fmt = {};
function parts(tz, now) {
  _fmt[tz] ||= new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour12: false, weekday: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const p = Object.fromEntries(_fmt[tz].formatToParts(now).map((x) => [x.type, x.value]));
  const wd = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(p.weekday);
  return { wd, h: +p.hour % 24, m: +p.minute, s: +p.second, text: `${p.hour}:${p.minute}:${p.second}` };
}
const mins = (t) => { const [a, b] = t.split(":").map(Number); return a * 60 + b; };

/** Regular-session status (exchange holidays not modelled). */
export function session(ex, now = new Date()) {
  const p = parts(ex.tz, now);
  const days = ex.days || [1, 2, 3, 4, 5];
  const cur = p.h * 60 + p.m + p.s / 60, o = mins(ex.open), c = mins(ex.close);
  const open = days.includes(p.wd) && cur >= o && cur < c;
  return { open, progress: open ? (cur - o) / (c - o) : 0, time: p.text };
}

// ISO3 -> ISO 3166-1 numeric (world-atlas ids)
export const ISO_NUM = {
  USA: 840, CAN: 124, BRA: 76, MEX: 484, ARG: 32, GBR: 826, DEU: 276, FRA: 250, ITA: 380, ESP: 724, CHE: 756, NLD: 528,
  TUR: 792, ISR: 376, JPN: 392, HKG: 344, CHN: 156, KOR: 410, TWN: 158, AUS: 36, NZL: 554, IDN: 360, SGP: 702, MYS: 458,
  IND: 356, UKR: 804, RUS: 643, PSE: 275, LBN: 422, SYR: 760, IRN: 364, IRQ: 368, YEM: 887, SAU: 682, SDN: 729, SSD: 728,
  ETH: 231, SOM: 706, LBY: 434, EGY: 818, MLI: 466, BFA: 854, NER: 562, NGA: 566, COD: 180, AFG: 4, PAK: 586, MMR: 104,
  PRK: 408, PHL: 608, VEN: 862, HTI: 332, COL: 170, ARM: 51, AZE: 31, SRB: 688, KWT: 414, ARE: 784, KAZ: 398, QAT: 634,
  DZA: 12, NOR: 578, AGO: 24, PRT: 620, POL: 616, UZB: 860, AUT: 40, THA: 764, ZAF: 710, BEL: 56, IRL: 372, FIN: 246,
  GRC: 300, OMN: 512, ERI: 232, DJI: 262, PAN: 591, MAR: 504, CHL: 152, PER: 604, SWE: 752, DNK: 208,
};
export const NUM_ISO = Object.fromEntries(Object.entries(ISO_NUM).map(([k, v]) => [v, k]));
export const EURO_AREA = ["DEU", "FRA", "ITA", "ESP", "NLD", "BEL", "AUT", "PRT", "IRL", "FIN", "GRC"];
export const COUNTRY_FX = { IND: "INR=X", JPN: "JPY=X", CHN: "CNY=X", CHE: "CHF=X", CAN: "CAD=X", BRA: "BRL=X", MEX: "MXN=X", KOR: "KRW=X", TUR: "TRY=X", ZAF: "ZAR=X", GBR: "GBPUSD=X", AUS: "AUDUSD=X" };
export const FX_INVERTED = new Set(["GBPUSD=X", "AUDUSD=X", "EURUSD=X"]); // quoted XXX/USD: up = local stronger

/** Sub-solar point for the day/night terminator. */
export function sunPosition(date = new Date()) {
  const rad = Math.PI / 180;
  const d = (date - Date.UTC(2000, 0, 1, 12)) / 864e5;
  const g = (357.529 + 0.98560028 * d) * rad;
  const q = 280.459 + 0.98564736 * d;
  const L = (q + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * rad;
  const e = (23.439 - 0.00000036 * d) * rad;
  const dec = Math.asin(Math.sin(e) * Math.sin(L));
  const ra = Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L)) / rad;
  const eqtDeg = ((((q - ra) % 360) + 540) % 360) - 180;
  const eqt = eqtDeg * 4; // equation of time, minutes
  const utcMin = date.getUTCHours() * 60 + date.getUTCMinutes() + date.getUTCSeconds() / 60;
  let lon = -((utcMin + eqt - 720) / 4);
  lon = ((((lon + 180) % 360) + 360) % 360) - 180;
  return { lat: dec / rad, lon };
}
