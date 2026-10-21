<script>
	import { onMount, tick } from 'svelte';

	let stats = $state(null);
	let file = $state(null);
	let previewUrl = $state('');
	let grayscale = $state(true);
	let loading = $state(false);
	let error = $state('');
	let result = $state(null);
	let selected = $state(0);
	let reveal = $state(50);
	let dragging = $state(false);
	let runId = 0;

	const featured = $derived(result ? result.matches[selected] : null);

	onMount(async () => {
		try {
			const res = await fetch('/api/stats');
			if (res.ok) stats = await res.json();
		} catch {
			// The status line below reports connection problems when a search is attempted.
		}
	});

	function pick(f) {
		if (!f) return;
		if (!f.type.startsWith('image/')) {
			error = 'Choose an image file (JPG, PNG or WebP).';
			return;
		}
		if (previewUrl) URL.revokeObjectURL(previewUrl);
		file = f;
		previewUrl = URL.createObjectURL(f);
		search();
	}

	function onFile(e) {
		const f = e.currentTarget.files?.[0];
		e.currentTarget.value = ''; // lets the same file be chosen twice in a row
		pick(f);
	}

	function onDrop(e) {
		e.preventDefault();
		dragging = false;
		pick(e.dataTransfer?.files?.[0]);
	}

	function onPaste(e) {
		const f = [...(e.clipboardData?.files ?? [])].find((x) => x.type.startsWith('image/'));
		if (f) pick(f);
	}

	function choose(i) {
		selected = i;
		reveal = 50;
	}

	async function search() {
		if (!file) return;
		const id = ++runId;
		loading = true;
		error = '';
		try {
			const body = new FormData();
			body.append('file', file);
			body.append('top_k', '13');
			body.append('grayscale', String(grayscale));

			const res = await fetch('/api/search', { method: 'POST', body });
			const data = await res.json().catch(() => ({}));
			if (id !== runId) return;

			if (!res.ok) {
				result = null;
				error = typeof data.detail === 'string' ? data.detail : `The search failed (error ${res.status}).`;
				return;
			}

			result = data;
			selected = 0;
			reveal = 50;
			await tick();
			const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
			document.getElementById('results')?.scrollIntoView({ block: 'start', behavior: calm ? 'auto' : 'smooth' });
		} catch {
			if (id === runId) error = 'Could not reach the server. Check that the containers are running.';
		} finally {
			if (id === runId) loading = false;
		}
	}
</script>

<svelte:head>
	<title>Old faces</title>
	<meta name="description" content="Find the faces in old photographs that look most like yours." />
</svelte:head>

<svelte:window onpaste={onPaste} />

