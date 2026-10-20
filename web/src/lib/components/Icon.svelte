<!-- core-flat 아이콘 — 색은 부모의 --l(면) / --d(선) 를 따른다 -->
<script lang="ts">
	import { icons, type IconName } from '#lib/icons.ts';

	let { name }: { name: IconName } = $props();
</script>

<span class="ico" aria-hidden="true">{@html icons[name]}</span>
