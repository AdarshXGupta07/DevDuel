import sys


def main():
    data = sys.stdin.buffer.read().split()
    n = int(data[0])
    cost = [int(x) for x in data[1:1 + n]]

    # prev2 = cheapest way to stand before version i-2, prev1 = before i-1.
    # Starting at either version 0 or 1 is free, which is why both begin at 0.
    prev2 = prev1 = 0
    for i in range(2, n + 1):
        current = min(prev1 + cost[i - 1], prev2 + cost[i - 2])
        prev2, prev1 = prev1, current
    print(prev1)


main()
