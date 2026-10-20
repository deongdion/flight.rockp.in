import { SITE_URL } from '#lib/site.ts';

// 색인할 화면은 특가 목록 하나 — 짧은 링크는 금방 바뀌어 넣지 않는다
export const GET = () => {
	const today = new Date().toISOString().slice(0, 10);
	const xml =
		'<?xml version="1.0" encoding="UTF-8"?>\n' +
		'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
		`  <url><loc>${SITE_URL}/</loc><lastmod>${today}</lastmod><changefreq>hourly</changefreq><priority>1.0</priority></url>\n` +
		'</urlset>\n';
	return new Response(xml, {
		headers: { 'content-type': 'application/xml; charset=utf-8', 'cache-control': 'public, max-age=3600' }
	});
};
