// Bookkeeping for cached reads of data that belongs to a signed-in user.
// Pure: the request function and the cache write are passed in, so the rules
// below can be tested without a browser.
//
// - A response that arrives after the session ended is dropped.
// - A resource reported gone or forbidden stays denied until a later read of
//   it succeeds; a network failure in between does not bring the cached copy back.
// - Of two overlapping reads of one resource, the one started later decides.
// - A read that begins while a prefetch of the same resource is in flight
//   joins it: one request, and the reader delivers the result.
// - A prefetch nobody joined writes to the cache only on success, and only if
//   no other read of the resource has begun since it started. (A cache write
//   makes SWR discard a read already in flight, so it must not race a newer one.)

export const isGone = (error: unknown) => [401, 403, 404].includes((error as { status?: number } | undefined)?.status ?? 0);

export interface Reads {
    read: <T>(url: string, pick: (body: unknown) => T) => Promise<T>;
    prefetch: <T>(url: string, pick: (body: unknown) => T, write: (url: string, data: T) => void) => Promise<void>;
    // The denial standing against this resource, if any.
    denied: (url: string) => Error | null;
    // The session ended: forget everything and drop responses still in flight.
    end: () => void;
}

type Started = { data: unknown; started: number };

/**
 * `watch.denied` is told each time a denial is recorded against a resource, whoever asked (a hook or a
 * prefetch), so anything else kept for that resource can be dropped with it. `watch.changed` is told
 * whenever the answer of `denied()` may have changed (recorded, lifted, or the session ended): a view that
 * shows a denial cannot rely on its own request to learn of either.
 */
export type ReadsWatch = { denied?: (url: string) => void; changed?: () => void };
export function createReads(request: (url: string) => Promise<unknown>, watch: ReadsWatch = {}): Reads {
    let session = 0;
    let clock = 0;
    // Start time of the newest read of each resource that has begun, and that has settled.
    const begun = new Map<string, number>();
    const settled = new Map<string, number>();
    const denials = new Map<string, Error>();
    // Prefetches in flight, and whether a read has joined them.
    const warming = new Map<string, { result: Promise<Started>; joined: boolean }>();

    async function start(url: string, pick: (body: unknown) => unknown): Promise<Started> {
        const started = ++clock;
        const mine = session;
        begun.set(url, started);
        const newest = () => (settled.get(url) ?? 0) < started;
        try {
            const data = pick(await request(url));
            if (mine !== session) throw new Error("The session ended before this response arrived");
            if (newest()) {
                settled.set(url, started);
                if (denials.delete(url)) watch.changed?.();
            }
            return { data, started };
        } catch (error) {
            if (mine === session && isGone(error) && newest()) {
                settled.set(url, started);
                denials.set(url, error as Error);
                watch.denied?.(url);
                watch.changed?.();
            }
            throw error;
        }
    }

    return {
        read: async <T,>(url: string, pick: (body: unknown) => T) => {
            const shared = warming.get(url);
            if (shared) {
                shared.joined = true;
                return (await shared.result).data as T;
            }
            return (await start(url, pick)).data as T;
        },
        prefetch: async (url, pick, write) => {
            if (warming.has(url)) return;
            const entry = { result: start(url, pick), joined: false };
            warming.set(url, entry);
            try {
                const { data, started } = await entry.result;
                if (!entry.joined && begun.get(url) === started && settled.get(url) === started) write(url, data as ReturnType<typeof pick>);
            } catch {
                // A prefetch that fails changes nothing; the real read reports the error.
            } finally {
                if (warming.get(url) === entry) warming.delete(url);
            }
        },
        denied: url => denials.get(url) ?? null,
        end: () => {
            session++;
            begun.clear();
            settled.clear();
            const any = denials.size > 0;
            denials.clear();
            warming.clear();
            if (any) watch.changed?.();
        },
    };
}
