import test from "node:test";
import assert from "node:assert/strict";

globalThis.document = undefined;
globalThis.localStorage = {
  getItem() {
    return null;
  },
};

const {
  formatDateTime,
  formatScore,
  formatScoreAsPoints,
  normalizeAiBase,
  normalizeApiBase,
  scoreTone,
  scoreToPercent,
  summarizePage,
} = await import("./app.js");

test("normalizeApiBase trims trailing slashes and falls back to localhost API", () => {
  assert.equal(normalizeApiBase(" http://localhost:8081/// "), "http://localhost:8081");
  assert.equal(normalizeApiBase(""), "http://localhost:8081");
});

test("normalizeAiBase trims trailing slashes and falls back to localhost AI engine", () => {
  assert.equal(normalizeAiBase(" http://localhost:8000/// "), "http://localhost:8000");
  assert.equal(normalizeAiBase(""), "http://localhost:8000");
});

test("scoreToPercent maps sentiment from -1..1 and clamps out of range values", () => {
  assert.equal(scoreToPercent(-1, "sentiment"), 0);
  assert.equal(scoreToPercent(0, "sentiment"), 50);
  assert.equal(scoreToPercent(1, "sentiment"), 100);
  assert.equal(scoreToPercent(2, "sentiment"), 100);
});

test("scoreToPercent maps bounded ratio scores to percentages", () => {
  assert.equal(scoreToPercent(0.24, "bias"), 24);
  assert.equal(scoreToPercent(0.876, "factuality"), 88);
  assert.equal(scoreToPercent(-0.1, "bias"), 0);
  assert.equal(scoreToPercent(1.5, "bias"), 100);
});

test("formatScore renders numeric scores with two decimal places", () => {
  assert.equal(formatScore(0.2), "0.20");
  assert.equal(formatScore(0.876), "0.88");
  assert.equal(formatScore(null), "-");
});

test("formatScoreAsPoints renders normalized scores on a 100 point scale", () => {
  assert.equal(formatScoreAsPoints(-1, "sentiment"), "0점");
  assert.equal(formatScoreAsPoints(0, "sentiment"), "50점");
  assert.equal(formatScoreAsPoints(0.876, "factuality"), "88점");
  assert.equal(formatScoreAsPoints(null, "bias"), "-");
});

test("scoreTone maps score meaning to visual severity", () => {
  assert.equal(scoreTone(0.8, "sentiment"), "good");
  assert.equal(scoreTone(-0.8, "sentiment"), "bad");
  assert.equal(scoreTone(0.2, "bias"), "good");
  assert.equal(scoreTone(0.9, "bias"), "bad");
  assert.equal(scoreTone(0.8, "factuality"), "good");
  assert.equal(scoreTone(0.2, "factuality"), "bad");
});

test("summarizePage normalizes Spring Data page responses", () => {
  const summary = summarizePage({
    content: [{ id: 1 }],
    page: {
      number: 2,
      size: 5,
      totalElements: 14,
      totalPages: 3,
    },
  });

  assert.deepEqual(summary, {
    content: [{ id: 1 }],
    number: 2,
    size: 5,
    totalElements: 14,
    totalPages: 3,
  });
});

test("formatDateTime returns a fallback for invalid dates", () => {
  assert.equal(formatDateTime("not-a-date"), "-");
  assert.match(formatDateTime("2026-06-06T09:00:00+09:00"), /2026/);
});
