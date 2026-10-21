// Proxies /api/* to the FastAPI service, so the browser only ever talks to the web app.
// Docker: API_URL=http://api:8000 (set in docker-compose.yml). Local dev: defaults to localhost.
import { env } from '$env/dynamic/private';

const PASS_THROUGH = ['content-type', 'cache-control', 'etag', 'last-modified'];

/** @type {import('./$types').RequestHandler} */
async function proxy({ request, params, url }) {
	const base = (env.API_URL || 'http://localhost:8000').replace(/\/$/, '');
	const target = `${base}/${params.path}${url.search}`;

	const headers = new Headers();
	const contentType = request.headers.get('content-type');
	if (contentType) headers.set('content-type', contentType);

	/** @type {RequestInit & { duplex?: 'half' }} */
	const init = { method: request.method, headers };
	if (request.method !== 'GET' && request.method !== 'HEAD') {
		init.body = request.body;
		init.duplex = 'half'; // required to stream a request body in Node's fetch
	}

	let upstream;
	try {
		upstream = await fetch(target, init);
	} catch {
		return new Response(JSON.stringify({ detail: 'The API is not reachable. Is the api container running?' }), {
			status: 502,
			headers: { 'content-type': 'application/json' }
		});
	}

	const out = new Headers();
	for (const name of PASS_THROUGH) {
		const value = upstream.headers.get(name);
		if (value) out.set(name, value);
	}
	return new Response(upstream.body, { status: upstream.status, headers: out });
}

export const GET = proxy;
export const POST = proxy;
