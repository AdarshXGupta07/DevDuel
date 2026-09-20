import sys
from bisect import bisect_left


def main():
    data = sys.stdin.buffer.read().split()
    n, q = int(data[0]), int(data[1])
    times = [int(x) for x in data[2:2 + n]]
    queries = [int(x) for x in data[2 + n:2 + n + q]]

    out = [str(bisect_left(times, x)) for x in queries]
    sys.stdout.write(" ".join(out))


main()
