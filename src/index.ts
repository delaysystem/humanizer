/**
 * Bodhan Humanizer Pipeline — Cloudflare Worker
 *
 * Implements:
 * - POST /humanize: HTTP API to humanize text via Bodhan back-translation & multi-hop chains
 * - POST /queue: Producer to enqueue humanization tasks
 * - queue: Consumer to process humanization tasks asynchronously
 * - GET /health & GET /: Status and service discovery
 *
 * Adheres to AGENTS.md §1, Cloudflare Workers guidelines, and Rule 1 (no hardcoded keys).
 */

export interface Env {
	MY_QUEUE: Queue;
	INDIC_TRANSLATE_API_KEY?: string;
	BODHAN_API_KEY?: string;
}

interface HumanizeRequest {
	text: string;
	strategy?: 'round-trip' | 'multi-hop' | 'hybrid';
	language?: string;
	chain?: string[];
}

interface BodhanChatCompletionResponse {
	id?: string;
	choices: Array<{
		message: {
			content: string;
			role: string;
		};
		finish_reason?: string;
	}>;
	usage?: {
		prompt_tokens: number;
		completion_tokens: number;
		total_tokens: number;
	};
}

const BODHAN_BASE_URL = 'https://api.bodhan.ai';
const BODHAN_CHAT_PATH = '/v1/chat/completions';
const BODHAN_MODEL = 'indic-translate';

const HYBRID_REPLACEMENTS: Array<[RegExp, string]> = [
	[/\bIn conclusion,\s*/gi, 'Overall, '],
	[/\bFurthermore,\s*/gi, 'Also, '],
	[/\bMoreover,\s*/gi, 'In addition, '],
	[/\bIt is important to note that\s*/gi, 'Note that '],
	[/\bIt is worth noting that\s*/gi, 'Noticeably, '],
	[/\bdelve into\b/gi, 'explore'],
	[/\ba testament to\b/gi, 'proof of'],
];

function applyHybridAdjustments(text: string): string {
	let adjusted = text;
	for (const [pattern, replacement] of HYBRID_REPLACEMENTS) {
		adjusted = adjusted.replace(pattern, replacement);
	}
	return adjusted;
}

function resolveApiKey(env: Env): string {
	const key = env.INDIC_TRANSLATE_API_KEY || env.BODHAN_API_KEY;
	if (!key) {
		throw new Error(
			'INDIC_TRANSLATE_API_KEY (or BODHAN_API_KEY) is not configured in Worker environment secrets.'
		);
	}
	return key;
}

async function translateLeg(
	text: string,
	targetLanguageCode: string,
	apiKey: string,
	script: string = 'native'
): Promise<string> {
	const payload = {
		model: BODHAN_MODEL,
		messages: [{ role: 'user', content: text }],
		target_language_code: targetLanguageCode,
		target_script: script,
	};

	const res = await fetch(`${BODHAN_BASE_URL}${BODHAN_CHAT_PATH}`, {
		method: 'POST',
		headers: {
			Authorization: `Bearer ${apiKey}`,
			'Content-Type': 'application/json',
		},
		body: JSON.stringify(payload),
	});

	if (!res.ok) {
		const errText = await res.text();
		if (res.status === 429) {
			throw new Error(`Bodhan rate limit reached (HTTP 429). Retry later: ${errText}`);
		}
		throw new Error(`Bodhan translation error (HTTP ${res.status}): ${errText}`);
	}

	const data = (await res.json()) as BodhanChatCompletionResponse;
	if (!data.choices || data.choices.length === 0 || !data.choices[0].message) {
		throw new Error('Bodhan returned empty or invalid response format');
	}

	return data.choices[0].message.content;
}

export async function runHumanizerPipeline(
	text: string,
	strategy: 'round-trip' | 'multi-hop' | 'hybrid' = 'round-trip',
	language: string = 'kn',
	chain: string[] = ['hi', 'kn'],
	apiKey: string
): Promise<{
	humanized_text: string;
	strategy: string;
	stages: Array<{ from: string; to: string; text: string }>;
}> {
	const stages: Array<{ from: string; to: string; text: string }> = [];

	if (strategy === 'round-trip') {
		const targetLang = language || 'kn';
		// Step 1: English -> Indic
		const intermediate = await translateLeg(text, targetLang, apiKey, 'native');
		stages.push({ from: 'en', to: targetLang, text: intermediate });

		// Step 2: Indic -> English
		const humanized = await translateLeg(intermediate, 'en', apiKey, 'native');
		stages.push({ from: targetLang, to: 'en', text: humanized });

		return {
			humanized_text: humanized,
			strategy,
			stages,
		};
	} else if (strategy === 'multi-hop' || strategy === 'hybrid') {
		const hops = chain && chain.length > 0 ? chain : ['hi', 'kn'];
		let current = text;
		let prevLang = 'en';

		for (const hop of hops) {
			current = await translateLeg(current, hop, apiKey, 'native');
			stages.push({ from: prevLang, to: hop, text: current });
			prevLang = hop;
		}

		let humanized = await translateLeg(current, 'en', apiKey, 'native');
		stages.push({ from: prevLang, to: 'en', text: humanized });

		if (strategy === 'hybrid') {
			humanized = applyHybridAdjustments(humanized);
			stages.push({ from: 'en', to: 'en_hybrid', text: humanized });
		}

		return {
			humanized_text: humanized,
			strategy,
			stages,
		};
	} else {
		throw new Error(`Unsupported strategy: ${strategy}`);
	}
}

