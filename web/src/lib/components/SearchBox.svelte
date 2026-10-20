<!--
  항공편 검색 상자.
    [서울 ▾ / ICN, GMP (모든 공항)] | [도쿄 ▾ / NRT 도착]   [📅 10.30.금] [📅 11.02.월]   ◉ 직항만
  넷 다 선택 사항이고, 검색 버튼 없이 고를 때마다 onchange 로 바로 다시 검색한다.
    출발지·도착지  자동완성 — 검색 칸 + 최근 검색·국내 출발지/인기 도착지 칩,
                   입력하면 결과 목록 (특가 수·최저가). 모바일은 전체 화면.
    날짜    가격 달력 — 특가 있는 날에만 최저가
  고를 목록(도착지 600여 곳·날짜별 최저가, 60KB)은 HTML 에 넣지 않고 검색 상자에 손이 가면
  (마우스를 올리거나 누르거나 포커스) 그때 받는다. 조건이 바뀌면 다음에 열 때 다시 받는다.
  왕복·성인 1명·일반석만 모으므로 탭·인원·좌석 선택은 두지 않는다.
  판은 화면 기준(fixed)으로 칸 아래에 두고, 640px 이하는 아래에서 올라오는 시트.
-->
<script lang="ts">
	import Caret from './Caret.svelte';
	import Icon from './Icon.svelte';
	import PriceCalendar from './PriceCalendar.svelte';
	import { cityName, dotDay, shortWon } from '#lib/format.ts';
	import { apiQuery } from '#lib/search.ts';
	import type { Facets, SearchFilters } from '#lib/types.ts';

	let {
		filters,
		destinationName = '',
		onchange,
		directOnly = $bindable(false)
	}: {
		filters: SearchFilters;
		destinationName?: string; // 고른 도착지 이름 (목록을 받기 전에도 칸에 보이게)
		onchange: (next: SearchFilters) => void;
		directOnly?: boolean;
	} = $props();

	// 고를 목록 — 처음 손이 갈 때 받는다
	const EMPTY: Facets = { origin: [], destination: [], departure_date: [], return_date: [] };
	let facets = $state<Facets>(EMPTY);
	let loadedFor = $state<string | null>(null);
	const loading = $derived(loadedFor === null);
	let pending: string | null = null;
	function loadFacets() {
		const q = apiQuery(filters);
		if (loadedFor === q || pending === q) return;
		pending = q;
		fetch(`/api/deals/facets?${q}`)
			.then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
			.then((f: Facets) => {
				if (pending !== q) return;
				facets = f;
				loadedFor = q;
			})
			.catch(() => {})
			.finally(() => pending === q && (pending = null));
	}

	type Key = keyof SearchFilters;
	let openKey = $state<Key | ''>('');
	let pos = $state({ top: 0, left: 0, width: 0 });
	let query = $state('');

	// 출발 도시 → 공항 (여러 공항을 묶은 도시만)
	const CITY_AIRPORTS: Record<string, string> = { SEL: 'ICN, GMP' };

	const destName = $derived(
		filters.destination
			? (facets.destination.find((f) => f.value === filters.destination)?.name ||
					destinationName ||
					filters.destination)
			: ''
	);
	const label = (key: 'origin' | 'destination', code: string) =>
		key === 'origin' ? cityName(code) : (facets.destination.find((f) => f.value === code)?.name ?? code);
	// 검색 결과 — 이름·코드에 글자가 들어간 것
	const matches = $derived.by(() => {
		if (openKey !== 'origin' && openKey !== 'destination') return [];
		const q = query.trim().toLowerCase();
		if (!q) return [];
		return facets[openKey]
			.filter((f) => label(openKey as 'origin' | 'destination', f.value).toLowerCase().includes(q) || f.value.toLowerCase().includes(q))
			.slice(0, 80);
	});
	// 도착지 지역 — 나라 코드로 묶고, 지역마다 특가가 많은 순 상위 PER_REGION 곳
	const PER_REGION = 9;
	const REGIONS: [string, string[]][] = [
		['일본', ['JP']],
		['중국', ['CN']],
		['대만·홍콩·마카오', ['TW', 'HK', 'MO']],
		['동남아시아', ['TH', 'VN', 'PH', 'SG', 'MY', 'ID', 'KH', 'LA', 'MM', 'BN']],
		['괌·사이판·대양주', ['GU', 'MP', 'AU', 'NZ', 'FJ', 'PW', 'PG', 'NC']],
		['미주', ['US', 'CA', 'MX', 'BR', 'AR', 'CL', 'PE']],
		['유럽', ['GB', 'FR', 'DE', 'IT', 'ES', 'NL', 'CH', 'AT', 'CZ', 'PL', 'HU', 'PT', 'GR', 'TR', 'DK', 'SE', 'NO', 'FI', 'IE', 'BE', 'RU', 'HR', 'RO']]
	];
	const regions = $derived.by(() => {
		const out = REGIONS.map(([name, codes]) => ({
			name,
			items: facets.destination.filter((f) => f.country && codes.includes(f.country)).slice(0, PER_REGION)
		}));
		const listed = new Set(REGIONS.flatMap(([, c]) => c));
		out.push({ name: '기타', items: facets.destination.filter((f) => !f.country || !listed.has(f.country)).slice(0, PER_REGION) });
		return out.filter((r) => r.items.length);
	});
	// 같은 이름이 둘 이상이면 (타이베이 TPE·TSA) 공항 코드를 붙여 구분
	const dupNames = $derived.by(() => {
		const seen = new Map<string, number>();
		for (const f of facets.destination) seen.set(f.name ?? f.value, (seen.get(f.name ?? f.value) ?? 0) + 1);
		return new Set([...seen].filter(([, n]) => n > 1).map(([name]) => name));
	});

	// 최근 검색 — 이 브라우저에만 (localStorage, 못 쓰면 그냥 없음)
	const RECENT_MAX = 6;
	let recent = $state<{ origin: string[]; destination: string[] }>({ origin: [], destination: [] });
	$effect(() => {
		try {
			recent = JSON.parse(localStorage.getItem('recent-search') ?? '') ?? recent;
		} catch {
			/* 처음이거나 저장소를 못 씀 */
		}
	});
	function remember(key: 'origin' | 'destination', code: string) {
		recent[key] = [code, ...recent[key].filter((c) => c !== code)].slice(0, RECENT_MAX);
		try {
			localStorage.setItem('recent-search', JSON.stringify(recent));
		} catch {
			/* 저장 못 해도 검색은 된다 */
		}
	}
	const known = (key: 'origin' | 'destination', code: string) => facets[key].some((f) => f.value === code);
	const preview = (count: number, min: number) => `${count.toLocaleString('ko-KR')}개 · ${shortWon(min)}~`;

	// 판이 열려 있는 동안 뒤 페이지가 스크롤되지 않게
	$effect(() => {
		if (!openKey) return;
		const { overflow } = document.body.style;
		document.body.style.overflow = 'hidden';
		return () => {
			document.body.style.overflow = overflow;
		};
	});

	// 판이 body 로 옮겨져 autofocus 가 안 먹으므로, 그려진 다음 직접 포커스
	function focusNow(node: HTMLInputElement) {
		requestAnimationFrame(() => node.focus({ preventScroll: true }));
	}

	function portal(node: HTMLElement) {
		document.body.appendChild(node);
		return { destroy: () => node.remove() };
	}

	function toggle(key: Key, el: HTMLElement) {
		if (openKey === key) return (openKey = '');
		loadFacets();
		const r = el.getBoundingClientRect();
		const width = Math.max(r.width, key.endsWith('_date') ? 340 : 400);
		pos = { top: r.bottom + 6, left: Math.max(8, Math.min(r.left, innerWidth - width - 8)), width };
		query = '';
		openKey = key;
	}

	function set(key: Key, value: string) {
		if (value && (key === 'origin' || key === 'destination')) remember(key, value);
		const next = { ...filters, [key]: value };
		// 오는 날은 가는 날 뒤여야 한다
		if (key === 'departure_date' && next.return_date && value && next.return_date <= value) next.return_date = '';
		openKey = '';
		onchange(next);
	}

	function clear(e: Event, key: Key) {
		e.stopPropagation();
		set(key, '');
	}
