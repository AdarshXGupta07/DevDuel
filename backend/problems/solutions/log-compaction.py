import sys
from collections import Counter


def main():
    tokens = sys.stdin.read().split()
    n = int(tokens[0])
    counts = Counter(tokens[1:1 + n])
    for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"{name} {count}")


main()
