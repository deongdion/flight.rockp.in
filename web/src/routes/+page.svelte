<!--
  특가 목록 (DESIGN.md 7번 목록 화면)
  검색 상자(출발지·도착지·가는 날·오는 날)는 주소로 서버가 DB 전체에서 찾는다 — 고를 때마다 바로 다시 검색.
  도착지를 안 고르면 도착지마다 최저 1건, 고르면 그 도착지의 모든 날짜.
  처음엔 한 쪽(24장)만 서버가 그려 보내고, 스크롤하면 다음 쪽을 /api/deals 로 이어 받는다.
  직항만·정렬도 주소에 담아 서버(DB)에서 거른다.
-->
<script lang="ts">
	import DealCard from '#lib/components/DealCard.svelte';
	import DealCardSkeleton from '#lib/components/DealCardSkeleton.svelte';
	import DealDetail from '#lib/components/DealDetail.svelte';
	import SearchBox from '#lib/components/SearchBox.svelte';
	import { goto } from '$app/navigation';
	import { navigating } from '$app/state';
	import { EMPTY_FILTERS, pageQuery, searchHref } from '#lib/search.ts';
	import Icon from '#lib/components/Icon.svelte';
	import Seo from '#lib/components/Seo.svelte';
	import { ago, cityName } from '#lib/format.ts';
	import { SITE_DESCRIPTION, SITE_NAME, SITE_URL } from '#lib/site.ts';
	import type { Deal, DealPage, SearchFilters } from '#lib/types.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// 서버가 첫 한 쪽을 그려 보낸다 (검색엔진·미리보기 봇도 특가를 읽는다). 스크롤하면 뒤에 이어 붙인다
	// 서버 데이터로 정해지고(조건이 바뀌면 다시), 스크롤하면 그 위에 덧붙인다 (덮어쓸 수 있는 $derived)
	let deals = $derived<Deal[] | null>(data.deals);
	let total = $derived(data.total);
	const error = $derived(data.error);
	const search = $derived(data.filters);
	const view = $derived(data.view);
	const now = Date.now();

	// 조건(출발지·도착지·날짜·직항만·정렬)이 바뀌면 주소를 바꿔 서버가 다시 찾게 한다 (스크롤은 그대로)
	const go = (next: SearchFilters, nextView = view) =>
		goto(searchHref(next, nextView), { replace: true, reset: false });
	const searchFor = (next: SearchFilters) => go(next);
	const searching = $derived(!!navigating.to);

	// 직항만 체크는 검색 상자와 주고받는다 — 바뀌면 다시 찾기
	let directOnly = $derived(data.view.directOnly);
	$effect(() => {
		if (directOnly !== view.directOnly) go(search, { ...view, directOnly });
	});
	let detail = $state<Deal | null>(null);

	// ── 메타 — 설명은 숫자 없는 한 문장 (site.ts) ──
	const seoDescription = SITE_DESCRIPTION;
	const jsonLd = $derived({
		'@context': 'https://schema.org',
		'@type': 'WebSite',
		name: SITE_NAME,
		url: SITE_URL,
		inLanguage: 'ko-KR',
		description: SITE_DESCRIPTION
	});

	const searching_any = $derived(Object.values(search).some(Boolean));
	const newest = $derived(deals?.length ? deals.reduce((a, d) => (d.checked_at > a ? d.checked_at : a), '') : '');

	// ── 스크롤하면 다음 쪽 ──
	let moreMark = $state<HTMLDivElement>();
	let loadingMore = $state(false);

	async function loadMore() {
		if (loadingMore || !deals || deals.length >= total) return;
		loadingMore = true;
		try {
			const r = await fetch(`/api/deals?${pageQuery(search, view, deals.length)}`);
			if (r.ok) {
				const next = (await r.json()) as DealPage;
				deals = [...deals, ...next.items];
				total = next.total;
			}
		} finally {
			loadingMore = false;
		}
	}

	$effect(() => {
		if (!moreMark) return;
		const io = new IntersectionObserver(([e]) => e.isIntersecting && loadMore(), { rootMargin: '800px' });
		io.observe(moreMark);
		return () => io.disconnect();
	});
</script>

<Seo
	title="{search.destination && deals?.[0]
		? `${search.origin ? cityName(search.origin) + ' 출발 ' : ''}${deals[0].destination_name} 급락 항공권`
		: search.origin
			? `${cityName(search.origin)} 출발 급락 항공권`
			: '오늘의 급락 항공권'} · {SITE_NAME}"
	description={seoDescription}
	path="/"
	{jsonLd}
