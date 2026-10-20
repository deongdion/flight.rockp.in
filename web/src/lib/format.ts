import type { Itinerary, Offer } from './types.ts';

const WEEKDAY = '일월화수목금토';

/** 출발 도시 코드 → 이름 */
export const CITY_NAMES: Record<string, string> = {
	SEL: '서울',
	PUS: '부산',
	CJU: '제주',
	CJJ: '청주',
	TAE: '대구',
	KWJ: '광주',
	USN: '울산',
	WJU: '원주',
	HIN: '사천',
	MWX: '무안',
	RSU: '여수',
	KUV: '군산',
	KPO: '포항',
	YNY: '양양'
};

export const cityName = (code: string) => CITY_NAMES[code] ?? code;

/** 출발 공항 코드 → 이름 (출발지는 늘 국내 공항) */
const AIRPORT_NAMES: Record<string, string> = {
	ICN: '인천',
	GMP: '김포',
	PUS: '부산',
	CJU: '제주',
	CJJ: '청주',
	TAE: '대구',
	KWJ: '광주',
	USN: '울산',
	WJU: '원주',
	HIN: '사천',
	MWX: '무안',
	RSU: '여수',
	KUV: '군산',
	KPO: '포항',
	YNY: '양양'
};

/** 공항·도시 코드 → 이름, 모르면 코드 그대로 */
export const placeName = (code: string) => AIRPORT_NAMES[code] ?? CITY_NAMES[code] ?? code;

/** 노선 화살표 — 왕복 "⇄", 편도 "→" (가는편·오는편 한 구간은 늘 "→") */
export const tripArrow = (returnDate: string | null | undefined) => (returnDate ? '⇄' : '→');

/** 1245000 → "1,245,000원" */
export const won = (n: number) => `${n.toLocaleString('ko-KR')}원`;

/** 98000 → "9.8만원" */
export const shortWon = (n: number) =>
	n >= 10_000 ? `${(Math.floor(n / 1000) / 10).toLocaleString('ko-KR')}만원` : won(n);

/** "0905" → "09:05" */
export const hhmm = (t: string) => (t.length >= 4 ? `${t.slice(0, 2)}:${t.slice(2, 4)}` : t);

/** 8700 → "2시간 25분" */
export function duration(sec: number): string {
	const h = Math.floor(sec / 3600);
	const m = Math.round((sec % 3600) / 60);
	return h ? (m ? `${h}시간 ${m}분` : `${h}시간`) : `${m}분`;
}

/** "2026-11-01" 또는 "20261101"(구간 날짜) → Date (로컬 자정) */
function toDate(s: string): Date {
	const d = s.replaceAll('-', '');
	return new Date(+d.slice(0, 4), +d.slice(4, 6) - 1, +d.slice(6, 8));
}

/** "2026-11-23" → "11.23(월)" */
export function day(s: string): string {
	const d = toDate(s);
	return `${d.getMonth() + 1}.${d.getDate()}(${WEEKDAY[d.getDay()]})`;
}

/** "2026-10-30" → "10.30.금" (검색 상자 날짜) */
export function dotDay(s: string): string {
	const d = toDate(s);
	return `${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}.${WEEKDAY[d.getDay()]}`;
}

/** "2026-10-30" → "2026.10.30.(금)" */
export function fullDay(s: string): string {
	const d = toDate(s);
	const mm = String(d.getMonth() + 1).padStart(2, '0');
	const dd = String(d.getDate()).padStart(2, '0');
	return `${d.getFullYear()}.${mm}.${dd}.(${WEEKDAY[d.getDay()]})`;
}

export const nights = (a: string, b: string) =>
	Math.round((toDate(b).getTime() - toDate(a).getTime()) / 86_400_000);

/** 도착일이 출발일보다 며칠 뒤인지 (+1 표기용) */
export function dayOffset(itinerary: Itinerary): number {
	const a = itinerary.segments[0]?.dep_date;
	const b = itinerary.segments.at(-1)?.arr_date;
	return a && b ? nights(a, b) : 0;
}

export const stops = (itinerary: Itinerary) => Math.max(0, itinerary.segments.length - 1);

