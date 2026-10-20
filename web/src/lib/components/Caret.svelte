<!-- 작은 선 표시 (▾ › × ✓) — DESIGN.md 5번 예외: 직접 그린 선 -->
<script lang="ts">
	let { kind = 'down' }: { kind?: 'down' | 'right' | 'close' | 'check' } = $props();

	const PATHS = {
		down: 'M2 3.5 5 6.5 8 3.5',
		right: 'M3.5 2 6.5 5 3.5 8',
		close: 'M2.5 2.5l5 5M7.5 2.5l-5 5',
		check: 'M2 5.2 4.2 7.4 8 2.8'
	};
</script>

<svg class="caret" viewBox="0 0 10 10" aria-hidden="true"><path d={PATHS[kind]} /></svg>