</script>

<svelte:window
	onkeydown={(e) => e.key === 'Escape' && openKey && (openKey = '')}
	onresize={() => openKey && (openKey = '')}
/>

<section class="box" aria-label="항공편 검색" onpointerenter={loadFacets} onfocusin={loadFacets}>
	<div class="panel-row">
		<!-- 출발지 · 도착지 -->
		<div class="routes">
			<button
				type="button"
				class="city start"
				class:on={!!filters.origin}
				aria-haspopup="listbox"
				aria-expanded={openKey === 'origin'}
				onclick={(e) => toggle('origin', e.currentTarget)}
			>
				<i class="name">
					{filters.origin ? cityName(filters.origin) : '출발지'}
					<Caret />
				</i>
				<span class="airport">
					{#if filters.origin}
						<b>{CITY_AIRPORTS[filters.origin] ?? filters.origin}</b>{CITY_AIRPORTS[filters.origin] ? '(모든 공항)' : '출발'}
					{:else}모든 출발지{/if}
				</span>
				{#if filters.origin}
					<span class="x" role="button" tabindex="-1" aria-label="출발지 지우기" onclick={(e) => clear(e, 'origin')} onkeydown={() => {}}><Caret kind="close" /></span>
				{/if}
			</button>

			<button
				type="button"
				class="city end"
				class:on={!!filters.destination}
				aria-haspopup="listbox"
				aria-expanded={openKey === 'destination'}
				onclick={(e) => toggle('destination', e.currentTarget)}
			>
				<i class="name">
					{destName || '도착지'}
					<Caret />
				</i>
				<span class="airport">
					{#if filters.destination}<b>{filters.destination}</b>도착{:else}도시, 공항 검색{/if}
				</span>
				{#if filters.destination}
					<span class="x" role="button" tabindex="-1" aria-label="도착지 지우기" onclick={(e) => clear(e, 'destination')} onkeydown={() => {}}><Caret kind="close" /></span>
				{/if}
			</button>
		</div>

		<!-- 가는 날 · 오는 날 -->
		<div class="options">
			{#each [['departure_date', '가는 날'], ['return_date', '오는 날']] as [key, label] (key)}
				{@const k = key as Key}
				<button
					type="button"
					class="option"
					class:on={!!filters[k]}
					aria-expanded={openKey === k}
					aria-label="{label} {filters[k] ? dotDay(filters[k]) : '전체'}"
					onclick={(e) => toggle(k, e.currentTarget)}
				>
					<svg class="cal" viewBox="0 0 16 16" aria-hidden="true">
						<path
							fill-rule="evenodd"
							d="M5.333 1.5a.5.5 0 01.5.5v.833h4.334V2a.5.5 0 011 0v.833h2.5c.644 0 1.166.523 1.166 1.167v9c0 .644-.522 1.167-1.166 1.167H2.333A1.167 1.167 0 011.167 13V4c0-.644.522-1.167 1.166-1.167h2.5V2a.5.5 0 01.5-.5zm8.5 5H2.167V13c0 .092.074.167.166.167h11.334a.167.167 0 00.166-.167V6.5z"
						/>
					</svg>
					<span class="num">{filters[k] ? dotDay(filters[k]) : label}</span>
					{#if filters[k]}
						<span class="x" role="button" tabindex="-1" aria-label="{label} 지우기" onclick={(e) => clear(e, k)} onkeydown={() => {}}><Caret kind="close" /></span>
					{/if}
				</button>
			{/each}
		</div>

		<!-- 직항만 -->
		<button type="button" role="checkbox" class="direct" aria-checked={directOnly} onclick={() => (directOnly = !directOnly)}>
			<svg viewBox="0 0 16 16" aria-hidden="true">
				<circle cx="7.9" cy="7.9" r="7.9" />
				<path d="M4.24 7.53l2.56 2.56 4.76-4.75" />
			</svg>
			직항만
		</button>
	</div>
</section>

{#if openKey}
	<div use:portal>
		<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
		<div class="backdrop" onclick={() => (openKey = '')}></div>
		<div
			class="sheet"
			class:cityModal={openKey === 'origin' || openKey === 'destination'}
			role="dialog"
			aria-modal="true"
			aria-label={openKey === 'origin' ? '출발지 선택' : openKey === 'destination' ? '도착지 선택' : '날짜 선택'}
			style:top="{pos.top}px"
			style:left="{pos.left}px"
			style:width="{pos.width}px"
		>
			<div class="handle" aria-hidden="true"></div>
			{#if loading}
				<p class="loading" aria-live="polite"><span class="sk"></span><span class="sk"></span><span class="sk"></span></p>
			{:else if openKey === 'origin' || openKey === 'destination'}
				{@const k = openKey}
				<div class="picker">
					<div class="query">
						<button type="button" class="back" aria-label="이전" onclick={() => (openKey = '')}>
							<Caret kind="right" />
						</button>
						<label class="search-field">
							<Icon name="search" />
							<input
								type="search"
								bind:value={query}
								use:focusNow
								placeholder="국가, 도시, 공항명 검색"
								aria-label="{k === 'origin' ? '출발지' : '도착지'} 검색"
								autocomplete="off"
								enterkeyhint="search"
								onkeydown={(e) => e.key === 'Enter' && matches[0] && (e.preventDefault(), set(k, matches[0].value))}
							/>
							{#if query}
								<button type="button" class="clear" aria-label="검색어 지우기" onclick={() => (query = '')}>
									<Caret kind="close" />
								</button>
							{/if}
						</label>
					</div>

					{#if query}
						<ul role="listbox" aria-label="{k === 'origin' ? '출발지' : '도착지'} 검색 결과">
							{#each matches as f (f.value)}
								<li role="option" aria-selected={f.value === filters[k]} onclick={() => set(k, f.value)} onkeydown={() => {}}>
									<span>{label(k, f.value)} <i>{k === 'origin' ? (CITY_AIRPORTS[f.value] ?? f.value) : f.value}</i></span>
									<small class="num">{preview(f.count, f.min_price)}</small>
								</li>
							{:else}
								<li class="none" role="presentation">찾는 {k === 'origin' ? '출발지' : '도착지'}가 없어요</li>
							{/each}
						</ul>
					{:else}
						<div class="heading">
							<b>{k === 'origin' ? '출발지' : '주요 도시'}</b>
							<button type="button" class="all" aria-pressed={!filters[k]} onclick={() => set(k, '')}>
								{k === 'origin' ? '모든 출발지' : '모든 도착지'}
							</button>
						</div>
						{#if recent[k].some((c) => known(k, c))}
							<p class="category">최근 검색</p>
							<div class="cities">
								{#each recent[k].filter((c) => known(k, c)).slice(0, 3) as code (code)}
									<button type="button" class="city-btn" aria-pressed={code === filters[k]} onclick={() => set(k, code)}>
										{label(k, code)}
									</button>
								{/each}
							</div>
						{/if}
						{#if k === 'origin'}
							<p class="category">국내</p>
							<div class="cities">
								{#each facets.origin as f (f.value)}
									<button type="button" class="city-btn" aria-pressed={f.value === filters.origin} onclick={() => set('origin', f.value)}>
										{label('origin', f.value)}
									</button>
								{/each}
							</div>
						{:else}
							{#each regions as region (region.name)}
								<p class="category">{region.name}</p>
								<div class="cities">
									{#each region.items as f (f.value)}
										<button type="button" class="city-btn" aria-pressed={f.value === filters.destination} onclick={() => set('destination', f.value)}>
											{f.name ?? f.value}{#if dupNames.has(f.name ?? f.value)}<i>{f.value}</i>{/if}
										</button>
									{/each}
								</div>
							{/each}
						{/if}
					{/if}
				</div>
			{:else}
				<p class="title">{openKey === 'departure_date' ? '가는 날' : '오는 날'}</p>
				<PriceCalendar
					days={facets[openKey]}
					value={filters[openKey]}
					min={openKey === 'return_date' ? filters.departure_date : ''}
					onpick={(d) => set(openKey as Key, d)}
				/>
			{/if}
		</div>
	</div>
{/if}

<style>
	/* 목록을 받는 동안 — 줄 모양 자리 */
	.loading {
		display: grid;
		gap: 10px;
		padding: 18px 16px;
	}

	.loading .sk {
		height: 36px;
		border-radius: 10px;
	}

	/* 검색 상자 — 흰 판, 옅은 그림자 */
	/* 양옆 여백은 아래 목록(.wrap)과 같게 — 폭이 좁아도 --gut 만큼 띄운다 */
	.box {
		width: calc(100% - 2 * var(--gut));
		max-width: calc(var(--max) - 2 * var(--gut));
		margin: 8px auto 0;
		padding: 14px 20px 18px;
		border-radius: 14px;
		background: #fff;
		box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.05), 0 2px 10px rgba(0, 0, 0, 0.05);
	}



	.panel-row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px 16px;
	}

	/* 출발지 · 도착지 */
	.routes {
		position: relative;
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
		flex: 1 1 380px;
		min-width: 0;
	}

	.city {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 2px;
		min-width: 0;
		padding: 6px 32px 6px 0;
		border: 0;
		background: none;
		text-align: left;
		cursor: pointer;
	}

	/* 출발지 | 도착지 — 가운데 세로 구분선 */
	.city.end {
		padding: 6px 28px 6px 20px;
		border-left: 1px solid var(--line);
	}

	.name {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		max-width: 100%;
		font-size: 17px;
		font-style: normal;
		font-weight: 600;
		line-height: 22px;
		letter-spacing: -0.3px;
		white-space: nowrap;
	}

	.city:not(.on) .name {
		color: var(--sub);
	}

	.name :global(.caret) {
		color: var(--muted);
	}

	.airport {
		max-width: 100%;
		overflow: hidden;
		color: var(--sub);
		font-size: 13px;
		white-space: nowrap;
		text-overflow: ellipsis;
	}

	.airport b {
		margin-right: 4px;
		color: var(--pt);
		font-weight: 500;
	}


	/* 날짜 — 회색 칸 */
	.options {
		display: flex;
		flex: 1 1 300px;
		gap: 6px;
	}

	.option {
		flex: 1;
		display: flex;
		align-items: center;
		gap: 6px;
		min-width: 0;
		height: 48px;
		padding: 0 12px 0 16px;
		border: 0;
		border-radius: 8px;
		background: var(--hover);
		color: var(--sub);
		font-size: 15px;
		font-weight: 600;
		letter-spacing: -0.3px;
		white-space: nowrap;
		cursor: pointer;
		transition: background 0.15s;
	}

	.option:hover {
		background: var(--el);
	}

	.option.on {
		color: #000;
	}

	.option span:not(.x) {
		flex: 1;
		text-align: left;
	}

	.cal {
		flex: none;
		width: 16px;
		height: 16px;
		fill: currentColor;
	}

	/* 직항만 — 둥근 체크 */
	.direct {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		height: 32px;
		padding: 0;
		border: 0;
		background: none;
		font-size: 14px;
		font-weight: 600;
		white-space: nowrap;
		cursor: pointer;
	}

	.direct svg {
		width: 18px;
		height: 18px;
	}

	.direct circle {
		fill: var(--line);
		transition: fill 0.15s;
	}

	.direct path {
		fill: none;
		stroke: #fff;
		stroke-width: 1.4;
	}

	.direct[aria-checked='true'] circle {
		fill: var(--pt);
	}

	/* 지우기 × */
	.x {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		flex: none;
		width: 24px;
		height: 24px;
		border-radius: 999px;
		color: var(--sub);
	}

	.city .x {
		position: absolute;
		top: 50%;
		right: 0;
		margin-top: -12px;
	}

	.city.start .x {
		right: 6px;
	}

	.x:hover {
		background: rgba(0, 0, 0, 0.06);
		color: #000;
	}

	/* 판 */
	.backdrop {
		position: fixed;
		inset: 0;
		z-index: 100;
	}

	.sheet {
		position: fixed;
		z-index: 101;
		max-height: min(460px, 64dvh);
		overflow-y: auto;
		overscroll-behavior: contain;
		padding: 6px;
		border-radius: 14px;
		background: #fff;
		box-shadow: var(--float-shadow);
		animation: drop 0.18s var(--ease);
	}

	.handle,
	.title {
		display: none;
	}

	/* 출발지·도착지 고르기 — 자동완성 */
	/* 검색 칸 — 위에 붙고, 아래 칩 목록과 옅은 선으로 나눈다 */
	.query {
		position: sticky;
		top: -6px;
		z-index: 1;
		display: flex;
		align-items: center;
		gap: 4px;
		margin: -6px -6px 6px;
		padding: 10px 10px 12px;
		border-bottom: 1px solid var(--el);
		background: #fff;
	}

	.search-field {
		position: relative;
		flex: 1;
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
		height: 48px;
		padding: 0 6px 0 14px;
		border-radius: 12px;
		background: var(--el);
		cursor: text;
		transition:
			background 0.15s,
			box-shadow 0.15s;
	}

	.search-field:focus-within {
		background: #fff;
		box-shadow: inset 0 0 0 2px var(--ink);
	}

	.search-field :global(.ico) {
		--l: #c5c7cc;
		--d: #6b6f76;
	}

	.search-field:focus-within :global(.ico) {
		--d: var(--ink);
	}

	.search-field :global(.ico svg) {
		width: 18px;
		height: 18px;
	}

	.search-field input {
		flex: 1;
		min-width: 0;
		height: 100%;
		border: 0;
		background: none;
		font-size: 16px; /* 16px 미만이면 iOS 가 입력할 때 화면을 확대한다 */
		font-weight: 500;
		letter-spacing: -0.2px;
		outline: none;
		-webkit-appearance: none;
		appearance: none;
	}

	.search-field input::placeholder {
		color: var(--muted);
	}

	.search-field input::-webkit-search-cancel-button {
		display: none; /* 브라우저 기본 ✕ 대신 우리 지우기 버튼 */
	}

	.search-field .clear {
		width: 28px;
		height: 28px;
		background: var(--line);
		color: #fff;
	}

	.search-field .clear:hover {
		background: var(--sub);
	}

	.search-field .clear :global(.caret) {
		width: 10px;
		height: 10px;
		stroke-width: 2.2;
	}

	.back,
	.clear {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		flex: none;
		width: 36px;
		height: 36px;
		border: 0;
		border-radius: 999px;
		background: none;
		color: var(--sub);
		cursor: pointer;
	}

	.back {
		display: none; /* 모바일 전체 화면에서만 */
		transform: rotate(180deg);
	}

	.back :global(.caret),
	.clear :global(.caret) {
		width: 13px;
		height: 13px;
	}


	.heading {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 8px 8px 0;
	}

	.heading b {
		font-size: 16px;
		font-weight: 700;
	}

	.all {
		height: 30px;
		padding: 0 12px;
		border: 0;
		border-radius: 999px;
		background: var(--el);
		color: var(--sub);
		font-size: 13px;
		font-weight: 600;
		cursor: pointer;
	}

	.all[aria-pressed='true'] {
		background: var(--ptBg);
		color: var(--pt);
	}

	/* 도시 버튼 — 테두리, 한 줄에 3개 */
	.cities {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 6px;
		padding: 0 8px 4px;
	}

	.city-btn {
		height: 42px;
		padding: 0 6px;
		overflow: hidden;
		border: 1px solid var(--line);
		border-radius: 10px;
		background: #fff;
		font-size: 14px;
		font-weight: 500;
		white-space: nowrap;
		text-overflow: ellipsis;
		cursor: pointer;
		transition:
			border-color 0.15s,
			background 0.15s,
			transform 0.1s;
	}

	.city-btn i {
		margin-left: 3px;
		color: var(--muted);
		font-size: 11px;
		font-style: normal;
	}

	.city-btn:hover {
		border-color: var(--muted);
	}

	.city-btn:active {
		transform: scale(0.97);
	}

	.city-btn[aria-pressed='true'] {
		border-color: var(--pt);
		background: var(--ptBg);
		color: var(--pt);
		font-weight: 600;
	}

	.category {
		padding: 12px 8px 8px;
		color: var(--sub);
		font-size: 13px;
		font-weight: 600;
	}









	ul {
		list-style: none;
	}

	li {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 9px 12px;
		border-radius: 8px;
		font-size: 14px;
		cursor: pointer;
	}

	li:hover {
		background: var(--hover);
	}

	li span {
		flex: 1;
		min-width: 0;
	}

	li i {
		margin-left: 4px;
		color: var(--muted);
		font-size: 12px;
		font-style: normal;
	}

	li small {
		color: var(--muted);
		font-size: 12px;
		white-space: nowrap;
	}

	li[aria-selected='true'] {
		background: var(--ptBg);
		color: var(--pt);
		font-weight: 600;
	}

	li.none {
		justify-content: center;
		color: var(--muted);
		cursor: default;
	}

	@keyframes drop {
		from {
			opacity: 0;
			transform: translateY(-4px);
		}
	}

	@keyframes sheet {
		from {
			transform: translateY(100%);
		}
	}

	@media (max-width: 640px) {
		.box {
			margin-top: 4px;
			padding: 12px 16px 14px;
		}

		.routes,
		.options {
			flex-basis: 100%;
		}

		.backdrop {
			background: rgba(0, 0, 0, 0.32);
		}

		.sheet {
			top: auto !important;
			left: 0 !important;
			right: 0;
			bottom: 0;
			width: auto !important;
			max-height: 72dvh;
			padding: 0 12px calc(16px + env(safe-area-inset-bottom));
			border-radius: 22px 22px 0 0;
			animation: sheet 0.3s var(--ease);
		}

		.handle {
			display: block;
			width: 36px;
			height: 4px;
			margin: 8px auto 4px;
			border-radius: 999px;
			background: var(--line);
		}

		.title {
			display: block;
			padding: 8px 12px 6px;
			font-size: 17px;
			font-weight: 700;
		}


		.sheet.cityModal {
			top: 0 !important;
			max-height: none;
			height: 100dvh;
			padding: 0 12px calc(16px + env(safe-area-inset-bottom));
			border-radius: 0;
			animation: rise 0.22s var(--ease);
		}

		.sheet.cityModal .handle,
		.sheet.cityModal .title {
			display: none;
		}

		.sheet.cityModal .query {
			top: 0;
			margin: 0 -12px 4px;
			padding: 10px 12px;
		}

		.back {
			display: inline-flex;
		}
	}

	@keyframes rise {
		from {
			opacity: 0;
			transform: translateY(8px);
		}
	}
</style>
