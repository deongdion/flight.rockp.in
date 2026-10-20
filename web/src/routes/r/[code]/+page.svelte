<!--
  짧은 링크 /r/<code> — 예약하기를 누르면 열리는 이동 화면.
    상태 막대 + 진행 라인 → 판매처 로고 → 가격 → 일정 → 안내 상자 → 바닥 로고
  1) 서버가 모을 때 본 항공편·판매처·가격을 HTML 에 그려 둔다 (OG 미리보기도 이것으로)
  2) 서버가 화면을 그릴 때 실시간 확인을 시작하고, 브라우저는 /api/links/<code>/redirect 로 결과를 받는다
     (판매처가 들어오는 즉시 끊어 보통 2~6초, 최대 15초 — 넘기면 판매처 검색 페이지)
  지금 가격이 같고 예약 페이지로 바로 가면 진행 라인이 차오른 뒤 자동 이동 (일시정지 가능),
  아니면 바뀐 점을 보여 주고 버튼으로. 빨강은 쓰지 않는다 — 내려가면 하늘색, 오르면 검정.
-->
<script lang="ts">
	import { page } from '$app/state';
	import Logo from '#lib/components/Logo.svelte';
	import Seo from '#lib/components/Seo.svelte';
	import SellerLogo from '#lib/components/SellerLogo.svelte';
	import {
		ago,
		airlineLogo,
		airlineName,
		cityPhoto,
		day,
		dayOffset,
		duration,
		fullDay,
		hhmm,
		nights,
		placeName,
		sellerWordmark,
		stops,
		tripArrow,
		won
	} from '#lib/format.ts';
	import { SITE_NAME } from '#lib/site.ts';
	import type { Itinerary, RedirectLink } from '#lib/types.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const AUTO_GO_MS = 3000; // 진행 라인이 다 차는 시간
	const link = $derived(data.link);
	const code = $derived(page.params.code ?? '');

	let live = $state<RedirectLink | null>(null);
	let failed = $state(false);
	let paused = $state(false);
	let progress = $state(0); // 0~1 — 자동 이동까지
	let wordmarkBroken = $state(false);

	const ids = (its: Itinerary[]) => its.map((i) => i.itinerary_id).join('-');
	const before = $derived(link?.offer.price ?? 0);
	const after = $derived(live?.price ?? null);
	// 확인이 끝났는데 지금 가격이 없으면 (요금 없음·확인 실패) 모을 때 가격은 흐리게 + 취소선
	const unconfirmed = $derived(failed || (!!live && (live.sold_out || after === null)));
	const diff = $derived(after && before ? after - before : 0);
	// 실시간으로 확인한 항공편이 모을 때와 다르면 (다른 항공편으로 다시 찾아진 경우)
	const flightChanged = $derived(
		!!link && !!live?.itineraries.length && !!link.itineraries.length && ids(live.itineraries) !== ids(link.itineraries)
	);
	const itineraries = $derived(flightChanged && live ? live.itineraries : (link?.itineraries ?? []));
	const autoGo = $derived(!!live && live.kind === 'booking' && after === before && !flightChanged);
	const checking = $derived(!live && !failed);

	const route = $derived(link ? `${placeName(link.origin)} ${tripArrow(link.return_date)} ${link.destination_name}` : '');

	// 일정 줄 — 가는편/오는편 (항공편 정보가 없으면 날짜만)
	const legs = $derived.by(() => {
		if (!link) return [];
		const out = [{ from: link.origin, to: link.destination, date: link.departure_date, it: itineraries[0] }];
		if (link.return_date) out.push({ from: link.destination, to: link.origin, date: link.return_date, it: itineraries[1] });
		return out;
	});
	const name = (code: string) => (code === link?.destination ? link.destination_name : placeName(code));

	const status = $derived(
		!link
			? ''
			: checking
				? '최신 가격을 확인하고 있어요'
				: live?.sold_out
					? '이 요금은 지금 판매되지 않아요'
					: failed || after === null
						? '지금 가격을 확인하지 못했어요'
						: autoGo
							? paused
								? '이동을 멈췄어요'
								: '판매자 사이트로 이동 중이에요'
							: diff
								? '가격이 바뀌었어요'
								: flightChanged
									? '항공편이 바뀌었어요'
									: '판매처 검색 화면으로 안내해요'
	);

	// 미리보기 설명 — "11.24(화) – 11.30(월) · 6박 · 트립닷컴 · 가는편 07:55 9C6150 직항"
	const seoDescription = $derived.by(() => {
		if (!link) return '링크가 만료됐어요. 오늘의 급락 항공권에서 다시 찾아보세요.';
		const n = link.return_date ? nights(link.departure_date, link.return_date) : 0;
		const go = link.itineraries[0];
		return [
			`${day(link.departure_date)}${link.return_date ? ` – ${day(link.return_date)} · ${n}박` : ''}`,
			link.offer.seller,
			go?.segments[0] &&
				`가는편 ${hhmm(go.segments[0].dep_time)} ${go.segments.map((s) => s.airline + s.flight_no).join(',')} ${stops(go) ? '경유' : '직항'}`,
			'예약 전에 지금 가격을 다시 확인해요'
		]
			.filter(Boolean)
			.join(' · ');
	});

	$effect(() => {
		if (!link) return;
		// 서버는 늦어도 15초 안에 답한다 — 그래도 안 오면(연결 문제) 20초에 포기하고 판매처로 가는 버튼을 보인다
		fetch(`/api/links/${code}/redirect`, { signal: AbortSignal.timeout(20_000) })
			.then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
			.then((d: RedirectLink) => (live = d))
			.catch(() => (failed = true));
	});

	// 자동 이동 — 진행 라인을 채우고 다 차면 이동. 일시정지 중에는 멈춘다
	$effect(() => {
		if (!autoGo || paused || !live) return;
		const url = live.url;
		const step = 50 / AUTO_GO_MS;
		const t = setInterval(() => {
			progress = Math.min(1, progress + step);
			if (progress >= 1) {
				clearInterval(t);
				location.assign(url);
			}
		}, 50);
		return () => clearInterval(t);
	});