/** 도시 사진 — 원본은 2~5MB 라 이미지 프록시로 640×480(약 60KB)으로 줄여 받는다 */
export const cityPhoto = (url: string) =>
	`https://search.pstatic.net/common/?src=${encodeURIComponent(url)}&type=f640_480`;

/** 항공사 코드 → 이름 (가격 데이터에는 코드만 있다). 모르면 코드 그대로 */
const AIRLINE_NAMES: Record<string, string> = {
	KE: '대한항공', OZ: '아시아나항공', '7C': '제주항공', LJ: '진에어', TW: '티웨이항공', BX: '에어부산',
	ZE: '이스타항공', RS: '에어서울', YP: '에어프레미아', RF: '에어로케이', WE: '파라타항공',
	JL: '일본항공', NH: '전일본공수', MM: '피치항공', GK: '젯스타재팬', BC: '스카이마크',
	MU: '중국동방항공', CA: '중국국제항공', CZ: '중국남방항공', HO: '길상항공', '9C': '춘추항공',
	SC: '산둥항공', FM: '상하이항공', ZH: '선전항공', '3U': '쓰촨항공', MF: '샤먼항공', HU: '하이난항공',
	CX: '캐세이퍼시픽', UO: '홍콩익스프레스', HX: '홍콩항공', NX: '마카오항공',
	CI: '중화항공', BR: '에바항공', IT: '타이거에어 타이완', JX: '스타럭스항공',
	VJ: '비엣젯항공', VN: '베트남항공', QH: '뱀부항공', TG: '타이항공', XJ: '타이에어아시아엑스',
	SQ: '싱가포르항공', TR: '스쿠트', PR: '필리핀항공', '5J': '세부퍼시픽', Z2: '필리핀에어아시아',
	AK: '에어아시아', D7: '에어아시아엑스', MH: '말레이시아항공', GA: '가루다인도네시아',
	OM: '몽골항공', KC: '에어아스타나', HY: '우즈베키스탄항공', UA: '유나이티드항공', DL: '델타항공',
	AA: '아메리칸항공', AF: '에어프랑스', KL: 'KLM', LH: '루프트한자', TK: '터키항공', EK: '에미레이트항공',
	ET: '에티오피아항공', QR: '카타르항공', EY: '에티하드항공', SU: '아에로플로트', AY: '핀에어'
};

export const airlineName = (code: string) => AIRLINE_NAMES[code] ?? code;

export const airlineLogo = (code: string) =>
	`https://techminds.pstatic.net/flight/vertical-static/flight/airlines/${code}.png?v=3`;

/** 판매처 코드 → 사이트 — core/affiliates.py PARTNERS 와 같은 판매처 (가격 데이터에는 판매처 로고가 없다) */
const SELLER_SITES: Record<string, string> = {
	CTR013: 'kr.trip.com',
	AGD217: 'www.agoda.com',
	YNJ035: 'nol.yanolja.com',
	INT005: 'nol.yanolja.com',
	MRT023: 'www.myrealtrip.com',
	SKP206: 'www.kiwi.com'
};

/** 판매처 가로 로고 (188×60) */
export const sellerWordmark = (partnerCode: string) =>
	`https://techminds.pstatic.net/flight/vertical-static/flight/redirects/v2/${partnerCode}.png`;

/** 판매처 아이콘 (사이트 favicon) — 모르는 판매처면 null */
export function sellerLogo(partnerCode: string): string | null {
	const site = SELLER_SITES[partnerCode];
	return site ? `https://www.google.com/s2/favicons?domain=${site}&sz=64` : null;
}

/** 확인 시각 → "방금" / "12분 전" / "3시간 전" */
export function ago(iso: string, now = Date.now()): string {
	const min = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60_000));
	if (min < 1) return '방금';
	if (min < 60) return `${min}분 전`;
	return `${Math.floor(min / 60)}시간 전`;
}

/** 예약 버튼 링크 — 짧은 링크. 이동 화면이 모을 때 가격을 먼저 보여 주고 실시간으로 다시 확인한다 */
export const linkHref = (offer: Offer) => `/r/${offer.code}`;
