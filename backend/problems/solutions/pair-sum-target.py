import sys
from collections import Counter


def main():
    data = sys.stdin.buffer.read().split()
    n = int(data[0])
    amounts = [int(x) for x in data[1:1 + n]]
    target = int(data[1 + n])

    seen = Counter()
    pairs = 0
    for value in amounts:
        pairs += seen[target - value]
        seen[value] += 1
    print(pairs)


main()
