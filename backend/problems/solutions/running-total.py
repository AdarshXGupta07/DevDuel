import sys


def main():
    data = sys.stdin.read().split()
    n = int(data[0])
    counts = [int(x) for x in data[1:1 + n]]
    out = []
    total = 0
    for c in counts:
        total += c
        out.append(str(total))
    print(" ".join(out))


main()
