import sys


def main():
    data = sys.stdin.buffer.read().split()
    n, head = int(data[0]), int(data[1])
    values = [int(x) for x in data[2:2 + n]]
    nxt = [int(x) for x in data[2 + n:2 + 2 * n]]

    # Walk the chain collecting values, then reverse. Reversing the traversal order is
    # the same answer as reversing the pointers, and costs one list instead of a rewire.
    order = []
    node = head
    while node != -1:
        order.append(values[node])
        node = nxt[node]

    order.reverse()
    sys.stdout.write(" ".join(map(str, order)))


main()
