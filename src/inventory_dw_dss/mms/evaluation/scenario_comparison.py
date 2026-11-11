from itertools import combinations


def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 1.0


def compare_results(results):
    overlap = []
    for (i, a), (j, b) in combinations(enumerate(results), 2):
        ar, br = {r.sku_id for r in a.review_list}, {r.sku_id for r in b.review_list}
        ao, bo = {r.sku_id for r in a.order_proposal}, {r.sku_id for r in b.order_proposal}
        ranks_a, ranks_b = {r.sku_id: r.rank for r in a.review_list}, {r.sku_id: r.rank for r in b.review_list}
        quantities_a = {r.sku_id: r.allocated_q for r in a.review_list}
        quantities_b = {r.sku_id: r.allocated_q for r in b.review_list}
        overlap.append(dict(scenario_a=i, scenario_b=j, review_jaccard=jaccard(ar, br),
            order_jaccard=jaccard(ao, bo), selected_only_a=sorted(ar-br), selected_only_b=sorted(br-ar),
            rank_changes={sku: ranks_b[sku]-ranks_a[sku] for sku in sorted(ar & br)},
            allocated_quantity_changes={sku: quantities_b.get(sku, 0)-quantities_a.get(sku, 0) for sku in sorted(ar | br)}))
    return tuple(overlap)
