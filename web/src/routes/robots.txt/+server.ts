import { SITE_URL } from '#lib/site.ts';

// 짧은 링크(/r/…)는 막지 않는다 — 막으면 링크 미리보기 봇이 OG 를 못 읽는다. 대신 페이지에 noindex.
export const GET = () =>
	new Response(`User-agent: *\nAllow: /\nDisallow: /api/\n\nSitemap: ${SITE_URL}/sitemap.xml\n`, {
		headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'public, max-age=3600' }
	});
