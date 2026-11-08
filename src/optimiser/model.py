"""The optimiser's maths, shared by demand.py and optimise.py. The map (optimiser/template.html) has a
line-by-line JavaScript copy, checked by src/optimiser/check_page.py.

Expected late orders in a zone with `orders` per hour and `couriers` positioned there:
    load = orders x minutes_with_courier / 60 / couriers          (Little's law: orders carried per courier)
    late = orders x max(floor, a + b x ln(load))                  (response curve calibrated on Meituan)
This is convex and decreasing in couriers, so giving each next courier to the zone where it removes the
most late orders (greedy marginal allocation) is exactly optimal. optimise.py checks this against an
integer program (PuLP / CBC).
"""
import heapq
import math


def late(orders, couriers, p):
    if orders <= 0:
        return 0.0
    load = orders * p["minutes_with_courier"] / 60 / max(couriers, 1e-9)
    return orders * max(p["curve_floor"], p["curve_a"] + p["curve_b"] * math.log(load))


def floor_for(total, zones, minimum):
    """The per-zone minimum only applies when there are at least that many couriers for every zone."""
    return minimum if total >= minimum * zones else 0


def greedy(orders, total, p, minimum=1):
    """Optimal allocation of `total` couriers over zones. Returns the allocation and the late count after
    each courier is placed (index k = late with minimum*zones + k couriers), used for 'couriers saved'."""
    n = len(orders)
    minimum = floor_for(total, n, minimum)
    alloc = [minimum] * n
    heap = [(-(late(o, minimum, p) - late(o, minimum + 1, p)), i) for i, o in enumerate(orders)]
    heapq.heapify(heap)
    current = sum(late(o, minimum, p) for o in orders)
    path = [current]
    for _ in range(max(0, total - minimum * n)):
        gain, i = heapq.heappop(heap)
        alloc[i] += 1
        current += gain
        path.append(current)
        heapq.heappush(heap, (-(late(orders[i], alloc[i], p) - late(orders[i], alloc[i] + 1, p)), i))
    return alloc, path


def proportional(weights, total, minimum=1):
    """Spread `total` couriers in proportion to `weights` (largest remainder), with a minimum per zone."""
    n = len(weights)
    minimum = floor_for(total, n, minimum)
    spare = total - minimum * n
    s = sum(weights) or 1
    raw = [spare * w / s for w in weights]
    alloc = [minimum + int(r) for r in raw]
    order = sorted(range(n), key=lambda i: (-(raw[i] - int(raw[i])), i))
    for i in order[:total - sum(alloc)]:
        alloc[i] += 1
    return alloc


def total_late(orders, alloc, p):
    return sum(late(o, a, p) for o, a in zip(orders, alloc))


def moves(base, target, names):
    """Pair zones with too many couriers with zones that need more, largest first."""
    give = sorted([[b - t, i] for i, (b, t) in enumerate(zip(base, target)) if b > t], key=lambda x: (-x[0], x[1]))
    need = sorted([[t - b, i] for i, (b, t) in enumerate(zip(base, target)) if t > b], key=lambda x: (-x[0], x[1]))
    out, gi = [], 0
    for amount, j in need:
        while amount > 0 and gi < len(give):
            k = min(amount, give[gi][0])
            out.append((names[give[gi][1]], names[j], k))
            amount -= k
            give[gi][0] -= k
            if give[gi][0] == 0:
                gi += 1
    return out


def couriers_saved(path, base_late, total):
    """How many fewer couriers, optimally placed, still match the baseline's late orders.
    path[k] = late orders with (total - len(path) + 1 + k) couriers; path[-1] uses all `total`."""
    start = total - (len(path) - 1)
    for k, value in enumerate(path):
        if value <= base_late + 1e-9:
            return total - (start + k)
    return 0
