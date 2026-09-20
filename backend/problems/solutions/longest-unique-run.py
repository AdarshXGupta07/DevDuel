import sys


def main():
    line = sys.stdin.readline()
    log = line.strip()

    last_seen = {}
    best = 0
    start = 0
    for i, ch in enumerate(log):
        # Only move the window start forwards — a repeat from before the current window
        # has already been stepped past and must not drag it backwards.
        if ch in last_seen and last_seen[ch] >= start:
            start = last_seen[ch] + 1
        last_seen[ch] = i
        best = max(best, i - start + 1)

    print(best)


main()
