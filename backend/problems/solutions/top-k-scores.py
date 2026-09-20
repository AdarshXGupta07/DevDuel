import sys
import heapq


def main():
    data = sys.stdin.buffer.read().split()
    n, k = int(data[0]), int(data[1])
    scores = [int(x) for x in data[2:2 + n]]

    # A min-heap of size k: the smallest of the current best-k sits on top, so each new
    # score is one comparison away from being discarded. O(n log k), O(k) space.
    heap = scores[:k]
    heapq.heapify(heap)
    for score in scores[k:]:
        if score > heap[0]:
            heapq.heapreplace(heap, score)

    heap.sort(reverse=True)
    sys.stdout.write(" ".join(map(str, heap)))


main()
