import sys


def main():
    data = sys.stdin.buffer.read().split()
    n = int(data[0])
    amounts = [int(x) for x in data[1:1 + n]]

    # Iterative doubling rather than recursion: each new item either joins every total
    # seen so far or does not, so the list doubles per item. Same 2^n work, no stack.
    totals = [0]
    for amount in amounts:
        totals += [t + amount for t in totals]

    totals.sort()
    sys.stdout.write(" ".join(map(str, totals)))


main()
