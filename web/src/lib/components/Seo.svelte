<!-- 페이지 메타 태그 — 제목·설명·canonical·Open Graph·Twitter·구조화 데이터. 서버 렌더링으로 HTML 에 들어간다 -->
<script lang="ts">
	import { OG_IMAGE, SITE_NAME, absolute } from '#lib/site.ts';

	let {
		title,
		description,
		path,
		image = OG_IMAGE,
		imageAlt = SITE_NAME,
		noindex = false,
		jsonLd
	}: {
		title: string;
		description: string;
		path: string; // canonical 경로 ("/", "/r/abc")
		image?: string;
		imageAlt?: string;
		noindex?: boolean;
		jsonLd?: Record<string, unknown>;
	} = $props();

	const url = $derived(absolute(path));
	const img = $derived(absolute(image));
	const isDefaultImage = $derived(image === OG_IMAGE);
	// 문자열 안의 '<' 를 이스케이프해 스크립트 태그가 중간에 닫히지 않게
	const ld = $derived(jsonLd ? JSON.stringify(jsonLd).replace(/</g, '\\u003c') : '');
</script>

<svelte:head>
	<title>{title}</title>
	<meta name="description" content={description} />
	<link rel="canonical" href={url} />
	<meta name="robots" content={noindex ? 'noindex, follow' : 'index, follow, max-image-preview:large'} />

	<meta property="og:type" content="website" />
	<meta property="og:site_name" content={SITE_NAME} />
	<meta property="og:locale" content="ko_KR" />
	<meta property="og:title" content={title} />
	<meta property="og:description" content={description} />
	<meta property="og:url" content={url} />
	<meta property="og:image" content={img} />
	<meta property="og:image:alt" content={imageAlt} />
	{#if isDefaultImage}
		<meta property="og:image:width" content="1200" />
		<meta property="og:image:height" content="630" />
	{/if}

	<meta name="twitter:card" content="summary_large_image" />
	<meta name="twitter:title" content={title} />
	<meta name="twitter:description" content={description} />
	<meta name="twitter:image" content={img} />

	{#if ld}
		{@html `<script type="application/ld+json">${ld}</script>`}
	{/if}
</svelte:head>