<main>
	<div class="top">
		<div class="intro">
			<h1>Who in history looks like you?</h1>
			<p class="lede">Upload a portrait and see which faces in old photographs look most like it.</p>

			{#if stats && stats.faces > 0}
				<p class="archive">
					Searching {stats.faces.toLocaleString()} faces from {stats.images_with_faces.toLocaleString()} photographs.
				</p>
			{:else if stats}
				<p class="archive">
					The archive is empty. Download photos with <code>make download</code>, then run <code>make index</code>.
				</p>
			{/if}

			<label class="toggle">
				<input type="checkbox" bind:checked={grayscale} onchange={search} />
				<span>Compare in black and white</span>
			</label>
			<p class="hint">
				Old photographs have no color, so this gives the fairest comparison. Your photo is searched in memory and is
				never saved.
			</p>
		</div>

		<label
			class="frame drop"
			class:dragging
			ondragover={(e) => {
				e.preventDefault();
				dragging = true;
			}}
			ondragleave={() => (dragging = false)}
			ondrop={onDrop}
		>
			<input type="file" accept="image/*" onchange={onFile} />
			<div class="well">
				{#if previewUrl}
					<img src={previewUrl} alt="The photo you chose" />
				{:else}
					<p>Drop a photo here, paste one, or choose a file.</p>
				{/if}
			</div>
			<span class="frame-caption">
				{previewUrl ? 'Choose a different photo' : 'A front-facing portrait works best'}
			</span>
		</label>
	</div>

	<div class="status" aria-live="polite">
		{#if loading}
			<p>Comparing your face with the archive…</p>
		{/if}
		{#if error}
			<p class="error" role="alert">{error}</p>
		{/if}
	</div>

	{#if result && featured}
		<section id="results" class:stale={loading} aria-label="Matches">
			{#if result.faces_in_photo > 1}
				<p class="note">{result.faces_in_photo} faces found in your photo. Using the largest one.</p>
			{/if}

			{#key featured.id}
				<div class="featured">
					<div class="frame">
						<div class="compare develop">
							<img class="layer" src={result.query_face} alt="Your face" />
							<img
								class="layer"
								src={`/api${featured.crop_url}`}
								alt={`Face from the photograph "${featured.title || 'untitled'}"`}
								style:clip-path={`inset(0 ${100 - reveal}% 0 0)`}
							/>
							<div class="handle" style:left={`${reveal}%`}></div>
							<input
								type="range"
								min="0"
								max="100"
								bind:value={reveal}
								aria-label="Slide to compare your face with the face from the old photograph"
							/>
						</div>
						<span class="frame-caption">Slide to compare</span>
					</div>

					<div class="details">
						<h2>{featured.title || 'Untitled photograph'}</h2>
						<dl>
							{#if featured.year}
								<div><dt>Date</dt><dd>{featured.year}</dd></div>
							{/if}
							{#if featured.author}
								<div><dt>Creator</dt><dd>{featured.author}</dd></div>
							{/if}
							{#if featured.license}
								<div><dt>License</dt><dd>{featured.license}</dd></div>
							{/if}
							<div>
								<dt>Similarity</dt>
								<dd>
									<span class="score">{featured.similarity.toFixed(2)}</span>
									<span class="meter" aria-hidden="true">
										<span style:width={`${Math.min(Math.max(featured.similarity / 0.6, 0), 1) * 100}%`}></span>
									</span>
								</dd>
							</div>
						</dl>
						<p class="links">
							<a href={`/api${featured.image_url}`} target="_blank" rel="noopener">View the full photograph</a>
							{#if featured.source_url}
								<a href={featured.source_url} target="_blank" rel="noopener">Open the source page</a>
							{/if}
						</p>
					</div>
				</div>
			{/key}

			{#if result.matches.length > 1}
				<h3>Closest matches</h3>
				<ul class="prints">
					{#each result.matches as m, i (m.id)}
						<li>
							<button
								type="button"
								class="print"
								aria-pressed={i === selected}
								aria-label={`${m.title || 'Untitled photograph'}, similarity ${m.similarity.toFixed(2)}`}
								onclick={() => choose(i)}
							>
								<img src={`/api${m.crop_url}`} alt="" loading="lazy" />
								<span class="cap">
									<span>{m.year || 'Undated'}</span>
									<span class="num">{m.similarity.toFixed(2)}</span>
								</span>
							</button>
						</li>
					{/each}
				</ul>
			{/if}

			<p class="fineprint">
				Similarity is the cosine score from a face-recognition model. Higher means more alike, and above about 0.30 is a
				close resemblance. It is for fun, not for identifying anyone.
			</p>
		</section>
	{/if}
</main>

<style>
	main {
		max-width: 1120px;
		margin: 0 auto;
		padding: clamp(2rem, 6vw, 4.5rem) clamp(16px, 5vw, 48px) 5rem;
	}

	/* Intro and drop zone */
	.top {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 400px);
		gap: clamp(2rem, 5vw, 4rem);
		align-items: start;
	}

	h1 {
		margin: 0 0 1.25rem;
		max-width: 11ch;
		font-family: var(--display);
		font-weight: 400;
		font-size: clamp(2.8rem, 7vw, 4.8rem);
		line-height: 1;
		letter-spacing: -0.01em;
	}

	.lede {
		margin: 0 0 1.5rem;
		max-width: 34rem;
		font-family: var(--serif);
		font-size: 1.2rem;
		line-height: 1.65;
	}

	.archive,
	.hint {
		margin: 0 0 1rem;
		max-width: 34rem;
		color: var(--muted);
		font-size: 0.95rem;
		line-height: 1.55;
	}

	.archive code {
		padding: 1px 6px;
		background: var(--blue-900);
		color: var(--ink);
		font-size: 0.9em;
	}

	.toggle {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		width: fit-content;
		margin: 1.75rem 0 0.5rem;
		cursor: pointer;
	}

	.toggle input {
		width: 1.1rem;
		height: 1.1rem;
		margin: 0;
		accent-color: var(--albumen);
	}

	/* Print mat, used for the drop zone, the comparison and the thumbnails */
	.frame {
		display: block;
		padding: 14px;
		background: var(--print);
		color: var(--print-ink);
	}

	.frame-caption {
		display: block;
		margin-top: 12px;
		font-family: var(--serif);
		font-style: italic;
		font-size: 0.95rem;
	}

	.drop {
		position: relative;
		cursor: pointer;
	}

	.drop:has(input:focus-visible) {
		outline: 3px solid var(--albumen);
		outline-offset: 4px;
	}

	.drop input {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		margin: 0;
		opacity: 0;
		cursor: pointer;
	}

	.well {
		position: relative;
		display: grid;
		place-items: center;
		aspect-ratio: 1;
		padding: 1.5rem;
		overflow: hidden;
		background: var(--blue-900);
		color: var(--muted);
		text-align: center;
		transition: background-color 0.15s;
	}

	.dragging .well {
		background: var(--blue-700);
	}

	.well p {
		margin: 0;
		max-width: 16rem;
	}

	.well img {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	/* Status */
	.status {
		min-height: 1.5rem;
		margin-top: 1.5rem;
	}

	.status p {
		margin: 0;
	}

	.error {
		color: var(--error);
	}

	/* Results */
	#results {
		margin-top: clamp(2.5rem, 6vw, 4rem);
		scroll-margin-top: 1.5rem;
		transition: opacity 0.2s;
	}

	#results.stale {
		opacity: 0.5;
	}

	.note {
		margin: 0 0 1.5rem;
		color: var(--muted);
	}

	.featured {
		display: grid;
		grid-template-columns: minmax(0, 460px) minmax(0, 1fr);
		gap: clamp(1.5rem, 4vw, 3.5rem);
		align-items: start;
	}

	.compare {
		position: relative;
		aspect-ratio: 1;
		overflow: hidden;
		background: var(--blue-900);
	}

	/* The one orchestrated moment: a new match "develops" like a print in the tray. */
	.develop {
		animation: develop 1.2s ease-out both;
	}

	@keyframes develop {
		from {
			filter: grayscale(1) blur(7px) brightness(1.6) contrast(0.5);
		}
		to {
			filter: none;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.develop {
			animation: none;
		}
	}

	.layer {
		position: absolute;
		inset: 0;
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	.handle {
		position: absolute;
		top: 0;
		bottom: 0;
		width: 2px;
		background: var(--print);
		box-shadow: 0 0 0 1px rgb(8 27 51 / 0.5);
		transform: translateX(-1px);
		pointer-events: none;
	}

	.handle::after {
		content: '';
		position: absolute;
		top: 50%;
		left: 50%;
		width: 28px;
		height: 28px;
		border: 2px solid var(--blue-900);
		border-radius: 50%;
		background: var(--print);
		transform: translate(-50%, -50%);
	}

	.compare:has(input:focus-visible) .handle::after {
		outline: 3px solid var(--albumen);
		outline-offset: 2px;
	}

	.compare input {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		margin: 0;
		opacity: 0;
		cursor: ew-resize;
		touch-action: pan-y;
	}

	.details h2 {
		margin: 0 0 1.25rem;
		font-family: var(--display);
		font-weight: 400;
		font-size: clamp(1.8rem, 3.4vw, 2.6rem);
		line-height: 1.1;
		overflow-wrap: anywhere;
	}

	dl {
		display: grid;
		grid-template-columns: max-content minmax(0, 1fr);
		gap: 0.5rem 1.5rem;
		margin: 0 0 1.5rem;
		font-size: 0.95rem;
	}

	dl > div {
		display: contents;
	}

	dt {
		color: var(--muted);
	}

	dd {
		margin: 0;
		overflow-wrap: anywhere;
	}

	.score,
	.num {
		font-variant-numeric: tabular-nums;
	}

	.score {
		margin-right: 0.75rem;
		font-weight: 500;
	}

	.meter {
		display: inline-block;
		width: 120px;
		height: 4px;
		vertical-align: middle;
		background: var(--blue-700);
	}

	.meter > span {
		display: block;
		height: 100%;
		background: var(--albumen);
	}

	.links {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1.5rem;
		margin: 0;
	}

	h3 {
		margin: clamp(2.5rem, 6vw, 3.5rem) 0 0;
		font-family: var(--display);
		font-weight: 400;
		font-size: 1.7rem;
	}

	.prints {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
		gap: 16px;
		margin: 1.25rem 0 0;
		padding: 0;
		list-style: none;
	}

	.print {
		display: block;
		width: 100%;
		padding: 8px 8px 10px;
		border: 0;
		background: var(--print);
		color: var(--print-ink);
		font: inherit;
		text-align: left;
		cursor: pointer;
	}

	.print[aria-pressed='true'] {
		outline: 3px solid var(--albumen);
		outline-offset: 2px;
	}

	.print img {
		display: block;
		width: 100%;
		aspect-ratio: 1;
		object-fit: cover;
	}

	.cap {
		display: flex;
		justify-content: space-between;
		gap: 0.5rem;
		margin-top: 8px;
		font-size: 0.8rem;
	}

	.cap > span:first-child {
		min-width: 0;
		overflow: hidden;
		font-family: var(--serif);
		font-style: italic;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.fineprint {
		max-width: 40rem;
		margin: 3rem 0 0;
		color: var(--muted);
		font-size: 0.85rem;
		line-height: 1.55;
	}

	@media (max-width: 820px) {
		.top,
		.featured {
			grid-template-columns: minmax(0, 1fr);
		}

		.drop {
			max-width: 420px;
		}
	}
</style>
