/**
 * Rank tiers.
 *
 * Deliberately a pure function of rating with no server round-trip: the tier is derived
 * data, not stored state. If it lived in the database it could disagree with the rating
 * it came from, and then you have two sources of truth for the same fact.
 */

export const TIERS = [
  { name: 'Bronze', min: 0, max: 1199, color: '#c17c4a', dim: '#5e3c22' },
  { name: 'Silver', min: 1200, max: 1499, color: '#b9c2cc', dim: '#5b626a' },
  { name: 'Gold', min: 1500, max: 1799, color: '#ffc93f', dim: '#7d631c' },
  { name: 'Platinum', min: 1800, max: 2099, color: '#5ee9d0', dim: '#20705f' },
  { name: 'Diamond', min: 2100, max: 2399, color: '#6cb6ff', dim: '#26516f' },
  { name: 'Master', min: 2400, max: Infinity, color: '#d98bff', dim: '#5b3175' },
];

export function tierFor(rating = 1200) {
  return TIERS.find((t) => rating >= t.min && rating <= t.max) ?? TIERS[0];
}

export function nextTier(rating = 1200) {
  const i = TIERS.indexOf(tierFor(rating));
  return i < TIERS.length - 1 ? TIERS[i + 1] : null;
}

/** Progress through the current tier, 0–1. Master is always full — there is no next. */
export function tierProgress(rating = 1200) {
  const tier = tierFor(rating);
  if (!Number.isFinite(tier.max)) return 1;
  return Math.min(1, Math.max(0, (rating - tier.min) / (tier.max - tier.min + 1)));
}

export function ratingToNextTier(rating = 1200) {
  const tier = tierFor(rating);
  return Number.isFinite(tier.max) ? tier.max + 1 - rating : 0;
}