</script>

<Seo
	title={link ? `${route} 항공권 ${won(before)} · ${SITE_NAME}` : `링크가 만료됐어요 · ${SITE_NAME}`}
	description={seoDescription}
	path="/r/{code}"
	image={link?.image_url ? cityPhoto(link.image_url) : undefined}
	imageAlt={link?.destination_name}
	noindex
/>

<main class="screen">
	<div class="container">
		{#if !link}
			<div class="bar"><span class="text">링크가 만료됐어요</span></div>
			<div class="top">
				<p class="desc">출발일이 지났거나 오래된 링크예요. 오늘의 특가에서 다시 찾아보세요.</p>
				<a class="btn lg primary wide" href="/">오늘의 특가 보기</a>
			</div>
		{:else}
			<!-- 상태 막대 + 진행 라인 -->
			<div class="bar">
				<span class="text" aria-live="polite">{status}</span>
				{#if autoGo}
					<button
						class="pause"
						aria-label="자동 이동 일시정지/계속"
						aria-pressed={paused}
						onclick={() => (paused = !paused)}
					>
						<svg viewBox="0 0 36 36" aria-hidden="true">
							<circle cx="18" cy="18" r="17.5" />
							{#if paused}
								<path d="M15 12.5v11l9-5.5z" class="fill" />
							{:else}
								<rect x="13.3" y="12.3" width="1.9" height="11.4" rx="0.95" class="fill" />
								<rect x="20.8" y="12.3" width="1.9" height="11.4" rx="0.95" class="fill" />
							{/if}
						</svg>
					</button>
				{/if}
			</div>
			<div class="progress" class:indeterminate={checking} role="progressbar" aria-label={status}>
				{#if autoGo}<div class="current" style:width="{progress * 100}%"></div>{/if}
			</div>

			<div class="top">
				<!-- 판매처 로고 -->
				<div class="seller">
					{#if !wordmarkBroken}
						<img
							src={sellerWordmark(link.offer.partner_code)}
							alt={link.offer.seller}
							height="30"
							onerror={() => (wordmarkBroken = true)}
						/>
					{:else}
						<SellerLogo partnerCode={link.offer.partner_code} size={24} />
						<strong>{link.offer.seller}</strong>
					{/if}
				</div>

				<!-- 가격 -->
				<div class="price">
					<strong class="total num" class:gone={unconfirmed}>{won(after ?? before)}</strong>
					{#if diff}
						<p class="change" class:down={diff < 0}>
							{diff < 0 ? '▼' : '▲'} {won(Math.abs(diff))} {diff < 0 ? '내렸어요' : '올랐어요'}
							<s class="num">{won(before)}</s>
						</p>
					{/if}
					<div class="meta">
						<span>성인 1명</span><span>일반석</span><span>{link.return_date ? '왕복' : '편도'}</span>
					</div>
				</div>

				<!-- 일정 -->
				<div class="schedule">
					{#each legs as leg, i (i)}
						<div class="itinerary">
							<div class="row">
								<span class="route"><b>{name(leg.from)}</b><i>{leg.from}</i></span>
								<span class="route"><b>{name(leg.to)}</b><i>{leg.to}</i></span>
								<span class="date num">{fullDay(leg.date)}</span>
							</div>
							{#if leg.it?.segments.length}
								{@const a = leg.it.segments[0]}
								{@const b = leg.it.segments.at(-1)!}
								<div class="flight num">
									<strong class="time">
										{hhmm(a.dep_time)} – {hhmm(b.arr_time)}{#if dayOffset(leg.it)}<sup>+{dayOffset(leg.it)}</sup>{/if}
									</strong>
									<span class="dot">{stops(leg.it) ? `경유 ${stops(leg.it)}회` : '직항'}</span>
									<span class="dot">{duration(leg.it.duration)}</span>
									<span class="airline">
										{#each [...new Set(leg.it.segments.map((s) => s.airline))] as al (al)}
											<img src={airlineLogo(al)} alt="" onerror={(e) => e.currentTarget.remove()} />
										{/each}
										{[...new Set(leg.it.segments.map((s) => airlineName(s.airline)))].join(' · ')}
										{leg.it.segments.map((s) => s.airline + s.flight_no).join(', ')}
									</span>
								</div>
							{/if}
						</div>
					{/each}
					{#if flightChanged}<p class="note">모을 때와 다른 항공편이에요 · 지금 가장 싼 항공편으로 안내해요</p>{/if}
				</div>

				<!-- 다음 행동 (자동 이동 중이 아닐 때) -->
				{#if live?.sold_out}
					<a class="btn lg primary wide" href="/">다른 특가 보기</a>
					<a class="sub-link" href={live.url}>{link.offer.seller}에서 직접 찾아보기</a>
				{:else if failed}
					<a class="btn lg primary wide" href={page.url.href}>다시 확인하기</a>
				{:else if live && (!autoGo || paused)}
					<a class="btn lg primary wide" href={live.url}>
						{autoGo ? '지금 이동하기' : live.kind === 'booking' ? '이 가격으로 예약하기' : `${link.offer.seller}에서 찾아보기`}
					</a>
					{#if live.kind === 'search'}<p class="note">판매처 사이트에서는 가격이 조금 다를 수 있어요</p>{/if}
				{/if}
			</div>

			<!-- 안내 상자 -->
			<div class="bottom">
				<div class="heading">
					<svg viewBox="0 0 30 30" aria-hidden="true">
						<path d="M28.27 24c.77 1.33-.19 3-1.73 3H3.46c-1.54 0-2.5-1.67-1.73-3L13.27 4c.77-1.33 2.7-1.33 3.46 0z" />
						<path d="M15 12v6" class="stroke" />
						<circle cx="15" cy="22" r="1" class="dot" />
					</svg>
					<span>항공권 취소/환불 주의사항</span>
				</div>
				<dl>
					<dd>판매처마다 요금 규정이 달라요. 구매 옵션에 따라 환불이 안 될 수 있으니 예약 전에 꼭 확인하세요.</dd>
					<dt>결제 수수료 안내</dt>
					<dd>결제수단에 따라 수수료가 붙을 수 있고, 해외 판매처는 환율에 따라 최종 결제 금액이 달라질 수 있어요.</dd>
				</dl>
				<ul>
					<li><strong>{link.offer.seller}에서 예약·결제해요</strong></li>
					{#if link.offer.baggage === 'FREE'}<li><strong>위탁 수화물 포함</strong></li>{/if}
					{#if link.offer.baggage === 'CHARGE'}<li><strong>위탁 수화물 별도</strong></li>{/if}
					{#if link.checked_at}<li>{ago(link.checked_at)} 모은 가격이에요. 이동하기 전에 지금 가격을 다시 확인해요.</li>{/if}
					<li>
						{SITE_NAME}은 판매처의 항공권 가격을 비교해 연결하는 서비스로, 예약·결제·환불 등의 의무와 책임은 각
						판매처에 있어요.
					</li>
				</ul>
			</div>
		{/if}

		<!-- 카드 맨 아래 왼쪽 로고 -->
		<a class="footer" href="/" aria-label="{SITE_NAME} 처음 화면"><Logo /></a>
	</div>
</main>

<style>
	.screen {
		position: relative;
		display: flex;
		flex-direction: column;
		justify-content: center;
		min-height: 100dvh;
		width: min(640px, 100%);
		margin: 0 auto;
		padding: 80px 0;
		font-size: 15px;
		line-height: 22px;
	}

	.screen::before {
		content: '';
		position: fixed;
		inset: 0;
		z-index: -1;
		background: var(--hover);
	}

	.container {
		padding: 20px 20px 30px;
		border-radius: 12px;
		background: #fff;
	}

	/* 상태 막대 */
	.bar {
		display: flex;
		align-items: center;
		min-height: 36px;
		padding-inline: 10px;
	}

	.bar .text {
		font-weight: 600;
		letter-spacing: -0.3px;
	}

	.pause {
		display: inline-flex;
		margin-left: auto;
		padding: 0;
		border: 0;
		background: none;
		cursor: pointer;
	}

	.pause svg {
		width: 36px;
		height: 36px;
		fill: none;
	}

	.pause circle {
		stroke: #c9c9c9;
	}

	.pause .fill {
		fill: #000;
		opacity: 0.8;
	}

	/* 진행 라인 */
	.progress {
		position: relative;
		height: 2px;
		margin: 10px 10px 0;
		border-radius: 10px;
		background: var(--line);
		overflow: hidden;
	}

	.progress .current {
		position: absolute;
		inset: 0 auto 0 0;
		border-radius: inherit;
		background: var(--ink);
		transition: width 0.05s linear;
	}

	.progress.indeterminate::after {
		content: '';
		position: absolute;
		inset: 0;
		width: 35%;
		border-radius: inherit;
		background: var(--ink);
		animation: slide 1.2s var(--ease) infinite;
	}

	@keyframes slide {
		from {
			transform: translateX(-100%);
		}
		to {
			transform: translateX(290%);
		}
	}

	.top {
		padding: 0 10px 40px;
	}

	.top > * {
		margin-top: 24px;
	}

	.seller {
		display: flex;
		align-items: center;
		gap: 8px;
		height: 30px;
	}

	.seller img {
		display: block;
		height: 30px;
		width: auto;
	}

	.seller strong {
		font-size: 17px;
		font-weight: 700;
	}

	/* 가격 */
	.total {
		font-size: 24px;
		font-weight: 700;
		line-height: 32px;
		letter-spacing: -0.3px;
	}

	.total.gone {
		color: var(--muted);
		text-decoration: line-through;
	}

	.change {
		color: #000;
		font-size: 13px;
		font-weight: 600;
	}

	.change.down {
		color: var(--pt);
	}

	.change s {
		margin-left: 4px;
		color: var(--muted);
		font-weight: 500;
	}

	.meta {
		color: var(--sub);
		font-size: 14px;
	}

	.meta span {
		font-weight: 500;
	}

	.meta span + span::before {
		content: '';
		display: inline-block;
		width: 3px;
		height: 3px;
		margin-inline: 5px;
		border-radius: 50%;
		background: var(--muted);
		vertical-align: 3px;
	}

	/* 일정 */
	.itinerary + .itinerary {
		margin-top: 14px;
	}

	.row {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		font-weight: 600;
		letter-spacing: -0.3px;
	}

	.route {
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}

	.route + .route::before {
		content: '→';
		margin-inline: 6px;
		color: var(--muted);
		font-weight: 500;
	}

	.route i {
		margin-left: 4px;
		color: var(--pt);
		font-style: normal;
	}

	.date {
		flex-shrink: 0;
		margin-left: auto;
		padding-left: 12px;
	}

	.flight {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 2px 8px;
		margin-top: 2px;
		color: var(--sub);
		font-size: 13px;
		line-height: 20px;
	}

	.flight img {
		width: 14px;
		height: 14px;
		object-fit: contain;
	}

	.flight .time {
		color: #000;
		font-size: 14px;
		font-weight: 600;
	}

	.flight .dot::before {
		content: '·';
		margin-right: 8px;
		color: var(--muted);
	}

	.flight .airline {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		margin-left: auto;
		color: var(--muted);
		font-size: 12px;
	}

	.flight sup {
		font-size: 10px;
	}

	.note {
		color: var(--muted);
		font-size: 12px;
	}

	.wide {
		width: 100%;
	}

	.sub-link {
		display: block;
		margin-top: 10px;
		color: var(--sub);
		font-size: 13px;
		font-weight: 600;
		text-align: center;
	}

	/* 안내 상자 */
	.bottom {
		padding: 20px;
		border-radius: 16px;
		background: var(--hover);
		color: var(--sub);
		font-size: 13px;
		line-height: 20px;
		letter-spacing: -0.2px;
	}

	.heading {
		display: flex;
		align-items: center;
		gap: 10px;
		color: #000;
		font-size: 16px;
		font-weight: 700;
		line-height: 23px;
	}

	.heading svg {
		flex: none;
		width: 30px;
		height: 30px;
		fill: var(--ink);
	}

	.heading .stroke {
		fill: none;
		stroke: #fff;
		stroke-width: 2;
		stroke-linecap: round;
	}

	.heading .dot {
		fill: #fff;
	}

	dl {
		margin-top: 10px;
	}

	dd {
		margin: 0 0 6px;
	}

	dt {
		font-weight: 700;
		color: #000;
	}

	ul {
		list-style: none;
		margin-top: 10px;
		padding-top: 10px;
		border-top: 1px solid var(--line);
	}

	li {
		padding-left: 12px;
		text-indent: -12px;
	}

	li + li {
		margin-top: 4px;
	}

	li::before {
		content: '';
		display: inline-block;
		width: 4px;
		height: 4px;
		margin-right: 8px;
		border-radius: 50%;
		background: var(--muted);
		vertical-align: 3px;
	}

	li strong {
		color: #000;
		font-weight: 700;
	}

	.desc {
		color: var(--sub);
	}

	.footer {
		display: block;
		width: 64px;
		margin: 24px 0 0 10px;
		color: #c9c9c9;
		transition: color 0.15s;
	}

	.footer:hover {
		color: var(--sub);
	}

	@media (max-width: 640px) {
		.screen {
			padding: 0 0 40px;
			justify-content: flex-start;
		}

		.screen::before {
			background: #fff;
		}

		.container {
			border-radius: 0;
		}
	}

	/* 모바일 — PC 와 같은 내용을 스크롤 없이 한 화면에: 여백·글자를 촘촘하게, 바닥 로고만 숨긴다 */
	@media (max-width: 640px) {
		.screen {
			min-height: 100dvh;
			padding: 0;
			font-size: 14px;
			line-height: 20px;
		}

		.container {
			flex: 1;
			padding: 10px 16px 16px;
		}

		.bar {
			min-height: 32px;
			padding-inline: 0;
		}

		.progress {
			margin: 6px 0 0;
		}

		.top {
			padding: 0 0 14px;
		}

		.top > * {
			margin-top: 14px;
		}

		.seller,
		.seller img {
			height: 22px;
		}

		.total {
			font-size: 22px;
			line-height: 28px;
		}

		.meta {
			font-size: 13px;
		}

		.itinerary + .itinerary {
			margin-top: 8px;
		}

		.flight {
			font-size: 12px;
			line-height: 18px;
		}

		.flight .time {
			font-size: 13px;
		}

		.flight .airline {
			font-size: 11px;
		}

		.bottom {
			padding: 12px 14px;
			border-radius: 14px;
			font-size: 11.5px;
			line-height: 16px;
		}

		.heading {
			gap: 8px;
			font-size: 13px;
			line-height: 18px;
		}

		.heading svg {
			width: 18px;
			height: 18px;
		}

		dl {
			margin-top: 6px;
		}

		dd {
			margin-bottom: 4px;
		}

		ul {
			margin-top: 6px;
			padding-top: 6px;
		}

		li + li {
			margin-top: 2px;
		}

		.footer {
			width: 56px;
			margin: 14px 0 0;
		}
	}
</style>
