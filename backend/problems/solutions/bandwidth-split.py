import sys


def main():
    data = sys.stdin.buffer.read().split()
    n, k = int(data[0]), int(data[1])
    sizes = [int(x) for x in data[2:2 + n]]

    def workers_needed(cap: int) -> int:
        """How many workers if none may exceed `cap`. Greedy is optimal here."""
        used, current = 1, 0
        for size in sizes:
            if current + size > cap:
                used += 1
                current = size
            else:
                current += size
        return used

    # Search on the answer: the cap is monotonic — if `cap` works, so does anything
    # larger — so binary search over the value rather than over the assignments.
    lo, hi = max(sizes), sum(sizes)
    while lo < hi:
        mid = (lo + hi) // 2
        if workers_needed(mid) <= k:
            hi = mid
        else:
            lo = mid + 1
    print(lo)


main()
