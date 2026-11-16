// Builds the short description shown when hovering an event.
import cameo from './cameo.json';

const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];

// Hotspots carry a CAMEO root code ("19"); links carry the more specific base code ("193").
export function actionLabel(item) {
  const code = item?.code || item?.event_code;
  if (!code) return null;
  return cameo[String(code).slice(0, 3)] || cameo[String(code).slice(0, 2)] || null;
}

export function sourceDomain(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return null;
  }
}

// Many article URLs end in a readable slug; use it when the ETL found no headline.
export function slugHeadline(url) {
  let path;
  try {
    path = decodeURIComponent(new URL(url).pathname);
  } catch {
    return null;
  }
  const segments = path.split('/').filter(Boolean).reverse();
  for (const segment of segments) {
    const words = segment
      .replace(/\.(html?|php|aspx?|cms)$/i, '')
      .split(/[-_]+/)
      .filter((word) => /[a-z]/i.test(word) && !/^\d/.test(word));
    if (words.length >= 4) {
      const text = words.join(' ');
      return text.charAt(0).toUpperCase() + text.slice(1);
    }
  }
  return null;
}

function toneLabel(tone) {
  if (tone <= -5) return 'very negative';
  if (tone < -1) return 'negative';
  if (tone <= 1) return 'neutral';
  return 'positive';
}

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

export function buildBrief(hotspot) {
  const activity = actionLabel(hotspot);
  const lead = hotspot.links?.[0];
  const headline = hotspot.headline || slugHeadline(hotspot.source_url);
  const facts = [];

  if (activity) facts.push(['ACTIVITY', activity]);
  facts.push(['LOCATION', hotspot.location || hotspot.country || 'Unknown']);
  facts.push(['COVERAGE', `${plural(hotspot.outlets ?? 0, 'outlet')} · ${plural(hotspot.articles ?? 0, 'article')}`]);
  if (hotspot.surge != null) {
    facts.push(['SURGE', `×${hotspot.surge.toFixed(1)} vs earlier windows`]);
  } else {
    facts.push(['SURGE', 'no baseline yet']);
  }
  if (typeof hotspot.severity === 'number') facts.push(['SEVERITY', `${hotspot.severity.toFixed(1)} / 10`]);
  if (typeof hotspot.strategic_share === 'number') {
    facts.push(['STATE/ARMED', `${Math.round(hotspot.strategic_share * 100)}% of events`]);
  }
  if (typeof hotspot.tone === 'number') facts.push(['TONE', `${hotspot.tone.toFixed(1)} (${toneLabel(hotspot.tone)})`]);
  if (lead?.actors?.length) facts.push(['ACTORS', lead.actors.join(' → ')]);
  const domain = sourceDomain(hotspot.source_url);
  if (domain) facts.push(['TOP SOURCE', domain]);

  return {
    headline: headline || activity || 'Unidentified activity',
    headlineIsGuess: !hotspot.headline && !!headline, // reconstructed from the URL, not the article's own title
    summary: hotspot.summary || null,
    facts
  };
}
