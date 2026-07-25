# Representative option and upload-order control

Use this reference after the thumbnail/detail review and Korean option-name cleanup are complete.

## Selection rule

1. Identify the advertised main product from the thumbnail and detail page before comparing prices.
2. From all selectable rows, retain only complete sellable variants of that main product.
3. Remove notices, deposits, shipping-only rows, forbidden-purchase rows, accessories, unrelated models, incomplete sets, and misleading low-price rows before choosing a representative.
4. Compare the actual upload sale price only inside the retained main-product group.
5. Select the lowest-sale-price row as the representative. If prices tie, prefer the row that most directly matches the thumbnail/detail; if still tied, preserve original source order.
6. Compute the upper bound as `representative sale price × 1.5`. Keep rows at or below the bound and exclude rows above it.
7. Sort the retained rows by upload sale price ascending. Preserve original order among equal-price rows.
8. Persist that exact sorted order as the upload order. The representative must be the first retained row.

## Save sequence

Option-name changes and order changes must be separate writes.

1. Read the latest full work data and keep a pre-write snapshot.
2. Save Korean option names and inclusion/exclusion changes first.
3. Read back and verify names, length, dimensions, and inclusion state.
4. Re-read prices, recompute the representative and 1.5× upper bound, and rebuild the retained order.
5. Directly designate exactly one retained SKU as representative.
6. Save the retained SKUs in the computed ascending-price upload order.
7. Read back and verify representative, inclusion range, prices, and order.
8. If verification fails, stop marketplace work, restore the snapshot where possible, and report the mismatch.

## Dimension safety

- Resolve a row by complete SKU identity, never by an option-value number that may be reused across dimensions.
- In two-dimensional options, use a dimension-aware rename path when the same value number appears in both dimensions.
- Never allow an excluded or non-product row to become representative.

## Verification

The final saved state must satisfy all of the following:

- exactly one representative exists;
- it is an included complete variant of the thumbnail/detail main product;
- it has the lowest upload sale price in the retained main-product group;
- every retained row is at or below 1.5× the representative price;
- every excluded-over-limit row is above that bound;
- retained rows are in ascending upload-sale-price order;
- equal-price rows preserve original order;
- the saved upload order matches the computed order;
- Korean option names remain correct after reordering;
- prices and stock were not changed unless separately requested.

## Safety boundary

Changing the Bulsaja representative, inclusion state, names, or upload order does not authorize an update to an already-listed marketplace product. Marketplace registration, update, or deletion requires separate seller approval and post-write verification.
