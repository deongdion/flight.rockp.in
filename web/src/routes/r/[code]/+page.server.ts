import { apiGet } from '#lib/server/api.ts';
import type { Link } from '#lib/types.ts';
import type { PageServerLoad } from './$types';

// 미리보기 봇(카톡·슬랙 등)은 실시간 확인을 시작시키지 않는다
const BOT = /bot|crawl|spider|preview|scrap|facebookexternalhit|slack|kakaotalk|discord|whatsapp|telegram/i;

// 짧은 링크 정보는 서버에서 받아 HTML·OG 에 넣는다 (카톡·슬랙 미리보기에 노선·가격이 뜨게).
// 사람이 열면 실시간 확인도 이때 시작한다 — 화면이 뜨는 동안 확인이 진행된다
export const load: PageServerLoad = async ({ params, fetch, request }) => {
	const warm = BOT.test(request.headers.get('user-agent') ?? '') ? '' : '?warm=true';
	try {
		return { link: await apiGet<Link>(`/api/links/${encodeURIComponent(params.code)}${warm}`, fetch) };
	} catch {
		return { link: null };
	}
};
