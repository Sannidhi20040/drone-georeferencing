// Minimal `--flag value` / `--flag` parser for the scripts in this folder.
export function parseArgs(argv, defaults = {}) {
    const out = { ...defaults };
    for (let i = 0; i < argv.length; i++) {
        if (!argv[i].startsWith('--')) continue;
        const key = argv[i].slice(2);
        const next = argv[i + 1];
        if (next === undefined || next.startsWith('--')) {
            out[key] = true;
        } else {
            out[key] = Number.isFinite(Number(next)) && next.trim() !== '' ? Number(next) : next;
            i++;
        }
    }
    return out;
}
