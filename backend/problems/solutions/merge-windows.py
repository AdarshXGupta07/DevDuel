import sys


def main():
    data = sys.stdin.buffer.read().split()
    n = int(data[0])
    windows = [(int(data[1 + 2 * i]), int(data[2 + 2 * i])) for i in range(n)]
    windows.sort()

    out = []
    start, end = windows[0]
    for s, e in windows[1:]:
        if s <= end:          # overlapping, or touching exactly at `end`
            end = max(end, e)
        else:
            out.append(f"{start} {end}")
            start, end = s, e
    out.append(f"{start} {end}")

    sys.stdout.write("\n".join(out))


main()
