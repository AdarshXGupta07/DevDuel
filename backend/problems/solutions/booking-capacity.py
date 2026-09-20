import sys


def main():
    data = sys.stdin.buffer.read().split()
    n = int(data[0])
    bookings = [(int(data[1 + 2 * i]), int(data[2 + 2 * i])) for i in range(n)]

    # Sort by END time, not start and not duration. Taking the booking that frees the
    # room earliest always leaves at least as much room for the rest — the exchange
    # argument behind classic activity selection.
    bookings.sort(key=lambda b: b[1])

    taken = 0
    free_from = None
    for start, end in bookings:
        if free_from is None or start >= free_from:
            taken += 1
            free_from = end
    print(taken)


main()
