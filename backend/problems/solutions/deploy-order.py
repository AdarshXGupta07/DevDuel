import heapq
import sys


def main():
    data = sys.stdin.buffer.read().split()
    n, m = int(data[0]), int(data[1])

    adj = [[] for _ in range(n + 1)]
    indegree = [0] * (n + 1)
    for i in range(m):
        a, b = int(data[2 + 2 * i]), int(data[3 + 2 * i])
        # a depends on b, so b must come first: edge b -> a
        adj[b].append(a)
        indegree[a] += 1

    heap = [v for v in range(1, n + 1) if indegree[v] == 0]
    heapq.heapify(heap)

    order = []
    while heap:
        v = heapq.heappop(heap)
        order.append(v)
        for nxt in adj[v]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(heap, nxt)

    if len(order) != n:
        print("CYCLE")
    else:
        print(" ".join(map(str, order)))


main()
