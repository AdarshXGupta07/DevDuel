import sys


def main():
    data = sys.stdin.buffer.read().split()
    n = int(data[0])
    changes = [int(x) for x in data[1:1 + n]]

    best = current = changes[0]
    for value in changes[1:]:
        current = max(value, current + value)
        best = max(best, current)
    print(best)


main()
