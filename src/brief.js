// Builds the short description shown when hovering an event.
import cameo from './cameo.json';

// How the ETL classified who is involved; it scales the risk score.
const ACTOR_CLASS = {
  'cross-border': 'State or armed actors of two countries (score raised)',
  'state or armed': 'State or armed actors',
  local: 'Local actors only (score reduced)'
};

const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];

// Older data files only carry the code inside the title ("GDELT Event: 192 in TU").
function eventCode(event) {
  if (event.event_code) return String(event.event_code);
  const match = /GDELT Event:\s*(\d{2,4})/i.exec(event.title || '');
  return match ? match[1] : null;
}

export function actionLabel(event) {
  const code = eventCode(event);
  if (!code) return null;
  return cameo[code.slice(0, 3)] || cameo[code.slice(0, 2)] || null;
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

function formatDate(timestamp) {
  const date = new Date(timestamp);
  if (isNaN(date)) return null;
  return `${String(date.getUTCDate()).padStart(2, '0')} ${MONTHS[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
}

function toneLabel(tone) {
  if (tone <= -5) return 'very negative';
  if (tone < -1) return 'negative';
  if (tone <= 1) return 'neutral';
  return 'positive';
}

export function buildBrief(event) {
  const action = actionLabel(event);
  const code = eventCode(event);
  const headline = event.headline || slugHeadline(event.source_url);
  const facts = [];

  if (action) facts.push(['ACTION', `${action}${code ? ` (CAMEO ${code})` : ''}`]);
  facts.push(['LOCATION', event.location || event.country || 'Unknown']);
  if (event.actors?.length) facts.push(['ACTORS', event.actors.join(' → ')]);
  if (event.actor_class) facts.push(['INVOLVES', ACTOR_CLASS[event.actor_class] || event.actor_class]);
  const date = formatDate(event.timestamp);
  if (date) facts.push(['DATE', date]);
  if (typeof event.tone === 'number') facts.push(['TONE', `${event.tone.toFixed(1)} (${toneLabel(event.tone)})`]);
  if (event.articles) facts.push(['COVERAGE', `${event.articles} article${event.articles === 1 ? '' : 's'}`]);
  const domain = sourceDomain(event.source_url);
  if (domain) facts.push(['SOURCE', domain]);

  return {
    headline: headline || action || event.title || 'Unidentified event',
    headlineIsGuess: !event.headline && !!headline, // reconstructed from the URL, not the article's own title
    summary: event.summary || null,
    facts
  };
}
