---
name: log-expense
description: Turn casual spending notes into clean expense entries (date, amount, category, note). Use whenever the user mentions spending or paying money, even briefly like 'uber 180', 'paid rent 15000' or 'spent 250 on lunch'.
---

# Log an expense

Turn a casual note about spending into clean, consistent expense entries, so the user can track money without typing a formal record.

## Steps

1. Read the user's note and pull out, for each expense:
   - **Date**: the date they mention; otherwise today's date (YYYY-MM-DD). "yesterday" = today minus one day. If one date is mentioned once for several items ("coffee 120, metro 40 yesterday"), apply it to all of them.
   - **Amount**: the number they spent. Assume Indian Rupees (₹) unless another currency is given; keep that currency's symbol if so (e.g. $15).
   - **Category**: one of Food, Travel, Bills, Shopping, Health, Entertainment, Other. Use Other only when nothing else fits, so categories stay useful for totals.
   - **Note**: a short description (2-5 words), e.g. "Lunch with team".
2. If an amount is missing, ask for it. Never guess amounts, because a wrong number silently corrupts the user's records. Everything else can be inferred.
3. For a single expense, reply in this format:

```
Date: 2026-10-03
Amount: ₹250
Category: Food
Note: Lunch
```

4. For several expenses, show one table with a total row:

| Date | Amount | Category | Note |
|---|---|---|---|
| 2026-10-02 | ₹120 | Food | Coffee |
| 2026-10-02 | ₹600 | Entertainment | Movie tickets |
| **Total** | **₹720** | | |

If currencies differ, total each currency separately.

## Examples

- "spent 250 on lunch" → today, ₹250, Food, Lunch
- "uber 180 yesterday" → yesterday's date, ₹180, Travel, Uber ride
- "paid electricity bill 1200" → today, ₹1200, Bills, Electricity bill
- "$15 netflix" → today, $15, Entertainment, Netflix subscription
- "bought groceries" → ask: "How much did you spend on groceries?"