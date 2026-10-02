// Standard text-token reference rates reviewed on 2026-09-30.
const rates: Record<string, { input: number; output: number; source: string }> =
  {
    'gpt-5.4-mini': {
      input: 0.75,
      output: 4.5,
      source: 'https://developers.openai.com/api/docs/models/gpt-5.4-mini',
    },
    'gpt-5.4-nano': {
      input: 0.2,
      output: 1.25,
      source: 'https://developers.openai.com/api/docs/models/gpt-5.4-nano',
    },
  }
export function priceReference(model: string) {
  const rate = rates[model]
  if (!rate) return null
  return {
    ...rate,
    reviewedAt: '2026-09-30',
    cost: (input: number, output: number) =>
      (input * rate.input + output * rate.output) / 1_000_000,
  }
}