/>

<SearchBox
	filters={search}
	destinationName={search.destination ? deals?.[0]?.destination_name : ''}
	onchange={searchFor}
	bind:directOnly
/>


<div class="wrap">
	{#if error}
		<div class="empty">
			<Icon name="empty" />
			<strong>특가를 불러오지 못했어요</strong>
			<p>잠시 뒤 다시 시도해 주세요</p>
			<div class="actions"><button class="btn" onclick={() => location.reload()}>다시 불러오기</button></div>
		</div>
	{:else if !deals}
		<div class="bar"><span class="sk" style="width: 160px; height: 18px"></span></div>
		<ul class="grid">
			{#each Array(8) as _, i (i)}<li><DealCardSkeleton /></li>{/each}
		</ul>
	{:else}
		<div class="bar">
			<p class="stamp num">
				{#if data.grouped}
					도착지 {total.toLocaleString('ko-KR')}곳 · 특가 {data.dealCount.toLocaleString('ko-KR')}개
				{:else}
					특가 {total.toLocaleString('ko-KR')}개
				{/if}{#if newest}{' · '}{ago(newest, now)} 갱신{/if}
			</p>
			<div class="seg" role="radiogroup" aria-label="정렬">
				<button role="radio" aria-checked={view.sort === 'price'} onclick={() => go(search, { ...view, sort: 'price' })}>낮은 가격순</button>
				<button role="radio" aria-checked={view.sort === 'date'} onclick={() => go(search, { ...view, sort: 'date' })}>빠른 출발순</button>
			</div>
		</div>
		<p class="sr-only" aria-live="polite">특가 {total}개</p>


		{#if !deals.length && view.directOnly}
			<div class="empty">
				<Icon name="empty" />
				<strong>조건에 맞는 특가가 없어요</strong>
				<p>직항이 아닌 항공편도 함께 볼까요?</p>
				<div class="actions"><button class="btn primary" onclick={() => (directOnly = false)}>‘직항만’ 빼기</button></div>
			</div>
		{:else if !deals.length && searching_any}
			<div class="empty">
				<Icon name="empty" />
				<strong>조건에 맞는 특가가 없어요</strong>
				<p>출발지·도착지·날짜 중 하나를 풀어 보세요</p>
				<div class="actions"><button class="btn primary" onclick={() => searchFor(EMPTY_FILTERS)}>조건 모두 지우기</button></div>
			</div>
		{:else if !deals.length}
			<div class="empty">
				<Icon name="empty" />
				<strong>아직 모은 특가가 없어요</strong>
				<p>새 특가를 모으고 있어요. 잠시 뒤 다시 와 주세요</p>
				<div class="actions"><button class="btn" onclick={() => location.reload()}>새로고침</button></div>
			</div>
		{:else}
			<ul class="grid" class:searching>
				{#each deals as deal (`${deal.origin}-${deal.destination}-${deal.departure_date}-${deal.return_date}`)}
					<li>
						<DealCard
							{deal}
							onopen={() => (detail = deal)}
						/>
					</li>
				{/each}
			</ul>
			{#if deals.length < total}<div bind:this={moreMark} class="more"></div>{/if}
		{/if}
	{/if}
</div>

{#if detail}
	{@const key = (d: Deal) => `${d.origin}-${d.destination}-${d.departure_date}-${d.return_date}`}
	{@const opened = key(detail)}
	<DealDetail
		deal={detail}
		{now}
		onclose={() => (detail = null)}
		onupdate={(fresh) => {
			// 자세히 보기에서 다시 확인한 값으로 카드도 바꾼다 (마감이면 목록에서 뺀다)
			if (!deals) return;
			deals = fresh ? deals.map((d) => (key(d) === opened ? fresh : d)) : deals.filter((d) => key(d) !== opened);
			if (!fresh) total = Math.max(0, total - 1);
		}}
	/>
{/if}

<style>







	.bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		padding: 18px 0 12px;
		min-height: 48px;
	}

	.stamp {
		color: var(--sub);
		font-size: 13px;
	}







	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
		gap: 20px 14px;
		list-style: none;
	}

	.grid > li {
		display: flex;
	}

	.grid > li > :global(*) {
		flex: 1;
	}

	.more {
		height: 1px;
	}

	/* 다시 찾는 동안 목록을 살짝 흐리게 */
	.grid.searching {
		opacity: 0.5;
		transition: opacity 0.15s 0.1s;
	}

	@media (max-width: 640px) {
		.grid {
			grid-template-columns: 1fr;
		}
	}
</style>
