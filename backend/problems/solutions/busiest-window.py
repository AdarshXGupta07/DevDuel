import sys


def main():
    data = sys.stdin.read().split()
    n, k = int(data[0]), int(data[1])
    buckets = [int(x) for x in data[2:2 + n]]
    window = sum(buckets[:k])
    best = window
    for i in range(k, n):
        window += buckets[i] - buckets[i - k]
        if window > best:
            best = window
    print(best)


main()
