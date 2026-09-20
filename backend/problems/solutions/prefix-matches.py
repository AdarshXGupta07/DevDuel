import sys
from collections import Counter


def main():
    data = sys.stdin.buffer.read().split()
    n, q = int(data[0]), int(data[1])
    commands = data[2:2 + n]
    queries = data[2 + n:2 + n + q]

    # A trie is the textbook answer, but with prefixes capped at 20 characters, counting
    # every prefix of every command into one dict is O(total length) and far simpler —
    # each lookup is then a single hash. The trie wins only when memory is tight.
    counts = Counter()
    for command in commands:
        for i in range(1, len(command) + 1):
            counts[command[:i]] += 1

    out = [str(counts.get(query, 0)) for query in queries]
    sys.stdout.write("\n".join(out))


main()
