/**
 * Mock data — ONLY for surfaces with no backend behind them yet.
 *
 * Auth, matchmaking, live duels, match history and the leaderboard all call the real
 * API and are not mocked. What is mocked here is what genuinely does not exist server
 * side yet: analytics aggregates, AI code review, the AI opponent's simulated pacing,
 * and global rank position.
 *
 * Every export is named `mock*` so it is obvious at the call site which parts of a
 * screen are real and which are placeholder.
 */

export const mockTopicStrength = [
  { topic: 'Arrays', solved: 42, attempted: 48, accuracy: 0.87 },
  { topic: 'Strings', solved: 31, attempted: 38, accuracy: 0.82 },
  { topic: 'Hashing', solved: 24, attempted: 28, accuracy: 0.86 },
  { topic: 'Sorting / Searching', solved: 19, attempted: 25, accuracy: 0.76 },
  { topic: 'Linked Lists', solved: 12, attempted: 19, accuracy: 0.63 },
  { topic: 'Trees', solved: 14, attempted: 26, accuracy: 0.54 },
  { topic: 'Recursion / Backtracking', solved: 8, attempted: 18, accuracy: 0.44 },
  { topic: 'Graphs', solved: 6, attempted: 17, accuracy: 0.35 },
  { topic: 'Dynamic Programming', solved: 4, attempted: 21, accuracy: 0.19 },
  { topic: 'Greedy', solved: 7, attempted: 15, accuracy: 0.47 },
  { topic: 'Bit Manipulation', solved: 3, attempted: 9, accuracy: 0.33 },
];

export const mockRatingHistory = [
  { date: '2026-07-14', rating: 1200 },
  { date: '2026-07-21', rating: 1184 },
  { date: '2026-07-28', rating: 1231 },
  { date: '2026-08-04', rating: 1262 },
  { date: '2026-08-11', rating: 1248 },
  { date: '2026-08-18', rating: 1297 },
  { date: '2026-08-25', rating: 1341 },
  { date: '2026-09-01', rating: 1319 },
  { date: '2026-09-08', rating: 1372 },
  { date: '2026-09-15', rating: 1408 },
];

export const mockWinRateTrend = [
  { week: 'W1', winRate: 0.42, avgSolveSeconds: 780 },
  { week: 'W2', winRate: 0.45, avgSolveSeconds: 742 },
  { week: 'W3', winRate: 0.51, avgSolveSeconds: 690 },
  { week: 'W4', winRate: 0.48, avgSolveSeconds: 665 },
  { week: 'W5', winRate: 0.56, avgSolveSeconds: 601 },
  { week: 'W6', winRate: 0.61, avgSolveSeconds: 574 },
];

export const mockGlobalPosition = { rank: 1204, totalPlayers: 18422 };

export const mockStreak = { current: 4, best: 11 };

/**
 * The AI opponent's simulated progress.
 *
 * Note what this is NOT: it does not run code. It replays a believable timeline of
 * events for a player at a given rating — which is the scripted approach from the plan,
 * chosen because it is three days of work instead of three weeks and cannot lose money
 * on inference. Times are seconds from duel start.
 */
export function mockAiTimeline(rating = 1200) {
  // Stronger opponents act sooner and waste fewer submissions.
  const pace = Math.max(0.55, Math.min(1.6, 1600 / Math.max(rating, 600)));
  const at = (s) => Math.round(s * pace);
  return [
    { at: at(4), state: 'typing' },
    { at: at(95), state: 'running', passed: 1, total: 2 },
    { at: at(150), state: 'typing' },
    { at: at(260), state: 'running', passed: 2, total: 2 },
    { at: at(300), state: 'submitting' },
    { at: at(315), state: 'ran_tests', passed: 4, total: 5, note: 'wrong_answer' },
    { at: at(360), state: 'typing' },
    { at: at(470), state: 'submitting' },
    { at: at(485), state: 'solved' },
  ];
}

export const mockAiReview = {
  verdict: 'Correct, but heavier than it needs to be',
  complexity: { time: 'O(n log n)', optimal: 'O(n)' },
  strengths: [
    'Handles the empty-input edge case explicitly rather than relying on a truthiness check.',
    'Variable names read as domain terms (`window`, `best`) instead of `a`, `b`, `tmp`.',
  ],
  issues: [
    {
      title: 'Sorting to find a maximum',
      detail:
        'You sort the whole array to read one value from it. That is O(n log n) work for an O(n) question — a single pass tracking the running maximum gives the same answer.',
    },
    {
      title: 'Recomputing the window sum each step',
      detail:
        'The inner loop re-adds every element of the window on each iteration. Subtracting the outgoing element and adding the incoming one keeps it O(1) per step.',
    },
  ],
  alternative: `window = sum(buckets[:k])
best = window
for i in range(k, n):
    window += buckets[i] - buckets[i - k]
    best = max(best, window)
print(best)`,
  alternativeNote:
    'The sliding window never recomputes what it already knows — each step costs one addition and one subtraction regardless of k.',
};
