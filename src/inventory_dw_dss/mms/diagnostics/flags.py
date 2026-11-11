def diagnostic_flags(row):
    flags = set(row.flags)
    if row.available_stock > 0 and row.sales_90d == 0:
        flags.add("stagnant_inventory")
    # Counts must come from verified daily observations excluding SOP days.
    if ("sop_excluded_diagnostics" in flags and row.diagnostic_observed_days is not None
            and row.observed_stockout_days is not None
            and row.diagnostic_observed_days >= 30
            and row.observed_stockout_days / row.diagnostic_observed_days >= .8):
        flags.add("chronic_stockout")
    if row.sales_90d > 0 and row.sales_7d > 2 * row.vel90 * 7:
        flags.add("demand_spike_informational")
    return tuple(sorted(flags))
