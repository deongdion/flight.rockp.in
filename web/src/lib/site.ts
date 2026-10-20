// 사이트 공통 정보 — 메타 태그·sitemap·robots 가 같이 쓴다.
// 주소는 터널 뒤에서 http 로 들어오므로 요청 주소 대신 고정 주소를 쓴다 (PUBLIC_SITE_URL 로 바꿀 수 있다).
import { PUBLIC_SITE_URL } from '$app/env/public';

export const SITE_NAME = '록핀';
export const SITE_URL = PUBLIC_SITE_URL;
export const SITE_DESCRIPTION = '판매처별 실시간 가격을 비교해 오늘 가장 싼 항공권을 모았어요.';
// 1200×630. 이미지를 바꾸면 v 를 올린다 — 주소가 같으면 카톡·브라우저·Cloudflare 가 예전 이미지를 계속 쓴다
export const OG_IMAGE = '/og.png?v=2';

/** "/r/abc" → "https://flight.rockp.in/r/abc", 이미 절대 주소면 그대로 */
export const absolute = (path: string) => (/^https?:\/\//.test(path) ? path : `${SITE_URL}${path}`);
