// Podcasti RSS (Apple/itunes nimeruum) salvestustest. Sama loogika: recorder/webserver.py
const x = (s) => String(s ?? "").replace(/[<>&'"]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" }[c]));
const TZ = "Europe/Tallinn";
export const showSlug = (id) => String(id ?? "muu").replace(/[^\w-]+/g, "-");

function hms(s) {
  s = Math.max(0, Math.round(s || 0));
  return [Math.floor(s / 3600), Math.floor((s % 3600) / 60), s % 60].map((n) => String(n).padStart(2, "0")).join(":");
}
function when(iso) {
  return new Date(iso).toLocaleString("et-EE", { timeZone: TZ, day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

// recs: rec/*.json metaandmed; slug: "koik" või saate slug
export function buildFeed(recs, { base, token, slug }) {
  const all = slug === "koik";
  const items = recs
    .filter((r) => r.key?.startsWith("rec/") && (all || showSlug(r.show_id) === slug))
    .sort((a, b) => b.start.localeCompare(a.start));
  const first = items[0];
  const title = all ? "Raadiosalvestaja" : `${first?.show || "Saade"} (Raadiosalvestaja)`;
  const image = all ? null : items.find((r) => r.thumbnail)?.thumbnail;
  const self = `${base}/feed/${token}/${slug}.xml`;
  const body = items.map((r) => {
    const t = `${all ? r.show + " · " : ""}${when(r.start)}${r.parts > 1 ? ` · osa ${r.part}/${r.parts}` : ""}${r.incomplete ? " (katkestatud)" : ""}`;
    return `<item>
  <title>${x(t)}</title>
  <description>${x([r.title, r.station_name, r.description].filter(Boolean).join(" – "))}</description>
  <guid isPermaLink="false">${x(r.key)}</guid>
  <pubDate>${new Date(r.start).toUTCString()}</pubDate>
  <enclosure url="${x(`${base}/feed/${token}/audio/${r.key}`)}" length="${r.size || 0}" type="audio/mpeg"/>
  <itunes:duration>${hms(r.duration)}</itunes:duration>${r.thumbnail ? `\n  <itunes:image href="${x(r.thumbnail)}"/>` : ""}
</item>`;
  }).join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>${x(title)}</title>
<link>${x(base)}</link>
<atom:link href="${x(self)}" rel="self" type="application/rss+xml"/>
<description>Isiklikud raadiosalvestused – privaatne feed, ära jaga.</description>
<language>et</language>
<itunes:block>Yes</itunes:block>
<itunes:explicit>false</itunes:explicit>${image ? `\n<itunes:image href="${x(image)}"/>\n<image><url>${x(image)}</url><title>${x(title)}</title><link>${x(base)}</link></image>` : ""}
${body}
</channel>
</rss>`;
}
