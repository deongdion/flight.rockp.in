<!--
  특가 카드 — 사진 → 내용 → 가격 → 버튼 (DESIGN.md 6번 카드, A형).
  카드 전체를 누르면 자세히(모달), 안쪽 버튼은 카드까지 올라가지 않는다.
-->
<script lang="ts">
	import { airlineLogo, airlineName, cityPhoto, day, duration, linkHref, nights, placeName, stops, won } from '#lib/format.ts';
	import type { Deal } from '#lib/types.ts';
	import SellerLogo from './SellerLogo.svelte';

	let {
		deal,
		onopen,
	}: {
		deal: Deal;
		onopen: () => void;
	} = $props();

	let loaded = $state(false);
	let broken = $state(false);
	let photo = $state<HTMLImageElement>();

	// 서버가 그린 HTML 에서는 화면이 연결되기 전에 사진을 다 받아 onload 를 놓칠 수 있다 → 연결 직후 한 번 확인
	$effect(() => {
		if (!photo?.complete) return;
		if (photo.naturalWidth > 0) loaded = true;
		else broken = true;
	});

	const outbound = $derived(deal.itineraries[0]);
	// 예약 조회는 공항 코드로 (origin 은 SEL 같은 도시 코드)
	const originAirport = $derived(outbound?.segments[0]?.dep_airport ?? deal.origin);
	const cheapest = $derived(deal.offers[0]);
	const airlines = $derived([...new Set(deal.itineraries.flatMap((i) => i.segments.map((s) => s.airline)))]);
	const direct = $derived(deal.itineraries.length > 0 && deal.itineraries.every((i) => stops(i) === 0));
	const bookHref = $derived(linkHref(cheapest));
	const n = $derived(deal.return_date ? nights(deal.departure_date, deal.return_date) : 0);
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
<article class="card" onclick={onopen}>
	<div class="photo" class:loaded>
		{#if deal.image_url && !broken}
			<img
				bind:this={photo}
				src={cityPhoto(deal.image_url)}
				alt={deal.destination_name}
				loading="lazy"
				onload={() => (loaded = true)}
				onerror={() => (broken = true)}
			/>
		{:else}
			<!-- 네이버가 도시 사진을 주지 않는 곳 (소도시 몇십 곳) — 국기와 이름으로 자리를 채운다 -->
			<span class="placeholder">
				{#if deal.country_code}
					<img class="big-flag" src="/flags/{deal.country_code.toLowerCase()}.svg" alt="" width="40" height="30" onerror={(e) => e.currentTarget.remove()} />
				{/if}
				<span>{deal.destination_name}</span>
			</span>
		{/if}
	</div>

	<div class="body">
		<h3>
			{#if deal.country_code}
				<img class="flag" src="/flags/{deal.country_code.toLowerCase()}.svg" alt="" width="20" height="15" loading="lazy" onerror={(e) => e.currentTarget.remove()} />
			{/if}
			{deal.destination_name} <span>{placeName(originAirport)} 출발</span>
		</h3>
		<p class="dates num">
			{day(deal.departure_date)}{#if deal.return_date}{' – '}{day(deal.return_date)}<span class="n">{n}박</span>{/if}
		</p>
		<p class="meta">
			<span class="logos">
				{#each airlines.slice(0, 2) as code (code)}
					<img src={airlineLogo(code)} alt={code} onerror={(e) => e.currentTarget.remove()} />
				{/each}
			</span>
			{#if outbound}
				<span>{airlines.map(airlineName).join(' · ')}</span>
				<span class="dot">{direct ? '직항' : `경유 ${stops(outbound)}회`}</span>
				<span class="dot">{duration(outbound.duration)}</span>
			{/if}
		</p>

		<div class="price">
			<span class="main"><strong class="num">{won(cheapest.price)}</strong><span>왕복</span></span>
			<span class="seller">
				<SellerLogo partnerCode={cheapest.partner_code} size={14} />
				{cheapest.seller}{deal.offers.length > 1 ? ` 외 ${deal.offers.length - 1}곳` : ''}
			</span>
		</div>

		<div class="btns">
			<button class="btn" onclick={(e) => (e.stopPropagation(), onopen())}>자세히 보기</button>
			<a class="btn primary" href={bookHref} target="_blank" rel="noopener" onclick={(e) => e.stopPropagation()}>
				예약하기
			</a>
		</div>
	</div>
</article>

<style>
	.card {
		display: flex;
		flex-direction: column;
		border-radius: 18px;
		background: #fff;
		box-shadow: var(--card-shadow);
		overflow: hidden;
		cursor: pointer;
		transition:
			transform 0.2s var(--ease),
			box-shadow 0.2s;
	}

	.card:hover {
		transform: translateY(-3px);
		box-shadow: var(--card-shadow-hover);
	}

	.card:active {
		transform: translateY(-1px) scale(0.99);
	}

	.photo {
		position: relative;
		height: 150px;
		display: flex;
		align-items: center;
		justify-content: center;
		overflow: hidden;
		background: var(--el);
	}

	.photo img {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover;
		opacity: 0;
		transition:
			opacity 0.35s,
			transform 0.5s var(--ease);
	}

	.photo.loaded img {
		opacity: 1;
	}

	.card:hover .photo img {
		transform: scale(1.04);
	}

	.placeholder {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 10px;
		color: var(--sub);
		font-size: 16px;
		font-weight: 700;
	}

	.photo .placeholder .big-flag {
		position: static;
		width: 40px;
		height: 30px;
		border-radius: 3px;
		opacity: 1;
		object-fit: cover;
		box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.06);
	}


	.body {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 5px;
		padding: 14px 16px 16px;
	}

	h3 {
		display: flex;
		align-items: center;
		gap: 7px;
		font-size: 17px;
		font-weight: 700;
		line-height: 1.3;
	}

	/* 나라 국기 — Rockpin/web/public/flags (DESIGN.md 카드 A형 "🇯🇵 제목") */
	.flag {
		flex: none;
		width: 20px;
		height: 15px;
		border-radius: 3px;
		box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.06);
		object-fit: cover;
	}

	h3 span {
		margin-left: -3px;
		color: var(--muted);
		font-size: 13px;
		font-weight: 500;
	}

	.dates {
		font-size: 14px;
		font-weight: 600;
	}

	.dates .n {
		margin-left: 6px;
		color: var(--sub);
		font-weight: 500;
	}

	.meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 2px 6px;
		color: var(--sub);
		font-size: 13px;
	}

	.meta .dot::before {
		content: '·';
		margin-right: 6px;
		color: var(--muted);
	}


	.logos {
		display: inline-flex;
		gap: 2px;
	}

	.logos img {
		width: 14px;
		height: 14px;
		object-fit: contain;
	}

	.price {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		justify-content: space-between;
		gap: 2px 8px;
		margin-top: auto;
		padding-top: 8px;
	}

	.main {
		display: flex;
		align-items: baseline;
		gap: 5px;
		white-space: nowrap;
	}

	.main strong {
		font-size: 19px;
		font-weight: 700;
		letter-spacing: -0.01em;
	}

	.main span {
		color: var(--muted);
		font-size: 12px;
	}

	.seller {
		color: var(--sub);
		font-size: 12px;
		font-weight: 600;
	}

	.seller {
		display: inline-flex;
		align-items: center;
		gap: 5px;
	}



	.btns {
		display: flex;
		gap: 6px;
		margin-top: 12px;
	}

	.btns .btn {
		flex: 1;
	}
</style>
