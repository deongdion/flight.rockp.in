<!--
  특가 자세히 — 가는편·오는편 항공편과 판매처별 요금(판매처마다 예약하기), 이 노선 가격 추이.
  열면 최저가 판매처 가격을 실시간으로 다시 확인하고(/api/links/<code>/redirect — 예약하기를 누르면 이 결과를 그대로 쓴다),
  끝나면 그 결과가 반영된 특가를 다시 받아 바뀐 점만 알려 준다 (확인 중 표시는 없고, 그대로면 "방금 확인"만).
  목록에도 onupdate 로 알려 카드 가격이 같이 바뀐다 (마감이면 null).
  한 칸으로 위에서 아래로 — 간격·그래프 높이를 줄여 스크롤 없이 한 화면에 (화면 높이가 낮으면 더 줄인다).
-->
<script lang="ts">
	import ItineraryRow from './ItineraryRow.svelte';
	import Modal from './Modal.svelte';
	import OfferRow from './OfferRow.svelte';
	import PriceTrend from './PriceTrend.svelte';
	import { ago, day, linkHref, nights, tripArrow, won } from '#lib/format.ts';
	import { apiQuery } from '#lib/search.ts';
	import type { Deal, DealPage, RedirectLink } from '#lib/types.ts';

	let {
		deal: initial,
		now,
		onclose,
		onupdate
	}: { deal: Deal; now: number; onclose: () => void; onupdate?: (deal: Deal | null) => void } = $props();

	// svelte-ignore state_referenced_locally
	let deal = $state(initial);
	// svelte-ignore state_referenced_locally
	const before = initial.offers[0].price;
	let status = $state<'checking' | 'same' | 'changed' | 'gone' | 'failed'>('checking');
	let checkedAt = $state<number | null>(null);

	$effect(() => {
		const ctrl = new AbortController();
		const signal = AbortSignal.any([ctrl.signal, AbortSignal.timeout(20_000)]);
		const key = {
			origin: initial.origin,
			destination: initial.destination,
			departure_date: initial.departure_date,
			return_date: initial.return_date ?? ''
		};
		fetch(`/api/links/${initial.offers[0].code}/redirect`, { signal })
			.then((r) => (r.ok ? (r.json() as Promise<RedirectLink>) : Promise.reject(r.status)))
			.then(() => fetch(`/api/deals?${apiQuery(key)}&limit=1`, { signal }))
			.then((r) => (r.ok ? (r.json() as Promise<DealPage>) : Promise.reject(r.status)))
			.then((page) => {
				const fresh = page.items[0] ?? null;
				checkedAt = Date.now();
				onupdate?.(fresh);
				if (!fresh) return (status = 'gone');
				deal = fresh;
				status = fresh.offers[0].price === before ? 'same' : 'changed';
			})
			.catch((e) => e?.name !== 'AbortError' && (status = 'failed'));
		return () => ctrl.abort();
	});

	const after = $derived(deal.offers[0]?.price ?? before);
	const originAirport = $derived(deal.itineraries[0]?.segments[0]?.dep_airport ?? deal.origin);
</script>

<Modal title="{deal.destination_name} 항공권" wide {onclose}>
	<div class="layout">
		<div class="main">
			<p class="when num">
				{originAirport} {tripArrow(deal.return_date)} {deal.destination} · {day(deal.departure_date)}{#if deal.return_date}
					– {day(deal.return_date)} · {nights(deal.departure_date, deal.return_date)}박{/if}
			</p>

			<!-- 실시간 확인 — 확인하는 동안은 아무것도 띄우지 않고, 바뀌었을 때만 알린다 -->
			{#if status === 'changed'}
				<p class="live num" class:down={after < before} aria-live="polite">
					최저가가 {after < before ? '내렸어요' : '올랐어요'} · <s>{won(before)}</s> → <b>{won(after)}</b>
				</p>
			{:else if status === 'gone'}
				<p class="live" aria-live="polite">이 특가는 판매가 끝났어요 · 다른 특가를 둘러보세요</p>
			{/if}

			{#if deal.itineraries.length}
				<section class="flights">
					{#each deal.itineraries as itinerary, i (itinerary.itinerary_id)}
						<ItineraryRow {itinerary} label={i ? '오는편' : '가는편'} />
					{/each}
					<p class="note">최저가 항공편 기준이에요. 판매처마다 항공편이 다를 수 있어요.</p>
				</section>
			{/if}

			<h3>판매처 {deal.offers.length}곳</h3>
			<div class="offers" class:dim={status === 'gone'}>
				{#each deal.offers as offer, i (offer.partner_code)}
					<OfferRow {offer} cheapest={i === 0} href={linkHref(offer)} />
				{/each}
			</div>

			<p class="checked">
				{checkedAt ? '방금' : ago(deal.checked_at, now)} 확인한 가격 · 예약하기를 누르면 가격을 다시 확인해요
			</p>
		</div>

		<div class="side">
			<PriceTrend origin={deal.origin} destination={deal.destination} price={after} />
		</div>
	</div>

	{#snippet footer()}
		<button class="btn lg" onclick={onclose}>닫기</button>
		{#if status === 'gone'}
			<a class="btn lg primary" href="/" onclick={onclose}>다른 특가 보기</a>
		{:else}
			<a class="btn lg primary" href={linkHref(deal.offers[0])} target="_blank" rel="noopener">최저가로 예약하기</a>
		{/if}
	{/snippet}
</Modal>

<style>
	.layout {
		display: grid;
		gap: 14px;
	}

	.when {
		color: var(--sub);
		font-size: 14px;
	}

	.live {
		margin-top: 8px;
		padding: 8px 12px;
		border-radius: 10px;
		background: var(--hover);
		color: var(--ink);
		font-size: 13px;
		font-weight: 600;
	}

	.live s {
		color: var(--muted);
		font-weight: 500;
	}

	/* 내렸으면 좋은 소식 — 하늘색 */
	.live.down {
		background: var(--ptBg);
		color: var(--pt);
	}

	.flights {
		margin-top: 10px;
		padding: 6px 12px;
		border-radius: 14px;
		background: var(--hover);
	}

	.note {
		margin-top: 2px;
		color: var(--muted);
		font-size: 12px;
	}

	h3 {
		margin: 14px 0 2px;
		font-size: 15px;
		font-weight: 700;
	}

	.offers {
		margin: 0 -12px;
	}

	.offers.dim {
		opacity: 0.45;
		pointer-events: none;
	}

	.checked {
		margin-top: 6px;
		color: var(--muted);
		font-size: 12px;
	}

	.flights {
		margin-top: 8px;
	}

	h3 {
		margin-top: 10px;
	}

	.offers :global(.offer) {
		padding: 6px 12px;
	}

	/* 화면 키가 작으면(아이폰 SE 667px, 노트북 720px 등) 여백을 더 줄인다 */
	@media (max-height: 799px) {
		.layout {
			gap: 8px;
		}

		.flights {
			padding: 2px 12px 4px;
		}

		.flights :global(.row) {
			padding: 2px 0;
		}

		h3 {
			margin: 6px 0 0;
		}

		.offers :global(.offer) {
			padding: 3px 12px;
		}

		.checked {
			margin-top: 2px;
		}
	}
</style>