export default {
	async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
		const url = new URL(req.url);

		// CORS Preflight
		if (req.method === 'OPTIONS') {
			return new Response(null, {
				headers: {
					'Access-Control-Allow-Origin': '*',
					'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
					'Access-Control-Allow-Headers': 'Content-Type, Authorization',
				},
			});
		}

		const corsHeaders = {
			'Content-Type': 'application/json',
			'Access-Control-Allow-Origin': '*',
		};

		// GET / and GET /health
		if (req.method === 'GET' && (url.pathname === '/' || url.pathname === '/health')) {
			return new Response(
				JSON.stringify({
					status: 'ok',
					service: 'bodhan-humanizer',
					version: '1.0.0',
					endpoints: {
						'POST /humanize': 'Transform AI text into human-detected text',
						'POST /queue': 'Enqueue text for async batch processing',
					},
					supported_strategies: ['round-trip', 'multi-hop', 'hybrid'],
					supported_languages: ['kn', 'hi', 'te', 'ta', 'mr', 'gu', 'bn', 'pa', 'ml', 'ur'],
				}),
				{ headers: corsHeaders }
			);
		}

		// POST /humanize
		if (req.method === 'POST' && url.pathname === '/humanize') {
			try {
				const apiKey = resolveApiKey(env);
				const body = (await req.json()) as HumanizeRequest;

				if (!body || !body.text || typeof body.text !== 'string' || body.text.trim().length === 0) {
					return new Response(
						JSON.stringify({
							status: 'error',
							error: 'Missing or empty "text" parameter in request body.',
						}),
						{ status: 400, headers: corsHeaders }
					);
				}

				const text = body.text.trim();
				const strategy = body.strategy || 'round-trip';
				const language = body.language || 'kn';
				const chain = body.chain || ['hi', 'kn'];

				const startTime = Date.now();
				const result = await runHumanizerPipeline(text, strategy, language, chain, apiKey);
				const durationMs = Date.now() - startTime;

				return new Response(
					JSON.stringify({
						status: 'success',
						strategy: result.strategy,
						duration_ms: durationMs,
						original_text: text,
						humanized_text: result.humanized_text,
						word_count_original: text.split(/\s+/).length,
						word_count_humanized: result.humanized_text.split(/\s+/).length,
						stages: result.stages,
					}),
					{ status: 200, headers: corsHeaders }
				);
			} catch (err: unknown) {
				const message = err instanceof Error ? err.message : String(err);
				return new Response(
					JSON.stringify({
						status: 'error',
						error: message,
					}),
					{ status: 500, headers: corsHeaders }
				);
			}
		}

		// POST /queue (enqueue for async batch worker)
		if (req.method === 'POST' && url.pathname === '/queue') {
			try {
				const body = (await req.json()) as HumanizeRequest;
				if (!body || !body.text) {
					return new Response(
						JSON.stringify({ status: 'error', error: 'Missing "text" field' }),
						{ status: 400, headers: corsHeaders }
					);
				}

				if (!env.MY_QUEUE) {
					return new Response(
						JSON.stringify({ status: 'error', error: 'Queue binding MY_QUEUE is not available' }),
						{ status: 500, headers: corsHeaders }
					);
				}

				await env.MY_QUEUE.send({
					id: crypto.randomUUID(),
					text: body.text,
					strategy: body.strategy || 'round-trip',
					language: body.language || 'kn',
					enqueued_at: new Date().toISOString(),
				});

				return new Response(
					JSON.stringify({ status: 'success', message: 'Job enqueued successfully' }),
					{ status: 202, headers: corsHeaders }
				);
			} catch (err: unknown) {
				const message = err instanceof Error ? err.message : String(err);
				return new Response(
					JSON.stringify({ status: 'error', error: message }),
					{ status: 500, headers: corsHeaders }
				);
			}
		}

		return new Response(
			JSON.stringify({ status: 'error', error: 'Not Found' }),
			{ status: 404, headers: corsHeaders }
		);
	},

	// Cloudflare Queue Consumer for batch operations
	async queue(batch: MessageBatch<any>, env: Env): Promise<void> {
		const apiKey = resolveApiKey(env);
		for (const message of batch.messages) {
			try {
				const item = message.body;
				if (item && item.text) {
					const result = await runHumanizerPipeline(
						item.text,
						item.strategy || 'round-trip',
						item.language || 'kn',
						item.chain || ['hi', 'kn'],
						apiKey
					);
					console.log(
						`[Queue Consumer] Successfully humanized message ${message.id}: ${result.humanized_text.slice(0, 80)}...`
					);
					message.ack();
				} else {
					message.ack();
				}
			} catch (err) {
				console.error(`[Queue Consumer] Failed processing message ${message.id}:`, err);
				message.retry();
			}
		}
	},
} satisfies ExportedHandler<Env, Error>;
